"""
S.S.I. SHADOW - Budget Applier Tests
"""

import pytest
from unittest.mock import AsyncMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from automation.budget_applier import (
    BudgetApplier,
    BudgetAllocation,
    BudgetApplierConfig,
    BudgetSafetyController,
    Platform
)


class TestBudgetSafetyController:
    """Tests for budget safety validation."""
    
    @pytest.fixture
    def controller(self):
        config = BudgetApplierConfig(
            max_increase_pct=1.0,
            max_decrease_pct=0.5,
            min_budget=5.0
        )
        return BudgetSafetyController(config)
    
    def test_valid_increase(self, controller):
        is_valid, error = controller.validate(100.0, 150.0)
        assert is_valid is True
        assert error is None
    
    def test_excessive_increase(self, controller):
        is_valid, error = controller.validate(100.0, 250.0)  # 150% increase
        assert is_valid is False
        assert "exceeds max" in error.lower()
    
    def test_excessive_decrease(self, controller):
        is_valid, error = controller.validate(100.0, 40.0)  # 60% decrease
        assert is_valid is False
        assert "exceeds max" in error.lower()
    
    def test_below_minimum(self, controller):
        is_valid, error = controller.validate(10.0, 3.0)
        assert is_valid is False
        assert "minimum" in error.lower()


class TestBudgetApplier:
    """Tests for BudgetApplier."""
    
    @pytest.fixture
    def applier(self):
        return BudgetApplier(
            config=BudgetApplierConfig(dry_run=True)
        )
    
    @pytest.mark.asyncio
    async def test_apply_allocation_dry_run(self, applier):
        allocations = [
            BudgetAllocation(
                campaign_id="123",
                platform=Platform.GOOGLE,
                current_budget=100.0,
                new_budget=120.0
            )
        ]
        
        results = await applier.apply_allocation(allocations, dry_run=True)
        
        assert len(results) == 1
        assert results[0].success is True
    
    @pytest.mark.asyncio
    async def test_apply_invalid_allocation(self, applier):
        allocations = [
            BudgetAllocation(
                campaign_id="123",
                platform=Platform.GOOGLE,
                current_budget=100.0,
                new_budget=3.0  # Below minimum
            )
        ]
        
        results = await applier.apply_allocation(allocations)
        
        assert len(results) == 1
        assert results[0].success is False
        assert results[0].error is not None


class TestBudgetAllocation:
    """Tests for BudgetAllocation dataclass."""
    
    def test_change_percentage(self):
        alloc = BudgetAllocation(
            campaign_id="123",
            platform=Platform.GOOGLE,
            current_budget=100.0,
            new_budget=120.0
        )
        
        assert alloc.change_pct == 0.2  # 20% increase
    
    def test_negative_change(self):
        alloc = BudgetAllocation(
            campaign_id="123",
            platform=Platform.GOOGLE,
            current_budget=100.0,
            new_budget=80.0
        )
        
        assert alloc.change_pct == -0.2  # 20% decrease
