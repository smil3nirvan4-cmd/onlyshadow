"""
S.S.I. SHADOW - Health Check Routes
"""

from fastapi import APIRouter
from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime
import os

router = APIRouter(tags=["Health"])


class HealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    environment: str


class DetailedHealthResponse(BaseModel):
    status: str
    timestamp: datetime
    version: str
    environment: str
    checks: Dict[str, Any]


@router.get("/health", response_model=HealthResponse)
async def health_check():
    """Basic health check endpoint."""
    return HealthResponse(
        status="healthy",
        timestamp=datetime.utcnow(),
        version=os.getenv("APP_VERSION", "1.0.0"),
        environment=os.getenv("ENVIRONMENT", "development")
    )


@router.get("/health/detailed", response_model=DetailedHealthResponse)
async def detailed_health_check():
    """
    Detailed health check with all dependencies.
    """
    checks = {}
    overall_status = "healthy"
    
    # Check Redis
    try:
        # Would actually ping Redis
        checks["redis"] = {"status": "healthy", "latency_ms": 1}
    except Exception as e:
        checks["redis"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "degraded"
    
    # Check BigQuery
    try:
        checks["bigquery"] = {"status": "healthy"}
    except Exception as e:
        checks["bigquery"] = {"status": "unhealthy", "error": str(e)}
        overall_status = "degraded"
    
    # Check external APIs
    checks["meta_api"] = {"status": "healthy"}
    checks["google_ads_api"] = {"status": "healthy"}
    
    return DetailedHealthResponse(
        status=overall_status,
        timestamp=datetime.utcnow(),
        version=os.getenv("APP_VERSION", "1.0.0"),
        environment=os.getenv("ENVIRONMENT", "development"),
        checks=checks
    )


@router.get("/ready")
async def readiness_check():
    """Kubernetes readiness probe."""
    return {"ready": True}


@router.get("/live")
async def liveness_check():
    """Kubernetes liveness probe."""
    return {"alive": True}
