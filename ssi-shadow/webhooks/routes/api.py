"""
S.S.I. SHADOW - Webhook Routes
==============================
API routes for webhook management.
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request

from webhooks.models.entities import (
    WebhookConfig,
    WebhookCreate,
    WebhookUpdate,
    WebhookDelivery,
    DeliveryAttempt,
    AlertRule,
    AlertRuleCreate,
    Alert,
    ReportSchedule,
    ReportScheduleCreate,
    NotificationChannel,
    SlackConfig,
    TelegramConfig,
    EmailConfig,
    WebhookEvent,
)
from webhooks.services.webhook_service import get_webhook_service
from webhooks.services.alert_service import get_alert_service
from webhooks.channels.notifications import get_notification_service

logger = logging.getLogger(__name__)


# Placeholder for auth dependency
class CurrentUser:
    def __init__(self):
        self.user_id = "usr_test"
        self.organization_id = "org_test"


async def get_current_user() -> CurrentUser:
    return CurrentUser()


# =============================================================================
# WEBHOOK ROUTES
# =============================================================================

webhook_router = APIRouter(prefix="/api/webhooks", tags=["Webhooks"])


@webhook_router.get(
    "",
    summary="List webhooks",
    description="List all webhooks for the organization."
)
async def list_webhooks(
    user: CurrentUser = Depends(get_current_user)
):
    """List all webhooks."""
    service = get_webhook_service()
    webhooks = await service.get_webhooks_by_organization(user.organization_id)
    
    return [
        {
            "id": wh.id,
            "name": wh.name,
            "url": wh.url,
            "events": wh.events,
            "is_active": wh.is_active,
            "total_deliveries": wh.total_deliveries,
            "successful_deliveries": wh.successful_deliveries,
            "failed_deliveries": wh.failed_deliveries,
            "last_delivery_at": wh.last_delivery_at.isoformat() if wh.last_delivery_at else None,
            "last_status": wh.last_status,
            "created_at": wh.created_at.isoformat()
        }
        for wh in webhooks
    ]


@webhook_router.post(
    "",
    summary="Create webhook",
    description="Create a new webhook endpoint."
)
async def create_webhook(
    data: WebhookCreate,
    user: CurrentUser = Depends(get_current_user)
):
    """Create a new webhook."""
    service = get_webhook_service()
    
    webhook = await service.create_webhook(
        user.organization_id,
        data,
        user.user_id
    )
    
    return {
        "id": webhook.id,
        "name": webhook.name,
        "url": webhook.url,
        "events": webhook.events,
        "secret": webhook.secret,  # Only shown on creation
        "is_active": webhook.is_active,
        "created_at": webhook.created_at.isoformat()
    }


@webhook_router.get(
    "/{webhook_id}",
    summary="Get webhook",
    description="Get webhook details."
)
async def get_webhook(
    webhook_id: str = Path(...),
    user: CurrentUser = Depends(get_current_user)
):
    """Get webhook details."""
    service = get_webhook_service()
    webhook = await service.get_webhook(webhook_id)
    
    if not webhook or webhook.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    return {
        "id": webhook.id,
        "name": webhook.name,
        "url": webhook.url,
        "events": webhook.events,
        "headers": webhook.headers,
        "is_active": webhook.is_active,
        "verify_ssl": webhook.verify_ssl,
        "max_retries": webhook.max_retries,
        "total_deliveries": webhook.total_deliveries,
        "successful_deliveries": webhook.successful_deliveries,
        "failed_deliveries": webhook.failed_deliveries,
        "last_delivery_at": webhook.last_delivery_at.isoformat() if webhook.last_delivery_at else None,
        "last_status": webhook.last_status,
        "created_at": webhook.created_at.isoformat(),
        "updated_at": webhook.updated_at.isoformat()
    }


@webhook_router.put(
    "/{webhook_id}",
    summary="Update webhook",
    description="Update webhook configuration."
)
async def update_webhook(
    data: WebhookUpdate,
    webhook_id: str = Path(...),
    user: CurrentUser = Depends(get_current_user)
):
    """Update a webhook."""
    service = get_webhook_service()
    
    webhook = await service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    updated = await service.update_webhook(webhook_id, data)
    
    return {
        "id": updated.id,
        "name": updated.name,
        "url": updated.url,
        "events": updated.events,
        "is_active": updated.is_active,
        "updated_at": updated.updated_at.isoformat()
    }


@webhook_router.delete(
    "/{webhook_id}",
    status_code=204,
    summary="Delete webhook",
    description="Delete a webhook."
)
async def delete_webhook(
    webhook_id: str = Path(...),
    user: CurrentUser = Depends(get_current_user)
):
    """Delete a webhook."""
    service = get_webhook_service()
    
    webhook = await service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    await service.delete_webhook(webhook_id)


@webhook_router.post(
    "/{webhook_id}/rotate-secret",
    summary="Rotate secret",
    description="Rotate the webhook signing secret."
)
async def rotate_webhook_secret(
    webhook_id: str = Path(...),
    user: CurrentUser = Depends(get_current_user)
):
    """Rotate webhook secret."""
    service = get_webhook_service()
    
    webhook = await service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    new_secret = await service.rotate_secret(webhook_id)
    
    return {"secret": new_secret}


@webhook_router.post(
    "/{webhook_id}/test",
    summary="Test webhook",
    description="Send a test event to the webhook."
)
async def test_webhook(
    webhook_id: str = Path(...),
    user: CurrentUser = Depends(get_current_user)
):
    """Send a test event to a webhook."""
    service = get_webhook_service()
    
    webhook = await service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    result = await service.test_webhook(webhook_id)
    
    return result


# =============================================================================
# DELIVERY LOG ROUTES
# =============================================================================

@webhook_router.get(
    "/{webhook_id}/deliveries",
    summary="List deliveries",
    description="List delivery logs for a webhook."
)
async def list_deliveries(
    webhook_id: str = Path(...),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    user: CurrentUser = Depends(get_current_user)
):
    """List deliveries for a webhook."""
    service = get_webhook_service()
    
    webhook = await service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    deliveries = await service.get_deliveries_for_webhook(webhook_id, limit, offset)
    
    return [
        {
            "id": d.id,
            "payload_id": d.payload_id,
            "event_type": d.event_type,
            "status": d.status,
            "attempt_count": d.attempt_count,
            "response_status": d.response_status,
            "response_time_ms": d.response_time_ms,
            "error_message": d.error_message,
            "created_at": d.created_at.isoformat(),
            "delivered_at": d.delivered_at.isoformat() if d.delivered_at else None
        }
        for d in deliveries
    ]


@webhook_router.get(
    "/{webhook_id}/deliveries/{delivery_id}",
    summary="Get delivery details",
    description="Get detailed delivery information."
)
async def get_delivery(
    webhook_id: str = Path(...),
    delivery_id: str = Path(...),
    user: CurrentUser = Depends(get_current_user)
):
    """Get delivery details."""
    service = get_webhook_service()
    
    webhook = await service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    delivery = await service.get_delivery(delivery_id)
    if not delivery or delivery.webhook_id != webhook_id:
        raise HTTPException(status_code=404, detail="Delivery not found")
    
    attempts = await service.get_delivery_attempts(delivery_id)
    
    return {
        "id": delivery.id,
        "payload_id": delivery.payload_id,
        "event_type": delivery.event_type,
        "status": delivery.status,
        "attempt_count": delivery.attempt_count,
        "max_attempts": delivery.max_attempts,
        "request_url": delivery.request_url,
        "request_headers": delivery.request_headers,
        "request_body": delivery.request_body[:1000],  # Truncate
        "response_status": delivery.response_status,
        "response_headers": delivery.response_headers,
        "response_body": delivery.response_body,
        "response_time_ms": delivery.response_time_ms,
        "error_message": delivery.error_message,
        "created_at": delivery.created_at.isoformat(),
        "delivered_at": delivery.delivered_at.isoformat() if delivery.delivered_at else None,
        "next_retry_at": delivery.next_retry_at.isoformat() if delivery.next_retry_at else None,
        "attempts": [
            {
                "attempt_number": a.attempt_number,
                "request_time": a.request_time.isoformat(),
                "response_status": a.response_status,
                "response_time_ms": a.response_time_ms,
                "success": a.success,
                "error": a.error
            }
            for a in attempts
        ]
    }


@webhook_router.post(
    "/{webhook_id}/deliveries/{delivery_id}/retry",
    summary="Retry delivery",
    description="Retry a failed delivery."
)
async def retry_delivery(
    webhook_id: str = Path(...),
    delivery_id: str = Path(...),
    user: CurrentUser = Depends(get_current_user)
):
    """Retry a failed delivery."""
    service = get_webhook_service()
    
    webhook = await service.get_webhook(webhook_id)
    if not webhook or webhook.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Webhook not found")
    
    success = await service.retry_delivery(delivery_id)
    
    if not success:
        raise HTTPException(status_code=400, detail="Cannot retry this delivery")
    
    return {"status": "retry_queued"}


# =============================================================================
# ALERT ROUTES
# =============================================================================

alert_router = APIRouter(prefix="/api/alerts", tags=["Alerts"])


@alert_router.get(
    "/rules",
    summary="List alert rules",
    description="List all alert rules."
)
async def list_alert_rules(
    user: CurrentUser = Depends(get_current_user)
):
    """List alert rules."""
    service = get_alert_service()
    rules = await service.get_rules_by_organization(user.organization_id)
    
    return [
        {
            "id": r.id,
            "name": r.name,
            "description": r.description,
            "metric": r.metric,
            "operator": r.operator,
            "threshold": r.threshold,
            "severity": r.severity,
            "channels": [c.value for c in r.channels],
            "is_active": r.is_active,
            "last_triggered_at": r.last_triggered_at.isoformat() if r.last_triggered_at else None,
            "created_at": r.created_at.isoformat()
        }
        for r in rules
    ]


@alert_router.post(
    "/rules",
    summary="Create alert rule",
    description="Create a new alert rule."
)
async def create_alert_rule(
    data: AlertRuleCreate,
    user: CurrentUser = Depends(get_current_user)
):
    """Create an alert rule."""
    service = get_alert_service()
    
    rule = await service.create_rule(user.organization_id, data)
    
    return {
        "id": rule.id,
        "name": rule.name,
        "metric": rule.metric,
        "operator": rule.operator,
        "threshold": rule.threshold,
        "severity": rule.severity,
        "channels": [c.value for c in rule.channels],
        "created_at": rule.created_at.isoformat()
    }


@alert_router.delete(
    "/rules/{rule_id}",
    status_code=204,
    summary="Delete alert rule",
    description="Delete an alert rule."
)
async def delete_alert_rule(
    rule_id: str = Path(...),
    user: CurrentUser = Depends(get_current_user)
):
    """Delete an alert rule."""
    service = get_alert_service()
    
    rule = await service.get_rule(rule_id)
    if not rule or rule.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Rule not found")
    
    await service.delete_rule(rule_id)


@alert_router.get(
    "",
    summary="List alerts",
    description="List triggered alerts."
)
async def list_alerts(
    limit: int = Query(100, ge=1, le=1000),
    acknowledged: Optional[bool] = Query(None),
    user: CurrentUser = Depends(get_current_user)
):
    """List alerts."""
    service = get_alert_service()
    alerts = await service.get_alerts_by_organization(
        user.organization_id,
        limit=limit,
        acknowledged=acknowledged
    )
    
    return [
        {
            "id": a.id,
            "rule_name": a.rule_name,
            "severity": a.severity,
            "title": a.title,
            "message": a.message,
            "metric": a.metric,
            "current_value": a.current_value,
            "threshold": a.threshold,
            "acknowledged": a.acknowledged,
            "acknowledged_by": a.acknowledged_by,
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
            "created_at": a.created_at.isoformat()
        }
        for a in alerts
    ]


@alert_router.post(
    "/{alert_id}/acknowledge",
    summary="Acknowledge alert",
    description="Acknowledge an alert."
)
async def acknowledge_alert(
    alert_id: str = Path(...),
    user: CurrentUser = Depends(get_current_user)
):
    """Acknowledge an alert."""
    service = get_alert_service()
    
    alert = await service.get_alert(alert_id)
    if not alert or alert.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Alert not found")
    
    updated = await service.acknowledge_alert(alert_id, user.user_id)
    
    return {
        "id": updated.id,
        "acknowledged": updated.acknowledged,
        "acknowledged_at": updated.acknowledged_at.isoformat()
    }


# =============================================================================
# NOTIFICATION ROUTES
# =============================================================================

notification_router = APIRouter(prefix="/api/notifications", tags=["Notifications"])


@notification_router.post(
    "/slack/configure",
    summary="Configure Slack",
    description="Configure Slack notifications."
)
async def configure_slack(
    webhook_url: str,
    channel: Optional[str] = None,
    events: List[WebhookEvent] = None,
    user: CurrentUser = Depends(get_current_user)
):
    """Configure Slack notifications."""
    service = get_notification_service()
    
    config = SlackConfig(
        webhook_url=webhook_url,
        channel=channel,
        events=events or [],
        is_active=True
    )
    
    service.configure_slack(config)
    
    return {"status": "configured", "channel": "slack"}


@notification_router.post(
    "/telegram/configure",
    summary="Configure Telegram",
    description="Configure Telegram notifications."
)
async def configure_telegram(
    bot_token: str,
    chat_id: str,
    events: List[WebhookEvent] = None,
    user: CurrentUser = Depends(get_current_user)
):
    """Configure Telegram notifications."""
    service = get_notification_service()
    
    config = TelegramConfig(
        bot_token=bot_token,
        chat_id=chat_id,
        events=events or [],
        is_active=True
    )
    
    service.configure_telegram(config)
    
    return {"status": "configured", "channel": "telegram"}


@notification_router.post(
    "/email/configure",
    summary="Configure Email",
    description="Configure email notifications."
)
async def configure_email(
    recipients: List[str],
    provider: str = "sendgrid",
    api_key: Optional[str] = None,
    events: List[WebhookEvent] = None,
    user: CurrentUser = Depends(get_current_user)
):
    """Configure email notifications."""
    service = get_notification_service()
    
    config = EmailConfig(
        recipients=recipients,
        provider=provider,
        api_key=api_key,
        events=events or [],
        is_active=True
    )
    
    service.configure_email(config)
    
    return {"status": "configured", "channel": "email"}


@notification_router.post(
    "/test",
    summary="Test notifications",
    description="Test all configured notification channels."
)
async def test_notifications(
    user: CurrentUser = Depends(get_current_user)
):
    """Test all notification channels."""
    service = get_notification_service()
    results = await service.test_all()
    
    return results


# =============================================================================
# REPORT SCHEDULE ROUTES
# =============================================================================

@notification_router.get(
    "/schedules",
    summary="List schedules",
    description="List scheduled reports."
)
async def list_schedules(
    user: CurrentUser = Depends(get_current_user)
):
    """List report schedules."""
    service = get_alert_service()
    schedules = await service.get_schedules_by_organization(user.organization_id)
    
    return [
        {
            "id": s.id,
            "name": s.name,
            "report_type": s.report_type,
            "schedule": s.schedule,
            "timezone": s.timezone,
            "channels": [c.value for c in s.channels],
            "is_active": s.is_active,
            "last_sent_at": s.last_sent_at.isoformat() if s.last_sent_at else None,
            "next_send_at": s.next_send_at.isoformat() if s.next_send_at else None,
            "created_at": s.created_at.isoformat()
        }
        for s in schedules
    ]


@notification_router.post(
    "/schedules",
    summary="Create schedule",
    description="Create a scheduled report."
)
async def create_schedule(
    data: ReportScheduleCreate,
    user: CurrentUser = Depends(get_current_user)
):
    """Create a report schedule."""
    service = get_alert_service()
    
    schedule = await service.create_schedule(user.organization_id, data)
    
    return {
        "id": schedule.id,
        "name": schedule.name,
        "report_type": schedule.report_type,
        "schedule": schedule.schedule,
        "created_at": schedule.created_at.isoformat()
    }


@notification_router.delete(
    "/schedules/{schedule_id}",
    status_code=204,
    summary="Delete schedule",
    description="Delete a scheduled report."
)
async def delete_schedule(
    schedule_id: str = Path(...),
    user: CurrentUser = Depends(get_current_user)
):
    """Delete a report schedule."""
    service = get_alert_service()
    
    schedules = await service.get_schedules_by_organization(user.organization_id)
    schedule_ids = [s.id for s in schedules]
    
    if schedule_id not in schedule_ids:
        raise HTTPException(status_code=404, detail="Schedule not found")
    
    await service.delete_schedule(schedule_id)


# =============================================================================
# WEBHOOK EVENT TYPES
# =============================================================================

@webhook_router.get(
    "/events",
    summary="List event types",
    description="List available webhook event types."
)
async def list_event_types():
    """List available webhook event types."""
    return [
        {
            "event": e.value,
            "description": _get_event_description(e)
        }
        for e in WebhookEvent
    ]


def _get_event_description(event: WebhookEvent) -> str:
    """Get description for an event type."""
    descriptions = {
        WebhookEvent.EVENT_RECEIVED: "Fired when an event is received",
        WebhookEvent.EVENT_PROCESSED: "Fired when an event is processed",
        WebhookEvent.EVENT_BLOCKED: "Fired when an event is blocked by trust score",
        WebhookEvent.PURCHASE: "Fired on every purchase event",
        WebhookEvent.PURCHASE_HIGH_VALUE: "Fired on high-value purchases",
        WebhookEvent.HIGH_LTV_DETECTED: "Fired when a high LTV customer is detected",
        WebhookEvent.CHURN_RISK_HIGH: "Fired when high churn risk is detected",
        WebhookEvent.PROPENSITY_HIGH: "Fired when high purchase propensity is detected",
        WebhookEvent.TRUST_SCORE_LOW: "Fired when trust score drops below threshold",
        WebhookEvent.TRUST_ANOMALY: "Fired when trust score anomaly is detected",
        WebhookEvent.BOT_DETECTED: "Fired when bot traffic is detected",
        WebhookEvent.PLATFORM_ERROR: "Fired on platform API errors",
        WebhookEvent.PLATFORM_RATE_LIMITED: "Fired when platform rate limit is hit",
        WebhookEvent.DAILY_SUMMARY: "Daily summary report",
        WebhookEvent.WEEKLY_REPORT: "Weekly report",
        WebhookEvent.THRESHOLD_ALERT: "Custom threshold alert triggered",
    }
    return descriptions.get(event, "")
