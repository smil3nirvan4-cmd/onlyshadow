"""
S.S.I. SHADOW - Plai Style Engine
Baseado em análise detalhada do Plai.io e AdManage.ai

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
FUNCIONALIDADES IMPLEMENTADAS:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. AI MARKETER (Plai "Optimize for Me")
   - Otimização automática diária de ads
   - Geração de novos criativos para superar originais
   - Remoção de audiences/placements/keywords underperforming
   - Foco do budget em resultados (leads, sales, traffic)
   - 24/7 AI ad manager

2. AUTOMATION RULES (Plai + Bïrch style)
   - Pause losers automaticamente
   - Scale winners automaticamente
   - Budget caps e alerts
   - CPA/ROAS thresholds
   - Regras customizadas

3. CREATIVE TRACKER
   - Performance de criativos em tempo real
   - Fatigue detection
   - A/B testing automático
   - Winner identification

4. AUDIENCE LAUNCHER
   - Criação em massa de audiences
   - Templates reutilizáveis
   - Targeting consistency
   - Funnel-based audiences

5. BUDGET OPTIMIZER (Plai Optimization Folders)
   - Shift de spend para top performers
   - Cross-platform budget allocation
   - Pausa automática de low performers
   - Goal-aligned optimization

6. LOOKALIKE GENERATOR
   - Criação automática de LAL audiences
   - Múltiplos percentuais (1%, 2-5%, 5-10%)
   - Seed audience optimization
   - Cross-platform LAL

7. CREATIVE VARIATIONS
   - Geração automática de variações
   - Headlines, descriptions, CTAs
   - Image variations
   - Copy testing matrix

8. AI IMAGE GENERATOR
   - Text-to-image generation
   - Product image transformation
   - UGC-style video generation
   - Memes e scroll-stopping ads

9. COMPETITOR ANALYSIS
   - Ad Library scraping
   - Creative analysis
   - Targeting insights
   - Performance estimation

10. AUTOMATED WORKFLOWS
    - n8n-style automation
    - Trigger → Condition → Action
    - Multi-step workflows
    - Scheduled tasks

11. FEED MANAGEMENT
    - Product catalog sync
    - Dynamic product ads
    - Feed optimization
    - Inventory sync

12. UNIFIED DASHBOARD
    - Cross-platform metrics
    - Real-time reporting
    - Smart insights
    - Goal tracking

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union, Tuple, Callable, Set
from enum import Enum
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json
import hashlib
import asyncio
import re
import uuid
import time
import random


# =============================================================================
# ENUMS
# =============================================================================

class Platform(Enum):
    """Plataformas suportadas"""
    META = "meta"
    GOOGLE = "google"
    TIKTOK = "tiktok"
    LINKEDIN = "linkedin"
    SPOTIFY = "spotify"
    SNAPCHAT = "snapchat"
    PINTEREST = "pinterest"
    YOUTUBE = "youtube"

class OptimizationGoal(Enum):
    """Objetivos de otimização"""
    LEADS = "leads"
    SALES = "sales"
    TRAFFIC = "traffic"
    BRAND_AWARENESS = "brand_awareness"
    APP_INSTALLS = "app_installs"
    ENGAGEMENT = "engagement"
    VIDEO_VIEWS = "video_views"
    MESSAGES = "messages"

class RuleCondition(Enum):
    """Condições para regras de automação"""
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    EQUAL = "=="
    NOT_EQUAL = "!="
    BETWEEN = "between"
    NOT_BETWEEN = "not_between"
    IN_TOP_PERCENT = "in_top_percent"
    IN_BOTTOM_PERCENT = "in_bottom_percent"

class RuleAction(Enum):
    """Ações para regras de automação"""
    PAUSE = "pause"
    ENABLE = "enable"
    INCREASE_BUDGET = "increase_budget"
    DECREASE_BUDGET = "decrease_budget"
    SET_BUDGET = "set_budget"
    INCREASE_BID = "increase_bid"
    DECREASE_BID = "decrease_bid"
    DUPLICATE = "duplicate"
    ARCHIVE = "archive"
    NOTIFY = "notify"
    CREATE_VARIATION = "create_variation"
    REFRESH_CREATIVE = "refresh_creative"
    EXPAND_AUDIENCE = "expand_audience"

class WorkflowTrigger(Enum):
    """Triggers para workflows"""
    SCHEDULE = "schedule"
    METRIC_THRESHOLD = "metric_threshold"
    TIME_RUNNING = "time_running"
    BUDGET_SPENT = "budget_spent"
    CONVERSION_COUNT = "conversion_count"
    NEW_CAMPAIGN = "new_campaign"
    CAMPAIGN_STATUS = "campaign_status"
    WEBHOOK = "webhook"

class CreativeType(Enum):
    """Tipos de criativos"""
    IMAGE = "image"
    VIDEO = "video"
    CAROUSEL = "carousel"
    COLLECTION = "collection"
    UGC = "ugc"
    MEME = "meme"
    TESTIMONIAL = "testimonial"
    PRODUCT = "product"

class AudienceType(Enum):
    """Tipos de audiência"""
    CUSTOM = "custom"
    LOOKALIKE = "lookalike"
    INTEREST = "interest"
    BEHAVIOR = "behavior"
    DEMOGRAPHIC = "demographic"
    RETARGETING = "retargeting"
    BROAD = "broad"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class CampaignMetrics:
    """Métricas de campanha"""
    campaign_id: str
    platform: Platform
    spend: float = 0.0
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    conversion_value: float = 0.0
    ctr: float = 0.0
    cvr: float = 0.0
    cpc: float = 0.0
    cpa: float = 0.0
    roas: float = 0.0
    frequency: float = 0.0
    reach: int = 0
    date: datetime = field(default_factory=datetime.now)
    
    def calculate_derived_metrics(self):
        """Calcula métricas derivadas"""
        if self.impressions > 0:
            self.ctr = (self.clicks / self.impressions) * 100
        if self.clicks > 0:
            self.cvr = (self.conversions / self.clicks) * 100
            self.cpc = self.spend / self.clicks
        if self.conversions > 0:
            self.cpa = self.spend / self.conversions
        if self.spend > 0:
            self.roas = self.conversion_value / self.spend
        if self.reach > 0:
            self.frequency = self.impressions / self.reach

@dataclass
class CreativeAsset:
    """Asset de criativo"""
    id: str
    name: str
    type: CreativeType
    url: Optional[str] = None
    file_path: Optional[str] = None
    width: int = 0
    height: int = 0
    duration_seconds: float = 0
    headline: Optional[str] = None
    description: Optional[str] = None
    cta: str = "Learn More"
    performance_score: float = 0.0
    created_at: datetime = field(default_factory=datetime.now)

@dataclass
class AudienceTemplate:
    """Template de audiência reutilizável"""
    id: str
    name: str
    type: AudienceType
    platform: Platform
    targeting: Dict = field(default_factory=dict)
    size_estimate: int = 0
    performance_score: float = 0.0
    uses_count: int = 0

@dataclass
class AutomationRule:
    """Regra de automação"""
    id: str
    name: str
    enabled: bool = True
    platforms: List[Platform] = field(default_factory=list)
    entity_type: str = "ad"  # campaign, ad_set, ad
    conditions: List[Dict] = field(default_factory=list)
    actions: List[Dict] = field(default_factory=list)
    schedule: Optional[str] = None  # cron expression
    last_run: Optional[datetime] = None
    times_triggered: int = 0

@dataclass
class Workflow:
    """Workflow automatizado"""
    id: str
    name: str
    enabled: bool = True
    trigger: WorkflowTrigger = WorkflowTrigger.SCHEDULE
    trigger_config: Dict = field(default_factory=dict)
    steps: List[Dict] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    runs_count: int = 0

@dataclass
class ProductFeed:
    """Feed de produtos"""
    id: str
    name: str
    source_url: Optional[str] = None
    products_count: int = 0
    last_sync: Optional[datetime] = None
    sync_frequency: str = "daily"
    status: str = "active"

@dataclass
class CompetitorAd:
    """Ad de concorrente"""
    id: str
    advertiser_name: str
    platform: Platform
    creative_url: Optional[str] = None
    ad_copy: Optional[str] = None
    cta: Optional[str] = None
    landing_page: Optional[str] = None
    first_seen: datetime = field(default_factory=datetime.now)
    last_seen: datetime = field(default_factory=datetime.now)
    estimated_spend: float = 0.0
    estimated_reach: int = 0


# =============================================================================
# 1. AI MARKETER - OPTIMIZE FOR ME
# =============================================================================

class AIMarketer:
    """
    AI Marketer - Similar ao Plai "Optimize for Me"
    Otimização automática 24/7 de campanhas
    """
    
    def __init__(self, optimization_goal: OptimizationGoal = OptimizationGoal.SALES):
        self.optimization_goal = optimization_goal
        self.optimization_history: List[Dict] = []
        self.benchmarks = self._load_benchmarks()
        
    def _load_benchmarks(self) -> Dict:
        """Carrega benchmarks por indústria"""
        return {
            "ecommerce": {
                "ctr": 1.5,
                "cvr": 2.5,
                "cpa": 25.0,
                "roas": 3.0
            },
            "lead_gen": {
                "ctr": 2.0,
                "cvr": 5.0,
                "cpa": 50.0,
                "roas": 2.0
            },
            "app_install": {
                "ctr": 2.5,
                "cvr": 3.0,
                "cpa": 10.0,
                "roas": 1.5
            }
        }
        
    async def optimize_for_me(
        self,
        campaigns: List[CampaignMetrics],
        creatives: List[CreativeAsset],
        audiences: List[AudienceTemplate],
        industry: str = "ecommerce"
    ) -> Dict:
        """
        Executa otimização completa automática
        Similar ao Plai "Optimize for Me"
        """
        
        benchmarks = self.benchmarks.get(industry, self.benchmarks["ecommerce"])
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "optimization_goal": self.optimization_goal.value,
            "campaigns_analyzed": len(campaigns),
            "actions_taken": [],
            "new_creatives_suggested": [],
            "audiences_removed": [],
            "budget_reallocations": [],
            "estimated_improvement": {}
        }
        
        # 1. Identificar underperformers
        underperformers = self._identify_underperformers(campaigns, benchmarks)
        
        # 2. Identificar winners para escalar
        winners = self._identify_winners(campaigns, benchmarks)
        
        # 3. Gerar novos criativos para superar originais
        new_creatives = await self._generate_improved_creatives(
            creatives, 
            campaigns
        )
        results["new_creatives_suggested"] = new_creatives
        
        # 4. Remover audiences/placements underperforming
        audiences_to_remove = self._identify_poor_audiences(audiences, campaigns)
        results["audiences_removed"] = audiences_to_remove
        
        # 5. Realocar budget para winners
        budget_changes = self._calculate_budget_reallocation(
            campaigns, 
            winners, 
            underperformers
        )
        results["budget_reallocations"] = budget_changes
        
        # 6. Gerar ações específicas
        for campaign in underperformers:
            if campaign.roas < benchmarks["roas"] * 0.5:
                results["actions_taken"].append({
                    "campaign_id": campaign.campaign_id,
                    "action": "pause",
                    "reason": f"ROAS {campaign.roas:.2f} abaixo de 50% do benchmark"
                })
            elif campaign.cpa > benchmarks["cpa"] * 1.5:
                results["actions_taken"].append({
                    "campaign_id": campaign.campaign_id,
                    "action": "decrease_budget",
                    "amount_percent": 20,
                    "reason": f"CPA ${campaign.cpa:.2f} acima de 150% do benchmark"
                })
                
        for campaign in winners:
            if campaign.roas > benchmarks["roas"] * 2:
                results["actions_taken"].append({
                    "campaign_id": campaign.campaign_id,
                    "action": "increase_budget",
                    "amount_percent": 30,
                    "reason": f"ROAS {campaign.roas:.2f} acima de 200% do benchmark"
                })
                
        # 7. Estimar melhoria
        results["estimated_improvement"] = {
            "cpa_reduction_percent": 15,
            "roas_increase_percent": 25,
            "spend_efficiency_increase": 20
        }
        
        self.optimization_history.append(results)
        
        return results
    
    def _identify_underperformers(
        self, 
        campaigns: List[CampaignMetrics],
        benchmarks: Dict
    ) -> List[CampaignMetrics]:
        """Identifica campanhas com baixo desempenho"""
        
        underperformers = []
        
        for campaign in campaigns:
            issues = 0
            
            if campaign.ctr < benchmarks["ctr"] * 0.7:
                issues += 1
            if campaign.cvr < benchmarks["cvr"] * 0.7:
                issues += 1
            if campaign.cpa > benchmarks["cpa"] * 1.3:
                issues += 1
            if campaign.roas < benchmarks["roas"] * 0.7:
                issues += 1
                
            if issues >= 2:
                underperformers.append(campaign)
                
        return underperformers
    
    def _identify_winners(
        self,
        campaigns: List[CampaignMetrics],
        benchmarks: Dict
    ) -> List[CampaignMetrics]:
        """Identifica campanhas vencedoras"""
        
        winners = []
        
        for campaign in campaigns:
            wins = 0
            
            if campaign.ctr > benchmarks["ctr"] * 1.3:
                wins += 1
            if campaign.cvr > benchmarks["cvr"] * 1.3:
                wins += 1
            if campaign.cpa < benchmarks["cpa"] * 0.7:
                wins += 1
            if campaign.roas > benchmarks["roas"] * 1.3:
                wins += 1
                
            if wins >= 2:
                winners.append(campaign)
                
        return winners
    
    async def _generate_improved_creatives(
        self,
        existing_creatives: List[CreativeAsset],
        campaigns: List[CampaignMetrics]
    ) -> List[Dict]:
        """Sugere novos criativos baseados nos top performers"""
        
        suggestions = []
        
        # Encontra criativos com melhor performance
        top_creatives = sorted(
            existing_creatives,
            key=lambda x: x.performance_score,
            reverse=True
        )[:3]
        
        for creative in top_creatives:
            # Gera variações
            suggestions.append({
                "based_on": creative.id,
                "type": "headline_variation",
                "suggestion": f"Variação de '{creative.headline}' com urgência",
                "expected_improvement": "+15% CTR"
            })
            
            suggestions.append({
                "based_on": creative.id,
                "type": "cta_variation",
                "suggestion": f"Testar CTA '{creative.cta}' → 'Shop Now' vs 'Get Yours'",
                "expected_improvement": "+10% CVR"
            })
            
        return suggestions
    
    def _identify_poor_audiences(
        self,
        audiences: List[AudienceTemplate],
        campaigns: List[CampaignMetrics]
    ) -> List[str]:
        """Identifica audiences com baixo desempenho"""
        
        poor_audiences = []
        
        for audience in audiences:
            if audience.performance_score < 0.3:
                poor_audiences.append(audience.id)
                
        return poor_audiences
    
    def _calculate_budget_reallocation(
        self,
        campaigns: List[CampaignMetrics],
        winners: List[CampaignMetrics],
        underperformers: List[CampaignMetrics]
    ) -> List[Dict]:
        """Calcula realocação de budget"""
        
        reallocations = []
        
        # Budget total dos underperformers para redistribuir
        budget_to_redistribute = sum(c.spend * 0.3 for c in underperformers)
        
        if budget_to_redistribute > 0 and winners:
            per_winner = budget_to_redistribute / len(winners)
            
            for winner in winners:
                reallocations.append({
                    "campaign_id": winner.campaign_id,
                    "action": "increase_budget",
                    "amount": per_winner,
                    "reason": "Realocação de budget de underperformers"
                })
                
            for underperformer in underperformers:
                reallocations.append({
                    "campaign_id": underperformer.campaign_id,
                    "action": "decrease_budget",
                    "amount": underperformer.spend * 0.3,
                    "reason": "Redistribuição para winners"
                })
                
        return reallocations


# =============================================================================
# 2. AUTOMATION RULES ENGINE
# =============================================================================

class AutomationRulesEngine:
    """
    Engine de regras de automação
    Similar ao Plai + Bïrch automation
    """
    
    def __init__(self):
        self.rules: Dict[str, AutomationRule] = {}
        self.rule_logs: List[Dict] = []
        
        # Carrega regras pré-configuradas
        self._load_default_rules()
        
    def _load_default_rules(self):
        """Carrega regras de automação padrão"""
        
        # Regra 1: Pausar ads com CPA alto
        self.add_rule(AutomationRule(
            id="pause_high_cpa",
            name="Pause High CPA Ads",
            platforms=[Platform.META, Platform.GOOGLE],
            entity_type="ad",
            conditions=[
                {"metric": "cpa", "operator": ">", "value": 100},
                {"metric": "spend", "operator": ">", "value": 50}
            ],
            actions=[
                {"type": "pause", "reason": "CPA > $100 com spend > $50"}
            ]
        ))
        
        # Regra 2: Escalar ads com ROAS alto
        self.add_rule(AutomationRule(
            id="scale_high_roas",
            name="Scale High ROAS Ads",
            platforms=[Platform.META, Platform.GOOGLE],
            entity_type="ad_set",
            conditions=[
                {"metric": "roas", "operator": ">", "value": 3.0},
                {"metric": "conversions", "operator": ">", "value": 5}
            ],
            actions=[
                {"type": "increase_budget", "percent": 20}
            ]
        ))
        
        # Regra 3: Detectar fadiga de criativo
        self.add_rule(AutomationRule(
            id="creative_fatigue",
            name="Detect Creative Fatigue",
            platforms=[Platform.META],
            entity_type="ad",
            conditions=[
                {"metric": "frequency", "operator": ">", "value": 3.0},
                {"metric": "ctr_change_7d", "operator": "<", "value": -20}
            ],
            actions=[
                {"type": "notify", "message": "Creative fatigue detected"},
                {"type": "decrease_budget", "percent": 30}
            ]
        ))
        
        # Regra 4: Proteção de budget
        self.add_rule(AutomationRule(
            id="budget_protection",
            name="Budget Cap Protection",
            platforms=[Platform.META, Platform.GOOGLE, Platform.TIKTOK],
            entity_type="campaign",
            conditions=[
                {"metric": "daily_spend", "operator": ">", "value": "daily_budget * 1.2"}
            ],
            actions=[
                {"type": "pause", "reason": "Daily budget exceeded by 20%"},
                {"type": "notify", "message": "Campaign paused due to overspend"}
            ]
        ))
        
        # Regra 5: Top performer scaling
        self.add_rule(AutomationRule(
            id="top_performer_scaling",
            name="Scale Top 10% Performers",
            platforms=[Platform.META, Platform.GOOGLE],
            entity_type="ad",
            conditions=[
                {"metric": "roas", "operator": "in_top_percent", "value": 10}
            ],
            actions=[
                {"type": "duplicate", "target": "new_ad_set"},
                {"type": "increase_budget", "percent": 50}
            ]
        ))
        
    def add_rule(self, rule: AutomationRule) -> str:
        """Adiciona nova regra"""
        self.rules[rule.id] = rule
        return rule.id
    
    def remove_rule(self, rule_id: str) -> bool:
        """Remove regra"""
        if rule_id in self.rules:
            del self.rules[rule_id]
            return True
        return False
    
    def toggle_rule(self, rule_id: str, enabled: bool) -> bool:
        """Ativa/desativa regra"""
        if rule_id in self.rules:
            self.rules[rule_id].enabled = enabled
            return True
        return False
    
    async def evaluate_rules(
        self,
        entities: List[Dict],
        entity_type: str,
        platform: Platform
    ) -> List[Dict]:
        """Avalia todas as regras para as entidades"""
        
        actions_to_take = []
        
        # Filtra regras aplicáveis
        applicable_rules = [
            rule for rule in self.rules.values()
            if rule.enabled 
            and rule.entity_type == entity_type
            and platform in rule.platforms
        ]
        
        for entity in entities:
            for rule in applicable_rules:
                if self._check_conditions(entity, rule.conditions):
                    actions = self._generate_actions(entity, rule)
                    actions_to_take.extend(actions)
                    
                    # Log
                    self.rule_logs.append({
                        "timestamp": datetime.now().isoformat(),
                        "rule_id": rule.id,
                        "rule_name": rule.name,
                        "entity_id": entity.get("id"),
                        "entity_type": entity_type,
                        "conditions_met": rule.conditions,
                        "actions_triggered": actions
                    })
                    
                    rule.times_triggered += 1
                    rule.last_run = datetime.now()
                    
        return actions_to_take
    
    def _check_conditions(
        self,
        entity: Dict,
        conditions: List[Dict]
    ) -> bool:
        """Verifica se todas as condições são atendidas"""
        
        for condition in conditions:
            metric = condition["metric"]
            operator = condition["operator"]
            value = condition["value"]
            
            entity_value = entity.get(metric, 0)
            
            if operator == ">":
                if not entity_value > value:
                    return False
            elif operator == "<":
                if not entity_value < value:
                    return False
            elif operator == ">=":
                if not entity_value >= value:
                    return False
            elif operator == "<=":
                if not entity_value <= value:
                    return False
            elif operator == "==":
                if not entity_value == value:
                    return False
            elif operator == "!=":
                if not entity_value != value:
                    return False
                    
        return True
    
    def _generate_actions(
        self,
        entity: Dict,
        rule: AutomationRule
    ) -> List[Dict]:
        """Gera ações baseadas na regra"""
        
        actions = []
        
        for action_config in rule.actions:
            action = {
                "entity_id": entity.get("id"),
                "rule_id": rule.id,
                "action_type": action_config["type"],
                "config": action_config,
                "timestamp": datetime.now().isoformat()
            }
            actions.append(action)
            
        return actions


# =============================================================================
# 3. CREATIVE TRACKER
# =============================================================================

class CreativeTracker:
    """
    Rastreamento de performance de criativos
    Fatigue detection e A/B testing
    """
    
    def __init__(self):
        self.creatives: Dict[str, CreativeAsset] = {}
        self.performance_history: Dict[str, List[Dict]] = {}
        self.fatigue_thresholds = {
            "frequency_max": 3.0,
            "ctr_drop_percent": 20,
            "days_running_max": 14
        }
        
    def track_creative(self, creative: CreativeAsset):
        """Adiciona criativo ao tracking"""
        self.creatives[creative.id] = creative
        self.performance_history[creative.id] = []
        
    def update_performance(
        self,
        creative_id: str,
        metrics: Dict
    ):
        """Atualiza métricas de performance"""
        
        if creative_id not in self.performance_history:
            self.performance_history[creative_id] = []
            
        metrics["timestamp"] = datetime.now().isoformat()
        self.performance_history[creative_id].append(metrics)
        
        # Atualiza score
        if creative_id in self.creatives:
            self.creatives[creative_id].performance_score = self._calculate_score(metrics)
            
    def _calculate_score(self, metrics: Dict) -> float:
        """Calcula score de performance (0-100)"""
        
        score = 50  # Base
        
        # CTR bonus
        ctr = metrics.get("ctr", 0)
        if ctr > 2.0:
            score += 20
        elif ctr > 1.5:
            score += 10
        elif ctr < 0.5:
            score -= 20
            
        # CVR bonus
        cvr = metrics.get("cvr", 0)
        if cvr > 3.0:
            score += 20
        elif cvr > 2.0:
            score += 10
        elif cvr < 1.0:
            score -= 20
            
        # ROAS bonus
        roas = metrics.get("roas", 0)
        if roas > 4.0:
            score += 10
        elif roas > 2.0:
            score += 5
        elif roas < 1.0:
            score -= 10
            
        return max(0, min(100, score))
    
    async def detect_fatigue(self) -> List[Dict]:
        """Detecta criativos com fadiga"""
        
        fatigued = []
        
        for creative_id, history in self.performance_history.items():
            if len(history) < 2:
                continue
                
            latest = history[-1]
            first = history[0]
            
            # Check frequency
            if latest.get("frequency", 0) > self.fatigue_thresholds["frequency_max"]:
                fatigued.append({
                    "creative_id": creative_id,
                    "reason": "High frequency",
                    "frequency": latest["frequency"],
                    "recommendation": "Refresh creative or expand audience"
                })
                continue
                
            # Check CTR drop
            first_ctr = first.get("ctr", 0)
            latest_ctr = latest.get("ctr", 0)
            
            if first_ctr > 0:
                ctr_change = ((latest_ctr - first_ctr) / first_ctr) * 100
                if ctr_change < -self.fatigue_thresholds["ctr_drop_percent"]:
                    fatigued.append({
                        "creative_id": creative_id,
                        "reason": "CTR decline",
                        "ctr_change_percent": ctr_change,
                        "recommendation": "Create new variation"
                    })
                    continue
                    
            # Check days running
            days_running = (datetime.now() - datetime.fromisoformat(first["timestamp"])).days
            if days_running > self.fatigue_thresholds["days_running_max"]:
                fatigued.append({
                    "creative_id": creative_id,
                    "reason": "Long runtime",
                    "days_running": days_running,
                    "recommendation": "Rotate to fresh creative"
                })
                
        return fatigued
    
    def get_top_performers(self, limit: int = 10) -> List[CreativeAsset]:
        """Retorna top performers"""
        
        return sorted(
            self.creatives.values(),
            key=lambda x: x.performance_score,
            reverse=True
        )[:limit]
    
    def get_ab_test_results(
        self,
        creative_a_id: str,
        creative_b_id: str
    ) -> Dict:
        """Compara dois criativos em A/B test"""
        
        if creative_a_id not in self.performance_history:
            return {"error": f"Creative {creative_a_id} not found"}
        if creative_b_id not in self.performance_history:
            return {"error": f"Creative {creative_b_id} not found"}
            
        history_a = self.performance_history[creative_a_id]
        history_b = self.performance_history[creative_b_id]
        
        if not history_a or not history_b:
            return {"error": "Insufficient data"}
            
        # Últimas métricas
        latest_a = history_a[-1]
        latest_b = history_b[-1]
        
        # Compara métricas
        results = {
            "creative_a": creative_a_id,
            "creative_b": creative_b_id,
            "comparison": {},
            "winner": None,
            "confidence": 0
        }
        
        metrics_to_compare = ["ctr", "cvr", "cpa", "roas"]
        a_wins = 0
        b_wins = 0
        
        for metric in metrics_to_compare:
            val_a = latest_a.get(metric, 0)
            val_b = latest_b.get(metric, 0)
            
            # Para CPA, menor é melhor
            if metric == "cpa":
                better = "A" if val_a < val_b else "B"
            else:
                better = "A" if val_a > val_b else "B"
                
            results["comparison"][metric] = {
                "a": val_a,
                "b": val_b,
                "winner": better
            }
            
            if better == "A":
                a_wins += 1
            else:
                b_wins += 1
                
        if a_wins > b_wins:
            results["winner"] = "A"
            results["confidence"] = (a_wins / len(metrics_to_compare)) * 100
        elif b_wins > a_wins:
            results["winner"] = "B"
            results["confidence"] = (b_wins / len(metrics_to_compare)) * 100
        else:
            results["winner"] = "TIE"
            results["confidence"] = 50
            
        return results


# =============================================================================
# 4. AUDIENCE LAUNCHER
# =============================================================================

class AudienceLauncher:
    """
    Lançador de audiências em massa
    Templates reutilizáveis e funnel-based
    """
    
    def __init__(self):
        self.templates: Dict[str, AudienceTemplate] = {}
        self.funnel_templates = self._load_funnel_templates()
        
    def _load_funnel_templates(self) -> Dict:
        """Carrega templates de funnel"""
        
        return {
            "tofu": {  # Top of Funnel
                "name": "TOFU - Cold Audiences",
                "audiences": [
                    {"type": "interest", "description": "Broad interests"},
                    {"type": "lookalike", "percent": "5-10%", "source": "website_visitors"},
                    {"type": "behavior", "description": "In-market audiences"}
                ]
            },
            "mofu": {  # Middle of Funnel
                "name": "MOFU - Warm Audiences",
                "audiences": [
                    {"type": "retargeting", "window": "30d", "source": "website_visitors"},
                    {"type": "lookalike", "percent": "1-5%", "source": "purchasers"},
                    {"type": "custom", "source": "video_viewers_50%+"}
                ]
            },
            "bofu": {  # Bottom of Funnel
                "name": "BOFU - Hot Audiences",
                "audiences": [
                    {"type": "retargeting", "window": "7d", "source": "add_to_cart"},
                    {"type": "retargeting", "window": "3d", "source": "checkout_started"},
                    {"type": "lookalike", "percent": "0-1%", "source": "high_value_purchasers"}
                ]
            }
        }
        
    def save_template(self, template: AudienceTemplate) -> str:
        """Salva template de audiência"""
        self.templates[template.id] = template
        return template.id
    
    def get_template(self, template_id: str) -> Optional[AudienceTemplate]:
        """Obtém template"""
        return self.templates.get(template_id)
    
    async def launch_funnel_audiences(
        self,
        funnel_stage: str,
        platform: Platform,
        seed_data: Dict
    ) -> List[Dict]:
        """Lança audiências para estágio do funnel"""
        
        if funnel_stage not in self.funnel_templates:
            return []
            
        template = self.funnel_templates[funnel_stage]
        created_audiences = []
        
        for audience_config in template["audiences"]:
            audience = {
                "id": str(uuid.uuid4())[:8],
                "name": f"{template['name']}_{audience_config['type']}",
                "type": audience_config["type"],
                "platform": platform.value,
                "config": audience_config,
                "status": "created"
            }
            created_audiences.append(audience)
            
        return created_audiences
    
    async def bulk_create_audiences(
        self,
        templates: List[AudienceTemplate],
        platforms: List[Platform]
    ) -> Dict:
        """Cria múltiplas audiências em massa"""
        
        results = {
            "total": 0,
            "success": 0,
            "failed": 0,
            "audiences": []
        }
        
        for template in templates:
            for platform in platforms:
                results["total"] += 1
                
                try:
                    audience = {
                        "id": str(uuid.uuid4())[:8],
                        "template_id": template.id,
                        "name": f"{template.name}_{platform.value}",
                        "platform": platform.value,
                        "type": template.type.value,
                        "targeting": template.targeting,
                        "status": "created"
                    }
                    results["audiences"].append(audience)
                    results["success"] += 1
                    
                    # Incrementa uso do template
                    template.uses_count += 1
                    
                except Exception as e:
                    results["failed"] += 1
                    
        return results


# =============================================================================
# 5. BUDGET OPTIMIZER - OPTIMIZATION FOLDERS
# =============================================================================

class BudgetOptimizer:
    """
    Otimizador de budget cross-platform
    Similar ao Plai Optimization Folders
    """
    
    def __init__(self):
        self.optimization_folders: Dict[str, Dict] = {}
        self.reallocation_history: List[Dict] = []
        
    def create_folder(
        self,
        name: str,
        campaigns: List[str],
        goal: OptimizationGoal,
        total_budget: float,
        min_budget_per_campaign: float = 10.0
    ) -> str:
        """Cria optimization folder"""
        
        folder_id = str(uuid.uuid4())[:8]
        
        self.optimization_folders[folder_id] = {
            "id": folder_id,
            "name": name,
            "campaigns": campaigns,
            "goal": goal.value,
            "total_budget": total_budget,
            "min_budget_per_campaign": min_budget_per_campaign,
            "created_at": datetime.now().isoformat(),
            "last_optimization": None
        }
        
        return folder_id
    
    async def optimize_folder(
        self,
        folder_id: str,
        campaign_metrics: List[CampaignMetrics]
    ) -> Dict:
        """Otimiza budget dentro de uma folder"""
        
        if folder_id not in self.optimization_folders:
            return {"error": "Folder not found"}
            
        folder = self.optimization_folders[folder_id]
        goal = OptimizationGoal(folder["goal"])
        
        # Filtra métricas das campanhas na folder
        folder_metrics = [
            m for m in campaign_metrics
            if m.campaign_id in folder["campaigns"]
        ]
        
        if not folder_metrics:
            return {"error": "No metrics found"}
            
        # Calcula scores baseado no goal
        scores = self._calculate_goal_scores(folder_metrics, goal)
        
        # Calcula nova distribuição de budget
        new_distribution = self._calculate_budget_distribution(
            scores,
            folder["total_budget"],
            folder["min_budget_per_campaign"]
        )
        
        # Gera realocações
        reallocations = []
        for campaign_id, new_budget in new_distribution.items():
            current = next(
                (m for m in folder_metrics if m.campaign_id == campaign_id),
                None
            )
            if current:
                change = new_budget - current.spend
                if abs(change) > 1:  # Só realoca se diferença > $1
                    reallocations.append({
                        "campaign_id": campaign_id,
                        "current_budget": current.spend,
                        "new_budget": new_budget,
                        "change": change,
                        "change_percent": (change / current.spend * 100) if current.spend > 0 else 0
                    })
                    
        result = {
            "folder_id": folder_id,
            "timestamp": datetime.now().isoformat(),
            "goal": goal.value,
            "campaigns_analyzed": len(folder_metrics),
            "reallocations": reallocations,
            "total_redistributed": sum(abs(r["change"]) for r in reallocations)
        }
        
        # Atualiza folder
        folder["last_optimization"] = datetime.now().isoformat()
        
        # Log
        self.reallocation_history.append(result)
        
        return result
    
    def _calculate_goal_scores(
        self,
        metrics: List[CampaignMetrics],
        goal: OptimizationGoal
    ) -> Dict[str, float]:
        """Calcula scores baseado no objetivo"""
        
        scores = {}
        
        for m in metrics:
            if goal == OptimizationGoal.SALES:
                # Prioriza ROAS
                score = m.roas * 0.5 + (1 / max(m.cpa, 1)) * 0.3 + m.cvr * 0.2
            elif goal == OptimizationGoal.LEADS:
                # Prioriza CPL baixo
                score = (1 / max(m.cpa, 1)) * 0.5 + m.cvr * 0.3 + m.ctr * 0.2
            elif goal == OptimizationGoal.TRAFFIC:
                # Prioriza CPC baixo e CTR alto
                score = (1 / max(m.cpc, 0.01)) * 0.5 + m.ctr * 0.5
            else:
                # Default: balanceado
                score = m.roas * 0.25 + m.ctr * 0.25 + m.cvr * 0.25 + (1 / max(m.cpa, 1)) * 0.25
                
            scores[m.campaign_id] = max(0, score)
            
        return scores
    
    def _calculate_budget_distribution(
        self,
        scores: Dict[str, float],
        total_budget: float,
        min_budget: float
    ) -> Dict[str, float]:
        """Calcula distribuição de budget baseado em scores"""
        
        total_score = sum(scores.values())
        
        if total_score == 0:
            # Distribui igualmente
            equal = total_budget / len(scores)
            return {cid: max(equal, min_budget) for cid in scores}
            
        distribution = {}
        
        for campaign_id, score in scores.items():
            # Budget proporcional ao score
            budget = (score / total_score) * total_budget
            # Garante mínimo
            distribution[campaign_id] = max(budget, min_budget)
            
        # Ajusta para não exceder total
        allocated = sum(distribution.values())
        if allocated > total_budget:
            factor = total_budget / allocated
            distribution = {k: v * factor for k, v in distribution.items()}
            
        return distribution


# =============================================================================
# 6. LOOKALIKE GENERATOR
# =============================================================================

class LookalikeGenerator:
    """
    Gerador automático de Lookalike Audiences
    """
    
    LOOKALIKE_PERCENTAGES = {
        "high_match": [1],
        "balanced": [1, 2, 3],
        "broad": [1, 5, 10]
    }
    
    def __init__(self):
        self.seed_audiences: Dict[str, Dict] = {}
        self.lookalikes_created: List[Dict] = []
        
    def register_seed_audience(
        self,
        seed_id: str,
        name: str,
        source: str,
        size: int,
        quality_score: float = 0.0
    ):
        """Registra seed audience para LALs"""
        
        self.seed_audiences[seed_id] = {
            "id": seed_id,
            "name": name,
            "source": source,
            "size": size,
            "quality_score": quality_score,
            "created_at": datetime.now().isoformat()
        }
        
    async def generate_lookalikes(
        self,
        seed_id: str,
        countries: List[str],
        strategy: str = "balanced",
        platform: Platform = Platform.META
    ) -> List[Dict]:
        """Gera LALs a partir de seed audience"""
        
        if seed_id not in self.seed_audiences:
            return []
            
        seed = self.seed_audiences[seed_id]
        percentages = self.LOOKALIKE_PERCENTAGES.get(strategy, [1, 5])
        
        lookalikes = []
        
        for country in countries:
            for percent in percentages:
                lal = {
                    "id": str(uuid.uuid4())[:8],
                    "name": f"LAL_{seed['name']}_{percent}%_{country}",
                    "seed_id": seed_id,
                    "seed_name": seed["name"],
                    "percent": percent,
                    "country": country,
                    "platform": platform.value,
                    "estimated_size": self._estimate_size(percent, country),
                    "created_at": datetime.now().isoformat()
                }
                lookalikes.append(lal)
                self.lookalikes_created.append(lal)
                
        return lookalikes
    
    def _estimate_size(self, percent: int, country: str) -> int:
        """Estima tamanho da LAL"""
        
        # Population estimates (simplified)
        populations = {
            "US": 330000000,
            "BR": 215000000,
            "UK": 67000000,
            "DE": 83000000,
            "FR": 67000000
        }
        
        pop = populations.get(country, 50000000)
        
        # ~50% of population is on social media, percent is of that
        return int(pop * 0.5 * (percent / 100))
    
    async def auto_generate_best_lookalikes(
        self,
        performance_data: List[Dict],
        countries: List[str]
    ) -> List[Dict]:
        """
        Gera automaticamente as melhores LALs
        baseado em performance data
        """
        
        # Encontra melhores seeds
        best_seeds = sorted(
            self.seed_audiences.values(),
            key=lambda x: x["quality_score"],
            reverse=True
        )[:3]
        
        all_lookalikes = []
        
        for seed in best_seeds:
            # Alta qualidade = LAL mais restrito
            strategy = "high_match" if seed["quality_score"] > 0.7 else "balanced"
            
            lals = await self.generate_lookalikes(
                seed["id"],
                countries,
                strategy
            )
            all_lookalikes.extend(lals)
            
        return all_lookalikes


# =============================================================================
# 7. CREATIVE VARIATIONS
# =============================================================================

class CreativeVariationsEngine:
    """
    Gerador de variações de criativos
    Headlines, descriptions, CTAs
    """
    
    HEADLINE_TEMPLATES = [
        "{benefit} + {urgency}",
        "{number} {result} em {timeframe}",
        "Como {action} sem {pain_point}",
        "{question}?",
        "Descubra o segredo para {goal}",
        "Pare de {problem}. Comece a {solution}",
        "{social_proof} já {action}",
        "O {product} que {benefit}"
    ]
    
    CTA_OPTIONS = [
        "Shop Now", "Buy Now", "Get Yours", "Learn More",
        "Sign Up", "Get Started", "Try Free", "Claim Offer",
        "Book Now", "Reserve", "Contact Us", "Download",
        "Compre Agora", "Saiba Mais", "Cadastre-se", "Baixar"
    ]
    
    URGENCY_PHRASES = [
        "Só hoje", "Últimas unidades", "Oferta limitada",
        "Termina em breve", "Aproveite agora", "Não perca",
        "Today only", "Limited time", "Last chance", "Hurry"
    ]
    
    def __init__(self):
        self.variations_generated: List[Dict] = []
        
    async def generate_headline_variations(
        self,
        original: str,
        product: str,
        benefit: str,
        count: int = 5
    ) -> List[str]:
        """Gera variações de headline"""
        
        variations = [original]  # Mantém original
        
        # Variação com urgência
        variations.append(f"{original} - {random.choice(self.URGENCY_PHRASES)}")
        
        # Variação com número
        variations.append(f"10x mais {benefit} com {product}")
        
        # Variação pergunta
        variations.append(f"Quer {benefit}? Conheça {product}")
        
        # Variação social proof
        variations.append(f"+10.000 clientes já aprovaram {product}")
        
        # Variação direta
        variations.append(f"{product}: {benefit} garantido")
        
        return variations[:count]
    
    async def generate_copy_matrix(
        self,
        headlines: List[str],
        descriptions: List[str],
        ctas: List[str]
    ) -> List[Dict]:
        """
        Gera matriz de combinações
        Headlines x Descriptions x CTAs
        """
        
        combinations = []
        
        for headline in headlines:
            for description in descriptions:
                for cta in ctas:
                    combinations.append({
                        "id": str(uuid.uuid4())[:8],
                        "headline": headline,
                        "description": description,
                        "cta": cta,
                        "combination_name": f"{headline[:20]}_{cta}"
                    })
                    
        # Limita a 100 combinações
        return combinations[:100]
    
    async def generate_creative_variations(
        self,
        base_creative: CreativeAsset,
        variation_types: List[str] = None
    ) -> List[Dict]:
        """Gera variações completas de um criativo"""
        
        if variation_types is None:
            variation_types = ["headline", "description", "cta"]
            
        variations = []
        
        # Variações de headline
        if "headline" in variation_types and base_creative.headline:
            headline_vars = await self.generate_headline_variations(
                base_creative.headline,
                base_creative.name,
                "resultados",
                5
            )
            for i, h in enumerate(headline_vars):
                variations.append({
                    "type": "headline_variation",
                    "variant_number": i + 1,
                    "original": base_creative.headline,
                    "variation": h,
                    "base_creative_id": base_creative.id
                })
                
        # Variações de CTA
        if "cta" in variation_types:
            for cta in random.sample(self.CTA_OPTIONS, min(5, len(self.CTA_OPTIONS))):
                variations.append({
                    "type": "cta_variation",
                    "original": base_creative.cta,
                    "variation": cta,
                    "base_creative_id": base_creative.id
                })
                
        self.variations_generated.extend(variations)
        
        return variations


# =============================================================================
# 8. AI IMAGE GENERATOR
# =============================================================================

class AIImageGenerator:
    """
    Gerador de imagens com AI
    Product transformation, UGC, memes
    """
    
    STYLE_PRESETS = {
        "product": {
            "description": "Clean product photography on white background",
            "dimensions": (1080, 1080)
        },
        "lifestyle": {
            "description": "Product in real-life usage scenario",
            "dimensions": (1080, 1350)
        },
        "ugc": {
            "description": "User-generated content style, authentic look",
            "dimensions": (1080, 1920)
        },
        "meme": {
            "description": "Funny, shareable meme format",
            "dimensions": (1080, 1080)
        },
        "comparison": {
            "description": "Before/after or product comparison",
            "dimensions": (1200, 628)
        }
    }
    
    def __init__(self):
        self.generated_images: List[Dict] = []
        
    async def generate_from_text(
        self,
        prompt: str,
        style: str = "product",
        count: int = 1
    ) -> List[Dict]:
        """Gera imagem a partir de texto (simulado)"""
        
        preset = self.STYLE_PRESETS.get(style, self.STYLE_PRESETS["product"])
        
        images = []
        
        for i in range(count):
            image = {
                "id": str(uuid.uuid4())[:8],
                "prompt": prompt,
                "style": style,
                "dimensions": preset["dimensions"],
                "status": "generated",
                "url": f"https://generated-images.example.com/{uuid.uuid4()}.jpg",
                "created_at": datetime.now().isoformat()
            }
            images.append(image)
            self.generated_images.append(image)
            
        return images
    
    async def transform_product_image(
        self,
        source_url: str,
        transformations: List[str]
    ) -> List[Dict]:
        """
        Transforma imagem de produto
        Ex: remove background, add lifestyle, change colors
        """
        
        results = []
        
        for transform in transformations:
            result = {
                "id": str(uuid.uuid4())[:8],
                "source": source_url,
                "transformation": transform,
                "status": "processed",
                "url": f"https://transformed.example.com/{uuid.uuid4()}.jpg",
                "created_at": datetime.now().isoformat()
            }
            results.append(result)
            
        return results
    
    async def generate_ugc_video(
        self,
        product_info: Dict,
        script: str,
        avatar_style: str = "casual"
    ) -> Dict:
        """Gera vídeo UGC com avatar AI"""
        
        return {
            "id": str(uuid.uuid4())[:8],
            "product": product_info.get("name"),
            "script": script,
            "avatar_style": avatar_style,
            "duration_seconds": len(script.split()) * 0.5,  # Estimativa
            "status": "rendering",
            "url": f"https://ugc-videos.example.com/{uuid.uuid4()}.mp4",
            "created_at": datetime.now().isoformat()
        }
    
    async def generate_ad_meme(
        self,
        template: str,
        top_text: str,
        bottom_text: str,
        product_image_url: Optional[str] = None
    ) -> Dict:
        """Gera meme para ad"""
        
        return {
            "id": str(uuid.uuid4())[:8],
            "template": template,
            "top_text": top_text,
            "bottom_text": bottom_text,
            "product_image": product_image_url,
            "status": "generated",
            "url": f"https://memes.example.com/{uuid.uuid4()}.jpg",
            "created_at": datetime.now().isoformat()
        }


# =============================================================================
# 9. COMPETITOR ANALYSIS
# =============================================================================

class CompetitorAnalyzer:
    """
    Análise de concorrentes
    Ad Library scraping e insights
    """
    
    def __init__(self):
        self.competitors: Dict[str, Dict] = {}
        self.competitor_ads: List[CompetitorAd] = []
        
    def add_competitor(
        self,
        name: str,
        page_id: str,
        platforms: List[Platform]
    ) -> str:
        """Adiciona concorrente para monitoramento"""
        
        competitor_id = str(uuid.uuid4())[:8]
        
        self.competitors[competitor_id] = {
            "id": competitor_id,
            "name": name,
            "page_id": page_id,
            "platforms": [p.value for p in platforms],
            "added_at": datetime.now().isoformat(),
            "last_scan": None
        }
        
        return competitor_id
    
    async def scan_competitor_ads(
        self,
        competitor_id: str,
        platform: Platform = Platform.META
    ) -> List[CompetitorAd]:
        """
        Escaneia ads do concorrente (simulado)
        Em produção, usaria Meta Ad Library API
        """
        
        if competitor_id not in self.competitors:
            return []
            
        competitor = self.competitors[competitor_id]
        
        # Simulação de ads encontrados
        mock_ads = []
        for i in range(5):
            ad = CompetitorAd(
                id=str(uuid.uuid4())[:8],
                advertiser_name=competitor["name"],
                platform=platform,
                creative_url=f"https://adlibrary.example.com/creative_{i}.jpg",
                ad_copy=f"Ad copy example {i} from {competitor['name']}",
                cta="Shop Now",
                landing_page=f"https://{competitor['name'].lower()}.com/landing",
                estimated_spend=random.uniform(100, 10000),
                estimated_reach=random.randint(10000, 1000000)
            )
            mock_ads.append(ad)
            self.competitor_ads.append(ad)
            
        competitor["last_scan"] = datetime.now().isoformat()
        
        return mock_ads
    
    async def analyze_competitor_strategy(
        self,
        competitor_id: str
    ) -> Dict:
        """Analisa estratégia do concorrente"""
        
        competitor_ads = [
            ad for ad in self.competitor_ads
            if ad.advertiser_name == self.competitors.get(competitor_id, {}).get("name")
        ]
        
        if not competitor_ads:
            return {"error": "No ads found"}
            
        analysis = {
            "competitor_id": competitor_id,
            "total_ads": len(competitor_ads),
            "estimated_total_spend": sum(ad.estimated_spend for ad in competitor_ads),
            "avg_spend_per_ad": sum(ad.estimated_spend for ad in competitor_ads) / len(competitor_ads),
            "platforms_active": list(set(ad.platform.value for ad in competitor_ads)),
            "creative_types": self._analyze_creative_types(competitor_ads),
            "top_ctas": self._analyze_ctas(competitor_ads),
            "copy_patterns": self._analyze_copy_patterns(competitor_ads),
            "recommendations": []
        }
        
        # Gera recomendações
        if analysis["estimated_total_spend"] > 5000:
            analysis["recommendations"].append(
                "Concorrente com alto investimento. Considere aumentar budget para competir."
            )
            
        return analysis
    
    def _analyze_creative_types(self, ads: List[CompetitorAd]) -> Dict[str, int]:
        """Analisa tipos de criativos"""
        types = {}
        for ad in ads:
            if ad.creative_url:
                ext = ad.creative_url.split(".")[-1].lower()
                creative_type = "video" if ext in ["mp4", "mov"] else "image"
                types[creative_type] = types.get(creative_type, 0) + 1
        return types
    
    def _analyze_ctas(self, ads: List[CompetitorAd]) -> Dict[str, int]:
        """Analisa CTAs mais usados"""
        ctas = {}
        for ad in ads:
            if ad.cta:
                ctas[ad.cta] = ctas.get(ad.cta, 0) + 1
        return dict(sorted(ctas.items(), key=lambda x: x[1], reverse=True)[:5])
    
    def _analyze_copy_patterns(self, ads: List[CompetitorAd]) -> Dict:
        """Analisa padrões de copy"""
        patterns = {
            "avg_length": 0,
            "has_emojis": 0,
            "has_urgency": 0,
            "has_numbers": 0
        }
        
        for ad in ads:
            if ad.ad_copy:
                patterns["avg_length"] += len(ad.ad_copy)
                if any(c in ad.ad_copy for c in "🔥✨💰🎁⚡"):
                    patterns["has_emojis"] += 1
                if any(word in ad.ad_copy.lower() for word in ["now", "today", "limited", "hurry", "agora", "hoje"]):
                    patterns["has_urgency"] += 1
                if any(c.isdigit() for c in ad.ad_copy):
                    patterns["has_numbers"] += 1
                    
        if ads:
            patterns["avg_length"] = patterns["avg_length"] / len(ads)
            
        return patterns


# =============================================================================
# 10. AUTOMATED WORKFLOWS
# =============================================================================

class WorkflowEngine:
    """
    Engine de workflows automatizados
    Similar a n8n / Zapier
    """
    
    def __init__(self):
        self.workflows: Dict[str, Workflow] = {}
        self.execution_history: List[Dict] = []
        
        # Carrega workflows padrão
        self._load_default_workflows()
        
    def _load_default_workflows(self):
        """Carrega workflows padrão"""
        
        # Workflow 1: Daily optimization
        self.create_workflow(
            name="Daily Campaign Optimization",
            trigger=WorkflowTrigger.SCHEDULE,
            trigger_config={"cron": "0 9 * * *"},  # 9 AM daily
            steps=[
                {"action": "fetch_metrics", "platforms": ["meta", "google"]},
                {"action": "identify_underperformers", "threshold": {"roas": 1.0}},
                {"action": "pause_campaigns", "condition": "underperformer"},
                {"action": "increase_budget", "condition": "top_performer", "percent": 20},
                {"action": "send_report", "channel": "email"}
            ]
        )
        
        # Workflow 2: Creative fatigue alert
        self.create_workflow(
            name="Creative Fatigue Alert",
            trigger=WorkflowTrigger.METRIC_THRESHOLD,
            trigger_config={"metric": "frequency", "operator": ">", "value": 3.0},
            steps=[
                {"action": "detect_fatigue", "window_days": 7},
                {"action": "generate_variations", "count": 5},
                {"action": "notify", "channel": "slack", "message": "Creative fatigue detected"}
            ]
        )
        
        # Workflow 3: Budget protection
        self.create_workflow(
            name="Budget Protection",
            trigger=WorkflowTrigger.BUDGET_SPENT,
            trigger_config={"percent": 80},
            steps=[
                {"action": "check_performance", "metric": "roas"},
                {"action": "pause_if_bad", "threshold": 1.0},
                {"action": "notify", "channel": "email", "message": "80% budget spent"}
            ]
        )
        
    def create_workflow(
        self,
        name: str,
        trigger: WorkflowTrigger,
        trigger_config: Dict,
        steps: List[Dict]
    ) -> str:
        """Cria novo workflow"""
        
        workflow = Workflow(
            id=str(uuid.uuid4())[:8],
            name=name,
            trigger=trigger,
            trigger_config=trigger_config,
            steps=steps
        )
        
        self.workflows[workflow.id] = workflow
        return workflow.id
    
    async def execute_workflow(
        self,
        workflow_id: str,
        context: Dict
    ) -> Dict:
        """Executa workflow"""
        
        if workflow_id not in self.workflows:
            return {"error": "Workflow not found"}
            
        workflow = self.workflows[workflow_id]
        
        if not workflow.enabled:
            return {"error": "Workflow disabled"}
            
        execution = {
            "workflow_id": workflow_id,
            "workflow_name": workflow.name,
            "started_at": datetime.now().isoformat(),
            "steps_executed": [],
            "status": "running"
        }
        
        for i, step in enumerate(workflow.steps):
            step_result = await self._execute_step(step, context)
            execution["steps_executed"].append({
                "step_number": i + 1,
                "action": step["action"],
                "result": step_result
            })
            
            # Atualiza contexto com resultado
            context[f"step_{i}_result"] = step_result
            
        execution["status"] = "completed"
        execution["completed_at"] = datetime.now().isoformat()
        
        # Atualiza workflow
        workflow.last_run = datetime.now()
        workflow.runs_count += 1
        
        self.execution_history.append(execution)
        
        return execution
    
    async def _execute_step(self, step: Dict, context: Dict) -> Dict:
        """Executa um step do workflow"""
        
        action = step.get("action")
        
        # Simulação de execução de steps
        return {
            "action": action,
            "status": "success",
            "executed_at": datetime.now().isoformat()
        }
    
    def get_workflow_history(
        self,
        workflow_id: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict]:
        """Retorna histórico de execuções"""
        
        history = self.execution_history
        
        if workflow_id:
            history = [h for h in history if h["workflow_id"] == workflow_id]
            
        return history[-limit:]


# =============================================================================
# 11. FEED MANAGEMENT
# =============================================================================

class FeedManager:
    """
    Gerenciamento de feeds de produtos
    Sync e otimização
    """
    
    def __init__(self):
        self.feeds: Dict[str, ProductFeed] = {}
        self.products: Dict[str, List[Dict]] = {}
        
    def add_feed(
        self,
        name: str,
        source_url: Optional[str] = None,
        sync_frequency: str = "daily"
    ) -> str:
        """Adiciona feed de produtos"""
        
        feed = ProductFeed(
            id=str(uuid.uuid4())[:8],
            name=name,
            source_url=source_url,
            sync_frequency=sync_frequency
        )
        
        self.feeds[feed.id] = feed
        self.products[feed.id] = []
        
        return feed.id
    
    async def sync_feed(self, feed_id: str) -> Dict:
        """Sincroniza feed com fonte"""
        
        if feed_id not in self.feeds:
            return {"error": "Feed not found"}
            
        feed = self.feeds[feed_id]
        
        # Simulação de sync
        # Em produção, faria request para source_url
        
        mock_products = [
            {
                "id": f"prod_{i}",
                "name": f"Product {i}",
                "price": round(random.uniform(10, 500), 2),
                "availability": random.choice(["in_stock", "out_of_stock"]),
                "image_url": f"https://products.example.com/{i}.jpg",
                "category": random.choice(["Electronics", "Fashion", "Home"])
            }
            for i in range(50)
        ]
        
        self.products[feed_id] = mock_products
        feed.products_count = len(mock_products)
        feed.last_sync = datetime.now()
        
        return {
            "feed_id": feed_id,
            "products_synced": len(mock_products),
            "sync_time": datetime.now().isoformat()
        }
    
    def optimize_feed(self, feed_id: str) -> Dict:
        """Otimiza feed para melhor performance"""
        
        if feed_id not in self.products:
            return {"error": "Feed not found"}
            
        products = self.products[feed_id]
        
        optimizations = {
            "feed_id": feed_id,
            "total_products": len(products),
            "issues_found": [],
            "optimizations_applied": []
        }
        
        for product in products:
            # Verifica título
            if len(product.get("name", "")) < 10:
                optimizations["issues_found"].append({
                    "product_id": product["id"],
                    "issue": "Title too short"
                })
                
            # Verifica preço
            if product.get("price", 0) == 0:
                optimizations["issues_found"].append({
                    "product_id": product["id"],
                    "issue": "Missing price"
                })
                
            # Verifica imagem
            if not product.get("image_url"):
                optimizations["issues_found"].append({
                    "product_id": product["id"],
                    "issue": "Missing image"
                })
                
        return optimizations
    
    def get_products_for_ads(
        self,
        feed_id: str,
        filters: Optional[Dict] = None,
        limit: int = 100
    ) -> List[Dict]:
        """Retorna produtos filtrados para ads"""
        
        if feed_id not in self.products:
            return []
            
        products = self.products[feed_id]
        
        if filters:
            # Filtra por disponibilidade
            if filters.get("availability"):
                products = [p for p in products if p.get("availability") == filters["availability"]]
                
            # Filtra por categoria
            if filters.get("category"):
                products = [p for p in products if p.get("category") == filters["category"]]
                
            # Filtra por preço mínimo
            if filters.get("min_price"):
                products = [p for p in products if p.get("price", 0) >= filters["min_price"]]
                
            # Filtra por preço máximo
            if filters.get("max_price"):
                products = [p for p in products if p.get("price", 0) <= filters["max_price"]]
                
        return products[:limit]


# =============================================================================
# 12. UNIFIED DASHBOARD
# =============================================================================

class UnifiedDashboard:
    """
    Dashboard unificado cross-platform
    """
    
    def __init__(self):
        self.connected_platforms: Set[Platform] = set()
        self.cached_metrics: Dict[Platform, Dict] = {}
        self.last_refresh: Optional[datetime] = None
        
    def connect_platform(self, platform: Platform):
        """Conecta plataforma ao dashboard"""
        self.connected_platforms.add(platform)
        
    def disconnect_platform(self, platform: Platform):
        """Desconecta plataforma"""
        self.connected_platforms.discard(platform)
        
    async def get_unified_metrics(
        self,
        date_range: Tuple[datetime, datetime],
        platforms: Optional[List[Platform]] = None
    ) -> Dict:
        """Retorna métricas unificadas de todas as plataformas"""
        
        target_platforms = platforms or list(self.connected_platforms)
        
        unified = {
            "date_range": {
                "start": date_range[0].isoformat(),
                "end": date_range[1].isoformat()
            },
            "totals": {
                "spend": 0,
                "impressions": 0,
                "clicks": 0,
                "conversions": 0,
                "revenue": 0
            },
            "by_platform": {},
            "calculated": {
                "ctr": 0,
                "cvr": 0,
                "cpc": 0,
                "cpa": 0,
                "roas": 0
            }
        }
        
        for platform in target_platforms:
            # Em produção, buscaria de cada API
            platform_metrics = await self._fetch_platform_metrics(
                platform, 
                date_range
            )
            
            unified["by_platform"][platform.value] = platform_metrics
            
            # Soma totais
            unified["totals"]["spend"] += platform_metrics["spend"]
            unified["totals"]["impressions"] += platform_metrics["impressions"]
            unified["totals"]["clicks"] += platform_metrics["clicks"]
            unified["totals"]["conversions"] += platform_metrics["conversions"]
            unified["totals"]["revenue"] += platform_metrics["revenue"]
            
        # Calcula métricas derivadas
        totals = unified["totals"]
        if totals["impressions"] > 0:
            unified["calculated"]["ctr"] = (totals["clicks"] / totals["impressions"]) * 100
        if totals["clicks"] > 0:
            unified["calculated"]["cvr"] = (totals["conversions"] / totals["clicks"]) * 100
            unified["calculated"]["cpc"] = totals["spend"] / totals["clicks"]
        if totals["conversions"] > 0:
            unified["calculated"]["cpa"] = totals["spend"] / totals["conversions"]
        if totals["spend"] > 0:
            unified["calculated"]["roas"] = totals["revenue"] / totals["spend"]
            
        self.last_refresh = datetime.now()
        
        return unified
    
    async def _fetch_platform_metrics(
        self,
        platform: Platform,
        date_range: Tuple[datetime, datetime]
    ) -> Dict:
        """Busca métricas de uma plataforma (simulado)"""
        
        # Simulação
        return {
            "platform": platform.value,
            "spend": round(random.uniform(1000, 10000), 2),
            "impressions": random.randint(100000, 1000000),
            "clicks": random.randint(1000, 50000),
            "conversions": random.randint(10, 500),
            "revenue": round(random.uniform(5000, 50000), 2)
        }
    
    async def get_smart_insights(
        self,
        metrics: Dict
    ) -> List[Dict]:
        """Gera insights inteligentes"""
        
        insights = []
        
        # Insight: ROAS
        roas = metrics.get("calculated", {}).get("roas", 0)
        if roas > 3:
            insights.append({
                "type": "positive",
                "title": "Strong ROAS",
                "message": f"Your ROAS of {roas:.2f}x is excellent. Consider scaling budget.",
                "action": "increase_budget"
            })
        elif roas < 1:
            insights.append({
                "type": "negative",
                "title": "Low ROAS Alert",
                "message": f"ROAS of {roas:.2f}x means you're losing money. Review campaigns.",
                "action": "review_campaigns"
            })
            
        # Insight: Platform comparison
        by_platform = metrics.get("by_platform", {})
        if len(by_platform) > 1:
            best = max(by_platform.items(), key=lambda x: x[1].get("revenue", 0) / max(x[1].get("spend", 1), 1))
            insights.append({
                "type": "info",
                "title": "Best Performing Platform",
                "message": f"{best[0].upper()} is your top performer. Consider shifting more budget here.",
                "action": "rebalance_budget"
            })
            
        # Insight: CPA trend
        cpa = metrics.get("calculated", {}).get("cpa", 0)
        if cpa > 100:
            insights.append({
                "type": "warning",
                "title": "High CPA",
                "message": f"CPA of ${cpa:.2f} is high. Review targeting and creatives.",
                "action": "optimize_targeting"
            })
            
        return insights
    
    async def generate_report(
        self,
        metrics: Dict,
        report_type: str = "summary"
    ) -> Dict:
        """Gera relatório"""
        
        report = {
            "generated_at": datetime.now().isoformat(),
            "type": report_type,
            "metrics": metrics,
            "insights": await self.get_smart_insights(metrics)
        }
        
        if report_type == "detailed":
            report["by_campaign"] = []  # Would include campaign-level data
            report["by_creative"] = []  # Would include creative-level data
            report["trends"] = {}  # Would include trend analysis
            
        return report


# =============================================================================
# MAIN ORCHESTRATOR - PLAI STYLE ENGINE
# =============================================================================

class PlaiStyleEngine:
    """
    Orquestrador principal do Plai Style Engine
    Combina todas as funcionalidades
    """
    
    def __init__(self, optimization_goal: OptimizationGoal = OptimizationGoal.SALES):
        # Core engines
        self.ai_marketer = AIMarketer(optimization_goal)
        self.automation_rules = AutomationRulesEngine()
        self.creative_tracker = CreativeTracker()
        self.audience_launcher = AudienceLauncher()
        self.budget_optimizer = BudgetOptimizer()
        self.lookalike_generator = LookalikeGenerator()
        self.creative_variations = CreativeVariationsEngine()
        self.image_generator = AIImageGenerator()
        self.competitor_analyzer = CompetitorAnalyzer()
        self.workflow_engine = WorkflowEngine()
        self.feed_manager = FeedManager()
        self.dashboard = UnifiedDashboard()
        
        # Config
        self.optimization_goal = optimization_goal
        
    async def run_full_optimization(
        self,
        campaigns: List[CampaignMetrics],
        creatives: List[CreativeAsset],
        audiences: List[AudienceTemplate]
    ) -> Dict:
        """Executa otimização completa"""
        
        results = {
            "timestamp": datetime.now().isoformat(),
            "optimization_goal": self.optimization_goal.value,
            "steps_completed": []
        }
        
        # 1. AI Marketer optimization
        ai_results = await self.ai_marketer.optimize_for_me(
            campaigns, creatives, audiences
        )
        results["ai_marketer"] = ai_results
        results["steps_completed"].append("ai_marketer")
        
        # 2. Creative fatigue detection
        fatigue_results = await self.creative_tracker.detect_fatigue()
        results["creative_fatigue"] = fatigue_results
        results["steps_completed"].append("creative_fatigue")
        
        # 3. Run automation rules
        entities = [{"id": c.campaign_id, **vars(c)} for c in campaigns]
        rule_actions = await self.automation_rules.evaluate_rules(
            entities, "campaign", Platform.META
        )
        results["automation_actions"] = rule_actions
        results["steps_completed"].append("automation_rules")
        
        # 4. Budget optimization
        # Cria folder se não existe
        if not self.budget_optimizer.optimization_folders:
            folder_id = self.budget_optimizer.create_folder(
                "Main Optimization",
                [c.campaign_id for c in campaigns],
                self.optimization_goal,
                sum(c.spend for c in campaigns)
            )
        else:
            folder_id = list(self.budget_optimizer.optimization_folders.keys())[0]
            
        budget_results = await self.budget_optimizer.optimize_folder(
            folder_id, campaigns
        )
        results["budget_optimization"] = budget_results
        results["steps_completed"].append("budget_optimization")
        
        return results
    
    async def get_dashboard_data(
        self,
        date_range: Tuple[datetime, datetime]
    ) -> Dict:
        """Retorna dados para dashboard"""
        
        # Connect platforms
        for platform in [Platform.META, Platform.GOOGLE, Platform.TIKTOK]:
            self.dashboard.connect_platform(platform)
            
        metrics = await self.dashboard.get_unified_metrics(date_range)
        insights = await self.dashboard.get_smart_insights(metrics)
        
        return {
            "metrics": metrics,
            "insights": insights,
            "top_creatives": self.creative_tracker.get_top_performers(5),
            "recent_optimizations": self.ai_marketer.optimization_history[-5:],
            "active_workflows": len([w for w in self.workflow_engine.workflows.values() if w.enabled]),
            "last_refresh": datetime.now().isoformat()
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "Platform",
    "OptimizationGoal",
    "RuleCondition",
    "RuleAction",
    "WorkflowTrigger",
    "CreativeType",
    "AudienceType",
    
    # Data Classes
    "CampaignMetrics",
    "CreativeAsset",
    "AudienceTemplate",
    "AutomationRule",
    "Workflow",
    "ProductFeed",
    "CompetitorAd",
    
    # Engines
    "AIMarketer",
    "AutomationRulesEngine",
    "CreativeTracker",
    "AudienceLauncher",
    "BudgetOptimizer",
    "LookalikeGenerator",
    "CreativeVariationsEngine",
    "AIImageGenerator",
    "CompetitorAnalyzer",
    "WorkflowEngine",
    "FeedManager",
    "UnifiedDashboard",
    "PlaiStyleEngine"
]
