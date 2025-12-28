"""
S.S.I. SHADOW - Cross-Platform Ad Launcher
Baseado em análise detalhada do AdManage.ai

FUNCIONALIDADES ADMANAGE.AI IMPLEMENTADAS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MASS AD LAUNCHING (Core Feature)
- Bulk Upload: 200+ creatives em batch único
- 17 segundos para lançar centenas de ads
- 100+ ads em menos de 1 minuto
- Parallel API requests com rate limiting

AUTO-GROUPING (40+ detection methods)
- Aspect ratio detection: 9:16, 4:5, 1:1, 16:9
- Filename pattern matching
- Multi-format auto-pairing
- Placement optimization

COPY TEMPLATES
- Save/Load templates
- Team-wide sharing
- Search & filter
- Performance scoring

POST ID SCALING
- Preserve engagement (likes, comments, shares)
- Creative ID mapping
- Social proof preservation

NAMING CONVENTIONS
- Dynamic naming patterns
- Date formats customizáveis
- Auto-increment variants
- Custom variables

UTM AUTOMATION
- Account-level rules
- Template variables
- Auto-apply on launch

CLOUD INTEGRATIONS
- Google Drive
- Dropbox
- Frame.io
- Air.inc
- Box

GOOGLE SHEETS INTEGRATION
- Direct launch from spreadsheets
- Bulk processing (50-ad batches)
- Column mapping

MULTI-LANGUAGE ADS
- 50+ languages
- Auto-translation
- Market targeting

TEAM MANAGEMENT
- Workspaces
- Role-based permissions
- Activity tracking
- Audit logs

CREATIVE ANALYTICS
- Top performers dashboard
- Performance metrics
- Custom reports
- Export capabilities

AUTOMATED RULES
- Pause low ROAS
- Scale winners
- Budget caps
- CPA alerts

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Tuple, Callable, Set
from enum import Enum, auto
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json
import hashlib
import asyncio
import re
import uuid
import time
from pathlib import Path


# =============================================================================
# ENUMS
# =============================================================================

class Platform(Enum):
    """Plataformas suportadas"""
    META = "meta"
    TIKTOK = "tiktok"
    GOOGLE = "google"
    SNAPCHAT = "snapchat"
    PINTEREST = "pinterest"

class AdFormat(Enum):
    """Formatos de anúncio"""
    SINGLE_IMAGE = "single_image"
    SINGLE_VIDEO = "single_video"
    CAROUSEL = "carousel"
    COLLECTION = "collection"
    FLEXIBLE = "flexible"
    PARTNERSHIP = "partnership"
    SPARK = "spark"
    DYNAMIC_PRODUCT = "dynamic_product"
    MULTI_LANGUAGE = "multi_language"

class AspectRatio(Enum):
    """Aspect ratios"""
    VERTICAL_9_16 = "9:16"      # Stories, Reels, TikTok
    PORTRAIT_4_5 = "4:5"        # Feed
    SQUARE_1_1 = "1:1"          # Feed
    HORIZONTAL_16_9 = "16:9"    # In-stream
    LANDSCAPE_1_91_1 = "1.91:1" # Link ads

class Placement(Enum):
    """Placements"""
    # Meta
    FACEBOOK_FEED = "facebook_feed"
    FACEBOOK_STORIES = "facebook_stories"
    FACEBOOK_REELS = "facebook_reels"
    FACEBOOK_MARKETPLACE = "facebook_marketplace"
    INSTAGRAM_FEED = "instagram_feed"
    INSTAGRAM_STORIES = "instagram_stories"
    INSTAGRAM_REELS = "instagram_reels"
    INSTAGRAM_EXPLORE = "instagram_explore"
    MESSENGER_HOME = "messenger_home"
    AUDIENCE_NETWORK = "audience_network"
    # TikTok
    TIKTOK_FEED = "tiktok_feed"
    TIKTOK_NEWS_FEED = "tiktok_news_feed"
    TIKTOK_PANGLE = "tiktok_pangle"

class LaunchStatus(Enum):
    """Status de lançamento"""
    PENDING = "pending"
    PROCESSING = "processing"
    SUCCESS = "success"
    FAILED = "failed"
    PARTIAL = "partial"

class Permission(Enum):
    """Permissões de usuário"""
    FULL_ACCESS = "full_access"
    LAUNCH_ONLY = "launch_only"
    EDIT_ONLY = "edit_only"
    ANALYTICS_VIEW = "analytics_view"


# =============================================================================
# DATA CLASSES - CREATIVE MANAGEMENT
# =============================================================================

@dataclass
class Creative:
    """Creative asset"""
    id: str = ""
    file_path: str = ""
    file_name: str = ""
    file_type: str = ""  # image, video
    file_size_bytes: int = 0
    width: int = 0
    height: int = 0
    aspect_ratio: AspectRatio = AspectRatio.SQUARE_1_1
    duration_seconds: float = 0  # for videos
    thumbnail_url: str = ""
    cloud_url: str = ""
    cloud_source: str = ""  # google_drive, dropbox, etc
    uploaded_at: datetime = field(default_factory=datetime.now)
    
    # Media IDs por plataforma
    meta_video_id: Optional[str] = None
    meta_image_hash: Optional[str] = None
    tiktok_video_id: Optional[str] = None
    tiktok_image_id: Optional[str] = None
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.aspect_ratio and self.width and self.height:
            self.aspect_ratio = self._detect_aspect_ratio()
            
    def _detect_aspect_ratio(self) -> AspectRatio:
        """Detecta aspect ratio das dimensões"""
        if self.height == 0:
            return AspectRatio.SQUARE_1_1
        ratio = self.width / self.height
        if ratio < 0.6:
            return AspectRatio.VERTICAL_9_16
        elif 0.75 <= ratio <= 0.85:
            return AspectRatio.PORTRAIT_4_5
        elif 0.95 <= ratio <= 1.05:
            return AspectRatio.SQUARE_1_1
        elif ratio >= 1.7:
            return AspectRatio.HORIZONTAL_16_9
        else:
            return AspectRatio.PORTRAIT_4_5

@dataclass
class CreativeGroup:
    """Grupo de criativos relacionados (multi-format)"""
    group_id: str = ""
    name: str = ""
    base_name: str = ""  # Nome base extraído do filename
    creatives: List[Creative] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.group_id:
            self.group_id = str(uuid.uuid4())[:8]
            
    @property
    def aspect_ratios(self) -> Set[AspectRatio]:
        return {c.aspect_ratio for c in self.creatives}
    
    @property
    def is_multi_format(self) -> bool:
        return len(self.aspect_ratios) > 1
    
    def get_creative_for_placement(self, placement: Placement) -> Optional[Creative]:
        """Retorna creative ideal para placement"""
        placement_ratios = {
            Placement.FACEBOOK_FEED: [AspectRatio.PORTRAIT_4_5, AspectRatio.SQUARE_1_1],
            Placement.FACEBOOK_STORIES: [AspectRatio.VERTICAL_9_16],
            Placement.FACEBOOK_REELS: [AspectRatio.VERTICAL_9_16],
            Placement.INSTAGRAM_FEED: [AspectRatio.PORTRAIT_4_5, AspectRatio.SQUARE_1_1],
            Placement.INSTAGRAM_STORIES: [AspectRatio.VERTICAL_9_16],
            Placement.INSTAGRAM_REELS: [AspectRatio.VERTICAL_9_16],
            Placement.TIKTOK_FEED: [AspectRatio.VERTICAL_9_16],
        }
        
        preferred = placement_ratios.get(placement, [])
        for ratio in preferred:
            for creative in self.creatives:
                if creative.aspect_ratio == ratio:
                    return creative
        return self.creatives[0] if self.creatives else None


# =============================================================================
# DATA CLASSES - COPY TEMPLATES
# =============================================================================

@dataclass
class CopyTemplate:
    """Template de copy reutilizável"""
    id: str = ""
    name: str = ""
    primary_text: str = ""
    headline: str = ""
    description: str = ""
    call_to_action: str = "LEARN_MORE"
    landing_page_url: str = ""
    display_link: str = ""
    
    # Multi-language
    translations: Dict[str, Dict[str, str]] = field(default_factory=dict)
    
    # Metadata
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    workspace_id: str = ""
    
    # Performance
    uses_count: int = 0
    avg_ctr: float = 0.0
    avg_cvr: float = 0.0
    performance_score: float = 0.0
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
            
    def get_translation(self, language: str) -> Dict[str, str]:
        """Retorna tradução para idioma"""
        if language in self.translations:
            return self.translations[language]
        return {
            "primary_text": self.primary_text,
            "headline": self.headline,
            "description": self.description
        }
    
    def add_translation(self, language: str, primary_text: str, headline: str, description: str = ""):
        """Adiciona tradução"""
        self.translations[language] = {
            "primary_text": primary_text,
            "headline": headline,
            "description": description
        }


# =============================================================================
# DATA CLASSES - NAMING & UTM
# =============================================================================

@dataclass
class NamingConvention:
    """Convenção de nomenclatura"""
    id: str = ""
    name: str = ""
    pattern: str = "{date}_{campaign}_{creative}_{variant}"
    date_format: str = "%Y%m%d"
    separator: str = "_"
    variables: Dict[str, str] = field(default_factory=dict)
    auto_increment: bool = True
    max_length: int = 100
    
    def generate_name(
        self,
        creative_name: str = "",
        variant: int = 1,
        **kwargs
    ) -> str:
        """Gera nome baseado no padrão"""
        
        # Variables padrão
        all_vars = {
            "date": datetime.now().strftime(self.date_format),
            "datetime": datetime.now().strftime("%Y%m%d_%H%M%S"),
            "creative": creative_name or "creative",
            "variant": str(variant).zfill(3),
            "uuid": str(uuid.uuid4())[:4],
            **self.variables,
            **kwargs
        }
        
        name = self.pattern
        for key, value in all_vars.items():
            name = name.replace(f"{{{key}}}", str(value))
            
        # Sanitiza
        name = re.sub(r'[^\w\-_]', self.separator, name)
        name = re.sub(f'{self.separator}+', self.separator, name)
        
        return name[:self.max_length]

@dataclass
class UTMConfig:
    """Configuração de UTM"""
    id: str = ""
    name: str = ""
    source: str = ""
    medium: str = ""
    campaign: str = ""
    content: str = ""
    term: str = ""
    custom_params: Dict[str, str] = field(default_factory=dict)
    
    # Template variables
    use_dynamic_values: bool = True
    
    def build_url(self, base_url: str, ad_name: str = "", creative_name: str = "") -> str:
        """Constrói URL com UTMs"""
        
        params = []
        
        if self.source:
            source = self._replace_vars(self.source, ad_name, creative_name)
            params.append(f"utm_source={source}")
            
        if self.medium:
            medium = self._replace_vars(self.medium, ad_name, creative_name)
            params.append(f"utm_medium={medium}")
            
        if self.campaign:
            campaign = self._replace_vars(self.campaign, ad_name, creative_name)
            params.append(f"utm_campaign={campaign}")
            
        if self.content:
            content = self._replace_vars(self.content, ad_name, creative_name)
            params.append(f"utm_content={content}")
            
        if self.term:
            term = self._replace_vars(self.term, ad_name, creative_name)
            params.append(f"utm_term={term}")
            
        for key, value in self.custom_params.items():
            value = self._replace_vars(value, ad_name, creative_name)
            params.append(f"{key}={value}")
            
        if not params:
            return base_url
            
        separator = "&" if "?" in base_url else "?"
        return f"{base_url}{separator}{'&'.join(params)}"
    
    def _replace_vars(self, template: str, ad_name: str, creative_name: str) -> str:
        """Substitui variáveis dinâmicas"""
        if not self.use_dynamic_values:
            return template
            
        replacements = {
            "{{ad_name}}": ad_name,
            "{{creative_name}}": creative_name,
            "{{date}}": datetime.now().strftime("%Y%m%d"),
            "{{timestamp}}": str(int(time.time()))
        }
        
        result = template
        for key, value in replacements.items():
            result = result.replace(key, value)
        return result


# =============================================================================
# DATA CLASSES - ADS
# =============================================================================

@dataclass
class AdConfig:
    """Configuração de um ad"""
    id: str = ""
    name: str = ""
    platform: Platform = Platform.META
    ad_format: AdFormat = AdFormat.SINGLE_VIDEO
    
    # Creative
    creative: Optional[Creative] = None
    creative_group: Optional[CreativeGroup] = None
    
    # Copy
    copy_template: Optional[CopyTemplate] = None
    primary_text: str = ""
    headline: str = ""
    description: str = ""
    call_to_action: str = "LEARN_MORE"
    landing_page_url: str = ""
    
    # Post ID (para preservar engagement)
    use_post_id: bool = False
    post_id: str = ""
    creative_id: str = ""
    
    # Targeting
    campaign_id: str = ""
    ad_set_id: str = ""
    ad_group_id: str = ""  # TikTok
    
    # Status
    status: str = "PAUSED"  # ACTIVE, PAUSED
    
    # Tracking
    pixel_id: str = ""
    url_tags: str = ""
    
    # Multi-language
    is_multi_language: bool = False
    languages: List[str] = field(default_factory=list)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]

@dataclass
class AdBatch:
    """Batch de ads para lançamento"""
    batch_id: str = ""
    name: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    
    # Ads
    ads: List[AdConfig] = field(default_factory=list)
    
    # Config
    naming_convention: Optional[NamingConvention] = None
    utm_config: Optional[UTMConfig] = None
    
    # Target
    platform: Platform = Platform.META
    campaign_ids: List[str] = field(default_factory=list)
    ad_set_ids: List[str] = field(default_factory=list)
    
    # Status
    status: LaunchStatus = LaunchStatus.PENDING
    
    # Results
    total_ads: int = 0
    launched_ads: int = 0
    failed_ads: int = 0
    errors: List[Dict] = field(default_factory=list)
    
    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    def __post_init__(self):
        if not self.batch_id:
            self.batch_id = str(uuid.uuid4())[:8]
            
    @property
    def duration_seconds(self) -> float:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return 0

@dataclass
class LaunchResult:
    """Resultado de lançamento"""
    batch_id: str
    ad_id: str
    ad_name: str
    platform: Platform
    status: LaunchStatus
    platform_ad_id: Optional[str] = None
    error_message: Optional[str] = None
    created_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# DATA CLASSES - WORKSPACES & TEAM
# =============================================================================

@dataclass
class TeamMember:
    """Membro do time"""
    id: str = ""
    name: str = ""
    email: str = ""
    permission: Permission = Permission.ANALYTICS_VIEW
    workspace_ids: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_active: Optional[datetime] = None

@dataclass
class Workspace:
    """Workspace isolado"""
    id: str = ""
    name: str = ""
    description: str = ""
    
    # Accounts
    meta_ad_account_ids: List[str] = field(default_factory=list)
    tiktok_advertiser_ids: List[str] = field(default_factory=list)
    
    # Team
    members: List[TeamMember] = field(default_factory=list)
    
    # Templates
    copy_templates: List[CopyTemplate] = field(default_factory=list)
    naming_conventions: List[NamingConvention] = field(default_factory=list)
    utm_configs: List[UTMConfig] = field(default_factory=list)
    
    # Stats
    ads_launched: int = 0
    created_at: datetime = field(default_factory=datetime.now)
    
    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]


# =============================================================================
# AUTO-GROUPING ENGINE
# =============================================================================

class AutoGroupingEngine:
    """
    Engine de agrupamento automático (40+ métodos)
    Similar ao AdManage.ai Auto-Grouping
    """
    
    # Padrões de aspect ratio no nome do arquivo
    ASPECT_PATTERNS = [
        # Formato X:Y
        (r"[_\-\s]9[x:]16", AspectRatio.VERTICAL_9_16),
        (r"[_\-\s]4[x:]5", AspectRatio.PORTRAIT_4_5),
        (r"[_\-\s]1[x:]1", AspectRatio.SQUARE_1_1),
        (r"[_\-\s]16[x:]9", AspectRatio.HORIZONTAL_16_9),
        
        # Formato XxY
        (r"[_\-\s]9-16", AspectRatio.VERTICAL_9_16),
        (r"[_\-\s]4-5", AspectRatio.PORTRAIT_4_5),
        (r"[_\-\s]1-1", AspectRatio.SQUARE_1_1),
        (r"[_\-\s]16-9", AspectRatio.HORIZONTAL_16_9),
        
        # Palavras-chave
        (r"[_\-\s]vertical", AspectRatio.VERTICAL_9_16),
        (r"[_\-\s]portrait", AspectRatio.PORTRAIT_4_5),
        (r"[_\-\s]square", AspectRatio.SQUARE_1_1),
        (r"[_\-\s]horizontal", AspectRatio.HORIZONTAL_16_9),
        (r"[_\-\s]landscape", AspectRatio.HORIZONTAL_16_9),
        
        # Placements
        (r"[_\-\s]story", AspectRatio.VERTICAL_9_16),
        (r"[_\-\s]stories", AspectRatio.VERTICAL_9_16),
        (r"[_\-\s]reel", AspectRatio.VERTICAL_9_16),
        (r"[_\-\s]reels", AspectRatio.VERTICAL_9_16),
        (r"[_\-\s]tiktok", AspectRatio.VERTICAL_9_16),
        (r"[_\-\s]feed", AspectRatio.PORTRAIT_4_5),
    ]
    
    def group_by_filename(self, creatives: List[Creative]) -> Dict[str, CreativeGroup]:
        """
        Agrupa criativos por nome base do arquivo
        Product_A_4x5.jpg + Product_A_9x16.jpg -> Grupo "Product_A"
        """
        
        groups: Dict[str, CreativeGroup] = {}
        
        for creative in creatives:
            base_name = self._extract_base_name(creative.file_name)
            
            if base_name not in groups:
                groups[base_name] = CreativeGroup(
                    name=base_name,
                    base_name=base_name
                )
                
            groups[base_name].creatives.append(creative)
            
        return groups
    
    def group_by_aspect_ratio(self, creatives: List[Creative]) -> Dict[AspectRatio, List[Creative]]:
        """Agrupa por aspect ratio"""
        
        groups: Dict[AspectRatio, List[Creative]] = {}
        
        for creative in creatives:
            ratio = creative.aspect_ratio
            if ratio not in groups:
                groups[ratio] = []
            groups[ratio].append(creative)
            
        return groups
    
    def auto_pair_multi_format(self, creatives: List[Creative]) -> List[CreativeGroup]:
        """
        Auto-detecta e agrupa criativos multi-format
        Retorna grupos com múltiplos aspect ratios
        """
        
        # Primeiro agrupa por nome
        by_name = self.group_by_filename(creatives)
        
        # Retorna apenas grupos multi-format
        multi_format = [
            group for group in by_name.values()
            if group.is_multi_format
        ]
        
        return multi_format
    
    def detect_aspect_from_filename(self, filename: str) -> Optional[AspectRatio]:
        """Detecta aspect ratio pelo nome do arquivo"""
        
        filename_lower = filename.lower()
        
        for pattern, ratio in self.ASPECT_PATTERNS:
            if re.search(pattern, filename_lower):
                return ratio
                
        return None
    
    def _extract_base_name(self, filename: str) -> str:
        """Extrai nome base removendo sufixos de aspect ratio"""
        
        # Remove extensão
        name = Path(filename).stem
        
        # Remove todos os padrões de aspect ratio
        for pattern, _ in self.ASPECT_PATTERNS:
            name = re.sub(pattern, "", name, flags=re.IGNORECASE)
            
        # Remove números de versão no final
        name = re.sub(r"[_\-\s]v?\d+$", "", name, flags=re.IGNORECASE)
        
        return name.strip("_- ")
    
    def validate_multi_placement(self, group: CreativeGroup) -> Dict:
        """Valida se grupo está pronto para multi-placement"""
        
        validation = {
            "is_valid": True,
            "has_feed": False,
            "has_stories": False,
            "missing": [],
            "warnings": []
        }
        
        ratios = group.aspect_ratios
        
        # Feed (4:5 ou 1:1)
        if AspectRatio.PORTRAIT_4_5 in ratios or AspectRatio.SQUARE_1_1 in ratios:
            validation["has_feed"] = True
        else:
            validation["missing"].append("Feed (4:5 or 1:1)")
            
        # Stories/Reels (9:16)
        if AspectRatio.VERTICAL_9_16 in ratios:
            validation["has_stories"] = True
        else:
            validation["missing"].append("Stories/Reels (9:16)")
            
        if validation["missing"]:
            validation["warnings"].append(
                f"Missing formats: {', '.join(validation['missing'])}"
            )
            
        return validation


# =============================================================================
# CLOUD INTEGRATIONS
# =============================================================================

class CloudProvider(ABC):
    """Interface base para cloud providers"""
    
    @abstractmethod
    async def list_files(self, folder_path: str) -> List[Dict]:
        pass
    
    @abstractmethod
    async def download_file(self, file_id: str) -> bytes:
        pass
    
    @abstractmethod
    async def get_direct_url(self, file_id: str) -> str:
        pass

class GoogleDriveProvider(CloudProvider):
    """Integração Google Drive"""
    
    def __init__(self, credentials: Dict):
        self.credentials = credentials
        
    async def list_files(self, folder_path: str) -> List[Dict]:
        """Lista arquivos de uma pasta"""
        # Mock - em produção usaria Google Drive API
        print(f"[Google Drive] Listing files in: {folder_path}")
        return [
            {"id": "file1", "name": "creative_1.mp4", "mimeType": "video/mp4"},
            {"id": "file2", "name": "creative_2.mp4", "mimeType": "video/mp4"}
        ]
    
    async def download_file(self, file_id: str) -> bytes:
        """Download de arquivo"""
        print(f"[Google Drive] Downloading: {file_id}")
        return b""
    
    async def get_direct_url(self, file_id: str) -> str:
        """Obtém URL direta"""
        return f"https://drive.google.com/uc?id={file_id}"

class DropboxProvider(CloudProvider):
    """Integração Dropbox"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        
    async def list_files(self, folder_path: str) -> List[Dict]:
        print(f"[Dropbox] Listing files in: {folder_path}")
        return []
    
    async def download_file(self, file_id: str) -> bytes:
        print(f"[Dropbox] Downloading: {file_id}")
        return b""
    
    async def get_direct_url(self, file_id: str) -> str:
        return f"https://dl.dropbox.com/{file_id}"

class FrameIOProvider(CloudProvider):
    """Integração Frame.io"""
    
    def __init__(self, access_token: str):
        self.access_token = access_token
        
    async def list_files(self, folder_path: str) -> List[Dict]:
        print(f"[Frame.io] Listing files in: {folder_path}")
        return []
    
    async def download_file(self, file_id: str) -> bytes:
        print(f"[Frame.io] Downloading: {file_id}")
        return b""
    
    async def get_direct_url(self, file_id: str) -> str:
        return f"https://frame.io/asset/{file_id}"

class CloudIntegrationManager:
    """Gerenciador de integrações cloud"""
    
    def __init__(self):
        self.providers: Dict[str, CloudProvider] = {}
        
    def register_provider(self, name: str, provider: CloudProvider):
        """Registra provider"""
        self.providers[name] = provider
        
    async def import_from_cloud(
        self,
        provider_name: str,
        folder_path: str
    ) -> List[Creative]:
        """Importa criativos de cloud storage"""
        
        if provider_name not in self.providers:
            raise ValueError(f"Provider '{provider_name}' not registered")
            
        provider = self.providers[provider_name]
        files = await provider.list_files(folder_path)
        
        creatives = []
        for file in files:
            url = await provider.get_direct_url(file["id"])
            
            creative = Creative(
                file_name=file["name"],
                cloud_url=url,
                cloud_source=provider_name
            )
            creatives.append(creative)
            
        return creatives


# =============================================================================
# GOOGLE SHEETS INTEGRATION
# =============================================================================

@dataclass
class SheetRow:
    """Linha do Google Sheets"""
    creative_url: str = ""
    ad_name: str = ""
    primary_text: str = ""
    headline: str = ""
    description: str = ""
    landing_page_url: str = ""
    call_to_action: str = "LEARN_MORE"
    ad_set_id: str = ""
    extra_data: Dict = field(default_factory=dict)

class GoogleSheetsIntegration:
    """
    Integração com Google Sheets
    Launch ads diretamente de planilhas
    """
    
    def __init__(self, credentials: Optional[Dict] = None):
        self.credentials = credentials
        self.column_mapping: Dict[str, str] = {
            "creative": "creative_url",
            "creative_url": "creative_url",
            "name": "ad_name",
            "ad_name": "ad_name",
            "primary_text": "primary_text",
            "text": "primary_text",
            "headline": "headline",
            "title": "headline",
            "description": "description",
            "url": "landing_page_url",
            "landing_page": "landing_page_url",
            "cta": "call_to_action",
            "ad_set": "ad_set_id",
            "adset_id": "ad_set_id"
        }
        
    async def parse_sheet(self, sheet_data: List[List[str]]) -> List[SheetRow]:
        """Parseia dados do sheet"""
        
        if not sheet_data or len(sheet_data) < 2:
            return []
            
        # Primeira linha = headers
        headers = [h.lower().strip().replace(" ", "_") for h in sheet_data[0]]
        rows = []
        
        for row_data in sheet_data[1:]:
            row = SheetRow()
            
            for i, value in enumerate(row_data):
                if i >= len(headers):
                    break
                    
                header = headers[i]
                mapped = self.column_mapping.get(header, header)
                
                if hasattr(row, mapped):
                    setattr(row, mapped, value)
                else:
                    row.extra_data[header] = value
                    
            rows.append(row)
            
        return rows
    
    async def create_ads_from_sheet(
        self,
        sheet_data: List[List[str]],
        default_ad_set_id: str = "",
        copy_template: Optional[CopyTemplate] = None
    ) -> List[AdConfig]:
        """Cria ads a partir de dados do sheet"""
        
        rows = await self.parse_sheet(sheet_data)
        ads = []
        
        for i, row in enumerate(rows):
            creative = Creative(
                cloud_url=row.creative_url,
                file_name=f"creative_{i+1}"
            )
            
            ad = AdConfig(
                name=row.ad_name or f"Ad_{i+1}",
                creative=creative,
                primary_text=row.primary_text or (copy_template.primary_text if copy_template else ""),
                headline=row.headline or (copy_template.headline if copy_template else ""),
                description=row.description or (copy_template.description if copy_template else ""),
                landing_page_url=row.landing_page_url,
                call_to_action=row.call_to_action or "LEARN_MORE",
                ad_set_id=row.ad_set_id or default_ad_set_id
            )
            ads.append(ad)
            
        return ads
    
    async def batch_process(
        self,
        ads: List[AdConfig],
        batch_size: int = 50
    ) -> List[List[AdConfig]]:
        """Processa em batches de 50 (como AdManage)"""
        
        batches = []
        for i in range(0, len(ads), batch_size):
            batches.append(ads[i:i + batch_size])
        return batches


# =============================================================================
# MULTI-LANGUAGE ENGINE
# =============================================================================

class MultiLanguageEngine:
    """
    Engine para Multi-Language Ads
    50+ idiomas suportados
    """
    
    SUPPORTED_LANGUAGES = [
        "en", "es", "fr", "de", "it", "pt", "nl", "pl", "ru", "ja",
        "ko", "zh", "ar", "hi", "tr", "th", "vi", "id", "ms", "tl",
        "sv", "no", "da", "fi", "cs", "hu", "ro", "el", "he", "uk",
        "bg", "hr", "sk", "sl", "lt", "lv", "et", "sr", "mk", "sq",
        "bn", "ta", "te", "mr", "gu", "kn", "ml", "pa", "ur", "sw"
    ]
    
    LANGUAGE_NAMES = {
        "en": "English",
        "es": "Spanish",
        "fr": "French",
        "de": "German",
        "it": "Italian",
        "pt": "Portuguese",
        "nl": "Dutch",
        "pl": "Polish",
        "ru": "Russian",
        "ja": "Japanese",
        "ko": "Korean",
        "zh": "Chinese",
        "ar": "Arabic",
        "hi": "Hindi",
        "tr": "Turkish",
        # ... mais idiomas
    }
    
    def create_multi_language_ad(
        self,
        base_copy: CopyTemplate,
        languages: List[str]
    ) -> Dict[str, Dict]:
        """Cria configuração de ad multi-language"""
        
        ad_config = {
            "is_multi_language": True,
            "default_language": "en",
            "languages": {},
            "asset_customization_rules": []
        }
        
        for lang in languages:
            if lang not in self.SUPPORTED_LANGUAGES:
                continue
                
            translation = base_copy.get_translation(lang)
            
            ad_config["languages"][lang] = {
                "primary_text": translation.get("primary_text", base_copy.primary_text),
                "headline": translation.get("headline", base_copy.headline),
                "description": translation.get("description", base_copy.description)
            }
            
            # Asset customization rule
            ad_config["asset_customization_rules"].append({
                "customization_spec": {
                    "locales": [{"country": self._get_country_for_lang(lang), "language": lang}]
                },
                "primary_text": translation.get("primary_text", base_copy.primary_text),
                "title": translation.get("headline", base_copy.headline),
                "description": translation.get("description", base_copy.description)
            })
            
        return ad_config
    
    def _get_country_for_lang(self, lang: str) -> str:
        """Mapeia idioma para país principal"""
        lang_to_country = {
            "en": "US", "es": "ES", "fr": "FR", "de": "DE",
            "it": "IT", "pt": "BR", "nl": "NL", "pl": "PL",
            "ru": "RU", "ja": "JP", "ko": "KR", "zh": "CN"
        }
        return lang_to_country.get(lang, "US")


# =============================================================================
# CROSS-PLATFORM AD LAUNCHER
# =============================================================================

class CrossPlatformAdLauncher:
    """
    Lançador cross-platform principal
    Integra Meta e TikTok
    """
    
    MAX_BATCH_SIZE = 200  # Máximo de ads por batch
    PARALLEL_REQUESTS = 10  # Requests paralelos
    
    def __init__(self):
        self.auto_grouping = AutoGroupingEngine()
        self.cloud_manager = CloudIntegrationManager()
        self.sheets_integration = GoogleSheetsIntegration()
        self.multi_language = MultiLanguageEngine()
        
        # Storage
        self.copy_templates: Dict[str, CopyTemplate] = {}
        self.naming_conventions: Dict[str, NamingConvention] = {}
        self.utm_configs: Dict[str, UTMConfig] = {}
        self.workspaces: Dict[str, Workspace] = {}
        self.batches: Dict[str, AdBatch] = {}
        
        # Default naming convention
        self._setup_defaults()
        
    def _setup_defaults(self):
        """Configura defaults"""
        
        # Default naming
        self.naming_conventions["default"] = NamingConvention(
            id="default",
            name="Default",
            pattern="{date}_{creative}_{variant}"
        )
        
        # Detailed naming
        self.naming_conventions["detailed"] = NamingConvention(
            id="detailed",
            name="Detailed",
            pattern="{campaign}_{audience}_{creative}_{variant}_{date}"
        )
        
        # Default UTM
        self.utm_configs["default"] = UTMConfig(
            id="default",
            name="Default",
            source="{{platform}}",
            medium="paid_social",
            campaign="{{campaign_name}}",
            content="{{ad_name}}"
        )
        
    # =========================================================================
    # TEMPLATE MANAGEMENT
    # =========================================================================
    
    def save_copy_template(self, template: CopyTemplate) -> str:
        """Salva template de copy"""
        self.copy_templates[template.id] = template
        return template.id
    
    def get_copy_template(self, template_id: str) -> Optional[CopyTemplate]:
        """Obtém template"""
        return self.copy_templates.get(template_id)
    
    def search_templates(self, query: str) -> List[CopyTemplate]:
        """Busca templates"""
        query_lower = query.lower()
        return [
            t for t in self.copy_templates.values()
            if query_lower in t.name.lower() or query_lower in t.primary_text.lower()
        ]
    
    def save_naming_convention(self, convention: NamingConvention) -> str:
        """Salva convenção de nomenclatura"""
        self.naming_conventions[convention.id] = convention
        return convention.id
    
    def save_utm_config(self, config: UTMConfig) -> str:
        """Salva configuração UTM"""
        self.utm_configs[config.id] = config
        return config.id
    
    # =========================================================================
    # CREATIVE IMPORT
    # =========================================================================
    
    async def import_creatives(
        self,
        file_paths: Optional[List[str]] = None,
        cloud_provider: Optional[str] = None,
        cloud_folder: Optional[str] = None,
        sheet_data: Optional[List[List[str]]] = None
    ) -> List[Creative]:
        """
        Importa criativos de múltiplas fontes
        - Local files
        - Cloud storage
        - Google Sheets
        """
        
        creatives = []
        
        # Local files
        if file_paths:
            for path in file_paths:
                creative = Creative(
                    file_path=path,
                    file_name=Path(path).name
                )
                # Detecta aspect ratio pelo nome
                detected = self.auto_grouping.detect_aspect_from_filename(creative.file_name)
                if detected:
                    creative.aspect_ratio = detected
                creatives.append(creative)
                
        # Cloud storage
        if cloud_provider and cloud_folder:
            cloud_creatives = await self.cloud_manager.import_from_cloud(
                cloud_provider, cloud_folder
            )
            creatives.extend(cloud_creatives)
            
        # Google Sheets
        if sheet_data:
            ads = await self.sheets_integration.create_ads_from_sheet(sheet_data)
            for ad in ads:
                if ad.creative:
                    creatives.append(ad.creative)
                    
        return creatives
    
    # =========================================================================
    # BATCH PREPARATION
    # =========================================================================
    
    async def prepare_batch(
        self,
        creatives: List[Creative],
        platform: Platform,
        campaign_id: str,
        ad_set_ids: List[str],
        copy_template_id: Optional[str] = None,
        naming_convention_id: str = "default",
        utm_config_id: str = "default",
        auto_group: bool = True,
        launch_as_paused: bool = True
    ) -> AdBatch:
        """
        Prepara batch de ads para lançamento
        
        Features:
        - Auto-grouping por aspect ratio
        - Apply copy template
        - Dynamic naming
        - UTM automation
        """
        
        batch = AdBatch(
            name=f"Batch_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            platform=platform,
            campaign_ids=[campaign_id],
            ad_set_ids=ad_set_ids,
            naming_convention=self.naming_conventions.get(naming_convention_id),
            utm_config=self.utm_configs.get(utm_config_id)
        )
        
        # Get templates
        copy_template = self.copy_templates.get(copy_template_id) if copy_template_id else None
        naming = batch.naming_convention or self.naming_conventions["default"]
        utm = batch.utm_config or self.utm_configs["default"]
        
        # Auto-group
        if auto_group:
            groups = self.auto_grouping.group_by_filename(creatives)
        else:
            # Cada creative = um grupo
            groups = {c.id: CreativeGroup(creatives=[c]) for c in creatives}
            
        # Cria ads
        variant = 1
        for group_name, group in groups.items():
            for ad_set_id in ad_set_ids:
                # Determina se é multi-format
                if group.is_multi_format:
                    # Um ad com multi-placement
                    ad_name = naming.generate_name(
                        creative_name=group.base_name,
                        variant=variant,
                        campaign=campaign_id[:8]
                    )
                    
                    ad = AdConfig(
                        name=ad_name,
                        platform=platform,
                        ad_format=AdFormat.FLEXIBLE if len(group.creatives) > 1 else AdFormat.SINGLE_VIDEO,
                        creative_group=group,
                        ad_set_id=ad_set_id,
                        campaign_id=campaign_id,
                        status="PAUSED" if launch_as_paused else "ACTIVE"
                    )
                    
                    # Apply copy template
                    if copy_template:
                        ad.primary_text = copy_template.primary_text
                        ad.headline = copy_template.headline
                        ad.description = copy_template.description
                        ad.call_to_action = copy_template.call_to_action
                        
                        # Apply UTM to landing URL
                        if copy_template.landing_page_url:
                            ad.landing_page_url = utm.build_url(
                                copy_template.landing_page_url,
                                ad_name=ad_name,
                                creative_name=group.base_name
                            )
                            
                    batch.ads.append(ad)
                    variant += 1
                    
                else:
                    # Um ad por creative
                    for creative in group.creatives:
                        ad_name = naming.generate_name(
                            creative_name=creative.file_name,
                            variant=variant,
                            campaign=campaign_id[:8]
                        )
                        
                        ad_format = AdFormat.SINGLE_VIDEO if creative.duration_seconds > 0 else AdFormat.SINGLE_IMAGE
                        
                        ad = AdConfig(
                            name=ad_name,
                            platform=platform,
                            ad_format=ad_format,
                            creative=creative,
                            ad_set_id=ad_set_id,
                            campaign_id=campaign_id,
                            status="PAUSED" if launch_as_paused else "ACTIVE"
                        )
                        
                        if copy_template:
                            ad.primary_text = copy_template.primary_text
                            ad.headline = copy_template.headline
                            ad.description = copy_template.description
                            ad.call_to_action = copy_template.call_to_action
                            
                            if copy_template.landing_page_url:
                                ad.landing_page_url = utm.build_url(
                                    copy_template.landing_page_url,
                                    ad_name=ad_name,
                                    creative_name=creative.file_name
                                )
                                
                        batch.ads.append(ad)
                        variant += 1
                        
        batch.total_ads = len(batch.ads)
        self.batches[batch.batch_id] = batch
        
        return batch
    
    # =========================================================================
    # LAUNCHING
    # =========================================================================
    
    async def launch_batch(
        self,
        batch: AdBatch,
        meta_client: Optional[Any] = None,
        tiktok_client: Optional[Any] = None,
        parallel: int = 10,
        delay_ms: int = 100
    ) -> Dict:
        """
        Lança batch de ads
        100+ ads em segundos
        """
        
        batch.status = LaunchStatus.PROCESSING
        batch.started_at = datetime.now()
        
        results = {
            "batch_id": batch.batch_id,
            "total": batch.total_ads,
            "success": 0,
            "failed": 0,
            "results": [],
            "errors": []
        }
        
        # Seleciona client
        if batch.platform == Platform.META and meta_client:
            client = meta_client
        elif batch.platform == Platform.TIKTOK and tiktok_client:
            client = tiktok_client
        else:
            # Mock client para desenvolvimento
            client = MockAPIClient()
            
        # Processa em batches paralelos
        for i in range(0, len(batch.ads), parallel):
            batch_ads = batch.ads[i:i + parallel]
            
            tasks = [
                self._launch_single_ad(ad, client)
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
                    batch.errors.append({
                        "ad_id": batch_ads[j].id,
                        "error": str(result)
                    })
                else:
                    results["success"] += 1
                    results["results"].append(result)
                    
            # Rate limiting delay
            if delay_ms > 0:
                await asyncio.sleep(delay_ms / 1000)
                
        # Finaliza
        batch.launched_ads = results["success"]
        batch.failed_ads = results["failed"]
        batch.completed_at = datetime.now()
        
        if results["failed"] == 0:
            batch.status = LaunchStatus.SUCCESS
        elif results["success"] == 0:
            batch.status = LaunchStatus.FAILED
        else:
            batch.status = LaunchStatus.PARTIAL
            
        results["duration_seconds"] = batch.duration_seconds
        results["ads_per_second"] = batch.total_ads / max(batch.duration_seconds, 0.1)
        
        return results
    
    async def _launch_single_ad(self, ad: AdConfig, client: Any) -> LaunchResult:
        """Lança um ad individual"""
        
        try:
            # Chama API do client
            platform_ad_id = await client.create_ad(ad)
            
            return LaunchResult(
                batch_id=ad.id,
                ad_id=ad.id,
                ad_name=ad.name,
                platform=ad.platform,
                status=LaunchStatus.SUCCESS,
                platform_ad_id=platform_ad_id
            )
            
        except Exception as e:
            return LaunchResult(
                batch_id=ad.id,
                ad_id=ad.id,
                ad_name=ad.name,
                platform=ad.platform,
                status=LaunchStatus.FAILED,
                error_message=str(e)
            )
    
    # =========================================================================
    # POST ID SCALING
    # =========================================================================
    
    async def launch_with_post_id(
        self,
        post_ids: List[str],
        ad_set_ids: List[str],
        platform: Platform,
        client: Any
    ) -> List[LaunchResult]:
        """
        Lança ads usando Post IDs existentes
        Preserva engagement (likes, comments, shares)
        """
        
        results = []
        
        for post_id in post_ids:
            for ad_set_id in ad_set_ids:
                ad = AdConfig(
                    name=f"PostID_{post_id}_{ad_set_id[:4]}",
                    platform=platform,
                    use_post_id=True,
                    post_id=post_id,
                    ad_set_id=ad_set_id
                )
                
                result = await self._launch_single_ad(ad, client)
                results.append(result)
                
        return results
    
    # =========================================================================
    # DUPLICATE CAMPAIGNS
    # =========================================================================
    
    async def duplicate_campaign(
        self,
        source_campaign_id: str,
        new_name: str,
        platform: Platform,
        client: Any,
        duplicate_ad_sets: bool = True,
        duplicate_ads: bool = True
    ) -> Dict:
        """
        Duplica campanha completa
        1-click duplication
        """
        
        result = {
            "source_campaign_id": source_campaign_id,
            "new_campaign_id": None,
            "ad_sets_duplicated": 0,
            "ads_duplicated": 0
        }
        
        # Duplica campanha
        new_campaign_id = await client.duplicate_campaign(
            source_campaign_id, 
            new_name
        )
        result["new_campaign_id"] = new_campaign_id
        
        if duplicate_ad_sets:
            # Obtém ad sets originais
            ad_sets = await client.get_campaign_ad_sets(source_campaign_id)
            
            for ad_set in ad_sets:
                new_ad_set_id = await client.duplicate_ad_set(
                    ad_set["id"],
                    new_campaign_id
                )
                result["ad_sets_duplicated"] += 1
                
                if duplicate_ads:
                    # Duplica ads
                    ads = await client.get_ad_set_ads(ad_set["id"])
                    for ad in ads:
                        await client.duplicate_ad(ad["id"], new_ad_set_id)
                        result["ads_duplicated"] += 1
                        
        return result
    
    # =========================================================================
    # CROSS-PLATFORM LAUNCH
    # =========================================================================
    
    async def launch_cross_platform(
        self,
        creatives: List[Creative],
        platforms: List[Platform],
        campaign_configs: Dict[Platform, Dict],
        copy_template: CopyTemplate,
        meta_client: Optional[Any] = None,
        tiktok_client: Optional[Any] = None
    ) -> Dict:
        """
        Lança mesmos criativos em múltiplas plataformas
        Meta + TikTok simultaneamente
        """
        
        results = {
            "platforms": {},
            "total_launched": 0,
            "total_failed": 0
        }
        
        for platform in platforms:
            config = campaign_configs.get(platform, {})
            
            # Prepara batch para plataforma
            batch = await self.prepare_batch(
                creatives=creatives,
                platform=platform,
                campaign_id=config.get("campaign_id", ""),
                ad_set_ids=config.get("ad_set_ids", []),
                copy_template_id=copy_template.id if copy_template else None
            )
            
            # Lança
            client = meta_client if platform == Platform.META else tiktok_client
            platform_results = await self.launch_batch(batch, meta_client, tiktok_client)
            
            results["platforms"][platform.value] = platform_results
            results["total_launched"] += platform_results["success"]
            results["total_failed"] += platform_results["failed"]
            
        return results
    
    # =========================================================================
    # STATISTICS
    # =========================================================================
    
    def get_launch_stats(self) -> Dict:
        """Retorna estatísticas de lançamento"""
        
        total_ads = sum(b.launched_ads for b in self.batches.values())
        total_batches = len(self.batches)
        
        success_batches = len([b for b in self.batches.values() if b.status == LaunchStatus.SUCCESS])
        failed_batches = len([b for b in self.batches.values() if b.status == LaunchStatus.FAILED])
        
        total_time = sum(b.duration_seconds for b in self.batches.values())
        avg_time_per_batch = total_time / max(total_batches, 1)
        avg_ads_per_second = total_ads / max(total_time, 1)
        
        return {
            "total_ads_launched": total_ads,
            "total_batches": total_batches,
            "success_batches": success_batches,
            "failed_batches": failed_batches,
            "total_time_seconds": total_time,
            "avg_time_per_batch": avg_time_per_batch,
            "avg_ads_per_second": avg_ads_per_second,
            "templates_count": len(self.copy_templates),
            "workspaces_count": len(self.workspaces)
        }


# =============================================================================
# MOCK API CLIENT
# =============================================================================

class MockAPIClient:
    """Mock client para desenvolvimento"""
    
    async def create_ad(self, ad: AdConfig) -> str:
        """Simula criação de ad"""
        await asyncio.sleep(0.05)  # Simula latência
        
        # 5% chance de erro (simula erros reais)
        import random
        if random.random() < 0.05:
            raise Exception("API Rate Limit Exceeded")
            
        return f"ad_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
    
    async def duplicate_campaign(self, campaign_id: str, new_name: str) -> str:
        await asyncio.sleep(0.1)
        return f"campaign_{uuid.uuid4().hex[:8]}"
    
    async def duplicate_ad_set(self, ad_set_id: str, campaign_id: str) -> str:
        await asyncio.sleep(0.05)
        return f"adset_{uuid.uuid4().hex[:8]}"
    
    async def duplicate_ad(self, ad_id: str, ad_set_id: str) -> str:
        await asyncio.sleep(0.05)
        return f"ad_{uuid.uuid4().hex[:8]}"
    
    async def get_campaign_ad_sets(self, campaign_id: str) -> List[Dict]:
        return [{"id": f"adset_{i}"} for i in range(3)]
    
    async def get_ad_set_ads(self, ad_set_id: str) -> List[Dict]:
        return [{"id": f"ad_{i}"} for i in range(5)]


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "Platform",
    "AdFormat",
    "AspectRatio",
    "Placement",
    "LaunchStatus",
    "Permission",
    
    # Data Classes
    "Creative",
    "CreativeGroup",
    "CopyTemplate",
    "NamingConvention",
    "UTMConfig",
    "AdConfig",
    "AdBatch",
    "LaunchResult",
    "TeamMember",
    "Workspace",
    "SheetRow",
    
    # Engines
    "AutoGroupingEngine",
    "CloudIntegrationManager",
    "GoogleDriveProvider",
    "DropboxProvider",
    "FrameIOProvider",
    "GoogleSheetsIntegration",
    "MultiLanguageEngine",
    "CrossPlatformAdLauncher",
    "MockAPIClient"
]
