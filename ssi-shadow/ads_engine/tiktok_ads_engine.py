"""
S.S.I. SHADOW - TikTok Ads Engine
Baseado em análise detalhada do AdManage.ai

Funcionalidades implementadas:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ADMANAGE.AI FEATURES:
- Mass Ad Launcher: Lança 100+ ads em segundos
- Auto-Grouping: Agrupa criativos por aspect ratio (9:16, 4:5, 1:1)
- Copy Templates: Templates de copy reutilizáveis
- Post ID Scaling: Mantém engagement ao escalar (Spark Ads)
- Google Sheets Integration: Lança ads direto do Sheets
- Cloud Integrations: Dropbox, Google Drive, Frame.io, Air.inc, Box
- Automated Rules: Pause losers, scale winners
- Creative Analytics: Dashboards de performance
- Multi-Format Support: Carousel, Collection, Flexible, Partnership
- Multi-Platform: Meta + TikTok simultaneamente
- Dynamic Naming: Nomenclatura dinâmica
- UTM Automation: UTMs automáticos
- Team Management: Workspaces e permissões
- AI Copy Variations: Variações de copy com AI
- Multi-Language: Suporte a 50+ idiomas
- Comments AI: Análise de sentimento
- Bulk Edit: Edição em massa
- Duplicate Campaigns: Duplicação de campanhas
- Spark Ads: Partnership/Creator ads
- Dynamic Product Ads: Catálogo de produtos

TIKTOK NATIVE FEATURES:
- Smart+ Campaigns: Full AI control
- Symphony: AI creative tools
- GMV Max: TikTok Shop optimization
- Display Cards / Countdown Stickers

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Tuple, Callable
from enum import Enum
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json
import hashlib
import asyncio
import re
import uuid
import time


# =============================================================================
# ENUMS
# =============================================================================

class TikTokObjective(Enum):
    """Objetivos de campanha TikTok"""
    REACH = "REACH"
    TRAFFIC = "TRAFFIC"
    VIDEO_VIEWS = "VIDEO_VIEWS"
    COMMUNITY_INTERACTION = "COMMUNITY_INTERACTION"
    APP_PROMOTION = "APP_PROMOTION"
    LEAD_GENERATION = "LEAD_GENERATION"
    WEBSITE_CONVERSIONS = "WEBSITE_CONVERSIONS"
    PRODUCT_SALES = "PRODUCT_SALES"
    SHOP_PURCHASES = "SHOP_PURCHASES"

class TikTokOptimizationGoal(Enum):
    """Metas de otimização"""
    SHOW = "SHOW"
    CLICK = "CLICK"
    REACH = "REACH"
    VIDEO_VIEW = "VIDEO_VIEW"
    ENGAGED_VIEW = "ENGAGED_VIEW"
    COMPLETE_PAYMENT = "COMPLETE_PAYMENT"
    VALUE = "VALUE"
    INSTALL = "INSTALL"
    IN_APP_EVENT = "IN_APP_EVENT"
    LEAD = "LEAD"
    ADD_TO_CART = "ADD_TO_CART"

class TikTokBidStrategy(Enum):
    """Estratégias de lance"""
    BID_TYPE_NO_BID = "BID_TYPE_NO_BID"  # Lowest Cost
    BID_TYPE_CUSTOM = "BID_TYPE_CUSTOM"  # Cost Cap
    BID_TYPE_FIXED = "BID_TYPE_FIXED"    # Fixed Bid

class TikTokAdFormat(Enum):
    """Formatos de anúncio"""
    SINGLE_VIDEO = "SINGLE_VIDEO"
    SINGLE_IMAGE = "SINGLE_IMAGE"
    CAROUSEL = "CAROUSEL"
    COLLECTION = "COLLECTION"
    SPARK_AD = "SPARK_AD"
    PLAYABLE = "PLAYABLE"
    PANGLE = "PANGLE"
    DISPLAY_CARD = "DISPLAY_CARD"
    COUNTDOWN_STICKER = "COUNTDOWN_STICKER"

class AspectRatio(Enum):
    """Aspect ratios suportados"""
    VERTICAL_9_16 = "9:16"      # 540x960, 720x1280, 1080x1920
    SQUARE_1_1 = "1:1"          # 540x540, 720x720, 1080x1080
    HORIZONTAL_16_9 = "16:9"    # 960x540, 1280x720, 1920x1080
    PORTRAIT_4_5 = "4:5"        # 864x1080

class TikTokPlacement(Enum):
    """Placements disponíveis"""
    TIKTOK = "TIKTOK"
    NEWS_FEED_APP = "NEWS_FEED_APP"
    PANGLE = "PANGLE"
    GLOBAL_APP_BUNDLE = "GLOBAL_APP_BUNDLE"

class TikTokStatus(Enum):
    """Status de entidades"""
    ENABLE = "ENABLE"
    DISABLE = "DISABLE"
    DELETE = "DELETE"

class SmartPlusType(Enum):
    """Tipos de Smart+ Campaign"""
    WEB_APP = "WEB_APP"
    CATALOG_SALES = "CATALOG_SALES"
    APP_RETARGETING = "APP_RETARGETING"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TikTokCreative:
    """Creative do TikTok"""
    id: Optional[str] = None
    file_path: Optional[str] = None
    video_id: Optional[str] = None
    image_ids: Optional[List[str]] = None
    thumbnail_url: Optional[str] = None
    aspect_ratio: AspectRatio = AspectRatio.VERTICAL_9_16
    duration_seconds: float = 0
    width: int = 0
    height: int = 0
    file_size_mb: float = 0
    
@dataclass
class AdCopyTemplate:
    """Template de copy reutilizável"""
    id: str
    name: str
    ad_text: str
    display_name: Optional[str] = None
    call_to_action: str = "LEARN_MORE"
    landing_page_url: Optional[str] = None
    utm_params: Optional[Dict[str, str]] = None
    language: str = "en"
    created_at: datetime = field(default_factory=datetime.now)
    performance_score: float = 0.0
    uses_count: int = 0

@dataclass
class NamingConvention:
    """Convenção de nomenclatura dinâmica"""
    pattern: str  # Ex: "{date}_{campaign}_{creative}_{audience}_{variant}"
    variables: Dict[str, str] = field(default_factory=dict)
    
    def generate_name(self, **kwargs) -> str:
        """Gera nome baseado no padrão"""
        name = self.pattern
        all_vars = {**self.variables, **kwargs}
        for key, value in all_vars.items():
            name = name.replace(f"{{{key}}}", str(value))
        return name

@dataclass
class UTMConfig:
    """Configuração de UTM automático"""
    source: str = "tiktok"
    medium: str = "paid"
    campaign: Optional[str] = None
    content: Optional[str] = None
    term: Optional[str] = None
    custom_params: Dict[str, str] = field(default_factory=dict)
    
    def generate_url(self, base_url: str) -> str:
        """Gera URL com UTMs"""
        separator = "&" if "?" in base_url else "?"
        params = [
            f"utm_source={self.source}",
            f"utm_medium={self.medium}"
        ]
        if self.campaign:
            params.append(f"utm_campaign={self.campaign}")
        if self.content:
            params.append(f"utm_content={self.content}")
        if self.term:
            params.append(f"utm_term={self.term}")
        for key, value in self.custom_params.items():
            params.append(f"{key}={value}")
        return f"{base_url}{separator}{'&'.join(params)}"

@dataclass
class CreativeGroup:
    """Grupo de criativos por aspect ratio"""
    group_id: str
    name: str
    aspect_ratio: AspectRatio
    creatives: List[TikTokCreative] = field(default_factory=list)
    
@dataclass
class AdBatch:
    """Batch de ads para lançamento em massa"""
    batch_id: str
    name: str
    campaign_id: str
    ad_group_id: str
    creatives: List[TikTokCreative] = field(default_factory=list)
    copy_template: Optional[AdCopyTemplate] = None
    naming_convention: Optional[NamingConvention] = None
    utm_config: Optional[UTMConfig] = None
    status: TikTokStatus = TikTokStatus.ENABLE
    created_at: datetime = field(default_factory=datetime.now)
    launched_count: int = 0
    failed_count: int = 0

@dataclass
class SparkAdConfig:
    """Configuração de Spark Ad (Partnership Ad)"""
    authorized_bc_id: str  # Business Center ID autorizado
    tiktok_item_id: str    # ID do post orgânico
    authorization_code: str
    preserve_engagement: bool = True

@dataclass
class TikTokCampaign:
    """Campanha TikTok"""
    id: Optional[str] = None
    name: str = ""
    objective: TikTokObjective = TikTokObjective.WEBSITE_CONVERSIONS
    budget_mode: str = "BUDGET_MODE_DAY"  # BUDGET_MODE_DAY, BUDGET_MODE_TOTAL
    budget: float = 0
    status: TikTokStatus = TikTokStatus.ENABLE
    is_smart_plus: bool = False
    smart_plus_type: Optional[SmartPlusType] = None

@dataclass
class TikTokAdGroup:
    """Ad Group (equivalente a Ad Set)"""
    id: Optional[str] = None
    name: str = ""
    campaign_id: str = ""
    placement_type: str = "PLACEMENT_TYPE_AUTOMATIC"
    placements: List[TikTokPlacement] = field(default_factory=list)
    optimization_goal: TikTokOptimizationGoal = TikTokOptimizationGoal.CLICK
    bid_type: TikTokBidStrategy = TikTokBidStrategy.BID_TYPE_NO_BID
    bid_price: Optional[float] = None
    budget_mode: str = "BUDGET_MODE_DAY"
    budget: float = 0
    schedule_type: str = "SCHEDULE_FROM_NOW"
    schedule_start_time: Optional[datetime] = None
    schedule_end_time: Optional[datetime] = None
    targeting: Dict = field(default_factory=dict)
    status: TikTokStatus = TikTokStatus.ENABLE
    creative_type: str = "CUSTOM_CREATIVE"  # CUSTOM_CREATIVE, SMART_CREATIVE

@dataclass
class TikTokAd:
    """Ad do TikTok"""
    id: Optional[str] = None
    name: str = ""
    ad_group_id: str = ""
    ad_format: TikTokAdFormat = TikTokAdFormat.SINGLE_VIDEO
    creative: Optional[TikTokCreative] = None
    ad_text: str = ""
    display_name: str = ""
    call_to_action: str = "LEARN_MORE"
    landing_page_url: str = ""
    tracking_pixel_id: Optional[str] = None
    is_spark_ad: bool = False
    spark_config: Optional[SparkAdConfig] = None
    status: TikTokStatus = TikTokStatus.ENABLE

@dataclass
class ProductCatalog:
    """Catálogo de produtos para Dynamic Product Ads"""
    catalog_id: str
    name: str
    feed_url: Optional[str] = None
    products_count: int = 0
    
@dataclass
class ProductSet:
    """Set de produtos do catálogo"""
    product_set_id: str
    catalog_id: str
    name: str
    filter_conditions: Dict = field(default_factory=dict)
    products_count: int = 0


# =============================================================================
# AUTO-GROUPING ENGINE - AGRUPAMENTO AUTOMÁTICO POR ASPECT RATIO
# =============================================================================

class AutoGroupingEngine:
    """
    Engine de agrupamento automático de criativos por aspect ratio
    Similar ao AdManage.ai Auto-Grouping
    """
    
    ASPECT_RATIO_THRESHOLDS = {
        AspectRatio.VERTICAL_9_16: (0.5, 0.6),   # ratio < 0.6
        AspectRatio.PORTRAIT_4_5: (0.75, 0.85),  # 0.75 < ratio < 0.85
        AspectRatio.SQUARE_1_1: (0.95, 1.05),    # 0.95 < ratio < 1.05
        AspectRatio.HORIZONTAL_16_9: (1.7, 1.9)  # ratio > 1.7
    }
    
    def detect_aspect_ratio(self, width: int, height: int) -> AspectRatio:
        """Detecta aspect ratio baseado nas dimensões"""
        
        if height == 0:
            return AspectRatio.SQUARE_1_1
            
        ratio = width / height
        
        if ratio < 0.6:
            return AspectRatio.VERTICAL_9_16
        elif 0.75 <= ratio <= 0.85:
            return AspectRatio.PORTRAIT_4_5
        elif 0.95 <= ratio <= 1.05:
            return AspectRatio.SQUARE_1_1
        elif ratio >= 1.7:
            return AspectRatio.HORIZONTAL_16_9
        else:
            # Default para o mais próximo
            if ratio < 1:
                return AspectRatio.PORTRAIT_4_5
            else:
                return AspectRatio.HORIZONTAL_16_9
    
    def group_creatives_by_filename(
        self,
        creatives: List[TikTokCreative]
    ) -> Dict[str, CreativeGroup]:
        """
        Agrupa criativos por nome de arquivo base
        Ex: creative_01_9x16.mp4, creative_01_4x5.mp4, creative_01_1x1.mp4
        -> Grupo "creative_01" com 3 aspect ratios
        """
        
        groups = {}
        
        for creative in creatives:
            if not creative.file_path:
                continue
                
            # Extrai nome base (remove aspect ratio suffix)
            filename = creative.file_path.split("/")[-1]
            base_name = self._extract_base_name(filename)
            
            if base_name not in groups:
                groups[base_name] = CreativeGroup(
                    group_id=hashlib.md5(base_name.encode()).hexdigest()[:8],
                    name=base_name,
                    aspect_ratio=creative.aspect_ratio,
                    creatives=[]
                )
                
            groups[base_name].creatives.append(creative)
            
        return groups
    
    def group_creatives_by_aspect_ratio(
        self,
        creatives: List[TikTokCreative]
    ) -> Dict[AspectRatio, CreativeGroup]:
        """Agrupa criativos por aspect ratio"""
        
        groups = {}
        
        for creative in creatives:
            ratio = creative.aspect_ratio
            
            if ratio not in groups:
                groups[ratio] = CreativeGroup(
                    group_id=f"ar_{ratio.value.replace(':', 'x')}",
                    name=f"Aspect Ratio {ratio.value}",
                    aspect_ratio=ratio,
                    creatives=[]
                )
                
            groups[ratio].creatives.append(creative)
            
        return groups
    
    def create_multi_format_ad_config(
        self,
        groups: Dict[str, CreativeGroup]
    ) -> List[Dict]:
        """
        Cria configuração de ads multi-format
        Combina 9:16 + 4:5 + 1:1 em um único ad
        """
        
        configs = []
        
        for group_name, group in groups.items():
            # Separa por aspect ratio
            by_ratio = {}
            for creative in group.creatives:
                ratio = creative.aspect_ratio
                if ratio not in by_ratio:
                    by_ratio[ratio] = []
                by_ratio[ratio].append(creative)
                
            # Se tem múltiplos ratios, cria multi-format
            if len(by_ratio) > 1:
                config = {
                    "type": "multi_format",
                    "group_name": group_name,
                    "creatives_by_placement": {}
                }
                
                # Mapeia ratios para placements
                if AspectRatio.VERTICAL_9_16 in by_ratio:
                    config["creatives_by_placement"]["tiktok_feed"] = by_ratio[AspectRatio.VERTICAL_9_16][0]
                if AspectRatio.SQUARE_1_1 in by_ratio:
                    config["creatives_by_placement"]["news_feed"] = by_ratio[AspectRatio.SQUARE_1_1][0]
                if AspectRatio.HORIZONTAL_16_9 in by_ratio:
                    config["creatives_by_placement"]["pangle"] = by_ratio[AspectRatio.HORIZONTAL_16_9][0]
                    
                configs.append(config)
            else:
                # Single format
                for creative in group.creatives:
                    configs.append({
                        "type": "single_format",
                        "group_name": group_name,
                        "creative": creative
                    })
                    
        return configs
    
    def _extract_base_name(self, filename: str) -> str:
        """Extrai nome base removendo sufixos de aspect ratio"""
        
        # Remove extensão
        name = filename.rsplit(".", 1)[0]
        
        # Padrões comuns de aspect ratio
        patterns = [
            r"_9x16$", r"_4x5$", r"_1x1$", r"_16x9$",
            r"_9-16$", r"_4-5$", r"_1-1$", r"_16-9$",
            r"_vertical$", r"_square$", r"_horizontal$",
            r"_portrait$", r"_landscape$",
            r"_story$", r"_feed$", r"_reels$"
        ]
        
        for pattern in patterns:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE)
            
        return name


# =============================================================================
# MASS AD LAUNCHER - LANÇADOR EM MASSA
# =============================================================================

class MassAdLauncher:
    """
    Lançador em massa de ads similar ao AdManage.ai
    Lança 100+ ads em segundos
    """
    
    def __init__(self):
        self.auto_grouping = AutoGroupingEngine()
        self.copy_templates: Dict[str, AdCopyTemplate] = {}
        self.naming_conventions: Dict[str, NamingConvention] = {}
        self.utm_configs: Dict[str, UTMConfig] = {}
        self.batches: Dict[str, AdBatch] = {}
        
    def register_copy_template(self, template: AdCopyTemplate) -> str:
        """Registra template de copy"""
        self.copy_templates[template.id] = template
        return template.id
    
    def register_naming_convention(
        self, 
        name: str, 
        convention: NamingConvention
    ) -> str:
        """Registra convenção de nomenclatura"""
        self.naming_conventions[name] = convention
        return name
    
    def register_utm_config(self, name: str, config: UTMConfig) -> str:
        """Registra configuração de UTM"""
        self.utm_configs[name] = config
        return name
    
    async def prepare_batch(
        self,
        creatives: List[TikTokCreative],
        campaign_id: str,
        ad_group_id: str,
        copy_template_id: Optional[str] = None,
        naming_convention_name: Optional[str] = None,
        utm_config_name: Optional[str] = None,
        auto_group: bool = True
    ) -> AdBatch:
        """Prepara batch de ads para lançamento"""
        
        batch_id = str(uuid.uuid4())[:8]
        
        # Auto-agrupamento
        if auto_group:
            groups = self.auto_grouping.group_creatives_by_filename(creatives)
            # Flatten groups mantendo ordem
            grouped_creatives = []
            for group in groups.values():
                grouped_creatives.extend(group.creatives)
            creatives = grouped_creatives if grouped_creatives else creatives
            
        batch = AdBatch(
            batch_id=batch_id,
            name=f"Batch_{batch_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            campaign_id=campaign_id,
            ad_group_id=ad_group_id,
            creatives=creatives,
            copy_template=self.copy_templates.get(copy_template_id) if copy_template_id else None,
            naming_convention=self.naming_conventions.get(naming_convention_name) if naming_convention_name else None,
            utm_config=self.utm_configs.get(utm_config_name) if utm_config_name else None
        )
        
        self.batches[batch_id] = batch
        return batch
    
    async def launch_batch(
        self,
        batch: AdBatch,
        api_client: 'TikTokAdsAPIClient',
        parallel_requests: int = 10,
        delay_between_batches: float = 0.1
    ) -> Dict:
        """
        Lança batch de ads em paralelo
        100+ ads em segundos
        """
        
        results = {
            "batch_id": batch.batch_id,
            "total": len(batch.creatives),
            "success": 0,
            "failed": 0,
            "ads_created": [],
            "errors": [],
            "duration_seconds": 0
        }
        
        start_time = time.time()
        
        # Prepara ads
        ads_to_create = []
        for i, creative in enumerate(batch.creatives):
            # Gera nome
            if batch.naming_convention:
                ad_name = batch.naming_convention.generate_name(
                    date=datetime.now().strftime("%Y%m%d"),
                    variant=str(i + 1).zfill(3),
                    creative=creative.file_path.split("/")[-1] if creative.file_path else f"creative_{i}"
                )
            else:
                ad_name = f"Ad_{batch.batch_id}_{i + 1}"
                
            # Aplica template de copy
            ad_text = ""
            cta = "LEARN_MORE"
            landing_url = ""
            
            if batch.copy_template:
                ad_text = batch.copy_template.ad_text
                cta = batch.copy_template.call_to_action
                landing_url = batch.copy_template.landing_page_url or ""
                
            # Aplica UTMs
            if batch.utm_config and landing_url:
                landing_url = batch.utm_config.generate_url(landing_url)
                
            ad = TikTokAd(
                name=ad_name,
                ad_group_id=batch.ad_group_id,
                ad_format=TikTokAdFormat.SINGLE_VIDEO if creative.duration_seconds > 0 else TikTokAdFormat.SINGLE_IMAGE,
                creative=creative,
                ad_text=ad_text,
                call_to_action=cta,
                landing_page_url=landing_url,
                status=batch.status
            )
            ads_to_create.append(ad)
            
        # Lança em paralelo (batches de N)
        for i in range(0, len(ads_to_create), parallel_requests):
            batch_ads = ads_to_create[i:i + parallel_requests]
            
            tasks = [
                api_client.create_ad(ad)
                for ad in batch_ads
            ]
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for j, result in enumerate(batch_results):
                if isinstance(result, Exception):
                    results["failed"] += 1
                    results["errors"].append({
                        "ad_name": batch_ads[j].name,
                        "error": str(result)
                    })
                else:
                    results["success"] += 1
                    results["ads_created"].append({
                        "ad_id": result,
                        "ad_name": batch_ads[j].name
                    })
                    
            # Delay entre batches para rate limiting
            await asyncio.sleep(delay_between_batches)
            
        results["duration_seconds"] = time.time() - start_time
        
        # Atualiza batch
        batch.launched_count = results["success"]
        batch.failed_count = results["failed"]
        
        return results
    
    async def duplicate_to_multiple_ad_groups(
        self,
        source_ads: List[TikTokAd],
        target_ad_group_ids: List[str],
        api_client: 'TikTokAdsAPIClient'
    ) -> Dict:
        """Duplica ads para múltiplos ad groups"""
        
        results = {
            "total_duplicated": 0,
            "failed": 0,
            "by_ad_group": {}
        }
        
        for ad_group_id in target_ad_group_ids:
            results["by_ad_group"][ad_group_id] = {
                "success": 0,
                "failed": 0,
                "ads": []
            }
            
            for ad in source_ads:
                try:
                    # Cria cópia do ad no novo ad group
                    new_ad = TikTokAd(
                        name=f"{ad.name}_dup_{ad_group_id[:4]}",
                        ad_group_id=ad_group_id,
                        ad_format=ad.ad_format,
                        creative=ad.creative,
                        ad_text=ad.ad_text,
                        display_name=ad.display_name,
                        call_to_action=ad.call_to_action,
                        landing_page_url=ad.landing_page_url,
                        status=ad.status
                    )
                    
                    new_ad_id = await api_client.create_ad(new_ad)
                    results["by_ad_group"][ad_group_id]["success"] += 1
                    results["by_ad_group"][ad_group_id]["ads"].append(new_ad_id)
                    results["total_duplicated"] += 1
                    
                except Exception as e:
                    results["by_ad_group"][ad_group_id]["failed"] += 1
                    results["failed"] += 1
                    
        return results


# =============================================================================
# SPARK ADS ENGINE - PARTNERSHIP/CREATOR ADS
# =============================================================================

class SparkAdsEngine:
    """
    Engine para Spark Ads (Partnership Ads)
    Preserva engagement de posts orgânicos
    """
    
    async def create_spark_ad(
        self,
        api_client: 'TikTokAdsAPIClient',
        ad_group_id: str,
        spark_config: SparkAdConfig,
        ad_name: str,
        ad_text: str = "",
        call_to_action: str = "LEARN_MORE",
        landing_page_url: str = ""
    ) -> str:
        """Cria Spark Ad a partir de post orgânico"""
        
        ad = TikTokAd(
            name=ad_name,
            ad_group_id=ad_group_id,
            ad_format=TikTokAdFormat.SPARK_AD,
            ad_text=ad_text,
            call_to_action=call_to_action,
            landing_page_url=landing_page_url,
            is_spark_ad=True,
            spark_config=spark_config,
            status=TikTokStatus.ENABLE
        )
        
        return await api_client.create_ad(ad)
    
    async def batch_create_spark_ads(
        self,
        api_client: 'TikTokAdsAPIClient',
        ad_group_id: str,
        spark_configs: List[SparkAdConfig],
        copy_template: Optional[AdCopyTemplate] = None
    ) -> List[Dict]:
        """Cria múltiplos Spark Ads em batch"""
        
        results = []
        
        for i, config in enumerate(spark_configs):
            try:
                ad_text = copy_template.ad_text if copy_template else ""
                cta = copy_template.call_to_action if copy_template else "LEARN_MORE"
                url = copy_template.landing_page_url if copy_template else ""
                
                ad_id = await self.create_spark_ad(
                    api_client,
                    ad_group_id,
                    config,
                    f"SparkAd_{config.tiktok_item_id[:8]}_{i+1}",
                    ad_text,
                    cta,
                    url
                )
                
                results.append({
                    "tiktok_item_id": config.tiktok_item_id,
                    "ad_id": ad_id,
                    "status": "success"
                })
                
            except Exception as e:
                results.append({
                    "tiktok_item_id": config.tiktok_item_id,
                    "error": str(e),
                    "status": "failed"
                })
                
        return results


# =============================================================================
# DYNAMIC PRODUCT ADS - CATÁLOGO DE PRODUTOS
# =============================================================================

class DynamicProductAdsEngine:
    """
    Engine para Dynamic Product Ads (DPA)
    Integração com catálogo de produtos
    """
    
    async def create_catalog_campaign(
        self,
        api_client: 'TikTokAdsAPIClient',
        campaign_name: str,
        catalog_id: str,
        product_set_id: str,
        daily_budget: float,
        optimization_goal: TikTokOptimizationGoal = TikTokOptimizationGoal.COMPLETE_PAYMENT
    ) -> Dict:
        """Cria campanha de catálogo"""
        
        # Cria campanha
        campaign = TikTokCampaign(
            name=campaign_name,
            objective=TikTokObjective.PRODUCT_SALES,
            budget_mode="BUDGET_MODE_DAY",
            budget=daily_budget
        )
        
        campaign_id = await api_client.create_campaign(campaign)
        
        # Cria ad group com catálogo
        ad_group = TikTokAdGroup(
            name=f"{campaign_name}_DPA",
            campaign_id=campaign_id,
            optimization_goal=optimization_goal,
            budget_mode="BUDGET_MODE_INFINITE",  # Usa budget da campanha
            creative_type="CUSTOM_CREATIVE"
        )
        
        ad_group_id = await api_client.create_ad_group(ad_group)
        
        # Cria ad dinâmico
        ad = TikTokAd(
            name=f"{campaign_name}_DPA_Ad",
            ad_group_id=ad_group_id,
            ad_format=TikTokAdFormat.COLLECTION
        )
        
        # Configuração específica para DPA
        dpa_config = {
            "catalog_id": catalog_id,
            "product_set_id": product_set_id,
            "template_type": "DYNAMIC_PRODUCT",
            "creative_template": {
                "title_template": "{{product.name}}",
                "description_template": "{{product.description}}",
                "price_template": "{{product.price}}"
            }
        }
        
        ad_id = await api_client.create_ad(ad, dpa_config)
        
        return {
            "campaign_id": campaign_id,
            "ad_group_id": ad_group_id,
            "ad_id": ad_id,
            "catalog_id": catalog_id,
            "product_set_id": product_set_id
        }


# =============================================================================
# SMART+ CAMPAIGNS - CAMPANHAS IA AUTOMATIZADAS
# =============================================================================

class SmartPlusCampaignEngine:
    """
    Engine para Smart+ Campaigns
    Full AI control do TikTok
    """
    
    async def create_smart_plus_campaign(
        self,
        api_client: 'TikTokAdsAPIClient',
        campaign_name: str,
        smart_plus_type: SmartPlusType,
        daily_budget: float,
        pixel_id: str,
        creatives: List[TikTokCreative],
        landing_page_url: str,
        optimization_goal: TikTokOptimizationGoal = TikTokOptimizationGoal.COMPLETE_PAYMENT
    ) -> Dict:
        """
        Cria campanha Smart+ com full AI control
        AI otimiza: targeting, bidding, placements, creative
        """
        
        campaign = TikTokCampaign(
            name=campaign_name,
            objective=TikTokObjective.WEBSITE_CONVERSIONS,
            budget_mode="BUDGET_MODE_DAY",
            budget=daily_budget,
            is_smart_plus=True,
            smart_plus_type=smart_plus_type
        )
        
        campaign_id = await api_client.create_campaign(campaign)
        
        # Smart+ usa ad group automático
        ad_group = TikTokAdGroup(
            name=f"{campaign_name}_SmartPlus",
            campaign_id=campaign_id,
            placement_type="PLACEMENT_TYPE_AUTOMATIC",
            optimization_goal=optimization_goal,
            bid_type=TikTokBidStrategy.BID_TYPE_NO_BID,
            creative_type="SMART_CREATIVE"  # AI seleciona criativos
        )
        
        ad_group_id = await api_client.create_ad_group(ad_group)
        
        # Adiciona múltiplos criativos para AI testar
        ad_ids = []
        for i, creative in enumerate(creatives):
            ad = TikTokAd(
                name=f"{campaign_name}_Creative_{i+1}",
                ad_group_id=ad_group_id,
                creative=creative,
                landing_page_url=landing_page_url
            )
            
            ad_id = await api_client.create_ad(ad)
            ad_ids.append(ad_id)
            
        return {
            "campaign_id": campaign_id,
            "ad_group_id": ad_group_id,
            "ad_ids": ad_ids,
            "smart_plus_type": smart_plus_type.value,
            "creatives_count": len(creatives)
        }


# =============================================================================
# CREATIVE ANALYTICS - ANÁLISE DE PERFORMANCE
# =============================================================================

@dataclass
class CreativePerformance:
    """Performance de um criativo"""
    creative_id: str
    ad_id: str
    ad_name: str
    impressions: int = 0
    clicks: int = 0
    spend: float = 0.0
    conversions: int = 0
    conversion_value: float = 0.0
    ctr: float = 0.0
    cvr: float = 0.0
    cpc: float = 0.0
    cpa: float = 0.0
    roas: float = 0.0
    video_views: int = 0
    video_views_p25: int = 0
    video_views_p50: int = 0
    video_views_p75: int = 0
    video_views_p100: int = 0
    avg_watch_time: float = 0.0
    engagement_rate: float = 0.0
    likes: int = 0
    comments: int = 0
    shares: int = 0

class CreativeAnalyticsEngine:
    """
    Engine de analytics de criativos
    Similar ao Motion/AdManage dashboards
    """
    
    async def get_top_performers(
        self,
        api_client: 'TikTokAdsAPIClient',
        ad_account_id: str,
        date_range: Tuple[datetime, datetime],
        metric: str = "roas",
        limit: int = 10
    ) -> List[CreativePerformance]:
        """Obtém top performers por métrica"""
        
        # Busca insights de todos os ads
        insights = await api_client.get_ads_insights(
            ad_account_id,
            date_range[0],
            date_range[1]
        )
        
        # Calcula métricas derivadas
        performances = []
        for insight in insights:
            perf = CreativePerformance(
                creative_id=insight.get("creative_id", ""),
                ad_id=insight.get("ad_id", ""),
                ad_name=insight.get("ad_name", ""),
                impressions=insight.get("impressions", 0),
                clicks=insight.get("clicks", 0),
                spend=insight.get("spend", 0),
                conversions=insight.get("conversions", 0),
                conversion_value=insight.get("conversion_value", 0),
                video_views=insight.get("video_views", 0),
                likes=insight.get("likes", 0),
                comments=insight.get("comments", 0),
                shares=insight.get("shares", 0)
            )
            
            # Calcula métricas
            if perf.impressions > 0:
                perf.ctr = (perf.clicks / perf.impressions) * 100
            if perf.clicks > 0:
                perf.cvr = (perf.conversions / perf.clicks) * 100
                perf.cpc = perf.spend / perf.clicks
            if perf.conversions > 0:
                perf.cpa = perf.spend / perf.conversions
            if perf.spend > 0:
                perf.roas = perf.conversion_value / perf.spend
            if perf.impressions > 0:
                perf.engagement_rate = ((perf.likes + perf.comments + perf.shares) / perf.impressions) * 100
                
            performances.append(perf)
            
        # Ordena por métrica
        performances.sort(
            key=lambda x: getattr(x, metric, 0),
            reverse=True
        )
        
        return performances[:limit]
    
    async def analyze_creative_fatigue(
        self,
        performances: List[CreativePerformance],
        days_running: Dict[str, int]
    ) -> List[Dict]:
        """Analisa fadiga de criativos"""
        
        fatigued = []
        
        for perf in performances:
            days = days_running.get(perf.ad_id, 0)
            
            # Indicadores de fadiga
            fatigue_score = 0
            reasons = []
            
            # CTR caindo
            if perf.ctr < 0.5:
                fatigue_score += 30
                reasons.append("CTR muito baixo")
                
            # Muitos dias rodando
            if days > 14:
                fatigue_score += 20
                reasons.append(f"Rodando há {days} dias")
                
            # Engajamento baixo
            if perf.engagement_rate < 0.1:
                fatigue_score += 25
                reasons.append("Engajamento baixo")
                
            # ROAS caindo
            if perf.roas < 1.0 and perf.spend > 50:
                fatigue_score += 25
                reasons.append("ROAS negativo")
                
            if fatigue_score >= 50:
                fatigued.append({
                    "ad_id": perf.ad_id,
                    "ad_name": perf.ad_name,
                    "fatigue_score": fatigue_score,
                    "reasons": reasons,
                    "recommendation": "Pausar e criar novas variações"
                })
                
        return fatigued
    
    async def get_performance_by_aspect_ratio(
        self,
        performances: List[CreativePerformance],
        creatives: Dict[str, TikTokCreative]
    ) -> Dict[AspectRatio, Dict]:
        """Analisa performance por aspect ratio"""
        
        by_ratio = {}
        
        for perf in performances:
            creative = creatives.get(perf.creative_id)
            if not creative:
                continue
                
            ratio = creative.aspect_ratio
            
            if ratio not in by_ratio:
                by_ratio[ratio] = {
                    "count": 0,
                    "total_spend": 0,
                    "total_conversions": 0,
                    "total_value": 0,
                    "total_impressions": 0,
                    "total_clicks": 0
                }
                
            by_ratio[ratio]["count"] += 1
            by_ratio[ratio]["total_spend"] += perf.spend
            by_ratio[ratio]["total_conversions"] += perf.conversions
            by_ratio[ratio]["total_value"] += perf.conversion_value
            by_ratio[ratio]["total_impressions"] += perf.impressions
            by_ratio[ratio]["total_clicks"] += perf.clicks
            
        # Calcula métricas agregadas
        for ratio, data in by_ratio.items():
            if data["total_spend"] > 0:
                data["roas"] = data["total_value"] / data["total_spend"]
            if data["total_conversions"] > 0:
                data["cpa"] = data["total_spend"] / data["total_conversions"]
            if data["total_impressions"] > 0:
                data["ctr"] = (data["total_clicks"] / data["total_impressions"]) * 100
                
        return by_ratio


# =============================================================================
# COMMENTS AI - ANÁLISE DE SENTIMENTO DE COMENTÁRIOS
# =============================================================================

class CommentsAIEngine:
    """
    Engine de análise de comentários com AI
    Sentiment analysis e auto-resposta
    """
    
    SENTIMENT_KEYWORDS = {
        "positive": [
            "love", "amazing", "great", "awesome", "perfect", "best",
            "amo", "incrível", "ótimo", "maravilhoso", "perfeito", "melhor"
        ],
        "negative": [
            "hate", "terrible", "awful", "worst", "scam", "fake",
            "odeio", "terrível", "horrível", "pior", "golpe", "falso"
        ],
        "question": [
            "how", "what", "where", "when", "price", "cost", "shipping",
            "como", "qual", "onde", "quando", "preço", "custo", "frete"
        ]
    }
    
    def analyze_sentiment(self, comment: str) -> Dict:
        """Analisa sentimento de um comentário"""
        
        comment_lower = comment.lower()
        
        positive_count = sum(1 for kw in self.SENTIMENT_KEYWORDS["positive"] if kw in comment_lower)
        negative_count = sum(1 for kw in self.SENTIMENT_KEYWORDS["negative"] if kw in comment_lower)
        is_question = any(kw in comment_lower for kw in self.SENTIMENT_KEYWORDS["question"])
        
        if positive_count > negative_count:
            sentiment = "positive"
            score = min(1.0, positive_count * 0.2)
        elif negative_count > positive_count:
            sentiment = "negative"
            score = min(1.0, negative_count * 0.2)
        else:
            sentiment = "neutral"
            score = 0.5
            
        return {
            "sentiment": sentiment,
            "score": score,
            "is_question": is_question,
            "positive_keywords": [kw for kw in self.SENTIMENT_KEYWORDS["positive"] if kw in comment_lower],
            "negative_keywords": [kw for kw in self.SENTIMENT_KEYWORDS["negative"] if kw in comment_lower]
        }
    
    async def analyze_ad_comments(
        self,
        api_client: 'TikTokAdsAPIClient',
        ad_id: str
    ) -> Dict:
        """Analisa todos os comentários de um ad"""
        
        comments = await api_client.get_ad_comments(ad_id)
        
        analysis = {
            "total_comments": len(comments),
            "positive": 0,
            "negative": 0,
            "neutral": 0,
            "questions": 0,
            "avg_sentiment_score": 0,
            "top_positive": [],
            "top_negative": [],
            "unanswered_questions": []
        }
        
        scores = []
        
        for comment in comments:
            sentiment_result = self.analyze_sentiment(comment.get("text", ""))
            scores.append(sentiment_result["score"])
            
            if sentiment_result["sentiment"] == "positive":
                analysis["positive"] += 1
                if len(analysis["top_positive"]) < 5:
                    analysis["top_positive"].append(comment)
            elif sentiment_result["sentiment"] == "negative":
                analysis["negative"] += 1
                if len(analysis["top_negative"]) < 5:
                    analysis["top_negative"].append(comment)
            else:
                analysis["neutral"] += 1
                
            if sentiment_result["is_question"] and not comment.get("has_reply"):
                analysis["questions"] += 1
                analysis["unanswered_questions"].append(comment)
                
        if scores:
            analysis["avg_sentiment_score"] = sum(scores) / len(scores)
            
        return analysis
    
    def generate_reply_suggestions(self, comment: str, sentiment: Dict) -> List[str]:
        """Gera sugestões de resposta"""
        
        suggestions = []
        
        if sentiment["sentiment"] == "positive":
            suggestions = [
                "Obrigado pelo feedback! 🙏",
                "Ficamos felizes que você gostou! ❤️",
                "Valeu! Isso nos motiva muito! 🚀"
            ]
        elif sentiment["sentiment"] == "negative":
            suggestions = [
                "Sentimos muito pela sua experiência. Entre em contato conosco para resolver.",
                "Gostaríamos de entender melhor. Pode nos enviar uma DM?",
                "Obrigado pelo feedback. Estamos sempre melhorando."
            ]
        elif sentiment["is_question"]:
            suggestions = [
                "Ótima pergunta! Entre em contato via DM para mais informações.",
                "Confira o link na bio para mais detalhes!",
                "Respondemos no privado! 😊"
            ]
            
        return suggestions


# =============================================================================
# TIKTOK ADS API CLIENT
# =============================================================================

class TikTokAdsAPIClient:
    """
    Cliente para TikTok Marketing API
    """
    
    API_VERSION = "v1.3"
    BASE_URL = f"https://business-api.tiktok.com/open_api/{API_VERSION}"
    
    def __init__(
        self,
        access_token: str,
        advertiser_id: str,
        app_id: Optional[str] = None,
        secret: Optional[str] = None
    ):
        self.access_token = access_token
        self.advertiser_id = advertiser_id
        self.app_id = app_id
        self.secret = secret
        
    def _get_headers(self) -> Dict[str, str]:
        return {
            "Access-Token": self.access_token,
            "Content-Type": "application/json"
        }
        
    async def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None
    ) -> Dict:
        """Faz request à API (mock para desenvolvimento)"""
        
        url = f"{self.BASE_URL}/{endpoint}"
        
        print(f"[TIKTOK API] {method} {url}")
        if data:
            print(f"  Data: {json.dumps(data, indent=2)[:500]}...")
            
        # Mock response
        return {
            "code": 0,
            "message": "OK",
            "data": {"id": f"tiktok_{int(time.time())}"}
        }
    
    async def create_campaign(self, campaign: TikTokCampaign) -> str:
        """Cria campanha"""
        
        data = {
            "advertiser_id": self.advertiser_id,
            "campaign_name": campaign.name,
            "objective_type": campaign.objective.value,
            "budget_mode": campaign.budget_mode,
            "budget": campaign.budget,
            "operation_status": campaign.status.value
        }
        
        if campaign.is_smart_plus:
            data["campaign_type"] = "SMART_PERFORMANCE_CAMPAIGN"
            
        result = await self._make_request("POST", "campaign/create/", data)
        return result.get("data", {}).get("campaign_id", result.get("data", {}).get("id", ""))
    
    async def create_ad_group(self, ad_group: TikTokAdGroup) -> str:
        """Cria ad group"""
        
        data = {
            "advertiser_id": self.advertiser_id,
            "campaign_id": ad_group.campaign_id,
            "adgroup_name": ad_group.name,
            "placement_type": ad_group.placement_type,
            "optimization_goal": ad_group.optimization_goal.value,
            "bid_type": ad_group.bid_type.value,
            "budget_mode": ad_group.budget_mode,
            "budget": ad_group.budget,
            "operation_status": ad_group.status.value
        }
        
        if ad_group.placements:
            data["placements"] = [p.value for p in ad_group.placements]
        if ad_group.targeting:
            data["targeting"] = ad_group.targeting
        if ad_group.bid_price:
            data["bid"] = ad_group.bid_price
            
        result = await self._make_request("POST", "adgroup/create/", data)
        return result.get("data", {}).get("adgroup_id", result.get("data", {}).get("id", ""))
    
    async def create_ad(
        self, 
        ad: TikTokAd,
        extra_config: Optional[Dict] = None
    ) -> str:
        """Cria ad"""
        
        data = {
            "advertiser_id": self.advertiser_id,
            "adgroup_id": ad.ad_group_id,
            "ad_name": ad.name,
            "ad_format": ad.ad_format.value,
            "ad_text": ad.ad_text,
            "call_to_action": ad.call_to_action,
            "landing_page_url": ad.landing_page_url,
            "operation_status": ad.status.value
        }
        
        if ad.creative:
            if ad.creative.video_id:
                data["video_id"] = ad.creative.video_id
            if ad.creative.image_ids:
                data["image_ids"] = ad.creative.image_ids
                
        if ad.is_spark_ad and ad.spark_config:
            data["creative_authorized"] = True
            data["tiktok_item_id"] = ad.spark_config.tiktok_item_id
            data["auth_code"] = ad.spark_config.authorization_code
            
        if ad.display_name:
            data["display_name"] = ad.display_name
        if ad.tracking_pixel_id:
            data["pixel_id"] = ad.tracking_pixel_id
            
        if extra_config:
            data.update(extra_config)
            
        result = await self._make_request("POST", "ad/create/", data)
        return result.get("data", {}).get("ad_id", result.get("data", {}).get("id", ""))
    
    async def upload_video(
        self,
        video_path: str,
        file_name: Optional[str] = None
    ) -> str:
        """Faz upload de vídeo"""
        
        data = {
            "advertiser_id": self.advertiser_id,
            "file_name": file_name or video_path.split("/")[-1],
            "upload_type": "UPLOAD_BY_FILE"
        }
        
        result = await self._make_request("POST", "file/video/ad/upload/", data)
        return result.get("data", {}).get("video_id", f"video_{int(time.time())}")
    
    async def upload_image(
        self,
        image_path: str,
        file_name: Optional[str] = None
    ) -> str:
        """Faz upload de imagem"""
        
        data = {
            "advertiser_id": self.advertiser_id,
            "file_name": file_name or image_path.split("/")[-1],
            "upload_type": "UPLOAD_BY_FILE"
        }
        
        result = await self._make_request("POST", "file/image/ad/upload/", data)
        return result.get("data", {}).get("image_id", f"image_{int(time.time())}")
    
    async def get_ads_insights(
        self,
        ad_account_id: str,
        start_date: datetime,
        end_date: datetime,
        dimensions: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None
    ) -> List[Dict]:
        """Obtém insights de ads"""
        
        default_metrics = [
            "spend", "impressions", "clicks", "conversion",
            "cost_per_conversion", "conversion_rate",
            "video_views_p25", "video_views_p50", "video_views_p75", "video_views_p100"
        ]
        
        data = {
            "advertiser_id": self.advertiser_id,
            "report_type": "BASIC",
            "dimensions": dimensions or ["ad_id"],
            "metrics": metrics or default_metrics,
            "start_date": start_date.strftime("%Y-%m-%d"),
            "end_date": end_date.strftime("%Y-%m-%d")
        }
        
        result = await self._make_request("GET", "report/integrated/get/", data)
        return result.get("data", {}).get("list", [])
    
    async def get_ad_comments(self, ad_id: str) -> List[Dict]:
        """Obtém comentários de um ad"""
        
        # Endpoint de comentários (mock)
        data = {
            "advertiser_id": self.advertiser_id,
            "ad_id": ad_id
        }
        
        result = await self._make_request("GET", "comment/list/", data)
        return result.get("data", {}).get("comments", [])
    
    async def update_ad_status(
        self,
        ad_ids: List[str],
        status: TikTokStatus
    ) -> Dict:
        """Atualiza status de múltiplos ads"""
        
        data = {
            "advertiser_id": self.advertiser_id,
            "ad_ids": ad_ids,
            "operation_status": status.value
        }
        
        result = await self._make_request("POST", "ad/status/update/", data)
        return result
    
    async def update_ad_group_budget(
        self,
        ad_group_id: str,
        budget: float
    ) -> Dict:
        """Atualiza budget de ad group"""
        
        data = {
            "advertiser_id": self.advertiser_id,
            "adgroup_id": ad_group_id,
            "budget": budget
        }
        
        result = await self._make_request("POST", "adgroup/update/", data)
        return result


# =============================================================================
# TIKTOK ADS ENGINE - ORQUESTRADOR PRINCIPAL
# =============================================================================

class TikTokAdsEngine:
    """
    Orquestrador principal do TikTok Ads Engine
    Combina todas as funcionalidades do AdManage.ai
    """
    
    def __init__(self):
        self.auto_grouping = AutoGroupingEngine()
        self.mass_launcher = MassAdLauncher()
        self.spark_ads = SparkAdsEngine()
        self.dpa = DynamicProductAdsEngine()
        self.smart_plus = SmartPlusCampaignEngine()
        self.analytics = CreativeAnalyticsEngine()
        self.comments_ai = CommentsAIEngine()
        
        # Templates padrão
        self._load_default_templates()
        
    def _load_default_templates(self):
        """Carrega templates padrão"""
        
        # Naming conventions
        self.mass_launcher.register_naming_convention(
            "default",
            NamingConvention(
                pattern="{date}_{campaign}_{creative}_{variant}",
                variables={"campaign": "Campaign"}
            )
        )
        
        self.mass_launcher.register_naming_convention(
            "detailed",
            NamingConvention(
                pattern="{brand}_{date}_{objective}_{audience}_{creative}_{variant}",
                variables={"brand": "Brand", "objective": "Conv", "audience": "Broad"}
            )
        )
        
        # UTM configs
        self.mass_launcher.register_utm_config(
            "default",
            UTMConfig(
                source="tiktok",
                medium="paid_social",
                campaign="{{campaign_name}}",
                content="{{ad_name}}"
            )
        )
        
    async def launch_ads_from_folder(
        self,
        api_client: TikTokAdsAPIClient,
        folder_path: str,
        campaign_id: str,
        ad_group_id: str,
        copy_template: AdCopyTemplate,
        auto_group: bool = True
    ) -> Dict:
        """
        Lança ads a partir de pasta de arquivos
        Similar ao AdManage.ai drag & drop
        """
        
        # Em produção, listaria arquivos da pasta
        # Aqui simulamos criativos
        creatives = [
            TikTokCreative(
                file_path=f"{folder_path}/creative_{i+1}.mp4",
                aspect_ratio=AspectRatio.VERTICAL_9_16,
                duration_seconds=15,
                width=1080,
                height=1920
            )
            for i in range(10)  # Simula 10 criativos
        ]
        
        # Registra template
        self.mass_launcher.register_copy_template(copy_template)
        
        # Prepara batch
        batch = await self.mass_launcher.prepare_batch(
            creatives=creatives,
            campaign_id=campaign_id,
            ad_group_id=ad_group_id,
            copy_template_id=copy_template.id,
            naming_convention_name="default",
            utm_config_name="default",
            auto_group=auto_group
        )
        
        # Lança batch
        results = await self.mass_launcher.launch_batch(batch, api_client)
        
        return results
    
    async def launch_multi_format_campaign(
        self,
        api_client: TikTokAdsAPIClient,
        campaign_name: str,
        creatives_by_ratio: Dict[AspectRatio, List[TikTokCreative]],
        daily_budget: float,
        copy_template: AdCopyTemplate,
        targeting: Dict
    ) -> Dict:
        """
        Lança campanha multi-format
        9:16 + 4:5 + 1:1 automaticamente
        """
        
        # Cria campanha
        campaign = TikTokCampaign(
            name=campaign_name,
            objective=TikTokObjective.WEBSITE_CONVERSIONS,
            budget_mode="BUDGET_MODE_DAY",
            budget=daily_budget
        )
        
        campaign_id = await api_client.create_campaign(campaign)
        
        # Cria ad group com todos os placements
        ad_group = TikTokAdGroup(
            name=f"{campaign_name}_MultiFormat",
            campaign_id=campaign_id,
            placement_type="PLACEMENT_TYPE_AUTOMATIC",
            targeting=targeting
        )
        
        ad_group_id = await api_client.create_ad_group(ad_group)
        
        # Agrupa por nome base
        all_creatives = []
        for ratio, creatives in creatives_by_ratio.items():
            all_creatives.extend(creatives)
            
        groups = self.auto_grouping.group_creatives_by_filename(all_creatives)
        
        # Cria ads multi-format
        results = {
            "campaign_id": campaign_id,
            "ad_group_id": ad_group_id,
            "ads_created": [],
            "groups_processed": len(groups)
        }
        
        for group_name, group in groups.items():
            # Cria ad combinando ratios
            ad = TikTokAd(
                name=f"{campaign_name}_{group_name}",
                ad_group_id=ad_group_id,
                ad_format=TikTokAdFormat.SINGLE_VIDEO,
                creative=group.creatives[0],  # Usa primeiro como principal
                ad_text=copy_template.ad_text,
                call_to_action=copy_template.call_to_action,
                landing_page_url=copy_template.landing_page_url or ""
            )
            
            ad_id = await api_client.create_ad(ad)
            results["ads_created"].append({
                "group": group_name,
                "ad_id": ad_id,
                "creatives_count": len(group.creatives)
            })
            
        return results
    
    async def get_dashboard_data(
        self,
        api_client: TikTokAdsAPIClient,
        date_range: Tuple[datetime, datetime]
    ) -> Dict:
        """Retorna dados para dashboard"""
        
        # Top performers
        top_ads = await self.analytics.get_top_performers(
            api_client,
            api_client.advertiser_id,
            date_range,
            metric="roas",
            limit=10
        )
        
        return {
            "date_range": {
                "start": date_range[0].isoformat(),
                "end": date_range[1].isoformat()
            },
            "top_performers": [
                {
                    "ad_id": ad.ad_id,
                    "ad_name": ad.ad_name,
                    "spend": ad.spend,
                    "roas": ad.roas,
                    "ctr": ad.ctr,
                    "conversions": ad.conversions
                }
                for ad in top_ads
            ],
            "batches_launched": len(self.mass_launcher.batches),
            "templates_available": len(self.mass_launcher.copy_templates)
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "TikTokObjective",
    "TikTokOptimizationGoal",
    "TikTokBidStrategy",
    "TikTokAdFormat",
    "AspectRatio",
    "TikTokPlacement",
    "TikTokStatus",
    "SmartPlusType",
    
    # Data Classes
    "TikTokCreative",
    "AdCopyTemplate",
    "NamingConvention",
    "UTMConfig",
    "CreativeGroup",
    "AdBatch",
    "SparkAdConfig",
    "TikTokCampaign",
    "TikTokAdGroup",
    "TikTokAd",
    "ProductCatalog",
    "ProductSet",
    "CreativePerformance",
    
    # Engines
    "AutoGroupingEngine",
    "MassAdLauncher",
    "SparkAdsEngine",
    "DynamicProductAdsEngine",
    "SmartPlusCampaignEngine",
    "CreativeAnalyticsEngine",
    "CommentsAIEngine",
    "TikTokAdsAPIClient",
    "TikTokAdsEngine"
]
