"""
S.S.I. SHADOW - Health Check Module
===================================
Comprehensive health checks for all system components.

Usage:
    from monitoring.health import HealthChecker, health_router
    
    # Check individual components
    checker = HealthChecker()
    result = await checker.check_all()
    
    # FastAPI integration
    app.include_router(health_router)
"""

import asyncio
import time
import logging
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime

import httpx
import redis.asyncio as redis

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & DATA CLASSES
# =============================================================================

class HealthStatus(str, Enum):
    """Health status enum."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class ComponentHealth:
    """Health status of a single component."""
    name: str
    status: HealthStatus
    message: str = ""
    latency_ms: float = 0
    details: Dict[str, Any] = field(default_factory=dict)
    last_check: datetime = field(default_factory=datetime.utcnow)


@dataclass
class SystemHealth:
    """Overall system health."""
    status: HealthStatus
    version: str
    uptime_seconds: float
    components: List[ComponentHealth]
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status.value,
            "version": self.version,
            "uptime_seconds": self.uptime_seconds,
            "timestamp": self.timestamp.isoformat(),
            "components": [
                {
                    "name": c.name,
                    "status": c.status.value,
                    "message": c.message,
                    "latency_ms": round(c.latency_ms, 2),
                    "details": c.details,
                    "last_check": c.last_check.isoformat()
                }
                for c in self.components
            ]
        }


# =============================================================================
# HEALTH CHECKER
# =============================================================================

class HealthChecker:
    """
    Comprehensive health checker for all system components.
    """
    
    def __init__(
        self,
        redis_url: str = None,
        bigquery_project: str = None,
        meta_pixel_id: str = None,
        version: str = "2.0.0"
    ):
        self.redis_url = redis_url
        self.bigquery_project = bigquery_project
        self.meta_pixel_id = meta_pixel_id
        self.version = version
        self.start_time = time.time()
        
        # HTTP client for external checks
        self.http_client = httpx.AsyncClient(timeout=10.0)
    
    @property
    def uptime(self) -> float:
        """Get uptime in seconds."""
        return time.time() - self.start_time
    
    async def check_all(self) -> SystemHealth:
        """Run all health checks."""
        checks = await asyncio.gather(
            self.check_redis(),
            self.check_bigquery(),
            self.check_meta_api(),
            self.check_tiktok_api(),
            self.check_google_api(),
            return_exceptions=True
        )
        
        components = []
        for check in checks:
            if isinstance(check, Exception):
                components.append(ComponentHealth(
                    name="unknown",
                    status=HealthStatus.UNHEALTHY,
                    message=str(check)
                ))
            else:
                components.append(check)
        
        # Determine overall status
        statuses = [c.status for c in components]
        if all(s == HealthStatus.HEALTHY for s in statuses):
            overall_status = HealthStatus.HEALTHY
        elif any(s == HealthStatus.UNHEALTHY for s in statuses):
            overall_status = HealthStatus.UNHEALTHY
        else:
            overall_status = HealthStatus.DEGRADED
        
        return SystemHealth(
            status=overall_status,
            version=self.version,
            uptime_seconds=self.uptime,
            components=components
        )
    
    async def check_redis(self) -> ComponentHealth:
        """Check Redis connectivity."""
        if not self.redis_url:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNKNOWN,
                message="Redis URL not configured"
            )
        
        start = time.time()
        try:
            client = redis.from_url(self.redis_url)
            await client.ping()
            
            # Get some stats
            info = await client.info("memory")
            used_memory = info.get("used_memory_human", "unknown")
            
            await client.close()
            
            return ComponentHealth(
                name="redis",
                status=HealthStatus.HEALTHY,
                message="Connected",
                latency_ms=(time.time() - start) * 1000,
                details={"used_memory": used_memory}
            )
        except Exception as e:
            return ComponentHealth(
                name="redis",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=(time.time() - start) * 1000
            )
    
    async def check_bigquery(self) -> ComponentHealth:
        """Check BigQuery connectivity."""
        if not self.bigquery_project:
            return ComponentHealth(
                name="bigquery",
                status=HealthStatus.UNKNOWN,
                message="BigQuery project not configured"
            )
        
        start = time.time()
        try:
            from google.cloud import bigquery
            
            client = bigquery.Client(project=self.bigquery_project)
            
            # Simple query to check connectivity
            query = "SELECT 1"
            job = client.query(query)
            list(job.result())
            
            return ComponentHealth(
                name="bigquery",
                status=HealthStatus.HEALTHY,
                message="Connected",
                latency_ms=(time.time() - start) * 1000,
                details={"project": self.bigquery_project}
            )
        except Exception as e:
            return ComponentHealth(
                name="bigquery",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=(time.time() - start) * 1000
            )
    
    async def check_meta_api(self) -> ComponentHealth:
        """Check Meta Graph API connectivity."""
        start = time.time()
        try:
            response = await self.http_client.get(
                "https://graph.facebook.com/v18.0/me",
                timeout=5.0
            )
            
            # We expect a 400 without token, but that means API is reachable
            if response.status_code in [200, 400, 401]:
                return ComponentHealth(
                    name="meta_api",
                    status=HealthStatus.HEALTHY,
                    message="API reachable",
                    latency_ms=(time.time() - start) * 1000
                )
            else:
                return ComponentHealth(
                    name="meta_api",
                    status=HealthStatus.DEGRADED,
                    message=f"Unexpected status: {response.status_code}",
                    latency_ms=(time.time() - start) * 1000
                )
        except Exception as e:
            return ComponentHealth(
                name="meta_api",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=(time.time() - start) * 1000
            )
    
    async def check_tiktok_api(self) -> ComponentHealth:
        """Check TikTok Events API connectivity."""
        start = time.time()
        try:
            response = await self.http_client.get(
                "https://business-api.tiktok.com/open_api/v1.3/pixel/list/",
                timeout=5.0
            )
            
            # We expect 401 without token, but that means API is reachable
            if response.status_code in [200, 400, 401, 403]:
                return ComponentHealth(
                    name="tiktok_api",
                    status=HealthStatus.HEALTHY,
                    message="API reachable",
                    latency_ms=(time.time() - start) * 1000
                )
            else:
                return ComponentHealth(
                    name="tiktok_api",
                    status=HealthStatus.DEGRADED,
                    message=f"Unexpected status: {response.status_code}",
                    latency_ms=(time.time() - start) * 1000
                )
        except Exception as e:
            return ComponentHealth(
                name="tiktok_api",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=(time.time() - start) * 1000
            )
    
    async def check_google_api(self) -> ComponentHealth:
        """Check Google Analytics API connectivity."""
        start = time.time()
        try:
            response = await self.http_client.get(
                "https://www.google-analytics.com/debug/collect",
                timeout=5.0
            )
            
            if response.status_code in [200, 400]:
                return ComponentHealth(
                    name="google_api",
                    status=HealthStatus.HEALTHY,
                    message="API reachable",
                    latency_ms=(time.time() - start) * 1000
                )
            else:
                return ComponentHealth(
                    name="google_api",
                    status=HealthStatus.DEGRADED,
                    message=f"Unexpected status: {response.status_code}",
                    latency_ms=(time.time() - start) * 1000
                )
        except Exception as e:
            return ComponentHealth(
                name="google_api",
                status=HealthStatus.UNHEALTHY,
                message=str(e),
                latency_ms=(time.time() - start) * 1000
            )
    
    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()


# =============================================================================
# READINESS & LIVENESS PROBES
# =============================================================================

class ProbeChecker:
    """
    Kubernetes-style readiness and liveness probes.
    """
    
    def __init__(self, health_checker: HealthChecker):
        self.health_checker = health_checker
        self._ready = False
        self._startup_complete = False
    
    def set_ready(self, ready: bool = True):
        """Set readiness state."""
        self._ready = ready
    
    def set_startup_complete(self):
        """Mark startup as complete."""
        self._startup_complete = True
        self._ready = True
    
    async def liveness(self) -> Dict[str, Any]:
        """
        Liveness probe - is the application running?
        Should return quickly and not check dependencies.
        """
        return {
            "status": "alive",
            "uptime_seconds": self.health_checker.uptime,
            "version": self.health_checker.version
        }
    
    async def readiness(self) -> Dict[str, Any]:
        """
        Readiness probe - is the application ready to receive traffic?
        Checks critical dependencies.
        """
        if not self._startup_complete:
            return {
                "status": "not_ready",
                "reason": "startup_incomplete"
            }
        
        if not self._ready:
            return {
                "status": "not_ready",
                "reason": "marked_not_ready"
            }
        
        # Quick check of critical dependencies
        checks = await asyncio.gather(
            self.health_checker.check_redis(),
            return_exceptions=True
        )
        
        for check in checks:
            if isinstance(check, Exception):
                return {
                    "status": "not_ready",
                    "reason": str(check)
                }
            if check.status == HealthStatus.UNHEALTHY:
                return {
                    "status": "not_ready",
                    "reason": f"{check.name}: {check.message}"
                }
        
        return {
            "status": "ready",
            "uptime_seconds": self.health_checker.uptime
        }
    
    async def startup(self) -> Dict[str, Any]:
        """
        Startup probe - has the application started successfully?
        """
        if self._startup_complete:
            return {"status": "started"}
        return {"status": "starting"}


# =============================================================================
# FASTAPI ROUTER
# =============================================================================

try:
    from fastapi import APIRouter, Response, status
    
    # Create router
    health_router = APIRouter(tags=["health"])
    
    # Global instances (initialized in app startup)
    _health_checker: Optional[HealthChecker] = None
    _probe_checker: Optional[ProbeChecker] = None
    
    def init_health_routes(
        redis_url: str = None,
        bigquery_project: str = None,
        version: str = "2.0.0"
    ):
        """Initialize health check instances."""
        global _health_checker, _probe_checker
        
        _health_checker = HealthChecker(
            redis_url=redis_url,
            bigquery_project=bigquery_project,
            version=version
        )
        _probe_checker = ProbeChecker(_health_checker)
        
        return _probe_checker
    
    @health_router.get("/health")
    async def health(response: Response):
        """Full health check endpoint."""
        if not _health_checker:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_initialized"}
        
        result = await _health_checker.check_all()
        
        if result.status == HealthStatus.UNHEALTHY:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        elif result.status == HealthStatus.DEGRADED:
            response.status_code = status.HTTP_200_OK  # Still accepting traffic
        
        return result.to_dict()
    
    @health_router.get("/health/live")
    async def liveness():
        """Kubernetes liveness probe."""
        if not _probe_checker:
            return {"status": "alive", "version": "unknown"}
        return await _probe_checker.liveness()
    
    @health_router.get("/health/ready")
    async def readiness(response: Response):
        """Kubernetes readiness probe."""
        if not _probe_checker:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_ready", "reason": "not_initialized"}
        
        result = await _probe_checker.readiness()
        
        if result["status"] != "ready":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
        return result
    
    @health_router.get("/health/startup")
    async def startup(response: Response):
        """Kubernetes startup probe."""
        if not _probe_checker:
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
            return {"status": "not_initialized"}
        
        result = await _probe_checker.startup()
        
        if result["status"] != "started":
            response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
        return result

except ImportError:
    health_router = None
    
    def init_health_routes(*args, **kwargs):
        logger.warning("FastAPI not installed, health routes not available")
        return None
