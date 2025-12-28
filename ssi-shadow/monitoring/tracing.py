"""
S.S.I. SHADOW - Distributed Tracing Module
==========================================
OpenTelemetry integration for distributed tracing across services.

Usage:
    from monitoring.tracing import tracer, init_tracing
    
    # Initialize at startup
    init_tracing(service_name="ssi-shadow-api")
    
    # Create spans
    with tracer.start_as_current_span("process_event") as span:
        span.set_attribute("event.name", "Purchase")
        span.set_attribute("event.value", 99.99)
        process_event()
"""

import os
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager
from functools import wraps

# OpenTelemetry imports
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.propagate import set_global_textmap
from opentelemetry.propagators.b3 import B3MultiFormat
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Instrumentation
from opentelemetry.instrumentation.requests import RequestsInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.instrumentation.logging import LoggingInstrumentor

logger = logging.getLogger(__name__)

# Global tracer
tracer: trace.Tracer = trace.get_tracer(__name__)


def init_tracing(
    service_name: str = "ssi-shadow",
    service_version: str = "2.0.0",
    environment: str = None,
    exporter_type: str = "otlp",
    otlp_endpoint: str = None,
    jaeger_host: str = None,
    jaeger_port: int = 6831,
    sample_rate: float = 1.0,
    enable_console: bool = False
) -> trace.Tracer:
    """
    Initialize OpenTelemetry tracing.
    
    Args:
        service_name: Name of the service
        service_version: Version of the service
        environment: Deployment environment (production, staging, etc.)
        exporter_type: Type of exporter ('otlp', 'jaeger', 'console')
        otlp_endpoint: OTLP collector endpoint
        jaeger_host: Jaeger agent host
        jaeger_port: Jaeger agent port
        sample_rate: Sampling rate (0.0 to 1.0)
        enable_console: Also log spans to console
    
    Returns:
        Configured tracer instance
    """
    global tracer
    
    # Get config from environment
    environment = environment or os.getenv("APP_ENV", "development")
    otlp_endpoint = otlp_endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    jaeger_host = jaeger_host or os.getenv("JAEGER_AGENT_HOST", "localhost")
    
    # Create resource
    resource = Resource.create({
        SERVICE_NAME: service_name,
        SERVICE_VERSION: service_version,
        "deployment.environment": environment,
        "service.namespace": "ssi-shadow",
        "host.name": os.getenv("HOSTNAME", "unknown"),
    })
    
    # Create tracer provider with sampling
    from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
    sampler = TraceIdRatioBased(sample_rate)
    
    provider = TracerProvider(
        resource=resource,
        sampler=sampler
    )
    
    # Add exporters
    if exporter_type == "otlp":
        try:
            otlp_exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(otlp_exporter))
            logger.info(f"OTLP exporter configured: {otlp_endpoint}")
        except Exception as e:
            logger.warning(f"Failed to configure OTLP exporter: {e}")
    
    elif exporter_type == "jaeger":
        try:
            jaeger_exporter = JaegerExporter(
                agent_host_name=jaeger_host,
                agent_port=jaeger_port,
            )
            provider.add_span_processor(BatchSpanProcessor(jaeger_exporter))
            logger.info(f"Jaeger exporter configured: {jaeger_host}:{jaeger_port}")
        except Exception as e:
            logger.warning(f"Failed to configure Jaeger exporter: {e}")
    
    if enable_console or environment == "development":
        console_exporter = ConsoleSpanExporter()
        provider.add_span_processor(BatchSpanProcessor(console_exporter))
    
    # Set global tracer provider
    trace.set_tracer_provider(provider)
    
    # Set up propagation
    set_global_textmap(TraceContextTextMapPropagator())
    
    # Auto-instrument libraries
    _instrument_libraries()
    
    # Get tracer
    tracer = trace.get_tracer(service_name, service_version)
    
    logger.info(f"Tracing initialized for {service_name} v{service_version}")
    
    return tracer


def _instrument_libraries():
    """Auto-instrument common libraries."""
    try:
        RequestsInstrumentor().instrument()
        logger.debug("Instrumented: requests")
    except Exception as e:
        logger.debug(f"Could not instrument requests: {e}")
    
    try:
        HTTPXClientInstrumentor().instrument()
        logger.debug("Instrumented: httpx")
    except Exception as e:
        logger.debug(f"Could not instrument httpx: {e}")
    
    try:
        RedisInstrumentor().instrument()
        logger.debug("Instrumented: redis")
    except Exception as e:
        logger.debug(f"Could not instrument redis: {e}")
    
    try:
        LoggingInstrumentor().instrument(set_logging_format=True)
        logger.debug("Instrumented: logging")
    except Exception as e:
        logger.debug(f"Could not instrument logging: {e}")


# =============================================================================
# DECORATORS
# =============================================================================

def traced(
    name: str = None,
    attributes: Dict[str, Any] = None,
    record_exception: bool = True
):
    """
    Decorator to create a span for a function.
    
    Args:
        name: Span name (defaults to function name)
        attributes: Additional span attributes
        record_exception: Whether to record exceptions
    
    Example:
        @traced(name="process_event", attributes={"component": "events"})
        def process_event(event):
            ...
    """
    def decorator(func):
        span_name = name or func.__name__
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    if record_exception:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for key, value in attributes.items():
                        span.set_attribute(key, value)
                try:
                    result = func(*args, **kwargs)
                    span.set_status(Status(StatusCode.OK))
                    return result
                except Exception as e:
                    if record_exception:
                        span.record_exception(e)
                        span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


# =============================================================================
# CONTEXT MANAGERS
# =============================================================================

@contextmanager
def span(
    name: str,
    attributes: Dict[str, Any] = None,
    kind: trace.SpanKind = trace.SpanKind.INTERNAL
):
    """
    Context manager for creating spans.
    
    Example:
        with span("process_event", {"event.name": "Purchase"}) as s:
            process_event()
            s.add_event("validation_complete")
    """
    with tracer.start_as_current_span(name, kind=kind) as s:
        if attributes:
            for key, value in attributes.items():
                s.set_attribute(key, value)
        try:
            yield s
            s.set_status(Status(StatusCode.OK))
        except Exception as e:
            s.record_exception(e)
            s.set_status(Status(StatusCode.ERROR, str(e)))
            raise


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_current_span() -> trace.Span:
    """Get the current active span."""
    return trace.get_current_span()


def get_trace_id() -> Optional[str]:
    """Get the current trace ID as a hex string."""
    span = trace.get_current_span()
    if span.get_span_context().is_valid:
        return format(span.get_span_context().trace_id, '032x')
    return None


def get_span_id() -> Optional[str]:
    """Get the current span ID as a hex string."""
    span = trace.get_current_span()
    if span.get_span_context().is_valid:
        return format(span.get_span_context().span_id, '016x')
    return None


def add_event(name: str, attributes: Dict[str, Any] = None):
    """Add an event to the current span."""
    span = trace.get_current_span()
    span.add_event(name, attributes=attributes)


def set_attribute(key: str, value: Any):
    """Set an attribute on the current span."""
    span = trace.get_current_span()
    span.set_attribute(key, value)


def set_error(exception: Exception, message: str = None):
    """Record an error on the current span."""
    span = trace.get_current_span()
    span.record_exception(exception)
    span.set_status(Status(StatusCode.ERROR, message or str(exception)))


# =============================================================================
# EVENT-SPECIFIC TRACING
# =============================================================================

class EventTracer:
    """Helper class for tracing event processing."""
    
    @staticmethod
    @contextmanager
    def process_event(event_id: str, event_name: str, platform: str = None):
        """Create a span for processing an event."""
        with tracer.start_as_current_span(
            "process_event",
            kind=trace.SpanKind.CONSUMER
        ) as span:
            span.set_attribute("event.id", event_id)
            span.set_attribute("event.name", event_name)
            if platform:
                span.set_attribute("event.platform", platform)
            yield span
    
    @staticmethod
    @contextmanager
    def platform_request(platform: str, endpoint: str):
        """Create a span for a platform API request."""
        with tracer.start_as_current_span(
            f"platform.{platform}",
            kind=trace.SpanKind.CLIENT
        ) as span:
            span.set_attribute("platform.name", platform)
            span.set_attribute("platform.endpoint", endpoint)
            span.set_attribute("http.method", "POST")
            yield span
    
    @staticmethod
    @contextmanager
    def ml_prediction(model: str, prediction_type: str):
        """Create a span for ML prediction."""
        with tracer.start_as_current_span(
            f"ml.{model}",
            kind=trace.SpanKind.INTERNAL
        ) as span:
            span.set_attribute("ml.model", model)
            span.set_attribute("ml.prediction_type", prediction_type)
            yield span
    
    @staticmethod
    @contextmanager
    def trust_score_calculation():
        """Create a span for trust score calculation."""
        with tracer.start_as_current_span(
            "trust_score.calculate",
            kind=trace.SpanKind.INTERNAL
        ) as span:
            yield span


event_tracer = EventTracer()


# =============================================================================
# FASTAPI MIDDLEWARE
# =============================================================================

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    
    class TracingMiddleware(BaseHTTPMiddleware):
        """Middleware for automatic request tracing."""
        
        async def dispatch(self, request: Request, call_next) -> Response:
            span_name = f"{request.method} {request.url.path}"
            
            with tracer.start_as_current_span(
                span_name,
                kind=trace.SpanKind.SERVER
            ) as span:
                # Set HTTP attributes
                span.set_attribute("http.method", request.method)
                span.set_attribute("http.url", str(request.url))
                span.set_attribute("http.scheme", request.url.scheme)
                span.set_attribute("http.host", request.url.hostname)
                span.set_attribute("http.target", request.url.path)
                span.set_attribute("http.user_agent", request.headers.get("user-agent", ""))
                
                # Add trace ID to response headers
                trace_id = get_trace_id()
                
                try:
                    response = await call_next(request)
                    
                    # Set response attributes
                    span.set_attribute("http.status_code", response.status_code)
                    
                    if response.status_code >= 400:
                        span.set_status(Status(StatusCode.ERROR))
                    else:
                        span.set_status(Status(StatusCode.OK))
                    
                    # Add trace ID to response
                    if trace_id:
                        response.headers["X-Trace-ID"] = trace_id
                    
                    return response
                    
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(Status(StatusCode.ERROR, str(e)))
                    raise

except ImportError:
    pass  # FastAPI not installed
