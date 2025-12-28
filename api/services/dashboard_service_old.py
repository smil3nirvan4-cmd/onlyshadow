"""
S.S.I. SHADOW - Dashboard Data Service
======================================
Service for fetching dashboard data from BigQuery with caching.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from functools import lru_cache
import hashlib
import json

from google.cloud import bigquery
import redis.asyncio as redis

logger = logging.getLogger(__name__)


class DashboardDataService:
    """
    Service for fetching dashboard metrics from BigQuery.
    Implements caching with Redis for performance.
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
        
        # Initialize BigQuery client
        self.bq_client = bigquery.Client(project=self.project_id)
        
        # Redis client (initialized lazily)
        self._redis: Optional[redis.Redis] = None
        
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
    
    async def _get_redis(self) -> Optional[redis.Redis]:
        """Get or create Redis connection."""
        if not self.redis_url:
            return None
        
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url)
        
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
                    "current": current,
                    "previous": previous,
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
                "last_updated": datetime.utcnow().isoformat(),
                "period": "today"
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["overview"])
            return data
            
        except Exception as e:
            logger.error(f"Failed to get overview: {e}")
            raise
    
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
            "last_updated": datetime.utcnow().isoformat(),
            "period": "today"
        }
    
    # =========================================================================
    # PLATFORMS
    # =========================================================================
    
    async def get_platforms(self, organization_id: str) -> Dict[str, Any]:
        """Get platform status and metrics."""
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
            for p in ["meta", "tiktok", "google"]:
                if not any(plat["platform"] == p for plat in platforms):
                    platforms.append({
                        "platform": p,
                        "status": "down",
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
                "last_updated": datetime.utcnow().isoformat()
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["platforms"])
            return data
            
        except Exception as e:
            logger.error(f"Failed to get platforms: {e}")
            raise
    
    # =========================================================================
    # TRUST SCORE
    # =========================================================================
    
    async def get_trust_score(self, organization_id: str) -> Dict[str, Any]:
        """Get trust score analytics."""
        cache_key = self._cache_key("trust_score", organization_id)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        
        query = f"""
        WITH events AS (
            SELECT
                trust_score,
                trust_action,
                ARRAY_TO_STRING(block_reasons, ',') as block_reasons_str
            FROM `{self.project_id}.{self.dataset_id}.events`
            WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            AND organization_id = '{organization_id}'
        ),
        distribution AS (
            SELECT
                FLOOR(trust_score * 10) / 10 as bucket,
                COUNT(*) as count
            FROM events
            GROUP BY bucket
        ),
        reasons AS (
            SELECT
                reason,
                COUNT(*) as count
            FROM events, UNNEST(SPLIT(block_reasons_str, ',')) as reason
            WHERE trust_action = 'block' AND reason != ''
            GROUP BY reason
            ORDER BY count DESC
            LIMIT 10
        )
        SELECT
            (SELECT COUNT(*) FROM events) as total_events,
            (SELECT COUNT(*) FROM events WHERE trust_action = 'allow') as allowed,
            (SELECT COUNT(*) FROM events WHERE trust_action = 'challenge') as challenged,
            (SELECT COUNT(*) FROM events WHERE trust_action = 'block') as blocked,
            (SELECT AVG(trust_score) FROM events) as avg_score,
            (SELECT APPROX_QUANTILES(trust_score, 2)[OFFSET(1)] FROM events) as median_score,
            (SELECT COUNTIF(block_reasons_str LIKE '%bot%') FROM events) as bot_detections,
            (SELECT COUNTIF(block_reasons_str LIKE '%datacenter%') FROM events) as datacenter_blocks,
            (SELECT COUNTIF(block_reasons_str LIKE '%behavior%') FROM events) as behavioral_blocks
        """
        
        try:
            result = list(self.bq_client.query(query).result())
            row = result[0] if result else None
            
            if not row or row.total_events == 0:
                return self._empty_trust_score()
            
            total = row.total_events
            
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
                bucket_max = (i + 1) / 10
                bucket_count = next(
                    (r.count for r in dist_result if r.bucket == bucket_min),
                    0
                )
                distribution.append({
                    "range_min": bucket_min,
                    "range_max": bucket_max,
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
            
            blocked = row.blocked or 0
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
                "bot_detections": row.bot_detections or 0,
                "datacenter_blocks": row.datacenter_blocks or 0,
                "behavioral_blocks": row.behavioral_blocks or 0,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["trust_score"])
            return data
            
        except Exception as e:
            logger.error(f"Failed to get trust score: {e}")
            raise
    
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
            "bot_detections": 0,
            "datacenter_blocks": 0,
            "behavioral_blocks": 0,
            "last_updated": datetime.utcnow().isoformat()
        }
    
    # =========================================================================
    # ML PREDICTIONS
    # =========================================================================
    
    async def get_ml_predictions(self, organization_id: str) -> Dict[str, Any]:
        """Get ML predictions overview."""
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
                    ltv_segments[tier] = {"count": 0, "total_ltv": 0, "avg_ltv": 0}
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
            ltv_list = []
            for tier, data in ltv_segments.items():
                ltv_list.append({
                    "tier": tier,
                    "count": data["count"],
                    "percentage": round(data["count"] / total_users * 100, 2) if total_users > 0 else 0,
                    "avg_ltv": round(data["total_ltv"] / data["count"], 2) if data["count"] > 0 else 0,
                    "total_ltv": round(data["total_ltv"], 2)
                })
            
            churn_list = []
            for risk, data in churn_segments.items():
                churn_list.append({
                    "risk": risk,
                    "count": data["count"],
                    "percentage": round(data["count"] / total_users * 100, 2) if total_users > 0 else 0,
                    "avg_probability": round(data["total_prob"] / data["count"], 4) if data["count"] > 0 else 0
                })
            
            prop_list = []
            for tier, data in propensity_segments.items():
                prop_list.append({
                    "tier": tier,
                    "count": data["count"],
                    "percentage": round(data["count"] / total_users * 100, 2) if total_users > 0 else 0,
                    "avg_score": round(data["total_score"] / data["count"], 4) if data["count"] > 0 else 0
                })
            
            # Count special segments
            high_value = sum(d["count"] for d in ltv_list if d["tier"] in ["VIP", "High"])
            at_risk = sum(d["count"] for d in churn_list if d["risk"] in ["Critical", "High"])
            ready_to_buy = sum(d["count"] for d in prop_list if d["tier"] in ["Very High", "High"])
            
            data = {
                "ltv_segments": ltv_list,
                "churn_segments": churn_list,
                "propensity_segments": prop_list,
                "total_users_predicted": total_users,
                "models_last_updated": datetime.utcnow().isoformat(),
                "high_value_users": high_value,
                "at_risk_users": at_risk,
                "ready_to_buy_users": ready_to_buy,
                "last_updated": datetime.utcnow().isoformat()
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["ml_predictions"])
            return data
            
        except Exception as e:
            logger.error(f"Failed to get ML predictions: {e}")
            raise
    
    # =========================================================================
    # FUNNEL
    # =========================================================================
    
    async def get_funnel(self, organization_id: str) -> Dict[str, Any]:
        """Get conversion funnel."""
        cache_key = self._cache_key("funnel", organization_id)
        cached = await self._get_cached(cache_key)
        if cached:
            return cached
        
        query = f"""
        WITH funnel AS (
            SELECT
                event_name,
                COUNT(*) as count,
                COUNT(DISTINCT ssi_id) as unique_users
            FROM `{self.project_id}.{self.dataset_id}.events`
            WHERE timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            AND organization_id = '{organization_id}'
            AND event_name IN ('PageView', 'ViewContent', 'AddToCart', 'InitiateCheckout', 'Purchase')
            GROUP BY event_name
        )
        SELECT * FROM funnel
        """
        
        try:
            result = list(self.bq_client.query(query).result())
            
            # Define funnel stages
            stage_order = ['PageView', 'ViewContent', 'AddToCart', 'InitiateCheckout', 'Purchase']
            stage_names = {
                'PageView': 'Page Views',
                'ViewContent': 'Product Views',
                'AddToCart': 'Add to Cart',
                'InitiateCheckout': 'Checkout',
                'Purchase': 'Purchase'
            }
            
            # Build stage map
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
            
            # Calculate overall
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
                "last_updated": datetime.utcnow().isoformat()
            }
            
            await self._set_cached(cache_key, data, self.cache_ttls["funnel"])
            return data
            
        except Exception as e:
            logger.error(f"Failed to get funnel: {e}")
            raise
    
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
        filters = filters or {}
        
        # Build WHERE clauses
        where_clauses = [
            f"organization_id = '{organization_id}'",
            "timestamp > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)"
        ]
        
        if filters.get("event_types"):
            types = ",".join(f"'{t}'" for t in filters["event_types"])
            where_clauses.append(f"event_name IN ({types})")
        
        if filters.get("platforms"):
            # This would need a different query structure
            pass
        
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
        
        # Count query
        count_query = f"""
        SELECT COUNT(*) as total
        FROM `{self.project_id}.{self.dataset_id}.events`
        WHERE {where_str}
        """
        
        # Data query
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
            # Get total count
            count_result = list(self.bq_client.query(count_query).result())
            total = count_result[0].total if count_result else 0
            
            # Get events
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
                "has_more": (offset + limit) < total
            }
            
        except Exception as e:
            logger.error(f"Failed to get events: {e}")
            raise
    
    async def get_event_detail(
        self,
        organization_id: str,
        event_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get detailed event information."""
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
                "num_items": row.num_items
            }
            
        except Exception as e:
            logger.error(f"Failed to get event detail: {e}")
            raise
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()
