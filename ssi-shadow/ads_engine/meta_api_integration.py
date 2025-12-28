"""
S.S.I. SHADOW - Meta Marketing API Integration
Integração completa com Meta Ads API (Facebook/Instagram)

Features:
- Campaign Management (CRUD)
- Ad Set Management
- Ad Management
- Audience Management (Custom, Lookalike, Saved)
- Insights & Reporting
- Conversions API (CAPI) Server-Side Tracking
- Batch Operations
- Real-time Webhooks
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Tuple
from enum import Enum
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json
import hashlib
import hmac
import asyncio
import time


# =============================================================================
# ENUMS
# =============================================================================

class MetaCampaignObjective(Enum):
    """Objetivos de campanha do Meta"""
    OUTCOME_AWARENESS = "OUTCOME_AWARENESS"
    OUTCOME_ENGAGEMENT = "OUTCOME_ENGAGEMENT"
    OUTCOME_LEADS = "OUTCOME_LEADS"
    OUTCOME_APP_PROMOTION = "OUTCOME_APP_PROMOTION"
    OUTCOME_SALES = "OUTCOME_SALES"
    OUTCOME_TRAFFIC = "OUTCOME_TRAFFIC"

class MetaBidStrategy(Enum):
    """Estratégias de lance"""
    LOWEST_COST_WITHOUT_CAP = "LOWEST_COST_WITHOUT_CAP"
    LOWEST_COST_WITH_BID_CAP = "LOWEST_COST_WITH_BID_CAP"
    COST_CAP = "COST_CAP"
    LOWEST_COST_WITH_MIN_ROAS = "LOWEST_COST_WITH_MIN_ROAS"

class MetaOptimizationGoal(Enum):
    """Metas de otimização"""
    IMPRESSIONS = "IMPRESSIONS"
    REACH = "REACH"
    LINK_CLICKS = "LINK_CLICKS"
    LANDING_PAGE_VIEWS = "LANDING_PAGE_VIEWS"
    OFFSITE_CONVERSIONS = "OFFSITE_CONVERSIONS"
    VALUE = "VALUE"
    APP_INSTALLS = "APP_INSTALLS"
    LEAD_GENERATION = "LEAD_GENERATION"
    ENGAGED_USERS = "ENGAGED_USERS"
    VIDEO_VIEWS = "VIDEO_VIEWS"
    THRUPLAY = "THRUPLAY"

class MetaBillingEvent(Enum):
    """Eventos de cobrança"""
    IMPRESSIONS = "IMPRESSIONS"
    LINK_CLICKS = "LINK_CLICKS"
    APP_INSTALLS = "APP_INSTALLS"
    PAGE_LIKES = "PAGE_LIKES"
    POST_ENGAGEMENT = "POST_ENGAGEMENT"
    VIDEO_VIEWS = "VIDEO_VIEWS"
    THRUPLAY = "THRUPLAY"

class MetaStatus(Enum):
    """Status de entidades"""
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    DELETED = "DELETED"
    ARCHIVED = "ARCHIVED"

class MetaPlacement(Enum):
    """Placements disponíveis"""
    FACEBOOK_FEED = "facebook_feed"
    FACEBOOK_MARKETPLACE = "facebook_marketplace"
    FACEBOOK_VIDEO_FEEDS = "facebook_video_feeds"
    FACEBOOK_RIGHT_COLUMN = "facebook_right_column"
    FACEBOOK_STORIES = "facebook_stories"
    FACEBOOK_REELS = "facebook_reels"
    INSTAGRAM_FEED = "instagram_feed"
    INSTAGRAM_STORIES = "instagram_stories"
    INSTAGRAM_REELS = "instagram_reels"
    INSTAGRAM_EXPLORE = "instagram_explore"
    AUDIENCE_NETWORK = "audience_network"
    MESSENGER_INBOX = "messenger_inbox"
    MESSENGER_STORIES = "messenger_stories"

class ConversionEvent(Enum):
    """Eventos de conversão padrão"""
    PAGE_VIEW = "PageView"
    VIEW_CONTENT = "ViewContent"
    SEARCH = "Search"
    ADD_TO_CART = "AddToCart"
    ADD_TO_WISHLIST = "AddToWishlist"
    INITIATE_CHECKOUT = "InitiateCheckout"
    ADD_PAYMENT_INFO = "AddPaymentInfo"
    PURCHASE = "Purchase"
    LEAD = "Lead"
    COMPLETE_REGISTRATION = "CompleteRegistration"
    CONTACT = "Contact"
    CUSTOMIZE_PRODUCT = "CustomizeProduct"
    DONATE = "Donate"
    FIND_LOCATION = "FindLocation"
    SCHEDULE = "Schedule"
    START_TRIAL = "StartTrial"
    SUBMIT_APPLICATION = "SubmitApplication"
    SUBSCRIBE = "Subscribe"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class MetaCampaign:
    """Campanha do Meta"""
    id: Optional[str] = None
    name: str = ""
    objective: MetaCampaignObjective = MetaCampaignObjective.OUTCOME_SALES
    status: MetaStatus = MetaStatus.PAUSED
    special_ad_categories: List[str] = field(default_factory=list)
    daily_budget: Optional[float] = None
    lifetime_budget: Optional[float] = None
    bid_strategy: MetaBidStrategy = MetaBidStrategy.LOWEST_COST_WITHOUT_CAP
    
@dataclass
class MetaAdSet:
    """Ad Set do Meta"""
    id: Optional[str] = None
    name: str = ""
    campaign_id: str = ""
    status: MetaStatus = MetaStatus.PAUSED
    daily_budget: Optional[float] = None
    lifetime_budget: Optional[float] = None
    optimization_goal: MetaOptimizationGoal = MetaOptimizationGoal.OFFSITE_CONVERSIONS
    billing_event: MetaBillingEvent = MetaBillingEvent.IMPRESSIONS
    bid_amount: Optional[int] = None  # Em centavos
    bid_strategy: MetaBidStrategy = MetaBidStrategy.LOWEST_COST_WITHOUT_CAP
    targeting: Dict = field(default_factory=dict)
    placements: List[MetaPlacement] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    
@dataclass
class MetaAd:
    """Ad do Meta"""
    id: Optional[str] = None
    name: str = ""
    adset_id: str = ""
    status: MetaStatus = MetaStatus.PAUSED
    creative_id: Optional[str] = None
    creative: Optional[Dict] = None
    tracking_specs: Optional[Dict] = None

@dataclass
class MetaCreative:
    """Creative do Meta"""
    id: Optional[str] = None
    name: str = ""
    object_story_spec: Optional[Dict] = None
    asset_feed_spec: Optional[Dict] = None
    url_tags: Optional[str] = None
    
@dataclass
class MetaCustomAudience:
    """Custom Audience"""
    id: Optional[str] = None
    name: str = ""
    description: str = ""
    subtype: str = "CUSTOM"  # CUSTOM, WEBSITE, APP, OFFLINE_CONVERSION, etc
    customer_file_source: Optional[str] = None
    retention_days: int = 180
    rule: Optional[Dict] = None
    
@dataclass
class MetaLookalikeAudience:
    """Lookalike Audience"""
    id: Optional[str] = None
    name: str = ""
    origin_audience_id: str = ""
    country: str = "BR"
    ratio: float = 0.01  # 1%
    starting_ratio: float = 0.0
    
@dataclass
class ConversionAPIEvent:
    """Evento do Conversions API"""
    event_name: ConversionEvent
    event_time: int  # Unix timestamp
    event_id: Optional[str] = None
    event_source_url: Optional[str] = None
    action_source: str = "website"  # website, app, phone_call, chat, physical_store, etc
    user_data: Dict = field(default_factory=dict)
    custom_data: Dict = field(default_factory=dict)
    opt_out: bool = False

@dataclass
class MetaInsights:
    """Insights/Métricas"""
    impressions: int = 0
    reach: int = 0
    clicks: int = 0
    spend: float = 0.0
    cpc: float = 0.0
    cpm: float = 0.0
    ctr: float = 0.0
    frequency: float = 0.0
    conversions: int = 0
    conversion_values: float = 0.0
    cost_per_conversion: float = 0.0
    roas: float = 0.0
    video_views: int = 0
    video_p25_watched: int = 0
    video_p50_watched: int = 0
    video_p75_watched: int = 0
    video_p100_watched: int = 0


# =============================================================================
# META ADS API CLIENT
# =============================================================================

class MetaAdsAPIClient:
    """
    Cliente para Meta Marketing API
    
    Requer:
    - access_token: Token de acesso do usuário ou system user
    - ad_account_id: ID da conta de anúncios (formato: act_XXXXXXX)
    - app_secret: (Opcional) Para validação de webhooks
    """
    
    API_VERSION = "v21.0"
    BASE_URL = f"https://graph.facebook.com/{API_VERSION}"
    
    def __init__(
        self,
        access_token: str,
        ad_account_id: str,
        app_secret: Optional[str] = None,
        pixel_id: Optional[str] = None
    ):
        self.access_token = access_token
        self.ad_account_id = ad_account_id
        self.app_secret = app_secret
        self.pixel_id = pixel_id
        
        # Rate limiting
        self._last_request_time = 0
        self._request_count = 0
        
    def _get_headers(self) -> Dict[str, str]:
        """Retorna headers para requests"""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
    
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        params: Optional[Dict] = None,
        data: Optional[Dict] = None
    ) -> Dict:
        """Faz request à API"""
        
        # Em produção, usar aiohttp
        # Aqui simulamos a chamada
        
        url = f"{self.BASE_URL}/{endpoint}"
        
        print(f"[META API] {method} {url}")
        if params:
            print(f"  Params: {params}")
        if data:
            print(f"  Data: {data}")
            
        # Mock response
        return {"success": True, "id": f"mock_{int(time.time())}"}
    
    # =========================================================================
    # CAMPAIGN MANAGEMENT
    # =========================================================================
    
    async def create_campaign(self, campaign: MetaCampaign) -> str:
        """Cria uma campanha"""
        
        data = {
            "name": campaign.name,
            "objective": campaign.objective.value,
            "status": campaign.status.value,
            "special_ad_categories": campaign.special_ad_categories
        }
        
        if campaign.daily_budget:
            data["daily_budget"] = int(campaign.daily_budget * 100)  # Centavos
        if campaign.lifetime_budget:
            data["lifetime_budget"] = int(campaign.lifetime_budget * 100)
            
        data["bid_strategy"] = campaign.bid_strategy.value
        
        result = await self._make_request(
            "POST",
            f"{self.ad_account_id}/campaigns",
            data=data
        )
        
        return result.get("id", "")
    
    async def get_campaign(self, campaign_id: str) -> MetaCampaign:
        """Obtém detalhes de uma campanha"""
        
        result = await self._make_request(
            "GET",
            campaign_id,
            params={
                "fields": "id,name,objective,status,daily_budget,lifetime_budget,bid_strategy"
            }
        )
        
        return MetaCampaign(
            id=result.get("id"),
            name=result.get("name", ""),
            objective=MetaCampaignObjective(result.get("objective", "OUTCOME_SALES")),
            status=MetaStatus(result.get("status", "PAUSED"))
        )
    
    async def update_campaign(
        self, 
        campaign_id: str, 
        updates: Dict
    ) -> bool:
        """Atualiza uma campanha"""
        
        # Converte budget para centavos
        if "daily_budget" in updates:
            updates["daily_budget"] = int(updates["daily_budget"] * 100)
        if "lifetime_budget" in updates:
            updates["lifetime_budget"] = int(updates["lifetime_budget"] * 100)
            
        result = await self._make_request(
            "POST",
            campaign_id,
            data=updates
        )
        
        return result.get("success", False)
    
    async def delete_campaign(self, campaign_id: str) -> bool:
        """Deleta uma campanha"""
        
        result = await self._make_request(
            "DELETE",
            campaign_id
        )
        
        return result.get("success", False)
    
    async def get_campaigns(
        self,
        status_filter: Optional[List[MetaStatus]] = None,
        limit: int = 100
    ) -> List[MetaCampaign]:
        """Lista campanhas da conta"""
        
        params = {
            "fields": "id,name,objective,status,daily_budget,lifetime_budget,bid_strategy,effective_status",
            "limit": limit
        }
        
        if status_filter:
            params["filtering"] = json.dumps([{
                "field": "effective_status",
                "operator": "IN",
                "value": [s.value for s in status_filter]
            }])
            
        result = await self._make_request(
            "GET",
            f"{self.ad_account_id}/campaigns",
            params=params
        )
        
        campaigns = []
        for item in result.get("data", []):
            campaigns.append(MetaCampaign(
                id=item.get("id"),
                name=item.get("name", ""),
                objective=MetaCampaignObjective(item.get("objective", "OUTCOME_SALES")),
                status=MetaStatus(item.get("status", "PAUSED"))
            ))
            
        return campaigns
    
    # =========================================================================
    # AD SET MANAGEMENT
    # =========================================================================
    
    async def create_adset(self, adset: MetaAdSet) -> str:
        """Cria um ad set"""
        
        data = {
            "name": adset.name,
            "campaign_id": adset.campaign_id,
            "status": adset.status.value,
            "optimization_goal": adset.optimization_goal.value,
            "billing_event": adset.billing_event.value,
            "bid_strategy": adset.bid_strategy.value
        }
        
        if adset.daily_budget:
            data["daily_budget"] = int(adset.daily_budget * 100)
        if adset.lifetime_budget:
            data["lifetime_budget"] = int(adset.lifetime_budget * 100)
        if adset.bid_amount:
            data["bid_amount"] = adset.bid_amount
        if adset.targeting:
            data["targeting"] = adset.targeting
        if adset.start_time:
            data["start_time"] = adset.start_time.isoformat()
        if adset.end_time:
            data["end_time"] = adset.end_time.isoformat()
            
        result = await self._make_request(
            "POST",
            f"{self.ad_account_id}/adsets",
            data=data
        )
        
        return result.get("id", "")
    
    async def get_adset(self, adset_id: str) -> MetaAdSet:
        """Obtém detalhes de um ad set"""
        
        result = await self._make_request(
            "GET",
            adset_id,
            params={
                "fields": "id,name,campaign_id,status,daily_budget,lifetime_budget,optimization_goal,billing_event,bid_amount,targeting"
            }
        )
        
        return MetaAdSet(
            id=result.get("id"),
            name=result.get("name", ""),
            campaign_id=result.get("campaign_id", ""),
            status=MetaStatus(result.get("status", "PAUSED"))
        )
    
    async def update_adset(self, adset_id: str, updates: Dict) -> bool:
        """Atualiza um ad set"""
        
        if "daily_budget" in updates:
            updates["daily_budget"] = int(updates["daily_budget"] * 100)
        if "lifetime_budget" in updates:
            updates["lifetime_budget"] = int(updates["lifetime_budget"] * 100)
            
        result = await self._make_request(
            "POST",
            adset_id,
            data=updates
        )
        
        return result.get("success", False)
    
    async def get_adsets(
        self,
        campaign_id: Optional[str] = None,
        status_filter: Optional[List[MetaStatus]] = None,
        limit: int = 100
    ) -> List[MetaAdSet]:
        """Lista ad sets"""
        
        endpoint = f"{campaign_id}/adsets" if campaign_id else f"{self.ad_account_id}/adsets"
        
        params = {
            "fields": "id,name,campaign_id,status,daily_budget,lifetime_budget,optimization_goal,targeting,effective_status",
            "limit": limit
        }
        
        if status_filter:
            params["filtering"] = json.dumps([{
                "field": "effective_status",
                "operator": "IN",
                "value": [s.value for s in status_filter]
            }])
            
        result = await self._make_request("GET", endpoint, params=params)
        
        adsets = []
        for item in result.get("data", []):
            adsets.append(MetaAdSet(
                id=item.get("id"),
                name=item.get("name", ""),
                campaign_id=item.get("campaign_id", ""),
                status=MetaStatus(item.get("status", "PAUSED")),
                targeting=item.get("targeting", {})
            ))
            
        return adsets
    
    # =========================================================================
    # AD MANAGEMENT
    # =========================================================================
    
    async def create_ad(self, ad: MetaAd) -> str:
        """Cria um ad"""
        
        data = {
            "name": ad.name,
            "adset_id": ad.adset_id,
            "status": ad.status.value
        }
        
        if ad.creative_id:
            data["creative"] = {"creative_id": ad.creative_id}
        elif ad.creative:
            data["creative"] = ad.creative
            
        if ad.tracking_specs:
            data["tracking_specs"] = ad.tracking_specs
            
        result = await self._make_request(
            "POST",
            f"{self.ad_account_id}/ads",
            data=data
        )
        
        return result.get("id", "")
    
    async def get_ad(self, ad_id: str) -> MetaAd:
        """Obtém detalhes de um ad"""
        
        result = await self._make_request(
            "GET",
            ad_id,
            params={
                "fields": "id,name,adset_id,status,creative,effective_status"
            }
        )
        
        return MetaAd(
            id=result.get("id"),
            name=result.get("name", ""),
            adset_id=result.get("adset_id", ""),
            status=MetaStatus(result.get("status", "PAUSED"))
        )
    
    async def update_ad(self, ad_id: str, updates: Dict) -> bool:
        """Atualiza um ad"""
        
        result = await self._make_request(
            "POST",
            ad_id,
            data=updates
        )
        
        return result.get("success", False)
    
    async def get_ads(
        self,
        adset_id: Optional[str] = None,
        campaign_id: Optional[str] = None,
        status_filter: Optional[List[MetaStatus]] = None,
        limit: int = 100
    ) -> List[MetaAd]:
        """Lista ads"""
        
        if adset_id:
            endpoint = f"{adset_id}/ads"
        elif campaign_id:
            endpoint = f"{campaign_id}/ads"
        else:
            endpoint = f"{self.ad_account_id}/ads"
            
        params = {
            "fields": "id,name,adset_id,status,creative,effective_status",
            "limit": limit
        }
        
        if status_filter:
            params["filtering"] = json.dumps([{
                "field": "effective_status",
                "operator": "IN",
                "value": [s.value for s in status_filter]
            }])
            
        result = await self._make_request("GET", endpoint, params=params)
        
        ads = []
        for item in result.get("data", []):
            ads.append(MetaAd(
                id=item.get("id"),
                name=item.get("name", ""),
                adset_id=item.get("adset_id", ""),
                status=MetaStatus(item.get("status", "PAUSED"))
            ))
            
        return ads
    
    # =========================================================================
    # CREATIVE MANAGEMENT
    # =========================================================================
    
    async def create_creative(self, creative: MetaCreative) -> str:
        """Cria um creative"""
        
        data = {"name": creative.name}
        
        if creative.object_story_spec:
            data["object_story_spec"] = creative.object_story_spec
        if creative.asset_feed_spec:
            data["asset_feed_spec"] = creative.asset_feed_spec
        if creative.url_tags:
            data["url_tags"] = creative.url_tags
            
        result = await self._make_request(
            "POST",
            f"{self.ad_account_id}/adcreatives",
            data=data
        )
        
        return result.get("id", "")
    
    async def create_image_ad_creative(
        self,
        name: str,
        page_id: str,
        image_hash: str,
        message: str,
        link: str,
        headline: str,
        description: str,
        cta_type: str = "LEARN_MORE"
    ) -> str:
        """Cria creative de imagem simples"""
        
        creative = MetaCreative(
            name=name,
            object_story_spec={
                "page_id": page_id,
                "link_data": {
                    "image_hash": image_hash,
                    "link": link,
                    "message": message,
                    "name": headline,
                    "description": description,
                    "call_to_action": {"type": cta_type}
                }
            }
        )
        
        return await self.create_creative(creative)
    
    async def create_video_ad_creative(
        self,
        name: str,
        page_id: str,
        video_id: str,
        message: str,
        link: str,
        headline: str,
        description: str,
        cta_type: str = "LEARN_MORE",
        thumbnail_url: Optional[str] = None
    ) -> str:
        """Cria creative de vídeo"""
        
        video_data = {
            "video_id": video_id,
            "link": link,
            "message": message,
            "name": headline,
            "description": description,
            "call_to_action": {"type": cta_type, "value": {"link": link}}
        }
        
        if thumbnail_url:
            video_data["picture"] = thumbnail_url
            
        creative = MetaCreative(
            name=name,
            object_story_spec={
                "page_id": page_id,
                "video_data": video_data
            }
        )
        
        return await self.create_creative(creative)
    
    async def create_carousel_creative(
        self,
        name: str,
        page_id: str,
        cards: List[Dict],  # [{image_hash, link, headline, description}]
        message: str,
        cta_type: str = "LEARN_MORE"
    ) -> str:
        """Cria creative de carrossel"""
        
        child_attachments = []
        for card in cards:
            child_attachments.append({
                "image_hash": card.get("image_hash"),
                "link": card.get("link"),
                "name": card.get("headline"),
                "description": card.get("description"),
                "call_to_action": {"type": cta_type}
            })
            
        creative = MetaCreative(
            name=name,
            object_story_spec={
                "page_id": page_id,
                "link_data": {
                    "message": message,
                    "child_attachments": child_attachments,
                    "multi_share_optimized": True
                }
            }
        )
        
        return await self.create_creative(creative)
    
    async def upload_image(self, image_path: str) -> str:
        """Faz upload de imagem e retorna hash"""
        
        # Em produção, faria upload real
        result = await self._make_request(
            "POST",
            f"{self.ad_account_id}/adimages",
            data={"filename": image_path}
        )
        
        return result.get("hash", f"hash_{int(time.time())}")
    
    async def upload_video(
        self, 
        video_path: str,
        title: Optional[str] = None
    ) -> str:
        """Faz upload de vídeo e retorna ID"""
        
        result = await self._make_request(
            "POST",
            f"{self.ad_account_id}/advideos",
            data={
                "source": video_path,
                "title": title or "Ad Video"
            }
        )
        
        return result.get("id", f"video_{int(time.time())}")
    
    # =========================================================================
    # AUDIENCE MANAGEMENT
    # =========================================================================
    
    async def create_custom_audience(
        self, 
        audience: MetaCustomAudience
    ) -> str:
        """Cria custom audience"""
        
        data = {
            "name": audience.name,
            "description": audience.description,
            "subtype": audience.subtype
        }
        
        if audience.customer_file_source:
            data["customer_file_source"] = audience.customer_file_source
        if audience.retention_days:
            data["retention_days"] = audience.retention_days
        if audience.rule:
            data["rule"] = json.dumps(audience.rule)
            
        result = await self._make_request(
            "POST",
            f"{self.ad_account_id}/customaudiences",
            data=data
        )
        
        return result.get("id", "")
    
    async def create_website_custom_audience(
        self,
        name: str,
        pixel_id: str,
        retention_days: int = 30,
        event_name: Optional[str] = None,
        url_contains: Optional[str] = None
    ) -> str:
        """Cria audience de visitantes do site"""
        
        rule = {"inclusions": {"operator": "or", "rules": []}}
        
        if event_name:
            rule["inclusions"]["rules"].append({
                "event_sources": [{"id": pixel_id, "type": "pixel"}],
                "retention_seconds": retention_days * 86400,
                "filter": {
                    "operator": "and",
                    "filters": [{
                        "field": "event",
                        "operator": "eq",
                        "value": event_name
                    }]
                }
            })
        elif url_contains:
            rule["inclusions"]["rules"].append({
                "event_sources": [{"id": pixel_id, "type": "pixel"}],
                "retention_seconds": retention_days * 86400,
                "filter": {
                    "operator": "and",
                    "filters": [{
                        "field": "url",
                        "operator": "i_contains",
                        "value": url_contains
                    }]
                }
            })
        else:
            rule["inclusions"]["rules"].append({
                "event_sources": [{"id": pixel_id, "type": "pixel"}],
                "retention_seconds": retention_days * 86400
            })
            
        audience = MetaCustomAudience(
            name=name,
            description=f"Website visitors - {retention_days} days",
            subtype="WEBSITE",
            rule=rule,
            retention_days=retention_days
        )
        
        return await self.create_custom_audience(audience)
    
    async def create_lookalike_audience(
        self,
        audience: MetaLookalikeAudience
    ) -> str:
        """Cria lookalike audience"""
        
        data = {
            "name": audience.name,
            "origin_audience_id": audience.origin_audience_id,
            "lookalike_spec": json.dumps({
                "country": audience.country,
                "ratio": audience.ratio,
                "starting_ratio": audience.starting_ratio,
                "type": "similarity"
            }),
            "subtype": "LOOKALIKE"
        }
        
        result = await self._make_request(
            "POST",
            f"{self.ad_account_id}/customaudiences",
            data=data
        )
        
        return result.get("id", "")
    
    async def add_users_to_audience(
        self,
        audience_id: str,
        users: List[Dict],  # [{email, phone, etc}]
        data_source: str = "PARTNER_PROVIDED_ONLY"
    ) -> Dict:
        """Adiciona usuários a uma custom audience"""
        
        # Hash dos dados (SHA256)
        hashed_users = []
        for user in users:
            hashed_user = {}
            for key, value in user.items():
                if value:
                    hashed_user[key] = hashlib.sha256(
                        value.lower().strip().encode()
                    ).hexdigest()
            hashed_users.append(hashed_user)
            
        data = {
            "payload": {
                "schema": list(users[0].keys()) if users else [],
                "data": [[u.get(k, "") for k in users[0].keys()] for u in hashed_users]
            },
            "data_source": {
                "type": data_source
            }
        }
        
        result = await self._make_request(
            "POST",
            f"{audience_id}/users",
            data=data
        )
        
        return result
    
    async def get_custom_audiences(self, limit: int = 100) -> List[MetaCustomAudience]:
        """Lista custom audiences"""
        
        result = await self._make_request(
            "GET",
            f"{self.ad_account_id}/customaudiences",
            params={
                "fields": "id,name,description,subtype,approximate_count,delivery_status",
                "limit": limit
            }
        )
        
        audiences = []
        for item in result.get("data", []):
            audiences.append(MetaCustomAudience(
                id=item.get("id"),
                name=item.get("name", ""),
                description=item.get("description", ""),
                subtype=item.get("subtype", "CUSTOM")
            ))
            
        return audiences
    
    # =========================================================================
    # INSIGHTS & REPORTING
    # =========================================================================
    
    async def get_insights(
        self,
        object_id: str,
        date_preset: str = "last_7d",
        fields: Optional[List[str]] = None,
        breakdowns: Optional[List[str]] = None,
        level: str = "account"
    ) -> List[MetaInsights]:
        """Obtém insights/métricas"""
        
        default_fields = [
            "impressions", "reach", "clicks", "spend",
            "cpc", "cpm", "ctr", "frequency",
            "actions", "action_values", "cost_per_action_type",
            "video_p25_watched_actions", "video_p50_watched_actions",
            "video_p75_watched_actions", "video_p100_watched_actions"
        ]
        
        params = {
            "date_preset": date_preset,
            "fields": ",".join(fields or default_fields),
            "level": level
        }
        
        if breakdowns:
            params["breakdowns"] = ",".join(breakdowns)
            
        result = await self._make_request(
            "GET",
            f"{object_id}/insights",
            params=params
        )
        
        insights = []
        for item in result.get("data", []):
            insight = MetaInsights(
                impressions=int(item.get("impressions", 0)),
                reach=int(item.get("reach", 0)),
                clicks=int(item.get("clicks", 0)),
                spend=float(item.get("spend", 0)),
                cpc=float(item.get("cpc", 0)),
                cpm=float(item.get("cpm", 0)),
                ctr=float(item.get("ctr", 0)),
                frequency=float(item.get("frequency", 0))
            )
            
            # Parse actions
            for action in item.get("actions", []):
                if action.get("action_type") == "purchase":
                    insight.conversions = int(action.get("value", 0))
                    
            for action_value in item.get("action_values", []):
                if action_value.get("action_type") == "purchase":
                    insight.conversion_values = float(action_value.get("value", 0))
                    
            # Calcula ROAS
            if insight.spend > 0:
                insight.roas = insight.conversion_values / insight.spend
                
            insights.append(insight)
            
        return insights
    
    async def get_account_insights(
        self,
        date_preset: str = "last_7d"
    ) -> MetaInsights:
        """Obtém insights da conta"""
        
        insights = await self.get_insights(
            self.ad_account_id,
            date_preset=date_preset,
            level="account"
        )
        
        return insights[0] if insights else MetaInsights()
    
    async def get_campaign_insights(
        self,
        campaign_id: str,
        date_preset: str = "last_7d"
    ) -> MetaInsights:
        """Obtém insights de uma campanha"""
        
        insights = await self.get_insights(
            campaign_id,
            date_preset=date_preset,
            level="campaign"
        )
        
        return insights[0] if insights else MetaInsights()
    
    # =========================================================================
    # CONVERSIONS API (CAPI) - SERVER-SIDE TRACKING
    # =========================================================================
    
    async def send_conversion_event(
        self,
        event: ConversionAPIEvent
    ) -> Dict:
        """Envia evento de conversão via CAPI"""
        
        if not self.pixel_id:
            raise ValueError("pixel_id é necessário para Conversions API")
            
        # Gera event_id se não fornecido
        if not event.event_id:
            event.event_id = hashlib.md5(
                f"{event.event_name.value}{event.event_time}{json.dumps(event.user_data)}".encode()
            ).hexdigest()
            
        data = {
            "data": [{
                "event_name": event.event_name.value,
                "event_time": event.event_time,
                "event_id": event.event_id,
                "action_source": event.action_source,
                "user_data": self._hash_user_data(event.user_data),
                "custom_data": event.custom_data,
                "opt_out": event.opt_out
            }]
        }
        
        if event.event_source_url:
            data["data"][0]["event_source_url"] = event.event_source_url
            
        result = await self._make_request(
            "POST",
            f"{self.pixel_id}/events",
            data=data
        )
        
        return result
    
    async def send_conversion_events_batch(
        self,
        events: List[ConversionAPIEvent]
    ) -> Dict:
        """Envia batch de eventos de conversão"""
        
        if not self.pixel_id:
            raise ValueError("pixel_id é necessário para Conversions API")
            
        events_data = []
        for event in events:
            if not event.event_id:
                event.event_id = hashlib.md5(
                    f"{event.event_name.value}{event.event_time}{json.dumps(event.user_data)}".encode()
                ).hexdigest()
                
            events_data.append({
                "event_name": event.event_name.value,
                "event_time": event.event_time,
                "event_id": event.event_id,
                "action_source": event.action_source,
                "user_data": self._hash_user_data(event.user_data),
                "custom_data": event.custom_data
            })
            
        result = await self._make_request(
            "POST",
            f"{self.pixel_id}/events",
            data={"data": events_data}
        )
        
        return result
    
    def _hash_user_data(self, user_data: Dict) -> Dict:
        """Hash dados do usuário para CAPI"""
        
        hashed = {}
        
        # Campos que devem ser hasheados
        hash_fields = ["em", "ph", "fn", "ln", "db", "ge", "ct", "st", "zp", "country"]
        
        for key, value in user_data.items():
            if key in hash_fields and value:
                # Normaliza e hash
                normalized = str(value).lower().strip()
                hashed[key] = hashlib.sha256(normalized.encode()).hexdigest()
            else:
                # Mantém original (ex: client_ip_address, client_user_agent, fbc, fbp)
                hashed[key] = value
                
        return hashed
    
    def create_purchase_event(
        self,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        value: float = 0,
        currency: str = "BRL",
        content_ids: Optional[List[str]] = None,
        content_type: str = "product",
        order_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        client_user_agent: Optional[str] = None,
        fbc: Optional[str] = None,
        fbp: Optional[str] = None,
        source_url: Optional[str] = None
    ) -> ConversionAPIEvent:
        """Cria evento de compra formatado para CAPI"""
        
        user_data = {}
        if email:
            user_data["em"] = email
        if phone:
            user_data["ph"] = phone
        if client_ip:
            user_data["client_ip_address"] = client_ip
        if client_user_agent:
            user_data["client_user_agent"] = client_user_agent
        if fbc:
            user_data["fbc"] = fbc
        if fbp:
            user_data["fbp"] = fbp
            
        custom_data = {
            "value": value,
            "currency": currency,
            "content_type": content_type
        }
        
        if content_ids:
            custom_data["content_ids"] = content_ids
        if order_id:
            custom_data["order_id"] = order_id
            
        return ConversionAPIEvent(
            event_name=ConversionEvent.PURCHASE,
            event_time=int(time.time()),
            event_source_url=source_url,
            action_source="website",
            user_data=user_data,
            custom_data=custom_data
        )
    
    # =========================================================================
    # BATCH OPERATIONS
    # =========================================================================
    
    async def batch_request(
        self,
        requests: List[Dict]
    ) -> List[Dict]:
        """Executa múltiplas operações em batch"""
        
        batch_data = []
        for req in requests:
            batch_data.append({
                "method": req.get("method", "GET"),
                "relative_url": req.get("relative_url"),
                "body": req.get("body")
            })
            
        result = await self._make_request(
            "POST",
            "",
            data={"batch": json.dumps(batch_data)}
        )
        
        return result.get("data", [])
    
    async def bulk_update_status(
        self,
        entity_ids: List[str],
        new_status: MetaStatus
    ) -> Dict:
        """Atualiza status de múltiplas entidades em batch"""
        
        requests = [
            {
                "method": "POST",
                "relative_url": entity_id,
                "body": f"status={new_status.value}"
            }
            for entity_id in entity_ids
        ]
        
        results = await self.batch_request(requests)
        
        return {
            "updated": len([r for r in results if r.get("code") == 200]),
            "failed": len([r for r in results if r.get("code") != 200]),
            "details": results
        }
    
    async def bulk_update_budgets(
        self,
        updates: List[Tuple[str, float]]  # [(entity_id, new_budget), ...]
    ) -> Dict:
        """Atualiza budgets de múltiplas entidades em batch"""
        
        requests = [
            {
                "method": "POST",
                "relative_url": entity_id,
                "body": f"daily_budget={int(budget * 100)}"
            }
            for entity_id, budget in updates
        ]
        
        results = await self.batch_request(requests)
        
        return {
            "updated": len([r for r in results if r.get("code") == 200]),
            "failed": len([r for r in results if r.get("code") != 200]),
            "details": results
        }


# =============================================================================
# META ADS AUTOMATION - AUTOMAÇÃO INTEGRADA
# =============================================================================

class MetaAdsAutomation:
    """
    Automação integrada para Meta Ads
    Conecta MetaAdsAPIClient com MetaAdsEngine
    """
    
    def __init__(
        self,
        api_client: MetaAdsAPIClient,
        engine: 'MetaAdsEngine' = None  # Do meta_ads_engine.py
    ):
        self.api = api_client
        self.engine = engine
        
    async def run_daily_optimization(self) -> Dict:
        """Executa otimização diária completa"""
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "campaigns_analyzed": 0,
            "adsets_analyzed": 0,
            "ads_analyzed": 0,
            "actions_taken": [],
            "savings_generated": 0,
            "recommendations": []
        }
        
        # 1. Busca todas as entidades ativas
        campaigns = await self.api.get_campaigns(
            status_filter=[MetaStatus.ACTIVE]
        )
        results["campaigns_analyzed"] = len(campaigns)
        
        all_adsets = []
        all_ads = []
        
        for campaign in campaigns:
            adsets = await self.api.get_adsets(campaign_id=campaign.id)
            all_adsets.extend(adsets)
            
            for adset in adsets:
                ads = await self.api.get_ads(adset_id=adset.id)
                all_ads.extend(ads)
                
        results["adsets_analyzed"] = len(all_adsets)
        results["ads_analyzed"] = len(all_ads)
        
        # 2. Busca insights
        account_insights = await self.api.get_account_insights()
        
        # 3. Executa automações do engine
        if self.engine:
            # Prepara dados para o engine
            items = []
            for ad in all_ads:
                ad_insights = await self.api.get_insights(
                    ad.id,
                    date_preset="last_7d",
                    level="ad"
                )
                
                if ad_insights:
                    items.append({
                        "id": ad.id,
                        "name": ad.name,
                        "level": "ad",
                        "metrics": {
                            "spend": ad_insights[0].spend,
                            "impressions": ad_insights[0].impressions,
                            "clicks": ad_insights[0].clicks,
                            "ctr": ad_insights[0].ctr,
                            "cpc": ad_insights[0].cpc,
                            "conversions": ad_insights[0].conversions,
                            "roas": ad_insights[0].roas,
                            "frequency": ad_insights[0].frequency
                        }
                    })
                    
            # Roda automações
            automation_results = await self.engine.run_automations(items, self.api)
            results["actions_taken"] = automation_results.get("actions_taken", [])
            
        return results
    
    async def pause_underperformers(
        self,
        min_spend: float = 50,
        max_cpa: float = 100,
        min_roas: float = 1.0
    ) -> Dict:
        """Pausa ads com performance ruim"""
        
        paused = []
        
        ads = await self.api.get_ads(status_filter=[MetaStatus.ACTIVE])
        
        for ad in ads:
            insights = await self.api.get_insights(
                ad.id,
                date_preset="last_7d",
                level="ad"
            )
            
            if not insights:
                continue
                
            insight = insights[0]
            
            # Verifica condições
            if insight.spend >= min_spend:
                cpa = insight.spend / insight.conversions if insight.conversions > 0 else float('inf')
                
                if cpa > max_cpa or insight.roas < min_roas:
                    # Pausa ad
                    await self.api.update_ad(ad.id, {"status": "PAUSED"})
                    paused.append({
                        "id": ad.id,
                        "name": ad.name,
                        "reason": f"CPA: ${cpa:.2f}, ROAS: {insight.roas:.2f}x"
                    })
                    
        return {
            "paused_count": len(paused),
            "paused_ads": paused
        }
    
    async def scale_winners(
        self,
        min_roas: float = 3.0,
        min_conversions: int = 5,
        budget_increase_percent: float = 20,
        max_budget: float = 1000
    ) -> Dict:
        """Escala ad sets vencedores"""
        
        scaled = []
        
        adsets = await self.api.get_adsets(status_filter=[MetaStatus.ACTIVE])
        
        for adset in adsets:
            insights = await self.api.get_insights(
                adset.id,
                date_preset="last_3d",
                level="adset"
            )
            
            if not insights:
                continue
                
            insight = insights[0]
            
            if insight.roas >= min_roas and insight.conversions >= min_conversions:
                # Calcula novo budget
                current_budget = adset.daily_budget or 0
                new_budget = min(
                    current_budget * (1 + budget_increase_percent / 100),
                    max_budget
                )
                
                if new_budget > current_budget:
                    await self.api.update_adset(
                        adset.id,
                        {"daily_budget": new_budget}
                    )
                    scaled.append({
                        "id": adset.id,
                        "name": adset.name,
                        "old_budget": current_budget,
                        "new_budget": new_budget,
                        "roas": insight.roas
                    })
                    
        return {
            "scaled_count": len(scaled),
            "scaled_adsets": scaled
        }
    
    async def detect_creative_fatigue(
        self,
        max_frequency: float = 3.0,
        min_ctr_drop: float = 0.3
    ) -> Dict:
        """Detecta criativos fatigados"""
        
        fatigued = []
        
        ads = await self.api.get_ads(status_filter=[MetaStatus.ACTIVE])
        
        for ad in ads:
            # Insights últimos 3 dias
            recent = await self.api.get_insights(
                ad.id,
                date_preset="last_3d",
                level="ad"
            )
            
            # Insights últimos 14 dias
            historical = await self.api.get_insights(
                ad.id,
                date_preset="last_14d",
                level="ad"
            )
            
            if not recent or not historical:
                continue
                
            recent_insight = recent[0]
            historical_insight = historical[0]
            
            # Verifica fatigue
            if recent_insight.frequency >= max_frequency:
                ctr_drop = (historical_insight.ctr - recent_insight.ctr) / historical_insight.ctr if historical_insight.ctr > 0 else 0
                
                if ctr_drop >= min_ctr_drop:
                    fatigued.append({
                        "id": ad.id,
                        "name": ad.name,
                        "frequency": recent_insight.frequency,
                        "ctr_drop": f"{ctr_drop*100:.1f}%",
                        "recommendation": "Criar novos criativos ou pausar"
                    })
                    
        return {
            "fatigued_count": len(fatigued),
            "fatigued_ads": fatigued
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "MetaCampaignObjective",
    "MetaBidStrategy",
    "MetaOptimizationGoal",
    "MetaBillingEvent",
    "MetaStatus",
    "MetaPlacement",
    "ConversionEvent",
    
    # Data Classes
    "MetaCampaign",
    "MetaAdSet",
    "MetaAd",
    "MetaCreative",
    "MetaCustomAudience",
    "MetaLookalikeAudience",
    "ConversionAPIEvent",
    "MetaInsights",
    
    # API Client
    "MetaAdsAPIClient",
    "MetaAdsAutomation"
]
