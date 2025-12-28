"""
SSI Shadow - Monitoring & Observability
"""
from .metrics import metrics, PrometheusMiddleware
from .health import health_router, ProbeChecker, init_health_routes
from .logging_config import setup_logging, LoggingMiddleware, get_logger

__all__ = [
    "metrics", "PrometheusMiddleware",
    "health_router", "ProbeChecker", "init_health_routes",
    "setup_logging", "LoggingMiddleware", "get_logger",
]
__version__ = "2.0.0"
