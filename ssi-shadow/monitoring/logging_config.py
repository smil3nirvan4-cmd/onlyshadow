"""
S.S.I. SHADOW - Structured Logging Module
=========================================
JSON-structured logging with context propagation and trace correlation.

Usage:
    from monitoring.logging_config import setup_logging, get_logger
    
    # Setup at startup
    setup_logging(level="INFO", format="json")
    
    # Get logger
    logger = get_logger(__name__)
    logger.info("Event processed", event_id="123", platform="meta")
"""

import logging
import sys
import json
import os
from datetime import datetime
from typing import Optional, Dict, Any
from contextvars import ContextVar
from functools import wraps

import structlog
from structlog.processors import JSONRenderer, TimeStamper, add_log_level
from structlog.stdlib import filter_by_level, add_logger_name, ProcessorFormatter

# Context variables for request-scoped data
request_id_var: ContextVar[str] = ContextVar('request_id', default='')
trace_id_var: ContextVar[str] = ContextVar('trace_id', default='')
user_id_var: ContextVar[str] = ContextVar('user_id', default='')


# =============================================================================
# CUSTOM PROCESSORS
# =============================================================================

def add_app_context(logger, method_name, event_dict):
    """Add application context to log events."""
    event_dict['service'] = os.getenv('SERVICE_NAME', 'ssi-shadow')
    event_dict['environment'] = os.getenv('APP_ENV', 'development')
    event_dict['version'] = os.getenv('APP_VERSION', '2.0.0')
    event_dict['host'] = os.getenv('HOSTNAME', 'unknown')
    return event_dict


def add_request_context(logger, method_name, event_dict):
    """Add request context from context variables."""
    if request_id := request_id_var.get():
        event_dict['request_id'] = request_id
    if trace_id := trace_id_var.get():
        event_dict['trace_id'] = trace_id
    if user_id := user_id_var.get():
        event_dict['user_id'] = user_id
    return event_dict


def add_caller_info(logger, method_name, event_dict):
    """Add caller information (file, function, line)."""
    import inspect
    
    # Walk up the stack to find the actual caller
    frame = None
    for f in inspect.stack():
        if 'structlog' not in f.filename and 'logging' not in f.filename:
            if 'monitoring' not in f.filename or 'test' in f.filename:
                frame = f
                break
    
    if frame:
        event_dict['caller'] = {
            'file': os.path.basename(frame.filename),
            'function': frame.function,
            'line': frame.lineno
        }
    
    return event_dict


def censor_sensitive(logger, method_name, event_dict):
    """Censor sensitive data in log events."""
    sensitive_keys = {
        'password', 'token', 'secret', 'api_key', 'access_token',
        'refresh_token', 'private_key', 'authorization', 'cookie',
        'email', 'phone', 'ip', 'credit_card', 'ssn'
    }
    
    def censor_dict(d):
        if not isinstance(d, dict):
            return d
        
        result = {}
        for key, value in d.items():
            key_lower = key.lower()
            if any(s in key_lower for s in sensitive_keys):
                if isinstance(value, str) and len(value) > 4:
                    result[key] = value[:2] + '*' * (len(value) - 4) + value[-2:]
                else:
                    result[key] = '***'
            elif isinstance(value, dict):
                result[key] = censor_dict(value)
            elif isinstance(value, list):
                result[key] = [censor_dict(item) if isinstance(item, dict) else item for item in value]
            else:
                result[key] = value
        return result
    
    return censor_dict(event_dict)


def format_exception(logger, method_name, event_dict):
    """Format exception information."""
    if exc_info := event_dict.pop('exc_info', None):
        if exc_info:
            import traceback
            event_dict['exception'] = {
                'type': exc_info[0].__name__ if exc_info[0] else None,
                'message': str(exc_info[1]) if exc_info[1] else None,
                'traceback': ''.join(traceback.format_exception(*exc_info))
            }
    return event_dict


# =============================================================================
# SETUP FUNCTIONS
# =============================================================================

def setup_logging(
    level: str = "INFO",
    format: str = "json",  # "json" or "console"
    enable_stdlib: bool = True,
    log_file: str = None
) -> None:
    """
    Setup structured logging.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        format: Output format ("json" or "console")
        enable_stdlib: Enable stdlib logging integration
        log_file: Optional log file path
    """
    # Determine log level
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Shared processors
    shared_processors = [
        add_log_level,
        add_logger_name,
        TimeStamper(fmt="iso", utc=True),
        add_app_context,
        add_request_context,
        format_exception,
        censor_sensitive,
        structlog.stdlib.ExtraAdder(),
    ]
    
    # Configure output format
    if format == "json":
        # JSON output for production
        processors = shared_processors + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        
        renderer = JSONRenderer(
            serializer=lambda obj, **kwargs: json.dumps(obj, default=str, **kwargs)
        )
    else:
        # Console output for development
        processors = shared_processors + [
            add_caller_info,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ]
        
        renderer = structlog.dev.ConsoleRenderer(
            colors=True,
            exception_formatter=structlog.dev.rich_traceback
        )
    
    # Configure structlog
    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )
    
    # Configure stdlib logging
    formatter = ProcessorFormatter(
        processor=renderer,
        foreign_pre_chain=shared_processors,
    )
    
    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(log_level)
    
    # File handler (optional)
    handlers = [console_handler]
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(log_level)
        handlers.append(file_handler)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.handlers = handlers
    
    # Reduce noise from third-party libraries
    for lib in ['urllib3', 'httpx', 'httpcore', 'asyncio', 'google']:
        logging.getLogger(lib).setLevel(logging.WARNING)


def get_logger(name: str = None) -> structlog.stdlib.BoundLogger:
    """
    Get a structured logger.
    
    Args:
        name: Logger name (usually __name__)
    
    Returns:
        Bound logger instance
    """
    return structlog.get_logger(name or __name__)


# =============================================================================
# CONTEXT MANAGERS
# =============================================================================

class LogContext:
    """Context manager for adding temporary context to logs."""
    
    def __init__(self, **kwargs):
        self.context = kwargs
        self.tokens = {}
    
    def __enter__(self):
        for key, value in self.context.items():
            if key == 'request_id':
                self.tokens[key] = request_id_var.set(value)
            elif key == 'trace_id':
                self.tokens[key] = trace_id_var.set(value)
            elif key == 'user_id':
                self.tokens[key] = user_id_var.set(value)
        return self
    
    def __exit__(self, *args):
        for key, token in self.tokens.items():
            if key == 'request_id':
                request_id_var.reset(token)
            elif key == 'trace_id':
                trace_id_var.reset(token)
            elif key == 'user_id':
                user_id_var.reset(token)


def set_request_context(
    request_id: str = None,
    trace_id: str = None,
    user_id: str = None
):
    """Set request context for logging."""
    if request_id:
        request_id_var.set(request_id)
    if trace_id:
        trace_id_var.set(trace_id)
    if user_id:
        user_id_var.set(user_id)


def clear_request_context():
    """Clear request context."""
    request_id_var.set('')
    trace_id_var.set('')
    user_id_var.set('')


# =============================================================================
# DECORATORS
# =============================================================================

def log_function_call(level: str = "DEBUG"):
    """Decorator to log function calls."""
    def decorator(func):
        logger = get_logger(func.__module__)
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            log_method = getattr(logger, level.lower())
            log_method(
                "Function called",
                function=func.__name__,
                args_count=len(args),
                kwargs_keys=list(kwargs.keys())
            )
            try:
                result = await func(*args, **kwargs)
                log_method(
                    "Function completed",
                    function=func.__name__,
                    success=True
                )
                return result
            except Exception as e:
                logger.exception(
                    "Function failed",
                    function=func.__name__,
                    error=str(e)
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            log_method = getattr(logger, level.lower())
            log_method(
                "Function called",
                function=func.__name__,
                args_count=len(args),
                kwargs_keys=list(kwargs.keys())
            )
            try:
                result = func(*args, **kwargs)
                log_method(
                    "Function completed",
                    function=func.__name__,
                    success=True
                )
                return result
            except Exception as e:
                logger.exception(
                    "Function failed",
                    function=func.__name__,
                    error=str(e)
                )
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# =============================================================================
# FASTAPI MIDDLEWARE
# =============================================================================

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    import uuid
    
    class LoggingMiddleware(BaseHTTPMiddleware):
        """Middleware for automatic request logging."""
        
        def __init__(self, app, logger_name: str = "api"):
            super().__init__(app)
            self.logger = get_logger(logger_name)
        
        async def dispatch(self, request: Request, call_next) -> Response:
            # Generate request ID
            request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
            trace_id = request.headers.get("X-Trace-ID", "")
            
            # Set context
            set_request_context(
                request_id=request_id,
                trace_id=trace_id
            )
            
            # Log request
            self.logger.info(
                "Request started",
                method=request.method,
                path=request.url.path,
                query=str(request.query_params),
                client_ip=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent", ""),
            )
            
            start_time = datetime.utcnow()
            
            try:
                response = await call_next(request)
                
                # Calculate duration
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                # Log response
                log_method = self.logger.info if response.status_code < 400 else self.logger.warning
                log_method(
                    "Request completed",
                    method=request.method,
                    path=request.url.path,
                    status_code=response.status_code,
                    duration_ms=round(duration_ms, 2),
                )
                
                # Add request ID to response
                response.headers["X-Request-ID"] = request_id
                
                return response
                
            except Exception as e:
                duration_ms = (datetime.utcnow() - start_time).total_seconds() * 1000
                
                self.logger.exception(
                    "Request failed",
                    method=request.method,
                    path=request.url.path,
                    duration_ms=round(duration_ms, 2),
                    error=str(e)
                )
                raise
            finally:
                clear_request_context()

except ImportError:
    pass  # FastAPI not installed


# =============================================================================
# LOG AGGREGATION HELPERS
# =============================================================================

class EventLogger:
    """Helper class for logging specific event types."""
    
    def __init__(self, logger: structlog.stdlib.BoundLogger = None):
        self.logger = logger or get_logger("events")
    
    def event_received(
        self,
        event_id: str,
        event_name: str,
        platform: str = None,
        value: float = None,
        **kwargs
    ):
        """Log event received."""
        self.logger.info(
            "Event received",
            event_id=event_id,
            event_name=event_name,
            platform=platform,
            value=value,
            **kwargs
        )
    
    def event_processed(
        self,
        event_id: str,
        event_name: str,
        duration_ms: float,
        platforms: list = None,
        **kwargs
    ):
        """Log event processed."""
        self.logger.info(
            "Event processed",
            event_id=event_id,
            event_name=event_name,
            duration_ms=round(duration_ms, 2),
            platforms=platforms or [],
            **kwargs
        )
    
    def event_blocked(
        self,
        event_id: str,
        reason: str,
        trust_score: float = None,
        **kwargs
    ):
        """Log event blocked."""
        self.logger.warning(
            "Event blocked",
            event_id=event_id,
            reason=reason,
            trust_score=trust_score,
            **kwargs
        )
    
    def platform_error(
        self,
        platform: str,
        error: str,
        event_id: str = None,
        **kwargs
    ):
        """Log platform error."""
        self.logger.error(
            "Platform error",
            platform=platform,
            error=error,
            event_id=event_id,
            **kwargs
        )


# Create global event logger instance
event_logger = EventLogger()
