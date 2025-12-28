"""
S.S.I. SHADOW - Global Error Handler Middleware
Catches all exceptions and returns consistent JSON responses.
"""

import logging
import traceback
import uuid
from datetime import datetime
from typing import Any, Callable, Dict, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_401_UNAUTHORIZED,
    HTTP_403_FORBIDDEN,
    HTTP_404_NOT_FOUND,
    HTTP_422_UNPROCESSABLE_ENTITY,
    HTTP_429_TOO_MANY_REQUESTS,
    HTTP_500_INTERNAL_SERVER_ERROR,
    HTTP_502_BAD_GATEWAY,
    HTTP_503_SERVICE_UNAVAILABLE
)

# Import our custom exceptions
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from core.exceptions import (
    SSIShadowException,
    ValidationException,
    SchemaValidationException,
    AuthenticationException,
    TokenExpiredException,
    InvalidTokenException,
    MissingTokenException,
    AuthorizationException,
    InsufficientPermissionsException,
    TenantAccessException,
    RateLimitException,
    APIRateLimitException,
    PlatformAPIException,
    DatabaseException,
    BigQueryException,
    RecordNotFoundException,
    CacheException,
    RedisConnectionException,
    ConfigurationException,
    BusinessLogicException,
    CircuitBreakerOpenException,
    ErrorCategory,
    exception_to_http_status,
    format_exception_for_logging
)

logger = logging.getLogger(__name__)


# =============================================================================
# ERROR RESPONSE MODELS
# =============================================================================

def create_error_response(
    error_code: str,
    message: str,
    status_code: int,
    details: Optional[Dict[str, Any]] = None,
    request_id: Optional[str] = None,
    retry_after: Optional[int] = None
) -> Dict[str, Any]:
    """Create standardized error response."""
    response = {
        "error": {
            "code": error_code,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        }
    }
    
    if details:
        response["error"]["details"] = details
    
    if request_id:
        response["error"]["request_id"] = request_id
    
    if retry_after:
        response["error"]["retry_after"] = retry_after
    
    return response


# =============================================================================
# EXCEPTION HANDLERS
# =============================================================================

def handle_ssi_shadow_exception(
    request: Request,
    exc: SSIShadowException,
    request_id: str
) -> JSONResponse:
    """Handle SSIShadowException and its subclasses."""
    status_code = exception_to_http_status(exc)
    
    response_data = create_error_response(
        error_code=exc.error_code,
        message=exc.message,
        status_code=status_code,
        details=exc.details if exc.details else None,
        request_id=request_id,
        retry_after=exc.retry_after
    )
    
    headers = {}
    if exc.retry_after:
        headers["Retry-After"] = str(exc.retry_after)
    
    return JSONResponse(
        status_code=status_code,
        content=response_data,
        headers=headers if headers else None
    )


def handle_validation_error(
    request: Request,
    exc: RequestValidationError,
    request_id: str
) -> JSONResponse:
    """Handle Pydantic validation errors."""
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    response_data = create_error_response(
        error_code="VAL_SCHEMA_001",
        message="Request validation failed",
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        details={"validation_errors": errors},
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=HTTP_422_UNPROCESSABLE_ENTITY,
        content=response_data
    )


def handle_http_exception(
    request: Request,
    exc: HTTPException,
    request_id: str
) -> JSONResponse:
    """Handle FastAPI HTTPException."""
    error_code_map = {
        400: "HTTP_400",
        401: "HTTP_401",
        403: "HTTP_403",
        404: "HTTP_404",
        405: "HTTP_405",
        422: "HTTP_422",
        429: "HTTP_429",
        500: "HTTP_500",
        502: "HTTP_502",
        503: "HTTP_503",
    }
    
    error_code = error_code_map.get(exc.status_code, f"HTTP_{exc.status_code}")
    
    response_data = create_error_response(
        error_code=error_code,
        message=exc.detail if isinstance(exc.detail, str) else str(exc.detail),
        status_code=exc.status_code,
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=exc.status_code,
        content=response_data,
        headers=exc.headers
    )


def handle_generic_exception(
    request: Request,
    exc: Exception,
    request_id: str,
    include_traceback: bool = False
) -> JSONResponse:
    """Handle unexpected exceptions."""
    # Log the full exception
    logger.exception(
        "Unhandled exception",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc)
        }
    )
    
    details = None
    if include_traceback:
        details = {
            "exception_type": type(exc).__name__,
            "traceback": traceback.format_exc()
        }
    
    response_data = create_error_response(
        error_code="INTERNAL_ERROR",
        message="An unexpected error occurred. Please try again later.",
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        details=details,
        request_id=request_id
    )
    
    return JSONResponse(
        status_code=HTTP_500_INTERNAL_SERVER_ERROR,
        content=response_data
    )


# =============================================================================
# ERROR HANDLER MIDDLEWARE
# =============================================================================

class ErrorHandlerMiddleware(BaseHTTPMiddleware):
    """
    Middleware that catches all exceptions and returns consistent JSON responses.
    
    Features:
    - Consistent error response format
    - Request ID tracking
    - Structured logging
    - Optional stack traces in development
    - Retry-After headers for rate limiting
    """
    
    def __init__(
        self,
        app: FastAPI,
        include_traceback: bool = False,
        log_all_errors: bool = True
    ):
        """
        Initialize the error handler middleware.
        
        Args:
            app: FastAPI application
            include_traceback: Whether to include traceback in error responses
            log_all_errors: Whether to log all errors (not just 5xx)
        """
        super().__init__(app)
        self.include_traceback = include_traceback
        self.log_all_errors = log_all_errors
    
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint
    ) -> Response:
        """Process request and handle any exceptions."""
        # Generate or extract request ID
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        
        # Add request ID to request state for access in handlers
        request.state.request_id = request_id
        
        try:
            response = await call_next(request)
            
            # Add request ID to response headers
            response.headers["X-Request-ID"] = request_id
            
            return response
        
        except SSIShadowException as exc:
            # Handle our custom exceptions
            exc.request_id = request_id
            
            if self.log_all_errors or exc.severity.value in ["high", "critical"]:
                log_data = format_exception_for_logging(exc)
                log_data["request_id"] = request_id
                log_data["path"] = request.url.path
                log_data["method"] = request.method
                
                if exc.severity.value == "critical":
                    logger.critical("Critical error", extra=log_data)
                elif exc.severity.value == "high":
                    logger.error("High severity error", extra=log_data)
                else:
                    logger.warning("Error", extra=log_data)
            
            response = handle_ssi_shadow_exception(request, exc, request_id)
            response.headers["X-Request-ID"] = request_id
            return response
        
        except RequestValidationError as exc:
            if self.log_all_errors:
                logger.warning(
                    "Validation error",
                    extra={
                        "request_id": request_id,
                        "path": request.url.path,
                        "errors": exc.errors()
                    }
                )
            
            response = handle_validation_error(request, exc, request_id)
            response.headers["X-Request-ID"] = request_id
            return response
        
        except HTTPException as exc:
            if self.log_all_errors:
                logger.warning(
                    f"HTTP {exc.status_code}",
                    extra={
                        "request_id": request_id,
                        "path": request.url.path,
                        "detail": exc.detail
                    }
                )
            
            response = handle_http_exception(request, exc, request_id)
            response.headers["X-Request-ID"] = request_id
            return response
        
        except Exception as exc:
            response = handle_generic_exception(
                request, exc, request_id, self.include_traceback
            )
            response.headers["X-Request-ID"] = request_id
            return response


# =============================================================================
# SETUP FUNCTION
# =============================================================================

def setup_error_handling(
    app: FastAPI,
    include_traceback: bool = False,
    log_all_errors: bool = True
):
    """
    Setup error handling for a FastAPI application.
    
    Args:
        app: FastAPI application
        include_traceback: Include traceback in error responses (dev only!)
        log_all_errors: Log all errors, not just 5xx
    
    Example:
        app = FastAPI()
        setup_error_handling(app, include_traceback=settings.DEBUG)
    """
    # Add middleware
    app.add_middleware(
        ErrorHandlerMiddleware,
        include_traceback=include_traceback,
        log_all_errors=log_all_errors
    )
    
    # Add exception handlers for specific types
    @app.exception_handler(SSIShadowException)
    async def ssi_exception_handler(request: Request, exc: SSIShadowException):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return handle_ssi_shadow_exception(request, exc, request_id)
    
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return handle_validation_error(request, exc, request_id)
    
    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return handle_http_exception(request, exc, request_id)
    
    @app.exception_handler(Exception)
    async def generic_exception_handler(request: Request, exc: Exception):
        request_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return handle_generic_exception(request, exc, request_id, include_traceback)
    
    logger.info("Error handling configured for FastAPI application")


# =============================================================================
# UTILITY DECORATORS
# =============================================================================

def handle_exceptions(
    error_message: str = "Operation failed",
    error_code: str = "OP_FAILED",
    log_exceptions: bool = True
):
    """
    Decorator to handle exceptions in route handlers.
    
    Args:
        error_message: Message to use if exception occurs
        error_code: Error code to use if exception occurs
        log_exceptions: Whether to log exceptions
    
    Example:
        @router.get("/data")
        @handle_exceptions(error_message="Failed to fetch data")
        async def get_data():
            return await fetch_data()
    """
    def decorator(func: Callable):
        async def wrapper(*args, **kwargs):
            try:
                return await func(*args, **kwargs)
            except SSIShadowException:
                raise
            except HTTPException:
                raise
            except Exception as e:
                if log_exceptions:
                    logger.exception(f"{error_message}: {e}")
                
                raise SSIShadowException(
                    message=error_message,
                    error_code=error_code,
                    cause=e
                )
        
        return wrapper
    
    return decorator


# =============================================================================
# ERROR RESPONSE HELPERS
# =============================================================================

def bad_request(
    message: str,
    details: Optional[Dict[str, Any]] = None
) -> HTTPException:
    """Create a 400 Bad Request exception."""
    return HTTPException(
        status_code=HTTP_400_BAD_REQUEST,
        detail={"message": message, "details": details}
    )


def unauthorized(message: str = "Authentication required") -> HTTPException:
    """Create a 401 Unauthorized exception."""
    return HTTPException(
        status_code=HTTP_401_UNAUTHORIZED,
        detail=message,
        headers={"WWW-Authenticate": "Bearer"}
    )


def forbidden(message: str = "Access denied") -> HTTPException:
    """Create a 403 Forbidden exception."""
    return HTTPException(
        status_code=HTTP_403_FORBIDDEN,
        detail=message
    )


def not_found(resource: str, resource_id: str) -> HTTPException:
    """Create a 404 Not Found exception."""
    return HTTPException(
        status_code=HTTP_404_NOT_FOUND,
        detail=f"{resource} with ID '{resource_id}' not found"
    )


def rate_limited(
    retry_after: int = 60,
    message: str = "Rate limit exceeded"
) -> HTTPException:
    """Create a 429 Too Many Requests exception."""
    return HTTPException(
        status_code=HTTP_429_TOO_MANY_REQUESTS,
        detail=message,
        headers={"Retry-After": str(retry_after)}
    )


def service_unavailable(
    service: str,
    retry_after: int = 30
) -> HTTPException:
    """Create a 503 Service Unavailable exception."""
    return HTTPException(
        status_code=HTTP_503_SERVICE_UNAVAILABLE,
        detail=f"Service '{service}' is temporarily unavailable",
        headers={"Retry-After": str(retry_after)}
    )
