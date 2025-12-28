"""
S.S.I. SHADOW - WebSocket Real-time Updates
===========================================
WebSocket endpoint for pushing real-time events and metrics to the dashboard.
"""

import asyncio
import logging
import json
from datetime import datetime
from typing import Dict, Set, Optional
from dataclasses import dataclass, field

from fastapi import WebSocket, WebSocketDisconnect, Depends, Query
from starlette.websockets import WebSocketState

from api.services.auth_service import get_auth_service

logger = logging.getLogger(__name__)


@dataclass
class WebSocketClient:
    """Represents a connected WebSocket client."""
    websocket: WebSocket
    organization_id: str
    user_id: str
    subscriptions: Set[str] = field(default_factory=set)
    connected_at: datetime = field(default_factory=datetime.utcnow)
    last_ping: datetime = field(default_factory=datetime.utcnow)


class ConnectionManager:
    """
    Manages WebSocket connections for real-time updates.
    
    Supports:
    - Organization-scoped connections
    - Topic-based subscriptions
    - Broadcast to all clients in an organization
    - Individual client messaging
    """
    
    def __init__(self):
        # Map of connection_id -> WebSocketClient
        self.active_connections: Dict[str, WebSocketClient] = {}
        
        # Map of organization_id -> set of connection_ids
        self.org_connections: Dict[str, Set[str]] = {}
        
        # Map of topic -> set of connection_ids
        self.topic_subscriptions: Dict[str, Set[str]] = {}
        
        # Background tasks
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._metrics_task: Optional[asyncio.Task] = None
    
    def _get_connection_id(self, websocket: WebSocket) -> str:
        """Generate a unique connection ID."""
        return f"{id(websocket)}_{datetime.utcnow().timestamp()}"
    
    async def connect(
        self,
        websocket: WebSocket,
        organization_id: str,
        user_id: str
    ) -> str:
        """
        Accept a WebSocket connection.
        
        Returns:
            Connection ID
        """
        await websocket.accept()
        
        connection_id = self._get_connection_id(websocket)
        
        client = WebSocketClient(
            websocket=websocket,
            organization_id=organization_id,
            user_id=user_id
        )
        
        self.active_connections[connection_id] = client
        
        # Add to organization map
        if organization_id not in self.org_connections:
            self.org_connections[organization_id] = set()
        self.org_connections[organization_id].add(connection_id)
        
        # Default subscriptions
        await self.subscribe(connection_id, "events")
        await self.subscribe(connection_id, "metrics")
        
        logger.info(f"WebSocket connected: {connection_id} (org: {organization_id})")
        
        # Send welcome message
        await self.send_to_client(connection_id, {
            "type": "connected",
            "connection_id": connection_id,
            "subscriptions": list(client.subscriptions),
            "timestamp": datetime.utcnow().isoformat()
        })
        
        return connection_id
    
    async def disconnect(self, connection_id: str):
        """Disconnect a WebSocket client."""
        client = self.active_connections.get(connection_id)
        
        if not client:
            return
        
        # Remove from organization map
        org_id = client.organization_id
        if org_id in self.org_connections:
            self.org_connections[org_id].discard(connection_id)
            if not self.org_connections[org_id]:
                del self.org_connections[org_id]
        
        # Remove from topic subscriptions
        for topic in client.subscriptions:
            if topic in self.topic_subscriptions:
                self.topic_subscriptions[topic].discard(connection_id)
        
        # Close websocket if still open
        if client.websocket.client_state == WebSocketState.CONNECTED:
            await client.websocket.close()
        
        # Remove from active connections
        del self.active_connections[connection_id]
        
        logger.info(f"WebSocket disconnected: {connection_id}")
    
    async def subscribe(self, connection_id: str, topic: str):
        """Subscribe a client to a topic."""
        client = self.active_connections.get(connection_id)
        
        if not client:
            return
        
        client.subscriptions.add(topic)
        
        if topic not in self.topic_subscriptions:
            self.topic_subscriptions[topic] = set()
        self.topic_subscriptions[topic].add(connection_id)
        
        logger.debug(f"Client {connection_id} subscribed to {topic}")
    
    async def unsubscribe(self, connection_id: str, topic: str):
        """Unsubscribe a client from a topic."""
        client = self.active_connections.get(connection_id)
        
        if not client:
            return
        
        client.subscriptions.discard(topic)
        
        if topic in self.topic_subscriptions:
            self.topic_subscriptions[topic].discard(connection_id)
    
    async def send_to_client(self, connection_id: str, message: dict):
        """Send a message to a specific client."""
        client = self.active_connections.get(connection_id)
        
        if not client:
            return
        
        try:
            if client.websocket.client_state == WebSocketState.CONNECTED:
                await client.websocket.send_json(message)
        except Exception as e:
            logger.warning(f"Failed to send to {connection_id}: {e}")
            await self.disconnect(connection_id)
    
    async def broadcast_to_organization(
        self,
        organization_id: str,
        message: dict,
        topic: str = None
    ):
        """
        Broadcast a message to all clients in an organization.
        
        Args:
            organization_id: Target organization
            message: Message to send
            topic: Optional topic filter (only send to subscribed clients)
        """
        connection_ids = self.org_connections.get(organization_id, set())
        
        for connection_id in list(connection_ids):
            client = self.active_connections.get(connection_id)
            
            if not client:
                continue
            
            # Check topic subscription if specified
            if topic and topic not in client.subscriptions:
                continue
            
            await self.send_to_client(connection_id, message)
    
    async def broadcast_to_topic(self, topic: str, message: dict):
        """Broadcast a message to all clients subscribed to a topic."""
        connection_ids = self.topic_subscriptions.get(topic, set())
        
        for connection_id in list(connection_ids):
            await self.send_to_client(connection_id, message)
    
    async def handle_client_message(self, connection_id: str, data: dict):
        """
        Handle a message from a client.
        
        Supported message types:
        - subscribe: Subscribe to a topic
        - unsubscribe: Unsubscribe from a topic
        - ping: Heartbeat
        """
        message_type = data.get("type")
        
        if message_type == "subscribe":
            topic = data.get("topic")
            if topic:
                await self.subscribe(connection_id, topic)
                await self.send_to_client(connection_id, {
                    "type": "subscribed",
                    "topic": topic,
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        elif message_type == "unsubscribe":
            topic = data.get("topic")
            if topic:
                await self.unsubscribe(connection_id, topic)
                await self.send_to_client(connection_id, {
                    "type": "unsubscribed",
                    "topic": topic,
                    "timestamp": datetime.utcnow().isoformat()
                })
        
        elif message_type == "ping":
            client = self.active_connections.get(connection_id)
            if client:
                client.last_ping = datetime.utcnow()
            await self.send_to_client(connection_id, {
                "type": "pong",
                "timestamp": datetime.utcnow().isoformat()
            })
    
    def get_stats(self) -> dict:
        """Get connection statistics."""
        return {
            "total_connections": len(self.active_connections),
            "organizations": len(self.org_connections),
            "topics": {
                topic: len(connections)
                for topic, connections in self.topic_subscriptions.items()
            }
        }
    
    # =========================================================================
    # BACKGROUND TASKS
    # =========================================================================
    
    async def start_background_tasks(self):
        """Start background tasks for heartbeat and metrics."""
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        self._metrics_task = asyncio.create_task(self._metrics_loop())
    
    async def stop_background_tasks(self):
        """Stop background tasks."""
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
        if self._metrics_task:
            self._metrics_task.cancel()
    
    async def _heartbeat_loop(self):
        """Send periodic heartbeats and clean up stale connections."""
        while True:
            try:
                await asyncio.sleep(30)  # Every 30 seconds
                
                now = datetime.utcnow()
                stale_connections = []
                
                for connection_id, client in self.active_connections.items():
                    # Check if connection is stale (no ping for 2 minutes)
                    if (now - client.last_ping).total_seconds() > 120:
                        stale_connections.append(connection_id)
                    else:
                        # Send heartbeat
                        await self.send_to_client(connection_id, {
                            "type": "heartbeat",
                            "timestamp": now.isoformat()
                        })
                
                # Clean up stale connections
                for connection_id in stale_connections:
                    logger.info(f"Cleaning up stale connection: {connection_id}")
                    await self.disconnect(connection_id)
                    
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat loop error: {e}")
    
    async def _metrics_loop(self):
        """Send periodic metrics updates to subscribed clients."""
        while True:
            try:
                await asyncio.sleep(5)  # Every 5 seconds
                
                # Generate mock real-time metrics
                metrics = {
                    "type": "metrics",
                    "data": {
                        "events_per_second": 45.2,
                        "active_users": 1523,
                        "revenue_last_minute": 234.50,
                        "error_rate": 0.001,
                        "avg_latency_ms": 45.3
                    },
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Broadcast to all metrics subscribers
                await self.broadcast_to_topic("metrics", metrics)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metrics loop error: {e}")


# Global connection manager
manager = ConnectionManager()


# =============================================================================
# WEBSOCKET ENDPOINT
# =============================================================================

async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    """
    WebSocket endpoint for real-time dashboard updates.
    
    Query Parameters:
    - token: JWT access token for authentication
    
    Message Types (client -> server):
    - subscribe: {"type": "subscribe", "topic": "events"}
    - unsubscribe: {"type": "unsubscribe", "topic": "events"}
    - ping: {"type": "ping"}
    
    Message Types (server -> client):
    - connected: Connection established
    - subscribed: Subscription confirmed
    - unsubscribed: Unsubscription confirmed
    - event: New event received
    - metrics: Real-time metrics update
    - alert: System alert
    - heartbeat: Keep-alive
    - pong: Ping response
    """
    # Authenticate
    auth_service = get_auth_service()
    payload = await auth_service.verify_token(token)
    
    if not payload:
        await websocket.close(code=4001, reason="Invalid token")
        return
    
    # Connect
    connection_id = await manager.connect(
        websocket,
        organization_id=payload.org,
        user_id=payload.sub
    )
    
    try:
        while True:
            # Receive message
            data = await websocket.receive_json()
            
            # Handle message
            await manager.handle_client_message(connection_id, data)
            
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        await manager.disconnect(connection_id)


# =============================================================================
# EVENT PUBLISHING
# =============================================================================

async def publish_event(organization_id: str, event: dict):
    """
    Publish a new event to connected WebSocket clients.
    
    Called by the event processing pipeline when a new event is received.
    """
    message = {
        "type": "event",
        "data": event,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await manager.broadcast_to_organization(organization_id, message, topic="events")


async def publish_alert(organization_id: str, alert: dict):
    """
    Publish an alert to connected WebSocket clients.
    """
    message = {
        "type": "alert",
        "data": alert,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await manager.broadcast_to_organization(organization_id, message, topic="alerts")


async def publish_platform_status(organization_id: str, status: dict):
    """
    Publish platform status update to connected WebSocket clients.
    """
    message = {
        "type": "platform_status",
        "data": status,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    await manager.broadcast_to_organization(organization_id, message, topic="platforms")
