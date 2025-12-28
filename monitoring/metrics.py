"""
S.S.I. SHADOW - Metrics Module
===============================
Prometheus metrics for Python services (API, Worker, ML)

Usage:
    from monitoring.metrics import metrics
    
    # Record event
    metrics.events_received.labels(event_name='PageView', platform='meta').inc()
    
    # Record latency
    with metrics.request_duration.labels(endpoint='/api/collect').time():
        process_request()
    
    # Update gauge
    metrics.queue_length.labels(queue='default').set(100)
"""

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    Summary,
    Info,
    CollectorRegistry,
    generate_latest,
    CONTENT_TYPE_LATEST,
    multiprocess,
    REGISTRY
)
from functools import wraps
import time
import os
from typing import Callable, Any
from contextlib import contextmanager


# =============================================================================
# REGISTRY SETUP
# =============================================================================

# Use multiprocess mode if running with gunicorn
if 'prometheus_multiproc_dir' in os.environ:
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
else:
    registry = REGISTRY


# =============================================================================
# CUSTOM BUCKETS
# =============================================================================

# For HTTP request latencies (in seconds)
HTTP_LATENCY_BUCKETS = (
    0.005, 0.01, 0.025, 0.05, 0.075, 0.1, 0.25, 0.5, 0.75, 1.0, 2.5, 5.0, 7.5, 10.0
)

# For event processing (in seconds)
EVENT_PROCESSING_BUCKETS = (
    0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0
)

# For platform API calls (in seconds)
PLATFORM_LATENCY_BUCKETS = (
    0.1, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0, 10.0
)

# For ML predictions (in seconds)
ML_LATENCY_BUCKETS = (
    0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 5.0
)

# For value/revenue (in dollars)
VALUE_BUCKETS = (
    1, 5, 10, 25, 50, 100, 250, 500, 1000, 5000, 10000
)


# =============================================================================
# METRICS CLASS
# =============================================================================

class SSIMetrics:
    """Central metrics registry for SSI Shadow."""
    
    def __init__(self):
        # =====================================================================
        # APPLICATION INFO
        # =====================================================================
        self.app_info = Info(
            'ssi_shadow',
            'SSI Shadow application information',
            registry=registry
        )
        
        # =====================================================================
        # HTTP REQUEST METRICS
        # =====================================================================
        self.http_requests_total = Counter(
            'http_requests_total',
            'Total HTTP requests',
            ['method', 'endpoint', 'status'],
            registry=registry
        )
        
        self.http_request_duration = Histogram(
            'http_request_duration_seconds',
            'HTTP request duration in seconds',
            ['method', 'endpoint'],
            buckets=HTTP_LATENCY_BUCKETS,
            registry=registry
        )
        
        self.http_request_size = Histogram(
            'http_request_size_bytes',
            'HTTP request size in bytes',
            ['method', 'endpoint'],
            buckets=(100, 500, 1000, 5000, 10000, 50000, 100000),
            registry=registry
        )
        
        self.http_response_size = Histogram(
            'http_response_size_bytes',
            'HTTP response size in bytes',
            ['method', 'endpoint'],
            buckets=(100, 500, 1000, 5000, 10000, 50000, 100000),
            registry=registry
        )
        
        # =====================================================================
        # EVENT METRICS
        # =====================================================================
        self.events_received = Counter(
            'ssi_events_received_total',
            'Total events received',
            ['event_name', 'platform', 'source'],
            registry=registry
        )
        
        self.events_processed = Counter(
            'ssi_events_processed_total',
            'Total events processed successfully',
            ['event_name', 'platform'],
            registry=registry
        )
        
        self.events_dropped = Counter(
            'ssi_events_dropped_total',
            'Total events dropped',
            ['event_name', 'reason'],
            registry=registry
        )
        
        self.events_blocked = Counter(
            'ssi_events_blocked_total',
            'Total events blocked by trust score',
            ['event_name', 'reason', 'action'],
            registry=registry
        )
        
        self.events_sent = Counter(
            'ssi_events_sent_total',
            'Total events sent to platforms',
            ['platform', 'event_name', 'status'],
            registry=registry
        )
        
        self.events_value = Counter(
            'ssi_events_value_total',
            'Total value of events (revenue)',
            ['event_name', 'currency'],
            registry=registry
        )
        
        self.event_processing_duration = Histogram(
            'ssi_event_processing_duration_seconds',
            'Event processing duration',
            ['event_name'],
            buckets=EVENT_PROCESSING_BUCKETS,
            registry=registry
        )
        
        self.events_queue_length = Gauge(
            'ssi_events_queue_length',
            'Current event queue length',
            ['queue'],
            registry=registry
        )
        
        # =====================================================================
        # TRUST SCORE METRICS
        # =====================================================================
        self.trust_score_distribution = Histogram(
            'ssi_trust_score_distribution',
            'Distribution of trust scores',
            ['action'],
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            registry=registry
        )
        
        self.trust_score_calculation_duration = Histogram(
            'ssi_trust_score_calculation_duration_seconds',
            'Trust score calculation duration',
            buckets=ML_LATENCY_BUCKETS,
            registry=registry
        )
        
        self.bot_detections = Counter(
            'ssi_bot_detections_total',
            'Total bot detections',
            ['detection_type', 'user_agent_category'],
            registry=registry
        )
        
        # =====================================================================
        # PLATFORM METRICS
        # =====================================================================
        self.platform_requests = Counter(
            'ssi_platform_requests_total',
            'Total requests to ad platforms',
            ['platform', 'endpoint', 'status'],
            registry=registry
        )
        
        self.platform_request_duration = Histogram(
            'ssi_platform_request_duration_seconds',
            'Platform API request duration',
            ['platform', 'endpoint'],
            buckets=PLATFORM_LATENCY_BUCKETS,
            registry=registry
        )
        
        self.platform_errors = Counter(
            'ssi_platform_errors_total',
            'Platform API errors',
            ['platform', 'error_type', 'error_code'],
            registry=registry
        )
        
        self.platform_rate_limits = Counter(
            'ssi_platform_rate_limits_total',
            'Platform rate limit hits',
            ['platform'],
            registry=registry
        )
        
        self.platform_cost = Counter(
            'ssi_platform_cost_total',
            'Total cost incurred on platforms',
            ['platform', 'cost_type'],
            registry=registry
        )
        
        # =====================================================================
        # BIGQUERY METRICS
        # =====================================================================
        self.bigquery_inserts = Counter(
            'ssi_bigquery_inserts_total',
            'Total BigQuery insert operations',
            ['table', 'status'],
            registry=registry
        )
        
        self.bigquery_rows_inserted = Counter(
            'ssi_bigquery_rows_inserted_total',
            'Total rows inserted into BigQuery',
            ['table'],
            registry=registry
        )
        
        self.bigquery_errors = Counter(
            'ssi_bigquery_errors_total',
            'BigQuery errors',
            ['table', 'error_type'],
            registry=registry
        )
        
        self.bigquery_latency = Histogram(
            'ssi_bigquery_latency_seconds',
            'BigQuery operation latency',
            ['operation', 'table'],
            buckets=PLATFORM_LATENCY_BUCKETS,
            registry=registry
        )
        
        # =====================================================================
        # PUB/SUB METRICS (Event Decoupling - C1)
        # =====================================================================
        self.pubsub_messages_published = Counter(
            'ssi_pubsub_messages_published_total',
            'Total messages published to Pub/Sub',
            ['topic', 'status'],
            registry=registry
        )
        
        self.pubsub_messages_consumed = Counter(
            'ssi_pubsub_messages_consumed_total',
            'Total messages consumed from Pub/Sub',
            ['subscription', 'status'],
            registry=registry
        )
        
        self.pubsub_publish_latency = Histogram(
            'ssi_pubsub_publish_latency_seconds',
            'Pub/Sub publish latency (Worker → Pub/Sub)',
            ['topic'],
            buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0),
            registry=registry
        )
        
        self.pubsub_lag_seconds = Histogram(
            'ssi_pubsub_lag_seconds',
            'End-to-end lag from Worker to BigQuery insert',
            ['topic'],
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0, 120.0),
            registry=registry
        )
        
        self.pubsub_batch_size = Histogram(
            'ssi_pubsub_batch_size',
            'Size of batches processed from Pub/Sub',
            ['subscription'],
            buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000),
            registry=registry
        )
        
        self.pubsub_consumer_lag = Gauge(
            'ssi_pubsub_consumer_lag_seconds',
            'Current consumer lag (oldest unacked message age)',
            ['subscription'],
            registry=registry
        )
        
        self.pubsub_fallback_to_bigquery = Counter(
            'ssi_pubsub_fallback_total',
            'Times Pub/Sub failed and fell back to direct BigQuery',
            ['reason'],
            registry=registry
        )
        
        self.pubsub_buffer_size = Gauge(
            'ssi_pubsub_buffer_size',
            'Current size of Pub/Sub consumer buffer',
            ['consumer_id'],
            registry=registry
        )
        
        # =====================================================================
        # ML METRICS
        # =====================================================================
        self.ml_predictions = Counter(
            'ssi_ml_predictions_total',
            'Total ML predictions made',
            ['model', 'prediction_type'],
            registry=registry
        )
        
        self.ml_prediction_duration = Histogram(
            'ssi_ml_prediction_duration_seconds',
            'ML prediction latency',
            ['model'],
            buckets=ML_LATENCY_BUCKETS,
            registry=registry
        )
        
        self.ml_prediction_errors = Counter(
            'ssi_ml_prediction_errors_total',
            'ML prediction errors',
            ['model', 'error_type'],
            registry=registry
        )
        
        self.ml_model_last_update = Gauge(
            'ssi_ml_model_last_update_timestamp',
            'Timestamp of last model update',
            ['model'],
            registry=registry
        )
        
        self.ml_ltv_predicted = Summary(
            'ssi_ml_ltv_predicted',
            'Predicted LTV values',
            ['tier'],
            registry=registry
        )
        
        self.ml_churn_probability = Histogram(
            'ssi_ml_churn_probability',
            'Churn probability distribution',
            ['risk_level'],
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            registry=registry
        )
        
        self.ml_propensity_score = Histogram(
            'ssi_ml_propensity_score',
            'Purchase propensity distribution',
            ['tier'],
            buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0),
            registry=registry
        )
        
        # =====================================================================
        # ANOMALY DETECTION METRICS (Prophet - C2)
        # =====================================================================
        self.anomaly_checks_total = Counter(
            'ssi_anomaly_checks_total',
            'Total anomaly detection checks performed',
            ['metric', 'result'],  # result: normal, spike, drop, drift
            registry=registry
        )
        
        self.anomaly_detected_total = Counter(
            'ssi_anomaly_detected_total',
            'Total anomalies detected',
            ['anomaly_type', 'severity'],  # anomaly_type: spike, drop, drift
            registry=registry
        )
        
        self.anomaly_zscore = Gauge(
            'ssi_anomaly_zscore',
            'Current Z-Score for monitored metrics',
            ['metric'],
            registry=registry
        )
        
        self.anomaly_actual_value = Gauge(
            'ssi_anomaly_actual_value',
            'Actual observed value for anomaly detection',
            ['metric'],
            registry=registry
        )
        
        self.anomaly_predicted_value = Gauge(
            'ssi_anomaly_predicted_value',
            'Prophet predicted value',
            ['metric'],
            registry=registry
        )
        
        self.anomaly_prediction_bounds = Gauge(
            'ssi_anomaly_prediction_bounds',
            'Prophet prediction confidence bounds',
            ['metric', 'bound'],  # bound: lower, upper
            registry=registry
        )
        
        self.anomaly_model_training_duration = Histogram(
            'ssi_anomaly_model_training_duration_seconds',
            'Duration of Prophet model training',
            buckets=(1.0, 5.0, 10.0, 30.0, 60.0, 120.0, 300.0),
            registry=registry
        )
        
        self.anomaly_check_duration = Histogram(
            'ssi_anomaly_check_duration_seconds',
            'Duration of anomaly check (including BQ query + prediction)',
            buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0),
            registry=registry
        )
        
        self.defense_mode_active = Gauge(
            'ssi_defense_mode_active',
            'Whether defense mode is currently active (1=active, 0=inactive)',
            registry=registry
        )
        
        self.defense_mode_activations_total = Counter(
            'ssi_defense_mode_activations_total',
            'Total times defense mode was activated',
            ['reason'],  # reason: spike, manual, api_error
            registry=registry
        )
        
        # =====================================================================
        # WORKER METRICS
        # =====================================================================
        self.worker_queue_length = Gauge(
            'ssi_worker_queue_length',
            'Worker queue length',
            ['queue'],
            registry=registry
        )
        
        self.worker_jobs_processed = Counter(
            'ssi_worker_jobs_processed_total',
            'Total jobs processed by workers',
            ['queue', 'job_type', 'status'],
            registry=registry
        )
        
        self.worker_job_duration = Histogram(
            'ssi_worker_job_duration_seconds',
            'Worker job duration',
            ['queue', 'job_type'],
            buckets=PLATFORM_LATENCY_BUCKETS,
            registry=registry
        )
        
        # =====================================================================
        # CRON JOB METRICS
        # =====================================================================
        self.cronjob_runs = Counter(
            'ssi_cronjob_runs_total',
            'Total cron job runs',
            ['job', 'status'],
            registry=registry
        )
        
        self.cronjob_duration = Histogram(
            'ssi_cronjob_duration_seconds',
            'Cron job duration',
            ['job'],
            buckets=(1, 5, 10, 30, 60, 120, 300, 600, 1800, 3600),
            registry=registry
        )
        
        self.cronjob_last_success = Gauge(
            'ssi_cronjob_last_success_timestamp',
            'Timestamp of last successful cron job',
            ['job'],
            registry=registry
        )
        
        self.cronjob_failures = Counter(
            'ssi_cronjob_failures_total',
            'Total cron job failures',
            ['job', 'error_type'],
            registry=registry
        )
        
        # =====================================================================
        # REDIS METRICS (Application-level)
        # =====================================================================
        self.redis_operations = Counter(
            'ssi_redis_operations_total',
            'Total Redis operations',
            ['operation', 'status'],
            registry=registry
        )
        
        self.redis_operation_duration = Histogram(
            'ssi_redis_operation_duration_seconds',
            'Redis operation duration',
            ['operation'],
            buckets=ML_LATENCY_BUCKETS,
            registry=registry
        )
        
        # =====================================================================
        # BUSINESS METRICS
        # =====================================================================
        self.revenue_total = Counter(
            'ssi_revenue_total',
            'Total revenue tracked',
            ['currency', 'source'],
            registry=registry
        )
        
        self.orders_total = Counter(
            'ssi_orders_total',
            'Total orders',
            ['status'],
            registry=registry
        )
        
        self.order_value = Histogram(
            'ssi_order_value',
            'Order value distribution',
            ['currency'],
            buckets=VALUE_BUCKETS,
            registry=registry
        )
        
        self.active_users = Gauge(
            'ssi_active_users',
            'Active users',
            ['period'],
            registry=registry
        )
        
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    def set_app_info(self, version: str, environment: str, git_commit: str = ""):
        """Set application info."""
        self.app_info.info({
            'version': version,
            'environment': environment,
            'git_commit': git_commit
        })
    
    @contextmanager
    def track_request(self, method: str, endpoint: str):
        """Context manager to track HTTP request metrics."""
        start_time = time.time()
        status = "500"
        try:
            yield
            status = "200"
        except Exception as e:
            status = "500"
            raise
        finally:
            duration = time.time() - start_time
            self.http_requests_total.labels(
                method=method, endpoint=endpoint, status=status
            ).inc()
            self.http_request_duration.labels(
                method=method, endpoint=endpoint
            ).observe(duration)
    
    @contextmanager
    def track_event_processing(self, event_name: str):
        """Context manager to track event processing."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.event_processing_duration.labels(
                event_name=event_name
            ).observe(duration)
    
    @contextmanager
    def track_platform_request(self, platform: str, endpoint: str):
        """Context manager to track platform API calls."""
        start_time = time.time()
        status = "error"
        try:
            yield
            status = "success"
        except Exception as e:
            status = "error"
            raise
        finally:
            duration = time.time() - start_time
            self.platform_requests.labels(
                platform=platform, endpoint=endpoint, status=status
            ).inc()
            self.platform_request_duration.labels(
                platform=platform, endpoint=endpoint
            ).observe(duration)
    
    @contextmanager
    def track_ml_prediction(self, model: str):
        """Context manager to track ML predictions."""
        start_time = time.time()
        try:
            yield
            self.ml_predictions.labels(model=model, prediction_type="success").inc()
        except Exception as e:
            self.ml_prediction_errors.labels(
                model=model, error_type=type(e).__name__
            ).inc()
            raise
        finally:
            duration = time.time() - start_time
            self.ml_prediction_duration.labels(model=model).observe(duration)
    
    def record_event(
        self,
        event_name: str,
        platform: str = "unknown",
        source: str = "unknown",
        value: float = 0,
        currency: str = "USD"
    ):
        """Record an incoming event."""
        self.events_received.labels(
            event_name=event_name,
            platform=platform,
            source=source
        ).inc()
        
        if value > 0:
            self.events_value.labels(
                event_name=event_name,
                currency=currency
            ).inc(value)
    
    def record_trust_score(self, score: float, action: str):
        """Record trust score result."""
        self.trust_score_distribution.labels(action=action).observe(score)
    
    def record_platform_event(
        self,
        platform: str,
        event_name: str,
        status: str = "success"
    ):
        """Record event sent to platform."""
        self.events_sent.labels(
            platform=platform,
            event_name=event_name,
            status=status
        ).inc()
    
    # =========================================================================
    # PUB/SUB METRICS HELPERS
    # =========================================================================
    
    def record_pubsub_publish(
        self,
        topic: str,
        success: bool,
        latency_seconds: float
    ):
        """Record Pub/Sub publish operation."""
        status = "success" if success else "failed"
        self.pubsub_messages_published.labels(
            topic=topic,
            status=status
        ).inc()
        
        if success:
            self.pubsub_publish_latency.labels(topic=topic).observe(latency_seconds)
    
    def record_pubsub_consume(
        self,
        subscription: str,
        batch_size: int,
        lag_seconds: float,
        success: bool = True
    ):
        """Record Pub/Sub consume operation with batch."""
        status = "success" if success else "failed"
        self.pubsub_messages_consumed.labels(
            subscription=subscription,
            status=status
        ).inc(batch_size)
        
        self.pubsub_batch_size.labels(subscription=subscription).observe(batch_size)
        self.pubsub_lag_seconds.labels(topic=subscription).observe(lag_seconds)
    
    def record_pubsub_fallback(self, reason: str):
        """Record fallback from Pub/Sub to direct BigQuery."""
        self.pubsub_fallback_to_bigquery.labels(reason=reason).inc()
    
    def set_pubsub_consumer_lag(self, subscription: str, lag_seconds: float):
        """Set current consumer lag gauge."""
        self.pubsub_consumer_lag.labels(subscription=subscription).set(lag_seconds)
    
    def set_pubsub_buffer_size(self, consumer_id: str, size: int):
        """Set current buffer size gauge."""
        self.pubsub_buffer_size.labels(consumer_id=consumer_id).set(size)
    
    @contextmanager
    def track_pubsub_publish(self, topic: str):
        """Context manager to track Pub/Sub publish."""
        start_time = time.time()
        success = False
        try:
            yield
            success = True
        except Exception:
            raise
        finally:
            duration = time.time() - start_time
            self.record_pubsub_publish(topic, success, duration)
    
    # =========================================================================
    # ANOMALY DETECTION METRICS HELPERS (C2)
    # =========================================================================
    
    def record_anomaly_check(
        self,
        metric: str,
        result: str,  # normal, spike, drop, drift
        actual: float,
        predicted: float,
        zscore: float,
        lower_bound: float,
        upper_bound: float,
        duration_seconds: float
    ):
        """Record an anomaly detection check."""
        # Increment check counter
        self.anomaly_checks_total.labels(metric=metric, result=result).inc()
        
        # Update gauges
        self.anomaly_zscore.labels(metric=metric).set(zscore)
        self.anomaly_actual_value.labels(metric=metric).set(actual)
        self.anomaly_predicted_value.labels(metric=metric).set(predicted)
        self.anomaly_prediction_bounds.labels(metric=metric, bound='lower').set(lower_bound)
        self.anomaly_prediction_bounds.labels(metric=metric, bound='upper').set(upper_bound)
        
        # Record check duration
        self.anomaly_check_duration.observe(duration_seconds)
    
    def record_anomaly_detected(
        self,
        anomaly_type: str,  # spike, drop, drift
        severity: str  # info, warning, critical
    ):
        """Record that an anomaly was detected."""
        self.anomaly_detected_total.labels(
            anomaly_type=anomaly_type,
            severity=severity
        ).inc()
    
    def record_model_training(self, duration_seconds: float):
        """Record Prophet model training duration."""
        self.anomaly_model_training_duration.observe(duration_seconds)
    
    def set_defense_mode(self, active: bool, reason: str = ""):
        """Update defense mode status."""
        self.defense_mode_active.set(1 if active else 0)
        if active and reason:
            self.defense_mode_activations_total.labels(reason=reason).inc()
    
    @contextmanager
    def track_anomaly_check(self, metric: str):
        """Context manager to track anomaly check duration."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.anomaly_check_duration.observe(duration)
    
    @contextmanager
    def track_model_training(self):
        """Context manager to track model training duration."""
        start_time = time.time()
        try:
            yield
        finally:
            duration = time.time() - start_time
            self.anomaly_model_training_duration.observe(duration)
    
    def get_metrics(self) -> bytes:
        """Generate latest metrics in Prometheus format."""
        return generate_latest(registry)
    
    def get_content_type(self) -> str:
        """Get content type for metrics endpoint."""
        return CONTENT_TYPE_LATEST


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

metrics = SSIMetrics()


# =============================================================================
# DECORATORS
# =============================================================================

def track_time(metric_name: str = "http_request_duration"):
    """Decorator to track function execution time."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = await func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                getattr(metrics, metric_name).observe(duration)
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                return result
            finally:
                duration = time.time() - start_time
                getattr(metrics, metric_name).observe(duration)
        
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    return decorator


def count_calls(counter_name: str, labels: dict = None):
    """Decorator to count function calls."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            counter = getattr(metrics, counter_name)
            if labels:
                counter.labels(**labels).inc()
            else:
                counter.inc()
            return func(*args, **kwargs)
        return wrapper
    return decorator


# =============================================================================
# FASTAPI MIDDLEWARE
# =============================================================================

try:
    from starlette.middleware.base import BaseHTTPMiddleware
    from starlette.requests import Request
    from starlette.responses import Response
    
    class PrometheusMiddleware(BaseHTTPMiddleware):
        """Middleware for automatic HTTP metrics collection."""
        
        async def dispatch(self, request: Request, call_next) -> Response:
            method = request.method
            path = request.url.path
            
            # Normalize path (remove IDs)
            normalized_path = self._normalize_path(path)
            
            start_time = time.time()
            
            try:
                response = await call_next(request)
                status = str(response.status_code)
            except Exception as e:
                status = "500"
                raise
            finally:
                duration = time.time() - start_time
                
                metrics.http_requests_total.labels(
                    method=method,
                    endpoint=normalized_path,
                    status=status
                ).inc()
                
                metrics.http_request_duration.labels(
                    method=method,
                    endpoint=normalized_path
                ).observe(duration)
            
            return response
        
        def _normalize_path(self, path: str) -> str:
            """Normalize path by replacing IDs with placeholders."""
            import re
            # Replace UUIDs
            path = re.sub(
                r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}',
                ':id',
                path
            )
            # Replace numeric IDs
            path = re.sub(r'/\d+', '/:id', path)
            return path

except ImportError:
    pass  # FastAPI not installed


import asyncio
