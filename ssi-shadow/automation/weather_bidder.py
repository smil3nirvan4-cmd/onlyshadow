"""
S.S.I. SHADOW - Weather-Based Bidding (C9)
==========================================

Ajusta lances de anúncios baseado em condições climáticas.
Produtos sensíveis ao clima (guarda-chuvas, protetor solar, etc.)
têm performance muito diferente dependendo do tempo.

Features:
- Integração com OpenWeatherMap API
- Regras de bid por condição climática
- Forecast para 5 dias (planejamento)
- Geo-targeting por cidade
- Histórico de correlação clima x performance

Uso:
    weather_bidder = WeatherBidder()
    
    # Obter modificador de bid
    modifier = await weather_bidder.get_bid_modifier(
        city='São Paulo',
        product_category='umbrella'
    )
    # Retorna: 1.5 (aumentar 50% se chover)
    
    # Verificar todas as cidades
    recommendations = await weather_bidder.get_all_recommendations()

Exemplo de correlação:
    - Chuva + guarda-chuva = +150% conversão
    - Sol + protetor solar = +80% conversão
    - Frio + casaco = +120% conversão

Author: SSI Shadow Team
Version: 1.0.0
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from dataclasses import dataclass, field
from enum import Enum

import httpx

# Local imports
from api.middleware.cache import cache, CacheTTL

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('weather_bidder')


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class WeatherConfig:
    """Weather service configuration."""
    
    # OpenWeatherMap API
    api_key: str = field(default_factory=lambda: os.getenv('OPENWEATHER_API_KEY', ''))
    base_url: str = "https://api.openweathermap.org/data/2.5"
    
    # Default settings
    default_country: str = "BR"
    units: str = "metric"  # celsius
    
    # Cache
    cache_ttl_minutes: int = 30
    
    # Bid modifiers
    default_modifier: float = 1.0
    max_modifier: float = 2.5
    min_modifier: float = 0.5


config = WeatherConfig()


# =============================================================================
# DATA CLASSES
# =============================================================================

class WeatherCondition(Enum):
    """Weather conditions."""
    CLEAR = "clear"
    CLOUDS = "clouds"
    RAIN = "rain"
    DRIZZLE = "drizzle"
    THUNDERSTORM = "thunderstorm"
    SNOW = "snow"
    MIST = "mist"
    FOG = "fog"
    HAZE = "haze"
    EXTREME_HEAT = "extreme_heat"
    EXTREME_COLD = "extreme_cold"
    UNKNOWN = "unknown"


class ProductCategory(Enum):
    """Product categories affected by weather."""
    UMBRELLA = "umbrella"
    RAINCOAT = "raincoat"
    SUNSCREEN = "sunscreen"
    SUNGLASSES = "sunglasses"
    WINTER_COAT = "winter_coat"
    SWEATER = "sweater"
    SHORTS = "shorts"
    SANDALS = "sandals"
    BOOTS = "boots"
    AC_UNIT = "ac_unit"
    HEATER = "heater"
    HOT_BEVERAGE = "hot_beverage"
    COLD_BEVERAGE = "cold_beverage"
    ICE_CREAM = "ice_cream"
    SOUP = "soup"
    OUTDOOR_FURNITURE = "outdoor_furniture"
    INDOOR_GAMES = "indoor_games"
    FITNESS_INDOOR = "fitness_indoor"
    FITNESS_OUTDOOR = "fitness_outdoor"


@dataclass
class WeatherData:
    """Current weather data."""
    city: str
    country: str
    condition: WeatherCondition
    condition_description: str
    temperature: float  # Celsius
    feels_like: float
    humidity: int  # Percentage
    wind_speed: float  # m/s
    clouds: int  # Percentage
    rain_1h: float = 0  # mm
    snow_1h: float = 0  # mm
    visibility: int = 10000  # meters
    timestamp: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def is_rainy(self) -> bool:
        return self.condition in [
            WeatherCondition.RAIN,
            WeatherCondition.DRIZZLE,
            WeatherCondition.THUNDERSTORM
        ]
    
    @property
    def is_hot(self) -> bool:
        return self.temperature >= 30 or self.feels_like >= 32
    
    @property
    def is_cold(self) -> bool:
        return self.temperature <= 15 or self.feels_like <= 12
    
    @property
    def is_sunny(self) -> bool:
        return self.condition == WeatherCondition.CLEAR and self.clouds < 30
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'city': self.city,
            'country': self.country,
            'condition': self.condition.value,
            'description': self.condition_description,
            'temperature': self.temperature,
            'feels_like': self.feels_like,
            'humidity': self.humidity,
            'is_rainy': self.is_rainy,
            'is_hot': self.is_hot,
            'is_cold': self.is_cold,
            'is_sunny': self.is_sunny,
            'timestamp': self.timestamp.isoformat(),
        }


@dataclass
class BidRecommendation:
    """Bid adjustment recommendation."""
    city: str
    product_category: str
    weather: WeatherData
    modifier: float  # 1.0 = no change, 1.5 = +50%, 0.5 = -50%
    reasoning: str
    confidence: float  # 0-1
    valid_until: datetime
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'city': self.city,
            'product_category': self.product_category,
            'weather_condition': self.weather.condition.value,
            'temperature': self.weather.temperature,
            'modifier': self.modifier,
            'modifier_percent': f"{(self.modifier - 1) * 100:+.0f}%",
            'reasoning': self.reasoning,
            'confidence': self.confidence,
            'valid_until': self.valid_until.isoformat(),
        }


# =============================================================================
# WEATHER RULES
# =============================================================================

# Bid modifier rules: (condition, product_category) -> (modifier, confidence, reasoning)
WEATHER_RULES: Dict[Tuple[str, str], Tuple[float, float, str]] = {
    # Rain products
    ("rain", "umbrella"): (2.0, 0.9, "Chuva aumenta demanda por guarda-chuvas"),
    ("rain", "raincoat"): (1.8, 0.85, "Chuva aumenta demanda por capas de chuva"),
    ("rain", "boots"): (1.5, 0.7, "Chuva aumenta demanda por botas"),
    ("rain", "indoor_games"): (1.3, 0.6, "Pessoas ficam em casa na chuva"),
    ("rain", "outdoor_furniture"): (0.5, 0.8, "Chuva reduz interesse em móveis externos"),
    ("rain", "fitness_outdoor"): (0.6, 0.7, "Chuva reduz exercícios ao ar livre"),
    
    ("thunderstorm", "umbrella"): (2.2, 0.95, "Tempestade forte aumenta urgência"),
    ("thunderstorm", "raincoat"): (2.0, 0.9, "Tempestade aumenta demanda"),
    
    ("drizzle", "umbrella"): (1.5, 0.7, "Garoa moderada aumenta demanda"),
    
    # Sun/heat products
    ("clear", "sunscreen"): (1.8, 0.85, "Sol forte aumenta demanda por protetor"),
    ("clear", "sunglasses"): (1.6, 0.8, "Sol aumenta demanda por óculos"),
    ("clear", "shorts"): (1.4, 0.7, "Sol aumenta demanda por roupas leves"),
    ("clear", "sandals"): (1.4, 0.7, "Sol aumenta demanda por sandálias"),
    ("clear", "outdoor_furniture"): (1.5, 0.75, "Sol aumenta interesse em área externa"),
    ("clear", "fitness_outdoor"): (1.4, 0.7, "Sol incentiva exercícios ao ar livre"),
    ("clear", "umbrella"): (0.6, 0.8, "Sol reduz demanda por guarda-chuvas"),
    
    ("extreme_heat", "ac_unit"): (2.5, 0.95, "Calor extremo dispara demanda por AC"),
    ("extreme_heat", "cold_beverage"): (1.8, 0.85, "Calor aumenta demanda por bebidas geladas"),
    ("extreme_heat", "ice_cream"): (2.0, 0.9, "Calor aumenta demanda por sorvete"),
    ("extreme_heat", "sunscreen"): (2.0, 0.9, "Calor extremo aumenta proteção solar"),
    ("extreme_heat", "hot_beverage"): (0.4, 0.85, "Calor reduz bebidas quentes"),
    ("extreme_heat", "soup"): (0.3, 0.9, "Calor extremo reduz demanda por sopas"),
    
    # Cold products
    ("extreme_cold", "winter_coat"): (2.2, 0.9, "Frio extremo aumenta demanda por casacos"),
    ("extreme_cold", "sweater"): (1.8, 0.85, "Frio aumenta demanda por blusas"),
    ("extreme_cold", "heater"): (2.5, 0.95, "Frio extremo dispara demanda por aquecedores"),
    ("extreme_cold", "hot_beverage"): (1.8, 0.85, "Frio aumenta bebidas quentes"),
    ("extreme_cold", "soup"): (1.7, 0.8, "Frio aumenta demanda por sopas"),
    ("extreme_cold", "ice_cream"): (0.5, 0.8, "Frio reduz demanda por sorvete"),
    ("extreme_cold", "sandals"): (0.4, 0.85, "Frio reduz demanda por sandálias"),
    
    # Cloudy - neutral mostly
    ("clouds", "fitness_indoor"): (1.2, 0.5, "Nublado pode incentivar academia"),
}

# Temperature-based rules (when no specific condition matches)
TEMPERATURE_RULES: Dict[str, List[Tuple[float, float, float, str]]] = {
    # (min_temp, max_temp, modifier, reasoning)
    "sunscreen": [(25, 100, 1.5, "Temperatura alta aumenta uso de protetor")],
    "ice_cream": [(28, 100, 1.6, "Temperatura alta aumenta sorvete")],
    "hot_beverage": [(-100, 18, 1.4, "Temperatura baixa aumenta bebidas quentes")],
    "cold_beverage": [(25, 100, 1.4, "Temperatura alta aumenta bebidas geladas")],
    "ac_unit": [(28, 100, 1.8, "Temperatura alta aumenta AC")],
    "heater": [(-100, 15, 1.6, "Temperatura baixa aumenta aquecedores")],
}


# =============================================================================
# WEATHER SERVICE
# =============================================================================

class WeatherService:
    """
    OpenWeatherMap API client.
    """
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or config.api_key
        self.base_url = config.base_url
        self.client = httpx.AsyncClient(timeout=10.0)
    
    async def close(self):
        await self.client.aclose()
    
    def _map_condition(self, weather_id: int, temp: float) -> WeatherCondition:
        """Map OpenWeatherMap condition ID to our enum."""
        # Check extreme temperatures first
        if temp >= 35:
            return WeatherCondition.EXTREME_HEAT
        if temp <= 5:
            return WeatherCondition.EXTREME_COLD
        
        # Map weather ID ranges
        if 200 <= weather_id < 300:
            return WeatherCondition.THUNDERSTORM
        elif 300 <= weather_id < 400:
            return WeatherCondition.DRIZZLE
        elif 500 <= weather_id < 600:
            return WeatherCondition.RAIN
        elif 600 <= weather_id < 700:
            return WeatherCondition.SNOW
        elif weather_id == 701:
            return WeatherCondition.MIST
        elif weather_id == 741:
            return WeatherCondition.FOG
        elif weather_id == 721:
            return WeatherCondition.HAZE
        elif 801 <= weather_id < 900:
            return WeatherCondition.CLOUDS
        elif weather_id == 800:
            return WeatherCondition.CLEAR
        
        return WeatherCondition.UNKNOWN
    
    async def get_current_weather(self, city: str, country: str = None) -> Optional[WeatherData]:
        """
        Get current weather for a city.
        
        Args:
            city: City name
            country: Country code (e.g., 'BR')
            
        Returns:
            WeatherData or None if failed
        """
        if not self.api_key:
            logger.error("OpenWeatherMap API key not configured")
            return None
        
        country = country or config.default_country
        
        try:
            response = await self.client.get(
                f"{self.base_url}/weather",
                params={
                    'q': f"{city},{country}",
                    'appid': self.api_key,
                    'units': config.units,
                    'lang': 'pt_br',
                }
            )
            
            if response.status_code != 200:
                logger.error(f"Weather API error: {response.status_code}")
                return None
            
            data = response.json()
            
            weather = data.get('weather', [{}])[0]
            main = data.get('main', {})
            wind = data.get('wind', {})
            clouds = data.get('clouds', {})
            rain = data.get('rain', {})
            snow = data.get('snow', {})
            
            temp = main.get('temp', 20)
            
            return WeatherData(
                city=city,
                country=country,
                condition=self._map_condition(weather.get('id', 0), temp),
                condition_description=weather.get('description', ''),
                temperature=temp,
                feels_like=main.get('feels_like', temp),
                humidity=main.get('humidity', 0),
                wind_speed=wind.get('speed', 0),
                clouds=clouds.get('all', 0),
                rain_1h=rain.get('1h', 0),
                snow_1h=snow.get('1h', 0),
                visibility=data.get('visibility', 10000),
            )
            
        except Exception as e:
            logger.error(f"Error fetching weather for {city}: {e}")
            return None
    
    async def get_forecast(
        self,
        city: str,
        country: str = None,
        days: int = 5
    ) -> List[WeatherData]:
        """
        Get weather forecast.
        
        Args:
            city: City name
            country: Country code
            days: Number of days (max 5 for free tier)
            
        Returns:
            List of WeatherData for each 3-hour interval
        """
        if not self.api_key:
            return []
        
        country = country or config.default_country
        
        try:
            response = await self.client.get(
                f"{self.base_url}/forecast",
                params={
                    'q': f"{city},{country}",
                    'appid': self.api_key,
                    'units': config.units,
                    'lang': 'pt_br',
                    'cnt': days * 8,  # 8 intervals per day (3-hour)
                }
            )
            
            if response.status_code != 200:
                return []
            
            data = response.json()
            forecasts = []
            
            for item in data.get('list', []):
                weather = item.get('weather', [{}])[0]
                main = item.get('main', {})
                temp = main.get('temp', 20)
                
                forecasts.append(WeatherData(
                    city=city,
                    country=country,
                    condition=self._map_condition(weather.get('id', 0), temp),
                    condition_description=weather.get('description', ''),
                    temperature=temp,
                    feels_like=main.get('feels_like', temp),
                    humidity=main.get('humidity', 0),
                    wind_speed=item.get('wind', {}).get('speed', 0),
                    clouds=item.get('clouds', {}).get('all', 0),
                    rain_1h=item.get('rain', {}).get('3h', 0) / 3,
                    timestamp=datetime.fromtimestamp(item.get('dt', 0)),
                ))
            
            return forecasts
            
        except Exception as e:
            logger.error(f"Error fetching forecast for {city}: {e}")
            return []


# =============================================================================
# WEATHER BIDDER
# =============================================================================

class WeatherBidder:
    """
    Main weather-based bidding engine.
    """
    
    def __init__(self, api_key: str = None):
        self.weather_service = WeatherService(api_key)
        self.cache: Dict[str, Tuple[WeatherData, datetime]] = {}
    
    async def close(self):
        await self.weather_service.close()
    
    async def get_weather(self, city: str, country: str = None) -> Optional[WeatherData]:
        """Get weather with caching."""
        cache_key = f"{city}:{country or config.default_country}"
        
        # Check cache
        if cache_key in self.cache:
            data, cached_at = self.cache[cache_key]
            if datetime.utcnow() - cached_at < timedelta(minutes=config.cache_ttl_minutes):
                return data
        
        # Fetch new data
        data = await self.weather_service.get_current_weather(city, country)
        
        if data:
            self.cache[cache_key] = (data, datetime.utcnow())
        
        return data
    
    def _calculate_modifier(
        self,
        weather: WeatherData,
        product_category: str
    ) -> Tuple[float, float, str]:
        """
        Calculate bid modifier for weather + product combination.
        
        Returns:
            Tuple of (modifier, confidence, reasoning)
        """
        condition = weather.condition.value
        
        # Check specific rules first
        rule_key = (condition, product_category)
        if rule_key in WEATHER_RULES:
            return WEATHER_RULES[rule_key]
        
        # Check temperature-based rules
        if product_category in TEMPERATURE_RULES:
            for min_temp, max_temp, modifier, reasoning in TEMPERATURE_RULES[product_category]:
                if min_temp <= weather.temperature <= max_temp:
                    return modifier, 0.6, reasoning
        
        # Check composite conditions
        if weather.is_rainy and product_category in ['umbrella', 'raincoat', 'boots']:
            return 1.5, 0.7, "Condições de chuva detectadas"
        
        if weather.is_hot and product_category in ['ac_unit', 'cold_beverage', 'ice_cream']:
            return 1.5, 0.7, "Temperatura alta detectada"
        
        if weather.is_cold and product_category in ['heater', 'hot_beverage', 'soup']:
            return 1.5, 0.7, "Temperatura baixa detectada"
        
        if weather.is_sunny and product_category in ['sunscreen', 'sunglasses']:
            return 1.4, 0.6, "Condições ensolaradas detectadas"
        
        # Default - no adjustment
        return config.default_modifier, 0.3, "Sem correlação significativa"
    
    async def get_bid_modifier(
        self,
        city: str,
        product_category: str,
        country: str = None
    ) -> BidRecommendation:
        """
        Get bid modifier recommendation for a city and product.
        
        Args:
            city: City name
            product_category: Product category (see ProductCategory enum)
            country: Country code
            
        Returns:
            BidRecommendation with modifier and details
        """
        weather = await self.get_weather(city, country)
        
        if not weather:
            # Return neutral recommendation if weather unavailable
            return BidRecommendation(
                city=city,
                product_category=product_category,
                weather=WeatherData(
                    city=city,
                    country=country or config.default_country,
                    condition=WeatherCondition.UNKNOWN,
                    condition_description="Weather data unavailable",
                    temperature=20,
                    feels_like=20,
                    humidity=50,
                    wind_speed=0,
                    clouds=50,
                ),
                modifier=1.0,
                reasoning="Weather data unavailable - using default bid",
                confidence=0.0,
                valid_until=datetime.utcnow() + timedelta(minutes=5),
            )
        
        modifier, confidence, reasoning = self._calculate_modifier(weather, product_category)
        
        # Apply limits
        modifier = max(config.min_modifier, min(config.max_modifier, modifier))
        
        return BidRecommendation(
            city=city,
            product_category=product_category,
            weather=weather,
            modifier=modifier,
            reasoning=reasoning,
            confidence=confidence,
            valid_until=datetime.utcnow() + timedelta(minutes=config.cache_ttl_minutes),
        )
    
    async def get_recommendations_for_cities(
        self,
        cities: List[str],
        product_category: str,
        country: str = None
    ) -> List[BidRecommendation]:
        """
        Get recommendations for multiple cities.
        
        Args:
            cities: List of city names
            product_category: Product category
            country: Country code
            
        Returns:
            List of BidRecommendation
        """
        tasks = [
            self.get_bid_modifier(city, product_category, country)
            for city in cities
        ]
        
        return await asyncio.gather(*tasks)
    
    async def get_all_recommendations(
        self,
        cities: List[str],
        product_categories: List[str],
        country: str = None
    ) -> Dict[str, Dict[str, BidRecommendation]]:
        """
        Get recommendations for all city + product combinations.
        
        Returns:
            Dict[city][product_category] -> BidRecommendation
        """
        results = {}
        
        for city in cities:
            results[city] = {}
            for category in product_categories:
                rec = await self.get_bid_modifier(city, category, country)
                results[city][category] = rec
        
        return results
    
    async def get_forecast_recommendations(
        self,
        city: str,
        product_category: str,
        days: int = 5,
        country: str = None
    ) -> List[BidRecommendation]:
        """
        Get recommendations based on weather forecast.
        
        Useful for planning campaigns ahead.
        """
        forecasts = await self.weather_service.get_forecast(city, country, days)
        
        recommendations = []
        for weather in forecasts:
            modifier, confidence, reasoning = self._calculate_modifier(weather, product_category)
            modifier = max(config.min_modifier, min(config.max_modifier, modifier))
            
            recommendations.append(BidRecommendation(
                city=city,
                product_category=product_category,
                weather=weather,
                modifier=modifier,
                reasoning=reasoning,
                confidence=confidence,
                valid_until=weather.timestamp + timedelta(hours=3),
            ))
        
        return recommendations


# =============================================================================
# INTEGRATION WITH BID CONTROLLER
# =============================================================================

class WeatherBidControllerIntegration:
    """
    Integration layer between WeatherBidder and BidController.
    """
    
    def __init__(self):
        self.weather_bidder = WeatherBidder()
        
        # City mapping for campaigns (campaign_id -> city)
        self.campaign_cities: Dict[str, str] = {}
        
        # Product category mapping for campaigns
        self.campaign_categories: Dict[str, str] = {}
    
    def configure_campaign(
        self,
        campaign_id: str,
        city: str,
        product_category: str
    ):
        """Configure weather parameters for a campaign."""
        self.campaign_cities[campaign_id] = city
        self.campaign_categories[campaign_id] = product_category
    
    async def get_campaign_modifier(self, campaign_id: str) -> float:
        """Get weather-based bid modifier for a campaign."""
        city = self.campaign_cities.get(campaign_id)
        category = self.campaign_categories.get(campaign_id)
        
        if not city or not category:
            return 1.0
        
        rec = await self.weather_bidder.get_bid_modifier(city, category)
        return rec.modifier
    
    async def get_all_campaign_modifiers(self) -> Dict[str, float]:
        """Get weather modifiers for all configured campaigns."""
        modifiers = {}
        
        for campaign_id in self.campaign_cities:
            modifiers[campaign_id] = await self.get_campaign_modifier(campaign_id)
        
        return modifiers


# =============================================================================
# FASTAPI ROUTES
# =============================================================================

try:
    from fastapi import APIRouter, HTTPException, Query
    from pydantic import BaseModel
    
    weather_router = APIRouter(prefix="/api/weather", tags=["weather"])
    
    # Global bidder instance
    _bidder: Optional[WeatherBidder] = None
    
    def get_bidder() -> WeatherBidder:
        global _bidder
        if _bidder is None:
            _bidder = WeatherBidder()
        return _bidder
    
    @weather_router.get("/current/{city}")
    async def get_current_weather(
        city: str,
        country: str = Query(default="BR")
    ):
        """Get current weather for a city."""
        bidder = get_bidder()
        weather = await bidder.get_weather(city, country)
        
        if not weather:
            raise HTTPException(404, "Weather data not available")
        
        return weather.to_dict()
    
    @weather_router.get("/modifier")
    async def get_bid_modifier(
        city: str,
        product_category: str,
        country: str = Query(default="BR")
    ):
        """Get bid modifier for city and product."""
        bidder = get_bidder()
        rec = await bidder.get_bid_modifier(city, product_category, country)
        return rec.to_dict()
    
    @weather_router.post("/modifiers/batch")
    async def get_batch_modifiers(
        cities: List[str],
        product_category: str,
        country: str = "BR"
    ):
        """Get modifiers for multiple cities."""
        bidder = get_bidder()
        recs = await bidder.get_recommendations_for_cities(cities, product_category, country)
        return {'recommendations': [r.to_dict() for r in recs]}
    
    @weather_router.get("/forecast/{city}")
    async def get_forecast(
        city: str,
        product_category: str,
        days: int = Query(default=5, le=5),
        country: str = Query(default="BR")
    ):
        """Get forecast-based recommendations."""
        bidder = get_bidder()
        recs = await bidder.get_forecast_recommendations(city, product_category, days, country)
        return {'recommendations': [r.to_dict() for r in recs]}
    
    @weather_router.get("/categories")
    async def list_categories():
        """List available product categories."""
        return {'categories': [c.value for c in ProductCategory]}
    
    @weather_router.get("/conditions")
    async def list_conditions():
        """List weather conditions."""
        return {'conditions': [c.value for c in WeatherCondition]}

except ImportError:
    weather_router = None


# =============================================================================
# CLI
# =============================================================================

async def main():
    """CLI for testing."""
    bidder = WeatherBidder()
    
    # Brazilian cities
    cities = ['São Paulo', 'Rio de Janeiro', 'Brasília', 'Curitiba', 'Porto Alegre']
    
    print("🌤️ Weather-Based Bid Recommendations")
    print("=" * 60)
    
    for city in cities:
        weather = await bidder.get_weather(city)
        if weather:
            print(f"\n📍 {city}")
            print(f"   Condição: {weather.condition_description}")
            print(f"   Temperatura: {weather.temperature:.1f}°C (sensação: {weather.feels_like:.1f}°C)")
            
            # Get modifiers for some products
            for category in ['umbrella', 'sunscreen', 'ice_cream']:
                rec = await bidder.get_bid_modifier(city, category)
                modifier_str = f"{(rec.modifier - 1) * 100:+.0f}%"
                print(f"   {category}: {modifier_str} ({rec.reasoning})")
    
    await bidder.close()


if __name__ == '__main__':
    asyncio.run(main())
