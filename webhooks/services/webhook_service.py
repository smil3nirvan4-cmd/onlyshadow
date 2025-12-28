"""
S.S.I. SHADOW - Webhook Service
===============================
Service for managing and delivering webhooks.
"""

import os
import logging
import asyncio
import json
import hmac
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import time

import httpx

from webhooks.models.entities import (
    WebhookConfig,
    WebhookCreate,
    WebhookUpdate,
    WebhookPayload,
    WebhookDelivery,
    DeliveryAttempt,
    DeliveryStatus,
    WebhookEvent,
)

logger = logging.getLogger(__name__)


class WebhookService:
    """
    Service for managing webhooks and delivering payloads.
    """
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        
        # HTTP client for deliveries
        self.http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True
        )
        
        # In-memory stores (replace with database in production)
        self.webhooks: Dict[str, WebhookConfig] = {}
        self.deliveries: Dict[str, WebhookDelivery] = {}
        self.attempts: Dict[str, List[DeliveryAttempt]] = {}
        
        # Delivery queue (replace with Redis/RabbitMQ in production)
        self.delivery_queue: asyncio.Queue = asyncio.Queue()
        
        # Background task
        self._worker_task: Optional[asyncio.Task] = None
        self._running = False
    
    # =========================================================================
    # WEBHOOK CRUD
    # =========================================================================
    
    async def create_webhook(
        self,
        org_id: str,
        data: WebhookCreate,
        created_by: str
    ) -> WebhookConfig:
        """Create a new webhook."""
        webhook = WebhookConfig(
            organization_id=org_id,
            name=data.name,
            url=str(data.url),
            events=data.events,
            headers=data.headers,
            verify_ssl=data.verify_ssl,
            created_by=created_by
        )
        
        self.webhooks[webhook.id] = webhook
        logger.info(f"Webhook created: {webhook.id} ({webhook.name})")
        
        return webhook
    
    async def get_webhook(self, webhook_id: str) -> Optional[WebhookConfig]:
        """Get a webhook by ID."""
        return self.webhooks.get(webhook_id)
    
    async def get_webhooks_by_organization(self, org_id: str) -> List[WebhookConfig]:
        """Get all webhooks for an organization."""
        return [
            wh for wh in self.webhooks.values()
            if wh.organization_id == org_id
        ]
    
    async def get_webhooks_for_event(
        self,
        org_id: str,
        event_type: WebhookEvent
    ) -> List[WebhookConfig]:
        """Get all active webhooks subscribed to an event."""
        return [
            wh for wh in self.webhooks.values()
            if wh.organization_id == org_id
            and wh.is_active
            and event_type in wh.events
        ]
    
    async def update_webhook(
        self,
        webhook_id: str,
        data: WebhookUpdate
    ) -> Optional[WebhookConfig]:
        """Update a webhook."""
        webhook = self.webhooks.get(webhook_id)
        if not webhook:
            return None
        
        if data.name is not None:
            webhook.name = data.name
        if data.url is not None:
            webhook.url = str(data.url)
        if data.events is not None:
            webhook.events = data.events
        if data.headers is not None:
            webhook.headers = data.headers
        if data.is_active is not None:
            webhook.is_active = data.is_active
        if data.verify_ssl is not None:
            webhook.verify_ssl = data.verify_ssl
        
        webhook.updated_at = datetime.utcnow()
        
        return webhook
    
    async def delete_webhook(self, webhook_id: str) -> bool:
        """Delete a webhook."""
        if webhook_id in self.webhooks:
            del self.webhooks[webhook_id]
            return True
        return False
    
    async def rotate_secret(self, webhook_id: str) -> Optional[str]:
        """Rotate webhook secret."""
        webhook = self.webhooks.get(webhook_id)
        if not webhook:
            return None
        
        import uuid
        webhook.secret = f"whsec_{uuid.uuid4().hex}"
        webhook.updated_at = datetime.utcnow()
        
        return webhook.secret
    
    # =========================================================================
    # SIGNATURE
    # =========================================================================
    
    def sign_payload(self, payload: str, secret: str) -> str:
        """
        Generate HMAC-SHA256 signature for payload.
        
        Returns:
            Signature in format: sha256=<hex_digest>
        """
        signature = hmac.new(
            secret.encode(),
            payload.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return f"sha256={signature}"
    
    def verify_signature(
        self,
        payload: str,
        signature: str,
        secret: str
    ) -> bool:
        """Verify a webhook signature."""
        expected = self.sign_payload(payload, secret)
        return hmac.compare_digest(signature, expected)
    
    # =========================================================================
    # DELIVERY
    # =========================================================================
    
    async def dispatch_event(
        self,
        org_id: str,
        event_type: WebhookEvent,
        data: Dict[str, Any],
        metadata: Dict[str, Any] = None
    ):
        """
        Dispatch an event to all subscribed webhooks.
        """
        # Get subscribed webhooks
        webhooks = await self.get_webhooks_for_event(org_id, event_type)
        
        if not webhooks:
            logger.debug(f"No webhooks for event {event_type} in org {org_id}")
            return
        
        # Create payload
        payload = WebhookPayload(
            type=event_type.value if isinstance(event_type, WebhookEvent) else event_type,
            organization_id=org_id,
            data=data,
            metadata=metadata or {}
        )
        
        # Queue deliveries
        for webhook in webhooks:
            delivery = WebhookDelivery(
                webhook_id=webhook.id,
                organization_id=org_id,
                payload_id=payload.id,
                event_type=payload.type,
                request_url=webhook.url,
                request_body=json.dumps(payload.to_dict()),
                max_attempts=webhook.max_retries
            )
            
            self.deliveries[delivery.id] = delivery
            await self.delivery_queue.put((delivery.id, webhook))
        
        logger.info(f"Dispatched event {event_type} to {len(webhooks)} webhooks")
    
    async def deliver_webhook(
        self,
        delivery_id: str,
        webhook: WebhookConfig
    ) -> bool:
        """
        Attempt to deliver a webhook.
        
        Returns:
            True if successful, False otherwise
        """
        delivery = self.deliveries.get(delivery_id)
        if not delivery:
            return False
        
        delivery.status = DeliveryStatus.DELIVERING
        delivery.attempt_count += 1
        
        # Prepare request
        payload_str = delivery.request_body
        signature = self.sign_payload(payload_str, webhook.secret)
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SSI-Shadow-Webhook/1.0",
            "X-SSI-Signature": signature,
            "X-SSI-Event": delivery.event_type,
            "X-SSI-Delivery": delivery.id,
            "X-SSI-Timestamp": datetime.utcnow().isoformat(),
            **webhook.headers
        }
        
        delivery.request_headers = headers
        
        # Create attempt record
        attempt = DeliveryAttempt(
            delivery_id=delivery_id,
            attempt_number=delivery.attempt_count
        )
        
        start_time = time.time()
        
        try:
            response = await self.http_client.post(
                webhook.url,
                content=payload_str,
                headers=headers,
                timeout=30.0
            )
            
            end_time = time.time()
            response_time_ms = (end_time - start_time) * 1000
            
            # Record response
            attempt.response_status = response.status_code
            attempt.response_body = response.text[:1000]  # Limit size
            attempt.response_time_ms = response_time_ms
            
            delivery.response_status = response.status_code
            delivery.response_headers = dict(response.headers)
            delivery.response_body = response.text[:1000]
            delivery.response_time_ms = response_time_ms
            
            # Check success (2xx status)
            if 200 <= response.status_code < 300:
                delivery.status = DeliveryStatus.DELIVERED
                delivery.delivered_at = datetime.utcnow()
                attempt.success = True
                
                # Update webhook stats
                webhook.total_deliveries += 1
                webhook.successful_deliveries += 1
                webhook.last_delivery_at = datetime.utcnow()
                webhook.last_status = "success"
                
                logger.info(f"Webhook delivered: {delivery_id} -> {response.status_code}")
                return True
            else:
                # Non-2xx response
                attempt.error = f"HTTP {response.status_code}"
                delivery.error_message = f"HTTP {response.status_code}: {response.text[:200]}"
                
        except httpx.TimeoutException:
            attempt.error = "Timeout"
            delivery.error_message = "Request timed out after 30s"
            logger.warning(f"Webhook timeout: {delivery_id}")
            
        except httpx.RequestError as e:
            attempt.error = str(e)
            delivery.error_message = f"Request error: {str(e)}"
            logger.warning(f"Webhook request error: {delivery_id} - {e}")
            
        except Exception as e:
            attempt.error = str(e)
            delivery.error_message = f"Unexpected error: {str(e)}"
            logger.error(f"Webhook error: {delivery_id} - {e}")
        
        # Store attempt
        if delivery_id not in self.attempts:
            self.attempts[delivery_id] = []
        self.attempts[delivery_id].append(attempt)
        
        # Schedule retry if possible
        if delivery.attempt_count < delivery.max_attempts:
            retry_index = min(delivery.attempt_count - 1, len(webhook.retry_backoff) - 1)
            retry_delay = webhook.retry_backoff[retry_index]
            delivery.status = DeliveryStatus.RETRYING
            delivery.next_retry_at = datetime.utcnow() + timedelta(seconds=retry_delay)
            
            # Schedule retry (in production, use a proper job queue)
            asyncio.create_task(self._schedule_retry(delivery_id, webhook, retry_delay))
            
            logger.info(f"Webhook retry scheduled: {delivery_id} in {retry_delay}s")
        else:
            # Max retries exceeded
            delivery.status = DeliveryStatus.FAILED
            webhook.total_deliveries += 1
            webhook.failed_deliveries += 1
            webhook.last_status = "failed"
            
            logger.warning(f"Webhook failed after {delivery.attempt_count} attempts: {delivery_id}")
        
        return False
    
    async def _schedule_retry(
        self,
        delivery_id: str,
        webhook: WebhookConfig,
        delay: int
    ):
        """Schedule a retry after delay."""
        await asyncio.sleep(delay)
        await self.delivery_queue.put((delivery_id, webhook))
    
    # =========================================================================
    # DELIVERY LOGS
    # =========================================================================
    
    async def get_delivery(self, delivery_id: str) -> Optional[WebhookDelivery]:
        """Get a delivery by ID."""
        return self.deliveries.get(delivery_id)
    
    async def get_deliveries_for_webhook(
        self,
        webhook_id: str,
        limit: int = 100,
        offset: int = 0
    ) -> List[WebhookDelivery]:
        """Get deliveries for a webhook."""
        deliveries = [
            d for d in self.deliveries.values()
            if d.webhook_id == webhook_id
        ]
        deliveries.sort(key=lambda x: x.created_at, reverse=True)
        return deliveries[offset:offset + limit]
    
    async def get_delivery_attempts(
        self,
        delivery_id: str
    ) -> List[DeliveryAttempt]:
        """Get all attempts for a delivery."""
        return self.attempts.get(delivery_id, [])
    
    async def retry_delivery(self, delivery_id: str) -> bool:
        """Manually retry a failed delivery."""
        delivery = self.deliveries.get(delivery_id)
        if not delivery:
            return False
        
        if delivery.status != DeliveryStatus.FAILED:
            return False
        
        webhook = self.webhooks.get(delivery.webhook_id)
        if not webhook:
            return False
        
        # Reset for retry
        delivery.status = DeliveryStatus.PENDING
        delivery.attempt_count = 0
        delivery.next_retry_at = None
        
        await self.delivery_queue.put((delivery_id, webhook))
        return True
    
    # =========================================================================
    # WORKER
    # =========================================================================
    
    async def start_worker(self):
        """Start the delivery worker."""
        if self._running:
            return
        
        self._running = True
        self._worker_task = asyncio.create_task(self._worker_loop())
        logger.info("Webhook worker started")
    
    async def stop_worker(self):
        """Stop the delivery worker."""
        self._running = False
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass
        logger.info("Webhook worker stopped")
    
    async def _worker_loop(self):
        """Process deliveries from the queue."""
        while self._running:
            try:
                # Wait for delivery with timeout
                try:
                    delivery_id, webhook = await asyncio.wait_for(
                        self.delivery_queue.get(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    continue
                
                # Process delivery
                await self.deliver_webhook(delivery_id, webhook)
                
                self.delivery_queue.task_done()
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Worker error: {e}")
                await asyncio.sleep(1)
    
    # =========================================================================
    # TEST ENDPOINT
    # =========================================================================
    
    async def test_webhook(self, webhook_id: str) -> Dict[str, Any]:
        """Send a test event to a webhook."""
        webhook = self.webhooks.get(webhook_id)
        if not webhook:
            return {"success": False, "error": "Webhook not found"}
        
        # Create test payload
        payload = WebhookPayload(
            type="test",
            organization_id=webhook.organization_id,
            data={
                "message": "This is a test webhook delivery",
                "timestamp": datetime.utcnow().isoformat()
            },
            metadata={"test": True}
        )
        
        payload_str = json.dumps(payload.to_dict())
        signature = self.sign_payload(payload_str, webhook.secret)
        
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "SSI-Shadow-Webhook/1.0",
            "X-SSI-Signature": signature,
            "X-SSI-Event": "test",
            "X-SSI-Timestamp": datetime.utcnow().isoformat(),
            **webhook.headers
        }
        
        start_time = time.time()
        
        try:
            response = await self.http_client.post(
                webhook.url,
                content=payload_str,
                headers=headers,
                timeout=10.0
            )
            
            response_time_ms = (time.time() - start_time) * 1000
            
            return {
                "success": 200 <= response.status_code < 300,
                "status_code": response.status_code,
                "response_time_ms": round(response_time_ms, 2),
                "response_body": response.text[:500]
            }
            
        except httpx.TimeoutException:
            return {"success": False, "error": "Timeout"}
        except httpx.RequestError as e:
            return {"success": False, "error": str(e)}
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def close(self):
        """Close the service."""
        await self.stop_worker()
        await self.http_client.aclose()


# =============================================================================
# SINGLETON
# =============================================================================

_webhook_service: Optional[WebhookService] = None


def get_webhook_service() -> WebhookService:
    """Get or create the webhook service."""
    global _webhook_service
    if _webhook_service is None:
        _webhook_service = WebhookService()
    return _webhook_service


async def init_webhook_service(redis_url: str = None) -> WebhookService:
    """Initialize the webhook service."""
    global _webhook_service
    _webhook_service = WebhookService(redis_url=redis_url)
    await _webhook_service.start_worker()
    return _webhook_service
