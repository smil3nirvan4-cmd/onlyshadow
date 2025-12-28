"""
S.S.I. SHADOW - Meta Ads API Client (Real Implementation)
==========================================================
Production-ready client using official Facebook Business SDK

Prerequisites:
    pip install facebook-business

Environment Variables:
    META_APP_ID - Facebook App ID
    META_APP_SECRET - Facebook App Secret
    META_ACCESS_TOKEN - Long-lived Access Token
    META_AD_ACCOUNT_ID - Ad Account ID (without 'act_' prefix)

Author: SSI Shadow Team
Version: 1.0.0
"""

import os
import logging
import asyncio
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Thread pool for blocking SDK calls
_executor = ThreadPoolExecutor(max_workers=4)

# Try to import Facebook Business SDK
try:
    from facebook_business.api import FacebookAdsApi
    from facebook_business.adobjects.adaccount import AdAccount
    from facebook_business.adobjects.campaign import Campaign as FbCampaign
    from facebook_business.adobjects.adset import AdSet as FbAdSet
    from facebook_business.adobjects.ad import Ad as FbAd
    from facebook_business.adobjects.adcreative import AdCreative
    from facebook_business.adobjects.customaudience import CustomAudience
    from facebook_business.adobjects.adsinsights import AdsInsights
    from facebook_business.exceptions import FacebookRequestError
    FB_SDK_AVAILABLE = True
except ImportError:
    FB_SDK_AVAILABLE = False
    logger.warning("facebook-business SDK not installed. Run: pip install facebook-business")


# =============================================================================
# ENUMS
# =============================================================================

class CampaignObjective(Enum):
    """Meta Campaign Objectives (ODAX)"""
    OUTCOME_AWARENESS = "OUTCOME_AWARENESS"
    OUTCOME_ENGAGEMENT = "OUTCOME_ENGAGEMENT"
    OUTCOME_LEADS = "OUTCOME_LEADS"
    OUTCOME_APP_PROMOTION = "OUTCOME_APP_PROMOTION"
    OUTCOME_SALES = "OUTCOME_SALES"
    OUTCOME_TRAFFIC = "OUTCOME_TRAFFIC"


class CampaignStatus(Enum):
    """Campaign Status"""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DELETED = "DELETED"
    ARCHIVED = "ARCHIVED"


class BidStrategy(Enum):
    """Bid Strategies"""
    LOWEST_COST_WITHOUT_CAP = "LOWEST_COST_WITHOUT_CAP"
    LOWEST_COST_WITH_BID_CAP = "LOWEST_COST_WITH_BID_CAP"
    COST_CAP = "COST_CAP"
    LOWEST_COST_WITH_MIN_ROAS = "LOWEST_COST_WITH_MIN_ROAS"


class OptimizationGoal(Enum):
    """Optimization Goals for Ad Sets"""
    IMPRESSIONS = "IMPRESSIONS"
    REACH = "REACH"
    LINK_CLICKS = "LINK_CLICKS"
    LANDING_PAGE_VIEWS = "LANDING_PAGE_VIEWS"
    OFFSITE_CONVERSIONS = "OFFSITE_CONVERSIONS"
    VALUE = "VALUE"
    APP_INSTALLS = "APP_INSTALLS"
    LEAD_GENERATION = "LEAD_GENERATION"


class BillingEvent(Enum):
    """Billing Events"""
    IMPRESSIONS = "IMPRESSIONS"
    LINK_CLICKS = "LINK_CLICKS"
    APP_INSTALLS = "APP_INSTALLS"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Campaign:
    """Campaign data model"""
    id: str
    name: str
    objective: str
    status: str
    daily_budget: Optional[float] = None
    lifetime_budget: Optional[float] = None
    bid_strategy: Optional[str] = None
    start_time: Optional[datetime] = None
    stop_time: Optional[datetime] = None
    created_time: Optional[datetime] = None
    updated_time: Optional[datetime] = None
    effective_status: Optional[str] = None


@dataclass
class AdSet:
    """Ad Set data model"""
    id: str
    name: str
    campaign_id: str
    status: str
    daily_budget: Optional[float] = None
    lifetime_budget: Optional[float] = None
    bid_amount: Optional[float] = None
    optimization_goal: Optional[str] = None
    billing_event: Optional[str] = None
    targeting: Optional[Dict] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


@dataclass
class Ad:
    """Ad data model"""
    id: str
    name: str
    adset_id: str
    status: str
    creative_id: Optional[str] = None
    creative: Optional[Dict] = None


@dataclass
class InsightsData:
    """Insights/Metrics data model"""
    date_start: str
    date_stop: str
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
    roas: float = 0.0
    revenue: float = 0.0


# =============================================================================
# REAL META ADS CLIENT
# =============================================================================

class MetaAdsClient:
    """
    Real Meta Ads API Client using official Facebook Business SDK.
    
    Usage:
        client = MetaAdsClient(
            app_id="your_app_id",
            app_secret="your_app_secret",
            access_token="your_access_token",
            ad_account_id="1234567890"
        )
        
        campaigns = await client.get_campaigns()
        for campaign in campaigns:
            print(f"{campaign.name}: {campaign.status}")
    """
    
    def __init__(
        self,
        app_id: str = None,
        app_secret: str = None,
        access_token: str = None,
        ad_account_id: str = None
    ):
        """
        Initialize Meta Ads Client.
        
        Args:
            app_id: Facebook App ID (or META_APP_ID env var)
            app_secret: Facebook App Secret (or META_APP_SECRET env var)
            access_token: Long-lived access token (or META_ACCESS_TOKEN env var)
            ad_account_id: Ad Account ID without 'act_' prefix (or META_AD_ACCOUNT_ID env var)
        """
        if not FB_SDK_AVAILABLE:
            raise RuntimeError(
                "facebook-business SDK is required. Install with: pip install facebook-business"
            )
        
        # Get credentials from params or environment
        self.app_id = app_id or os.getenv("META_APP_ID")
        self.app_secret = app_secret or os.getenv("META_APP_SECRET")
        self.access_token = access_token or os.getenv("META_ACCESS_TOKEN")
        self.ad_account_id = ad_account_id or os.getenv("META_AD_ACCOUNT_ID")
        
        # Validate required credentials
        if not self.access_token:
            raise ValueError("META_ACCESS_TOKEN is required")
        if not self.ad_account_id:
            raise ValueError("META_AD_ACCOUNT_ID is required")
        
        # Format account ID
        if not self.ad_account_id.startswith("act_"):
            self.ad_account_id = f"act_{self.ad_account_id}"
        
        # Initialize Facebook API
        if self.app_id and self.app_secret:
            FacebookAdsApi.init(
                app_id=self.app_id,
                app_secret=self.app_secret,
                access_token=self.access_token
            )
        else:
            FacebookAdsApi.init(access_token=self.access_token)
        
        # Create AdAccount object
        self._account = AdAccount(self.ad_account_id)
        
        logger.info(f"✅ Meta Ads Client initialized for account {self.ad_account_id}")
    
    # =========================================================================
    # HELPER METHODS
    # =========================================================================
    
    async def _run_sync(self, func, *args, **kwargs):
        """Run blocking SDK call in thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            _executor,
            lambda: func(*args, **kwargs)
        )
    
    def _parse_datetime(self, value: Any) -> Optional[datetime]:
        """Parse datetime from API response."""
        if not value:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return datetime.fromisoformat(value.replace('Z', '+00:00'))
        except (ValueError, AttributeError):
            return None
    
    def _cents_to_dollars(self, cents: Any) -> Optional[float]:
        """Convert cents to dollars."""
        if cents is None:
            return None
        try:
            return float(cents) / 100
        except (ValueError, TypeError):
            return None
    
    def _dollars_to_cents(self, dollars: float) -> int:
        """Convert dollars to cents."""
        return int(dollars * 100)
    
    # =========================================================================
    # CAMPAIGN MANAGEMENT
    # =========================================================================
    
    async def get_campaigns(
        self,
        status_filter: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Campaign]:
        """
        Get all campaigns from the ad account.
        
        Args:
            status_filter: Filter by status (e.g., ['ACTIVE', 'PAUSED'])
            limit: Maximum number of campaigns to return
            
        Returns:
            List of Campaign objects
        """
        fields = [
            FbCampaign.Field.id,
            FbCampaign.Field.name,
            FbCampaign.Field.objective,
            FbCampaign.Field.status,
            FbCampaign.Field.effective_status,
            FbCampaign.Field.daily_budget,
            FbCampaign.Field.lifetime_budget,
            FbCampaign.Field.bid_strategy,
            FbCampaign.Field.start_time,
            FbCampaign.Field.stop_time,
            FbCampaign.Field.created_time,
            FbCampaign.Field.updated_time,
        ]
        
        params = {"limit": limit}
        
        if status_filter:
            params["filtering"] = [{
                "field": "effective_status",
                "operator": "IN",
                "value": status_filter
            }]
        
        try:
            def fetch():
                return list(self._account.get_campaigns(fields=fields, params=params))
            
            fb_campaigns = await self._run_sync(fetch)
            
            campaigns = []
            for c in fb_campaigns:
                campaigns.append(Campaign(
                    id=c.get(FbCampaign.Field.id),
                    name=c.get(FbCampaign.Field.name, ""),
                    objective=c.get(FbCampaign.Field.objective, ""),
                    status=c.get(FbCampaign.Field.status, ""),
                    effective_status=c.get(FbCampaign.Field.effective_status, ""),
                    daily_budget=self._cents_to_dollars(c.get(FbCampaign.Field.daily_budget)),
                    lifetime_budget=self._cents_to_dollars(c.get(FbCampaign.Field.lifetime_budget)),
                    bid_strategy=c.get(FbCampaign.Field.bid_strategy),
                    start_time=self._parse_datetime(c.get(FbCampaign.Field.start_time)),
                    stop_time=self._parse_datetime(c.get(FbCampaign.Field.stop_time)),
                    created_time=self._parse_datetime(c.get(FbCampaign.Field.created_time)),
                    updated_time=self._parse_datetime(c.get(FbCampaign.Field.updated_time)),
                ))
            
            logger.info(f"Retrieved {len(campaigns)} campaigns")
            return campaigns
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error getting campaigns: {e.api_error_message()}")
            raise
    
    async def get_campaign(self, campaign_id: str) -> Campaign:
        """Get a single campaign by ID."""
        fields = [
            FbCampaign.Field.id,
            FbCampaign.Field.name,
            FbCampaign.Field.objective,
            FbCampaign.Field.status,
            FbCampaign.Field.effective_status,
            FbCampaign.Field.daily_budget,
            FbCampaign.Field.lifetime_budget,
            FbCampaign.Field.bid_strategy,
        ]
        
        try:
            def fetch():
                campaign = FbCampaign(campaign_id)
                return campaign.api_get(fields=fields)
            
            c = await self._run_sync(fetch)
            
            return Campaign(
                id=c.get(FbCampaign.Field.id),
                name=c.get(FbCampaign.Field.name, ""),
                objective=c.get(FbCampaign.Field.objective, ""),
                status=c.get(FbCampaign.Field.status, ""),
                effective_status=c.get(FbCampaign.Field.effective_status, ""),
                daily_budget=self._cents_to_dollars(c.get(FbCampaign.Field.daily_budget)),
                lifetime_budget=self._cents_to_dollars(c.get(FbCampaign.Field.lifetime_budget)),
                bid_strategy=c.get(FbCampaign.Field.bid_strategy),
            )
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error getting campaign {campaign_id}: {e.api_error_message()}")
            raise
    
    async def create_campaign(
        self,
        name: str,
        objective: CampaignObjective,
        status: CampaignStatus = CampaignStatus.PAUSED,
        daily_budget: Optional[float] = None,
        lifetime_budget: Optional[float] = None,
        bid_strategy: BidStrategy = BidStrategy.LOWEST_COST_WITHOUT_CAP,
        special_ad_categories: List[str] = None
    ) -> str:
        """
        Create a new campaign.
        
        Args:
            name: Campaign name
            objective: Campaign objective
            status: Initial status (PAUSED by default for safety)
            daily_budget: Daily budget in dollars
            lifetime_budget: Lifetime budget in dollars
            bid_strategy: Bid strategy
            special_ad_categories: Special ad categories if applicable
            
        Returns:
            Campaign ID
        """
        params = {
            "name": name,
            "objective": objective.value,
            "status": status.value,
            "bid_strategy": bid_strategy.value,
            "special_ad_categories": special_ad_categories or [],
        }
        
        if daily_budget:
            params["daily_budget"] = self._dollars_to_cents(daily_budget)
        if lifetime_budget:
            params["lifetime_budget"] = self._dollars_to_cents(lifetime_budget)
        
        try:
            def create():
                return self._account.create_campaign(params=params)
            
            result = await self._run_sync(create)
            campaign_id = result.get("id")
            
            logger.info(f"Created campaign '{name}' with ID {campaign_id}")
            return campaign_id
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error creating campaign: {e.api_error_message()}")
            raise
    
    async def update_campaign(
        self,
        campaign_id: str,
        name: Optional[str] = None,
        status: Optional[CampaignStatus] = None,
        daily_budget: Optional[float] = None,
        lifetime_budget: Optional[float] = None
    ) -> bool:
        """Update a campaign."""
        params = {}
        
        if name:
            params["name"] = name
        if status:
            params["status"] = status.value
        if daily_budget is not None:
            params["daily_budget"] = self._dollars_to_cents(daily_budget)
        if lifetime_budget is not None:
            params["lifetime_budget"] = self._dollars_to_cents(lifetime_budget)
        
        if not params:
            return True  # Nothing to update
        
        try:
            def update():
                campaign = FbCampaign(campaign_id)
                return campaign.api_update(params=params)
            
            await self._run_sync(update)
            logger.info(f"Updated campaign {campaign_id}")
            return True
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error updating campaign: {e.api_error_message()}")
            return False
    
    async def update_status(self, item_id: str, status: str) -> bool:
        """Update status of any entity (campaign, adset, ad)."""
        try:
            def update():
                # Try as campaign first, then adset, then ad
                for obj_class in [FbCampaign, FbAdSet, FbAd]:
                    try:
                        obj = obj_class(item_id)
                        obj.api_update(params={"status": status})
                        return True
                    except:
                        continue
                return False
            
            result = await self._run_sync(update)
            if result:
                logger.info(f"Updated {item_id} status to {status}")
            return result
            
        except Exception as e:
            logger.error(f"Error updating status: {e}")
            return False
    
    async def pause_campaign(self, campaign_id: str) -> bool:
        """Pause a campaign."""
        return await self.update_campaign(campaign_id, status=CampaignStatus.PAUSED)
    
    async def enable_campaign(self, campaign_id: str) -> bool:
        """Enable/activate a campaign."""
        return await self.update_campaign(campaign_id, status=CampaignStatus.ACTIVE)
    
    async def delete_campaign(self, campaign_id: str) -> bool:
        """Delete (archive) a campaign."""
        return await self.update_campaign(campaign_id, status=CampaignStatus.DELETED)
    
    # =========================================================================
    # AD SET MANAGEMENT
    # =========================================================================
    
    async def get_adsets(
        self,
        campaign_id: Optional[str] = None,
        status_filter: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[AdSet]:
        """Get ad sets, optionally filtered by campaign."""
        fields = [
            FbAdSet.Field.id,
            FbAdSet.Field.name,
            FbAdSet.Field.campaign_id,
            FbAdSet.Field.status,
            FbAdSet.Field.effective_status,
            FbAdSet.Field.daily_budget,
            FbAdSet.Field.lifetime_budget,
            FbAdSet.Field.bid_amount,
            FbAdSet.Field.optimization_goal,
            FbAdSet.Field.billing_event,
            FbAdSet.Field.targeting,
        ]
        
        params = {"limit": limit}
        
        if status_filter:
            params["filtering"] = [{
                "field": "effective_status",
                "operator": "IN",
                "value": status_filter
            }]
        
        try:
            def fetch():
                if campaign_id:
                    campaign = FbCampaign(campaign_id)
                    return list(campaign.get_ad_sets(fields=fields, params=params))
                else:
                    return list(self._account.get_ad_sets(fields=fields, params=params))
            
            fb_adsets = await self._run_sync(fetch)
            
            adsets = []
            for a in fb_adsets:
                adsets.append(AdSet(
                    id=a.get(FbAdSet.Field.id),
                    name=a.get(FbAdSet.Field.name, ""),
                    campaign_id=a.get(FbAdSet.Field.campaign_id, ""),
                    status=a.get(FbAdSet.Field.status, ""),
                    daily_budget=self._cents_to_dollars(a.get(FbAdSet.Field.daily_budget)),
                    lifetime_budget=self._cents_to_dollars(a.get(FbAdSet.Field.lifetime_budget)),
                    bid_amount=self._cents_to_dollars(a.get(FbAdSet.Field.bid_amount)),
                    optimization_goal=a.get(FbAdSet.Field.optimization_goal),
                    billing_event=a.get(FbAdSet.Field.billing_event),
                    targeting=a.get(FbAdSet.Field.targeting),
                ))
            
            logger.info(f"Retrieved {len(adsets)} ad sets")
            return adsets
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error getting ad sets: {e.api_error_message()}")
            raise
    
    async def create_adset(
        self,
        campaign_id: str,
        name: str,
        daily_budget: Optional[float] = None,
        lifetime_budget: Optional[float] = None,
        optimization_goal: OptimizationGoal = OptimizationGoal.LINK_CLICKS,
        billing_event: BillingEvent = BillingEvent.IMPRESSIONS,
        targeting: Optional[Dict] = None,
        status: CampaignStatus = CampaignStatus.PAUSED
    ) -> str:
        """Create a new ad set."""
        params = {
            "campaign_id": campaign_id,
            "name": name,
            "optimization_goal": optimization_goal.value,
            "billing_event": billing_event.value,
            "status": status.value,
        }
        
        if daily_budget:
            params["daily_budget"] = self._dollars_to_cents(daily_budget)
        if lifetime_budget:
            params["lifetime_budget"] = self._dollars_to_cents(lifetime_budget)
        if targeting:
            params["targeting"] = targeting
        
        try:
            def create():
                return self._account.create_ad_set(params=params)
            
            result = await self._run_sync(create)
            adset_id = result.get("id")
            
            logger.info(f"Created ad set '{name}' with ID {adset_id}")
            return adset_id
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error creating ad set: {e.api_error_message()}")
            raise
    
    async def update_adset(
        self,
        adset_id: str,
        name: Optional[str] = None,
        status: Optional[CampaignStatus] = None,
        daily_budget: Optional[float] = None,
        bid_amount: Optional[float] = None
    ) -> bool:
        """Update an ad set."""
        params = {}
        
        if name:
            params["name"] = name
        if status:
            params["status"] = status.value
        if daily_budget is not None:
            params["daily_budget"] = self._dollars_to_cents(daily_budget)
        if bid_amount is not None:
            params["bid_amount"] = self._dollars_to_cents(bid_amount)
        
        if not params:
            return True
        
        try:
            def update():
                adset = FbAdSet(adset_id)
                return adset.api_update(params=params)
            
            await self._run_sync(update)
            logger.info(f"Updated ad set {adset_id}")
            return True
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error updating ad set: {e.api_error_message()}")
            return False
    
    async def update_budget(self, item_id: str, budget: float) -> bool:
        """Update budget of an entity."""
        try:
            # Try as campaign first, then adset
            for obj_class in [FbCampaign, FbAdSet]:
                try:
                    def update():
                        obj = obj_class(item_id)
                        return obj.api_update(params={
                            "daily_budget": self._dollars_to_cents(budget)
                        })
                    
                    await self._run_sync(update)
                    logger.info(f"Updated {item_id} budget to ${budget:.2f}")
                    return True
                except:
                    continue
            return False
            
        except Exception as e:
            logger.error(f"Error updating budget: {e}")
            return False
    
    async def update_bid(self, item_id: str, bid: float) -> bool:
        """Update bid amount of an ad set."""
        try:
            def update():
                adset = FbAdSet(item_id)
                return adset.api_update(params={
                    "bid_amount": self._dollars_to_cents(bid)
                })
            
            await self._run_sync(update)
            logger.info(f"Updated {item_id} bid to ${bid:.2f}")
            return True
            
        except Exception as e:
            logger.error(f"Error updating bid: {e}")
            return False
    
    # =========================================================================
    # AD MANAGEMENT
    # =========================================================================
    
    async def get_ads(
        self,
        adset_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        status_filter: Optional[List[str]] = None,
        limit: int = 100
    ) -> List[Ad]:
        """Get ads, optionally filtered by ad set or campaign."""
        fields = [
            FbAd.Field.id,
            FbAd.Field.name,
            FbAd.Field.adset_id,
            FbAd.Field.status,
            FbAd.Field.effective_status,
            FbAd.Field.creative,
        ]
        
        params = {"limit": limit}
        
        if status_filter:
            params["filtering"] = [{
                "field": "effective_status",
                "operator": "IN",
                "value": status_filter
            }]
        
        try:
            def fetch():
                if adset_id:
                    adset = FbAdSet(adset_id)
                    return list(adset.get_ads(fields=fields, params=params))
                elif campaign_id:
                    campaign = FbCampaign(campaign_id)
                    return list(campaign.get_ads(fields=fields, params=params))
                else:
                    return list(self._account.get_ads(fields=fields, params=params))
            
            fb_ads = await self._run_sync(fetch)
            
            ads = []
            for a in fb_ads:
                creative = a.get(FbAd.Field.creative, {})
                ads.append(Ad(
                    id=a.get(FbAd.Field.id),
                    name=a.get(FbAd.Field.name, ""),
                    adset_id=a.get(FbAd.Field.adset_id, ""),
                    status=a.get(FbAd.Field.status, ""),
                    creative_id=creative.get("id") if isinstance(creative, dict) else None,
                    creative=creative if isinstance(creative, dict) else None,
                ))
            
            logger.info(f"Retrieved {len(ads)} ads")
            return ads
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error getting ads: {e.api_error_message()}")
            raise
    
    async def create_ad(
        self,
        adset_id: str,
        name: str,
        creative_id: str,
        status: CampaignStatus = CampaignStatus.PAUSED
    ) -> str:
        """Create a new ad."""
        params = {
            "adset_id": adset_id,
            "name": name,
            "creative": {"creative_id": creative_id},
            "status": status.value,
        }
        
        try:
            def create():
                return self._account.create_ad(params=params)
            
            result = await self._run_sync(create)
            ad_id = result.get("id")
            
            logger.info(f"Created ad '{name}' with ID {ad_id}")
            return ad_id
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error creating ad: {e.api_error_message()}")
            raise
    
    async def duplicate(self, item_id: str, new_name: Optional[str] = None) -> str:
        """Duplicate a campaign, ad set, or ad."""
        try:
            # Try to determine type and duplicate
            for obj_class, copy_method in [
                (FbCampaign, "create_copies"),
                (FbAdSet, "create_copies"),
                (FbAd, "create_copies"),
            ]:
                try:
                    def dup():
                        obj = obj_class(item_id)
                        params = {"rename_options": {"rename_suffix": " - Copy"}}
                        if new_name:
                            params["rename_options"]["rename_prefix"] = new_name
                        result = getattr(obj, copy_method)(params=params)
                        return list(result)[0].get("id") if result else None
                    
                    new_id = await self._run_sync(dup)
                    if new_id:
                        logger.info(f"Duplicated {item_id} to {new_id}")
                        return new_id
                except:
                    continue
            
            raise ValueError(f"Could not duplicate {item_id}")
            
        except Exception as e:
            logger.error(f"Error duplicating: {e}")
            raise
    
    # =========================================================================
    # INSIGHTS & REPORTING
    # =========================================================================
    
    async def get_insights(
        self,
        entity_id: Optional[str] = None,
        level: str = "campaign",
        date_preset: str = "last_7d",
        fields: List[str] = None
    ) -> List[InsightsData]:
        """
        Get performance insights.
        
        Args:
            entity_id: Optional entity ID (campaign, adset, ad)
            level: Aggregation level (account, campaign, adset, ad)
            date_preset: Date range preset (today, yesterday, last_7d, last_30d, etc.)
            fields: List of fields to retrieve
        """
        default_fields = [
            "impressions", "clicks", "spend", "reach",
            "cpm", "cpc", "ctr",
            "actions", "action_values",
            "conversions", "cost_per_conversion",
        ]
        
        params = {
            "level": level,
            "date_preset": date_preset,
        }
        
        try:
            def fetch():
                if entity_id:
                    # Get insights for specific entity
                    for obj_class in [FbCampaign, FbAdSet, FbAd]:
                        try:
                            obj = obj_class(entity_id)
                            return list(obj.get_insights(
                                fields=fields or default_fields,
                                params=params
                            ))
                        except:
                            continue
                    return []
                else:
                    # Get account-level insights
                    return list(self._account.get_insights(
                        fields=fields or default_fields,
                        params=params
                    ))
            
            fb_insights = await self._run_sync(fetch)
            
            insights = []
            for i in fb_insights:
                # Parse actions for conversions
                actions = i.get("actions", [])
                conversions = 0
                for action in actions:
                    if action.get("action_type") in ["purchase", "lead", "complete_registration"]:
                        conversions += int(action.get("value", 0))
                
                # Parse action_values for revenue
                action_values = i.get("action_values", [])
                revenue = 0.0
                for av in action_values:
                    if av.get("action_type") in ["purchase", "omni_purchase"]:
                        revenue += float(av.get("value", 0))
                
                spend = float(i.get("spend", 0))
                
                insights.append(InsightsData(
                    date_start=i.get("date_start", ""),
                    date_stop=i.get("date_stop", ""),
                    impressions=int(i.get("impressions", 0)),
                    clicks=int(i.get("clicks", 0)),
                    spend=spend,
                    reach=int(i.get("reach", 0)),
                    cpm=float(i.get("cpm", 0)),
                    cpc=float(i.get("cpc", 0)) if i.get("cpc") else 0,
                    ctr=float(i.get("ctr", 0)),
                    conversions=conversions,
                    conversion_rate=conversions / int(i.get("clicks", 1)) if i.get("clicks") else 0,
                    cost_per_conversion=spend / conversions if conversions > 0 else 0,
                    revenue=revenue,
                    roas=revenue / spend if spend > 0 else 0,
                ))
            
            logger.info(f"Retrieved {len(insights)} insight records")
            return insights
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error getting insights: {e.api_error_message()}")
            raise
    
    # =========================================================================
    # AUDIENCE MANAGEMENT
    # =========================================================================
    
    async def get_custom_audiences(self, limit: int = 100) -> List[Dict]:
        """Get custom audiences."""
        fields = [
            CustomAudience.Field.id,
            CustomAudience.Field.name,
            CustomAudience.Field.description,
            CustomAudience.Field.subtype,
            CustomAudience.Field.approximate_count,
            CustomAudience.Field.time_created,
            CustomAudience.Field.time_updated,
        ]
        
        try:
            def fetch():
                return list(self._account.get_custom_audiences(
                    fields=fields,
                    params={"limit": limit}
                ))
            
            audiences = await self._run_sync(fetch)
            
            return [
                {
                    "id": a.get(CustomAudience.Field.id),
                    "name": a.get(CustomAudience.Field.name),
                    "description": a.get(CustomAudience.Field.description),
                    "subtype": a.get(CustomAudience.Field.subtype),
                    "size": a.get(CustomAudience.Field.approximate_count),
                }
                for a in audiences
            ]
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error getting audiences: {e.api_error_message()}")
            raise
    
    async def create_lookalike(
        self,
        source_audience_id: str,
        name: str,
        country: str = "BR",
        ratio: float = 0.01,  # 1%
        starting_ratio: float = 0.0
    ) -> str:
        """Create a lookalike audience."""
        params = {
            "name": name,
            "subtype": "LOOKALIKE",
            "origin_audience_id": source_audience_id,
            "lookalike_spec": {
                "type": "similarity",
                "country": country,
                "ratio": ratio,
                "starting_ratio": starting_ratio,
            }
        }
        
        try:
            def create():
                return self._account.create_custom_audience(params=params)
            
            result = await self._run_sync(create)
            audience_id = result.get("id")
            
            logger.info(f"Created lookalike audience '{name}' with ID {audience_id}")
            return audience_id
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error creating lookalike: {e.api_error_message()}")
            raise
    
    async def create_audience(self, config: Dict) -> str:
        """Create a custom audience from configuration."""
        params = {
            "name": config.get("name"),
            "subtype": config.get("subtype", "CUSTOM"),
            "description": config.get("description", ""),
            "customer_file_source": config.get("source", "USER_PROVIDED_ONLY"),
        }
        
        try:
            def create():
                return self._account.create_custom_audience(params=params)
            
            result = await self._run_sync(create)
            audience_id = result.get("id")
            
            logger.info(f"Created audience '{config.get('name')}' with ID {audience_id}")
            return audience_id
            
        except FacebookRequestError as e:
            logger.error(f"Meta API Error creating audience: {e.api_error_message()}")
            raise
    
    # =========================================================================
    # CREATIVE MANAGEMENT
    # =========================================================================
    
    async def rotate_creative(self, ad_id: str) -> bool:
        """Rotate creative for an ad (pause current, enable next)."""
        # This would typically involve duplicating the ad with a different creative
        logger.warning(f"rotate_creative not fully implemented for {ad_id}")
        return True
    
    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================
    
    async def batch_update_status(
        self,
        item_ids: List[str],
        status: CampaignStatus
    ) -> Dict[str, bool]:
        """Batch update status for multiple entities."""
        results = {}
        
        for item_id in item_ids:
            try:
                success = await self.update_status(item_id, status.value)
                results[item_id] = success
            except Exception as e:
                logger.error(f"Error updating {item_id}: {e}")
                results[item_id] = False
        
        return results
    
    # =========================================================================
    # UTILITY METHODS
    # =========================================================================
    
    async def test_connection(self) -> Dict:
        """Test the API connection."""
        try:
            def test():
                return self._account.api_get(fields=["id", "name", "account_status"])
            
            result = await self._run_sync(test)
            
            return {
                "success": True,
                "account_id": result.get("id"),
                "account_name": result.get("name"),
                "account_status": result.get("account_status"),
            }
            
        except FacebookRequestError as e:
            return {
                "success": False,
                "error": e.api_error_message(),
                "error_code": e.api_error_code(),
            }


# =============================================================================
# MOCK CLIENT FOR TESTING
# =============================================================================

class MockMetaAdsClient:
    """Mock client for testing without real API credentials."""
    
    def __init__(self, *args, **kwargs):
        self._id_counter = 1000
        logger.info("🎭 Using MockMetaAdsClient (no real API calls)")
    
    def _generate_id(self) -> str:
        self._id_counter += 1
        return str(self._id_counter)
    
    async def get_campaigns(self, **kwargs) -> List[Campaign]:
        return [
            Campaign(id="123456789", name="Test Campaign 1", objective="OUTCOME_SALES", status="ACTIVE", daily_budget=100.0),
            Campaign(id="987654321", name="Test Campaign 2", objective="OUTCOME_TRAFFIC", status="PAUSED", daily_budget=50.0),
        ]
    
    async def get_adsets(self, **kwargs) -> List[AdSet]:
        return [
            AdSet(id="111111", name="Test AdSet 1", campaign_id="123456789", status="ACTIVE", daily_budget=50.0),
            AdSet(id="222222", name="Test AdSet 2", campaign_id="123456789", status="PAUSED", daily_budget=30.0),
        ]
    
    async def get_ads(self, **kwargs) -> List[Ad]:
        return [
            Ad(id="aaa111", name="Test Ad 1", adset_id="111111", status="ACTIVE"),
            Ad(id="bbb222", name="Test Ad 2", adset_id="111111", status="PAUSED"),
        ]
    
    async def create_campaign(self, name: str, objective: CampaignObjective, **kwargs) -> str:
        new_id = self._generate_id()
        logger.info(f"[MOCK] Created campaign '{name}' -> {new_id}")
        return new_id
    
    async def create_adset(self, campaign_id: str, name: str, **kwargs) -> str:
        new_id = self._generate_id()
        logger.info(f"[MOCK] Created ad set '{name}' in {campaign_id} -> {new_id}")
        return new_id
    
    async def create_ad(self, adset_id: str, name: str, creative_id: str, **kwargs) -> str:
        new_id = self._generate_id()
        logger.info(f"[MOCK] Created ad '{name}' in {adset_id} -> {new_id}")
        return new_id
    
    async def update_status(self, item_id: str, status: str) -> bool:
        logger.info(f"[MOCK] Updated {item_id} status to {status}")
        return True
    
    async def update_budget(self, item_id: str, budget: float) -> bool:
        logger.info(f"[MOCK] Updated {item_id} budget to ${budget:.2f}")
        return True
    
    async def update_bid(self, item_id: str, bid: float) -> bool:
        logger.info(f"[MOCK] Updated {item_id} bid to ${bid:.2f}")
        return True
    
    async def duplicate(self, item_id: str, **kwargs) -> str:
        new_id = self._generate_id()
        logger.info(f"[MOCK] Duplicated {item_id} -> {new_id}")
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
                date_start="2024-01-01",
                date_stop="2024-01-07",
                impressions=50000,
                clicks=1500,
                spend=500.0,
                reach=35000,
                cpm=10.0,
                cpc=0.33,
                ctr=3.0,
                conversions=45,
                conversion_rate=0.03,
                cost_per_conversion=11.11,
                revenue=2250.0,
                roas=4.5,
            )
        ]
    
    async def test_connection(self) -> Dict:
        return {"success": True, "account_id": "mock_123", "account_name": "Mock Account"}


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def get_meta_ads_client(
    use_mock: bool = None,
    **kwargs
) -> Union[MetaAdsClient, MockMetaAdsClient]:
    """
    Factory function to get the appropriate Meta Ads client.
    
    Args:
        use_mock: Force mock mode. If None, auto-detect based on credentials.
        **kwargs: Arguments to pass to the client constructor.
    
    Returns:
        MetaAdsClient or MockMetaAdsClient instance.
    """
    # Check if we should use mock
    if use_mock is True:
        return MockMetaAdsClient(**kwargs)
    
    if use_mock is False:
        return MetaAdsClient(**kwargs)
    
    # Auto-detect: use mock if SDK not available or no credentials
    if not FB_SDK_AVAILABLE:
        logger.warning("facebook-business SDK not installed. Using mock client.")
        return MockMetaAdsClient(**kwargs)
    
    access_token = kwargs.get("access_token") or os.getenv("META_ACCESS_TOKEN")
    ad_account_id = kwargs.get("ad_account_id") or os.getenv("META_AD_ACCOUNT_ID")
    
    if not access_token or not ad_account_id:
        logger.warning("META_ACCESS_TOKEN or META_AD_ACCOUNT_ID not set. Using mock client.")
        return MockMetaAdsClient(**kwargs)
    
    try:
        return MetaAdsClient(**kwargs)
    except Exception as e:
        logger.error(f"Failed to initialize MetaAdsClient: {e}. Using mock client.")
        return MockMetaAdsClient(**kwargs)


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Main Client
    "MetaAdsClient",
    "MockMetaAdsClient",
    "get_meta_ads_client",
    
    # Enums
    "CampaignObjective",
    "CampaignStatus",
    "BidStrategy",
    "OptimizationGoal",
    "BillingEvent",
    
    # Data Classes
    "Campaign",
    "AdSet",
    "Ad",
    "InsightsData",
    
    # Flags
    "FB_SDK_AVAILABLE",
]
