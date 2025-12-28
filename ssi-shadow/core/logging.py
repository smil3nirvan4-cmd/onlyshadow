"""
S.S.I. SHADOW - Structured Logging
Enterprise-grade logging with structured output.
"""

import os
import sys
import logging
import json
from datetime import datetime
from typing import Any, Dict, Optional
from contextvars import ContextVar
from functools import wraps

# Context variables for request tracking
_request_id: ContextVar[Optional[str]] = ContextVar('request_id', default=None)
_tenant_id: ContextVar[Optional[str]] = ContextVar('tenant_id', default=None)


def get_request_id() -> Optional[str]:
    return _request_id.get()


def set_request_id(request_id: str):
    _request_id.set(request_id)


class StructuredFormatter(logging.Formatter):
    """
    JSON structured log formatter.
    """
    
    def __init__(self, include_extras: bool = True):
        super().__init__()
        self.include_extras = include_extras
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add location info
        log_data["location"] = {
            "file": record.filename,
            "line": record.lineno,
            "function": record.funcName
        }
        
        # Add context
        request_id = get_request_id()
        if request_id:
            log_data["request_id"] = request_id
        
        tenant_id = _tenant_id.get()
        if tenant_id:
            log_data["tenant_id"] = tenant_id
        
        # Add exception info
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        if self.include_extras and hasattr(record, '__dict__'):
            extras = {
                k: v for k, v in record.__dict__.items()
                if k not in {
                    'name', 'msg', 'args', 'created', 'filename', 'funcName',
                    'levelname', 'levelno', 'lineno', 'module', 'msecs',
                    'pathname', 'process', 'processName', 'relativeCreated',
                    'stack_info', 'exc_info', 'exc_text', 'thread', 'threadName',
                    'message'
                }
            }
            if extras:
                log_data["extra"] = extras
        
        return json.dumps(log_data)


class ConsoleFormatter(logging.Formatter):
    """
    Human-readable console formatter with colors.
    """
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[35m', # Magenta
    }
    RESET = '\033[0m'
    
    def format(self, record: logging.LogRecord) -> str:
        color = self.COLORS.get(record.levelname, '')
        timestamp = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')
        
        # Base message
        msg = f"{color}{timestamp} [{record.levelname:8}]{self.RESET} {record.getMessage()}"
        
        # Add request ID if present
        request_id = get_request_id()
        if request_id:
            msg = f"{msg} [req:{request_id[:8]}]"
        
        # Add exception
        if record.exc_info:
            msg += f"\n{self.formatException(record.exc_info)}"
        
        return msg


class SSILogger:
    """
    Structured logger wrapper with convenience methods.
    """
    
    def __init__(self, name: str):
        self._logger = logging.getLogger(name)
    
    def _log(self, level: int, message: str, **kwargs):
        """Internal log method with extra data."""
        self._logger.log(level, message, extra=kwargs)
    
    def debug(self, message: str, **kwargs):
        self._log(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        self._log(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        self._log(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        self._log(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        self._log(logging.CRITICAL, message, **kwargs)
    
    def exception(self, message: str, **kwargs):
        self._logger.exception(message, extra=kwargs)
    
    # Convenience methods for common log patterns
    def event_received(self, event_name: str, event_id: str, **kwargs):
        self.info("Event received", event_name=event_name, event_id=event_id, **kwargs)
    
    def event_processed(self, event_name: str, event_id: str, duration_ms: int, **kwargs):
        self.info("Event processed", event_name=event_name, event_id=event_id, 
                 duration_ms=duration_ms, **kwargs)
    
    def api_call(self, service: str, method: str, duration_ms: int, status: str, **kwargs):
        self.info("API call", service=service, method=method, 
                 duration_ms=duration_ms, status=status, **kwargs)
    
    def cache_hit(self, key: str, **kwargs):
        self.debug("Cache hit", cache_key=key, **kwargs)
    
    def cache_miss(self, key: str, **kwargs):
        self.debug("Cache miss", cache_key=key, **kwargs)


def configure_logging(
    level: str = "INFO",
    json_output: bool = True,
    include_extras: bool = True
):
    """
    Configure application logging.
    
    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        json_output: Use JSON format (for production)
        include_extras: Include extra fields in JSON output
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))
    
    # Remove existing handlers
    root_logger.handlers.clear()
    
    # Create handler
    handler = logging.StreamHandler(sys.stdout)
    
    if json_output:
        handler.setFormatter(StructuredFormatter(include_extras=include_extras))
    else:
        handler.setFormatter(ConsoleFormatter())
    
    root_logger.addHandler(handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("aiohttp").setLevel(logging.WARNING)


def get_logger(name: str) -> SSILogger:
    """Get a structured logger instance."""
    return SSILogger(name)


# Decorator for logging function calls
def log_call(logger: Optional[SSILogger] = None, level: str = "DEBUG"):
    """
    Decorator to log function calls.
    
    Args:
        logger: Logger instance (uses function's module logger if not provided)
        level: Log level
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            _logger = logger or get_logger(func.__module__)
            start = datetime.utcnow()
            
            _logger._log(
                getattr(logging, level.upper()),
                f"Calling {func.__name__}",
                function=func.__name__,
                args_count=len(args),
                kwargs_keys=list(kwargs.keys())
            )
            
            try:
                result = await func(*args, **kwargs)
                duration = int((datetime.utcnow() - start).total_seconds() * 1000)
                _logger._log(
                    getattr(logging, level.upper()),
                    f"Completed {func.__name__}",
                    function=func.__name__,
                    duration_ms=duration,
                    status="success"
                )
                return result
            except Exception as e:
                duration = int((datetime.utcnow() - start).total_seconds() * 1000)
                _logger.error(
                    f"Failed {func.__name__}: {e}",
                    function=func.__name__,
                    duration_ms=duration,
                    status="error",
                    error_type=type(e).__name__
                )
                raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            _logger = logger or get_logger(func.__module__)
            start = datetime.utcnow()
            
            try:
                result = func(*args, **kwargs)
                duration = int((datetime.utcnow() - start).total_seconds() * 1000)
                _logger._log(
                    getattr(logging, level.upper()),
                    f"Completed {func.__name__}",
                    function=func.__name__,
                    duration_ms=duration
                )
                return result
            except Exception as e:
                _logger.error(f"Failed {func.__name__}: {e}")
                raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# Initialize with default configuration
configure_logging(
    level=os.getenv("LOG_LEVEL", "INFO"),
    json_output=os.getenv("LOG_FORMAT", "json") == "json"
)
