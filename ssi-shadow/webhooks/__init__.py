"""
SSI Shadow - Webhooks & Notifications
=====================================
Webhook dispatch, notifications (Slack/Telegram/Email), alerts.
"""

from .models.entities import (
    WebhookConfig, WebhookCreate, WebhookUpdate, WebhookPayload,
    WebhookDelivery, DeliveryAttempt, WebhookEvent, DeliveryStatus,
    SlackConfig, TelegramConfig, EmailConfig, SMSConfig,
    NotificationChannel, NotificationConfig,
    AlertRule, AlertRuleCreate, Alert, AlertSeverity,
    ReportSchedule, ReportScheduleCreate
)
from .services.webhook_service import WebhookService, get_webhook_service, init_webhook_service
from .services.alert_service import AlertService, get_alert_service, init_alert_service
from .channels.notifications import (
    NotificationService, get_notification_service,
    SlackChannel, TelegramChannel, EmailChannel, SMSChannel
)
from .templates.renderer import TemplateRenderer, get_template_renderer
from .routes.api import webhook_router, alert_router, notification_router

__all__ = [
    # Models
    "WebhookConfig", "WebhookCreate", "WebhookUpdate", "WebhookPayload",
    "WebhookDelivery", "DeliveryAttempt", "WebhookEvent", "DeliveryStatus",
    "SlackConfig", "TelegramConfig", "EmailConfig", "SMSConfig",
    "NotificationChannel", "NotificationConfig",
    "AlertRule", "AlertRuleCreate", "Alert", "AlertSeverity",
    "ReportSchedule", "ReportScheduleCreate",
    # Services
    "WebhookService", "get_webhook_service", "init_webhook_service",
    "AlertService", "get_alert_service", "init_alert_service",
    # Channels
    "NotificationService", "get_notification_service",
    "SlackChannel", "TelegramChannel", "EmailChannel", "SMSChannel",
    # Templates
    "TemplateRenderer", "get_template_renderer",
    # Routes
    "webhook_router", "alert_router", "notification_router",
]

__version__ = "2.0.0"
