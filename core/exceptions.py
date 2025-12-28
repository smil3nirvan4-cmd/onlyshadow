"""
S.S.I. SHADOW - Custom Exceptions
Enterprise-grade exception hierarchy for the entire system.
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from enum import Enum
import traceback
import json


class ErrorSeverity(Enum):
    """Error severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ErrorCategory(Enum):
    """Error categories for classification."""
    VALIDATION = "validation"
    AUTHENTICATION = "authentication"
    AUTHORIZATION = "authorization"
    RATE_LIMIT = "rate_limit"
    EXTERNAL_API = "external_api"
    DATABASE = "database"
    CACHE = "cache"
    CONFIGURATION = "configuration"
    BUSINESS_LOGIC = "business_logic"
    INTERNAL = "internal"


class SSIShadowException(Exception):
    """
    Base exception for all SSI Shadow errors.
    
    Attributes:
        message: Human-readable error message
        error_code: Machine-readable error code (e.g., 'AUTH_001')
        category: Error category for classification
        severity: Error severity level
        details: Additional error details
        retry_after: Seconds to wait before retry (if applicable)
        request_id: Associated request ID for tracing
        timestamp: When the error occurred
    """
    
    def __init__(
        self,
        message: str,
        error_code: str = "SSI_ERR_001",
        category: ErrorCategory = ErrorCategory.INTERNAL,
        severity: ErrorSeverity = ErrorSeverity.MEDIUM,
        details: Optional[Dict[str, Any]] = None,
        retry_after: Optional[int] = None,
        request_id: Optional[str] = None,
        cause: Optional[Exception] = None
    ):
        self.message = message
        self.error_code = error_code
        self.category = category
        self.severity = severity
        self.details = details or {}
        self.retry_after = retry_after
        self.request_id = request_id
        self.timestamp = datetime.utcnow()
        self.cause = cause
        
        # Include cause in message if present
        full_message = message
        if cause:
            full_message = f"{message} (caused by: {type(cause).__name__}: {cause})"
        
        super().__init__(full_message)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert exception to dictionary for JSON serialization."""
        result = {
            "error": self.error_code,
            "message": self.message,
            "category": self.category.value,
            "severity": self.severity.value,
            "timestamp": self.timestamp.isoformat(),
        }
        
        if self.details:
            result["details"] = self.details
        
        if self.retry_after:
            result["retry_after"] = self.retry_after
        
        if self.request_id:
            result["request_id"] = self.request_id
        
        return result
    
    def to_json(self) -> str:
        """Convert exception to JSON string."""
        return json.dumps(self.to_dict())
    
    @property
    def is_retryable(self) -> bool:
        """Check if this error is retryable."""
        return self.retry_after is not None or self.category in [
            ErrorCategory.RATE_LIMIT,
            ErrorCategory.EXTERNAL_API,
            ErrorCategory.DATABASE,
            ErrorCategory.CACHE
        ]


# =============================================================================
# VALIDATION ERRORS
# =============================================================================

class ValidationException(SSIShadowException):
    """Data validation error."""
    
    def __init__(
        self,
        message: str,
        field: Optional[str] = None,
        value: Any = None,
        constraints: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if field:
            details["field"] = field
        if value is not None:
            details["value"] = str(value)[:100]  # Truncate for safety
        if constraints:
            details["constraints"] = constraints
        
        super().__init__(
            message=message,
            error_code="VAL_001",
            category=ErrorCategory.VALIDATION,
            severity=ErrorSeverity.LOW,
            details=details,
            **kwargs
        )


class SchemaValidationException(ValidationException):
    """JSON schema validation error."""
    
    def __init__(
        self,
        message: str,
        schema_errors: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if schema_errors:
            details["schema_errors"] = schema_errors
        
        super().__init__(
            message=message,
            error_code="VAL_002",
            details=details,
            **kwargs
        )


class MissingFieldException(ValidationException):
    """Required field is missing."""
    
    def __init__(self, field: str, **kwargs):
        super().__init__(
            message=f"Required field '{field}' is missing",
            field=field,
            error_code="VAL_003",
            **kwargs
        )


class InvalidFormatException(ValidationException):
    """Field has invalid format."""
    
    def __init__(
        self,
        field: str,
        value: Any,
        expected_format: str,
        **kwargs
    ):
        super().__init__(
            message=f"Field '{field}' has invalid format. Expected: {expected_format}",
            field=field,
            value=value,
            constraints={"expected_format": expected_format},
            error_code="VAL_004",
            **kwargs
        )


# =============================================================================
# AUTHENTICATION ERRORS
# =============================================================================

class AuthenticationException(SSIShadowException):
    """Authentication failed."""
    
    def __init__(
        self,
        message: str = "Authentication failed",
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="AUTH_001",
            category=ErrorCategory.AUTHENTICATION,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class InvalidCredentialsException(AuthenticationException):
    """Invalid username or password."""
    
    def __init__(self, **kwargs):
        super().__init__(
            message="Invalid credentials provided",
            error_code="AUTH_002",
            **kwargs
        )


class TokenExpiredException(AuthenticationException):
    """JWT token has expired."""
    
    def __init__(self, **kwargs):
        super().__init__(
            message="Authentication token has expired",
            error_code="AUTH_003",
            **kwargs
        )


class InvalidTokenException(AuthenticationException):
    """JWT token is invalid."""
    
    def __init__(self, reason: str = "Token is invalid", **kwargs):
        super().__init__(
            message=reason,
            error_code="AUTH_004",
            **kwargs
        )


class MissingTokenException(AuthenticationException):
    """No authentication token provided."""
    
    def __init__(self, **kwargs):
        super().__init__(
            message="Authentication token is required",
            error_code="AUTH_005",
            **kwargs
        )


# =============================================================================
# AUTHORIZATION ERRORS
# =============================================================================

class AuthorizationException(SSIShadowException):
    """Authorization failed."""
    
    def __init__(
        self,
        message: str = "Access denied",
        resource: Optional[str] = None,
        action: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if resource:
            details["resource"] = resource
        if action:
            details["action"] = action
        
        super().__init__(
            message=message,
            error_code="AUTHZ_001",
            category=ErrorCategory.AUTHORIZATION,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            **kwargs
        )


class InsufficientPermissionsException(AuthorizationException):
    """User lacks required permissions."""
    
    def __init__(
        self,
        required_permissions: List[str],
        **kwargs
    ):
        details = kwargs.pop("details", {})
        details["required_permissions"] = required_permissions
        
        super().__init__(
            message="Insufficient permissions to perform this action",
            error_code="AUTHZ_002",
            details=details,
            **kwargs
        )


class TenantAccessException(AuthorizationException):
    """Access to tenant resource denied."""
    
    def __init__(self, tenant_id: str, **kwargs):
        super().__init__(
            message=f"Access to tenant '{tenant_id}' is denied",
            error_code="AUTHZ_003",
            resource=f"tenant:{tenant_id}",
            **kwargs
        )


# =============================================================================
# RATE LIMIT ERRORS
# =============================================================================

class RateLimitException(SSIShadowException):
    """Rate limit exceeded."""
    
    def __init__(
        self,
        message: str = "Rate limit exceeded",
        limit: Optional[int] = None,
        window_seconds: Optional[int] = None,
        retry_after: int = 60,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if limit:
            details["limit"] = limit
        if window_seconds:
            details["window_seconds"] = window_seconds
        
        super().__init__(
            message=message,
            error_code="RATE_001",
            category=ErrorCategory.RATE_LIMIT,
            severity=ErrorSeverity.LOW,
            details=details,
            retry_after=retry_after,
            **kwargs
        )


class APIRateLimitException(RateLimitException):
    """API rate limit exceeded."""
    
    def __init__(
        self,
        api_name: str,
        retry_after: int = 60,
        **kwargs
    ):
        super().__init__(
            message=f"API rate limit exceeded for {api_name}",
            error_code="RATE_002",
            retry_after=retry_after,
            **kwargs
        )
        self.details["api_name"] = api_name


class ConcurrencyLimitException(RateLimitException):
    """Too many concurrent requests."""
    
    def __init__(
        self,
        current: int,
        limit: int,
        **kwargs
    ):
        super().__init__(
            message=f"Concurrency limit exceeded ({current}/{limit})",
            error_code="RATE_003",
            limit=limit,
            retry_after=5,
            **kwargs
        )
        self.details["current"] = current


# =============================================================================
# EXTERNAL API ERRORS
# =============================================================================

class PlatformAPIException(SSIShadowException):
    """External platform API error."""
    
    def __init__(
        self,
        platform: str,
        message: str,
        status_code: Optional[int] = None,
        api_error_code: Optional[str] = None,
        api_error_message: Optional[str] = None,
        retry_after: Optional[int] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        details["platform"] = platform
        if status_code:
            details["status_code"] = status_code
        if api_error_code:
            details["api_error_code"] = api_error_code
        if api_error_message:
            details["api_error_message"] = api_error_message
        
        super().__init__(
            message=f"[{platform}] {message}",
            error_code="API_001",
            category=ErrorCategory.EXTERNAL_API,
            severity=ErrorSeverity.MEDIUM,
            details=details,
            retry_after=retry_after,
            **kwargs
        )
        self.platform = platform
        self.status_code = status_code


class MetaAPIException(PlatformAPIException):
    """Meta (Facebook) API error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(platform="meta", message=message, error_code="API_META_001", **kwargs)


class GoogleAdsAPIException(PlatformAPIException):
    """Google Ads API error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(platform="google_ads", message=message, error_code="API_GADS_001", **kwargs)


class TikTokAPIException(PlatformAPIException):
    """TikTok API error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(platform="tiktok", message=message, error_code="API_TIKTOK_001", **kwargs)


class LinkedInAPIException(PlatformAPIException):
    """LinkedIn API error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(platform="linkedin", message=message, error_code="API_LINKEDIN_001", **kwargs)


class PinterestAPIException(PlatformAPIException):
    """Pinterest API error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(platform="pinterest", message=message, error_code="API_PINTEREST_001", **kwargs)


class SnapchatAPIException(PlatformAPIException):
    """Snapchat API error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(platform="snapchat", message=message, error_code="API_SNAPCHAT_001", **kwargs)


class OpenWeatherAPIException(PlatformAPIException):
    """OpenWeatherMap API error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(platform="openweathermap", message=message, error_code="API_WEATHER_001", **kwargs)


# =============================================================================
# DATABASE ERRORS
# =============================================================================

class DatabaseException(SSIShadowException):
    """Database operation error."""
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        table: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if operation:
            details["operation"] = operation
        if table:
            details["table"] = table
        
        super().__init__(
            message=message,
            error_code="DB_001",
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.HIGH,
            details=details,
            retry_after=5,
            **kwargs
        )


class BigQueryException(DatabaseException):
    """BigQuery specific error."""
    
    def __init__(self, message: str, query: Optional[str] = None, **kwargs):
        details = kwargs.pop("details", {})
        if query:
            # Truncate query for safety
            details["query"] = query[:500] + "..." if len(query) > 500 else query
        
        super().__init__(
            message=message,
            error_code="DB_BQ_001",
            details=details,
            **kwargs
        )


class RecordNotFoundException(DatabaseException):
    """Record not found in database."""
    
    def __init__(
        self,
        resource_type: str,
        resource_id: str,
        **kwargs
    ):
        super().__init__(
            message=f"{resource_type} with ID '{resource_id}' not found",
            error_code="DB_002",
            operation="SELECT",
            **kwargs
        )
        self.details["resource_type"] = resource_type
        self.details["resource_id"] = resource_id


class DuplicateRecordException(DatabaseException):
    """Duplicate record error."""
    
    def __init__(
        self,
        resource_type: str,
        field: str,
        value: str,
        **kwargs
    ):
        super().__init__(
            message=f"{resource_type} with {field}='{value}' already exists",
            error_code="DB_003",
            operation="INSERT",
            **kwargs
        )
        self.details["resource_type"] = resource_type
        self.details["field"] = field


# =============================================================================
# CACHE ERRORS
# =============================================================================

class CacheException(SSIShadowException):
    """Cache operation error."""
    
    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        key: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if operation:
            details["operation"] = operation
        if key:
            details["key"] = key
        
        super().__init__(
            message=message,
            error_code="CACHE_001",
            category=ErrorCategory.CACHE,
            severity=ErrorSeverity.LOW,
            details=details,
            retry_after=1,
            **kwargs
        )


class RedisConnectionException(CacheException):
    """Redis connection error."""
    
    def __init__(self, message: str = "Failed to connect to Redis", **kwargs):
        super().__init__(
            message=message,
            error_code="CACHE_002",
            **kwargs
        )


class CacheMissException(CacheException):
    """Cache miss (not really an error, but useful for flow control)."""
    
    def __init__(self, key: str, **kwargs):
        super().__init__(
            message=f"Cache miss for key: {key}",
            error_code="CACHE_003",
            key=key,
            **kwargs
        )


# =============================================================================
# CONFIGURATION ERRORS
# =============================================================================

class ConfigurationException(SSIShadowException):
    """Configuration error."""
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        **kwargs
    ):
        details = kwargs.pop("details", {})
        if config_key:
            details["config_key"] = config_key
        
        super().__init__(
            message=message,
            error_code="CONFIG_001",
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.CRITICAL,
            details=details,
            **kwargs
        )


class MissingConfigException(ConfigurationException):
    """Required configuration is missing."""
    
    def __init__(self, config_key: str, **kwargs):
        super().__init__(
            message=f"Required configuration '{config_key}' is missing",
            config_key=config_key,
            error_code="CONFIG_002",
            **kwargs
        )


class InvalidConfigException(ConfigurationException):
    """Configuration value is invalid."""
    
    def __init__(
        self,
        config_key: str,
        value: Any,
        reason: str,
        **kwargs
    ):
        super().__init__(
            message=f"Invalid configuration for '{config_key}': {reason}",
            config_key=config_key,
            error_code="CONFIG_003",
            **kwargs
        )
        self.details["value"] = str(value)[:100]
        self.details["reason"] = reason


# =============================================================================
# BUSINESS LOGIC ERRORS
# =============================================================================

class BusinessLogicException(SSIShadowException):
    """Business logic error."""
    
    def __init__(
        self,
        message: str,
        **kwargs
    ):
        super().__init__(
            message=message,
            error_code="BIZ_001",
            category=ErrorCategory.BUSINESS_LOGIC,
            severity=ErrorSeverity.MEDIUM,
            **kwargs
        )


class InsufficientBudgetException(BusinessLogicException):
    """Insufficient budget for operation."""
    
    def __init__(
        self,
        required: float,
        available: float,
        currency: str = "USD",
        **kwargs
    ):
        super().__init__(
            message=f"Insufficient budget: required {currency} {required:.2f}, available {currency} {available:.2f}",
            error_code="BIZ_002",
            **kwargs
        )
        self.details["required"] = required
        self.details["available"] = available
        self.details["currency"] = currency


class CampaignLimitException(BusinessLogicException):
    """Campaign limit exceeded."""
    
    def __init__(
        self,
        current: int,
        limit: int,
        **kwargs
    ):
        super().__init__(
            message=f"Campaign limit exceeded: {current}/{limit}",
            error_code="BIZ_003",
            **kwargs
        )
        self.details["current"] = current
        self.details["limit"] = limit


class OptimizationException(BusinessLogicException):
    """Optimization process error."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            message=message,
            error_code="BIZ_004",
            severity=ErrorSeverity.HIGH,
            **kwargs
        )


# =============================================================================
# CIRCUIT BREAKER ERRORS
# =============================================================================

class CircuitBreakerOpenException(SSIShadowException):
    """Circuit breaker is open, requests are being blocked."""
    
    def __init__(
        self,
        service_name: str,
        retry_after: int = 30,
        **kwargs
    ):
        super().__init__(
            message=f"Circuit breaker for '{service_name}' is open",
            error_code="CB_001",
            category=ErrorCategory.EXTERNAL_API,
            severity=ErrorSeverity.HIGH,
            retry_after=retry_after,
            **kwargs
        )
        self.details["service_name"] = service_name


# =============================================================================
# STARTUP ERRORS
# =============================================================================

class StartupException(SSIShadowException):
    """System startup error."""
    
    def __init__(
        self,
        component: str,
        message: str,
        **kwargs
    ):
        super().__init__(
            message=f"Startup failed for '{component}': {message}",
            error_code="STARTUP_001",
            category=ErrorCategory.CONFIGURATION,
            severity=ErrorSeverity.CRITICAL,
            **kwargs
        )
        self.details["component"] = component


class SystemConfigurationError(StartupException):
    """System is misconfigured and cannot start."""
    
    def __init__(self, message: str, **kwargs):
        super().__init__(
            component="system",
            message=message,
            error_code="STARTUP_002",
            **kwargs
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def is_retryable_exception(exc: Exception) -> bool:
    """Check if an exception is retryable."""
    if isinstance(exc, SSIShadowException):
        return exc.is_retryable
    
    # Common retryable exception types
    retryable_types = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    
    return isinstance(exc, retryable_types)


def get_retry_after(exc: Exception) -> Optional[int]:
    """Get retry-after value from exception."""
    if isinstance(exc, SSIShadowException):
        return exc.retry_after
    return None


def exception_to_http_status(exc: SSIShadowException) -> int:
    """Map exception to HTTP status code."""
    status_map = {
        ErrorCategory.VALIDATION: 400,
        ErrorCategory.AUTHENTICATION: 401,
        ErrorCategory.AUTHORIZATION: 403,
        ErrorCategory.RATE_LIMIT: 429,
        ErrorCategory.EXTERNAL_API: 502,
        ErrorCategory.DATABASE: 503,
        ErrorCategory.CACHE: 503,
        ErrorCategory.CONFIGURATION: 500,
        ErrorCategory.BUSINESS_LOGIC: 422,
        ErrorCategory.INTERNAL: 500,
    }
    return status_map.get(exc.category, 500)


def format_exception_for_logging(exc: Exception) -> Dict[str, Any]:
    """Format exception for structured logging."""
    if isinstance(exc, SSIShadowException):
        return {
            "exception_type": type(exc).__name__,
            "error_code": exc.error_code,
            "message": exc.message,
            "category": exc.category.value,
            "severity": exc.severity.value,
            "details": exc.details,
            "traceback": traceback.format_exc()
        }
    
    return {
        "exception_type": type(exc).__name__,
        "message": str(exc),
        "traceback": traceback.format_exc()
    }
