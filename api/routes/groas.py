"""
S.S.I. SHADOW - gROAS API Routes
Endpoints for gROAS automation control.
"""

from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime

router = APIRouter(prefix="/groas", tags=["gROAS Automation"])


# =============================================================================
# SCHEMAS
# =============================================================================

class OptimizationRequest(BaseModel):
    campaign_ids: Optional[List[str]] = Field(None, description="Campaign IDs to optimize (all if empty)")
    auto_apply: bool = Field(False, description="Automatically apply recommendations")
    dry_run: bool = Field(True, description="Don't make actual changes")


class RecommendationResponse(BaseModel):
    action: str
    campaign_id: str
    ad_group_id: Optional[str]
    keyword_text: Optional[str]
    current_value: Optional[float]
    recommended_value: Optional[float]
    reason: str
    confidence: float


class OptimizationResponse(BaseModel):
    cycle_id: str
    status: str
    started_at: datetime
    completed_at: Optional[datetime]
    campaigns_analyzed: int
    recommendations_count: int
    recommendations_applied: int
    recommendations: List[RecommendationResponse]


class StatusResponse(BaseModel):
    running: bool
    last_optimization: Optional[str]
    last_run_at: Optional[datetime]
    total_applied_changes: int
    config: Dict[str, Any]


# =============================================================================
# DEPENDENCY (would be injected in real app)
# =============================================================================

_orchestrator = None

def get_orchestrator():
    global _orchestrator
    if _orchestrator is None:
        from ads_engine.groas_orchestrator import GROASOrchestrator
        from ads_engine.google_ads_client import create_google_ads_manager
        
        google_client = create_google_ads_manager(use_mock=True)
        _orchestrator = GROASOrchestrator(google_ads_client=google_client)
    
    return _orchestrator


# =============================================================================
# ENDPOINTS
# =============================================================================

@router.post("/start", response_model=OptimizationResponse)
async def start_optimization(
    request: OptimizationRequest,
    background_tasks: BackgroundTasks,
    orchestrator = Depends(get_orchestrator)
):
    """
    Start a gROAS optimization cycle.
    
    This will:
    1. Fetch search terms from Google Ads
    2. Analyze intent for each term
    3. Generate keyword and bid recommendations
    4. Optionally apply changes (if auto_apply=True and dry_run=False)
    """
    if orchestrator.is_running:
        raise HTTPException(status_code=409, detail="Optimization already running")
    
    result = await orchestrator.run_optimization_cycle(
        campaign_ids=request.campaign_ids,
        auto_apply=request.auto_apply,
        dry_run=request.dry_run
    )
    
    return OptimizationResponse(
        cycle_id=result.cycle_id,
        status="completed",
        started_at=result.started_at,
        completed_at=result.completed_at,
        campaigns_analyzed=result.campaigns_analyzed,
        recommendations_count=result.recommendations_generated,
        recommendations_applied=result.recommendations_applied,
        recommendations=[
            RecommendationResponse(
                action=r.action.value,
                campaign_id=r.campaign_id,
                ad_group_id=r.ad_group_id,
                keyword_text=r.keyword_text,
                current_value=r.current_value,
                recommended_value=r.recommended_value,
                reason=r.reason,
                confidence=r.confidence
            )
            for r in result.recommendations[:50]  # Limit response size
        ]
    )


@router.get("/status", response_model=StatusResponse)
async def get_status(orchestrator = Depends(get_orchestrator)):
    """Get current gROAS automation status."""
    status = orchestrator.get_status()
    return StatusResponse(**status)


@router.get("/recommendations", response_model=List[RecommendationResponse])
async def get_recommendations(
    campaign_ids: Optional[str] = None,
    orchestrator = Depends(get_orchestrator)
):
    """
    Get recommendations without applying them.
    
    Use this to preview what changes would be made.
    """
    ids = campaign_ids.split(",") if campaign_ids else None
    recommendations = await orchestrator.get_recommendations(campaign_ids=ids)
    
    return [
        RecommendationResponse(
            action=r.action.value,
            campaign_id=r.campaign_id,
            ad_group_id=r.ad_group_id,
            keyword_text=r.keyword_text,
            current_value=r.current_value,
            recommended_value=r.recommended_value,
            reason=r.reason,
            confidence=r.confidence
        )
        for r in recommendations
    ]


@router.post("/apply")
async def apply_recommendations(
    recommendation_ids: List[str],
    orchestrator = Depends(get_orchestrator)
):
    """
    Manually apply specific recommendations.
    """
    # In a full implementation, would apply specific recommendations by ID
    return {"status": "not_implemented", "message": "Manual apply coming soon"}


@router.post("/stop")
async def stop_optimization(orchestrator = Depends(get_orchestrator)):
    """Stop running optimization."""
    if not orchestrator.is_running:
        raise HTTPException(status_code=400, detail="No optimization running")
    
    # Would stop scheduler if running
    return {"status": "stopped"}
