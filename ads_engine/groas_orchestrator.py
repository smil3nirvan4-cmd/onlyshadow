"""
S.S.I. SHADOW - gROAS Automation Orchestrator
Connects Search Intent Engine with Google Ads API for end-to-end automation.
"""

import os
import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from enum import Enum

logger = logging.getLogger(__name__)


class OptimizationAction(Enum):
    ADD_KEYWORD = "add_keyword"
    ADD_NEGATIVE = "add_negative"
    INCREASE_BID = "increase_bid"
    DECREASE_BID = "decrease_bid"
    PAUSE_KEYWORD = "pause_keyword"
    REFRESH_COPY = "refresh_copy"
    ADJUST_BUDGET = "adjust_budget"


@dataclass
class OptimizationRecommendation:
    """Single optimization recommendation."""
    action: OptimizationAction
    campaign_id: str
    ad_group_id: Optional[str] = None
    keyword_id: Optional[str] = None
    keyword_text: Optional[str] = None
    current_value: Optional[float] = None
    recommended_value: Optional[float] = None
    reason: str = ""
    confidence: float = 0.0
    expected_impact: Dict[str, float] = field(default_factory=dict)
    applied: bool = False
    applied_at: Optional[datetime] = None


@dataclass
class OptimizationResult:
    """Result of an optimization cycle."""
    cycle_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    campaigns_analyzed: int = 0
    search_terms_analyzed: int = 0
    recommendations_generated: int = 0
    recommendations_applied: int = 0
    recommendations_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    recommendations: List[OptimizationRecommendation] = field(default_factory=list)


@dataclass
class GROASConfig:
    """Configuration for gROAS orchestrator."""
    # Thresholds
    min_impressions_for_analysis: int = 50
    min_conversions_for_bid_increase: float = 1.0
    high_intent_score_threshold: float = 0.7
    low_intent_score_threshold: float = 0.3
    
    # Bid adjustments
    max_bid_increase_pct: float = 0.30  # 30%
    max_bid_decrease_pct: float = 0.20  # 20%
    min_cpc_bid: float = 0.10
    max_cpc_bid: float = 50.0
    
    # Safety limits
    max_keywords_per_cycle: int = 50
    max_negatives_per_cycle: int = 30
    max_bid_changes_per_cycle: int = 100
    
    # Approval
    require_approval_for_large_changes: bool = True
    large_change_threshold_pct: float = 0.25
    
    # Auto-rollback
    enable_auto_rollback: bool = True
    rollback_if_performance_drops_pct: float = 0.20


class SearchIntentAnalyzer:
    """Analyzes search terms for purchase intent."""
    
    PURCHASE_SIGNALS = {
        'high': ['buy', 'comprar', 'price', 'preço', 'order', 'shop', 'store', 'discount', 'coupon'],
        'medium': ['best', 'review', 'compare', 'vs', 'deal', 'sale']
    }
    
    NEGATIVE_SIGNALS = ['free', 'diy', 'how to make', 'tutorial', 'recipe', 'download']
    
    def analyze(self, search_term: str) -> Dict[str, Any]:
        """Analyze search term and return intent data."""
        term_lower = search_term.lower()
        
        # Calculate intent score
        intent_score = 0.5  # Base score
        
        for signal in self.PURCHASE_SIGNALS['high']:
            if signal in term_lower:
                intent_score += 0.15
        
        for signal in self.PURCHASE_SIGNALS['medium']:
            if signal in term_lower:
                intent_score += 0.08
        
        for signal in self.NEGATIVE_SIGNALS:
            if signal in term_lower:
                intent_score -= 0.20
        
        intent_score = max(0.0, min(1.0, intent_score))
        
        return {
            'search_term': search_term,
            'intent_score': intent_score,
            'is_high_intent': intent_score >= 0.7,
            'is_low_intent': intent_score <= 0.3,
            'suggested_action': self._suggest_action(intent_score)
        }
    
    def _suggest_action(self, score: float) -> str:
        if score >= 0.7:
            return 'add_as_keyword'
        elif score <= 0.3:
            return 'add_as_negative'
        else:
            return 'monitor'


class GROASOrchestrator:
    """
    Orchestrates gROAS automation end-to-end.
    
    Flow:
    1. Fetch search terms from Google Ads
    2. Analyze intent using SearchIntentAnalyzer
    3. Generate recommendations
    4. Apply changes (if auto_apply enabled)
    5. Track results
    """
    
    def __init__(
        self,
        google_ads_client,
        config: Optional[GROASConfig] = None
    ):
        self.google_ads = google_ads_client
        self.config = config or GROASConfig()
        self.intent_analyzer = SearchIntentAnalyzer()
        
        # State
        self._running = False
        self._last_optimization: Optional[OptimizationResult] = None
        self._applied_changes: List[OptimizationRecommendation] = []
    
    @property
    def is_running(self) -> bool:
        return self._running
    
    async def run_optimization_cycle(
        self,
        campaign_ids: Optional[List[str]] = None,
        auto_apply: bool = False,
        dry_run: bool = True
    ) -> OptimizationResult:
        """
        Run a complete optimization cycle.
        
        Args:
            campaign_ids: Campaigns to optimize (all if None)
            auto_apply: Automatically apply recommendations
            dry_run: If True, don't apply changes even if auto_apply
        
        Returns:
            OptimizationResult with all recommendations
        """
        import uuid
        
        result = OptimizationResult(
            cycle_id=str(uuid.uuid4())[:8],
            started_at=datetime.utcnow()
        )
        
        self._running = True
        
        try:
            # Get campaigns
            campaigns = await self.google_ads.get_campaigns()
            if campaign_ids:
                campaigns = [c for c in campaigns if c.id in campaign_ids]
            
            result.campaigns_analyzed = len(campaigns)
            
            for campaign in campaigns:
                try:
                    # Analyze search terms
                    recommendations = await self._analyze_campaign(campaign)
                    result.recommendations.extend(recommendations)
                    
                except Exception as e:
                    logger.error(f"Error analyzing campaign {campaign.id}: {e}")
                    result.errors.append(f"Campaign {campaign.id}: {str(e)}")
            
            result.recommendations_generated = len(result.recommendations)
            
            # Apply recommendations if enabled
            if auto_apply and not dry_run:
                applied = await self._apply_recommendations(result.recommendations)
                result.recommendations_applied = applied
                result.recommendations_skipped = len(result.recommendations) - applied
            
            result.completed_at = datetime.utcnow()
            self._last_optimization = result
            
            logger.info(
                f"Optimization cycle {result.cycle_id} completed: "
                f"{result.recommendations_generated} recommendations, "
                f"{result.recommendations_applied} applied"
            )
            
        finally:
            self._running = False
        
        return result
    
    async def _analyze_campaign(self, campaign) -> List[OptimizationRecommendation]:
        """Analyze a single campaign and generate recommendations."""
        recommendations = []
        
        # Get search terms
        search_terms = await self.google_ads.get_search_terms_report(campaign.id)
        
        for st in search_terms:
            if st.impressions < self.config.min_impressions_for_analysis:
                continue
            
            # Analyze intent
            analysis = self.intent_analyzer.analyze(st.search_term)
            
            if analysis['is_high_intent'] and st.conversions >= self.config.min_conversions_for_bid_increase:
                # High intent, good conversions -> add as keyword
                recommendations.append(OptimizationRecommendation(
                    action=OptimizationAction.ADD_KEYWORD,
                    campaign_id=campaign.id,
                    ad_group_id=st.ad_group_id,
                    keyword_text=st.search_term,
                    reason=f"High intent score ({analysis['intent_score']:.2f}) with {st.conversions} conversions",
                    confidence=analysis['intent_score'],
                    expected_impact={'conversions': st.conversions * 0.1}
                ))
            
            elif analysis['is_low_intent'] and st.conversions < 0.5:
                # Low intent, no conversions -> add as negative
                recommendations.append(OptimizationRecommendation(
                    action=OptimizationAction.ADD_NEGATIVE,
                    campaign_id=campaign.id,
                    keyword_text=st.search_term,
                    reason=f"Low intent score ({analysis['intent_score']:.2f}) with minimal conversions",
                    confidence=1.0 - analysis['intent_score'],
                    expected_impact={'cost_savings': st.cost_micros / 1_000_000}
                ))
        
        return recommendations[:self.config.max_keywords_per_cycle]
    
    async def _apply_recommendations(
        self,
        recommendations: List[OptimizationRecommendation]
    ) -> int:
        """Apply recommendations to Google Ads."""
        applied = 0
        
        # Group by action type
        keywords_to_add = []
        negatives_to_add = []
        bids_to_update = []
        
        for rec in recommendations:
            if rec.action == OptimizationAction.ADD_KEYWORD:
                keywords_to_add.append(rec)
            elif rec.action == OptimizationAction.ADD_NEGATIVE:
                negatives_to_add.append(rec)
            elif rec.action in [OptimizationAction.INCREASE_BID, OptimizationAction.DECREASE_BID]:
                bids_to_update.append(rec)
        
        # Apply keywords (batch by ad group)
        ad_group_keywords: Dict[str, List[str]] = {}
        for rec in keywords_to_add[:self.config.max_keywords_per_cycle]:
            if rec.ad_group_id:
                if rec.ad_group_id not in ad_group_keywords:
                    ad_group_keywords[rec.ad_group_id] = []
                ad_group_keywords[rec.ad_group_id].append(rec.keyword_text)
        
        for ad_group_id, keywords in ad_group_keywords.items():
            try:
                from .google_ads_client import KeywordMatchType
                kw_tuples = [(kw, KeywordMatchType.PHRASE) for kw in keywords]
                await self.google_ads.add_keywords(ad_group_id, kw_tuples)
                applied += len(keywords)
            except Exception as e:
                logger.error(f"Error adding keywords to {ad_group_id}: {e}")
        
        # Apply negative keywords (batch by campaign)
        campaign_negatives: Dict[str, List[str]] = {}
        for rec in negatives_to_add[:self.config.max_negatives_per_cycle]:
            if rec.campaign_id not in campaign_negatives:
                campaign_negatives[rec.campaign_id] = []
            campaign_negatives[rec.campaign_id].append(rec.keyword_text)
        
        for campaign_id, negatives in campaign_negatives.items():
            try:
                await self.google_ads.add_negative_keywords(campaign_id, negatives)
                applied += len(negatives)
            except Exception as e:
                logger.error(f"Error adding negatives to {campaign_id}: {e}")
        
        return applied
    
    async def get_recommendations(
        self,
        campaign_ids: Optional[List[str]] = None
    ) -> List[OptimizationRecommendation]:
        """Get recommendations without applying them."""
        result = await self.run_optimization_cycle(
            campaign_ids=campaign_ids,
            auto_apply=False,
            dry_run=True
        )
        return result.recommendations
    
    def get_status(self) -> Dict[str, Any]:
        """Get current orchestrator status."""
        return {
            "running": self._running,
            "last_optimization": self._last_optimization.cycle_id if self._last_optimization else None,
            "last_run_at": self._last_optimization.started_at.isoformat() if self._last_optimization else None,
            "total_applied_changes": len(self._applied_changes),
            "config": {
                "max_keywords_per_cycle": self.config.max_keywords_per_cycle,
                "auto_apply_enabled": not self.config.require_approval_for_large_changes
            }
        }


class GROASScheduler:
    """Schedules automatic gROAS optimization runs."""
    
    def __init__(self, orchestrator: GROASOrchestrator):
        self.orchestrator = orchestrator
        self._task: Optional[asyncio.Task] = None
        self._running = False
    
    async def start(
        self,
        optimization_interval_hours: int = 6,
        auto_apply: bool = False
    ):
        """Start scheduled optimization."""
        self._running = True
        
        while self._running:
            try:
                await self.orchestrator.run_optimization_cycle(
                    auto_apply=auto_apply,
                    dry_run=not auto_apply
                )
            except Exception as e:
                logger.error(f"Scheduled optimization failed: {e}")
            
            await asyncio.sleep(optimization_interval_hours * 3600)
    
    def stop(self):
        """Stop scheduled optimization."""
        self._running = False
        if self._task:
            self._task.cancel()
