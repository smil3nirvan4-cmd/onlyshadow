"""
S.S.I. SHADOW - Weather Bidder Tests
"""

import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from automation.weather_bid_applier import (
    WeatherBidApplier,
    WeatherData,
    WeatherCondition,
    ProductWeatherMapper,
    ProductWeatherRule,
    WeatherBidAdjustment
)


class TestProductWeatherMapper:
    """Tests for product-weather mapping."""
    
    @pytest.fixture
    def mapper(self):
        return ProductWeatherMapper()
    
    def test_umbrella_rain_boost(self, mapper):
        weather = WeatherData(
            city="New York",
            country="US",
            condition=WeatherCondition.RAIN,
            temperature=15.0,
            humidity=80.0,
            wind_speed=10.0,
            timestamp=datetime.utcnow()
        )
        
        bid_mult, budget_mult = mapper.get_multipliers("umbrellas", weather)
        
        assert bid_mult == 1.5
        assert budget_mult == 1.3
    
    def test_sunscreen_hot_clear(self, mapper):
        weather = WeatherData(
            city="Miami",
            country="US",
            condition=WeatherCondition.CLEAR,
            temperature=32.0,  # Within range
            humidity=60.0,
            wind_speed=5.0,
            timestamp=datetime.utcnow()
        )
        
        bid_mult, budget_mult = mapper.get_multipliers("sunscreen", weather)
        
        assert bid_mult == 1.4
        assert budget_mult == 1.2
    
    def test_no_adjustment_for_unmatched(self, mapper):
        weather = WeatherData(
            city="LA",
            country="US",
            condition=WeatherCondition.CLEAR,
            temperature=22.0,
            humidity=50.0,
            wind_speed=5.0,
            timestamp=datetime.utcnow()
        )
        
        bid_mult, budget_mult = mapper.get_multipliers("unknown_product", weather)
        
        assert bid_mult == 1.0
        assert budget_mult == 1.0


class TestWeatherBidApplier:
    """Tests for WeatherBidApplier."""
    
    @pytest.fixture
    def mock_weather_service(self):
        service = AsyncMock()
        service.get_weather = AsyncMock(return_value=WeatherData(
            city="New York",
            country="US",
            condition=WeatherCondition.RAIN,
            temperature=15.0,
            humidity=80.0,
            wind_speed=10.0,
            timestamp=datetime.utcnow()
        ))
        return service
    
    @pytest.fixture
    def applier(self, mock_weather_service):
        return WeatherBidApplier(weather_service=mock_weather_service)
    
    def test_configure_campaign(self, applier):
        applier.configure_campaign(
            campaign_id="123",
            cities=["New York", "Boston"],
            product_category="umbrellas"
        )
        
        assert "123" in applier._campaign_config
    
    @pytest.mark.asyncio
    async def test_calculate_adjustments(self, applier, mock_weather_service):
        applier.configure_campaign(
            campaign_id="123",
            cities=["New York"],
            product_category="umbrellas"
        )
        
        adjustments = await applier.calculate_adjustments()
        
        assert len(adjustments) > 0
        assert adjustments[0].bid_multiplier == 1.5
    
    @pytest.mark.asyncio
    async def test_apply_adjustments_dry_run(self, applier):
        adjustments = [
            WeatherBidAdjustment(
                campaign_id="123",
                city="New York",
                weather=WeatherCondition.RAIN,
                temperature=15.0,
                bid_multiplier=1.5,
                budget_multiplier=1.3,
                reason="Rain in New York"
            )
        ]
        
        result = await applier.apply_adjustments(adjustments, dry_run=True)
        
        assert result["applied"] == 1
        assert result["total"] == 1
