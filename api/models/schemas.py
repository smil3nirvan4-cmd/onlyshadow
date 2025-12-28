"""
S.S.I. SHADOW - API Models
==========================
Pydantic models for API requests and responses.
"""

from pydantic import BaseModel, Field, EmailStr, validator
from typing import Optional, List, Dict, Any, Literal
from datetime import datetime
from enum import Enum


# =============================================================================
# ENUMS
# =============================================================================

class PlatformStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    DOWN = "down"


class EventType(str, Enum):
    PAGE_VIEW = "PageView"
    VIEW_CONTENT = "ViewContent"
    ADD_TO_CART = "AddToCart"
    INITIATE_CHECKOUT = "InitiateCheckout"
    PURCHASE = "Purchase"
    LEAD = "Lead"
    COMPLETE_REGISTRATION = "CompleteRegistration"
    SEARCH = "Search"


class TrustAction(str, Enum):
    ALLOW = "allow"
    CHALLENGE = "challenge"
    BLOCK = "block"


class LTVTier(str, Enum):
    VIP = "VIP"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class ChurnRisk(str, Enum):
    CRITICAL = "Critical"
    HIGH = "High"
    MEDIUM = "Medium"
    LOW = "Low"


class BidStrategy(str, Enum):
    AGGRESSIVE = "aggressive"
    RETENTION = "retention"
    STANDARD = "standard"
    CONSERVATIVE = "conservative"
    EXCLUDE = "exclude"


# =============================================================================
# AUTH MODELS
# =============================================================================

class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    user: "UserResponse"


class RefreshTokenRequest(BaseModel):
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: EmailStr
    name: str
    role: str
    organization_id: str
    organization_name: str
    created_at: datetime
    last_login: Optional[datetime] = None


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8)


# =============================================================================
# DASHBOARD OVERVIEW
# =============================================================================

class MetricComparison(BaseModel):
    """Metric with comparison to previous period."""
    current: float
    previous: float
    change_percent: float
    trend: Literal["up", "down", "stable"]


class OverviewResponse(BaseModel):
    """Dashboard overview metrics."""
    events_today: MetricComparison
    unique_users: MetricComparison
    revenue: MetricComparison
    conversion_rate: MetricComparison
    avg_order_value: MetricComparison
    blocked_rate: MetricComparison
    
    last_updated: datetime
    period: str = "today"


# =============================================================================
# PLATFORM STATUS
# =============================================================================

class PlatformMetrics(BaseModel):
    """Metrics for a single platform."""
    platform: str
    status: PlatformStatus
    events_sent: int
    events_failed: int
    success_rate: float
    avg_latency_ms: float
    p99_latency_ms: float
    errors_last_hour: int
    last_error: Optional[str] = None
    last_success: Optional[datetime] = None


class PlatformsResponse(BaseModel):
    """Status of all platforms."""
    platforms: List[PlatformMetrics]
    overall_status: PlatformStatus
    total_events_sent: int
    overall_success_rate: float
    last_updated: datetime


# =============================================================================
# TRUST SCORE
# =============================================================================

class TrustScoreBucket(BaseModel):
    """Trust score distribution bucket."""
    range_min: float
    range_max: float
    count: int
    percentage: float


class BlockReason(BaseModel):
    """Reason for blocking events."""
    reason: str
    count: int
    percentage: float


class TrustScoreResponse(BaseModel):
    """Trust score analytics."""
    distribution: List[TrustScoreBucket]
    
    total_events: int
    allowed_events: int
    challenged_events: int
    blocked_events: int
    
    allow_rate: float
    challenge_rate: float
    block_rate: float
    
    avg_trust_score: float
    median_trust_score: float
    
    top_block_reasons: List[BlockReason]
    
    bot_detections: int
    datacenter_blocks: int
    behavioral_blocks: int
    
    last_updated: datetime


# =============================================================================
# ML PREDICTIONS
# =============================================================================

class LTVSegment(BaseModel):
    """LTV segment distribution."""
    tier: LTVTier
    count: int
    percentage: float
    avg_ltv: float
    total_ltv: float


class ChurnSegment(BaseModel):
    """Churn risk distribution."""
    risk: ChurnRisk
    count: int
    percentage: float
    avg_probability: float


class PropensitySegment(BaseModel):
    """Purchase propensity distribution."""
    tier: str
    count: int
    percentage: float
    avg_score: float


class MLPredictionsResponse(BaseModel):
    """ML predictions overview."""
    ltv_segments: List[LTVSegment]
    churn_segments: List[ChurnSegment]
    propensity_segments: List[PropensitySegment]
    
    total_users_predicted: int
    models_last_updated: datetime
    
    ltv_model_accuracy: Optional[float] = None
    churn_model_accuracy: Optional[float] = None
    propensity_model_accuracy: Optional[float] = None
    
    high_value_users: int
    at_risk_users: int
    ready_to_buy_users: int
    
    last_updated: datetime


# =============================================================================
# BID OPTIMIZATION
# =============================================================================

class BidStrategyMetrics(BaseModel):
    """Metrics for a bid strategy."""
    strategy: BidStrategy
    count: int
    percentage: float
    avg_multiplier: float
    total_budget_impact: float


class BidMetricsResponse(BaseModel):
    """Bid optimization metrics."""
    strategy_distribution: List[BidStrategyMetrics]
    
    total_bid_adjustments: int
    avg_multiplier: float
    
    budget_saved: float
    budget_reallocated: float
    
    excluded_users: int
    aggressive_bids: int
    retention_bids: int
    
    platform_breakdown: Dict[str, Dict[str, float]]
    
    last_updated: datetime


# =============================================================================
# FUNNEL
# =============================================================================

class FunnelStage(BaseModel):
    """Funnel stage metrics."""
    stage: str
    event_name: str
    count: int
    unique_users: int
    conversion_rate: float
    drop_off_rate: float
    avg_time_to_next: Optional[float] = None


class FunnelResponse(BaseModel):
    """Conversion funnel."""
    stages: List[FunnelStage]
    
    total_sessions: int
    completed_purchases: int
    overall_conversion_rate: float
    
    avg_time_to_purchase: Optional[float] = None
    
    comparison: Optional[Dict[str, float]] = None
    
    last_updated: datetime


# =============================================================================
# EVENTS
# =============================================================================

class EventSummary(BaseModel):
    """Summary of a single event."""
    event_id: str
    ssi_id: Optional[str] = None
    event_name: EventType
    timestamp: datetime
    
    url: Optional[str] = None
    value: Optional[float] = None
    currency: Optional[str] = None
    
    trust_score: float
    trust_action: TrustAction
    
    platforms_sent: List[str]
    platform_success: bool
    
    user_agent: Optional[str] = None
    ip_country: Optional[str] = None


class EventDetail(EventSummary):
    """Detailed event information."""
    # User data
    email_hash: Optional[str] = None
    phone_hash: Optional[str] = None
    external_id: Optional[str] = None
    
    # Trust score details
    trust_signals: Dict[str, Any] = {}
    block_reasons: List[str] = []
    
    # Platform responses
    platform_responses: Dict[str, Dict[str, Any]] = {}
    
    # ML predictions (if available)
    ltv_tier: Optional[str] = None
    churn_risk: Optional[str] = None
    propensity_score: Optional[float] = None
    
    # Bid optimization
    bid_strategy: Optional[str] = None
    bid_multiplier: Optional[float] = None
    
    # E-commerce
    content_ids: Optional[List[str]] = None
    content_type: Optional[str] = None
    content_category: Optional[str] = None
    num_items: Optional[int] = None


class EventsListResponse(BaseModel):
    """Paginated list of events."""
    events: List[EventSummary]
    total: int
    limit: int
    offset: int
    has_more: bool


class EventFilters(BaseModel):
    """Filters for events query."""
    event_types: Optional[List[EventType]] = None
    platforms: Optional[List[str]] = None
    trust_actions: Optional[List[TrustAction]] = None
    min_trust_score: Optional[float] = None
    max_trust_score: Optional[float] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    search: Optional[str] = None


# =============================================================================
# REAL-TIME
# =============================================================================

class RealtimeEvent(BaseModel):
    """Real-time event for WebSocket."""
    type: Literal["event", "metric", "alert"]
    timestamp: datetime
    data: Dict[str, Any]


class RealtimeMetrics(BaseModel):
    """Real-time metrics update."""
    events_per_second: float
    active_users: int
    revenue_last_minute: float
    error_rate: float
    avg_latency_ms: float


# =============================================================================
# REPORTS
# =============================================================================

class ReportRequest(BaseModel):
    """Request for generating a report."""
    report_type: Literal["daily", "weekly", "monthly", "custom"]
    start_date: datetime
    end_date: datetime
    include_events: bool = False
    include_ml: bool = True
    format: Literal["json", "csv", "pdf"] = "json"


class ReportResponse(BaseModel):
    """Generated report metadata."""
    report_id: str
    status: Literal["pending", "processing", "ready", "failed"]
    download_url: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None


# =============================================================================
# SETTINGS
# =============================================================================

class OrganizationSettings(BaseModel):
    """Organization settings."""
    organization_id: str
    name: str
    
    # Platform credentials (masked)
    meta_pixel_id: Optional[str] = None
    meta_configured: bool = False
    tiktok_pixel_id: Optional[str] = None
    tiktok_configured: bool = False
    ga4_measurement_id: Optional[str] = None
    ga4_configured: bool = False
    
    # Feature flags
    trust_score_enabled: bool = True
    ml_predictions_enabled: bool = True
    bid_optimization_enabled: bool = True
    
    # Thresholds
    trust_score_block_threshold: float = 0.3
    trust_score_challenge_threshold: float = 0.5
    
    # Notifications
    alert_email: Optional[EmailStr] = None
    slack_webhook_configured: bool = False
    
    created_at: datetime
    updated_at: datetime


class UpdateSettingsRequest(BaseModel):
    """Request to update settings."""
    name: Optional[str] = None
    
    meta_pixel_id: Optional[str] = None
    meta_access_token: Optional[str] = None
    tiktok_pixel_id: Optional[str] = None
    tiktok_access_token: Optional[str] = None
    ga4_measurement_id: Optional[str] = None
    ga4_api_secret: Optional[str] = None
    
    trust_score_enabled: Optional[bool] = None
    ml_predictions_enabled: Optional[bool] = None
    bid_optimization_enabled: Optional[bool] = None
    
    trust_score_block_threshold: Optional[float] = None
    trust_score_challenge_threshold: Optional[float] = None
    
    alert_email: Optional[EmailStr] = None
    slack_webhook_url: Optional[str] = None


# =============================================================================
# ERROR RESPONSES
# =============================================================================

class ErrorResponse(BaseModel):
    """Standard error response."""
    error: str
    message: str
    details: Optional[Dict[str, Any]] = None
    request_id: Optional[str] = None


class ValidationError(BaseModel):
    """Validation error detail."""
    field: str
    message: str
    value: Optional[Any] = None


class ValidationErrorResponse(BaseModel):
    """Validation error response."""
    error: str = "validation_error"
    message: str = "Request validation failed"
    errors: List[ValidationError]


# Update forward references
LoginResponse.model_rebuild()
