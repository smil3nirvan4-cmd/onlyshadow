"""
S.S.I. SHADOW - Budget Applier
Applies budget allocations from Ax Optimizer to ad platforms.
"""

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)


class Platform(Enum):
    META = "meta"
    GOOGLE = "google"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    PINTEREST = "pinterest"


@dataclass
class BudgetAllocation:
    """Budget allocation for a campaign."""
    campaign_id: str
    platform: Platform
    current_budget: float
    new_budget: float
    change_pct: float = 0.0
    
    def __post_init__(self):
        if self.current_budget > 0:
            self.change_pct = (self.new_budget - self.current_budget) / self.current_budget


@dataclass
class ApplyResult:
    """Result of applying budget changes."""
    success: bool
    campaign_id: str
    platform: Platform
    previous_budget: float
    new_budget: float
    error: Optional[str] = None
    applied_at: Optional[datetime] = None


@dataclass
class BudgetApplierConfig:
    """Configuration for budget applier."""
    max_increase_pct: float = 1.0  # 100% max increase
    max_decrease_pct: float = 0.5  # 50% max decrease
    min_budget: float = 5.0  # Minimum $5 budget
    require_confirmation: bool = True
    dry_run: bool = False


class BudgetSafetyController:
    """Validates budget changes before applying."""
    
    def __init__(self, config: BudgetApplierConfig):
        self.config = config
    
    def validate(
        self,
        current: float,
        proposed: float
    ) -> tuple[bool, Optional[str]]:
        """
        Validate a budget change.
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        if proposed < self.config.min_budget:
            return False, f"Budget ${proposed:.2f} below minimum ${self.config.min_budget}"
        
        if current > 0:
            change_pct = (proposed - current) / current
            
            if change_pct > self.config.max_increase_pct:
                return False, f"Increase {change_pct:.0%} exceeds max {self.config.max_increase_pct:.0%}"
            
            if change_pct < -self.config.max_decrease_pct:
                return False, f"Decrease {abs(change_pct):.0%} exceeds max {self.config.max_decrease_pct:.0%}"
        
        return True, None


class BudgetApplier:
    """
    Applies budget allocations to multiple ad platforms.
    """
    
    def __init__(
        self,
        meta_client=None,
        google_client=None,
        tiktok_client=None,
        config: Optional[BudgetApplierConfig] = None
    ):
        self.meta_client = meta_client
        self.google_client = google_client
        self.tiktok_client = tiktok_client
        self.config = config or BudgetApplierConfig()
        self.safety = BudgetSafetyController(self.config)
        
        # History
        self._history: List[ApplyResult] = []
    
    async def apply_allocation(
        self,
        allocations: List[BudgetAllocation],
        dry_run: Optional[bool] = None
    ) -> List[ApplyResult]:
        """
        Apply budget allocations to all platforms.
        
        Args:
            allocations: List of budget allocations
            dry_run: Override config dry_run setting
        
        Returns:
            List of apply results
        """
        dry_run = dry_run if dry_run is not None else self.config.dry_run
        results = []
        
        for alloc in allocations:
            # Validate
            is_valid, error = self.safety.validate(alloc.current_budget, alloc.new_budget)
            
            if not is_valid:
                results.append(ApplyResult(
                    success=False,
                    campaign_id=alloc.campaign_id,
                    platform=alloc.platform,
                    previous_budget=alloc.current_budget,
                    new_budget=alloc.new_budget,
                    error=error
                ))
                continue
            
            # Apply
            if dry_run:
                logger.info(
                    f"[DRY RUN] Would update {alloc.platform.value} campaign {alloc.campaign_id} "
                    f"from ${alloc.current_budget:.2f} to ${alloc.new_budget:.2f}"
                )
                result = ApplyResult(
                    success=True,
                    campaign_id=alloc.campaign_id,
                    platform=alloc.platform,
                    previous_budget=alloc.current_budget,
                    new_budget=alloc.new_budget,
                    applied_at=datetime.utcnow()
                )
            else:
                result = await self._apply_single(alloc)
            
            results.append(result)
            self._history.append(result)
        
        # Log summary
        success_count = sum(1 for r in results if r.success)
        logger.info(f"Applied {success_count}/{len(results)} budget changes")
        
        return results
    
    async def _apply_single(self, alloc: BudgetAllocation) -> ApplyResult:
        """Apply a single budget change."""
        try:
            if alloc.platform == Platform.META:
                await self._apply_to_meta(alloc.campaign_id, alloc.new_budget)
            elif alloc.platform == Platform.GOOGLE:
                await self._apply_to_google(alloc.campaign_id, alloc.new_budget)
            elif alloc.platform == Platform.TIKTOK:
                await self._apply_to_tiktok(alloc.campaign_id, alloc.new_budget)
            else:
                raise ValueError(f"Unsupported platform: {alloc.platform}")
            
            return ApplyResult(
                success=True,
                campaign_id=alloc.campaign_id,
                platform=alloc.platform,
                previous_budget=alloc.current_budget,
                new_budget=alloc.new_budget,
                applied_at=datetime.utcnow()
            )
        
        except Exception as e:
            logger.error(f"Failed to apply budget to {alloc.campaign_id}: {e}")
            return ApplyResult(
                success=False,
                campaign_id=alloc.campaign_id,
                platform=alloc.platform,
                previous_budget=alloc.current_budget,
                new_budget=alloc.new_budget,
                error=str(e)
            )
    
    async def _apply_to_meta(self, campaign_id: str, budget: float):
        """Apply budget to Meta campaign."""
        if self.meta_client:
            await self.meta_client.update_campaign(campaign_id, daily_budget=budget)
        else:
            logger.warning(f"[MOCK] Meta: Set campaign {campaign_id} budget to ${budget:.2f}")
    
    async def _apply_to_google(self, campaign_id: str, budget: float):
        """Apply budget to Google Ads campaign."""
        if self.google_client:
            await self.google_client.update_campaign_budget(campaign_id, budget)
        else:
            logger.warning(f"[MOCK] Google: Set campaign {campaign_id} budget to ${budget:.2f}")
    
    async def _apply_to_tiktok(self, campaign_id: str, budget: float):
        """Apply budget to TikTok campaign."""
        if self.tiktok_client:
            await self.tiktok_client.update_campaign_budget(campaign_id, budget)
        else:
            logger.warning(f"[MOCK] TikTok: Set campaign {campaign_id} budget to ${budget:.2f}")
    
    async def rollback(self, results: List[ApplyResult]) -> List[ApplyResult]:
        """Rollback applied budget changes."""
        rollback_allocations = [
            BudgetAllocation(
                campaign_id=r.campaign_id,
                platform=r.platform,
                current_budget=r.new_budget,
                new_budget=r.previous_budget
            )
            for r in results
            if r.success
        ]
        
        return await self.apply_allocation(rollback_allocations, dry_run=False)
    
    def get_history(self, limit: int = 100) -> List[ApplyResult]:
        """Get recent apply history."""
        return self._history[-limit:]


class AxBudgetOptimizerV2:
    """
    Extended Ax Optimizer with auto-apply capability.
    """
    
    def __init__(
        self,
        ax_optimizer,
        budget_applier: BudgetApplier
    ):
        self.optimizer = ax_optimizer
        self.applier = budget_applier
    
    async def optimize_and_apply(
        self,
        total_budget: float,
        auto_apply: bool = True,
        dry_run: bool = False
    ) -> Dict[str, Any]:
        """
        Run optimization and optionally apply results.
        
        Args:
            total_budget: Total budget to allocate
            auto_apply: Whether to apply the allocation
            dry_run: If True, don't actually apply
        
        Returns:
            Optimization result with applied allocations
        """
        # Run optimization
        allocation = await self.optimizer.optimize(total_budget)
        
        result = {
            "allocation": allocation,
            "total_budget": total_budget,
            "applied": False,
            "apply_results": []
        }
        
        if auto_apply:
            # Convert to BudgetAllocation objects
            allocations = []
            for campaign_id, new_budget in allocation.items():
                # Get current budget (would need to fetch from platform)
                current_budget = new_budget * 0.9  # Placeholder
                
                allocations.append(BudgetAllocation(
                    campaign_id=campaign_id,
                    platform=Platform.GOOGLE,  # Would need to determine from campaign
                    current_budget=current_budget,
                    new_budget=new_budget
                ))
            
            apply_results = await self.applier.apply_allocation(allocations, dry_run=dry_run)
            result["applied"] = not dry_run
            result["apply_results"] = [
                {"campaign_id": r.campaign_id, "success": r.success, "error": r.error}
                for r in apply_results
            ]
        
        return result
