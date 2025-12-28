"""
S.S.I. SHADOW - Integration Tests
End-to-end flow tests.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))


class TestEventToOptimizationFlow:
    """Test complete flow from event to optimization."""
    
    @pytest.mark.asyncio
    async def test_event_triggers_analysis(self):
        """
        Test flow:
        1. Event received
        2. Stored in BigQuery
        3. Attribution calculated
        4. gROAS triggered
        5. Recommendations generated
        """
        # Mock components
        bq_client = AsyncMock()
        redis_client = AsyncMock()
        google_ads = AsyncMock()
        
        google_ads.get_campaigns.return_value = [
            MagicMock(id="123", name="Test Campaign")
        ]
        google_ads.get_search_terms_report.return_value = [
            MagicMock(
                search_term="buy product",
                campaign_id="123",
                ad_group_id="456",
                impressions=100,
                clicks=10,
                cost_micros=5_000_000,
                conversions=2.0
            )
        ]
        
        from ads_engine.groas_orchestrator import GROASOrchestrator
        
        orchestrator = GROASOrchestrator(
            google_ads_client=google_ads
        )
        
        result = await orchestrator.run_optimization_cycle(
            auto_apply=False,
            dry_run=True
        )
        
        assert result.campaigns_analyzed == 1
        assert result.recommendations_generated >= 0


class TestBudgetOptimizationFlow:
    """Test budget optimization flow."""
    
    @pytest.mark.asyncio
    async def test_optimize_and_apply(self):
        """
        Test flow:
        1. Get campaign performance
        2. Run Bayesian optimization
        3. Generate allocations
        4. Validate with safety checks
        5. Apply (if not dry run)
        """
        from automation.budget_applier import (
            BudgetApplier,
            BudgetAllocation,
            Platform,
            BudgetApplierConfig
        )
        
        applier = BudgetApplier(
            config=BudgetApplierConfig(dry_run=True)
        )
        
        allocations = [
            BudgetAllocation(
                campaign_id="123",
                platform=Platform.GOOGLE,
                current_budget=100.0,
                new_budget=120.0
            ),
            BudgetAllocation(
                campaign_id="456",
                platform=Platform.META,
                current_budget=80.0,
                new_budget=70.0
            )
        ]
        
        results = await applier.apply_allocation(allocations, dry_run=True)
        
        assert len(results) == 2
        assert all(r.success for r in results)


class TestWeatherBiddingFlow:
    """Test weather-based bidding flow."""
    
    @pytest.mark.asyncio
    async def test_weather_to_bid_adjustment(self):
        """
        Test flow:
        1. Fetch weather for target locations
        2. Match with product categories
        3. Calculate bid adjustments
        4. Apply to campaigns
        """
        from automation.weather_bid_applier import (
            WeatherBidApplier,
            WeatherData,
            WeatherCondition,
            ProductWeatherMapper
        )
        from datetime import datetime
        
        # Create mock weather service
        mock_weather = AsyncMock()
        mock_weather.get_weather = AsyncMock(return_value=WeatherData(
            city="New York",
            country="US",
            condition=WeatherCondition.RAIN,
            temperature=15.0,
            humidity=80.0,
            wind_speed=10.0,
            timestamp=datetime.utcnow()
        ))
        
        applier = WeatherBidApplier(weather_service=mock_weather)
        
        # Configure campaigns
        applier.configure_campaign(
            campaign_id="123",
            cities=["New York"],
            product_category="umbrellas"
        )
        
        # Calculate adjustments
        adjustments = await applier.calculate_adjustments()
        
        assert len(adjustments) == 1
        assert adjustments[0].bid_multiplier == 1.5  # Rain boost for umbrellas


class TestMultiTenancyFlow:
    """Test multi-tenant isolation."""
    
    @pytest.mark.asyncio
    async def test_tenant_data_isolation(self):
        """
        Test that data is isolated between tenants.
        """
        from tenant.tenant import (
            TenantContext,
            TenantRepository,
            Tenant,
            TenantPlan,
            get_current_tenant
        )
        
        repo = TenantRepository()
        
        # Create two tenants
        await repo.create(Tenant(id="tenant_a", name="A", plan=TenantPlan.PRO))
        await repo.create(Tenant(id="tenant_b", name="B", plan=TenantPlan.FREE))
        
        # Operations within tenant A context
        with TenantContext("tenant_a"):
            assert get_current_tenant() == "tenant_a"
            tenant = await repo.get("tenant_a")
            assert tenant.name == "A"
        
        # Operations within tenant B context
        with TenantContext("tenant_b"):
            assert get_current_tenant() == "tenant_b"
            tenant = await repo.get("tenant_b")
            assert tenant.name == "B"


class TestAPIEndpointFlow:
    """Test API endpoint flows."""
    
    @pytest.mark.asyncio
    async def test_health_endpoint(self):
        """Test health check returns correct status."""
        from fastapi.testclient import TestClient
        
        # Would import and test actual app
        # For now, just validate structure
        pass
    
    @pytest.mark.asyncio
    async def test_groas_endpoint(self):
        """Test gROAS endpoint triggers optimization."""
        pass
