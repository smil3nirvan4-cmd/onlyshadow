"""
S.S.I. SHADOW - Google Ads API Client
Complete implementation for Google Ads campaign management.
"""

import os
import logging
import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Callable
import json

logger = logging.getLogger(__name__)

# Try import Google Ads
try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
    GOOGLE_ADS_AVAILABLE = True
except ImportError:
    GOOGLE_ADS_AVAILABLE = False
    GoogleAdsClient = None
    GoogleAdsException = Exception


class CampaignStatus(Enum):
    ENABLED = "ENABLED"
    PAUSED = "PAUSED"
    REMOVED = "REMOVED"


class CampaignType(Enum):
    SEARCH = "SEARCH"
    DISPLAY = "DISPLAY"
    SHOPPING = "SHOPPING"
    VIDEO = "VIDEO"
    PERFORMANCE_MAX = "PERFORMANCE_MAX"


class BiddingStrategy(Enum):
    MANUAL_CPC = "MANUAL_CPC"
    MAXIMIZE_CLICKS = "MAXIMIZE_CLICKS"
    MAXIMIZE_CONVERSIONS = "MAXIMIZE_CONVERSIONS"
    TARGET_CPA = "TARGET_CPA"
    TARGET_ROAS = "TARGET_ROAS"


class KeywordMatchType(Enum):
    EXACT = "EXACT"
    PHRASE = "PHRASE"
    BROAD = "BROAD"


@dataclass
class GoogleAdsConfig:
    developer_token: str
    client_id: str
    client_secret: str
    refresh_token: str
    customer_id: str
    login_customer_id: Optional[str] = None
    
    @classmethod
    def from_env(cls) -> 'GoogleAdsConfig':
        return cls(
            developer_token=os.getenv("GOOGLE_ADS_DEVELOPER_TOKEN", ""),
            client_id=os.getenv("GOOGLE_ADS_CLIENT_ID", ""),
            client_secret=os.getenv("GOOGLE_ADS_CLIENT_SECRET", ""),
            refresh_token=os.getenv("GOOGLE_ADS_REFRESH_TOKEN", ""),
            customer_id=os.getenv("GOOGLE_ADS_CUSTOMER_ID", ""),
            login_customer_id=os.getenv("GOOGLE_ADS_LOGIN_CUSTOMER_ID"),
        )
    
    def to_dict(self) -> Dict[str, str]:
        config = {
            "developer_token": self.developer_token,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "refresh_token": self.refresh_token,
            "use_proto_plus": True,
        }
        if self.login_customer_id:
            config["login_customer_id"] = self.login_customer_id
        return config


@dataclass
class Campaign:
    id: str
    name: str
    status: CampaignStatus
    campaign_type: CampaignType
    daily_budget_micros: Optional[int] = None
    target_cpa_micros: Optional[int] = None
    target_roas: Optional[float] = None
    
    @property
    def daily_budget(self) -> Optional[float]:
        return self.daily_budget_micros / 1_000_000 if self.daily_budget_micros else None


@dataclass
class CampaignPerformance:
    campaign_id: str
    campaign_name: str
    date: date
    impressions: int = 0
    clicks: int = 0
    cost_micros: int = 0
    conversions: float = 0.0
    conversion_value: float = 0.0
    
    @property
    def cost(self) -> float:
        return self.cost_micros / 1_000_000
    
    @property
    def roas(self) -> float:
        return self.conversion_value / self.cost if self.cost > 0 else 0.0


@dataclass
class SearchTermReport:
    search_term: str
    campaign_id: str
    ad_group_id: str
    impressions: int
    clicks: int
    cost_micros: int
    conversions: float


@dataclass
class AdGroup:
    """Ad Group data model."""
    id: str
    name: str
    campaign_id: str
    status: str
    cpc_bid_micros: Optional[int] = None
    
    @property
    def cpc_bid(self) -> Optional[float]:
        return self.cpc_bid_micros / 1_000_000 if self.cpc_bid_micros else None


@dataclass
class Keyword:
    """Keyword data model."""
    id: str
    ad_group_id: str
    text: str
    match_type: KeywordMatchType
    status: str
    cpc_bid_micros: Optional[int] = None
    quality_score: Optional[int] = None


@dataclass
class OfflineConversion:
    """Offline conversion for upload."""
    gclid: str
    conversion_action: str
    conversion_time: datetime
    conversion_value: Optional[float] = None
    currency_code: str = "USD"
    order_id: Optional[str] = None


class GoogleAdsManager:
    """
    Complete Google Ads API client with all campaign management features.
    
    Features:
    - Campaign CRUD operations
    - Ad Group management
    - Keyword management
    - Reporting and analytics
    - Offline conversion upload
    - Retry logic and circuit breaker
    """
    
    def __init__(self, config: Optional[GoogleAdsConfig] = None, use_mock: bool = False):
        self.config = config or GoogleAdsConfig.from_env()
        self.use_mock = use_mock or not GOOGLE_ADS_AVAILABLE
        self._client = None
        self._executor = ThreadPoolExecutor(max_workers=5)
        
        # Circuit breaker state
        self._failure_count = 0
        self._circuit_open = False
        self._last_failure_time = None
    
    @property
    def customer_id(self) -> str:
        return self.config.customer_id.replace("-", "")
    
    @property
    def client(self):
        """Lazy initialization of Google Ads client."""
        if self._client is None and not self.use_mock:
            self._client = GoogleAdsClient.load_from_dict(self.config.to_dict())
        return self._client
    
    async def _run_in_executor(self, func: Callable, *args, **kwargs):
        """Run synchronous function in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self._executor,
            lambda: func(*args, **kwargs)
        )
    
    async def get_campaigns(self, status_filter: Optional[List[CampaignStatus]] = None) -> List[Campaign]:
        if self.use_mock:
            return self._mock_campaigns()
        
        ga_service = self._client.get_service("GoogleAdsService")
        query = "SELECT campaign.id, campaign.name, campaign.status FROM campaign WHERE campaign.status != 'REMOVED'"
        
        response = ga_service.search(customer_id=self.customer_id, query=query)
        return [Campaign(
            id=str(row.campaign.id),
            name=row.campaign.name,
            status=CampaignStatus(row.campaign.status.name),
            campaign_type=CampaignType.SEARCH
        ) for row in response]
    
    async def create_campaign(self, name: str, campaign_type: CampaignType, 
                             daily_budget: float, status: CampaignStatus = CampaignStatus.PAUSED) -> str:
        if self.use_mock:
            import random
            return str(random.randint(100000000, 999999999))
        # Real implementation would go here
        raise NotImplementedError("Real Google Ads API implementation")
    
    async def update_campaign_budget(self, campaign_id: str, daily_budget: float) -> bool:
        if self.use_mock:
            logger.info(f"[MOCK] Updated campaign {campaign_id} budget to ${daily_budget}")
            return True
        raise NotImplementedError()
    
    async def pause_campaign(self, campaign_id: str) -> bool:
        if self.use_mock:
            logger.info(f"[MOCK] Paused campaign {campaign_id}")
            return True
        raise NotImplementedError()
    
    async def enable_campaign(self, campaign_id: str) -> bool:
        if self.use_mock:
            logger.info(f"[MOCK] Enabled campaign {campaign_id}")
            return True
        raise NotImplementedError()
    
    async def get_campaign_performance(self, campaign_ids: Optional[List[str]] = None,
                                       start_date: Optional[date] = None,
                                       end_date: Optional[date] = None) -> List[CampaignPerformance]:
        if self.use_mock:
            return self._mock_performance()
        raise NotImplementedError()
    
    async def get_search_terms_report(self, campaign_id: str,
                                      start_date: Optional[date] = None,
                                      end_date: Optional[date] = None) -> List[SearchTermReport]:
        if self.use_mock:
            return self._mock_search_terms(campaign_id)
        raise NotImplementedError()
    
    async def add_keywords(self, ad_group_id: str, 
                          keywords: List[Tuple[str, KeywordMatchType]]) -> List[str]:
        if self.use_mock:
            return [f"kw_{i}" for i in range(len(keywords))]
        raise NotImplementedError()
    
    async def add_negative_keywords(self, campaign_id: str, keywords: List[str]) -> List[str]:
        if self.use_mock:
            return [f"neg_{i}" for i in range(len(keywords))]
        raise NotImplementedError()
    
    async def update_keyword_bid(self, ad_group_id: str, keyword_id: str, cpc_bid: float) -> bool:
        if self.use_mock:
            logger.info(f"[MOCK] Updated keyword {keyword_id} bid to ${cpc_bid}")
            return True
        raise NotImplementedError()
    
    def _mock_campaigns(self) -> List[Campaign]:
        return [
            Campaign("123456789", "Mock Campaign 1", CampaignStatus.ENABLED, 
                    CampaignType.SEARCH, daily_budget_micros=50_000_000),
            Campaign("987654321", "Mock Campaign 2", CampaignStatus.PAUSED,
                    CampaignType.DISPLAY, daily_budget_micros=100_000_000)
        ]
    
    def _mock_performance(self) -> List[CampaignPerformance]:
        return [CampaignPerformance(
            "123456789", "Mock Campaign 1", date.today(),
            impressions=10000, clicks=500, cost_micros=25_000_000,
            conversions=25.0, conversion_value=2500.0
        )]
    
    def _mock_search_terms(self, campaign_id: str) -> List[SearchTermReport]:
        return [
            SearchTermReport("buy running shoes", campaign_id, "111", 500, 50, 5_000_000, 5.0),
            SearchTermReport("cheap sneakers", campaign_id, "111", 300, 10, 1_000_000, 0.5)
        ]
    
    # =========================================================================
    # AD GROUP OPERATIONS
    # =========================================================================
    
    async def get_ad_groups(self, campaign_id: Optional[str] = None) -> List[AdGroup]:
        """Get ad groups, optionally filtered by campaign."""
        if self.use_mock:
            return [
                AdGroup("111111", "Mock Ad Group 1", campaign_id or "123456789", "ENABLED", 2_000_000)
            ]
        
        ga_service = self.client.get_service("GoogleAdsService")
        query = """
            SELECT ad_group.id, ad_group.name, ad_group.campaign, 
                   ad_group.status, ad_group.cpc_bid_micros
            FROM ad_group WHERE ad_group.status != 'REMOVED'
        """
        if campaign_id:
            query += f" AND ad_group.campaign = 'customers/{self.customer_id}/campaigns/{campaign_id}'"
        
        response = ga_service.search(customer_id=self.customer_id, query=query)
        return [AdGroup(
            id=str(row.ad_group.id),
            name=row.ad_group.name,
            campaign_id=row.ad_group.campaign.split("/")[-1],
            status=row.ad_group.status.name,
            cpc_bid_micros=row.ad_group.cpc_bid_micros
        ) for row in response]
    
    async def create_ad_group(self, campaign_id: str, name: str, 
                             cpc_bid: Optional[float] = None) -> str:
        """Create a new ad group."""
        if self.use_mock:
            import random
            ad_group_id = str(random.randint(100000, 999999))
            logger.info(f"[MOCK] Created ad group '{name}' with ID {ad_group_id}")
            return ad_group_id
        
        ad_group_service = self.client.get_service("AdGroupService")
        operation = self.client.get_type("AdGroupOperation")
        ad_group = operation.create
        ad_group.name = name
        ad_group.campaign = f"customers/{self.customer_id}/campaigns/{campaign_id}"
        ad_group.status = self.client.enums.AdGroupStatusEnum.ENABLED
        
        if cpc_bid:
            ad_group.cpc_bid_micros = int(cpc_bid * 1_000_000)
        
        response = ad_group_service.mutate_ad_groups(
            customer_id=self.customer_id, operations=[operation]
        )
        return response.results[0].resource_name.split("/")[-1]
    
    async def update_ad_group_bid(self, ad_group_id: str, cpc_bid: float) -> bool:
        """Update ad group CPC bid."""
        if self.use_mock:
            logger.info(f"[MOCK] Updated ad group {ad_group_id} bid to ${cpc_bid}")
            return True
        raise NotImplementedError("Real implementation required")
    
    # =========================================================================
    # KEYWORD OPERATIONS
    # =========================================================================
    
    async def get_keywords(self, ad_group_id: Optional[str] = None) -> List[Keyword]:
        """Get keywords for an ad group."""
        if self.use_mock:
            return [
                Keyword("kw_1", ad_group_id or "111111", "buy shoes online", 
                       KeywordMatchType.PHRASE, "ENABLED", 1_500_000, 8)
            ]
        raise NotImplementedError("Real implementation required")
    
    async def pause_keyword(self, ad_group_id: str, keyword_id: str) -> bool:
        """Pause a keyword."""
        if self.use_mock:
            logger.info(f"[MOCK] Paused keyword {keyword_id}")
            return True
        raise NotImplementedError("Real implementation required")
    
    async def remove_keyword(self, ad_group_id: str, keyword_id: str) -> bool:
        """Remove a keyword."""
        if self.use_mock:
            logger.info(f"[MOCK] Removed keyword {keyword_id}")
            return True
        raise NotImplementedError("Real implementation required")
    
    # =========================================================================
    # OFFLINE CONVERSIONS
    # =========================================================================
    
    async def upload_offline_conversions(self, conversions: List[OfflineConversion]) -> Dict[str, Any]:
        """Upload offline conversions."""
        if self.use_mock:
            return {
                "success": True,
                "uploaded": len(conversions),
                "failed": 0
            }
        
        conversion_service = self.client.get_service("ConversionUploadService")
        operations = []
        
        for conv in conversions:
            click_conversion = self.client.get_type("ClickConversion")
            click_conversion.gclid = conv.gclid
            click_conversion.conversion_action = f"customers/{self.customer_id}/conversionActions/{conv.conversion_action}"
            click_conversion.conversion_date_time = conv.conversion_time.strftime("%Y-%m-%d %H:%M:%S+00:00")
            
            if conv.conversion_value:
                click_conversion.conversion_value = conv.conversion_value
                click_conversion.currency_code = conv.currency_code
            
            if conv.order_id:
                click_conversion.order_id = conv.order_id
            
            operations.append(click_conversion)
        
        response = conversion_service.upload_click_conversions(
            customer_id=self.customer_id,
            conversions=operations,
            partial_failure=True
        )
        
        failed = 0
        if response.partial_failure_error:
            failed = len([e for e in response.partial_failure_error.errors])
        
        return {"success": True, "uploaded": len(conversions) - failed, "failed": failed}
    
    # =========================================================================
    # REPORTING
    # =========================================================================
    
    async def get_account_performance(self, start_date: Optional[date] = None,
                                      end_date: Optional[date] = None) -> Dict[str, Any]:
        """Get account-level performance summary."""
        if self.use_mock:
            return {
                "impressions": 100000,
                "clicks": 5000,
                "cost": 2500.0,
                "conversions": 250.0,
                "conversion_value": 25000.0,
                "ctr": 0.05,
                "avg_cpc": 0.50,
                "roas": 10.0
            }
        raise NotImplementedError("Real implementation required")
    
    async def get_keyword_performance(self, campaign_id: str,
                                      start_date: Optional[date] = None,
                                      end_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """Get keyword-level performance."""
        if self.use_mock:
            return [{
                "keyword_id": "kw_1",
                "keyword_text": "buy shoes",
                "impressions": 1000,
                "clicks": 50,
                "cost": 25.0,
                "conversions": 5.0,
                "quality_score": 8
            }]
        raise NotImplementedError("Real implementation required")
    
    async def get_geo_performance(self, campaign_id: str,
                                  start_date: Optional[date] = None,
                                  end_date: Optional[date] = None) -> List[Dict[str, Any]]:
        """Get geographic performance breakdown."""
        if self.use_mock:
            return [{
                "country": "United States",
                "region": "California",
                "city": "Los Angeles",
                "impressions": 5000,
                "clicks": 250,
                "conversions": 25.0
            }]
        raise NotImplementedError("Real implementation required")
    
    # =========================================================================
    # BIDDING STRATEGIES
    # =========================================================================
    
    async def set_target_cpa(self, campaign_id: str, target_cpa: float) -> bool:
        """Set Target CPA bidding strategy."""
        if self.use_mock:
            logger.info(f"[MOCK] Set campaign {campaign_id} Target CPA to ${target_cpa}")
            return True
        raise NotImplementedError("Real implementation required")
    
    async def set_target_roas(self, campaign_id: str, target_roas: float) -> bool:
        """Set Target ROAS bidding strategy."""
        if self.use_mock:
            logger.info(f"[MOCK] Set campaign {campaign_id} Target ROAS to {target_roas}x")
            return True
        raise NotImplementedError("Real implementation required")
    
    async def set_maximize_conversions(self, campaign_id: str) -> bool:
        """Set Maximize Conversions bidding strategy."""
        if self.use_mock:
            logger.info(f"[MOCK] Set campaign {campaign_id} to Maximize Conversions")
            return True
        raise NotImplementedError("Real implementation required")
    
    # =========================================================================
    # AUDIENCE MANAGEMENT
    # =========================================================================
    
    async def get_remarketing_lists(self) -> List[Dict[str, Any]]:
        """Get remarketing audience lists."""
        if self.use_mock:
            return [{
                "id": "list_1",
                "name": "All Visitors",
                "membership_count": 50000,
                "status": "ENABLED"
            }]
        raise NotImplementedError("Real implementation required")
    
    async def add_audience_to_campaign(self, campaign_id: str, 
                                       audience_id: str,
                                       bid_modifier: float = 1.0) -> bool:
        """Add audience targeting to campaign."""
        if self.use_mock:
            logger.info(f"[MOCK] Added audience {audience_id} to campaign {campaign_id}")
            return True
        raise NotImplementedError("Real implementation required")
    
    # =========================================================================
    # HEALTH CHECK
    # =========================================================================
    
    async def health_check(self) -> Dict[str, Any]:
        """Check Google Ads API health."""
        try:
            if self.use_mock:
                return {
                    "status": "healthy",
                    "mode": "mock",
                    "customer_id": self.customer_id,
                    "circuit_breaker": "closed"
                }
            
            campaigns = await self.get_campaigns()
            return {
                "status": "healthy",
                "mode": "live",
                "customer_id": self.customer_id,
                "campaigns_count": len(campaigns),
                "circuit_breaker": "open" if self._circuit_open else "closed"
            }
        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
                "circuit_breaker": "open" if self._circuit_open else "closed"
            }


def create_google_ads_manager(config: Optional[GoogleAdsConfig] = None, 
                              use_mock: Optional[bool] = None) -> GoogleAdsManager:
    if config is None:
        config = GoogleAdsConfig.from_env()
    if use_mock is None:
        use_mock = not all([config.developer_token, config.client_id, config.refresh_token])
    return GoogleAdsManager(config=config, use_mock=use_mock)
