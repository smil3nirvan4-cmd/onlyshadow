"""
S.S.I. SHADOW - Meta Ads Engine
Baseado em análise detalhada de Madgicx e Bïrch (Revealbot)

Funcionalidades implementadas:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MADGICX FEATURES:
- AI Marketer: Audita conta, identifica oportunidades, recomenda ações
- Automation Tactics: Regras pré-configuradas por experts
- Custom Automation: Regras personalizadas com builder avançado
- AI Bidding: Otimização de bid com ML
- Cloud Tracking / CAPI Gateway: Server-side tracking
- Creative Insights: Análise de criativos com AI tagging
- Ad Copy Insights: Análise de copy performance
- Audience Launcher: Lançamento massivo de audiences
- AI Ad Generator: Geração de ads com AI
- Cross-channel Reporting: Dashboard unificado

BÏRCH (REVEALBOT) FEATURES:
- Advanced Rule Constructor: AND/OR operators, nested conditions
- Metric Comparison: Comparar métrica com métrica
- Ranking Conditions: Condições baseadas em ranking relativo
- Custom Metrics: Métricas personalizadas calculadas
- 20+ Actions: Mais de 20 ações disponíveis
- Google Sheets Integration: Dados externos em automações
- Rule Logs: Histórico detalhado de execução
- Bulk Creation: Criação em massa de ads/audiences
- Post Boosting: Boost automático de posts orgânicos
- Slack Notifications: Alertas em tempo real
- Multi-platform: Meta, Google, TikTok, Snapchat

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Callable, Union, Tuple
from enum import Enum
from datetime import datetime, timedelta
from abc import ABC, abstractmethod
import json
import hashlib
import asyncio
import re
import math
import statistics


# =============================================================================
# ENUMS E TYPES
# =============================================================================

class Platform(Enum):
    META = "meta"
    GOOGLE = "google"
    TIKTOK = "tiktok"
    SNAPCHAT = "snapchat"

class CampaignObjective(Enum):
    CONVERSIONS = "conversions"
    TRAFFIC = "traffic"
    ENGAGEMENT = "engagement"
    APP_INSTALLS = "app_installs"
    LEADS = "leads"
    SALES = "sales"
    AWARENESS = "awareness"
    REACH = "reach"
    VIDEO_VIEWS = "video_views"

class AdStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    DELETED = "deleted"
    PENDING = "pending"
    IN_REVIEW = "in_review"

class RuleAction(Enum):
    # Budget Actions
    INCREASE_BUDGET = "increase_budget"
    DECREASE_BUDGET = "decrease_budget"
    SET_BUDGET = "set_budget"
    
    # Status Actions
    PAUSE = "pause"
    ENABLE = "enable"
    DELETE = "delete"
    
    # Bid Actions
    INCREASE_BID = "increase_bid"
    DECREASE_BID = "decrease_bid"
    SET_BID = "set_bid"
    
    # Scale Actions
    DUPLICATE = "duplicate"
    DUPLICATE_TO_CAMPAIGN = "duplicate_to_campaign"
    
    # Notification Actions
    SEND_SLACK = "send_slack"
    SEND_EMAIL = "send_email"
    SEND_WEBHOOK = "send_webhook"
    
    # Schedule Actions
    SCHEDULE_PAUSE = "schedule_pause"
    SCHEDULE_ENABLE = "schedule_enable"
    
    # Creative Actions
    ROTATE_CREATIVE = "rotate_creative"
    REFRESH_CREATIVE = "refresh_creative"
    
    # Audience Actions
    EXPAND_AUDIENCE = "expand_audience"
    NARROW_AUDIENCE = "narrow_audience"
    CREATE_LOOKALIKE = "create_lookalike"
    
    # Attribution Actions
    CHANGE_ATTRIBUTION = "change_attribution"

class ConditionOperator(Enum):
    GREATER_THAN = ">"
    LESS_THAN = "<"
    GREATER_EQUAL = ">="
    LESS_EQUAL = "<="
    EQUALS = "=="
    NOT_EQUALS = "!="
    CONTAINS = "contains"
    NOT_CONTAINS = "not_contains"
    IN_RANGE = "in_range"
    NOT_IN_RANGE = "not_in_range"
    IS_TOP_PERCENT = "is_top_percent"
    IS_BOTTOM_PERCENT = "is_bottom_percent"

class LogicalOperator(Enum):
    AND = "and"
    OR = "or"

class TimeRange(Enum):
    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_3_DAYS = "last_3_days"
    LAST_7_DAYS = "last_7_days"
    LAST_14_DAYS = "last_14_days"
    LAST_30_DAYS = "last_30_days"
    THIS_WEEK = "this_week"
    LAST_WEEK = "last_week"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"
    LIFETIME = "lifetime"
    CUSTOM = "custom"

class CreativeType(Enum):
    IMAGE = "image"
    VIDEO = "video"
    CAROUSEL = "carousel"
    COLLECTION = "collection"
    INSTANT_EXPERIENCE = "instant_experience"
    DYNAMIC = "dynamic"

class AudienceType(Enum):
    CUSTOM = "custom"
    LOOKALIKE = "lookalike"
    SAVED = "saved"
    INTEREST = "interest"
    BEHAVIOR = "behavior"


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class Metric:
    """Métrica para automação"""
    name: str
    value: float
    time_range: TimeRange = TimeRange.LAST_7_DAYS
    platform: Platform = Platform.META
    
@dataclass
class CustomMetric:
    """Métrica customizada calculada"""
    name: str
    formula: str  # Ex: "(revenue - cost) / cost * 100"
    description: str = ""
    
    def calculate(self, metrics: Dict[str, float]) -> float:
        """Calcula métrica customizada"""
        try:
            # Substitui nomes de métricas por valores
            expression = self.formula
            for name, value in metrics.items():
                expression = expression.replace(name, str(value))
            return eval(expression)
        except:
            return 0.0

@dataclass
class Condition:
    """Condição para regra de automação"""
    metric: str
    operator: ConditionOperator
    value: Union[float, str, List[float]]
    time_range: TimeRange = TimeRange.LAST_7_DAYS
    compare_to_metric: Optional[str] = None  # Para comparação métrica vs métrica
    compare_time_range: Optional[TimeRange] = None  # Período de comparação
    
@dataclass
class ConditionGroup:
    """Grupo de condições com operador lógico"""
    conditions: List[Union['Condition', 'ConditionGroup']]
    operator: LogicalOperator = LogicalOperator.AND

@dataclass
class ActionConfig:
    """Configuração de ação"""
    action: RuleAction
    value: Optional[Union[float, str, Dict]] = None
    percentage: Optional[float] = None  # Para aumentos/diminuições percentuais
    absolute: Optional[float] = None  # Para valores absolutos
    max_value: Optional[float] = None  # Limite máximo
    min_value: Optional[float] = None  # Limite mínimo
    slack_channel: Optional[str] = None
    email_to: Optional[str] = None
    webhook_url: Optional[str] = None
    
@dataclass
class AutomationRule:
    """Regra de automação completa"""
    id: str
    name: str
    description: str
    platform: Platform
    level: str  # campaign, adset, ad
    conditions: ConditionGroup
    actions: List[ActionConfig]
    schedule: Dict[str, Any]  # Frequência de execução
    is_active: bool = True
    created_at: datetime = field(default_factory=datetime.now)
    last_run: Optional[datetime] = None
    run_count: int = 0
    affected_items_count: int = 0

@dataclass
class RuleLog:
    """Log de execução de regra"""
    rule_id: str
    timestamp: datetime
    items_checked: int
    items_affected: int
    actions_taken: List[Dict]
    metrics_snapshot: Dict[str, float]
    errors: List[str] = field(default_factory=list)

@dataclass 
class CreativeInsight:
    """Insight de criativo"""
    creative_id: str
    creative_type: CreativeType
    elements: Dict[str, Any]  # Elementos detectados por AI
    performance_score: float
    fatigue_score: float
    recommendations: List[str]
    
@dataclass
class AdCopyInsight:
    """Insight de copy"""
    ad_id: str
    headline: str
    description: str
    cta: str
    sentiment_score: float
    urgency_score: float
    clarity_score: float
    emotional_triggers: List[str]
    power_words: List[str]
    recommendations: List[str]

@dataclass
class AudiencePerformance:
    """Performance de audience cross-campaign"""
    audience_id: str
    audience_name: str
    audience_type: AudienceType
    campaigns_count: int
    total_spend: float
    total_revenue: float
    roas: float
    cpa: float
    cvr: float
    ctr: float
    reach: int
    frequency: float
    
@dataclass
class AccountAudit:
    """Resultado de auditoria da conta"""
    timestamp: datetime
    account_id: str
    platform: Platform
    health_score: float
    issues: List[Dict]
    opportunities: List[Dict]
    quick_wins: List[Dict]
    estimated_savings: float
    estimated_revenue_increase: float


# =============================================================================
# RULE ENGINE - MOTOR DE REGRAS (BASEADO EM BÏRCH)
# =============================================================================

class RuleEngine:
    """
    Motor de regras avançado similar ao Bïrch (Revealbot)
    
    Features:
    - AND/OR operators com nested conditions
    - Comparação métrica vs métrica
    - Ranking conditions (top/bottom X%)
    - Custom metrics calculadas
    - 20+ actions disponíveis
    - Rule logs detalhados
    """
    
    def __init__(self):
        self.rules: Dict[str, AutomationRule] = {}
        self.custom_metrics: Dict[str, CustomMetric] = {}
        self.logs: List[RuleLog] = []
        self.external_data: Dict[str, Dict] = {}  # Google Sheets integration
        
        # Métricas padrão disponíveis
        self.standard_metrics = [
            "spend", "impressions", "clicks", "reach", "frequency",
            "ctr", "cpc", "cpm", "conversions", "conversion_value",
            "roas", "cpa", "cvr", "add_to_cart", "purchases",
            "leads", "link_clicks", "video_views", "video_p25",
            "video_p50", "video_p75", "video_p100", "engagement",
            "post_engagement", "page_engagement", "cost_per_lead",
            "cost_per_atc", "cost_per_purchase", "revenue", "profit",
            "margin", "aov", "ltv", "frequency_cap", "quality_score"
        ]
        
    def register_custom_metric(self, metric: CustomMetric) -> None:
        """Registra métrica customizada"""
        self.custom_metrics[metric.name] = metric
        
    def load_external_data(self, source: str, data: Dict) -> None:
        """Carrega dados externos (Google Sheets)"""
        self.external_data[source] = data
        
    def create_rule(self, rule: AutomationRule) -> str:
        """Cria nova regra de automação"""
        self.rules[rule.id] = rule
        return rule.id
    
    def evaluate_condition(
        self, 
        condition: Condition, 
        metrics: Dict[str, float],
        all_items_metrics: Optional[List[Dict[str, float]]] = None
    ) -> bool:
        """Avalia uma condição"""
        
        # Obtém valor da métrica
        metric_value = metrics.get(condition.metric, 0)
        
        # Se é custom metric, calcula
        if condition.metric in self.custom_metrics:
            metric_value = self.custom_metrics[condition.metric].calculate(metrics)
            
        # Se é comparação com outra métrica
        if condition.compare_to_metric:
            compare_value = metrics.get(condition.compare_to_metric, 0)
            if condition.compare_to_metric in self.custom_metrics:
                compare_value = self.custom_metrics[condition.compare_to_metric].calculate(metrics)
            condition_value = compare_value
        else:
            condition_value = condition.value
            
        # Avalia operador
        op = condition.operator
        
        if op == ConditionOperator.GREATER_THAN:
            return metric_value > condition_value
        elif op == ConditionOperator.LESS_THAN:
            return metric_value < condition_value
        elif op == ConditionOperator.GREATER_EQUAL:
            return metric_value >= condition_value
        elif op == ConditionOperator.LESS_EQUAL:
            return metric_value <= condition_value
        elif op == ConditionOperator.EQUALS:
            return metric_value == condition_value
        elif op == ConditionOperator.NOT_EQUALS:
            return metric_value != condition_value
        elif op == ConditionOperator.CONTAINS:
            return str(condition_value) in str(metric_value)
        elif op == ConditionOperator.NOT_CONTAINS:
            return str(condition_value) not in str(metric_value)
        elif op == ConditionOperator.IN_RANGE:
            return condition_value[0] <= metric_value <= condition_value[1]
        elif op == ConditionOperator.NOT_IN_RANGE:
            return not (condition_value[0] <= metric_value <= condition_value[1])
        elif op == ConditionOperator.IS_TOP_PERCENT:
            # Ranking condition - requer all_items_metrics
            if not all_items_metrics:
                return False
            all_values = [m.get(condition.metric, 0) for m in all_items_metrics]
            percentile = 100 - condition_value
            threshold = statistics.quantiles(all_values, n=100)[int(percentile)-1] if all_values else 0
            return metric_value >= threshold
        elif op == ConditionOperator.IS_BOTTOM_PERCENT:
            if not all_items_metrics:
                return False
            all_values = [m.get(condition.metric, 0) for m in all_items_metrics]
            threshold = statistics.quantiles(all_values, n=100)[int(condition_value)-1] if all_values else 0
            return metric_value <= threshold
            
        return False
    
    def evaluate_condition_group(
        self, 
        group: ConditionGroup, 
        metrics: Dict[str, float],
        all_items_metrics: Optional[List[Dict[str, float]]] = None
    ) -> bool:
        """Avalia grupo de condições com AND/OR"""
        
        results = []
        
        for condition in group.conditions:
            if isinstance(condition, ConditionGroup):
                result = self.evaluate_condition_group(condition, metrics, all_items_metrics)
            else:
                result = self.evaluate_condition(condition, metrics, all_items_metrics)
            results.append(result)
            
        if group.operator == LogicalOperator.AND:
            return all(results)
        else:  # OR
            return any(results)
            
    async def execute_action(
        self, 
        action: ActionConfig, 
        item_id: str,
        current_metrics: Dict[str, float],
        api_client: Any
    ) -> Dict:
        """Executa uma ação"""
        
        result = {
            "action": action.action.value,
            "item_id": item_id,
            "timestamp": datetime.now().isoformat(),
            "success": False,
            "details": {}
        }
        
        try:
            if action.action == RuleAction.PAUSE:
                await api_client.update_status(item_id, "paused")
                result["success"] = True
                result["details"]["new_status"] = "paused"
                
            elif action.action == RuleAction.ENABLE:
                await api_client.update_status(item_id, "active")
                result["success"] = True
                result["details"]["new_status"] = "active"
                
            elif action.action == RuleAction.INCREASE_BUDGET:
                current_budget = current_metrics.get("daily_budget", 0)
                if action.percentage:
                    new_budget = current_budget * (1 + action.percentage / 100)
                else:
                    new_budget = current_budget + (action.absolute or 0)
                    
                # Aplica limites
                if action.max_value:
                    new_budget = min(new_budget, action.max_value)
                    
                await api_client.update_budget(item_id, new_budget)
                result["success"] = True
                result["details"]["old_budget"] = current_budget
                result["details"]["new_budget"] = new_budget
                
            elif action.action == RuleAction.DECREASE_BUDGET:
                current_budget = current_metrics.get("daily_budget", 0)
                if action.percentage:
                    new_budget = current_budget * (1 - action.percentage / 100)
                else:
                    new_budget = current_budget - (action.absolute or 0)
                    
                # Aplica limites
                if action.min_value:
                    new_budget = max(new_budget, action.min_value)
                    
                await api_client.update_budget(item_id, new_budget)
                result["success"] = True
                result["details"]["old_budget"] = current_budget
                result["details"]["new_budget"] = new_budget
                
            elif action.action == RuleAction.SET_BUDGET:
                await api_client.update_budget(item_id, action.value)
                result["success"] = True
                result["details"]["new_budget"] = action.value
                
            elif action.action == RuleAction.INCREASE_BID:
                current_bid = current_metrics.get("bid", 0)
                if action.percentage:
                    new_bid = current_bid * (1 + action.percentage / 100)
                else:
                    new_bid = current_bid + (action.absolute or 0)
                    
                if action.max_value:
                    new_bid = min(new_bid, action.max_value)
                    
                await api_client.update_bid(item_id, new_bid)
                result["success"] = True
                result["details"]["old_bid"] = current_bid
                result["details"]["new_bid"] = new_bid
                
            elif action.action == RuleAction.DECREASE_BID:
                current_bid = current_metrics.get("bid", 0)
                if action.percentage:
                    new_bid = current_bid * (1 - action.percentage / 100)
                else:
                    new_bid = current_bid - (action.absolute or 0)
                    
                if action.min_value:
                    new_bid = max(new_bid, action.min_value)
                    
                await api_client.update_bid(item_id, new_bid)
                result["success"] = True
                result["details"]["old_bid"] = current_bid
                result["details"]["new_bid"] = new_bid
                
            elif action.action == RuleAction.DUPLICATE:
                new_id = await api_client.duplicate(item_id)
                result["success"] = True
                result["details"]["new_item_id"] = new_id
                
            elif action.action == RuleAction.SEND_SLACK:
                await self._send_slack_notification(
                    action.slack_channel,
                    item_id,
                    current_metrics
                )
                result["success"] = True
                result["details"]["channel"] = action.slack_channel
                
            elif action.action == RuleAction.SEND_EMAIL:
                await self._send_email_notification(
                    action.email_to,
                    item_id,
                    current_metrics
                )
                result["success"] = True
                result["details"]["email"] = action.email_to
                
            elif action.action == RuleAction.SEND_WEBHOOK:
                await self._send_webhook(
                    action.webhook_url,
                    item_id,
                    current_metrics
                )
                result["success"] = True
                result["details"]["webhook"] = action.webhook_url
                
            elif action.action == RuleAction.ROTATE_CREATIVE:
                await api_client.rotate_creative(item_id)
                result["success"] = True
                
            elif action.action == RuleAction.CREATE_LOOKALIKE:
                new_audience_id = await api_client.create_lookalike(
                    item_id, 
                    action.value  # Percentage
                )
                result["success"] = True
                result["details"]["new_audience_id"] = new_audience_id
                
        except Exception as e:
            result["error"] = str(e)
            
        return result
    
    async def run_rule(
        self,
        rule: AutomationRule,
        items: List[Dict],
        api_client: Any
    ) -> RuleLog:
        """Executa uma regra em lista de items"""
        
        log = RuleLog(
            rule_id=rule.id,
            timestamp=datetime.now(),
            items_checked=len(items),
            items_affected=0,
            actions_taken=[],
            metrics_snapshot={}
        )
        
        # Coleta métricas de todos os items para ranking conditions
        all_metrics = [item.get("metrics", {}) for item in items]
        
        for item in items:
            item_id = item.get("id")
            metrics = item.get("metrics", {})
            
            # Avalia condições
            if self.evaluate_condition_group(rule.conditions, metrics, all_metrics):
                log.items_affected += 1
                
                # Executa ações
                for action in rule.actions:
                    result = await self.execute_action(action, item_id, metrics, api_client)
                    log.actions_taken.append(result)
                    
        # Atualiza rule stats
        rule.last_run = datetime.now()
        rule.run_count += 1
        rule.affected_items_count += log.items_affected
        
        # Salva log
        self.logs.append(log)
        
        return log
    
    async def _send_slack_notification(
        self, 
        channel: str, 
        item_id: str, 
        metrics: Dict
    ) -> None:
        """Envia notificação Slack"""
        # Implementação real usaria Slack API
        print(f"[SLACK] #{channel}: Item {item_id} triggered automation. Metrics: {metrics}")
        
    async def _send_email_notification(
        self, 
        email: str, 
        item_id: str, 
        metrics: Dict
    ) -> None:
        """Envia notificação por email"""
        print(f"[EMAIL] To {email}: Item {item_id} triggered automation. Metrics: {metrics}")
        
    async def _send_webhook(
        self, 
        url: str, 
        item_id: str, 
        metrics: Dict
    ) -> None:
        """Envia webhook"""
        print(f"[WEBHOOK] {url}: Item {item_id}, Metrics: {metrics}")


# =============================================================================
# AUTOMATION TACTICS - TÁTICAS PRÉ-CONFIGURADAS (BASEADO EM MADGICX)
# =============================================================================

class AutomationTactics:
    """
    Táticas de automação pré-configuradas por experts
    Similar ao Madgicx Automation Tactics
    """
    
    @staticmethod
    def stop_losing_ads(
        min_spend: float = 50,
        max_cpa: float = 100,
        min_roas: float = 1.0
    ) -> AutomationRule:
        """
        Para ads que estão perdendo dinheiro
        Condições: Spend > X E (CPA > Y OU ROAS < Z)
        """
        return AutomationRule(
            id=f"stop_losing_{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}",
            name="Stop Losing Ads",
            description="Pausa automaticamente ads com performance ruim",
            platform=Platform.META,
            level="ad",
            conditions=ConditionGroup(
                conditions=[
                    Condition(
                        metric="spend",
                        operator=ConditionOperator.GREATER_THAN,
                        value=min_spend,
                        time_range=TimeRange.LAST_7_DAYS
                    ),
                    ConditionGroup(
                        conditions=[
                            Condition(
                                metric="cpa",
                                operator=ConditionOperator.GREATER_THAN,
                                value=max_cpa,
                                time_range=TimeRange.LAST_7_DAYS
                            ),
                            Condition(
                                metric="roas",
                                operator=ConditionOperator.LESS_THAN,
                                value=min_roas,
                                time_range=TimeRange.LAST_7_DAYS
                            )
                        ],
                        operator=LogicalOperator.OR
                    )
                ],
                operator=LogicalOperator.AND
            ),
            actions=[
                ActionConfig(action=RuleAction.PAUSE),
                ActionConfig(
                    action=RuleAction.SEND_SLACK,
                    slack_channel="ads-alerts"
                )
            ],
            schedule={"frequency": "every_15_minutes"}
        )
    
    @staticmethod
    def scale_winners(
        min_roas: float = 3.0,
        min_conversions: int = 5,
        budget_increase_percent: float = 20,
        max_budget: float = 1000
    ) -> AutomationRule:
        """
        Escala ad sets que estão performando bem
        """
        return AutomationRule(
            id=f"scale_winners_{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}",
            name="Scale Winning Ad Sets",
            description="Aumenta budget de ad sets com alta performance",
            platform=Platform.META,
            level="adset",
            conditions=ConditionGroup(
                conditions=[
                    Condition(
                        metric="roas",
                        operator=ConditionOperator.GREATER_THAN,
                        value=min_roas,
                        time_range=TimeRange.LAST_3_DAYS
                    ),
                    Condition(
                        metric="conversions",
                        operator=ConditionOperator.GREATER_EQUAL,
                        value=min_conversions,
                        time_range=TimeRange.LAST_3_DAYS
                    )
                ],
                operator=LogicalOperator.AND
            ),
            actions=[
                ActionConfig(
                    action=RuleAction.INCREASE_BUDGET,
                    percentage=budget_increase_percent,
                    max_value=max_budget
                ),
                ActionConfig(
                    action=RuleAction.SEND_SLACK,
                    slack_channel="ads-wins"
                )
            ],
            schedule={"frequency": "every_6_hours"}
        )
    
    @staticmethod
    def prevent_overspend(
        daily_budget_limit: float = 500,
        account_spend_limit: float = 5000
    ) -> AutomationRule:
        """
        Previne gastos excessivos
        """
        return AutomationRule(
            id=f"prevent_overspend_{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}",
            name="Prevent Overspend",
            description="Pausa campanhas que excedem limite de gasto",
            platform=Platform.META,
            level="campaign",
            conditions=ConditionGroup(
                conditions=[
                    Condition(
                        metric="spend",
                        operator=ConditionOperator.GREATER_THAN,
                        value=daily_budget_limit,
                        time_range=TimeRange.TODAY
                    )
                ],
                operator=LogicalOperator.AND
            ),
            actions=[
                ActionConfig(action=RuleAction.PAUSE),
                ActionConfig(
                    action=RuleAction.SEND_EMAIL,
                    email_to="ads@company.com"
                )
            ],
            schedule={"frequency": "every_15_minutes"}
        )
    
    @staticmethod
    def creative_fatigue_detection(
        min_frequency: float = 3.0,
        ctr_drop_percent: float = 30
    ) -> AutomationRule:
        """
        Detecta fadiga de criativo
        """
        return AutomationRule(
            id=f"creative_fatigue_{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}",
            name="Creative Fatigue Detection",
            description="Detecta quando criativos estão fatigados",
            platform=Platform.META,
            level="ad",
            conditions=ConditionGroup(
                conditions=[
                    Condition(
                        metric="frequency",
                        operator=ConditionOperator.GREATER_THAN,
                        value=min_frequency,
                        time_range=TimeRange.LAST_7_DAYS
                    ),
                    # CTR atual < CTR da semana passada * (1 - drop%)
                    Condition(
                        metric="ctr",
                        operator=ConditionOperator.LESS_THAN,
                        value=0,  # Será calculado dinamicamente
                        time_range=TimeRange.LAST_3_DAYS,
                        compare_to_metric="ctr",
                        compare_time_range=TimeRange.LAST_14_DAYS
                    )
                ],
                operator=LogicalOperator.AND
            ),
            actions=[
                ActionConfig(action=RuleAction.ROTATE_CREATIVE),
                ActionConfig(
                    action=RuleAction.SEND_SLACK,
                    slack_channel="creative-alerts"
                )
            ],
            schedule={"frequency": "daily"}
        )
    
    @staticmethod
    def dayparting_pause(
        pause_hours: List[int] = [0, 1, 2, 3, 4, 5]  # Midnight to 5 AM
    ) -> AutomationRule:
        """
        Pausa ads em horários de baixa performance
        """
        return AutomationRule(
            id=f"dayparting_{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}",
            name="Dayparting - Night Pause",
            description="Pausa ads durante a noite",
            platform=Platform.META,
            level="adset",
            conditions=ConditionGroup(
                conditions=[
                    Condition(
                        metric="hour_of_day",
                        operator=ConditionOperator.IN_RANGE,
                        value=[min(pause_hours), max(pause_hours)]
                    )
                ],
                operator=LogicalOperator.AND
            ),
            actions=[
                ActionConfig(action=RuleAction.PAUSE)
            ],
            schedule={
                "frequency": "every_hour",
                "hours": pause_hours
            }
        )
    
    @staticmethod
    def top_performer_scaling(
        top_percent: float = 10
    ) -> AutomationRule:
        """
        Escala os top X% performers
        """
        return AutomationRule(
            id=f"top_scaling_{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}",
            name="Top Performer Scaling",
            description=f"Escala os top {top_percent}% ad sets por ROAS",
            platform=Platform.META,
            level="adset",
            conditions=ConditionGroup(
                conditions=[
                    Condition(
                        metric="roas",
                        operator=ConditionOperator.IS_TOP_PERCENT,
                        value=top_percent,
                        time_range=TimeRange.LAST_7_DAYS
                    ),
                    Condition(
                        metric="spend",
                        operator=ConditionOperator.GREATER_THAN,
                        value=50,
                        time_range=TimeRange.LAST_7_DAYS
                    )
                ],
                operator=LogicalOperator.AND
            ),
            actions=[
                ActionConfig(
                    action=RuleAction.INCREASE_BUDGET,
                    percentage=30,
                    max_value=2000
                )
            ],
            schedule={"frequency": "daily"}
        )
    
    @staticmethod
    def bottom_performer_pause(
        bottom_percent: float = 20,
        min_spend: float = 100
    ) -> AutomationRule:
        """
        Pausa os bottom X% performers
        """
        return AutomationRule(
            id=f"bottom_pause_{hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]}",
            name="Bottom Performer Pause",
            description=f"Pausa os bottom {bottom_percent}% ad sets por ROAS",
            platform=Platform.META,
            level="adset",
            conditions=ConditionGroup(
                conditions=[
                    Condition(
                        metric="roas",
                        operator=ConditionOperator.IS_BOTTOM_PERCENT,
                        value=bottom_percent,
                        time_range=TimeRange.LAST_7_DAYS
                    ),
                    Condition(
                        metric="spend",
                        operator=ConditionOperator.GREATER_THAN,
                        value=min_spend,
                        time_range=TimeRange.LAST_7_DAYS
                    )
                ],
                operator=LogicalOperator.AND
            ),
            actions=[
                ActionConfig(action=RuleAction.PAUSE),
                ActionConfig(
                    action=RuleAction.SEND_SLACK,
                    slack_channel="ads-alerts"
                )
            ],
            schedule={"frequency": "daily"}
        )


# =============================================================================
# AI MARKETER - AUDITOR DE CONTA (BASEADO EM MADGICX)
# =============================================================================

class AIMarketer:
    """
    AI Marketer similar ao Madgicx
    Audita conta, identifica problemas e oportunidades
    """
    
    def __init__(self):
        self.audit_weights = {
            "budget_efficiency": 0.15,
            "creative_performance": 0.15,
            "audience_performance": 0.15,
            "bidding_efficiency": 0.10,
            "frequency_health": 0.10,
            "conversion_rate": 0.15,
            "roas_performance": 0.10,
            "learning_phase": 0.10
        }
        
    async def audit_account(
        self,
        campaigns: List[Dict],
        ad_sets: List[Dict],
        ads: List[Dict],
        account_metrics: Dict
    ) -> AccountAudit:
        """
        Executa auditoria completa da conta
        """
        issues = []
        opportunities = []
        quick_wins = []
        
        # 1. Análise de Budget
        budget_analysis = self._analyze_budget_efficiency(campaigns, ad_sets)
        issues.extend(budget_analysis["issues"])
        opportunities.extend(budget_analysis["opportunities"])
        
        # 2. Análise de Criativos
        creative_analysis = self._analyze_creative_performance(ads)
        issues.extend(creative_analysis["issues"])
        opportunities.extend(creative_analysis["opportunities"])
        
        # 3. Análise de Audiences
        audience_analysis = self._analyze_audience_performance(ad_sets)
        issues.extend(audience_analysis["issues"])
        opportunities.extend(audience_analysis["opportunities"])
        
        # 4. Análise de Bidding
        bidding_analysis = self._analyze_bidding_efficiency(ad_sets)
        issues.extend(bidding_analysis["issues"])
        quick_wins.extend(bidding_analysis["quick_wins"])
        
        # 5. Análise de Frequency
        frequency_analysis = self._analyze_frequency_health(ads)
        issues.extend(frequency_analysis["issues"])
        quick_wins.extend(frequency_analysis["quick_wins"])
        
        # 6. Análise de Learning Phase
        learning_analysis = self._analyze_learning_phase(ad_sets)
        issues.extend(learning_analysis["issues"])
        
        # Calcula health score
        health_score = self._calculate_health_score(
            len(issues), len(opportunities), len(quick_wins)
        )
        
        # Estima savings e revenue increase
        estimated_savings = sum(i.get("potential_savings", 0) for i in issues)
        estimated_revenue_increase = sum(o.get("potential_revenue", 0) for o in opportunities)
        
        return AccountAudit(
            timestamp=datetime.now(),
            account_id=account_metrics.get("account_id", ""),
            platform=Platform.META,
            health_score=health_score,
            issues=issues,
            opportunities=opportunities,
            quick_wins=quick_wins,
            estimated_savings=estimated_savings,
            estimated_revenue_increase=estimated_revenue_increase
        )
    
    def _analyze_budget_efficiency(
        self, 
        campaigns: List[Dict], 
        ad_sets: List[Dict]
    ) -> Dict:
        """Analisa eficiência de budget"""
        issues = []
        opportunities = []
        
        for campaign in campaigns:
            metrics = campaign.get("metrics", {})
            
            # Check for campaigns with budget not being spent
            budget = metrics.get("daily_budget", 0)
            spend = metrics.get("spend", 0)
            if budget > 0 and spend < budget * 0.5:
                issues.append({
                    "type": "underspend",
                    "level": "campaign",
                    "id": campaign.get("id"),
                    "name": campaign.get("name"),
                    "message": f"Campanha gastando apenas {spend/budget*100:.1f}% do budget",
                    "recommendation": "Revisar targeting ou aumentar lances",
                    "potential_savings": 0
                })
                
            # Check for high-performing campaigns with low budget
            roas = metrics.get("roas", 0)
            if roas > 3 and budget < 500:
                opportunities.append({
                    "type": "scale_opportunity",
                    "level": "campaign",
                    "id": campaign.get("id"),
                    "name": campaign.get("name"),
                    "message": f"Campanha com ROAS {roas:.2f}x pode ser escalada",
                    "recommendation": f"Aumentar budget para ${budget * 2:.2f}",
                    "potential_revenue": budget * (roas - 1)
                })
                
        return {"issues": issues, "opportunities": opportunities}
    
    def _analyze_creative_performance(self, ads: List[Dict]) -> Dict:
        """Analisa performance de criativos"""
        issues = []
        opportunities = []
        
        for ad in ads:
            metrics = ad.get("metrics", {})
            
            # Creative fatigue check
            frequency = metrics.get("frequency", 0)
            ctr = metrics.get("ctr", 0)
            if frequency > 3 and ctr < 1.0:
                issues.append({
                    "type": "creative_fatigue",
                    "level": "ad",
                    "id": ad.get("id"),
                    "name": ad.get("name"),
                    "message": f"Criativo com frequency {frequency:.1f} e CTR {ctr:.2f}%",
                    "recommendation": "Criar novos criativos ou pausar",
                    "potential_savings": metrics.get("spend", 0) * 0.3
                })
                
            # High CTR but low CVR
            cvr = metrics.get("cvr", 0)
            if ctr > 2.0 and cvr < 1.0:
                opportunities.append({
                    "type": "landing_page_opportunity",
                    "level": "ad",
                    "id": ad.get("id"),
                    "name": ad.get("name"),
                    "message": f"CTR alto ({ctr:.2f}%) mas CVR baixo ({cvr:.2f}%)",
                    "recommendation": "Otimizar landing page para melhor conversão",
                    "potential_revenue": metrics.get("clicks", 0) * 0.02 * metrics.get("aov", 100)
                })
                
        return {"issues": issues, "opportunities": opportunities}
    
    def _analyze_audience_performance(self, ad_sets: List[Dict]) -> Dict:
        """Analisa performance de audiences"""
        issues = []
        opportunities = []
        
        # Agrupa por audience type
        audience_performance = {}
        for ad_set in ad_sets:
            audience_type = ad_set.get("audience_type", "unknown")
            metrics = ad_set.get("metrics", {})
            
            if audience_type not in audience_performance:
                audience_performance[audience_type] = []
            audience_performance[audience_type].append(metrics)
            
        # Analisa cada tipo
        for audience_type, metrics_list in audience_performance.items():
            avg_roas = statistics.mean([m.get("roas", 0) for m in metrics_list]) if metrics_list else 0
            avg_cpa = statistics.mean([m.get("cpa", 0) for m in metrics_list]) if metrics_list else 0
            
            if avg_roas < 1.0:
                issues.append({
                    "type": "audience_underperforming",
                    "level": "audience",
                    "audience_type": audience_type,
                    "message": f"Audience type '{audience_type}' com ROAS médio {avg_roas:.2f}x",
                    "recommendation": "Considerar pausar ou refinar targeting",
                    "potential_savings": sum(m.get("spend", 0) for m in metrics_list) * 0.5
                })
            elif avg_roas > 4.0:
                opportunities.append({
                    "type": "audience_scaling",
                    "level": "audience",
                    "audience_type": audience_type,
                    "message": f"Audience type '{audience_type}' com excelente ROAS {avg_roas:.2f}x",
                    "recommendation": "Criar Lookalikes e escalar budget",
                    "potential_revenue": sum(m.get("revenue", 0) for m in metrics_list) * 0.5
                })
                
        return {"issues": issues, "opportunities": opportunities}
    
    def _analyze_bidding_efficiency(self, ad_sets: List[Dict]) -> Dict:
        """Analisa eficiência de bidding"""
        issues = []
        quick_wins = []
        
        for ad_set in ad_sets:
            metrics = ad_set.get("metrics", {})
            bid_strategy = ad_set.get("bid_strategy", "")
            
            cpa = metrics.get("cpa", 0)
            target_cpa = ad_set.get("target_cpa", 0)
            
            # CPA muito acima do target
            if target_cpa > 0 and cpa > target_cpa * 1.5:
                issues.append({
                    "type": "bid_inefficiency",
                    "level": "adset",
                    "id": ad_set.get("id"),
                    "name": ad_set.get("name"),
                    "message": f"CPA ${cpa:.2f} está 50%+ acima do target ${target_cpa:.2f}",
                    "recommendation": "Reduzir target CPA ou revisar audience"
                })
                
            # CPA muito abaixo - pode escalar
            if target_cpa > 0 and cpa < target_cpa * 0.5:
                quick_wins.append({
                    "type": "bid_optimization",
                    "level": "adset",
                    "id": ad_set.get("id"),
                    "name": ad_set.get("name"),
                    "message": f"CPA ${cpa:.2f} bem abaixo do target ${target_cpa:.2f}",
                    "action": "Aumentar target CPA para ${:.2f} e budget".format(cpa * 1.3),
                    "one_click_action": {
                        "action": "update_bid",
                        "new_value": cpa * 1.3
                    }
                })
                
        return {"issues": issues, "quick_wins": quick_wins}
    
    def _analyze_frequency_health(self, ads: List[Dict]) -> Dict:
        """Analisa saúde de frequency"""
        issues = []
        quick_wins = []
        
        for ad in ads:
            metrics = ad.get("metrics", {})
            frequency = metrics.get("frequency", 0)
            reach = metrics.get("reach", 0)
            
            if frequency > 4:
                issues.append({
                    "type": "high_frequency",
                    "level": "ad",
                    "id": ad.get("id"),
                    "name": ad.get("name"),
                    "message": f"Frequency {frequency:.1f} está muito alta",
                    "recommendation": "Pausar e criar novos criativos",
                    "potential_savings": metrics.get("spend", 0) * 0.2
                })
                
            if frequency > 2.5 and frequency <= 4:
                quick_wins.append({
                    "type": "frequency_warning",
                    "level": "ad",
                    "id": ad.get("id"),
                    "name": ad.get("name"),
                    "message": f"Frequency {frequency:.1f} se aproximando do limite",
                    "action": "Preparar novos criativos",
                    "one_click_action": {
                        "action": "set_frequency_cap",
                        "new_value": 3
                    }
                })
                
        return {"issues": issues, "quick_wins": quick_wins}
    
    def _analyze_learning_phase(self, ad_sets: List[Dict]) -> Dict:
        """Analisa ad sets em learning phase"""
        issues = []
        
        for ad_set in ad_sets:
            status = ad_set.get("effective_status", "")
            learning_stage = ad_set.get("learning_stage", "")
            conversions = ad_set.get("metrics", {}).get("conversions", 0)
            
            if learning_stage == "LEARNING_LIMITED":
                issues.append({
                    "type": "learning_limited",
                    "level": "adset",
                    "id": ad_set.get("id"),
                    "name": ad_set.get("name"),
                    "message": f"Ad set em Learning Limited com {conversions} conversões",
                    "recommendation": "Aumentar budget ou expandir targeting"
                })
            elif learning_stage == "LEARNING":
                # Não é issue, mas tracking
                pass
                
        return {"issues": issues}
    
    def _calculate_health_score(
        self, 
        issues_count: int, 
        opportunities_count: int,
        quick_wins_count: int
    ) -> float:
        """Calcula health score da conta (0-100)"""
        base_score = 100
        
        # Penalidades por issues
        base_score -= issues_count * 5
        
        # Bônus por opportunities aproveitáveis
        base_score += opportunities_count * 2
        
        # Bônus por quick wins
        base_score += quick_wins_count * 1
        
        return max(0, min(100, base_score))
    
    def generate_recommendations(self, audit: AccountAudit) -> List[Dict]:
        """Gera lista de recomendações priorizadas"""
        recommendations = []
        
        # Quick wins primeiro (one-click actions)
        for qw in audit.quick_wins:
            recommendations.append({
                "priority": "HIGH",
                "type": "quick_win",
                "title": qw.get("message"),
                "action": qw.get("action"),
                "one_click": qw.get("one_click_action"),
                "impact": "immediate"
            })
            
        # Issues críticos
        for issue in audit.issues:
            if issue.get("potential_savings", 0) > 100:
                recommendations.append({
                    "priority": "HIGH",
                    "type": "issue",
                    "title": issue.get("message"),
                    "recommendation": issue.get("recommendation"),
                    "potential_savings": issue.get("potential_savings"),
                    "impact": "cost_reduction"
                })
                
        # Opportunities
        for opp in audit.opportunities:
            recommendations.append({
                "priority": "MEDIUM",
                "type": "opportunity",
                "title": opp.get("message"),
                "recommendation": opp.get("recommendation"),
                "potential_revenue": opp.get("potential_revenue"),
                "impact": "revenue_increase"
            })
            
        return recommendations


# =============================================================================
# CREATIVE INSIGHTS - ANÁLISE DE CRIATIVOS COM AI (BASEADO EM MADGICX)
# =============================================================================

class CreativeInsightsEngine:
    """
    Análise de criativos com AI similar ao Madgicx Creative Insights
    """
    
    def __init__(self):
        # Elementos detectáveis em imagens/videos
        self.detectable_elements = [
            "person", "face", "product", "text", "logo", "cta_button",
            "background_color", "dominant_color", "lifestyle", "product_shot",
            "ugc_style", "professional", "before_after", "testimonial",
            "discount", "urgency", "social_proof", "emotion"
        ]
        
        # Benchmarks por tipo de criativo
        self.benchmarks = {
            CreativeType.IMAGE: {"ctr": 1.5, "cvr": 2.0, "frequency_limit": 4},
            CreativeType.VIDEO: {"ctr": 2.0, "cvr": 2.5, "frequency_limit": 3},
            CreativeType.CAROUSEL: {"ctr": 1.8, "cvr": 2.2, "frequency_limit": 4},
            CreativeType.COLLECTION: {"ctr": 2.5, "cvr": 3.0, "frequency_limit": 5}
        }
        
    async def analyze_creative(
        self,
        creative_id: str,
        creative_type: CreativeType,
        metrics: Dict[str, float],
        creative_data: Dict
    ) -> CreativeInsight:
        """Analisa um criativo e gera insights"""
        
        # Detecta elementos (simulado - em produção usaria Vision AI)
        elements = self._detect_elements(creative_data)
        
        # Calcula performance score
        performance_score = self._calculate_performance_score(
            creative_type, metrics
        )
        
        # Calcula fatigue score
        fatigue_score = self._calculate_fatigue_score(metrics)
        
        # Gera recomendações
        recommendations = self._generate_creative_recommendations(
            creative_type, elements, metrics, performance_score, fatigue_score
        )
        
        return CreativeInsight(
            creative_id=creative_id,
            creative_type=creative_type,
            elements=elements,
            performance_score=performance_score,
            fatigue_score=fatigue_score,
            recommendations=recommendations
        )
    
    def _detect_elements(self, creative_data: Dict) -> Dict[str, Any]:
        """Detecta elementos no criativo (simulado)"""
        # Em produção, usaria Google Vision AI, AWS Rekognition, etc
        
        elements = {
            "has_person": creative_data.get("has_person", False),
            "has_face": creative_data.get("has_face", False),
            "has_product": creative_data.get("has_product", True),
            "has_text_overlay": creative_data.get("has_text_overlay", True),
            "has_logo": creative_data.get("has_logo", True),
            "has_cta_button": creative_data.get("has_cta_button", True),
            "dominant_color": creative_data.get("dominant_color", "#ffffff"),
            "style": creative_data.get("style", "professional"),
            "text_amount": creative_data.get("text_amount", "medium"),
            "emotion_detected": creative_data.get("emotion", "neutral"),
            "has_discount_badge": creative_data.get("has_discount", False),
            "has_urgency_element": creative_data.get("has_urgency", False),
            "has_social_proof": creative_data.get("has_social_proof", False),
            "video_length_seconds": creative_data.get("video_length", 0),
            "first_frame_quality": creative_data.get("first_frame_quality", 0.8)
        }
        
        return elements
    
    def _calculate_performance_score(
        self,
        creative_type: CreativeType,
        metrics: Dict[str, float]
    ) -> float:
        """Calcula score de performance (0-100)"""
        
        benchmarks = self.benchmarks.get(creative_type, self.benchmarks[CreativeType.IMAGE])
        
        ctr = metrics.get("ctr", 0)
        cvr = metrics.get("cvr", 0)
        roas = metrics.get("roas", 0)
        
        # Score baseado em comparação com benchmarks
        ctr_score = min(100, (ctr / benchmarks["ctr"]) * 50)
        cvr_score = min(100, (cvr / benchmarks["cvr"]) * 50)
        roas_score = min(100, roas * 20)  # ROAS 5x = 100
        
        # Peso: CTR 30%, CVR 40%, ROAS 30%
        performance_score = (ctr_score * 0.3) + (cvr_score * 0.4) + (roas_score * 0.3)
        
        return round(performance_score, 1)
    
    def _calculate_fatigue_score(self, metrics: Dict[str, float]) -> float:
        """Calcula score de fadiga (0-100, maior = mais fatigado)"""
        
        frequency = metrics.get("frequency", 0)
        days_running = metrics.get("days_running", 0)
        ctr_trend = metrics.get("ctr_trend", 0)  # Negativo = caindo
        
        # Fatigue baseado em frequency
        frequency_fatigue = min(100, frequency * 20)  # Freq 5 = 100
        
        # Fatigue baseado em tempo
        time_fatigue = min(50, days_running * 1.5)  # 30 dias = 45
        
        # Fatigue baseado em trend
        trend_fatigue = max(0, -ctr_trend * 10)  # -10% trend = 100
        
        fatigue_score = (frequency_fatigue * 0.5) + (time_fatigue * 0.25) + (trend_fatigue * 0.25)
        
        return round(fatigue_score, 1)
    
    def _generate_creative_recommendations(
        self,
        creative_type: CreativeType,
        elements: Dict,
        metrics: Dict,
        performance_score: float,
        fatigue_score: float
    ) -> List[str]:
        """Gera recomendações para o criativo"""
        
        recommendations = []
        
        # Recomendações baseadas em fatigue
        if fatigue_score > 70:
            recommendations.append("🔴 Criativo altamente fatigado - criar novas variações URGENTE")
        elif fatigue_score > 50:
            recommendations.append("🟡 Criativo começando a fatigar - preparar substituições")
            
        # Recomendações baseadas em elementos
        if not elements.get("has_person"):
            recommendations.append("📸 Considere adicionar pessoas - aumenta CTR em média 38%")
            
        if not elements.get("has_cta_button"):
            recommendations.append("🔘 Adicione CTA button visual - aumenta conversões em 28%")
            
        if not elements.get("has_urgency_element"):
            recommendations.append("⏰ Adicione elemento de urgência - pode aumentar CVR em 15%")
            
        if not elements.get("has_social_proof"):
            recommendations.append("⭐ Adicione social proof (reviews, badges) - aumenta trust")
            
        if elements.get("text_amount") == "high":
            recommendations.append("📝 Reduza texto - Meta penaliza imagens com muito texto")
            
        # Recomendações específicas por tipo
        if creative_type == CreativeType.VIDEO:
            video_length = elements.get("video_length_seconds", 0)
            if video_length > 60:
                recommendations.append("🎬 Vídeo muito longo - versões de 15-30s performam melhor")
            if elements.get("first_frame_quality", 0) < 0.7:
                recommendations.append("🖼️ Melhore primeiro frame - crucial para hook inicial")
                
        # Recomendações baseadas em performance
        if performance_score < 30:
            recommendations.append("❌ Performance muito baixa - considere pausar e testar novo conceito")
        elif performance_score > 80:
            recommendations.append("✅ Excelente performance - criar variações para escalar")
            
        # Comparação com benchmarks
        ctr = metrics.get("ctr", 0)
        if ctr < 1.0:
            recommendations.append("📉 CTR abaixo de 1% - revisar headline e imagem")
            
        cvr = metrics.get("cvr", 0)
        if cvr < 1.5:
            recommendations.append("🛒 CVR abaixo da média - verificar congruência com landing page")
            
        return recommendations
    
    async def analyze_creative_portfolio(
        self,
        creatives: List[Dict]
    ) -> Dict:
        """Analisa portfolio completo de criativos"""
        
        results = {
            "total_creatives": len(creatives),
            "by_type": {},
            "top_performers": [],
            "needs_refresh": [],
            "recommendations": [],
            "elements_analysis": {}
        }
        
        insights = []
        for creative in creatives:
            insight = await self.analyze_creative(
                creative.get("id"),
                CreativeType(creative.get("type", "image")),
                creative.get("metrics", {}),
                creative.get("data", {})
            )
            insights.append(insight)
            
        # Agrupa por tipo
        for creative_type in CreativeType:
            type_insights = [i for i in insights if i.creative_type == creative_type]
            if type_insights:
                results["by_type"][creative_type.value] = {
                    "count": len(type_insights),
                    "avg_performance": statistics.mean([i.performance_score for i in type_insights]),
                    "avg_fatigue": statistics.mean([i.fatigue_score for i in type_insights])
                }
                
        # Top performers
        sorted_by_performance = sorted(insights, key=lambda x: x.performance_score, reverse=True)
        results["top_performers"] = [
            {"id": i.creative_id, "score": i.performance_score}
            for i in sorted_by_performance[:5]
        ]
        
        # Needs refresh
        fatigued = [i for i in insights if i.fatigue_score > 60]
        results["needs_refresh"] = [
            {"id": i.creative_id, "fatigue": i.fatigue_score}
            for i in fatigued
        ]
        
        # Portfolio-level recommendations
        if len(fatigued) > len(creatives) * 0.3:
            results["recommendations"].append("⚠️ 30%+ dos criativos fatigados - urgente criar novos")
            
        # Análise de elementos mais comuns
        element_counts = {}
        for insight in insights:
            for element, value in insight.elements.items():
                if isinstance(value, bool) and value:
                    element_counts[element] = element_counts.get(element, 0) + 1
                    
        results["elements_analysis"] = element_counts
        
        return results


# =============================================================================
# AD COPY INSIGHTS - ANÁLISE DE COPY (BASEADO EM MADGICX)
# =============================================================================

class AdCopyInsightsEngine:
    """
    Análise de copy de ads similar ao Madgicx Ad Copy Insights
    """
    
    def __init__(self):
        # Power words que aumentam conversão
        self.power_words = {
            "urgency": ["agora", "hoje", "última", "limitado", "acaba", "restam", "urgente", "imediato"],
            "exclusivity": ["exclusivo", "vip", "premium", "selecionado", "especial", "único"],
            "value": ["grátis", "desconto", "economia", "oferta", "promoção", "barato", "preço"],
            "trust": ["garantia", "comprovado", "aprovado", "certificado", "seguro", "confiável"],
            "emotion": ["incrível", "surpreendente", "maravilhoso", "fantástico", "perfeito", "melhor"],
            "action": ["descubra", "aproveite", "garanta", "conquiste", "transforme", "experimente"]
        }
        
        # CTAs efetivos
        self.effective_ctas = [
            "compre agora", "saiba mais", "aproveite", "garanta o seu",
            "clique aqui", "não perca", "comece agora", "experimente grátis",
            "reserve já", "faça seu pedido", "cadastre-se", "baixe grátis"
        ]
        
    async def analyze_copy(
        self,
        ad_id: str,
        headline: str,
        description: str,
        cta: str,
        metrics: Dict[str, float]
    ) -> AdCopyInsight:
        """Analisa copy de um ad"""
        
        full_text = f"{headline} {description}".lower()
        
        # Análise de sentiment
        sentiment_score = self._analyze_sentiment(full_text)
        
        # Análise de urgência
        urgency_score = self._analyze_urgency(full_text)
        
        # Análise de clareza
        clarity_score = self._analyze_clarity(headline, description)
        
        # Detecta triggers emocionais
        emotional_triggers = self._detect_emotional_triggers(full_text)
        
        # Detecta power words
        power_words_found = self._detect_power_words(full_text)
        
        # Gera recomendações
        recommendations = self._generate_copy_recommendations(
            headline, description, cta, metrics,
            sentiment_score, urgency_score, clarity_score,
            emotional_triggers, power_words_found
        )
        
        return AdCopyInsight(
            ad_id=ad_id,
            headline=headline,
            description=description,
            cta=cta,
            sentiment_score=sentiment_score,
            urgency_score=urgency_score,
            clarity_score=clarity_score,
            emotional_triggers=emotional_triggers,
            power_words=power_words_found,
            recommendations=recommendations
        )
    
    def _analyze_sentiment(self, text: str) -> float:
        """Analisa sentiment do texto (0-1, 1 = positivo)"""
        
        positive_words = ["bom", "ótimo", "melhor", "incrível", "perfeito", "excelente", 
                         "maravilhoso", "fantástico", "sucesso", "feliz", "amor"]
        negative_words = ["ruim", "péssimo", "pior", "horrível", "problema", "difícil",
                         "nunca", "não", "sem", "falta"]
        
        positive_count = sum(1 for word in positive_words if word in text)
        negative_count = sum(1 for word in negative_words if word in text)
        
        total = positive_count + negative_count
        if total == 0:
            return 0.5
            
        return positive_count / total
    
    def _analyze_urgency(self, text: str) -> float:
        """Analisa nível de urgência (0-1)"""
        
        urgency_triggers = self.power_words["urgency"]
        found = sum(1 for word in urgency_triggers if word in text)
        
        return min(1.0, found * 0.3)
    
    def _analyze_clarity(self, headline: str, description: str) -> float:
        """Analisa clareza do copy (0-1)"""
        
        score = 1.0
        
        # Penaliza headlines muito longas
        if len(headline) > 40:
            score -= 0.2
            
        # Penaliza descrições muito longas
        if len(description) > 150:
            score -= 0.2
            
        # Penaliza muitas palavras difíceis
        words = description.split()
        long_words = [w for w in words if len(w) > 10]
        if len(long_words) > len(words) * 0.2:
            score -= 0.1
            
        # Beneficia uso de números
        if any(c.isdigit() for c in headline + description):
            score += 0.1
            
        return max(0, min(1, score))
    
    def _detect_emotional_triggers(self, text: str) -> List[str]:
        """Detecta triggers emocionais"""
        
        triggers = []
        
        trigger_patterns = {
            "FOMO": ["última chance", "não perca", "acaba hoje", "restam poucos"],
            "Curiosidade": ["descubra", "segredo", "revelado", "você sabia"],
            "Aspiração": ["sonho", "conquiste", "transforme", "seja"],
            "Medo": ["evite", "cuidado", "perigo", "não cometa"],
            "Pertencimento": ["junte-se", "faça parte", "milhares de pessoas"]
        }
        
        for trigger, patterns in trigger_patterns.items():
            if any(p in text for p in patterns):
                triggers.append(trigger)
                
        return triggers
    
    def _detect_power_words(self, text: str) -> List[str]:
        """Detecta power words no texto"""
        
        found = []
        for category, words in self.power_words.items():
            for word in words:
                if word in text:
                    found.append(f"{category}: {word}")
                    
        return found
    
    def _generate_copy_recommendations(
        self,
        headline: str,
        description: str,
        cta: str,
        metrics: Dict,
        sentiment: float,
        urgency: float,
        clarity: float,
        triggers: List[str],
        power_words: List[str]
    ) -> List[str]:
        """Gera recomendações de copy"""
        
        recommendations = []
        
        # Headline
        if len(headline) < 20:
            recommendations.append("📝 Headline muito curta - adicione benefício principal")
        if len(headline) > 45:
            recommendations.append("📝 Headline muito longa - reduza para melhor legibilidade")
        if not any(c.isdigit() for c in headline):
            recommendations.append("🔢 Adicione números ao headline - aumenta CTR em 36%")
            
        # Urgency
        if urgency < 0.3:
            recommendations.append("⏰ Adicione elemento de urgência (ex: 'Oferta por tempo limitado')")
            
        # Clarity
        if clarity < 0.6:
            recommendations.append("✍️ Simplifique o copy - use frases mais curtas e diretas")
            
        # Emotional triggers
        if not triggers:
            recommendations.append("💭 Adicione trigger emocional (FOMO, curiosidade, aspiração)")
            
        # Power words
        if len(power_words) < 2:
            recommendations.append("💪 Use mais power words (grátis, exclusivo, garantia, etc)")
            
        # CTA
        cta_lower = cta.lower()
        if not any(c in cta_lower for c in self.effective_ctas):
            recommendations.append("🔘 Use CTA mais direto (ex: 'Compre Agora', 'Aproveite')")
            
        # Performance-based
        ctr = metrics.get("ctr", 0)
        cvr = metrics.get("cvr", 0)
        
        if ctr < 1.0:
            recommendations.append("📉 CTR baixo - teste headlines mais provocativos")
        if cvr < 1.5:
            recommendations.append("🛒 CVR baixo - alinhe copy com oferta da landing page")
            
        # Sentiment
        if sentiment < 0.3:
            recommendations.append("😊 Tom muito negativo - use linguagem mais positiva")
            
        return recommendations
    
    async def get_top_performing_copy_elements(
        self,
        ads: List[Dict]
    ) -> Dict:
        """Analisa quais elementos de copy performam melhor"""
        
        analysis = {
            "top_headlines": [],
            "top_ctas": [],
            "winning_patterns": [],
            "recommendations": []
        }
        
        # Agrupa por CTR e CVR
        sorted_by_ctr = sorted(ads, key=lambda x: x.get("metrics", {}).get("ctr", 0), reverse=True)
        sorted_by_cvr = sorted(ads, key=lambda x: x.get("metrics", {}).get("cvr", 0), reverse=True)
        
        # Top headlines por CTR
        analysis["top_headlines"] = [
            {
                "headline": ad.get("headline"),
                "ctr": ad.get("metrics", {}).get("ctr", 0)
            }
            for ad in sorted_by_ctr[:5]
        ]
        
        # Analisa padrões vencedores
        for ad in sorted_by_ctr[:10]:
            headline = ad.get("headline", "").lower()
            
            # Detecta padrões
            if any(c.isdigit() for c in headline):
                if "números" not in [p["pattern"] for p in analysis["winning_patterns"]]:
                    analysis["winning_patterns"].append({
                        "pattern": "números",
                        "example": headline,
                        "avg_ctr_lift": "+36%"
                    })
                    
            if "?" in headline:
                if "pergunta" not in [p["pattern"] for p in analysis["winning_patterns"]]:
                    analysis["winning_patterns"].append({
                        "pattern": "pergunta",
                        "example": headline,
                        "avg_ctr_lift": "+28%"
                    })
                    
        return analysis


# =============================================================================
# AUDIENCE LAUNCHER - LANÇAMENTO MASSIVO DE AUDIENCES (BASEADO EM MADGICX)
# =============================================================================

class AudienceLauncher:
    """
    Lançamento massivo de audiences similar ao Madgicx Audience Launcher
    """
    
    def __init__(self):
        # Templates de audience por funnel stage
        self.audience_templates = {
            "TOFU": [  # Top of Funnel
                {"name": "Interests - Broad", "type": "interest", "size": "large"},
                {"name": "Lookalike 5-10%", "type": "lookalike", "percentage": [5, 10]},
                {"name": "Behavior - In-Market", "type": "behavior", "behaviors": ["in_market_buyers"]},
            ],
            "MOFU": [  # Middle of Funnel
                {"name": "Website Visitors 30d", "type": "custom", "source": "website", "days": 30},
                {"name": "Lookalike 1-5%", "type": "lookalike", "percentage": [1, 5]},
                {"name": "Video Viewers 50%+", "type": "engagement", "video_percentage": 50},
                {"name": "Page Engagers", "type": "engagement", "source": "page"}
            ],
            "BOFU": [  # Bottom of Funnel
                {"name": "Add to Cart 7d", "type": "custom", "event": "AddToCart", "days": 7},
                {"name": "Checkout Started 3d", "type": "custom", "event": "InitiateCheckout", "days": 3},
                {"name": "Lookalike 0-1%", "type": "lookalike", "percentage": [0, 1]},
                {"name": "Past Purchasers", "type": "custom", "event": "Purchase", "days": 180}
            ],
            "RETENTION": [
                {"name": "Repeat Customers", "type": "custom", "event": "Purchase", "min_count": 2},
                {"name": "High LTV", "type": "value_based", "ltv_percentile": 20},
                {"name": "At-Risk Churners", "type": "custom", "event": "Purchase", "days_since_min": 60}
            ]
        }
        
    async def generate_audience_strategy(
        self,
        seed_audiences: List[Dict],
        monthly_budget: float,
        objective: CampaignObjective
    ) -> Dict:
        """Gera estratégia completa de audiences"""
        
        strategy = {
            "recommended_audiences": [],
            "budget_allocation": {},
            "testing_plan": [],
            "expected_reach": 0
        }
        
        # Determina mix de funnel baseado no objetivo
        if objective in [CampaignObjective.AWARENESS, CampaignObjective.REACH]:
            funnel_mix = {"TOFU": 0.7, "MOFU": 0.2, "BOFU": 0.1}
        elif objective in [CampaignObjective.TRAFFIC, CampaignObjective.ENGAGEMENT]:
            funnel_mix = {"TOFU": 0.4, "MOFU": 0.4, "BOFU": 0.2}
        elif objective in [CampaignObjective.CONVERSIONS, CampaignObjective.SALES]:
            funnel_mix = {"TOFU": 0.2, "MOFU": 0.3, "BOFU": 0.5}
        else:
            funnel_mix = {"TOFU": 0.33, "MOFU": 0.34, "BOFU": 0.33}
            
        # Gera audiences por stage
        for stage, percentage in funnel_mix.items():
            stage_budget = monthly_budget * percentage
            templates = self.audience_templates.get(stage, [])
            
            for template in templates:
                audience_config = {
                    "stage": stage,
                    "name": template["name"],
                    "type": template["type"],
                    "config": template,
                    "recommended_budget": stage_budget / len(templates)
                }
                strategy["recommended_audiences"].append(audience_config)
                
        # Allocation
        strategy["budget_allocation"] = {
            stage: monthly_budget * pct
            for stage, pct in funnel_mix.items()
        }
        
        # Testing plan
        strategy["testing_plan"] = [
            {
                "week": 1,
                "action": "Launch all TOFU audiences with equal budget",
                "budget": strategy["budget_allocation"]["TOFU"] / 4
            },
            {
                "week": 2,
                "action": "Add MOFU audiences, pause worst TOFU performers",
                "budget": strategy["budget_allocation"]["MOFU"] / 4
            },
            {
                "week": 3,
                "action": "Add BOFU audiences, scale winning MOFU",
                "budget": strategy["budget_allocation"]["BOFU"] / 4
            },
            {
                "week": 4,
                "action": "Full optimization - scale winners, pause losers",
                "budget": monthly_budget / 4
            }
        ]
        
        return strategy
    
    async def bulk_create_audiences(
        self,
        api_client: Any,
        strategy: Dict
    ) -> List[Dict]:
        """Cria audiences em massa baseado na estratégia"""
        
        created_audiences = []
        
        for audience_config in strategy["recommended_audiences"]:
            try:
                # Cria audience via API (simulado)
                audience_id = await api_client.create_audience(audience_config)
                
                created_audiences.append({
                    "id": audience_id,
                    "name": audience_config["name"],
                    "stage": audience_config["stage"],
                    "status": "created"
                })
                
            except Exception as e:
                created_audiences.append({
                    "name": audience_config["name"],
                    "stage": audience_config["stage"],
                    "status": "error",
                    "error": str(e)
                })
                
        return created_audiences
    
    def get_cross_campaign_audience_performance(
        self,
        ad_sets: List[Dict]
    ) -> List[AudiencePerformance]:
        """Analisa performance de audiences cross-campaign"""
        
        # Agrupa métricas por audience
        audience_metrics = {}
        
        for ad_set in ad_sets:
            audience_id = ad_set.get("audience_id")
            audience_name = ad_set.get("audience_name")
            audience_type = ad_set.get("audience_type", "custom")
            metrics = ad_set.get("metrics", {})
            
            if audience_id not in audience_metrics:
                audience_metrics[audience_id] = {
                    "name": audience_name,
                    "type": audience_type,
                    "campaigns": 0,
                    "spend": 0,
                    "revenue": 0,
                    "impressions": 0,
                    "clicks": 0,
                    "conversions": 0,
                    "reach": 0
                }
                
            am = audience_metrics[audience_id]
            am["campaigns"] += 1
            am["spend"] += metrics.get("spend", 0)
            am["revenue"] += metrics.get("revenue", 0)
            am["impressions"] += metrics.get("impressions", 0)
            am["clicks"] += metrics.get("clicks", 0)
            am["conversions"] += metrics.get("conversions", 0)
            am["reach"] += metrics.get("reach", 0)
            
        # Calcula métricas derivadas
        performances = []
        for audience_id, am in audience_metrics.items():
            roas = am["revenue"] / am["spend"] if am["spend"] > 0 else 0
            cpa = am["spend"] / am["conversions"] if am["conversions"] > 0 else 0
            cvr = (am["conversions"] / am["clicks"] * 100) if am["clicks"] > 0 else 0
            ctr = (am["clicks"] / am["impressions"] * 100) if am["impressions"] > 0 else 0
            frequency = am["impressions"] / am["reach"] if am["reach"] > 0 else 0
            
            performances.append(AudiencePerformance(
                audience_id=audience_id,
                audience_name=am["name"],
                audience_type=AudienceType(am["type"]) if am["type"] in [t.value for t in AudienceType] else AudienceType.CUSTOM,
                campaigns_count=am["campaigns"],
                total_spend=am["spend"],
                total_revenue=am["revenue"],
                roas=roas,
                cpa=cpa,
                cvr=cvr,
                ctr=ctr,
                reach=am["reach"],
                frequency=frequency
            ))
            
        # Ordena por ROAS
        performances.sort(key=lambda x: x.roas, reverse=True)
        
        return performances


# =============================================================================
# BULK CREATION - CRIAÇÃO EM MASSA (BASEADO EM BÏRCH)
# =============================================================================

class BulkCreator:
    """
    Criação em massa de ads similar ao Bïrch Bulk Creation
    """
    
    async def create_ad_variations(
        self,
        api_client: Any,
        campaign_id: str,
        ad_set_id: str,
        headlines: List[str],
        descriptions: List[str],
        images: List[str],
        ctas: List[str],
        max_combinations: int = 100
    ) -> List[Dict]:
        """
        Cria todas as combinações possíveis de ads
        Headline x Description x Image x CTA
        """
        
        created_ads = []
        combination_count = 0
        
        for headline in headlines:
            for description in descriptions:
                for image in images:
                    for cta in ctas:
                        if combination_count >= max_combinations:
                            break
                            
                        ad_config = {
                            "campaign_id": campaign_id,
                            "ad_set_id": ad_set_id,
                            "headline": headline,
                            "description": description,
                            "image": image,
                            "cta": cta,
                            "name": f"Ad_{combination_count+1}_{headline[:20]}"
                        }
                        
                        try:
                            ad_id = await api_client.create_ad(ad_config)
                            created_ads.append({
                                "id": ad_id,
                                "config": ad_config,
                                "status": "created"
                            })
                        except Exception as e:
                            created_ads.append({
                                "config": ad_config,
                                "status": "error",
                                "error": str(e)
                            })
                            
                        combination_count += 1
                        
        return created_ads
    
    async def duplicate_winning_ads(
        self,
        api_client: Any,
        source_ads: List[Dict],
        target_ad_sets: List[str],
        copy_creative: bool = True,
        copy_targeting: bool = False
    ) -> List[Dict]:
        """Duplica ads vencedores para outros ad sets"""
        
        duplicated = []
        
        for ad in source_ads:
            for target_ad_set in target_ad_sets:
                try:
                    new_ad_id = await api_client.duplicate_ad(
                        ad["id"],
                        target_ad_set,
                        copy_creative=copy_creative
                    )
                    duplicated.append({
                        "source_ad": ad["id"],
                        "target_ad_set": target_ad_set,
                        "new_ad_id": new_ad_id,
                        "status": "success"
                    })
                except Exception as e:
                    duplicated.append({
                        "source_ad": ad["id"],
                        "target_ad_set": target_ad_set,
                        "status": "error",
                        "error": str(e)
                    })
                    
        return duplicated
    
    async def split_test_setup(
        self,
        api_client: Any,
        campaign_id: str,
        test_variable: str,  # "audience", "creative", "placement", "optimization"
        variations: List[Dict],
        budget_per_variation: float
    ) -> Dict:
        """Configura split test com múltiplas variações"""
        
        test_config = {
            "campaign_id": campaign_id,
            "test_variable": test_variable,
            "variations": [],
            "total_budget": budget_per_variation * len(variations),
            "created_at": datetime.now().isoformat()
        }
        
        for i, variation in enumerate(variations):
            ad_set_config = {
                "name": f"Split Test - {test_variable} - Var {i+1}",
                "daily_budget": budget_per_variation,
                **variation
            }
            
            try:
                ad_set_id = await api_client.create_ad_set(campaign_id, ad_set_config)
                test_config["variations"].append({
                    "variation_number": i + 1,
                    "ad_set_id": ad_set_id,
                    "config": variation,
                    "status": "created"
                })
            except Exception as e:
                test_config["variations"].append({
                    "variation_number": i + 1,
                    "config": variation,
                    "status": "error",
                    "error": str(e)
                })
                
        return test_config


# =============================================================================
# POST BOOSTING - BOOST AUTOMÁTICO DE POSTS (BASEADO EM BÏRCH)
# =============================================================================

class PostBooster:
    """
    Boost automático de posts orgânicos similar ao Bïrch Post Boosting
    """
    
    def __init__(self):
        self.boost_rules: List[Dict] = []
        
    def add_boost_rule(
        self,
        min_organic_reach: int = 0,
        min_engagement_rate: float = 0,
        min_likes: int = 0,
        min_comments: int = 0,
        min_shares: int = 0,
        keyword_contains: Optional[List[str]] = None,
        keyword_excludes: Optional[List[str]] = None,
        boost_budget: float = 50,
        boost_duration_days: int = 3,
        target_audience_id: Optional[str] = None
    ) -> str:
        """Adiciona regra de boost automático"""
        
        rule_id = hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]
        
        self.boost_rules.append({
            "id": rule_id,
            "conditions": {
                "min_organic_reach": min_organic_reach,
                "min_engagement_rate": min_engagement_rate,
                "min_likes": min_likes,
                "min_comments": min_comments,
                "min_shares": min_shares,
                "keyword_contains": keyword_contains or [],
                "keyword_excludes": keyword_excludes or []
            },
            "boost_config": {
                "budget": boost_budget,
                "duration_days": boost_duration_days,
                "target_audience_id": target_audience_id
            },
            "created_at": datetime.now().isoformat()
        })
        
        return rule_id
    
    async def evaluate_posts(
        self,
        posts: List[Dict],
        api_client: Any
    ) -> List[Dict]:
        """Avalia posts e aplica boost rules"""
        
        boosted_posts = []
        
        for post in posts:
            post_id = post.get("id")
            post_text = post.get("text", "").lower()
            metrics = post.get("metrics", {})
            
            for rule in self.boost_rules:
                conditions = rule["conditions"]
                
                # Verifica condições
                meets_conditions = True
                
                if metrics.get("reach", 0) < conditions["min_organic_reach"]:
                    meets_conditions = False
                if metrics.get("engagement_rate", 0) < conditions["min_engagement_rate"]:
                    meets_conditions = False
                if metrics.get("likes", 0) < conditions["min_likes"]:
                    meets_conditions = False
                if metrics.get("comments", 0) < conditions["min_comments"]:
                    meets_conditions = False
                if metrics.get("shares", 0) < conditions["min_shares"]:
                    meets_conditions = False
                    
                # Keywords
                if conditions["keyword_contains"]:
                    if not any(kw in post_text for kw in conditions["keyword_contains"]):
                        meets_conditions = False
                if conditions["keyword_excludes"]:
                    if any(kw in post_text for kw in conditions["keyword_excludes"]):
                        meets_conditions = False
                        
                if meets_conditions:
                    # Aplica boost
                    try:
                        boost_result = await api_client.boost_post(
                            post_id,
                            rule["boost_config"]
                        )
                        boosted_posts.append({
                            "post_id": post_id,
                            "rule_id": rule["id"],
                            "boost_config": rule["boost_config"],
                            "status": "boosted",
                            "ad_id": boost_result.get("ad_id")
                        })
                    except Exception as e:
                        boosted_posts.append({
                            "post_id": post_id,
                            "rule_id": rule["id"],
                            "status": "error",
                            "error": str(e)
                        })
                    break  # Um post só é boosted por uma regra
                    
        return boosted_posts


# =============================================================================
# CROSS-CHANNEL REPORTING - RELATÓRIOS CROSS-PLATFORM (BASEADO EM MADGICX)
# =============================================================================

class CrossChannelReporting:
    """
    Relatórios cross-platform similar ao Madgicx Reporting
    """
    
    def __init__(self):
        self.connected_platforms: List[Platform] = []
        self.data_sources: Dict[str, Any] = {}
        
    def connect_platform(self, platform: Platform, credentials: Dict) -> bool:
        """Conecta uma plataforma"""
        self.connected_platforms.append(platform)
        self.data_sources[platform.value] = credentials
        return True
    
    async def get_unified_dashboard(
        self,
        date_range: Tuple[datetime, datetime],
        platforms: Optional[List[Platform]] = None
    ) -> Dict:
        """Gera dashboard unificado de todas as plataformas"""
        
        platforms = platforms or self.connected_platforms
        
        dashboard = {
            "date_range": {
                "start": date_range[0].isoformat(),
                "end": date_range[1].isoformat()
            },
            "summary": {
                "total_spend": 0,
                "total_revenue": 0,
                "total_roas": 0,
                "total_conversions": 0,
                "total_impressions": 0,
                "total_clicks": 0
            },
            "by_platform": {},
            "by_campaign": [],
            "trends": {
                "daily_spend": [],
                "daily_roas": [],
                "daily_conversions": []
            }
        }
        
        # Agrega dados por plataforma (simulado)
        for platform in platforms:
            platform_data = await self._fetch_platform_data(platform, date_range)
            
            dashboard["by_platform"][platform.value] = platform_data
            
            # Soma totais
            dashboard["summary"]["total_spend"] += platform_data.get("spend", 0)
            dashboard["summary"]["total_revenue"] += platform_data.get("revenue", 0)
            dashboard["summary"]["total_conversions"] += platform_data.get("conversions", 0)
            dashboard["summary"]["total_impressions"] += platform_data.get("impressions", 0)
            dashboard["summary"]["total_clicks"] += platform_data.get("clicks", 0)
            
        # Calcula ROAS total
        if dashboard["summary"]["total_spend"] > 0:
            dashboard["summary"]["total_roas"] = (
                dashboard["summary"]["total_revenue"] / 
                dashboard["summary"]["total_spend"]
            )
            
        return dashboard
    
    async def _fetch_platform_data(
        self,
        platform: Platform,
        date_range: Tuple[datetime, datetime]
    ) -> Dict:
        """Busca dados de uma plataforma (simulado)"""
        
        # Em produção, conectaria às APIs reais
        return {
            "spend": 1000,
            "revenue": 3500,
            "roas": 3.5,
            "conversions": 50,
            "impressions": 100000,
            "clicks": 2500,
            "ctr": 2.5,
            "cpc": 0.40,
            "cpa": 20,
            "cvr": 2.0
        }
    
    async def generate_report(
        self,
        report_type: str,
        date_range: Tuple[datetime, datetime],
        platforms: Optional[List[Platform]] = None,
        dimensions: Optional[List[str]] = None,
        metrics: Optional[List[str]] = None
    ) -> Dict:
        """Gera relatório customizado"""
        
        report = {
            "type": report_type,
            "generated_at": datetime.now().isoformat(),
            "date_range": {
                "start": date_range[0].isoformat(),
                "end": date_range[1].isoformat()
            },
            "data": []
        }
        
        dimensions = dimensions or ["campaign"]
        metrics = metrics or ["spend", "revenue", "roas", "conversions"]
        
        # Diferentes tipos de relatório
        if report_type == "campaign_performance":
            report["data"] = await self._campaign_report(date_range, platforms, metrics)
        elif report_type == "creative_analysis":
            report["data"] = await self._creative_report(date_range, platforms)
        elif report_type == "audience_insights":
            report["data"] = await self._audience_report(date_range, platforms)
        elif report_type == "budget_pacing":
            report["data"] = await self._budget_pacing_report(date_range, platforms)
            
        return report
    
    async def _campaign_report(
        self,
        date_range: Tuple[datetime, datetime],
        platforms: Optional[List[Platform]],
        metrics: List[str]
    ) -> List[Dict]:
        """Relatório de performance de campanhas"""
        # Simulado
        return [
            {
                "campaign_name": "Campaign 1",
                "platform": "meta",
                "spend": 500,
                "revenue": 1800,
                "roas": 3.6,
                "conversions": 25
            },
            {
                "campaign_name": "Campaign 2",
                "platform": "google",
                "spend": 300,
                "revenue": 900,
                "roas": 3.0,
                "conversions": 15
            }
        ]
    
    async def _creative_report(
        self,
        date_range: Tuple[datetime, datetime],
        platforms: Optional[List[Platform]]
    ) -> List[Dict]:
        """Relatório de criativos"""
        return []
    
    async def _audience_report(
        self,
        date_range: Tuple[datetime, datetime],
        platforms: Optional[List[Platform]]
    ) -> List[Dict]:
        """Relatório de audiences"""
        return []
    
    async def _budget_pacing_report(
        self,
        date_range: Tuple[datetime, datetime],
        platforms: Optional[List[Platform]]
    ) -> Dict:
        """Relatório de pacing de budget"""
        return {
            "monthly_budget": 10000,
            "spent_so_far": 3500,
            "remaining": 6500,
            "days_remaining": 15,
            "recommended_daily_spend": 433.33,
            "on_track": True
        }
    
    def schedule_report(
        self,
        report_config: Dict,
        schedule: str,  # "daily", "weekly", "monthly"
        recipients: List[str],
        format: str = "pdf"  # "pdf", "csv", "json"
    ) -> str:
        """Agenda envio automático de relatório"""
        
        schedule_id = hashlib.md5(str(datetime.now()).encode()).hexdigest()[:8]
        
        # Em produção, salvaria no scheduler
        print(f"Scheduled report {schedule_id}: {schedule} to {recipients}")
        
        return schedule_id


# =============================================================================
# META ADS ENGINE - ORQUESTRADOR PRINCIPAL
# =============================================================================

class MetaAdsEngine:
    """
    Orquestrador principal do Meta Ads Engine
    Combina todas as funcionalidades de Madgicx e Bïrch
    """
    
    def __init__(self):
        self.rule_engine = RuleEngine()
        self.ai_marketer = AIMarketer()
        self.creative_insights = CreativeInsightsEngine()
        self.copy_insights = AdCopyInsightsEngine()
        self.audience_launcher = AudienceLauncher()
        self.bulk_creator = BulkCreator()
        self.post_booster = PostBooster()
        self.reporting = CrossChannelReporting()
        
        # Carrega táticas pré-configuradas
        self._load_default_tactics()
        
    def _load_default_tactics(self):
        """Carrega táticas de automação padrão"""
        
        tactics = [
            AutomationTactics.stop_losing_ads(),
            AutomationTactics.scale_winners(),
            AutomationTactics.prevent_overspend(),
            AutomationTactics.creative_fatigue_detection(),
            AutomationTactics.top_performer_scaling(),
            AutomationTactics.bottom_performer_pause()
        ]
        
        for tactic in tactics:
            self.rule_engine.create_rule(tactic)
            
    async def run_full_audit(
        self,
        campaigns: List[Dict],
        ad_sets: List[Dict],
        ads: List[Dict],
        account_metrics: Dict
    ) -> Dict:
        """Executa auditoria completa da conta"""
        
        # 1. AI Marketer Audit
        audit = await self.ai_marketer.audit_account(
            campaigns, ad_sets, ads, account_metrics
        )
        
        # 2. Creative Portfolio Analysis
        creative_analysis = await self.creative_insights.analyze_creative_portfolio(ads)
        
        # 3. Copy Analysis
        copy_insights = []
        for ad in ads[:10]:  # Top 10
            insight = await self.copy_insights.analyze_copy(
                ad.get("id"),
                ad.get("headline", ""),
                ad.get("description", ""),
                ad.get("cta", ""),
                ad.get("metrics", {})
            )
            copy_insights.append(insight)
            
        # 4. Audience Performance
        audience_performance = self.audience_launcher.get_cross_campaign_audience_performance(ad_sets)
        
        # 5. Generate Recommendations
        recommendations = self.ai_marketer.generate_recommendations(audit)
        
        return {
            "audit": audit,
            "creative_analysis": creative_analysis,
            "copy_insights": copy_insights,
            "audience_performance": audience_performance[:10],
            "recommendations": recommendations,
            "health_score": audit.health_score,
            "potential_savings": audit.estimated_savings,
            "potential_revenue_increase": audit.estimated_revenue_increase
        }
    
    async def run_automations(
        self,
        items: List[Dict],
        api_client: Any
    ) -> Dict:
        """Executa todas as automações ativas"""
        
        results = {
            "rules_executed": 0,
            "items_affected": 0,
            "actions_taken": [],
            "logs": []
        }
        
        for rule_id, rule in self.rule_engine.rules.items():
            if rule.is_active:
                log = await self.rule_engine.run_rule(rule, items, api_client)
                results["rules_executed"] += 1
                results["items_affected"] += log.items_affected
                results["actions_taken"].extend(log.actions_taken)
                results["logs"].append(log)
                
        return results
    
    async def launch_campaign_suite(
        self,
        api_client: Any,
        campaign_name: str,
        objective: CampaignObjective,
        monthly_budget: float,
        seed_audiences: List[Dict],
        creatives: List[Dict]
    ) -> Dict:
        """Lança suite completa de campanha otimizada"""
        
        results = {
            "campaign_id": None,
            "audiences_created": [],
            "ad_sets_created": [],
            "ads_created": [],
            "automation_rules_applied": []
        }
        
        # 1. Cria campanha
        campaign_id = await api_client.create_campaign(campaign_name, objective)
        results["campaign_id"] = campaign_id
        
        # 2. Gera estratégia de audiences
        audience_strategy = await self.audience_launcher.generate_audience_strategy(
            seed_audiences, monthly_budget, objective
        )
        
        # 3. Cria audiences
        created_audiences = await self.audience_launcher.bulk_create_audiences(
            api_client, audience_strategy
        )
        results["audiences_created"] = created_audiences
        
        # 4. Cria ad sets para cada audience
        for audience in created_audiences:
            if audience.get("status") == "created":
                ad_set_id = await api_client.create_ad_set(
                    campaign_id,
                    {
                        "name": f"AdSet - {audience['name']}",
                        "audience_id": audience["id"],
                        "daily_budget": audience_strategy["budget_allocation"].get(
                            audience["stage"], 100
                        ) / len(created_audiences) * 30  # Daily from monthly
                    }
                )
                results["ad_sets_created"].append({
                    "id": ad_set_id,
                    "audience": audience["name"]
                })
                
                # 5. Cria ads para cada ad set
                for creative in creatives:
                    ad_id = await api_client.create_ad({
                        "ad_set_id": ad_set_id,
                        "creative": creative
                    })
                    results["ads_created"].append({
                        "id": ad_id,
                        "ad_set_id": ad_set_id
                    })
                    
        # 6. Aplica regras de automação
        for rule_id, rule in self.rule_engine.rules.items():
            results["automation_rules_applied"].append({
                "rule_id": rule_id,
                "name": rule.name
            })
            
        return results
    
    def get_dashboard_data(self) -> Dict:
        """Retorna dados para dashboard"""
        
        return {
            "active_rules": len([r for r in self.rule_engine.rules.values() if r.is_active]),
            "total_rules": len(self.rule_engine.rules),
            "custom_metrics": len(self.rule_engine.custom_metrics),
            "recent_logs": self.rule_engine.logs[-10:],
            "connected_platforms": len(self.reporting.connected_platforms)
        }


# =============================================================================
# MOCK API CLIENT - PARA TESTES
# =============================================================================

class MockMetaAdsClient:
    """Cliente mock para Meta Ads API - para desenvolvimento/testes"""
    
    def __init__(self, access_token: str = ""):
        self.access_token = access_token
        self._id_counter = 1000
        
    def _generate_id(self) -> str:
        self._id_counter += 1
        return str(self._id_counter)
    
    async def update_status(self, item_id: str, status: str) -> bool:
        print(f"[MOCK] Updated {item_id} status to {status}")
        return True
    
    async def update_budget(self, item_id: str, budget: float) -> bool:
        print(f"[MOCK] Updated {item_id} budget to ${budget:.2f}")
        return True
    
    async def update_bid(self, item_id: str, bid: float) -> bool:
        print(f"[MOCK] Updated {item_id} bid to ${bid:.2f}")
        return True
    
    async def duplicate(self, item_id: str) -> str:
        new_id = self._generate_id()
        print(f"[MOCK] Duplicated {item_id} to {new_id}")
        return new_id
    
    async def rotate_creative(self, item_id: str) -> bool:
        print(f"[MOCK] Rotated creative for {item_id}")
        return True
    
    async def create_lookalike(self, source_id: str, percentage: float) -> str:
        new_id = self._generate_id()
        print(f"[MOCK] Created {percentage}% lookalike from {source_id}: {new_id}")
        return new_id
    
    async def create_audience(self, config: Dict) -> str:
        new_id = self._generate_id()
        print(f"[MOCK] Created audience: {config.get('name')} -> {new_id}")
        return new_id
    
    async def create_campaign(self, name: str, objective: CampaignObjective) -> str:
        new_id = self._generate_id()
        print(f"[MOCK] Created campaign: {name} ({objective.value}) -> {new_id}")
        return new_id
    
    async def create_ad_set(self, campaign_id: str, config: Dict) -> str:
        new_id = self._generate_id()
        print(f"[MOCK] Created ad set in {campaign_id}: {config.get('name')} -> {new_id}")
        return new_id
    
    async def create_ad(self, config: Dict) -> str:
        new_id = self._generate_id()
        print(f"[MOCK] Created ad in {config.get('ad_set_id')} -> {new_id}")
        return new_id
    
    async def boost_post(self, post_id: str, config: Dict) -> Dict:
        ad_id = self._generate_id()
        print(f"[MOCK] Boosted post {post_id} with ${config.get('budget')} -> {ad_id}")
        return {"ad_id": ad_id}
    
    async def duplicate_ad(
        self, 
        ad_id: str, 
        target_ad_set: str,
        copy_creative: bool = True
    ) -> str:
        new_id = self._generate_id()
        print(f"[MOCK] Duplicated ad {ad_id} to {target_ad_set} -> {new_id}")
        return new_id


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    # Enums
    "Platform",
    "CampaignObjective", 
    "AdStatus",
    "RuleAction",
    "ConditionOperator",
    "LogicalOperator",
    "TimeRange",
    "CreativeType",
    "AudienceType",
    
    # Data Classes
    "Metric",
    "CustomMetric",
    "Condition",
    "ConditionGroup",
    "ActionConfig",
    "AutomationRule",
    "RuleLog",
    "CreativeInsight",
    "AdCopyInsight",
    "AudiencePerformance",
    "AccountAudit",
    
    # Engines
    "RuleEngine",
    "AutomationTactics",
    "AIMarketer",
    "CreativeInsightsEngine",
    "AdCopyInsightsEngine",
    "AudienceLauncher",
    "BulkCreator",
    "PostBooster",
    "CrossChannelReporting",
    "MetaAdsEngine",
    
    # Mock
    "MockMetaAdsClient"
]
