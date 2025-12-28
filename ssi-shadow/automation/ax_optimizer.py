"""
S.S.I. SHADOW - Ax Bayesian Optimizer (C4)
==========================================

Otimização bayesiana de budget usando Facebook's Ax library.
Encontra a alocação ótima de budget entre campanhas.

Features:
- Multi-objective optimization (ROAS + Volume)
- Thompson Sampling para exploration/exploitation
- Integração com BidController existente
- Constraints de budget mínimo/máximo
- Warm start com dados históricos

Matemática:
- Gaussian Process surrogate model
- Expected Improvement acquisition function
- Multi-Armed Bandit para campanhas

Uso:
    optimizer = AxBudgetOptimizer()
    
    # Adicionar campanhas
    optimizer.add_campaign('camp1', current_budget=100, roas=2.5)
    optimizer.add_campaign('camp2', current_budget=200, roas=1.8)
    
    # Otimizar alocação
    allocation = await optimizer.optimize(total_budget=500)
    
    # Resultado: {'camp1': 180, 'camp2': 320}

Author: SSI Shadow Team
Version: 1.0.0
"""

import os
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

# Ax (Facebook's optimization library)
try:
    from ax.service.ax_client import AxClient
    from ax.modelbridge.generation_strategy import GenerationStrategy
    from ax.modelbridge.registry import Models
    from ax.core.observation import ObservationFeatures
    from ax.utils.common.result import Ok
    AX_AVAILABLE = True
except ImportError:
    AX_AVAILABLE = False
    AxClient = None

# BigQuery
try:
    from google.cloud import bigquery
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False
    bigquery = None

# Local imports
from monitoring.metrics import metrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ax_optimizer')


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class AxOptimizerConfig:
    """Configuration for Ax optimizer."""
    
    # BigQuery
    gcp_project_id: str = field(default_factory=lambda: os.getenv('GCP_PROJECT_ID', ''))
    bq_dataset: str = field(default_factory=lambda: os.getenv('BQ_DATASET', 'ssi_shadow'))
    
    # Optimization
    exploration_rate: float = 0.2         # 20% exploration
    min_data_points: int = 10             # Minimum trials before GP
    max_iterations: int = 100             # Maximum optimization iterations
    
    # Budget constraints
    min_campaign_budget: float = 10.0     # Minimum $10 per campaign
    max_campaign_budget_pct: float = 0.5  # Max 50% of total in one campaign
    
    # Objectives
    primary_objective: str = 'roas'       # 'roas', 'conversions', 'revenue'
    secondary_objective: str = 'volume'   # 'volume', 'cpa'
    
    # Thresholds
    min_roas: float = 1.0                 # Don't allocate if ROAS < 1
    min_spend_for_data: float = 50.0      # Minimum spend to have reliable data
    
    # Update frequency
    update_interval_hours: int = 6        # Re-optimize every 6 hours


config = AxOptimizerConfig()


# =============================================================================
# DATA CLASSES
# =============================================================================

class OptimizationObjective(Enum):
    """Optimization objectives."""
    MAXIMIZE_ROAS = "maximize_roas"
    MAXIMIZE_REVENUE = "maximize_revenue"
    MAXIMIZE_CONVERSIONS = "maximize_conversions"
    MINIMIZE_CPA = "minimize_cpa"
    BALANCED = "balanced"


@dataclass
class CampaignData:
    """Campaign data for optimization."""
    campaign_id: str
    campaign_name: str
    platform: str  # 'meta', 'google', 'tiktok'
    
    # Current state
    current_budget: float
    current_spend: float
    
    # Performance metrics
    impressions: int
    clicks: int
    conversions: int
    revenue: float
    
    # Calculated metrics
    ctr: float = 0.0
    cvr: float = 0.0
    cpa: float = 0.0
    roas: float = 0.0
    
    # Constraints
    min_budget: float = 10.0
    max_budget: float = 10000.0
    
    # Metadata
    last_updated: datetime = field(default_factory=datetime.utcnow)
    
    def __post_init__(self):
        """Calculate derived metrics."""
        if self.impressions > 0:
            self.ctr = self.clicks / self.impressions
        if self.clicks > 0:
            self.cvr = self.conversions / self.clicks
        if self.conversions > 0:
            self.cpa = self.current_spend / self.conversions
        if self.current_spend > 0:
            self.roas = self.revenue / self.current_spend


@dataclass
class OptimizationResult:
    """Result of budget optimization."""
    allocations: Dict[str, float]  # campaign_id -> budget
    expected_roas: float
    expected_revenue: float
    confidence: float
    iterations: int
    converged: bool
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'allocations': self.allocations,
            'expected_roas': round(self.expected_roas, 2),
            'expected_revenue': round(self.expected_revenue, 2),
            'confidence': round(self.confidence, 2),
            'iterations': self.iterations,
            'converged': self.converged,
            'timestamp': self.timestamp.isoformat(),
        }


# =============================================================================
# THOMPSON SAMPLING (Simple Multi-Armed Bandit)
# =============================================================================

class ThompsonSampling:
    """
    Thompson Sampling for campaign selection.
    
    Used when we don't have enough data for full GP optimization.
    Models each campaign's ROAS as a Beta distribution.
    """
    
    def __init__(self):
        # Beta distribution parameters for each campaign
        # alpha = successes (conversions), beta = failures (clicks - conversions)
        self.alphas: Dict[str, float] = {}
        self.betas: Dict[str, float] = {}
        self.revenues: Dict[str, float] = {}
        self.spends: Dict[str, float] = {}
    
    def update(self, campaign_id: str, data: CampaignData):
        """Update beliefs based on new data."""
        # Use conversions as successes
        alpha = max(1, data.conversions)
        beta = max(1, data.clicks - data.conversions) if data.clicks > data.conversions else 1
        
        self.alphas[campaign_id] = alpha
        self.betas[campaign_id] = beta
        self.revenues[campaign_id] = data.revenue
        self.spends[campaign_id] = data.current_spend
    
    def sample(self, campaign_id: str) -> float:
        """Sample from posterior distribution."""
        alpha = self.alphas.get(campaign_id, 1)
        beta = self.betas.get(campaign_id, 1)
        
        # Sample conversion rate from Beta distribution
        cvr_sample = np.random.beta(alpha, beta)
        
        # Estimate ROAS from sampled CVR
        # Assume average order value based on historical data
        if campaign_id in self.spends and self.spends[campaign_id] > 0:
            avg_order_value = self.revenues.get(campaign_id, 0) / max(1, self.alphas.get(campaign_id, 1))
        else:
            avg_order_value = 50  # Default assumption
        
        # ROAS = (CVR * AOV * Clicks) / Spend
        # Simplified: proportional to CVR
        return cvr_sample * avg_order_value
    
    def allocate(self, campaign_ids: List[str], total_budget: float) -> Dict[str, float]:
        """Allocate budget using Thompson Sampling."""
        # Sample for each campaign
        samples = {cid: self.sample(cid) for cid in campaign_ids}
        
        # Allocate proportionally to samples
        total_samples = sum(samples.values())
        if total_samples == 0:
            # Equal allocation
            return {cid: total_budget / len(campaign_ids) for cid in campaign_ids}
        
        allocations = {}
        for cid, sample in samples.items():
            allocations[cid] = (sample / total_samples) * total_budget
        
        return allocations


# =============================================================================
# AX BAYESIAN OPTIMIZER
# =============================================================================

class AxBudgetOptimizer:
    """
    Bayesian optimization for budget allocation using Ax.
    
    Uses Gaussian Process to model the relationship between
    budget allocation and ROAS/Revenue.
    """
    
    def __init__(self, config: AxOptimizerConfig = None):
        self.config = config or AxOptimizerConfig()
        
        if not AX_AVAILABLE:
            logger.warning("Ax library not available. Using Thompson Sampling fallback.")
        
        self.campaigns: Dict[str, CampaignData] = {}
        self.ax_client: Optional[AxClient] = None
        self.thompson_sampler = ThompsonSampling()
        self.history: List[OptimizationResult] = []
        
        # BigQuery client
        self.bq_client = bigquery.Client(project=self.config.gcp_project_id) if BIGQUERY_AVAILABLE else None
    
    def add_campaign(self, campaign: CampaignData):
        """Add or update campaign data."""
        self.campaigns[campaign.campaign_id] = campaign
        self.thompson_sampler.update(campaign.campaign_id, campaign)
    
    def remove_campaign(self, campaign_id: str):
        """Remove campaign from optimization."""
        if campaign_id in self.campaigns:
            del self.campaigns[campaign_id]
    
    async def load_campaigns_from_bigquery(self, hours: int = 24) -> int:
        """
        Load campaign performance data from BigQuery.
        
        Returns:
            Number of campaigns loaded
        """
        if not self.bq_client:
            logger.error("BigQuery client not available")
            return 0
        
        query = f"""
        WITH campaign_stats AS (
            SELECT
                COALESCE(
                    JSON_EXTRACT_SCALAR(custom_data, '$.campaign_id'),
                    'unknown'
                ) as campaign_id,
                COALESCE(
                    JSON_EXTRACT_SCALAR(custom_data, '$.campaign_name'),
                    'Unknown Campaign'
                ) as campaign_name,
                COALESCE(
                    JSON_EXTRACT_SCALAR(custom_data, '$.platform'),
                    'meta'
                ) as platform,
                COUNT(*) as impressions,
                COUNTIF(event_name = 'PageView') as pageviews,
                COUNTIF(event_name IN ('AddToCart', 'InitiateCheckout')) as clicks,
                COUNTIF(event_name = 'Purchase') as conversions,
                SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) as revenue,
                SUM(CASE WHEN event_name = 'Purchase' THEN 
                    COALESCE(CAST(JSON_EXTRACT_SCALAR(custom_data, '$.cost') AS FLOAT64), 0)
                ELSE 0 END) as spend
            FROM `{self.config.gcp_project_id}.{self.config.bq_dataset}.events_raw`
            WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
            GROUP BY campaign_id, campaign_name, platform
            HAVING conversions > 0 OR clicks > 10
        )
        SELECT * FROM campaign_stats
        WHERE campaign_id != 'unknown'
        ORDER BY revenue DESC
        """
        
        try:
            results = self.bq_client.query(query).result()
            
            count = 0
            for row in results:
                campaign = CampaignData(
                    campaign_id=row.campaign_id,
                    campaign_name=row.campaign_name,
                    platform=row.platform,
                    current_budget=row.spend * 1.2,  # Estimate budget as 120% of spend
                    current_spend=row.spend,
                    impressions=row.impressions,
                    clicks=row.clicks,
                    conversions=row.conversions,
                    revenue=row.revenue,
                )
                self.add_campaign(campaign)
                count += 1
            
            logger.info(f"Loaded {count} campaigns from BigQuery")
            return count
            
        except Exception as e:
            logger.error(f"Error loading campaigns: {e}")
            return 0
    
    def _initialize_ax_client(self, total_budget: float):
        """Initialize Ax client with campaign parameters."""
        if not AX_AVAILABLE:
            return
        
        # Create parameters for each campaign's budget allocation
        parameters = []
        for cid, campaign in self.campaigns.items():
            min_budget = max(self.config.min_campaign_budget, campaign.min_budget)
            max_budget = min(
                total_budget * self.config.max_campaign_budget_pct,
                campaign.max_budget
            )
            
            parameters.append({
                'name': f'budget_{cid}',
                'type': 'range',
                'bounds': [min_budget, max_budget],
                'value_type': 'float',
            })
        
        # Constraint: sum of budgets <= total_budget
        parameter_constraints = [
            f"{' + '.join([f'budget_{cid}' for cid in self.campaigns.keys()])} <= {total_budget}"
        ]
        
        # Create Ax client
        self.ax_client = AxClient(
            generation_strategy=GenerationStrategy(
                steps=[
                    # Start with Sobol (quasi-random)
                    {"model": Models.SOBOL, "num_trials": self.config.min_data_points},
                    # Then switch to Gaussian Process
                    {"model": Models.GPEI, "num_trials": -1},
                ]
            ),
            verbose_logging=False
        )
        
        self.ax_client.create_experiment(
            name="budget_optimization",
            parameters=parameters,
            objectives={
                "roas": "maximize",
                "revenue": "maximize",
            },
            parameter_constraints=parameter_constraints,
        )
    
    def _evaluate_allocation(self, allocation: Dict[str, float]) -> Tuple[float, float]:
        """
        Evaluate an allocation based on historical data.
        
        This is a simplified model - in production, you'd want to
        use actual response curves from experiments.
        """
        total_revenue = 0
        total_spend = 0
        
        for cid, budget in allocation.items():
            if cid not in self.campaigns:
                continue
            
            campaign = self.campaigns[cid]
            
            # Simple model: revenue scales with sqrt of budget
            # (diminishing returns)
            if campaign.current_spend > 0:
                # Base ROAS from historical data
                base_roas = campaign.roas
                
                # Scale factor based on budget change
                budget_ratio = budget / campaign.current_spend
                
                # Diminishing returns: ROAS decreases as budget increases
                # Using log to model diminishing returns
                efficiency = 1 / (1 + 0.1 * np.log(max(1, budget_ratio)))
                
                expected_roas = base_roas * efficiency
                expected_revenue = budget * expected_roas
            else:
                # No historical data - use prior
                expected_revenue = budget * self.config.min_roas
            
            total_revenue += expected_revenue
            total_spend += budget
        
        roas = total_revenue / total_spend if total_spend > 0 else 0
        return roas, total_revenue
    
    async def optimize(
        self,
        total_budget: float,
        objective: OptimizationObjective = OptimizationObjective.BALANCED,
        max_iterations: int = None
    ) -> OptimizationResult:
        """
        Find optimal budget allocation.
        
        Args:
            total_budget: Total budget to allocate
            objective: Optimization objective
            max_iterations: Maximum optimization iterations
        
        Returns:
            OptimizationResult with allocations
        """
        max_iterations = max_iterations or self.config.max_iterations
        
        if not self.campaigns:
            logger.warning("No campaigns to optimize")
            return OptimizationResult(
                allocations={},
                expected_roas=0,
                expected_revenue=0,
                confidence=0,
                iterations=0,
                converged=False
            )
        
        # Check if we have enough data for Ax
        total_conversions = sum(c.conversions for c in self.campaigns.values())
        
        if not AX_AVAILABLE or total_conversions < self.config.min_data_points * len(self.campaigns):
            # Use Thompson Sampling
            logger.info("Using Thompson Sampling (insufficient data for GP)")
            allocations = self.thompson_sampler.allocate(
                list(self.campaigns.keys()),
                total_budget
            )
            
            # Apply constraints
            allocations = self._apply_constraints(allocations, total_budget)
            
            roas, revenue = self._evaluate_allocation(allocations)
            
            result = OptimizationResult(
                allocations=allocations,
                expected_roas=roas,
                expected_revenue=revenue,
                confidence=0.5,  # Lower confidence for Thompson Sampling
                iterations=1,
                converged=True
            )
        else:
            # Use Ax Bayesian Optimization
            logger.info("Using Ax Bayesian Optimization")
            result = await self._ax_optimize(total_budget, max_iterations)
        
        # Record result
        self.history.append(result)
        
        # Update metrics
        if config.gcp_project_id:  # Only if metrics available
            metrics.ml_predictions.labels(
                model='ax_budget_optimizer',
                prediction_type='optimization'
            ).inc()
        
        return result
    
    async def _ax_optimize(
        self,
        total_budget: float,
        max_iterations: int
    ) -> OptimizationResult:
        """Run Ax optimization loop."""
        
        # Initialize Ax
        self._initialize_ax_client(total_budget)
        
        best_allocation = None
        best_roas = 0
        best_revenue = 0
        
        for i in range(max_iterations):
            # Get next trial
            try:
                parameters, trial_index = self.ax_client.get_next_trial()
            except Exception as e:
                logger.warning(f"Ax trial generation failed: {e}")
                break
            
            # Extract allocation from parameters
            allocation = {
                cid: parameters.get(f'budget_{cid}', 0)
                for cid in self.campaigns.keys()
            }
            
            # Evaluate allocation
            roas, revenue = self._evaluate_allocation(allocation)
            
            # Report results to Ax
            self.ax_client.complete_trial(
                trial_index=trial_index,
                raw_data={
                    'roas': (roas, 0.1),  # (mean, sem)
                    'revenue': (revenue, revenue * 0.1),
                }
            )
            
            # Track best
            if roas > best_roas:
                best_roas = roas
                best_revenue = revenue
                best_allocation = allocation
            
            # Check convergence
            if i > 20:
                # Simple convergence check
                recent_trials = self.ax_client.get_trials_data_frame()
                if len(recent_trials) > 10:
                    recent_roas = recent_trials['roas'].tail(10).std()
                    if recent_roas < 0.01:  # Very little variance
                        logger.info(f"Converged after {i} iterations")
                        break
        
        # Get final best parameters
        try:
            best_parameters, _ = self.ax_client.get_best_parameters()
            allocation = {
                cid: best_parameters.get(f'budget_{cid}', 0)
                for cid in self.campaigns.keys()
            }
            roas, revenue = self._evaluate_allocation(allocation)
        except:
            allocation = best_allocation or {}
            roas, revenue = best_roas, best_revenue
        
        # Apply constraints
        allocation = self._apply_constraints(allocation, total_budget)
        
        return OptimizationResult(
            allocations=allocation,
            expected_roas=roas,
            expected_revenue=revenue,
            confidence=0.8 if i > 20 else 0.6,
            iterations=i + 1,
            converged=i < max_iterations - 1
        )
    
    def _apply_constraints(
        self,
        allocation: Dict[str, float],
        total_budget: float
    ) -> Dict[str, float]:
        """Apply budget constraints to allocation."""
        
        # Ensure minimum budgets
        for cid in allocation:
            if cid in self.campaigns:
                min_budget = max(
                    self.config.min_campaign_budget,
                    self.campaigns[cid].min_budget
                )
                allocation[cid] = max(allocation[cid], min_budget)
        
        # Ensure no campaign gets more than max percentage
        max_per_campaign = total_budget * self.config.max_campaign_budget_pct
        for cid in allocation:
            allocation[cid] = min(allocation[cid], max_per_campaign)
        
        # Scale to match total budget
        current_total = sum(allocation.values())
        if current_total > 0 and abs(current_total - total_budget) > 0.01:
            scale = total_budget / current_total
            allocation = {cid: budget * scale for cid, budget in allocation.items()}
        
        # Round to cents
        allocation = {cid: round(budget, 2) for cid, budget in allocation.items()}
        
        return allocation
    
    def get_recommendation_explanation(self, result: OptimizationResult) -> str:
        """Generate human-readable explanation of allocation."""
        lines = [
            "📊 Budget Allocation Recommendation",
            "=" * 40,
            f"Total Budget: ${sum(result.allocations.values()):,.2f}",
            f"Expected ROAS: {result.expected_roas:.2f}x",
            f"Expected Revenue: ${result.expected_revenue:,.2f}",
            f"Confidence: {result.confidence:.0%}",
            "",
            "Allocation by Campaign:",
        ]
        
        # Sort by allocation
        sorted_alloc = sorted(
            result.allocations.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        total = sum(result.allocations.values())
        for cid, budget in sorted_alloc:
            pct = budget / total * 100 if total > 0 else 0
            campaign = self.campaigns.get(cid)
            name = campaign.campaign_name if campaign else cid
            
            current = campaign.current_budget if campaign else 0
            change = budget - current
            change_pct = (change / current * 100) if current > 0 else 0
            
            arrow = "↑" if change > 0 else "↓" if change < 0 else "→"
            
            lines.append(
                f"  • {name}: ${budget:,.2f} ({pct:.1f}%) {arrow} {change_pct:+.1f}%"
            )
        
        lines.extend([
            "",
            f"Optimization: {result.iterations} iterations, {'converged' if result.converged else 'max iterations reached'}",
        ])
        
        return "\n".join(lines)


# =============================================================================
# INTEGRATION WITH BID CONTROLLER
# =============================================================================

class AxBidControllerIntegration:
    """
    Integration layer between Ax optimizer and existing BidController.
    """
    
    def __init__(self, optimizer: AxBudgetOptimizer):
        self.optimizer = optimizer
    
    async def get_bid_recommendations(
        self,
        total_budget: float,
        current_bids: Dict[str, float]
    ) -> Dict[str, Dict[str, Any]]:
        """
        Get bid recommendations based on optimal allocation.
        
        Args:
            total_budget: Total budget to allocate
            current_bids: Current bid for each campaign
        
        Returns:
            Dict of campaign_id -> {
                'current_bid': float,
                'recommended_bid': float,
                'action': str,
                'budget_allocation': float,
                'expected_roas': float,
            }
        """
        # Optimize budget allocation
        result = await self.optimizer.optimize(total_budget)
        
        recommendations = {}
        
        for cid, budget in result.allocations.items():
            current_bid = current_bids.get(cid, 0)
            campaign = self.optimizer.campaigns.get(cid)
            
            if not campaign:
                continue
            
            # Calculate bid adjustment based on budget change
            if campaign.current_budget > 0:
                budget_change_pct = (budget - campaign.current_budget) / campaign.current_budget
            else:
                budget_change_pct = 0
            
            # Bid strategy: increase bid proportionally to budget increase
            # But cap at 50% change
            bid_change_pct = max(-0.5, min(0.5, budget_change_pct * 0.5))
            new_bid = current_bid * (1 + bid_change_pct) if current_bid > 0 else budget * 0.1
            
            # Determine action
            if abs(bid_change_pct) < 0.05:
                action = 'maintain'
            elif bid_change_pct > 0:
                action = 'increase'
            else:
                action = 'decrease'
            
            recommendations[cid] = {
                'current_bid': current_bid,
                'recommended_bid': round(new_bid, 2),
                'action': action,
                'budget_allocation': budget,
                'expected_roas': result.expected_roas,
                'reasoning': f"Budget {'increased' if budget_change_pct > 0 else 'decreased'} by {abs(budget_change_pct)*100:.1f}%"
            }
        
        return recommendations


# =============================================================================
# FASTAPI ROUTES
# =============================================================================

try:
    from fastapi import APIRouter, HTTPException
    from pydantic import BaseModel
    
    ax_router = APIRouter(prefix="/api/optimizer", tags=["optimizer"])
    
    # Global optimizer instance
    _optimizer: Optional[AxBudgetOptimizer] = None
    
    def get_optimizer() -> AxBudgetOptimizer:
        global _optimizer
        if _optimizer is None:
            _optimizer = AxBudgetOptimizer()
        return _optimizer
    
    class OptimizeRequest(BaseModel):
        total_budget: float
        objective: str = "balanced"
    
    class CampaignInput(BaseModel):
        campaign_id: str
        campaign_name: str
        platform: str = "meta"
        current_budget: float
        current_spend: float
        impressions: int = 0
        clicks: int = 0
        conversions: int = 0
        revenue: float = 0
    
    @ax_router.post("/campaigns")
    async def add_campaign(campaign: CampaignInput):
        """Add campaign data for optimization."""
        optimizer = get_optimizer()
        
        data = CampaignData(
            campaign_id=campaign.campaign_id,
            campaign_name=campaign.campaign_name,
            platform=campaign.platform,
            current_budget=campaign.current_budget,
            current_spend=campaign.current_spend,
            impressions=campaign.impressions,
            clicks=campaign.clicks,
            conversions=campaign.conversions,
            revenue=campaign.revenue,
        )
        
        optimizer.add_campaign(data)
        return {"status": "added", "campaign_id": campaign.campaign_id}
    
    @ax_router.post("/optimize")
    async def optimize(request: OptimizeRequest):
        """Run budget optimization."""
        optimizer = get_optimizer()
        
        if not optimizer.campaigns:
            raise HTTPException(400, "No campaigns added")
        
        objective = OptimizationObjective.BALANCED
        try:
            objective = OptimizationObjective[request.objective.upper()]
        except KeyError:
            pass
        
        result = await optimizer.optimize(
            total_budget=request.total_budget,
            objective=objective
        )
        
        return {
            **result.to_dict(),
            'explanation': optimizer.get_recommendation_explanation(result)
        }
    
    @ax_router.get("/campaigns")
    async def list_campaigns():
        """List all campaigns."""
        optimizer = get_optimizer()
        return {
            'campaigns': [
                {
                    'campaign_id': c.campaign_id,
                    'campaign_name': c.campaign_name,
                    'platform': c.platform,
                    'current_budget': c.current_budget,
                    'roas': c.roas,
                    'conversions': c.conversions,
                }
                for c in optimizer.campaigns.values()
            ]
        }
    
    @ax_router.post("/load-from-bigquery")
    async def load_from_bigquery(hours: int = 24):
        """Load campaigns from BigQuery."""
        optimizer = get_optimizer()
        count = await optimizer.load_campaigns_from_bigquery(hours)
        return {"loaded": count}
    
    @ax_router.get("/history")
    async def get_history(limit: int = 10):
        """Get optimization history."""
        optimizer = get_optimizer()
        return {
            'history': [r.to_dict() for r in optimizer.history[-limit:]]
        }

except ImportError:
    ax_router = None


# =============================================================================
# CLI
# =============================================================================

async def main():
    """CLI for testing."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Ax Budget Optimizer')
    parser.add_argument('--budget', type=float, default=1000, help='Total budget')
    parser.add_argument('--load-bq', action='store_true', help='Load from BigQuery')
    args = parser.parse_args()
    
    optimizer = AxBudgetOptimizer()
    
    if args.load_bq:
        await optimizer.load_campaigns_from_bigquery()
    else:
        # Add sample campaigns
        for i in range(5):
            optimizer.add_campaign(CampaignData(
                campaign_id=f'camp_{i}',
                campaign_name=f'Campaign {i}',
                platform='meta',
                current_budget=100 + i * 50,
                current_spend=80 + i * 40,
                impressions=10000 + i * 5000,
                clicks=500 + i * 200,
                conversions=10 + i * 5,
                revenue=500 + i * 300,
            ))
    
    result = await optimizer.optimize(args.budget)
    print(optimizer.get_recommendation_explanation(result))


if __name__ == '__main__':
    asyncio.run(main())
