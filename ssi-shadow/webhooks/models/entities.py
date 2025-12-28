"""
S.S.I. SHADOW - Webhook Data Models
===================================
Models for webhooks, deliveries, and notifications.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, HttpUrl, validator
import uuid


# =============================================================================
# ENUMS
# =============================================================================

class WebhookEvent(str, Enum):
    """Events that can trigger webhooks."""
    # Event tracking
    EVENT_RECEIVED = "event.received"
    EVENT_PROCESSED = "event.processed"
    EVENT_BLOCKED = "event.blocked"
    
    # Purchases
    PURCHASE = "purchase"
    PURCHASE_HIGH_VALUE = "purchase.high_value"
    
    # ML predictions
    HIGH_LTV_DETECTED = "ml.high_ltv_detected"
    CHURN_RISK_HIGH = "ml.churn_risk_high"
    PROPENSITY_HIGH = "ml.propensity_high"
    
    # Trust score
    TRUST_SCORE_LOW = "trust.score_low"
    TRUST_ANOMALY = "trust.anomaly"
    BOT_DETECTED = "trust.bot_detected"
    
    # Platform
    PLATFORM_ERROR = "platform.error"
    PLATFORM_RATE_LIMITED = "platform.rate_limited"
    
    # System
    DAILY_SUMMARY = "report.daily_summary"
    WEEKLY_REPORT = "report.weekly"
    THRESHOLD_ALERT = "alert.threshold"


class DeliveryStatus(str, Enum):
    """Webhook delivery status."""
    PENDING = "pending"
    DELIVERING = "delivering"
    DELIVERED = "delivered"
    FAILED = "failed"
    RETRYING = "retrying"


class NotificationChannel(str, Enum):
    """Notification channels."""
    WEBHOOK = "webhook"
    SLACK = "slack"
    TELEGRAM = "telegram"
    EMAIL = "email"
    SMS = "sms"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


# =============================================================================
# WEBHOOK CONFIGURATION
# =============================================================================

class WebhookConfig(BaseModel):
    """Webhook endpoint configuration."""
    id: str = Field(default_factory=lambda: f"wh_{uuid.uuid4().hex[:16]}")
    organization_id: str
    
    # Endpoint
    name: str = Field(..., min_length=2, max_length=100)
    url: HttpUrl
    
    # Events to receive
    events: List[WebhookEvent] = Field(default_factory=list)
    
    # Authentication
    secret: str = Field(default_factory=lambda: f"whsec_{uuid.uuid4().hex}")
    
    # Headers to include
    headers: Dict[str, str] = Field(default_factory=dict)
    
    # Status
    is_active: bool = True
    
    # Rate limiting
    rate_limit: int = 100  # Max deliveries per minute
    
    # Retry configuration
    max_retries: int = 5
    retry_backoff: List[int] = Field(default_factory=lambda: [0, 300, 1800, 7200, 86400])  # seconds
    
    # SSL verification
    verify_ssl: bool = True
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    
    # Stats
    total_deliveries: int = 0
    successful_deliveries: int = 0
    failed_deliveries: int = 0
    last_delivery_at: Optional[datetime] = None
    last_status: Optional[str] = None
    
    class Config:
        use_enum_values = True


class WebhookCreate(BaseModel):
    """Schema for creating a webhook."""
    name: str = Field(..., min_length=2, max_length=100)
    url: HttpUrl
    events: List[WebhookEvent]
    headers: Dict[str, str] = Field(default_factory=dict)
    verify_ssl: bool = True


class WebhookUpdate(BaseModel):
    """Schema for updating a webhook."""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    url: Optional[HttpUrl] = None
    events: Optional[List[WebhookEvent]] = None
    headers: Optional[Dict[str, str]] = None
    is_active: Optional[bool] = None
    verify_ssl: Optional[bool] = None


# =============================================================================
# WEBHOOK PAYLOAD
# =============================================================================

class WebhookPayload(BaseModel):
    """Webhook delivery payload."""
    id: str = Field(default_factory=lambda: f"evt_{uuid.uuid4().hex[:16]}")
    type: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Organization context
    organization_id: str
    
    # Event data
    data: Dict[str, Any]
    
    # Metadata
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "id": self.id,
            "type": self.type,
            "timestamp": self.timestamp.isoformat(),
            "organization_id": self.organization_id,
            "data": self.data,
            "metadata": self.metadata
        }


# =============================================================================
# WEBHOOK DELIVERY
# =============================================================================

class WebhookDelivery(BaseModel):
    """Record of a webhook delivery attempt."""
    id: str = Field(default_factory=lambda: f"dlv_{uuid.uuid4().hex[:16]}")
    webhook_id: str
    organization_id: str
    
    # Payload
    payload_id: str
    event_type: str
    
    # Status
    status: DeliveryStatus = DeliveryStatus.PENDING
    
    # Attempts
    attempt_count: int = 0
    max_attempts: int = 5
    next_retry_at: Optional[datetime] = None
    
    # Request details
    request_url: str
    request_headers: Dict[str, str] = Field(default_factory=dict)
    request_body: str = ""
    
    # Response details
    response_status: Optional[int] = None
    response_headers: Dict[str, str] = Field(default_factory=dict)
    response_body: Optional[str] = None
    response_time_ms: Optional[float] = None
    
    # Error
    error_message: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    delivered_at: Optional[datetime] = None
    
    class Config:
        use_enum_values = True


class DeliveryAttempt(BaseModel):
    """Single delivery attempt."""
    id: str = Field(default_factory=lambda: f"att_{uuid.uuid4().hex[:12]}")
    delivery_id: str
    attempt_number: int
    
    # Request
    request_time: datetime = Field(default_factory=datetime.utcnow)
    
    # Response
    response_status: Optional[int] = None
    response_body: Optional[str] = None
    response_time_ms: Optional[float] = None
    
    # Result
    success: bool = False
    error: Optional[str] = None


# =============================================================================
# NOTIFICATION CONFIGURATION
# =============================================================================

class SlackConfig(BaseModel):
    """Slack notification configuration."""
    webhook_url: HttpUrl
    channel: Optional[str] = None
    username: str = "SSI Shadow"
    icon_emoji: str = ":chart_with_upwards_trend:"
    events: List[WebhookEvent] = Field(default_factory=list)
    is_active: bool = True


class TelegramConfig(BaseModel):
    """Telegram notification configuration."""
    bot_token: str
    chat_id: str
    events: List[WebhookEvent] = Field(default_factory=list)
    is_active: bool = True
    parse_mode: str = "HTML"


class EmailConfig(BaseModel):
    """Email notification configuration."""
    recipients: List[str]
    sender_email: str = "notifications@ssi-shadow.io"
    sender_name: str = "SSI Shadow"
    events: List[WebhookEvent] = Field(default_factory=list)
    is_active: bool = True
    
    # Email provider
    provider: str = "sendgrid"  # sendgrid, ses, smtp
    api_key: Optional[str] = None
    
    # SMTP settings (if provider is smtp)
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None


class SMSConfig(BaseModel):
    """SMS notification configuration (for critical alerts only)."""
    phone_numbers: List[str]
    provider: str = "twilio"
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    from_number: Optional[str] = None
    events: List[WebhookEvent] = Field(default_factory=list)
    is_active: bool = True


class NotificationConfig(BaseModel):
    """Complete notification configuration for an organization."""
    id: str = Field(default_factory=lambda: f"ntf_{uuid.uuid4().hex[:12]}")
    organization_id: str
    
    slack: Optional[SlackConfig] = None
    telegram: Optional[TelegramConfig] = None
    email: Optional[EmailConfig] = None
    sms: Optional[SMSConfig] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)


# =============================================================================
# ALERTS
# =============================================================================

class AlertRule(BaseModel):
    """Alert rule configuration."""
    id: str = Field(default_factory=lambda: f"rule_{uuid.uuid4().hex[:12]}")
    organization_id: str
    
    name: str
    description: Optional[str] = None
    
    # Condition
    metric: str  # e.g., "conversion_rate", "error_rate", "spend"
    operator: str  # gt, lt, eq, gte, lte
    threshold: float
    
    # Time window
    window_minutes: int = 15
    
    # Trigger
    trigger_event: WebhookEvent
    severity: AlertSeverity = AlertSeverity.WARNING
    
    # Channels
    channels: List[NotificationChannel] = Field(default_factory=lambda: [NotificationChannel.SLACK])
    
    # Cooldown (prevent spam)
    cooldown_minutes: int = 60
    last_triggered_at: Optional[datetime] = None
    
    # Status
    is_active: bool = True
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class AlertRuleCreate(BaseModel):
    """Schema for creating an alert rule."""
    name: str
    description: Optional[str] = None
    metric: str
    operator: str
    threshold: float
    window_minutes: int = 15
    severity: AlertSeverity = AlertSeverity.WARNING
    channels: List[NotificationChannel] = Field(default_factory=lambda: [NotificationChannel.SLACK])
    cooldown_minutes: int = 60


class Alert(BaseModel):
    """Triggered alert instance."""
    id: str = Field(default_factory=lambda: f"alert_{uuid.uuid4().hex[:16]}")
    organization_id: str
    
    rule_id: str
    rule_name: str
    
    # Alert details
    severity: AlertSeverity
    title: str
    message: str
    
    # Context
    metric: str
    current_value: float
    threshold: float
    
    # Delivery
    channels_sent: List[str] = Field(default_factory=list)
    
    # Status
    acknowledged: bool = False
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


# =============================================================================
# SCHEDULED REPORTS
# =============================================================================

class ReportSchedule(BaseModel):
    """Scheduled report configuration."""
    id: str = Field(default_factory=lambda: f"rpt_{uuid.uuid4().hex[:12]}")
    organization_id: str
    
    name: str
    report_type: str  # daily_summary, weekly_report, monthly_analysis
    
    # Schedule (cron-like)
    schedule: str  # "0 8 * * *" for daily at 8am
    timezone: str = "UTC"
    
    # Delivery
    channels: List[NotificationChannel]
    recipients: Dict[str, List[str]] = Field(default_factory=dict)  # channel -> list of targets
    
    # Content
    include_sections: List[str] = Field(default_factory=lambda: [
        "overview", "events", "platforms", "trust_score", "ml_predictions"
    ])
    
    # Status
    is_active: bool = True
    last_sent_at: Optional[datetime] = None
    next_send_at: Optional[datetime] = None
    
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class ReportScheduleCreate(BaseModel):
    """Schema for creating a report schedule."""
    name: str
    report_type: str
    schedule: str
    timezone: str = "UTC"
    channels: List[NotificationChannel]
    recipients: Dict[str, List[str]] = Field(default_factory=dict)
    include_sections: List[str] = Field(default_factory=list)
