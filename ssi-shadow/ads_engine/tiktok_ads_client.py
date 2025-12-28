"""
S.S.I. SHADOW - TikTok Ads API Client (Real Implementation)
============================================================
Production-ready client for TikTok Marketing API

API Documentation: https://business-api.tiktok.com/portal/docs

Prerequisites:
    pip install httpx aiohttp

Environment Variables:
    TIKTOK_ACCESS_TOKEN - Long-lived Access Token
    TIKTOK_ADVERTISER_ID - Advertiser ID
    TIKTOK_APP_ID - TikTok App ID (optional)
    TIKTOK_APP_SECRET - TikTok App Secret (optional)

Author: SSI Shadow Team
Version: 1.0.0
"""

import os
import logging
import asyncio
import time
import json
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool for sync operations
_executor = ThreadPoolExecutor(max_workers=4)

# Try to import httpx for async HTTP
try:
    import httpx
    HTTPX_AVAILABLE = True
except ImportError:
    HTTPX_AVAILABLE = False
    logger.warning("httpx not installed. Run: pip install httpx")


# =============================================================================
# ENUMS
# =============================================================================

class CampaignObjective(Enum):
    """TikTok Campaign Objectives"""
    REACH = "REACH"
    TRAFFIC = "TRAFFIC"
    VIDEO_VIEWS = "VIDEO_VIEWS"
    COMMUNITY_INTERACTION = "COMMUNITY_INTERACTION"
    APP_PROMOTION = "APP_PROMOTION"
    LEAD_GENERATION = "LEAD_GENERATION"
    WEBSITE_CONVERSIONS = "WEBSITE_CONVERSIONS"
    PRODUCT_SALES = "PRODUCT_SALES"
    SHOP_PURCHASES = "SHOP_PURCHASES"


class CampaignStatus(Enum):
    """Campaign/AdGroup/Ad Status"""
    ENABLE = "ENABLE"
    DISABLE = "DISABLE"
    DELETE = "DELETE"


class OptimizationGoal(Enum):
    """Optimization Goals"""
    SHOW = "SHOW"              # Impressions
    CLICK = "CLICK"            # Clicks
    REACH = "REACH"            # Reach
    VIDEO_VIEW = "VIDEO_VIEW"  # Video Views
    ENGAGED_VIEW = "ENGAGED_VIEW"  # 6s+ views
    COMPLETE_PAYMENT = "COMPLETE_PAYMENT"  # Purchases
    VALUE = "VALUE"            # ROAS
    INSTALL = "INSTALL"        # App Installs
    IN_APP_EVENT = "IN_APP_EVENT"
    LEAD = "LEAD"              # Lead Gen
    ADD_TO_CART = "ADD_TO_CART"


class BidStrategy(Enum):
    """Bid Strategies"""
    BID_TYPE_NO_BID = "BID_TYPE_NO_BID"    # Lowest Cost
    BID_TYPE_CUSTOM = "BID_TYPE_CUSTOM"    # Cost Cap
    BID_TYPE_FIXED = "BID_TYPE_FIXED"      # Maximum Bid


class BudgetMode(Enum):
    """Budget Mode"""
    BUDGET_MODE_DAY = "BUDGET_MODE_DAY"        # Daily Budget
    BUDGET_MODE_TOTAL = "BUDGET_MODE_TOTAL"    # Lifetime Budget
    BUDGET_MODE_INFINITE = "BUDGET_MODE_INFINITE"  # No Budget Limit


class AdFormat(Enum):
    """Ad Formats"""
    SINGLE_VIDEO = "SINGLE_VIDEO"
    SINGLE_IMAGE = "SINGLE_IMAGE"
    CAROUSEL = "CAROUSEL"
    SPARK_AD = "SPARK_AD"
    COLLECTION = "COLLECTION"
    PLAYABLE = "PLAYABLE"


class Placement(Enum):
    """Ad Placements"""
    TIKTOK = "PLACEMENT_TIKTOK"
    PANGLE = "PLACEMENT_PANGLE"
    GLOBAL_APP_BUNDLE = "PLACEMENT_GLOBAL_APP_BUNDLE"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Campaign:
    """Campaign data model"""
    campaign_id: str
    campaign_name: str
    objective_type: str
    status: str = "ENABLE"
    budget_mode: str = "BUDGET_MODE_DAY"
    budget: float = 0.0
    create_time: Optional[str] = None
    modify_time: Optional[str] = None
    is_smart_campaign: bool = False


@dataclass
class AdGroup:
    """Ad Group data model"""
    adgroup_id: str
    adgroup_name: str
    campaign_id: str
    status: str = "ENABLE"
    optimization_goal: str = "CLICK"
    bid_type: str = "BID_TYPE_NO_BID"
    budget_mode: str = "BUDGET_MODE_DAY"
    budget: float = 0.0
    bid_price: Optional[float] = None
    targeting: Optional[Dict] = None
    placements: Optional[List[str]] = None
    create_time: Optional[str] = None
    modify_time: Optional[str] = None


@dataclass
class Ad:
    """Ad data model"""
    ad_id: str
    ad_name: str
    adgroup_id: str
    status: str = "ENABLE"
    ad_format: str = "SINGLE_VIDEO"
    ad_text: str = ""
    call_to_action: str = "LEARN_MORE"
    landing_page_url: Optional[str] = None
    video_id: Optional[str] = None
    image_ids: Optional[List[str]] = None
    create_time: Optional[str] = None
    modify_time: Optional[str] = None


@dataclass
class InsightsData:
    """Reporting/Insights data model"""
    date: str
    advertiser_id: str
    campaign_id: Optional[str] = None
    adgroup_id: Optional[str] = None
    ad_id: Optional[str] = None
    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    reach: int = 0
    cpm: float = 0.0
    cpc: float = 0.0
    ctr: float = 0.0
    conversions: int = 0
    conversion_rate: float = 0.0
    cost_per_conversion: float = 0.0
    video_views: int = 0
    video_watched_2s: int = 0
    video_watched_6s: int = 0
    average_video_play: float = 0.0


# =============================================================================
# API ERROR HANDLING
# =============================================================================

class TikTokAPIError(Exception):
    """TikTok API Error"""
    def __init__(self, code: int, message: str, request_id: str = None):
        self.code = code
        self.message = message
        self.request_id = request_id
        super().__init__(f"TikTok API Error {code}: {message}")


# Error codes reference
ERROR_CODES = {
    0: "OK",
    40001: "Invalid parameter",
    40002: "Missing required parameter",
    40100: "Authentication failed",
    40101: "Access token expired",
    40102: "Invalid access token",
    40104: "Permission denied",
    40105: "Advertiser not authorized",
    50000: "Internal server error",
    50001: "Rate limit exceeded",
    50002: "Service unavailable",
}


# =============================================================================
# REAL TIKTOK ADS CLIENT
# =============================================================================

class TikTokAdsClient:
    """
    Real TikTok Marketing API Client.
    
    Usage:
        client = TikTokAdsClient(
            access_token="your_access_token",
            advertiser_id="1234567890"
        )
        
        campaigns = await client.get_campaigns()
        for campaign in campaigns:
            print(f"{campaign.campaign_name}: {campaign.status}")
    """
    
    API_VERSION = "v1.3"
    BASE_URL = f"https://business-api.tiktok.com/open_api/{API_VERSION}"
    
    # Rate limiting
    MAX_REQUESTS_PER_SECOND = 10
    MAX_REQUESTS_PER_MINUTE = 600
    RETRY_DELAYS = [1, 2, 5, 10, 30]  # Seconds
    
    def __init__(
        self,
        access_token: str = None,
        advertiser_id: str = None,
        app_id: str = None,
        app_secret: str = None,
        sandbox: bool = False
    ):
        """
        Initialize TikTok Ads Client.
        
        Args:
            access_token: TikTok Marketing API access token (or TIKTOK_ACCESS_TOKEN env)
            advertiser_id: Advertiser ID (or TIKTOK_ADVERTISER_ID env)
            app_id: TikTok App ID (optional, or TIKTOK_APP_ID env)
            app_secret: TikTok App Secret (optional, or TIKTOK_APP_SECRET env)
            sandbox: Use sandbox environment
        """
        if not HTTPX_AVAILABLE:
            raise RuntimeError("httpx is required. Install with: pip install httpx")
        
        # Get credentials from params or environment
        self.access_token = access_token or os.getenv("TIKTOK_ACCESS_TOKEN")
        self.advertiser_id = advertiser_id or os.getenv("TIKTOK_ADVERTISER_ID")
        self.app_id = app_id or os.getenv("TIKTOK_APP_ID")
        self.app_secret = app_secret or os.getenv("TIKTOK_APP_SECRET")
        
        # Validate required credentials
        if not self.access_token:
            raise ValueError("TIKTOK_ACCESS_TOKEN is required")
        if not self.advertiser_id:
            raise ValueError("TIKTOK_ADVERTISER_ID is required")
        
        # Sandbox mode
        if sandbox:
            self.BASE_URL = f"https://sandbox-ads.tiktok.com/open_api/{self.API_VERSION}"
        
        # Rate limiting state
        self._request_times = []
        self._last_request_time = 0
        
        # HTTP client
        self._client = None
        
        logger.info(f"✅ TikTok Ads Client initialized for advertiser {self.advertiser_id}")
    
    # =========================================================================
    # HTTP CLIENT MANAGEMENT
    # =========================================================================
    
    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=5)
            )
        return self._client
    
    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
    
    def _get_headers(self) -> Dict[str, str]:
        """Get API request headers."""
        return {
            "Access-Token": self.access_token,
            "Content-Type": "application/json",
        }
    
    # =========================================================================
    # RATE LIMITING
    # =========================================================================
    
    async def _check_rate_limit(self):
        """Check and enforce rate limits."""
        now = time.time()
        
        # Clean old request times (older than 60 seconds)
        self._request_times = [t for t in self._request_times if now - t < 60]
        
        # Check per-minute limit
        if len(self._request_times) >= self.MAX_REQUESTS_PER_MINUTE:
            wait_time = 60 - (now - self._request_times[0])
            if wait_time > 0:
                logger.warning(f"Rate limit: waiting {wait_time:.1f}s (per-minute limit)")
                await asyncio.sleep(wait_time)
        
        # Check per-second limit
        if now - self._last_request_time < 1.0 / self.MAX_REQUESTS_PER_SECOND:
            wait_time = 1.0 / self.MAX_REQUESTS_PER_SECOND - (now - self._last_request_time)
            await asyncio.sleep(wait_time)
        
        # Record this request
        self._request_times.append(time.time())
        self._last_request_time = time.time()
    
    # =========================================================================
    # API REQUEST HANDLING
    # =========================================================================
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        params: Optional[Dict] = None,
        retry_count: int = 0
    ) -> Dict:
        """
        Make API request with error handling and retry logic.
        
        Args:
            method: HTTP method (GET, POST)
            endpoint: API endpoint (e.g., "campaign/get/")
            data: Request body for POST
            params: Query parameters for GET
            retry_count: Current retry attempt
            
        Returns:
            API response data
            
        Raises:
            TikTokAPIError: If API returns an error
        """
        await self._check_rate_limit()
        
        url = f"{self.BASE_URL}/{endpoint}"
        client = await self._get_client()
        
        try:
            if method.upper() == "GET":
                # GET requests: params in query string
                response = await client.get(
                    url,
                    params=params,
                    headers=self._get_headers()
                )
            else:
                # POST requests: data in body
                response = await client.post(
                    url,
                    json=data,
                    headers=self._get_headers()
                )
            
            result = response.json()
            
            # Check for API errors
            code = result.get("code", -1)
            message = result.get("message", "Unknown error")
            request_id = result.get("request_id", "")
            
            if code != 0:
                # Handle rate limit errors with retry
                if code == 50001 and retry_count < len(self.RETRY_DELAYS):
                    delay = self.RETRY_DELAYS[retry_count]
                    logger.warning(f"Rate limited. Retrying in {delay}s (attempt {retry_count + 1})")
                    await asyncio.sleep(delay)
                    return await self._make_request(method, endpoint, data, params, retry_count + 1)
                
                # Handle token expiration
                if code in [40101, 40102]:
                    logger.error(f"Access token error: {message}. Token may need refresh.")
                
                raise TikTokAPIError(code, message, request_id)
            
            logger.debug(f"TikTok API {method} {endpoint}: OK")
            return result.get("data", result)
            
        except httpx.TimeoutException:
            if retry_count < len(self.RETRY_DELAYS):
                delay = self.RETRY_DELAYS[retry_count]
                logger.warning(f"Request timeout. Retrying in {delay}s")
                await asyncio.sleep(delay)
                return await self._make_request(method, endpoint, data, params, retry_count + 1)
            raise TikTokAPIError(50002, "Request timeout after retries")
            
        except httpx.HTTPError as e:
            logger.error(f"HTTP error: {e}")
            raise TikTokAPIError(50000, str(e))
    
    # =========================================================================
    # CAMPAIGN MANAGEMENT
    # =========================================================================
    
    async def get_campaigns(
        self,
        campaign_ids: Optional[List[str]] = None,
        status_filter: Optional[List[str]] = None,
        objective_filter: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[Campaign]:
        """
        Get campaigns from the advertiser account.
        
        Args:
            campaign_ids: Filter by specific campaign IDs
            status_filter: Filter by status (ENABLE, DISABLE, DELETE)
            objective_filter: Filter by objective type
            page: Page number (1-based)
            page_size: Results per page (max 1000)
            
        Returns:
            List of Campaign objects
        """
        params = {
            "advertiser_id": self.advertiser_id,
            "page": page,
            "page_size": min(page_size, 1000),
        }
        
        # Build filtering
        filtering = {}
        if campaign_ids:
            filtering["campaign_ids"] = campaign_ids
        if status_filter:
            filtering["primary_status"] = status_filter[0] if len(status_filter) == 1 else None
        if objective_filter:
            filtering["objective_type"] = objective_filter
        
        if filtering:
            params["filtering"] = json.dumps(filtering)
        
        # Request fields
        params["fields"] = json.dumps([
            "campaign_id", "campaign_name", "objective_type", "status",
            "budget_mode", "budget", "create_time", "modify_time",
            "campaign_type", "is_smart_performance_campaign"
        ])
        
        result = await self._make_request("GET", "campaign/get/", params=params)
        
        campaigns = []
        for item in result.get("list", []):
            campaigns.append(Campaign(
                campaign_id=item.get("campaign_id", ""),
                campaign_name=item.get("campaign_name", ""),
                objective_type=item.get("objective_type", ""),
                status=item.get("status", ""),
                budget_mode=item.get("budget_mode", ""),
                budget=float(item.get("budget", 0)),
                create_time=item.get("create_time"),
                modify_time=item.get("modify_time"),
                is_smart_campaign=item.get("is_smart_performance_campaign", False),
            ))
        
        logger.info(f"Retrieved {len(campaigns)} campaigns (page {page})")
        return campaigns
    
    async def get_all_campaigns(
        self,
        status_filter: Optional[List[str]] = None
    ) -> List[Campaign]:
        """Get all campaigns with automatic pagination."""
        all_campaigns = []
        page = 1
        page_size = 1000
        
        while True:
            campaigns = await self.get_campaigns(
                status_filter=status_filter,
                page=page,
                page_size=page_size
            )
            all_campaigns.extend(campaigns)
            
            if len(campaigns) < page_size:
                break
            page += 1
        
        return all_campaigns
    
    async def get_campaign(self, campaign_id: str) -> Campaign:
        """Get a single campaign by ID."""
        campaigns = await self.get_campaigns(campaign_ids=[campaign_id])
        if not campaigns:
            raise TikTokAPIError(40001, f"Campaign {campaign_id} not found")
        return campaigns[0]
    
    async def create_campaign(
        self,
        name: str,
        objective: CampaignObjective,
        budget: float = 0.0,
        budget_mode: BudgetMode = BudgetMode.BUDGET_MODE_DAY,
        status: CampaignStatus = CampaignStatus.DISABLE,  # Disabled by default for safety
        is_smart_campaign: bool = False
    ) -> str:
        """
        Create a new campaign.
        
        Args:
            name: Campaign name
            objective: Campaign objective
            budget: Budget amount (in currency)
            budget_mode: Daily, lifetime, or infinite
            status: Initial status (DISABLE by default for safety)
            is_smart_campaign: Use Smart Performance Campaign
            
        Returns:
            Campaign ID
        """
        data = {
            "advertiser_id": self.advertiser_id,
            "campaign_name": name,
            "objective_type": objective.value,
            "budget_mode": budget_mode.value,
            "operation_status": status.value,
        }
        
        if budget > 0:
            data["budget"] = budget
        
        if is_smart_campaign:
            data["campaign_type"] = "SMART_PERFORMANCE_CAMPAIGN"
        
        result = await self._make_request("POST", "campaign/create/", data=data)
        campaign_id = result.get("campaign_id", "")
        
        logger.info(f"Created campaign '{name}' with ID {campaign_id}")
        return campaign_id
    
    async def update_campaign(
        self,
        campaign_id: str,
        name: Optional[str] = None,
        budget: Optional[float] = None,
        status: Optional[CampaignStatus] = None
    ) -> bool:
        """Update a campaign."""
        data = {
            "advertiser_id": self.advertiser_id,
            "campaign_id": campaign_id,
        }
        
        if name:
            data["campaign_name"] = name
        if budget is not None:
            data["budget"] = budget
        if status:
            data["operation_status"] = status.value
        
        await self._make_request("POST", "campaign/update/", data=data)
        logger.info(f"Updated campaign {campaign_id}")
        return True
    
    async def update_status(self, entity_id: str, status: str, entity_type: str = "campaign") -> bool:
        """
        Update status of an entity.
        
        Args:
            entity_id: Campaign, AdGroup, or Ad ID
            status: ENABLE, DISABLE, or DELETE
            entity_type: "campaign", "adgroup", or "ad"
        """
        endpoint_map = {
            "campaign": "campaign/status/update/",
            "adgroup": "adgroup/status/update/",
            "ad": "ad/status/update/",
        }
        
        endpoint = endpoint_map.get(entity_type, "campaign/status/update/")
        id_field = f"{entity_type}_ids" if entity_type != "ad" else "ad_ids"
        
        data = {
            "advertiser_id": self.advertiser_id,
            id_field: [entity_id],
            "operation_status": status,
        }
        
        await self._make_request("POST", endpoint, data=data)
        logger.info(f"Updated {entity_type} {entity_id} status to {status}")
        return True
    
    async def pause_campaign(self, campaign_id: str) -> bool:
        """Pause a campaign."""
        return await self.update_status(campaign_id, "DISABLE", "campaign")
    
    async def enable_campaign(self, campaign_id: str) -> bool:
        """Enable a campaign."""
        return await self.update_status(campaign_id, "ENABLE", "campaign")
    
    async def delete_campaign(self, campaign_id: str) -> bool:
        """Delete a campaign."""
        return await self.update_status(campaign_id, "DELETE", "campaign")
    
    # =========================================================================
    # AD GROUP MANAGEMENT
    # =========================================================================
    
    async def get_adgroups(
        self,
        campaign_ids: Optional[List[str]] = None,
        adgroup_ids: Optional[List[str]] = None,
        status_filter: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[AdGroup]:
        """Get ad groups."""
        params = {
            "advertiser_id": self.advertiser_id,
            "page": page,
            "page_size": min(page_size, 1000),
        }
        
        filtering = {}
        if campaign_ids:
            filtering["campaign_ids"] = campaign_ids
        if adgroup_ids:
            filtering["adgroup_ids"] = adgroup_ids
        if status_filter:
            filtering["primary_status"] = status_filter[0] if len(status_filter) == 1 else None
        
        if filtering:
            params["filtering"] = json.dumps(filtering)
        
        params["fields"] = json.dumps([
            "adgroup_id", "adgroup_name", "campaign_id", "status",
            "optimization_goal", "bid_type", "budget_mode", "budget",
            "bid_price", "targeting", "placements", "create_time", "modify_time"
        ])
        
        result = await self._make_request("GET", "adgroup/get/", params=params)
        
        adgroups = []
        for item in result.get("list", []):
            adgroups.append(AdGroup(
                adgroup_id=item.get("adgroup_id", ""),
                adgroup_name=item.get("adgroup_name", ""),
                campaign_id=item.get("campaign_id", ""),
                status=item.get("status", ""),
                optimization_goal=item.get("optimization_goal", ""),
                bid_type=item.get("bid_type", ""),
                budget_mode=item.get("budget_mode", ""),
                budget=float(item.get("budget", 0)),
                bid_price=float(item.get("bid_price", 0)) if item.get("bid_price") else None,
                targeting=item.get("targeting"),
                placements=item.get("placements"),
                create_time=item.get("create_time"),
                modify_time=item.get("modify_time"),
            ))
        
        logger.info(f"Retrieved {len(adgroups)} ad groups")
        return adgroups
    
    async def create_adgroup(
        self,
        campaign_id: str,
        name: str,
        budget: float = 0.0,
        budget_mode: BudgetMode = BudgetMode.BUDGET_MODE_DAY,
        optimization_goal: OptimizationGoal = OptimizationGoal.CLICK,
        bid_strategy: BidStrategy = BidStrategy.BID_TYPE_NO_BID,
        bid_price: Optional[float] = None,
        targeting: Optional[Dict] = None,
        placements: Optional[List[Placement]] = None,
        status: CampaignStatus = CampaignStatus.DISABLE
    ) -> str:
        """Create a new ad group."""
        data = {
            "advertiser_id": self.advertiser_id,
            "campaign_id": campaign_id,
            "adgroup_name": name,
            "budget_mode": budget_mode.value,
            "optimization_goal": optimization_goal.value,
            "bid_type": bid_strategy.value,
            "operation_status": status.value,
        }
        
        if budget > 0:
            data["budget"] = budget
        if bid_price:
            data["bid_price"] = bid_price
        if targeting:
            data["targeting"] = targeting
        if placements:
            data["placements"] = [p.value for p in placements]
        
        result = await self._make_request("POST", "adgroup/create/", data=data)
        adgroup_id = result.get("adgroup_id", "")
        
        logger.info(f"Created ad group '{name}' with ID {adgroup_id}")
        return adgroup_id
    
    async def update_adgroup(
        self,
        adgroup_id: str,
        name: Optional[str] = None,
        budget: Optional[float] = None,
        bid_price: Optional[float] = None,
        status: Optional[CampaignStatus] = None
    ) -> bool:
        """Update an ad group."""
        data = {
            "advertiser_id": self.advertiser_id,
            "adgroup_id": adgroup_id,
        }
        
        if name:
            data["adgroup_name"] = name
        if budget is not None:
            data["budget"] = budget
        if bid_price is not None:
            data["bid_price"] = bid_price
        if status:
            data["operation_status"] = status.value
        
        await self._make_request("POST", "adgroup/update/", data=data)
        logger.info(f"Updated ad group {adgroup_id}")
        return True
    
    async def update_budget(self, entity_id: str, budget: float, entity_type: str = "campaign") -> bool:
        """Update budget of a campaign or ad group."""
        if entity_type == "campaign":
            return await self.update_campaign(entity_id, budget=budget)
        else:
            return await self.update_adgroup(entity_id, budget=budget)
    
    async def update_bid(self, adgroup_id: str, bid_price: float) -> bool:
        """Update bid price of an ad group."""
        return await self.update_adgroup(adgroup_id, bid_price=bid_price)
    
    # =========================================================================
    # AD MANAGEMENT
    # =========================================================================
    
    async def get_ads(
        self,
        adgroup_ids: Optional[List[str]] = None,
        campaign_ids: Optional[List[str]] = None,
        ad_ids: Optional[List[str]] = None,
        status_filter: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[Ad]:
        """Get ads."""
        params = {
            "advertiser_id": self.advertiser_id,
            "page": page,
            "page_size": min(page_size, 1000),
        }
        
        filtering = {}
        if campaign_ids:
            filtering["campaign_ids"] = campaign_ids
        if adgroup_ids:
            filtering["adgroup_ids"] = adgroup_ids
        if ad_ids:
            filtering["ad_ids"] = ad_ids
        if status_filter:
            filtering["primary_status"] = status_filter[0] if len(status_filter) == 1 else None
        
        if filtering:
            params["filtering"] = json.dumps(filtering)
        
        params["fields"] = json.dumps([
            "ad_id", "ad_name", "adgroup_id", "status", "ad_format",
            "ad_text", "call_to_action", "landing_page_url",
            "video_id", "image_ids", "create_time", "modify_time"
        ])
        
        result = await self._make_request("GET", "ad/get/", params=params)
        
        ads = []
        for item in result.get("list", []):
            ads.append(Ad(
                ad_id=item.get("ad_id", ""),
                ad_name=item.get("ad_name", ""),
                adgroup_id=item.get("adgroup_id", ""),
                status=item.get("status", ""),
                ad_format=item.get("ad_format", ""),
                ad_text=item.get("ad_text", ""),
                call_to_action=item.get("call_to_action", ""),
                landing_page_url=item.get("landing_page_url"),
                video_id=item.get("video_id"),
                image_ids=item.get("image_ids"),
                create_time=item.get("create_time"),
                modify_time=item.get("modify_time"),
            ))
        
        logger.info(f"Retrieved {len(ads)} ads")
        return ads
    
    async def create_ad(
        self,
        adgroup_id: str,
        name: str,
        ad_format: AdFormat = AdFormat.SINGLE_VIDEO,
        ad_text: str = "",
        call_to_action: str = "LEARN_MORE",
        landing_page_url: Optional[str] = None,
        video_id: Optional[str] = None,
        image_ids: Optional[List[str]] = None,
        status: CampaignStatus = CampaignStatus.DISABLE
    ) -> str:
        """Create a new ad."""
        data = {
            "advertiser_id": self.advertiser_id,
            "adgroup_id": adgroup_id,
            "ad_name": name,
            "ad_format": ad_format.value,
            "ad_text": ad_text,
            "call_to_action": call_to_action,
            "operation_status": status.value,
        }
        
        if landing_page_url:
            data["landing_page_url"] = landing_page_url
        if video_id:
            data["video_id"] = video_id
        if image_ids:
            data["image_ids"] = image_ids
        
        result = await self._make_request("POST", "ad/create/", data=data)
        ad_id = result.get("ad_id", "")
        
        logger.info(f"Created ad '{name}' with ID {ad_id}")
        return ad_id
    
    # =========================================================================
    # REPORTING & INSIGHTS
    # =========================================================================
    
    async def get_insights(
        self,
        start_date: str,
        end_date: str,
        level: str = "AUCTION_CAMPAIGN",  # AUCTION_CAMPAIGN, AUCTION_ADGROUP, AUCTION_AD
        campaign_ids: Optional[List[str]] = None,
        adgroup_ids: Optional[List[str]] = None,
        ad_ids: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None,
        page: int = 1,
        page_size: int = 100
    ) -> List[InsightsData]:
        """
        Get performance insights/reports.
        
        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            level: Report level (AUCTION_CAMPAIGN, AUCTION_ADGROUP, AUCTION_AD)
            campaign_ids: Filter by campaigns
            adgroup_ids: Filter by ad groups
            ad_ids: Filter by ads
            metrics: List of metrics to retrieve
            page: Page number
            page_size: Results per page
        """
        default_metrics = [
            "spend", "impressions", "clicks", "reach",
            "cpm", "cpc", "ctr", "conversion", "cost_per_conversion",
            "video_views", "video_watched_2s", "video_watched_6s",
            "average_video_play", "result", "cost_per_result"
        ]
        
        data = {
            "advertiser_id": self.advertiser_id,
            "report_type": "BASIC",
            "data_level": level,
            "start_date": start_date,
            "end_date": end_date,
            "metrics": json.dumps(metrics or default_metrics),
            "page": page,
            "page_size": min(page_size, 1000),
        }
        
        # Build filtering
        filtering = {}
        if campaign_ids:
            filtering["campaign_ids"] = campaign_ids
        if adgroup_ids:
            filtering["adgroup_ids"] = adgroup_ids
        if ad_ids:
            filtering["ad_ids"] = ad_ids
        
        if filtering:
            data["filtering"] = json.dumps(filtering)
        
        # Request dimensions based on level
        if level == "AUCTION_CAMPAIGN":
            data["dimensions"] = json.dumps(["campaign_id"])
        elif level == "AUCTION_ADGROUP":
            data["dimensions"] = json.dumps(["adgroup_id"])
        elif level == "AUCTION_AD":
            data["dimensions"] = json.dumps(["ad_id"])
        
        result = await self._make_request("GET", "report/integrated/get/", params=data)
        
        insights = []
        for item in result.get("list", []):
            metrics_data = item.get("metrics", {})
            dimensions = item.get("dimensions", {})
            
            insights.append(InsightsData(
                date=f"{start_date} - {end_date}",
                advertiser_id=self.advertiser_id,
                campaign_id=dimensions.get("campaign_id"),
                adgroup_id=dimensions.get("adgroup_id"),
                ad_id=dimensions.get("ad_id"),
                impressions=int(metrics_data.get("impressions", 0)),
                clicks=int(metrics_data.get("clicks", 0)),
                spend=float(metrics_data.get("spend", 0)),
                reach=int(metrics_data.get("reach", 0)),
                cpm=float(metrics_data.get("cpm", 0)),
                cpc=float(metrics_data.get("cpc", 0)) if metrics_data.get("cpc") else 0,
                ctr=float(metrics_data.get("ctr", 0)),
                conversions=int(metrics_data.get("conversion", 0)),
                cost_per_conversion=float(metrics_data.get("cost_per_conversion", 0)) if metrics_data.get("cost_per_conversion") else 0,
                video_views=int(metrics_data.get("video_views", 0)),
                video_watched_2s=int(metrics_data.get("video_watched_2s", 0)),
                video_watched_6s=int(metrics_data.get("video_watched_6s", 0)),
                average_video_play=float(metrics_data.get("average_video_play", 0)),
            ))
        
        logger.info(f"Retrieved {len(insights)} insight records")
        return insights
    
    # =========================================================================
    # AUDIENCE MANAGEMENT
    # =========================================================================
    
    async def get_audiences(
        self,
        page: int = 1,
        page_size: int = 100
    ) -> List[Dict]:
        """Get custom audiences."""
        params = {
            "advertiser_id": self.advertiser_id,
            "page": page,
            "page_size": min(page_size, 1000),
        }
        
        result = await self._make_request("GET", "dmp/custom_audience/list/", params=params)
        
        return result.get("list", [])
    
    async def create_lookalike(
        self,
        source_audience_id: str,
        name: str,
        lookalike_type: str = "REACH",  # REACH, SIMILARITY, BALANCE
        audience_size: int = 2000000
    ) -> str:
        """Create a lookalike audience."""
        data = {
            "advertiser_id": self.advertiser_id,
            "custom_audience_name": name,
            "source_audience_id": source_audience_id,
            "lookalike_type": lookalike_type,
            "audience_size": audience_size,
        }
        
        result = await self._make_request("POST", "dmp/custom_audience/lookalike/create/", data=data)
        audience_id = result.get("custom_audience_id", "")
        
        logger.info(f"Created lookalike audience '{name}' with ID {audience_id}")
        return audience_id
    
    async def create_audience(self, config: Dict) -> str:
        """Create a custom audience from configuration."""
        data = {
            "advertiser_id": self.advertiser_id,
            "custom_audience_name": config.get("name"),
            "audience_type": config.get("type", "CUSTOM_AUDIENCE"),
        }
        data.update(config)
        
        result = await self._make_request("POST", "dmp/custom_audience/create/", data=data)
        audience_id = result.get("custom_audience_id", "")
        
        logger.info(f"Created audience '{config.get('name')}' with ID {audience_id}")
        return audience_id
    
    # =========================================================================
    # ASSET MANAGEMENT
    # =========================================================================
    
    async def upload_video(
        self,
        video_url: str = None,
        video_file: bytes = None,
        filename: str = "video.mp4"
    ) -> str:
        """
        Upload a video for use in ads.
        
        Args:
            video_url: URL of video to upload
            video_file: Video file bytes
            filename: Filename for the upload
            
        Returns:
            Video ID
        """
        if video_url:
            data = {
                "advertiser_id": self.advertiser_id,
                "video_url": video_url,
            }
            result = await self._make_request("POST", "file/video/ad/upload/", data=data)
        else:
            raise NotImplementedError("Direct file upload requires multipart form")
        
        video_id = result.get("video_id", "")
        logger.info(f"Uploaded video: {video_id}")
        return video_id
    
    async def upload_image(
        self,
        image_url: str = None,
        image_file: bytes = None,
        filename: str = "image.jpg"
    ) -> str:
        """Upload an image for use in ads."""
        if image_url:
            data = {
                "advertiser_id": self.advertiser_id,
                "image_url": image_url,
            }
            result = await self._make_request("POST", "file/image/ad/upload/", data=data)
        else:
            raise NotImplementedError("Direct file upload requires multipart form")
        
        image_id = result.get("image_id", "")
        logger.info(f"Uploaded image: {image_id}")
        return image_id
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def test_connection(self) -> Dict:
        """Test the API connection."""
        try:
            params = {
                "advertiser_id": self.advertiser_id,
                "page": 1,
                "page_size": 1,
            }
            await self._make_request("GET", "advertiser/info/", params=params)
            
            return {
                "success": True,
                "advertiser_id": self.advertiser_id,
                "message": "Connection successful",
            }
            
        except TikTokAPIError as e:
            return {
                "success": False,
                "error": e.message,
                "error_code": e.code,
            }
    
    async def duplicate(self, entity_id: str, entity_type: str = "campaign") -> str:
        """Duplicate a campaign or ad group."""
        # TikTok doesn't have a direct duplicate API, so we copy the entity
        logger.warning(f"TikTok doesn't have native duplicate API. Creating copy of {entity_type} {entity_id}")
        
        if entity_type == "campaign":
            campaign = await self.get_campaign(entity_id)
            new_id = await self.create_campaign(
                name=f"{campaign.campaign_name} - Copy",
                objective=CampaignObjective(campaign.objective_type),
                budget=campaign.budget,
            )
            return new_id
        
        raise NotImplementedError(f"Duplicate not implemented for {entity_type}")
    
    async def rotate_creative(self, ad_id: str) -> bool:
        """Rotate creative for an ad."""
        logger.warning(f"rotate_creative not fully implemented for TikTok {ad_id}")
        return True


# =============================================================================
# MOCK CLIENT FOR TESTING
# =============================================================================

class MockTikTokAdsClient:
    """Mock client for testing without real API credentials."""
    
    def __init__(self, *args, **kwargs):
        self._id_counter = 7000000000000000000
        logger.info("🎭 Using MockTikTokAdsClient (no real API calls)")
    
    def _generate_id(self) -> str:
        self._id_counter += 1
        return str(self._id_counter)
    
    async def close(self):
        pass
    
    async def get_campaigns(self, **kwargs) -> List[Campaign]:
        return [
            Campaign(campaign_id="7123456789012345678", campaign_name="Test Campaign 1", 
                    objective_type="WEBSITE_CONVERSIONS", status="ENABLE", budget=500.0),
            Campaign(campaign_id="7987654321098765432", campaign_name="Test Campaign 2",
                    objective_type="TRAFFIC", status="DISABLE", budget=200.0),
        ]
    
    async def get_all_campaigns(self, **kwargs) -> List[Campaign]:
        return await self.get_campaigns()
    
    async def get_campaign(self, campaign_id: str) -> Campaign:
        return Campaign(campaign_id=campaign_id, campaign_name="Test Campaign",
                       objective_type="WEBSITE_CONVERSIONS", status="ENABLE", budget=500.0)
    
    async def get_adgroups(self, **kwargs) -> List[AdGroup]:
        return [
            AdGroup(adgroup_id="7111111111111111111", adgroup_name="Test AdGroup 1",
                   campaign_id="7123456789012345678", status="ENABLE", budget=100.0),
            AdGroup(adgroup_id="7222222222222222222", adgroup_name="Test AdGroup 2",
                   campaign_id="7123456789012345678", status="DISABLE", budget=50.0),
        ]
    
    async def get_ads(self, **kwargs) -> List[Ad]:
        return [
            Ad(ad_id="7333333333333333333", ad_name="Test Ad 1",
               adgroup_id="7111111111111111111", status="ENABLE"),
            Ad(ad_id="7444444444444444444", ad_name="Test Ad 2",
               adgroup_id="7111111111111111111", status="DISABLE"),
        ]
    
    async def create_campaign(self, name: str, objective: CampaignObjective, **kwargs) -> str:
        new_id = self._generate_id()
        logger.info(f"[MOCK] Created campaign '{name}' -> {new_id}")
        return new_id
    
    async def create_adgroup(self, campaign_id: str, name: str, **kwargs) -> str:
        new_id = self._generate_id()
        logger.info(f"[MOCK] Created ad group '{name}' in {campaign_id} -> {new_id}")
        return new_id
    
    async def create_ad(self, adgroup_id: str, name: str, **kwargs) -> str:
        new_id = self._generate_id()
        logger.info(f"[MOCK] Created ad '{name}' in {adgroup_id} -> {new_id}")
        return new_id
    
    async def update_status(self, entity_id: str, status: str, entity_type: str = "campaign") -> bool:
        logger.info(f"[MOCK] Updated {entity_type} {entity_id} status to {status}")
        return True
    
    async def pause_campaign(self, campaign_id: str) -> bool:
        return await self.update_status(campaign_id, "DISABLE", "campaign")
    
    async def enable_campaign(self, campaign_id: str) -> bool:
        return await self.update_status(campaign_id, "ENABLE", "campaign")
    
    async def update_campaign(self, campaign_id: str, **kwargs) -> bool:
        logger.info(f"[MOCK] Updated campaign {campaign_id}")
        return True
    
    async def update_adgroup(self, adgroup_id: str, **kwargs) -> bool:
        logger.info(f"[MOCK] Updated ad group {adgroup_id}")
        return True
    
    async def update_budget(self, entity_id: str, budget: float, entity_type: str = "campaign") -> bool:
        logger.info(f"[MOCK] Updated {entity_type} {entity_id} budget to ${budget:.2f}")
        return True
    
    async def update_bid(self, adgroup_id: str, bid_price: float) -> bool:
        logger.info(f"[MOCK] Updated ad group {adgroup_id} bid to ${bid_price:.2f}")
        return True
    
    async def duplicate(self, entity_id: str, entity_type: str = "campaign") -> str:
        new_id = self._generate_id()
        logger.info(f"[MOCK] Duplicated {entity_type} {entity_id} -> {new_id}")
        return new_id
    
    async def create_lookalike(self, source_id: str, name: str, **kwargs) -> str:
        new_id = self._generate_id()
        logger.info(f"[MOCK] Created lookalike from {source_id} -> {new_id}")
        return new_id
    
    async def create_audience(self, config: Dict) -> str:
        new_id = self._generate_id()
        logger.info(f"[MOCK] Created audience '{config.get('name')}' -> {new_id}")
        return new_id
    
    async def rotate_creative(self, ad_id: str) -> bool:
        logger.info(f"[MOCK] Rotated creative for {ad_id}")
        return True
    
    async def get_insights(self, **kwargs) -> List[InsightsData]:
        return [
            InsightsData(
                date="2024-01-01 - 2024-01-07",
                advertiser_id="mock_123",
                campaign_id="7123456789012345678",
                impressions=100000,
                clicks=3500,
                spend=850.0,
                reach=75000,
                cpm=8.50,
                cpc=0.24,
                ctr=3.5,
                conversions=120,
                cost_per_conversion=7.08,
                video_views=45000,
                video_watched_6s=22000,
            )
        ]
    
    async def test_connection(self) -> Dict:
        return {"success": True, "advertiser_id": "mock_123", "message": "Mock connection"}


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_tiktok_ads_client(
    use_mock: bool = None,
    **kwargs
) -> Union[TikTokAdsClient, MockTikTokAdsClient]:
    """
    Factory function to get the appropriate TikTok Ads client.
    
    Args:
        use_mock: Force mock mode. If None, auto-detect based on credentials.
        **kwargs: Arguments to pass to the client constructor.
    
    Returns:
        TikTokAdsClient or MockTikTokAdsClient instance.
    """
    # Check if we should use mock
    if use_mock is True:
        return MockTikTokAdsClient(**kwargs)
    
    if use_mock is False:
        return TikTokAdsClient(**kwargs)
    
    # Auto-detect: use mock if httpx not available or no credentials
    if not HTTPX_AVAILABLE:
        logger.warning("httpx not installed. Using mock client.")
        return MockTikTokAdsClient(**kwargs)
    
    access_token = kwargs.get("access_token") or os.getenv("TIKTOK_ACCESS_TOKEN")
    advertiser_id = kwargs.get("advertiser_id") or os.getenv("TIKTOK_ADVERTISER_ID")
    
    if not access_token or not advertiser_id:
        logger.warning("TIKTOK_ACCESS_TOKEN or TIKTOK_ADVERTISER_ID not set. Using mock client.")
        return MockTikTokAdsClient(**kwargs)
    
    try:
        return TikTokAdsClient(**kwargs)
    except Exception as e:
        logger.error(f"Failed to initialize TikTokAdsClient: {e}. Using mock client.")
        return MockTikTokAdsClient(**kwargs)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Main Client
    "TikTokAdsClient",
    "MockTikTokAdsClient",
    "get_tiktok_ads_client",
    
    # Enums
    "CampaignObjective",
    "CampaignStatus",
    "OptimizationGoal",
    "BidStrategy",
    "BudgetMode",
    "AdFormat",
    "Placement",
    
    # Data Classes
    "Campaign",
    "AdGroup",
    "Ad",
    "InsightsData",
    
    # Errors
    "TikTokAPIError",
    
    # Flags
    "HTTPX_AVAILABLE",
]
