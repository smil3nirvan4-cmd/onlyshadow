"""
S.S.I. SHADOW - Dashboard Data Service v2
==========================================
Service for fetching dashboard data from BigQuery with caching.

FEATURES:
- Automatic fallback to MOCK mode when BigQuery is unavailable
- Graceful degradation without breaking the API
- Redis caching for performance
- Environment variable control: USE_MOCK_DATA=true

Author: SSI Shadow Team
Version: 2.0.0
"""

import os
import logging
import random
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from functools import lru_cache
import hashlib
import json

logger = logging.getLogger(__name__)

# Try to import BigQuery - fail gracefully
try:
    from google.cloud import bigquery
    from google.api_core.exceptions import GoogleAPIError
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False
    logger.warning("google-cloud-bigquery not installed. Using MOCK mode.")

# Try to import Redis - fail gracefully
REDIS_AVAILABLE = False
RedisType = Any  # Type alias for Redis client

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
    RedisType = aioredis.Redis
except ImportError:
    aioredis = None
    logger.warning("redis not installed. Caching disabled.")


class DashboardDataService:
    """
    Service for fetching dashboard metrics from BigQuery.
    Implements caching with Redis for performance.
    
    Automatically falls back to MOCK mode when:
    - USE_MOCK_DATA=true environment variable is set
    - BigQuery credentials are missing
    - BigQuery library is not installed
    - Any BigQuery query fails
    """
    
    def __init__(
        self,
        project_id: str = None,
        dataset_id: str = "ssi_shadow",
        redis_url: str = None
    ):
        self.project_id = project_id or os.getenv("GCP_PROJECT_ID")
        self.dataset_id = dataset_id
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        
        # Determine if we should use mock mode
        self.use_mock = self._should_use_mock()
        
        # Initialize BigQuery client (if not in mock mode)
        self.bq_client = None
        if not self.use_mock and BIGQUERY_AVAILABLE:
            try:
                self.bq_client = bigquery.Client(project=self.project_id)
                # Test connection with a simple query
                list(self.bq_client.query("SELECT 1").result())
                logger.info("✅ BigQuery Client initialized successfully.")
            except Exception as e:
                logger.warning(f"⚠️ Failed to init BigQuery: {e}. Falling back to MOCK mode.")
                self.use_mock = True
        
        # Redis client (initialized lazily)
        self._redis: Optional[Any] = None
        
        # Cache TTLs (in seconds)
        self.cache_ttls = {
            "overview": 30,
            "platforms": 10,
            "trust_score": 60,
            "ml_predictions": 300,
            "bid_metrics": 60,
            "funnel": 120,
            "events": 10,
        }
        
        # Log mode
        if self.use_mock:
            logger.info("🎭 Dashboard Service running in MOCK MODE")
        else:
            logger.info("🚀 Dashboard Service running in PRODUCTION MODE")
    
    def _should_use_mock(self) -> bool:
        """Determine if mock mode should be used."""
        # Explicit env var
        if os.getenv("USE_MOCK_DATA", "false").lower() == "true":
            return True
        
        # No BigQuery library
        if not BIGQUERY_AVAILABLE:
            return True
        
        # No project ID
        if not self.project_id:
            logger.warning("GCP_PROJECT_ID not set. Using MOCK mode.")
            return True
        
        # Check for credentials
        creds_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS")
        if not creds_path and not os.getenv("GOOGLE_CLOUD_PROJECT"):
            # Check if running in GCP (default credentials)
            try:
                from google.auth import default
                default()
            except Exception:
                logger.warning("No GCP credentials found. Using MOCK mode.")
                return True
        
        return False
    
    # =========================================================================
    # REDIS CACHE
    # =========================================================================
    
    async def _get_redis(self) -> Optional[Any]:
        """Get or create Redis connection."""
        if not self.redis_url or not REDIS_AVAILABLE:
            return None
        
        if self._redis is None:
            try:
                self._redis = aioredis.from_url(self.redis_url)
                # Test connection
                await self._redis.ping()
            except Exception as e:
                logger.warning(f"Redis connection failed: {e}")
                return None
        
        return self._redis
    
    async def _get_cached(self, key: str) -> Optional[Dict]:
        """Get cached value."""
        try:
            r = await self._get_redis()
            if r:
                data = await r.get(key)
                if data:
                    return json.loads(data)
        except Exception as e:
            logger.warning(f"Cache get failed: {e}")
        return None
    
    async def _set_cached(self, key: str, value: Dict, ttl: int):
        """Set cached value."""
        try:
            r = await self._get_redis()
            if r:
                await r.setex(key, ttl, json.dumps(value, default=str))
        except Exception as e:
            logger.warning(f"Cache set failed: {e}")
    
    def _cache_key(self, prefix: str, org_id: str, **kwargs) -> str:
        """Generate cache key."""
        params = json.dumps(kwargs, sort_keys=True, default=str)
        hash_str = hashlib.md5(params.encode()).hexdigest()[:8]
        return f"dashboard:{prefix}:{org_id}:{hash_str}"
    
    # =========================================================================
    # OVERVIEW
    # =========================================================================
    
    async def get_overview(
        self,
        organization_id: str,
        date: datetime = None
    ) -> Dict[str, Any]:
        """Get dashboard overview metrics."""
        if self.use_mock:
            return self._mock_overview()
        
        date = date or datetime.utcnow()
        today = date.date()
        yesterday = today - timedelta(days=1)
        
        cache_key = self._cache_key("overview", organization_id, date=str(today))
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        
        query = f"""
        WITH today_metrics AS (
            SELECT
                COUNT(*) as events,
                COUNT(DISTINCT ssi_id) as unique_users,
                SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) as revenue,
                SAFE_DIVIDE(
                    COUNTIF(event_name = 'Purchase'),
                    COUNTIF(event_name = 'PageView')
                ) as conversion_rate,
                AVG(CASE WHEN event_name = 'Purchase' THEN value END) as avg_order_value,
                AVG(trust_score) as avg_trust_score,
                SAFE_DIVIDE(
                    COUNTIF(trust_action = 'block'),
                    COUNT(*)
                ) as blocked_rate
            FROM `{self.project_id}.{self.dataset_id}.events`
            WHERE DATE(timestamp) = '{today}'
            AND organization_id = '{organization_id}'
        ),
        yesterday_metrics AS (
            SELECT
                COUNT(*) as events,
                COUNT(DISTINCT ssi_id) as unique_users,
                SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) as revenue,
                SAFE_DIVIDE(
                    COUNTIF(event_name = 'Purchase'),
                    COUNTIF(event_name = 'PageView')
                ) as conversion_rate,
                AVG(CASE WHEN event_name = 'Purchase' THEN value END) as avg_order_value,
                AVG(trust_score) as avg_trust_score,
                SAFE_DIVIDE(
                    COUNTIF(trust_action = 'block'),
                    COUNT(*)
                ) as blocked_rate
            FROM `{self.project_id}.{self.dataset_id}.events`
            WHERE DATE(timestamp) = '{yesterday}'
            AND organization_id = '{organization_id}'
        )
        SELECT
            t.events as events_today,
            y.events as events_yesterday,
            t.unique_users as unique_users_today,
            y.unique_users as unique_users_yesterday,
            t.revenue as revenue_today,
            y.revenue as revenue_yesterday,
            t.conversion_rate as conversion_rate_today,
            y.conversion_rate as conversion_rate_yesterday,
            t.avg_order_value as aov_today,
            y.avg_order_value as aov_yesterday,
            t.avg_trust_score as avg_trust_score,
            t.blocked_rate as blocked_rate_today,
            y.blocked_rate as blocked_rate_yesterday
        FROM today_metrics t, yesterday_metrics y
        """
        
        try:
            result = list(self.bq_client.query(query).result())
            row = result[0] if result else None
            
            if not row:
                return self._empty_overview()
            
            def make_metric(current, previous):
                current = current or 0
                previous = previous or 0
                change = ((current - previous) / previous * 100) if previous else 0
                trend = "up" if change > 1 else ("down" if change < -1 else "stable")
                return {
                    "current": round(current, 2) if isinstance(current, float) else current,
                    "previous": round(previous, 2) if isinstance(previous, float) else previous,
                    "change_percent": round(change, 2),
                    "trend": trend
                }
            
            data = {
                "events_today": make_metric(row.events_today, row.events_yesterday),
                "unique_users": make_metric(row.unique_users_today, row.unique_users_yesterday),
                "revenue": make_metric(row.revenue_today, row.revenue_yesterday),
                "conversion_rate": make_metric(row.conversion_rate_today, row.conversion_rate_yesterday),
                "avg_order_value": make_metric(row.aov_today, row.aov_yesterday),
                "blocked_rate": make_metric(row.blocked_rate_today, row.blocked_rate_yesterday),
                "avg_trust_score": round(row.avg_trust_score or 0, 4),
                "last_updated": datetime.utcnow().isoformat(),
                "period": "today",
                "data_source": "bigquery"
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["overview"])
            return data
            
        except Exception as e:
            logger.error(f"BigQuery Error in get_overview: {e}")
            # Fall back to mock on error
            return self._mock_overview()
    
    def _empty_overview(self) -> Dict:
        """Return empty overview metrics."""
        empty_metric = {"current": 0, "previous": 0, "change_percent": 0, "trend": "stable"}
        return {
            "events_today": empty_metric,
            "unique_users": empty_metric,
            "revenue": empty_metric,
            "conversion_rate": empty_metric,
            "avg_order_value": empty_metric,
            "blocked_rate": empty_metric,
            "avg_trust_score": 0,
            "last_updated": datetime.utcnow().isoformat(),
            "period": "today",
            "data_source": "empty"
        }
    
    def _mock_overview(self) -> Dict:
        """Return mock overview data for development."""
        base_events = 45000 + random.randint(-5000, 5000)
        base_users = 12000 + random.randint(-1000, 1000)
        base_revenue = 28000 + random.randint(-3000, 3000)
        
        def make_mock_metric(base_current, variance_pct=15):
            variance = base_current * (variance_pct / 100)
            current = base_current + random.uniform(-variance/2, variance/2)
            previous = base_current + random.uniform(-variance, variance)
            change = ((current - previous) / previous * 100) if previous else 0
            trend = "up" if change > 1 else ("down" if change < -1 else "stable")
            return {
                "current": round(current, 2) if isinstance(current, float) else int(current),
                "previous": round(previous, 2) if isinstance(previous, float) else int(previous),
                "change_percent": round(change, 2),
                "trend": trend
            }
        
        return {
            "events_today": make_mock_metric(base_events),
            "unique_users": make_mock_metric(base_users),
            "revenue": make_mock_metric(base_revenue),
            "conversion_rate": make_mock_metric(0.034, 20),
            "avg_order_value": make_mock_metric(89.50, 10),
            "blocked_rate": make_mock_metric(0.062, 25),
            "avg_trust_score": round(0.75 + random.uniform(-0.05, 0.05), 4),
            "last_updated": datetime.utcnow().isoformat(),
            "period": "today",
            "data_source": "mock"
        }
    
    # =========================================================================
    # PLATFORMS
    # =========================================================================
    
    async def get_platforms(self, organization_id: str) -> Dict[str, Any]:
        """Get platform status and metrics."""
        if self.use_mock:
            return self._mock_platforms()
        
        cache_key = self._cache_key("platforms", organization_id)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        
        query = f"""
        SELECT
            platform,
            COUNT(*) as events_sent,
            COUNTIF(status = 'error') as events_failed,
            SAFE_DIVIDE(COUNTIF(status = 'success'), COUNT(*)) as success_rate,
            AVG(latency_ms) as avg_latency_ms,
            APPROX_QUANTILES(latency_ms, 100)[OFFSET(99)] as p99_latency_ms,
            COUNTIF(status = 'error' AND timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)) as errors_last_hour,
            MAX(CASE WHEN status = 'error' THEN error_message END) as last_error,
            MAX(CASE WHEN status = 'success' THEN timestamp END) as last_success
        FROM `{self.project_id}.{self.dataset_id}.platform_requests`
        WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        AND organization_id = '{organization_id}'
        GROUP BY platform
        """
        
        try:
            result = list(self.bq_client.query(query).result())
            
            platforms = []
            total_sent = 0
            total_success = 0
            
            for row in result:
                success_rate = row.success_rate or 0
                status = "healthy" if success_rate >= 0.99 else ("degraded" if success_rate >= 0.95 else "down")
                
                platforms.append({
                    "platform": row.platform,
                    "status": status,
                    "events_sent": row.events_sent,
                    "events_failed": row.events_failed,
                    "success_rate": round(success_rate, 4),
                    "avg_latency_ms": round(row.avg_latency_ms or 0, 2),
                    "p99_latency_ms": round(row.p99_latency_ms or 0, 2),
                    "errors_last_hour": row.errors_last_hour,
                    "last_error": row.last_error,
                    "last_success": row.last_success.isoformat() if row.last_success else None
                })
                
                total_sent += row.events_sent
                total_success += row.events_sent - row.events_failed
            
            # Add missing platforms
            existing = {p["platform"] for p in platforms}
            for p in ["meta", "tiktok", "google", "microsoft", "snapchat", "pinterest", "linkedin", "twitter", "bigquery"]:
                if p not in existing:
                    platforms.append({
                        "platform": p,
                        "status": "disabled",
                        "events_sent": 0,
                        "events_failed": 0,
                        "success_rate": 0,
                        "avg_latency_ms": 0,
                        "p99_latency_ms": 0,
                        "errors_last_hour": 0,
                        "last_error": None,
                        "last_success": None
                    })
            
            overall_rate = total_success / total_sent if total_sent > 0 else 0
            overall_status = "healthy" if overall_rate >= 0.99 else ("degraded" if overall_rate >= 0.95 else "down")
            
            data = {
                "platforms": platforms,
                "overall_status": overall_status,
                "total_events_sent": total_sent,
                "overall_success_rate": round(overall_rate, 4),
                "last_updated": datetime.utcnow().isoformat(),
                "data_source": "bigquery"
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["platforms"])
            return data
            
        except Exception as e:
            logger.error(f"BigQuery Error in get_platforms: {e}")
            return self._mock_platforms()
    
    def _mock_platforms(self) -> Dict:
        """Return mock platform data."""
        now = datetime.utcnow()
        
        platforms = [
            {
                "platform": "meta",
                "status": "healthy",
                "events_sent": 42000 + random.randint(-2000, 2000),
                "events_failed": random.randint(10, 50),
                "success_rate": 0.998 + random.uniform(-0.002, 0.001),
                "avg_latency_ms": 120 + random.randint(-20, 30),
                "p99_latency_ms": 280 + random.randint(-30, 50),
                "errors_last_hour": random.randint(0, 5),
                "last_error": None,
                "last_success": (now - timedelta(seconds=random.randint(1, 60))).isoformat()
            },
            {
                "platform": "google",
                "status": "healthy",
                "events_sent": 41000 + random.randint(-2000, 2000),
                "events_failed": random.randint(5, 30),
                "success_rate": 0.999 + random.uniform(-0.001, 0.0005),
                "avg_latency_ms": 95 + random.randint(-15, 20),
                "p99_latency_ms": 220 + random.randint(-20, 40),
                "errors_last_hour": random.randint(0, 3),
                "last_error": None,
                "last_success": (now - timedelta(seconds=random.randint(1, 60))).isoformat()
            },
            {
                "platform": "tiktok",
                "status": "healthy",
                "events_sent": 38000 + random.randint(-2000, 2000),
                "events_failed": random.randint(15, 60),
                "success_rate": 0.995 + random.uniform(-0.003, 0.003),
                "avg_latency_ms": 150 + random.randint(-25, 35),
                "p99_latency_ms": 350 + random.randint(-40, 60),
                "errors_last_hour": random.randint(0, 8),
                "last_error": None,
                "last_success": (now - timedelta(seconds=random.randint(1, 60))).isoformat()
            },
            {
                "platform": "microsoft",
                "status": "healthy",
                "events_sent": 15000 + random.randint(-1000, 1000),
                "events_failed": random.randint(5, 20),
                "success_rate": 0.997 + random.uniform(-0.002, 0.002),
                "avg_latency_ms": 110 + random.randint(-15, 25),
                "p99_latency_ms": 250 + random.randint(-25, 45),
                "errors_last_hour": random.randint(0, 3),
                "last_error": None,
                "last_success": (now - timedelta(seconds=random.randint(1, 120))).isoformat()
            },
            {
                "platform": "bigquery",
                "status": "healthy",
                "events_sent": 45000 + random.randint(-2000, 2000),
                "events_failed": random.randint(0, 10),
                "success_rate": 0.9999,
                "avg_latency_ms": 45 + random.randint(-10, 15),
                "p99_latency_ms": 120 + random.randint(-15, 25),
                "errors_last_hour": random.randint(0, 1),
                "last_error": None,
                "last_success": (now - timedelta(seconds=random.randint(1, 30))).isoformat()
            }
        ]
        
        # Add disabled platforms
        for p in ["snapchat", "pinterest", "linkedin", "twitter"]:
            platforms.append({
                "platform": p,
                "status": "disabled",
                "events_sent": 0,
                "events_failed": 0,
                "success_rate": 0,
                "avg_latency_ms": 0,
                "p99_latency_ms": 0,
                "errors_last_hour": 0,
                "last_error": None,
                "last_success": None
            })
        
        total_sent = sum(p["events_sent"] for p in platforms)
        total_success = sum(p["events_sent"] - p["events_failed"] for p in platforms)
        
        return {
            "platforms": platforms,
            "overall_status": "healthy",
            "total_events_sent": total_sent,
            "overall_success_rate": round(total_success / total_sent if total_sent > 0 else 0, 4),
            "last_updated": datetime.utcnow().isoformat(),
            "data_source": "mock"
        }
    
    # =========================================================================
    # TRUST SCORE
    # =========================================================================
    
    async def get_trust_score(self, organization_id: str) -> Dict[str, Any]:
        """Get trust score analytics."""
        if self.use_mock:
            return self._mock_trust_score()
        
        cache_key = self._cache_key("trust_score", organization_id)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        
        query = f"""
        WITH events AS (
            SELECT
                trust_score,
                trust_action,
                block_reasons
            FROM `{self.project_id}.{self.dataset_id}.events`
            WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            AND organization_id = '{organization_id}'
        )
        SELECT
            COUNT(*) as total_events,
            COUNTIF(trust_action = 'allow') as allowed,
            COUNTIF(trust_action = 'challenge') as challenged,
            COUNTIF(trust_action = 'block') as blocked,
            AVG(trust_score) as avg_score,
            APPROX_QUANTILES(trust_score, 2)[OFFSET(1)] as median_score
        FROM events
        """
        
        try:
            result = list(self.bq_client.query(query).result())
            row = result[0] if result else None
            
            if not row or row.total_events == 0:
                return self._empty_trust_score()
            
            total = row.total_events
            blocked = row.blocked or 0
            
            # Get distribution
            dist_query = f"""
            SELECT
                FLOOR(trust_score * 10) / 10 as bucket,
                COUNT(*) as count
            FROM `{self.project_id}.{self.dataset_id}.events`
            WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            AND organization_id = '{organization_id}'
            GROUP BY bucket
            ORDER BY bucket
            """
            dist_result = list(self.bq_client.query(dist_query).result())
            
            distribution = []
            for i in range(10):
                bucket_min = i / 10
                bucket_count = next(
                    (r.count for r in dist_result if r.bucket == bucket_min),
                    0
                )
                distribution.append({
                    "range_min": bucket_min,
                    "range_max": (i + 1) / 10,
                    "count": bucket_count,
                    "percentage": round(bucket_count / total * 100, 2) if total > 0 else 0
                })
            
            # Get block reasons
            reasons_query = f"""
            SELECT
                reason,
                COUNT(*) as count
            FROM `{self.project_id}.{self.dataset_id}.events`,
            UNNEST(block_reasons) as reason
            WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            AND organization_id = '{organization_id}'
            AND trust_action = 'block'
            GROUP BY reason
            ORDER BY count DESC
            LIMIT 10
            """
            reasons_result = list(self.bq_client.query(reasons_query).result())
            
            top_reasons = [
                {
                    "reason": r.reason,
                    "count": r.count,
                    "percentage": round(r.count / blocked * 100, 2) if blocked > 0 else 0
                }
                for r in reasons_result
            ]
            
            data = {
                "distribution": distribution,
                "total_events": total,
                "allowed_events": row.allowed or 0,
                "challenged_events": row.challenged or 0,
                "blocked_events": blocked,
                "allow_rate": round((row.allowed or 0) / total, 4),
                "challenge_rate": round((row.challenged or 0) / total, 4),
                "block_rate": round(blocked / total, 4),
                "avg_trust_score": round(row.avg_score or 0, 4),
                "median_trust_score": round(row.median_score or 0, 4),
                "top_block_reasons": top_reasons,
                "last_updated": datetime.utcnow().isoformat(),
                "data_source": "bigquery"
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["trust_score"])
            return data
            
        except Exception as e:
            logger.error(f"BigQuery Error in get_trust_score: {e}")
            return self._mock_trust_score()
    
    def _empty_trust_score(self) -> Dict:
        """Return empty trust score data."""
        return {
            "distribution": [
                {"range_min": i/10, "range_max": (i+1)/10, "count": 0, "percentage": 0}
                for i in range(10)
            ],
            "total_events": 0,
            "allowed_events": 0,
            "challenged_events": 0,
            "blocked_events": 0,
            "allow_rate": 0,
            "challenge_rate": 0,
            "block_rate": 0,
            "avg_trust_score": 0,
            "median_trust_score": 0,
            "top_block_reasons": [],
            "last_updated": datetime.utcnow().isoformat(),
            "data_source": "empty"
        }
    
    def _mock_trust_score(self) -> Dict:
        """Return mock trust score data."""
        total = 45000 + random.randint(-5000, 5000)
        
        # Generate realistic distribution (skewed towards high scores)
        distribution = []
        dist_weights = [0.02, 0.03, 0.05, 0.08, 0.12, 0.15, 0.18, 0.17, 0.12, 0.08]
        
        for i in range(10):
            count = int(total * dist_weights[i] * (1 + random.uniform(-0.1, 0.1)))
            distribution.append({
                "range_min": i / 10,
                "range_max": (i + 1) / 10,
                "count": count,
                "percentage": round(count / total * 100, 2)
            })
        
        blocked = int(total * 0.062)
        challenged = int(total * 0.038)
        allowed = total - blocked - challenged
        
        top_reasons = [
            {"reason": "Bot User-Agent", "count": int(blocked * 0.35), "percentage": 35.0},
            {"reason": "Datacenter IP", "count": int(blocked * 0.25), "percentage": 25.0},
            {"reason": "Rate Limit Exceeded", "count": int(blocked * 0.15), "percentage": 15.0},
            {"reason": "Headless Browser", "count": int(blocked * 0.10), "percentage": 10.0},
            {"reason": "Suspicious Behavior", "count": int(blocked * 0.08), "percentage": 8.0},
            {"reason": "Known Proxy", "count": int(blocked * 0.07), "percentage": 7.0},
        ]
        
        return {
            "distribution": distribution,
            "total_events": total,
            "allowed_events": allowed,
            "challenged_events": challenged,
            "blocked_events": blocked,
            "allow_rate": round(allowed / total, 4),
            "challenge_rate": round(challenged / total, 4),
            "block_rate": round(blocked / total, 4),
            "avg_trust_score": round(0.72 + random.uniform(-0.05, 0.05), 4),
            "median_trust_score": round(0.78 + random.uniform(-0.03, 0.03), 4),
            "top_block_reasons": top_reasons,
            "last_updated": datetime.utcnow().isoformat(),
            "data_source": "mock"
        }
    
    # =========================================================================
    # ML PREDICTIONS
    # =========================================================================
    
    async def get_ml_predictions(self, organization_id: str) -> Dict[str, Any]:
        """Get ML predictions overview."""
        if self.use_mock:
            return self._mock_ml_predictions()
        
        cache_key = self._cache_key("ml_predictions", organization_id)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        
        query = f"""
        SELECT
            ltv_tier,
            churn_risk,
            propensity_tier,
            COUNT(*) as count,
            AVG(ltv_90d) as avg_ltv,
            SUM(ltv_90d) as total_ltv,
            AVG(churn_probability) as avg_churn_prob,
            AVG(propensity_score) as avg_propensity
        FROM `{self.project_id}.{self.dataset_id}.ml_predictions`
        WHERE organization_id = '{organization_id}'
        AND updated_at > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
        GROUP BY ltv_tier, churn_risk, propensity_tier
        """
        
        try:
            result = list(self.bq_client.query(query).result())
            
            # Aggregate by tier
            ltv_segments = {}
            churn_segments = {}
            propensity_segments = {}
            total_users = 0
            
            for row in result:
                count = row.count
                total_users += count
                
                # LTV
                tier = row.ltv_tier or "Unknown"
                if tier not in ltv_segments:
                    ltv_segments[tier] = {"count": 0, "total_ltv": 0}
                ltv_segments[tier]["count"] += count
                ltv_segments[tier]["total_ltv"] += row.total_ltv or 0
                
                # Churn
                risk = row.churn_risk or "Unknown"
                if risk not in churn_segments:
                    churn_segments[risk] = {"count": 0, "total_prob": 0}
                churn_segments[risk]["count"] += count
                churn_segments[risk]["total_prob"] += (row.avg_churn_prob or 0) * count
                
                # Propensity
                prop_tier = row.propensity_tier or "Unknown"
                if prop_tier not in propensity_segments:
                    propensity_segments[prop_tier] = {"count": 0, "total_score": 0}
                propensity_segments[prop_tier]["count"] += count
                propensity_segments[prop_tier]["total_score"] += (row.avg_propensity or 0) * count
            
            # Format results
            ltv_list = [
                {
                    "tier": tier,
                    "count": data["count"],
                    "percentage": round(data["count"] / total_users * 100, 2) if total_users > 0 else 0,
                    "avg_ltv": round(data["total_ltv"] / data["count"], 2) if data["count"] > 0 else 0,
                    "total_ltv": round(data["total_ltv"], 2)
                }
                for tier, data in ltv_segments.items()
            ]
            
            churn_list = [
                {
                    "risk": risk,
                    "count": data["count"],
                    "percentage": round(data["count"] / total_users * 100, 2) if total_users > 0 else 0,
                    "avg_probability": round(data["total_prob"] / data["count"], 4) if data["count"] > 0 else 0
                }
                for risk, data in churn_segments.items()
            ]
            
            prop_list = [
                {
                    "tier": tier,
                    "count": data["count"],
                    "percentage": round(data["count"] / total_users * 100, 2) if total_users > 0 else 0,
                    "avg_score": round(data["total_score"] / data["count"], 4) if data["count"] > 0 else 0
                }
                for tier, data in propensity_segments.items()
            ]
            
            # Count special segments
            high_value = sum(d["count"] for d in ltv_list if d["tier"] in ["VIP", "High"])
            at_risk = sum(d["count"] for d in churn_list if d["risk"] in ["Critical", "High"])
            ready_to_buy = sum(d["count"] for d in prop_list if d["tier"] in ["Very High", "High"])
            
            data = {
                "ltv_segments": ltv_list,
                "churn_segments": churn_list,
                "propensity_segments": prop_list,
                "total_users_predicted": total_users,
                "high_value_users": high_value,
                "at_risk_users": at_risk,
                "ready_to_buy_users": ready_to_buy,
                "last_updated": datetime.utcnow().isoformat(),
                "data_source": "bigquery"
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["ml_predictions"])
            return data
            
        except Exception as e:
            logger.error(f"BigQuery Error in get_ml_predictions: {e}")
            return self._mock_ml_predictions()
    
    def _mock_ml_predictions(self) -> Dict:
        """Return mock ML predictions data."""
        total_users = 12000 + random.randint(-1000, 1000)
        
        ltv_segments = [
            {"tier": "VIP", "count": int(total_users * 0.02), "percentage": 2.0, "avg_ltv": 1200.00, "total_ltv": int(total_users * 0.02 * 1200)},
            {"tier": "High", "count": int(total_users * 0.15), "percentage": 15.0, "avg_ltv": 350.00, "total_ltv": int(total_users * 0.15 * 350)},
            {"tier": "Medium", "count": int(total_users * 0.38), "percentage": 38.0, "avg_ltv": 120.00, "total_ltv": int(total_users * 0.38 * 120)},
            {"tier": "Low", "count": int(total_users * 0.45), "percentage": 45.0, "avg_ltv": 25.00, "total_ltv": int(total_users * 0.45 * 25)},
        ]
        
        churn_segments = [
            {"risk": "Critical", "count": int(total_users * 0.05), "percentage": 5.0, "avg_probability": 0.85},
            {"risk": "High", "count": int(total_users * 0.12), "percentage": 12.0, "avg_probability": 0.65},
            {"risk": "Medium", "count": int(total_users * 0.25), "percentage": 25.0, "avg_probability": 0.35},
            {"risk": "Low", "count": int(total_users * 0.58), "percentage": 58.0, "avg_probability": 0.10},
        ]
        
        propensity_segments = [
            {"tier": "Very High", "count": int(total_users * 0.08), "percentage": 8.0, "avg_score": 0.88},
            {"tier": "High", "count": int(total_users * 0.18), "percentage": 18.0, "avg_score": 0.68},
            {"tier": "Medium", "count": int(total_users * 0.35), "percentage": 35.0, "avg_score": 0.42},
            {"tier": "Low", "count": int(total_users * 0.25), "percentage": 25.0, "avg_score": 0.22},
            {"tier": "Very Low", "count": int(total_users * 0.14), "percentage": 14.0, "avg_score": 0.08},
        ]
        
        return {
            "ltv_segments": ltv_segments,
            "churn_segments": churn_segments,
            "propensity_segments": propensity_segments,
            "total_users_predicted": total_users,
            "high_value_users": int(total_users * 0.17),
            "at_risk_users": int(total_users * 0.17),
            "ready_to_buy_users": int(total_users * 0.26),
            "last_updated": datetime.utcnow().isoformat(),
            "data_source": "mock"
        }
    
    # =========================================================================
    # FUNNEL
    # =========================================================================
    
    async def get_funnel(self, organization_id: str) -> Dict[str, Any]:
        """Get conversion funnel."""
        if self.use_mock:
            return self._mock_funnel()
        
        cache_key = self._cache_key("funnel", organization_id)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        
        query = f"""
        SELECT
            event_name,
            COUNT(*) as count,
            COUNT(DISTINCT ssi_id) as unique_users
        FROM `{self.project_id}.{self.dataset_id}.events`
        WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        AND organization_id = '{organization_id}'
        AND event_name IN ('PageView', 'ViewContent', 'AddToCart', 'InitiateCheckout', 'Purchase')
        GROUP BY event_name
        """
        
        try:
            result = list(self.bq_client.query(query).result())
            
            stage_order = ['PageView', 'ViewContent', 'AddToCart', 'InitiateCheckout', 'Purchase']
            stage_names = {
                'PageView': 'Page Views',
                'ViewContent': 'Product Views',
                'AddToCart': 'Add to Cart',
                'InitiateCheckout': 'Checkout',
                'Purchase': 'Purchase'
            }
            
            stage_map = {r.event_name: r for r in result}
            
            stages = []
            prev_count = None
            
            for event_name in stage_order:
                row = stage_map.get(event_name)
                count = row.count if row else 0
                unique = row.unique_users if row else 0
                
                if prev_count is None:
                    conversion_rate = 1.0
                    drop_off = 0.0
                else:
                    conversion_rate = count / prev_count if prev_count > 0 else 0
                    drop_off = 1 - conversion_rate
                
                stages.append({
                    "stage": stage_names.get(event_name, event_name),
                    "event_name": event_name,
                    "count": count,
                    "unique_users": unique,
                    "conversion_rate": round(conversion_rate, 4),
                    "drop_off_rate": round(drop_off, 4)
                })
                
                prev_count = count
            
            page_views = stage_map.get('PageView')
            purchases = stage_map.get('Purchase')
            
            total_sessions = page_views.unique_users if page_views else 0
            completed = purchases.count if purchases else 0
            overall_rate = completed / (page_views.count if page_views else 1)
            
            data = {
                "stages": stages,
                "total_sessions": total_sessions,
                "completed_purchases": completed,
                "overall_conversion_rate": round(overall_rate, 4),
                "last_updated": datetime.utcnow().isoformat(),
                "data_source": "bigquery"
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["funnel"])
            return data
            
        except Exception as e:
            logger.error(f"BigQuery Error in get_funnel: {e}")
            return self._mock_funnel()
    
    def _mock_funnel(self) -> Dict:
        """Return mock funnel data."""
        base_pageviews = 45000 + random.randint(-5000, 5000)
        
        # Realistic conversion rates
        stages = [
            {"stage": "Page Views", "event_name": "PageView", "count": base_pageviews, "unique_users": int(base_pageviews * 0.75)},
            {"stage": "Product Views", "event_name": "ViewContent", "count": int(base_pageviews * 0.62), "unique_users": int(base_pageviews * 0.50)},
            {"stage": "Add to Cart", "event_name": "AddToCart", "count": int(base_pageviews * 0.19), "unique_users": int(base_pageviews * 0.16)},
            {"stage": "Checkout", "event_name": "InitiateCheckout", "count": int(base_pageviews * 0.10), "unique_users": int(base_pageviews * 0.085)},
            {"stage": "Purchase", "event_name": "Purchase", "count": int(base_pageviews * 0.034), "unique_users": int(base_pageviews * 0.030)},
        ]
        
        prev_count = None
        for stage in stages:
            if prev_count is None:
                stage["conversion_rate"] = 1.0
                stage["drop_off_rate"] = 0.0
            else:
                stage["conversion_rate"] = round(stage["count"] / prev_count, 4)
                stage["drop_off_rate"] = round(1 - stage["conversion_rate"], 4)
            prev_count = stage["count"]
        
        return {
            "stages": stages,
            "total_sessions": stages[0]["unique_users"],
            "completed_purchases": stages[-1]["count"],
            "overall_conversion_rate": round(stages[-1]["count"] / stages[0]["count"], 4),
            "last_updated": datetime.utcnow().isoformat(),
            "data_source": "mock"
        }
    
    # =========================================================================
    # EVENTS
    # =========================================================================
    
    async def get_events(
        self,
        organization_id: str,
        limit: int = 100,
        offset: int = 0,
        filters: Dict = None
    ) -> Dict[str, Any]:
        """Get paginated list of events."""
        if self.use_mock:
            return self._mock_events(limit, offset)
        
        filters = filters or {}
        
        where_clauses = [
            f"organization_id = '{organization_id}'",
            "timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)"
        ]
        
        if filters.get("event_types"):
            types = ",".join(f"'{t}'" for t in filters["event_types"])
            where_clauses.append(f"event_name IN ({types})")
        
        if filters.get("trust_actions"):
            actions = ",".join(f"'{a}'" for a in filters["trust_actions"])
            where_clauses.append(f"trust_action IN ({actions})")
        
        if filters.get("min_trust_score") is not None:
            where_clauses.append(f"trust_score >= {filters['min_trust_score']}")
        
        if filters.get("max_trust_score") is not None:
            where_clauses.append(f"trust_score <= {filters['max_trust_score']}")
        
        if filters.get("min_value") is not None:
            where_clauses.append(f"value >= {filters['min_value']}")
        
        where_str = " AND ".join(where_clauses)
        
        count_query = f"""
        SELECT COUNT(*) as total
        FROM `{self.project_id}.{self.dataset_id}.events`
        WHERE {where_str}
        """
        
        data_query = f"""
        SELECT
            event_id,
            ssi_id,
            event_name,
            timestamp,
            url,
            value,
            currency,
            trust_score,
            trust_action,
            platforms_sent,
            platform_success,
            user_agent,
            ip_country
        FROM `{self.project_id}.{self.dataset_id}.events`
        WHERE {where_str}
        ORDER BY timestamp DESC
        LIMIT {limit}
        OFFSET {offset}
        """
        
        try:
            count_result = list(self.bq_client.query(count_query).result())
            total = count_result[0].total if count_result else 0
            
            result = list(self.bq_client.query(data_query).result())
            
            events = []
            for row in result:
                events.append({
                    "event_id": row.event_id,
                    "ssi_id": row.ssi_id,
                    "event_name": row.event_name,
                    "timestamp": row.timestamp.isoformat(),
                    "url": row.url,
                    "value": row.value,
                    "currency": row.currency,
                    "trust_score": row.trust_score,
                    "trust_action": row.trust_action,
                    "platforms_sent": row.platforms_sent or [],
                    "platform_success": row.platform_success,
                    "user_agent": row.user_agent,
                    "ip_country": row.ip_country
                })
            
            return {
                "events": events,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": (offset + limit) < total,
                "data_source": "bigquery"
            }
            
        except Exception as e:
            logger.error(f"BigQuery Error in get_events: {e}")
            return self._mock_events(limit, offset)
    
    def _mock_events(self, limit: int = 100, offset: int = 0) -> Dict:
        """Return mock events data."""
        total = 45000
        event_types = ['PageView', 'ViewContent', 'AddToCart', 'InitiateCheckout', 'Purchase']
        trust_actions = ['allow', 'allow', 'allow', 'allow', 'allow', 'allow', 'allow', 'challenge', 'block']
        countries = ['BR', 'BR', 'BR', 'US', 'PT', 'AR', 'MX']
        currencies = ['BRL', 'BRL', 'BRL', 'USD']
        
        events = []
        now = datetime.utcnow()
        
        for i in range(min(limit, total - offset)):
            event_name = random.choice(event_types)
            is_purchase = event_name == 'Purchase'
            
            events.append({
                "event_id": f"evt_{now.timestamp()}_{offset + i}_{random.randint(1000, 9999)}",
                "ssi_id": f"ssi_{hashlib.md5(str(random.random()).encode()).hexdigest()[:16]}",
                "event_name": event_name,
                "timestamp": (now - timedelta(seconds=random.randint(1, 86400))).isoformat(),
                "url": f"https://loja.exemplo.com/{'checkout' if is_purchase else 'produto/' + str(random.randint(100, 999))}",
                "value": round(random.uniform(50, 500), 2) if is_purchase else None,
                "currency": random.choice(currencies) if is_purchase else None,
                "trust_score": round(random.uniform(0.3, 1.0), 4),
                "trust_action": random.choice(trust_actions),
                "platforms_sent": ["meta", "google", "tiktok", "bigquery"],
                "platform_success": random.randint(3, 4),
                "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "ip_country": random.choice(countries)
            })
        
        return {
            "events": events,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + limit) < total,
            "data_source": "mock"
        }
    
    async def get_event_detail(
        self,
        organization_id: str,
        event_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get detailed event information."""
        if self.use_mock:
            return self._mock_event_detail(event_id)
        
        query = f"""
        SELECT *
        FROM `{self.project_id}.{self.dataset_id}.events`
        WHERE event_id = '{event_id}'
        AND organization_id = '{organization_id}'
        """
        
        try:
            result = list(self.bq_client.query(query).result())
            
            if not result:
                return None
            
            row = result[0]
            
            return {
                "event_id": row.event_id,
                "ssi_id": row.ssi_id,
                "event_name": row.event_name,
                "timestamp": row.timestamp.isoformat(),
                "url": row.url,
                "value": row.value,
                "currency": row.currency,
                "trust_score": row.trust_score,
                "trust_action": row.trust_action,
                "platforms_sent": row.platforms_sent or [],
                "platform_success": row.platform_success,
                "user_agent": row.user_agent,
                "ip_country": row.ip_country,
                "email_hash": row.email_hash,
                "phone_hash": row.phone_hash,
                "external_id": row.external_id,
                "trust_signals": row.trust_signals or {},
                "block_reasons": row.block_reasons or [],
                "platform_responses": row.platform_responses or {},
                "ltv_tier": row.ltv_tier,
                "churn_risk": row.churn_risk,
                "propensity_score": row.propensity_score,
                "bid_strategy": row.bid_strategy,
                "bid_multiplier": row.bid_multiplier,
                "content_ids": row.content_ids,
                "content_type": row.content_type,
                "content_category": row.content_category,
                "num_items": row.num_items,
                "data_source": "bigquery"
            }
            
        except Exception as e:
            logger.error(f"BigQuery Error in get_event_detail: {e}")
            return self._mock_event_detail(event_id)
    
    def _mock_event_detail(self, event_id: str) -> Dict:
        """Return mock event detail."""
        now = datetime.utcnow()
        
        return {
            "event_id": event_id,
            "ssi_id": f"ssi_{hashlib.md5(event_id.encode()).hexdigest()[:16]}",
            "event_name": "Purchase",
            "timestamp": now.isoformat(),
            "url": "https://loja.exemplo.com/checkout",
            "value": round(random.uniform(100, 500), 2),
            "currency": "BRL",
            "trust_score": round(random.uniform(0.7, 0.95), 4),
            "trust_action": "allow",
            "platforms_sent": ["meta", "google", "tiktok", "bigquery"],
            "platform_success": 4,
            "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "ip_country": "BR",
            "email_hash": hashlib.sha256(b"test@example.com").hexdigest(),
            "phone_hash": hashlib.sha256(b"+5511999999999").hexdigest(),
            "external_id": f"user_{random.randint(10000, 99999)}",
            "trust_signals": {
                "ip_reputation": 0.85,
                "user_agent_valid": True,
                "has_click_id": True,
                "behavior_score": 0.78
            },
            "block_reasons": [],
            "platform_responses": {
                "meta": {"status": 200, "events_received": 1},
                "google": {"status": 204},
                "tiktok": {"status": 200},
                "bigquery": {"status": 200}
            },
            "ltv_tier": "High",
            "churn_risk": "Low",
            "propensity_score": 0.72,
            "bid_strategy": "acquisition",
            "bid_multiplier": 1.25,
            "content_ids": ["PROD-001", "PROD-002"],
            "content_type": "product",
            "content_category": "electronics",
            "num_items": 2,
            "data_source": "mock"
        }
    
    # =========================================================================
    # BID METRICS
    # =========================================================================
    
    async def get_bid_metrics(self, organization_id: str) -> Dict[str, Any]:
        """Get bid optimization metrics."""
        if self.use_mock:
            return self._mock_bid_metrics()
        
        cache_key = self._cache_key("bid_metrics", organization_id)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        
        query = f"""
        SELECT
            bid_strategy,
            COUNT(*) as count,
            AVG(bid_multiplier) as avg_multiplier,
            AVG(CASE WHEN event_name = 'Purchase' THEN value END) as avg_value
        FROM `{self.project_id}.{self.dataset_id}.events`
        WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        AND organization_id = '{organization_id}'
        AND bid_strategy IS NOT NULL
        GROUP BY bid_strategy
        """
        
        try:
            result = list(self.bq_client.query(query).result())
            
            strategies = {}
            total_count = 0
            total_multiplier = 0
            
            for row in result:
                strategy = row.bid_strategy
                strategies[strategy] = {
                    "count": row.count,
                    "avg_multiplier": round(row.avg_multiplier or 1.0, 4),
                    "avg_value": round(row.avg_value or 0, 2)
                }
                total_count += row.count
                total_multiplier += (row.avg_multiplier or 1.0) * row.count
            
            data = {
                "strategies": strategies,
                "total_events_with_bid": total_count,
                "avg_multiplier": round(total_multiplier / total_count, 4) if total_count > 0 else 1.0,
                "last_updated": datetime.utcnow().isoformat(),
                "data_source": "bigquery"
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["bid_metrics"])
            return data
            
        except Exception as e:
            logger.error(f"BigQuery Error in get_bid_metrics: {e}")
            return self._mock_bid_metrics()
    
    def _mock_bid_metrics(self) -> Dict:
        """Return mock bid metrics."""
        total = 12000 + random.randint(-1000, 1000)
        
        return {
            "strategies": {
                "aggressive": {"count": int(total * 0.08), "avg_multiplier": 1.65, "avg_value": 180.50},
                "retention": {"count": int(total * 0.12), "avg_multiplier": 1.45, "avg_value": 145.00},
                "acquisition": {"count": int(total * 0.25), "avg_multiplier": 1.25, "avg_value": 95.00},
                "nurture": {"count": int(total * 0.35), "avg_multiplier": 1.05, "avg_value": 65.00},
                "conservative": {"count": int(total * 0.15), "avg_multiplier": 0.85, "avg_value": 45.00},
                "exclude": {"count": int(total * 0.05), "avg_multiplier": 0, "avg_value": 0},
            },
            "total_events_with_bid": total,
            "avg_multiplier": 1.15,
            "last_updated": datetime.utcnow().isoformat(),
            "data_source": "mock"
        }
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()
            self._redis = None


# =============================================================================
# SINGLETON / FACTORY
# =============================================================================

_dashboard_service: Optional[DashboardDataService] = None


def get_dashboard_service() -> DashboardDataService:
    """Get or create the dashboard service singleton."""
    global _dashboard_service
    if _dashboard_service is None:
        _dashboard_service = DashboardDataService()
    return _dashboard_service


async def init_dashboard_service(
    project_id: str = None,
    dataset_id: str = "ssi_shadow",
    redis_url: str = None
) -> DashboardDataService:
    """Initialize the dashboard service with specific config."""
    global _dashboard_service
    _dashboard_service = DashboardDataService(
        project_id=project_id,
        dataset_id=dataset_id,
        redis_url=redis_url
    )
    return _dashboard_service
