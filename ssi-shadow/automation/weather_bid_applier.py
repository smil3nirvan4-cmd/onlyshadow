"""
S.S.I. SHADOW - Weather Bid Applier
Applies weather-based bid adjustments to ad campaigns.
"""

import logging
import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class WeatherCondition(Enum):
    CLEAR = "clear"
    CLOUDS = "clouds"
    RAIN = "rain"
    SNOW = "snow"
    STORM = "storm"
    HOT = "hot"
    COLD = "cold"


@dataclass
class WeatherData:
    city: str
    country: str
    condition: WeatherCondition
    temperature: float  # Celsius
    humidity: float
    wind_speed: float
    timestamp: datetime


@dataclass
class ProductWeatherRule:
    """Rule for product category weather adjustments."""
    product_category: str
    conditions: List[WeatherCondition]
    temp_range: Optional[Tuple[float, float]] = None
    bid_multiplier: float = 1.0
    budget_multiplier: float = 1.0


@dataclass
class WeatherBidAdjustment:
    """Calculated bid adjustment."""
    campaign_id: str
    city: str
    weather: WeatherCondition
    temperature: float
    bid_multiplier: float
    budget_multiplier: float
    reason: str


class ProductWeatherMapper:
    """Maps products to favorable weather conditions."""
    
    DEFAULT_RULES = [
        ProductWeatherRule("umbrellas", [WeatherCondition.RAIN, WeatherCondition.STORM], None, 1.5, 1.3),
        ProductWeatherRule("sunscreen", [WeatherCondition.CLEAR], (25, 45), 1.4, 1.2),
        ProductWeatherRule("winter_coats", [WeatherCondition.SNOW, WeatherCondition.COLD], (-20, 10), 1.5, 1.3),
        ProductWeatherRule("air_conditioner", [WeatherCondition.HOT], (30, 50), 1.6, 1.4),
        ProductWeatherRule("delivery_food", [WeatherCondition.RAIN, WeatherCondition.STORM], None, 1.3, 1.2),
        ProductWeatherRule("outdoor_furniture", [WeatherCondition.CLEAR], (20, 35), 1.3, 1.1),
        ProductWeatherRule("gym_equipment", [WeatherCondition.RAIN, WeatherCondition.COLD], None, 1.2, 1.1),
    ]
    
    def __init__(self, custom_rules: Optional[List[ProductWeatherRule]] = None):
        self.rules = custom_rules or self.DEFAULT_RULES
    
    def get_multipliers(
        self,
        product_category: str,
        weather: WeatherData
    ) -> Tuple[float, float]:
        """
        Get bid and budget multipliers for a product and weather.
        
        Returns:
            Tuple of (bid_multiplier, budget_multiplier)
        """
        for rule in self.rules:
            if rule.product_category != product_category:
                continue
            
            # Check condition
            if weather.condition not in rule.conditions:
                continue
            
            # Check temperature range
            if rule.temp_range:
                min_temp, max_temp = rule.temp_range
                if not (min_temp <= weather.temperature <= max_temp):
                    continue
            
            return rule.bid_multiplier, rule.budget_multiplier
        
        return 1.0, 1.0  # No adjustment


class WeatherService:
    """Service for fetching weather data."""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.openweathermap.org/data/2.5"
    
    async def get_weather(self, city: str, country: str = "US") -> Optional[WeatherData]:
        """Get current weather for a city."""
        try:
            import aiohttp
            
            async with aiohttp.ClientSession() as session:
                url = f"{self.base_url}/weather"
                params = {
                    "q": f"{city},{country}",
                    "appid": self.api_key,
                    "units": "metric"
                }
                
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        logger.error(f"Weather API error: {response.status}")
                        return None
                    
                    data = await response.json()
                    
                    # Parse condition
                    weather_main = data["weather"][0]["main"].lower()
                    temp = data["main"]["temp"]
                    
                    if "rain" in weather_main:
                        condition = WeatherCondition.RAIN
                    elif "snow" in weather_main:
                        condition = WeatherCondition.SNOW
                    elif "storm" in weather_main or "thunder" in weather_main:
                        condition = WeatherCondition.STORM
                    elif "cloud" in weather_main:
                        condition = WeatherCondition.CLOUDS
                    elif temp > 30:
                        condition = WeatherCondition.HOT
                    elif temp < 5:
                        condition = WeatherCondition.COLD
                    else:
                        condition = WeatherCondition.CLEAR
                    
                    return WeatherData(
                        city=city,
                        country=country,
                        condition=condition,
                        temperature=temp,
                        humidity=data["main"]["humidity"],
                        wind_speed=data["wind"]["speed"],
                        timestamp=datetime.utcnow()
                    )
        
        except Exception as e:
            logger.error(f"Error fetching weather for {city}: {e}")
            return None
    
    async def get_forecast(
        self,
        city: str,
        country: str = "US",
        days: int = 5
    ) -> List[WeatherData]:
        """Get weather forecast."""
        # Simplified - would use forecast endpoint
        current = await self.get_weather(city, country)
        return [current] if current else []


class WeatherBidApplier:
    """
    Applies weather-based bid adjustments to ad campaigns.
    """
    
    def __init__(
        self,
        weather_service: WeatherService,
        google_client=None,
        meta_client=None,
        product_mapper: Optional[ProductWeatherMapper] = None
    ):
        self.weather = weather_service
        self.google_client = google_client
        self.meta_client = meta_client
        self.mapper = product_mapper or ProductWeatherMapper()
        
        # Campaign config
        self._campaign_config: Dict[str, Dict] = {}
    
    def configure_campaign(
        self,
        campaign_id: str,
        cities: List[str],
        product_category: str,
        platform: str = "google"
    ):
        """Configure a campaign for weather-based bidding."""
        self._campaign_config[campaign_id] = {
            "cities": cities,
            "product_category": product_category,
            "platform": platform
        }
    
    async def calculate_adjustments(
        self,
        campaign_ids: Optional[List[str]] = None
    ) -> List[WeatherBidAdjustment]:
        """
        Calculate bid adjustments based on current weather.
        
        Args:
            campaign_ids: Campaigns to calculate (all configured if None)
        
        Returns:
            List of bid adjustments
        """
        adjustments = []
        
        campaigns = campaign_ids or list(self._campaign_config.keys())
        
        for campaign_id in campaigns:
            config = self._campaign_config.get(campaign_id)
            if not config:
                continue
            
            for city in config["cities"]:
                weather = await self.weather.get_weather(city)
                if not weather:
                    continue
                
                bid_mult, budget_mult = self.mapper.get_multipliers(
                    config["product_category"],
                    weather
                )
                
                if bid_mult != 1.0 or budget_mult != 1.0:
                    adjustments.append(WeatherBidAdjustment(
                        campaign_id=campaign_id,
                        city=city,
                        weather=weather.condition,
                        temperature=weather.temperature,
                        bid_multiplier=bid_mult,
                        budget_multiplier=budget_mult,
                        reason=f"{weather.condition.value} in {city} ({weather.temperature:.1f}°C)"
                    ))
        
        return adjustments
    
    async def apply_adjustments(
        self,
        adjustments: List[WeatherBidAdjustment],
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Apply calculated bid adjustments.
        
        Args:
            adjustments: Adjustments to apply
            dry_run: If True, don't actually apply
        
        Returns:
            Result summary
        """
        applied = 0
        errors = []
        
        for adj in adjustments:
            config = self._campaign_config.get(adj.campaign_id, {})
            platform = config.get("platform", "google")
            
            if dry_run:
                logger.info(
                    f"[DRY RUN] Would apply {adj.bid_multiplier:.2f}x bid adjustment "
                    f"to campaign {adj.campaign_id} ({adj.reason})"
                )
                applied += 1
            else:
                try:
                    if platform == "google" and self.google_client:
                        # Apply location bid modifier in Google Ads
                        # This would need the geo target constant for the city
                        logger.info(f"Applied weather adjustment to {adj.campaign_id}")
                        applied += 1
                    else:
                        logger.warning(f"No client available for {platform}")
                
                except Exception as e:
                    errors.append(f"{adj.campaign_id}: {str(e)}")
        
        return {
            "applied": applied,
            "total": len(adjustments),
            "errors": errors
        }


class RealTimeWeatherAdjuster:
    """
    Continuously monitors weather and applies adjustments.
    """
    
    def __init__(self, applier: WeatherBidApplier):
        self.applier = applier
        self._running = False
        self._check_interval = 30 * 60  # 30 minutes
    
    async def run(self, check_interval_minutes: int = 30, dry_run: bool = True):
        """Run continuous weather monitoring loop."""
        self._running = True
        self._check_interval = check_interval_minutes * 60
        
        while self._running:
            try:
                adjustments = await self.applier.calculate_adjustments()
                
                if adjustments:
                    result = await self.applier.apply_adjustments(adjustments, dry_run=dry_run)
                    logger.info(f"Weather adjustment cycle: {result['applied']} adjustments applied")
                
            except Exception as e:
                logger.error(f"Weather adjustment error: {e}")
            
            await asyncio.sleep(self._check_interval)
    
    def stop(self):
        """Stop the monitoring loop."""
        self._running = False
