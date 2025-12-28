"""
S.S.I. SHADOW - Alert Service
=============================
Service for managing alert rules and triggering alerts.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import asyncio

from webhooks.models.entities import (
    AlertRule,
    AlertRuleCreate,
    Alert,
    AlertSeverity,
    NotificationChannel,
    ReportSchedule,
    ReportScheduleCreate,
    WebhookEvent,
)
from webhooks.channels.notifications import get_notification_service

logger = logging.getLogger(__name__)


class AlertService:
    """
    Service for managing alert rules and triggering alerts.
    """
    
    def __init__(self):
        # In-memory stores (replace with database in production)
        self.rules: Dict[str, AlertRule] = {}
        self.alerts: Dict[str, Alert] = {}
        self.schedules: Dict[str, ReportSchedule] = {}
        
        # Metrics cache (for threshold checking)
        self.metrics_cache: Dict[str, Dict[str, float]] = {}
        
        # Background tasks
        self._checker_task: Optional[asyncio.Task] = None
        self._scheduler_task: Optional[asyncio.Task] = None
        self._running = False
    
    # =========================================================================
    # RULE CRUD
    # =========================================================================
    
    async def create_rule(
        self,
        org_id: str,
        data: AlertRuleCreate
    ) -> AlertRule:
        """Create an alert rule."""
        rule = AlertRule(
            organization_id=org_id,
            name=data.name,
            description=data.description,
            metric=data.metric,
            operator=data.operator,
            threshold=data.threshold,
            window_minutes=data.window_minutes,
            trigger_event=WebhookEvent.THRESHOLD_ALERT,
            severity=data.severity,
            channels=[NotificationChannel(c) for c in data.channels],
            cooldown_minutes=data.cooldown_minutes
        )
        
        self.rules[rule.id] = rule
        logger.info(f"Alert rule created: {rule.id} ({rule.name})")
        
        return rule
    
    async def get_rule(self, rule_id: str) -> Optional[AlertRule]:
        """Get an alert rule by ID."""
        return self.rules.get(rule_id)
    
    async def get_rules_by_organization(self, org_id: str) -> List[AlertRule]:
        """Get all alert rules for an organization."""
        return [
            rule for rule in self.rules.values()
            if rule.organization_id == org_id
        ]
    
    async def update_rule(
        self,
        rule_id: str,
        data: Dict[str, Any]
    ) -> Optional[AlertRule]:
        """Update an alert rule."""
        rule = self.rules.get(rule_id)
        if not rule:
            return None
        
        for key, value in data.items():
            if hasattr(rule, key) and value is not None:
                setattr(rule, key, value)
        
        rule.updated_at = datetime.utcnow()
        return rule
    
    async def delete_rule(self, rule_id: str) -> bool:
        """Delete an alert rule."""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False
    
    # =========================================================================
    # ALERT TRIGGERING
    # =========================================================================
    
    async def check_and_trigger(
        self,
        org_id: str,
        metric: str,
        value: float
    ) -> List[Alert]:
        """
        Check if value triggers any alerts for the given metric.
        
        Returns:
            List of triggered alerts
        """
        triggered = []
        
        # Get rules for this metric
        rules = [
            rule for rule in self.rules.values()
            if rule.organization_id == org_id
            and rule.metric == metric
            and rule.is_active
        ]
        
        for rule in rules:
            # Check cooldown
            if rule.last_triggered_at:
                cooldown_end = rule.last_triggered_at + timedelta(minutes=rule.cooldown_minutes)
                if datetime.utcnow() < cooldown_end:
                    continue
            
            # Check threshold
            if self._check_threshold(value, rule.operator, rule.threshold):
                alert = await self._trigger_alert(rule, value)
                triggered.append(alert)
        
        return triggered
    
    def _check_threshold(
        self,
        value: float,
        operator: str,
        threshold: float
    ) -> bool:
        """Check if value matches threshold condition."""
        if operator == "gt":
            return value > threshold
        elif operator == "gte":
            return value >= threshold
        elif operator == "lt":
            return value < threshold
        elif operator == "lte":
            return value <= threshold
        elif operator == "eq":
            return value == threshold
        elif operator == "ne":
            return value != threshold
        return False
    
    async def _trigger_alert(
        self,
        rule: AlertRule,
        value: float
    ) -> Alert:
        """Trigger an alert and send notifications."""
        # Create alert
        alert = Alert(
            organization_id=rule.organization_id,
            rule_id=rule.id,
            rule_name=rule.name,
            severity=rule.severity,
            title=f"Alert: {rule.name}",
            message=self._build_alert_message(rule, value),
            metric=rule.metric,
            current_value=value,
            threshold=rule.threshold
        )
        
        self.alerts[alert.id] = alert
        
        # Update rule last triggered
        rule.last_triggered_at = datetime.utcnow()
        
        # Send notifications
        notification_service = get_notification_service()
        
        channel_names = [c.value for c in rule.channels]
        results = await notification_service.send(
            channels=channel_names,
            title=alert.title,
            message=alert.message,
            data={
                "Metric": rule.metric,
                "Current Value": f"{value:.2f}",
                "Threshold": f"{rule.operator} {rule.threshold}",
                "Severity": rule.severity.value
            },
            severity=rule.severity
        )
        
        alert.channels_sent = [
            channel for channel, success in results.items()
            if success
        ]
        
        logger.info(f"Alert triggered: {alert.id} ({rule.name})")
        return alert
    
    def _build_alert_message(self, rule: AlertRule, value: float) -> str:
        """Build alert message."""
        operator_text = {
            "gt": "exceeded",
            "gte": "reached or exceeded",
            "lt": "dropped below",
            "lte": "dropped to or below",
            "eq": "equals",
            "ne": "changed from"
        }
        
        op_text = operator_text.get(rule.operator, "triggered")
        
        return (
            f"The metric '{rule.metric}' has {op_text} the threshold.\n\n"
            f"Current value: {value:.2f}\n"
            f"Threshold: {rule.threshold}\n\n"
            f"{rule.description or ''}"
        )
    
    # =========================================================================
    # ALERT MANAGEMENT
    # =========================================================================
    
    async def get_alert(self, alert_id: str) -> Optional[Alert]:
        """Get an alert by ID."""
        return self.alerts.get(alert_id)
    
    async def get_alerts_by_organization(
        self,
        org_id: str,
        limit: int = 100,
        acknowledged: Optional[bool] = None
    ) -> List[Alert]:
        """Get alerts for an organization."""
        alerts = [
            alert for alert in self.alerts.values()
            if alert.organization_id == org_id
            and (acknowledged is None or alert.acknowledged == acknowledged)
        ]
        alerts.sort(key=lambda x: x.created_at, reverse=True)
        return alerts[:limit]
    
    async def acknowledge_alert(
        self,
        alert_id: str,
        user_id: str
    ) -> Optional[Alert]:
        """Acknowledge an alert."""
        alert = self.alerts.get(alert_id)
        if not alert:
            return None
        
        alert.acknowledged = True
        alert.acknowledged_by = user_id
        alert.acknowledged_at = datetime.utcnow()
        
        return alert
    
    # =========================================================================
    # SCHEDULED REPORTS
    # =========================================================================
    
    async def create_schedule(
        self,
        org_id: str,
        data: ReportScheduleCreate
    ) -> ReportSchedule:
        """Create a scheduled report."""
        schedule = ReportSchedule(
            organization_id=org_id,
            name=data.name,
            report_type=data.report_type,
            schedule=data.schedule,
            timezone=data.timezone,
            channels=[NotificationChannel(c) for c in data.channels],
            recipients=data.recipients,
            include_sections=data.include_sections
        )
        
        self.schedules[schedule.id] = schedule
        logger.info(f"Report schedule created: {schedule.id}")
        
        return schedule
    
    async def get_schedules_by_organization(self, org_id: str) -> List[ReportSchedule]:
        """Get all report schedules for an organization."""
        return [
            sched for sched in self.schedules.values()
            if sched.organization_id == org_id
        ]
    
    async def delete_schedule(self, schedule_id: str) -> bool:
        """Delete a report schedule."""
        if schedule_id in self.schedules:
            del self.schedules[schedule_id]
            return True
        return False
    
    # =========================================================================
    # PREDEFINED ALERTS
    # =========================================================================
    
    async def trigger_purchase_alert(
        self,
        org_id: str,
        event_data: Dict[str, Any]
    ):
        """Trigger alert for high-value purchase."""
        value = event_data.get("value", 0)
        
        notification_service = get_notification_service()
        
        await notification_service.send(
            channels=["slack", "telegram"],
            title="🎉 New Purchase!",
            message=f"A new purchase of ${value:.2f} was just completed!",
            data={
                "Order ID": event_data.get("order_id", "N/A"),
                "Value": f"${value:.2f}",
                "Currency": event_data.get("currency", "USD"),
                "Items": str(event_data.get("num_items", 1))
            },
            severity=AlertSeverity.INFO
        )
    
    async def trigger_high_ltv_alert(
        self,
        org_id: str,
        user_data: Dict[str, Any]
    ):
        """Trigger alert for high LTV user detected."""
        notification_service = get_notification_service()
        
        await notification_service.send(
            channels=["slack"],
            title="⭐ High Value Customer Detected",
            message="A new high-value customer has been identified!",
            data={
                "LTV Tier": user_data.get("ltv_tier", "VIP"),
                "Predicted LTV": f"${user_data.get('ltv_90d', 0):.2f}",
                "User ID": user_data.get("user_id", "N/A")
            },
            severity=AlertSeverity.INFO
        )
    
    async def trigger_churn_risk_alert(
        self,
        org_id: str,
        user_data: Dict[str, Any]
    ):
        """Trigger alert for high churn risk."""
        notification_service = get_notification_service()
        
        await notification_service.send(
            channels=["slack", "email"],
            title="⚠️ High Churn Risk Detected",
            message="A customer has been flagged as high churn risk.",
            data={
                "User ID": user_data.get("user_id", "N/A"),
                "Churn Probability": f"{user_data.get('churn_probability', 0):.1%}",
                "Last Active": user_data.get("last_active", "N/A")
            },
            severity=AlertSeverity.WARNING
        )
    
    async def trigger_platform_error_alert(
        self,
        org_id: str,
        error_data: Dict[str, Any]
    ):
        """Trigger alert for platform API error."""
        notification_service = get_notification_service()
        
        await notification_service.send(
            channels=["slack", "telegram"],
            title="🚨 Platform API Error",
            message=f"An error occurred with the {error_data.get('platform', 'unknown')} API.",
            data={
                "Platform": error_data.get("platform", "Unknown"),
                "Error Code": error_data.get("error_code", "N/A"),
                "Error Message": error_data.get("error_message", "N/A"),
                "Events Affected": str(error_data.get("events_affected", 0))
            },
            severity=AlertSeverity.ERROR
        )
    
    # =========================================================================
    # BACKGROUND TASKS
    # =========================================================================
    
    async def start_background_tasks(self):
        """Start background tasks."""
        if self._running:
            return
        
        self._running = True
        self._checker_task = asyncio.create_task(self._metric_checker_loop())
        self._scheduler_task = asyncio.create_task(self._report_scheduler_loop())
        
        logger.info("Alert service background tasks started")
    
    async def stop_background_tasks(self):
        """Stop background tasks."""
        self._running = False
        
        if self._checker_task:
            self._checker_task.cancel()
        if self._scheduler_task:
            self._scheduler_task.cancel()
        
        logger.info("Alert service background tasks stopped")
    
    async def _metric_checker_loop(self):
        """Periodically check metrics against rules."""
        while self._running:
            try:
                # In production, fetch actual metrics from BigQuery
                # For now, this is a placeholder
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Metric checker error: {e}")
                await asyncio.sleep(60)
    
    async def _report_scheduler_loop(self):
        """Check and send scheduled reports."""
        while self._running:
            try:
                now = datetime.utcnow()
                
                for schedule in self.schedules.values():
                    if not schedule.is_active:
                        continue
                    
                    # Check if it's time to send
                    if schedule.next_send_at and now >= schedule.next_send_at:
                        await self._send_scheduled_report(schedule)
                
                await asyncio.sleep(60)  # Check every minute
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Report scheduler error: {e}")
                await asyncio.sleep(60)
    
    async def _send_scheduled_report(self, schedule: ReportSchedule):
        """Send a scheduled report."""
        logger.info(f"Sending scheduled report: {schedule.name}")
        
        # Build report content (placeholder)
        title = f"📊 {schedule.name}"
        message = f"Here's your {schedule.report_type} report."
        
        data = {
            "Report Type": schedule.report_type,
            "Generated At": datetime.utcnow().isoformat(),
            "Sections": ", ".join(schedule.include_sections)
        }
        
        # Send via configured channels
        notification_service = get_notification_service()
        channel_names = [c.value for c in schedule.channels]
        
        await notification_service.send(
            channels=channel_names,
            title=title,
            message=message,
            data=data,
            severity=AlertSeverity.INFO
        )
        
        # Update last sent
        schedule.last_sent_at = datetime.utcnow()
        
        # Calculate next send time (simplified - in production use croniter)
        schedule.next_send_at = datetime.utcnow() + timedelta(days=1)


# =============================================================================
# SINGLETON
# =============================================================================

_alert_service: Optional[AlertService] = None


def get_alert_service() -> AlertService:
    """Get or create the alert service."""
    global _alert_service
    if _alert_service is None:
        _alert_service = AlertService()
    return _alert_service


async def init_alert_service() -> AlertService:
    """Initialize the alert service."""
    global _alert_service
    _alert_service = AlertService()
    await _alert_service.start_background_tasks()
    return _alert_service
