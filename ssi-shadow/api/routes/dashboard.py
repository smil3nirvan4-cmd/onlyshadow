"""
S.S.I. SHADOW - Dashboard Routes
================================
REST API endpoints for the dashboard.
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Path

from api.models.schemas import (
    OverviewResponse,
    PlatformsResponse,
    TrustScoreResponse,
    MLPredictionsResponse,
    BidMetricsResponse,
    FunnelResponse,
    EventsListResponse,
    EventDetail,
    EventFilters,
    EventType,
    TrustAction,
)
from api.middleware.auth import (
    get_current_user,
    get_organization_context,
    check_rate_limit,
    AuthenticatedUser,
    OrganizationContext,
)
from api.services.dashboard_service import DashboardDataService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

# Service instance (initialized in main.py)
_data_service: Optional[DashboardDataService] = None


def get_data_service() -> DashboardDataService:
    """Get the dashboard data service."""
    global _data_service
    if _data_service is None:
        _data_service = DashboardDataService()
    return _data_service


def set_data_service(service: DashboardDataService):
    """Set the dashboard data service (for testing)."""
    global _data_service
    _data_service = service


# =============================================================================
# OVERVIEW
# =============================================================================

@router.get(
    "/overview",
    response_model=OverviewResponse,
    summary="Get dashboard overview",
    description="Returns key metrics for the dashboard overview with comparison to previous period."
)
async def get_overview(
    date: Optional[datetime] = Query(None, description="Date to get metrics for (defaults to today)"),
    ctx: OrganizationContext = Depends(get_organization_context),
    _: None = Depends(check_rate_limit)
):
    """Get dashboard overview metrics."""
    try:
        service = get_data_service()
        data = await service.get_overview(ctx.organization_id, date)
        return OverviewResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get overview: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve overview data")


# =============================================================================
# PLATFORMS
# =============================================================================

@router.get(
    "/platforms",
    response_model=PlatformsResponse,
    summary="Get platform status",
    description="Returns the status and metrics for all ad platforms (Meta, TikTok, Google)."
)
async def get_platforms(
    ctx: OrganizationContext = Depends(get_organization_context),
    _: None = Depends(check_rate_limit)
):
    """Get platform status and metrics."""
    try:
        service = get_data_service()
        data = await service.get_platforms(ctx.organization_id)
        return PlatformsResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get platforms: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve platform data")


# =============================================================================
# TRUST SCORE
# =============================================================================

@router.get(
    "/trust-score",
    response_model=TrustScoreResponse,
    summary="Get trust score analytics",
    description="Returns trust score distribution, block rates, and top block reasons."
)
async def get_trust_score(
    ctx: OrganizationContext = Depends(get_organization_context),
    _: None = Depends(check_rate_limit)
):
    """Get trust score analytics."""
    try:
        service = get_data_service()
        data = await service.get_trust_score(ctx.organization_id)
        return TrustScoreResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get trust score: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve trust score data")


# =============================================================================
# ML PREDICTIONS
# =============================================================================

@router.get(
    "/ml-predictions",
    response_model=MLPredictionsResponse,
    summary="Get ML predictions overview",
    description="Returns LTV segments, churn risk distribution, and propensity scores."
)
async def get_ml_predictions(
    ctx: OrganizationContext = Depends(get_organization_context),
    _: None = Depends(check_rate_limit)
):
    """Get ML predictions overview."""
    try:
        service = get_data_service()
        data = await service.get_ml_predictions(ctx.organization_id)
        return MLPredictionsResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get ML predictions: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve ML predictions")


# =============================================================================
# BID METRICS
# =============================================================================

@router.get(
    "/bid-metrics",
    response_model=BidMetricsResponse,
    summary="Get bid optimization metrics",
    description="Returns bid strategy distribution and budget impact metrics."
)
async def get_bid_metrics(
    ctx: OrganizationContext = Depends(get_organization_context),
    _: None = Depends(check_rate_limit)
):
    """Get bid optimization metrics."""
    # For now, return mock data as bid metrics require additional tables
    return BidMetricsResponse(
        strategy_distribution=[
            {"strategy": "aggressive", "count": 1500, "percentage": 15.0, "avg_multiplier": 1.5, "total_budget_impact": 2500.0},
            {"strategy": "retention", "count": 800, "percentage": 8.0, "avg_multiplier": 1.3, "total_budget_impact": 1200.0},
            {"strategy": "standard", "count": 6000, "percentage": 60.0, "avg_multiplier": 1.0, "total_budget_impact": 0.0},
            {"strategy": "conservative", "count": 1200, "percentage": 12.0, "avg_multiplier": 0.7, "total_budget_impact": -800.0},
            {"strategy": "exclude", "count": 500, "percentage": 5.0, "avg_multiplier": 0.0, "total_budget_impact": -1500.0},
        ],
        total_bid_adjustments=10000,
        avg_multiplier=1.02,
        budget_saved=2300.0,
        budget_reallocated=3700.0,
        excluded_users=500,
        aggressive_bids=1500,
        retention_bids=800,
        platform_breakdown={
            "meta": {"avg_multiplier": 1.05, "total_impact": 1200.0},
            "tiktok": {"avg_multiplier": 0.98, "total_impact": -200.0},
            "google": {"avg_multiplier": 1.01, "total_impact": 400.0},
        },
        last_updated=datetime.utcnow()
    )


# =============================================================================
# FUNNEL
# =============================================================================

@router.get(
    "/funnel",
    response_model=FunnelResponse,
    summary="Get conversion funnel",
    description="Returns the conversion funnel from page view to purchase."
)
async def get_funnel(
    ctx: OrganizationContext = Depends(get_organization_context),
    _: None = Depends(check_rate_limit)
):
    """Get conversion funnel."""
    try:
        service = get_data_service()
        data = await service.get_funnel(ctx.organization_id)
        return FunnelResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get funnel: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve funnel data")


# =============================================================================
# EVENTS
# =============================================================================

@router.get(
    "/events",
    response_model=EventsListResponse,
    summary="Get events list",
    description="Returns a paginated list of events with optional filters."
)
async def get_events(
    limit: int = Query(100, ge=1, le=1000, description="Number of events to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
    event_types: Optional[List[EventType]] = Query(None, description="Filter by event types"),
    platforms: Optional[List[str]] = Query(None, description="Filter by platforms"),
    trust_actions: Optional[List[TrustAction]] = Query(None, description="Filter by trust actions"),
    min_trust_score: Optional[float] = Query(None, ge=0, le=1, description="Minimum trust score"),
    max_trust_score: Optional[float] = Query(None, ge=0, le=1, description="Maximum trust score"),
    min_value: Optional[float] = Query(None, ge=0, description="Minimum event value"),
    max_value: Optional[float] = Query(None, description="Maximum event value"),
    start_date: Optional[datetime] = Query(None, description="Filter events after this date"),
    end_date: Optional[datetime] = Query(None, description="Filter events before this date"),
    search: Optional[str] = Query(None, description="Search in event ID or URL"),
    ctx: OrganizationContext = Depends(get_organization_context),
    _: None = Depends(check_rate_limit)
):
    """Get paginated list of events."""
    try:
        filters = {
            "event_types": event_types,
            "platforms": platforms,
            "trust_actions": trust_actions,
            "min_trust_score": min_trust_score,
            "max_trust_score": max_trust_score,
            "min_value": min_value,
            "max_value": max_value,
            "start_date": start_date,
            "end_date": end_date,
            "search": search,
        }
        
        service = get_data_service()
        data = await service.get_events(ctx.organization_id, limit, offset, filters)
        return EventsListResponse(**data)
    except Exception as e:
        logger.error(f"Failed to get events: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve events")


@router.get(
    "/events/{event_id}",
    response_model=EventDetail,
    summary="Get event details",
    description="Returns detailed information about a specific event."
)
async def get_event_detail(
    event_id: str = Path(..., description="Event ID"),
    ctx: OrganizationContext = Depends(get_organization_context),
    _: None = Depends(check_rate_limit)
):
    """Get detailed event information."""
    try:
        service = get_data_service()
        data = await service.get_event_detail(ctx.organization_id, event_id)
        
        if not data:
            raise HTTPException(status_code=404, detail="Event not found")
        
        return EventDetail(**data)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to get event detail: {e}")
        raise HTTPException(status_code=500, detail="Failed to retrieve event details")


# =============================================================================
# EXPORT
# =============================================================================

@router.post(
    "/export",
    summary="Export data",
    description="Request a data export in CSV or JSON format."
)
async def request_export(
    export_type: str = Query(..., pattern="^(events|overview|trust_score|ml_predictions)$"),
    format: str = Query("csv", pattern="^(csv|json)$"),
    start_date: Optional[datetime] = Query(None),
    end_date: Optional[datetime] = Query(None),
    ctx: OrganizationContext = Depends(get_organization_context),
    _: None = Depends(check_rate_limit)
):
    """Request a data export."""
    import uuid
    
    # Generate export ID
    export_id = str(uuid.uuid4())
    
    # In production, this would queue a background job
    return {
        "export_id": export_id,
        "status": "queued",
        "export_type": export_type,
        "format": format,
        "estimated_time_seconds": 30,
        "download_url": None,  # Will be populated when ready
        "created_at": datetime.utcnow().isoformat()
    }


@router.get(
    "/export/{export_id}",
    summary="Get export status",
    description="Check the status of a data export request."
)
async def get_export_status(
    export_id: str = Path(...),
    ctx: OrganizationContext = Depends(get_organization_context)
):
    """Get export status."""
    # Mock response - in production would check actual export status
    return {
        "export_id": export_id,
        "status": "completed",
        "download_url": f"https://storage.ssi-shadow.io/exports/{export_id}.csv",
        "expires_at": datetime.utcnow().isoformat(),
        "file_size_bytes": 1024000
    }
