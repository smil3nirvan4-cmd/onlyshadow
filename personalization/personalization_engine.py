"""
S.S.I. SHADOW — REAL-TIME PERSONALIZATION ENGINE
EDGE ML INFERENCE & CONTENT OPTIMIZATION

Personalização em tempo real no edge (Cloudflare Workers):
1. Audience targeting
2. Content optimization
3. Offer selection
4. Dynamic pricing signals
5. CTA personalization

Latência: <50ms para decisões em tempo real.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Callable
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import random
import math

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_personalization')

# =============================================================================
# TYPES
# =============================================================================

class PersonalizationType(Enum):
    CONTENT = "content"
    OFFER = "offer"
    LAYOUT = "layout"
    MESSAGING = "messaging"
    CTA = "cta"
    TIMING = "timing"


class TargetingCriteria(Enum):
    SEGMENT = "segment"
    BEHAVIOR = "behavior"
    CONTEXT = "context"
    PREDICTIVE = "predictive"


@dataclass
class VisitorContext:
    """Contexto do visitante para personalização"""
    # Identity
    ssi_id: str
    visitor_id: Optional[str] = None
    
    # Session
    session_id: str = ""
    pageviews_this_session: int = 0
    time_on_site_seconds: int = 0
    current_page: str = ""
    referrer: str = ""
    
    # Behavioral
    scroll_depth: float = 0
    interactions: int = 0
    products_viewed: List[str] = field(default_factory=list)
    cart_value: float = 0
    
    # Scores
    trust_score: float = 0.5
    intent_score: float = 0.5
    ltv_score: float = 0.5
    
    # Segments
    segments: List[str] = field(default_factory=list)
    
    # Device
    device_type: str = "desktop"
    browser: str = ""
    os: str = ""
    
    # Geo
    country: str = ""
    region: str = ""
    city: str = ""
    
    # Source
    utm_source: str = ""
    utm_medium: str = ""
    utm_campaign: str = ""
    
    # History (from CDP)
    total_orders: int = 0
    total_revenue: float = 0
    days_since_last_visit: int = 999
    days_since_last_purchase: int = 999


@dataclass
class PersonalizationRule:
    """Regra de personalização"""
    id: str
    name: str
    description: str = ""
    personalization_type: PersonalizationType = PersonalizationType.CONTENT
    
    # Targeting
    targeting_criteria: TargetingCriteria = TargetingCriteria.SEGMENT
    target_segments: List[str] = field(default_factory=list)
    target_conditions: Dict[str, Any] = field(default_factory=dict)
    
    # Action
    action: str = ""  # e.g., 'show_banner', 'change_cta'
    action_params: Dict[str, Any] = field(default_factory=dict)
    
    # Priority (higher = more important)
    priority: int = 0
    
    # Limits
    max_impressions_per_session: int = 0  # 0 = unlimited
    max_impressions_per_day: int = 0
    
    # Status
    enabled: bool = True
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    
    # Metrics
    impressions: int = 0
    conversions: int = 0


@dataclass
class PersonalizationDecision:
    """Decisão de personalização"""
    rule_id: str
    personalization_type: PersonalizationType
    action: str
    params: Dict[str, Any]
    confidence: float
    reason: str


@dataclass
class PersonalizationResponse:
    """Resposta do engine de personalização"""
    decisions: List[PersonalizationDecision]
    visitor_context: VisitorContext
    processing_time_ms: float
    debug_info: Optional[Dict] = None


# =============================================================================
# TARGETING ENGINE
# =============================================================================

class TargetingEngine:
    """
    Engine de targeting para avaliar regras.
    """
    
    def evaluate_condition(
        self,
        context: VisitorContext,
        field: str,
        operator: str,
        value: Any
    ) -> bool:
        """Avalia uma condição contra o contexto"""
        
        # Get field value
        if hasattr(context, field):
            actual_value = getattr(context, field)
        else:
            return False
        
        # Evaluate operator
        if operator == 'eq':
            return actual_value == value
        elif operator == 'neq':
            return actual_value != value
        elif operator == 'gt':
            return actual_value > value
        elif operator == 'gte':
            return actual_value >= value
        elif operator == 'lt':
            return actual_value < value
        elif operator == 'lte':
            return actual_value <= value
        elif operator == 'in':
            return actual_value in value
        elif operator == 'contains':
            return value in actual_value
        elif operator == 'starts_with':
            return str(actual_value).startswith(str(value))
        elif operator == 'ends_with':
            return str(actual_value).endswith(str(value))
        
        return False
    
    def evaluate_rule(
        self,
        rule: PersonalizationRule,
        context: VisitorContext
    ) -> Tuple[bool, float, str]:
        """
        Avalia se uma regra se aplica ao contexto.
        Returns: (matches, confidence, reason)
        """
        # Check if enabled
        if not rule.enabled:
            return False, 0, "Rule disabled"
        
        # Check date range
        now = datetime.now()
        if rule.start_date and now < rule.start_date:
            return False, 0, "Not started yet"
        if rule.end_date and now > rule.end_date:
            return False, 0, "Expired"
        
        # Check targeting criteria
        if rule.targeting_criteria == TargetingCriteria.SEGMENT:
            # Check segment membership
            if rule.target_segments:
                matches = any(seg in context.segments for seg in rule.target_segments)
                if not matches:
                    return False, 0, "Not in target segments"
        
        elif rule.targeting_criteria == TargetingCriteria.BEHAVIOR:
            # Check behavioral conditions
            for field, condition in rule.target_conditions.items():
                operator = condition.get('operator', 'eq')
                value = condition.get('value')
                
                if not self.evaluate_condition(context, field, operator, value):
                    return False, 0, f"Condition not met: {field}"
        
        elif rule.targeting_criteria == TargetingCriteria.PREDICTIVE:
            # Check predictive scores
            min_intent = rule.target_conditions.get('min_intent_score', 0)
            if context.intent_score < min_intent:
                return False, 0, f"Intent score too low: {context.intent_score}"
            
            min_ltv = rule.target_conditions.get('min_ltv_score', 0)
            if context.ltv_score < min_ltv:
                return False, 0, f"LTV score too low: {context.ltv_score}"
        
        # Calculate confidence
        confidence = 0.8
        
        # Boost confidence for high-quality visitors
        if context.trust_score >= 0.7:
            confidence += 0.1
        
        # Boost for engaged visitors
        if context.scroll_depth >= 50:
            confidence += 0.05
        
        confidence = min(1.0, confidence)
        
        return True, confidence, f"Matched rule: {rule.name}"


# =============================================================================
# PERSONALIZATION ENGINE
# =============================================================================

class PersonalizationEngine:
    """
    Engine principal de personalização.
    """
    
    def __init__(self):
        self.rules: Dict[str, PersonalizationRule] = {}
        self.targeting = TargetingEngine()
        self._setup_default_rules()
    
    def _setup_default_rules(self):
        """Configura regras padrão"""
        
        # High Intent - Urgency CTA
        self.add_rule(PersonalizationRule(
            id='high_intent_urgency',
            name='High Intent - Show Urgency',
            personalization_type=PersonalizationType.CTA,
            targeting_criteria=TargetingCriteria.PREDICTIVE,
            target_conditions={
                'min_intent_score': 0.7
            },
            action='show_urgency_cta',
            action_params={
                'text': 'Compre agora - Oferta limitada!',
                'countdown_minutes': 15,
                'style': 'urgent'
            },
            priority=90
        ))
        
        # Cart Abandonment - Discount Offer
        self.add_rule(PersonalizationRule(
            id='cart_abandonment_discount',
            name='Cart Abandonment - Show Discount',
            personalization_type=PersonalizationType.OFFER,
            targeting_criteria=TargetingCriteria.BEHAVIOR,
            target_conditions={
                'cart_value': {'operator': 'gt', 'value': 0},
                'time_on_site_seconds': {'operator': 'gt', 'value': 300}
            },
            action='show_exit_intent_popup',
            action_params={
                'discount_percent': 10,
                'headline': 'Espere! Ganhe 10% de desconto',
                'cta': 'Aplicar Desconto'
            },
            priority=85
        ))
        
        # New Visitor - Welcome Message
        self.add_rule(PersonalizationRule(
            id='new_visitor_welcome',
            name='New Visitor - Welcome',
            personalization_type=PersonalizationType.MESSAGING,
            targeting_criteria=TargetingCriteria.BEHAVIOR,
            target_conditions={
                'total_orders': {'operator': 'eq', 'value': 0},
                'pageviews_this_session': {'operator': 'lte', 'value': 2}
            },
            action='show_welcome_banner',
            action_params={
                'message': 'Bem-vindo! Primeira compra com frete grátis.',
                'cta': 'Ver ofertas'
            },
            priority=50
        ))
        
        # Returning Customer - Personalized Recommendations
        self.add_rule(PersonalizationRule(
            id='returning_customer_recs',
            name='Returning Customer - Recommendations',
            personalization_type=PersonalizationType.CONTENT,
            targeting_criteria=TargetingCriteria.BEHAVIOR,
            target_conditions={
                'total_orders': {'operator': 'gte', 'value': 1},
                'days_since_last_visit': {'operator': 'gte', 'value': 7}
            },
            action='show_personalized_recs',
            action_params={
                'rec_type': 'based_on_history',
                'num_products': 4
            },
            priority=70
        ))
        
        # High LTV - VIP Treatment
        self.add_rule(PersonalizationRule(
            id='high_ltv_vip',
            name='High LTV - VIP Treatment',
            personalization_type=PersonalizationType.LAYOUT,
            targeting_criteria=TargetingCriteria.PREDICTIVE,
            target_conditions={
                'min_ltv_score': 0.8
            },
            action='enable_vip_layout',
            action_params={
                'show_vip_badge': True,
                'priority_support': True,
                'exclusive_offers': True
            },
            priority=95
        ))
        
        # Mobile - Simplified Layout
        self.add_rule(PersonalizationRule(
            id='mobile_simplified',
            name='Mobile - Simplified Layout',
            personalization_type=PersonalizationType.LAYOUT,
            targeting_criteria=TargetingCriteria.BEHAVIOR,
            target_conditions={
                'device_type': {'operator': 'eq', 'value': 'mobile'}
            },
            action='enable_mobile_layout',
            action_params={
                'simplified_nav': True,
                'larger_buttons': True,
                'hide_secondary_content': True
            },
            priority=60
        ))
    
    def add_rule(self, rule: PersonalizationRule):
        """Adiciona regra"""
        self.rules[rule.id] = rule
    
    def remove_rule(self, rule_id: str):
        """Remove regra"""
        if rule_id in self.rules:
            del self.rules[rule_id]
    
    def decide(
        self,
        context: VisitorContext,
        requested_types: List[PersonalizationType] = None
    ) -> PersonalizationResponse:
        """
        Toma decisões de personalização para o contexto.
        """
        start_time = datetime.now()
        
        decisions = []
        debug_info = {'rules_evaluated': 0, 'rules_matched': 0}
        
        # Sort rules by priority
        sorted_rules = sorted(
            self.rules.values(),
            key=lambda r: r.priority,
            reverse=True
        )
        
        # Track which types we've already decided
        decided_types = set()
        
        for rule in sorted_rules:
            debug_info['rules_evaluated'] += 1
            
            # Skip if type already decided
            if rule.personalization_type in decided_types:
                continue
            
            # Skip if not in requested types
            if requested_types and rule.personalization_type not in requested_types:
                continue
            
            # Evaluate rule
            matches, confidence, reason = self.targeting.evaluate_rule(rule, context)
            
            if matches:
                debug_info['rules_matched'] += 1
                
                decisions.append(PersonalizationDecision(
                    rule_id=rule.id,
                    personalization_type=rule.personalization_type,
                    action=rule.action,
                    params=rule.action_params,
                    confidence=confidence,
                    reason=reason
                ))
                
                # Update rule metrics
                rule.impressions += 1
                
                # Mark type as decided
                decided_types.add(rule.personalization_type)
        
        processing_time = (datetime.now() - start_time).total_seconds() * 1000
        
        return PersonalizationResponse(
            decisions=decisions,
            visitor_context=context,
            processing_time_ms=processing_time,
            debug_info=debug_info
        )
    
    def get_content_variant(
        self,
        context: VisitorContext,
        content_id: str,
        variants: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Seleciona variante de conteúdo baseado no contexto.
        Usa Multi-Armed Bandit (Thompson Sampling) para otimização.
        """
        if not variants:
            return {}
        
        if len(variants) == 1:
            return variants[0]
        
        # Simple Thompson Sampling
        best_variant = None
        best_sample = -1
        
        for variant in variants:
            # Get variant stats (from cache in production)
            alpha = variant.get('successes', 1) + 1  # Conversions
            beta = variant.get('failures', 1) + 1  # Non-conversions
            
            # Sample from Beta distribution
            sample = random.betavariate(alpha, beta)
            
            if sample > best_sample:
                best_sample = sample
                best_variant = variant
        
        return best_variant or variants[0]
    
    def record_conversion(self, rule_id: str):
        """Registra conversão para uma regra"""
        if rule_id in self.rules:
            self.rules[rule_id].conversions += 1


# =============================================================================
# EDGE PERSONALIZATION (TypeScript output for Cloudflare)
# =============================================================================

def generate_edge_personalization_script() -> str:
    """
    Gera script TypeScript para personalização no edge.
    Pode ser incluído no Worker.
    """
    return '''
// SSI Shadow - Edge Personalization
// Generated script for Cloudflare Worker

interface VisitorContext {
  ssi_id: string;
  intent_score: number;
  ltv_score: number;
  trust_score: number;
  segments: string[];
  device_type: string;
  cart_value: number;
  total_orders: number;
}

interface PersonalizationDecision {
  type: string;
  action: string;
  params: Record<string, any>;
}

export function personalize(ctx: VisitorContext): PersonalizationDecision[] {
  const decisions: PersonalizationDecision[] = [];
  
  // High Intent - Urgency
  if (ctx.intent_score >= 0.7) {
    decisions.push({
      type: 'cta',
      action: 'show_urgency',
      params: {
        text: 'Compre agora!',
        countdown: 900
      }
    });
  }
  
  // Cart Abandonment
  if (ctx.cart_value > 0 && ctx.intent_score < 0.5) {
    decisions.push({
      type: 'offer',
      action: 'show_discount',
      params: {
        percent: 10,
        code: 'SAVE10'
      }
    });
  }
  
  // High LTV - VIP
  if (ctx.ltv_score >= 0.8) {
    decisions.push({
      type: 'layout',
      action: 'vip_treatment',
      params: {
        badge: true,
        priority: true
      }
    });
  }
  
  // Mobile optimization
  if (ctx.device_type === 'mobile') {
    decisions.push({
      type: 'layout',
      action: 'mobile_optimized',
      params: {
        simplified: true
      }
    });
  }
  
  return decisions;
}

// Inject personalization into HTML
export function applyPersonalization(
  html: string, 
  decisions: PersonalizationDecision[]
): string {
  let modifiedHtml = html;
  
  for (const decision of decisions) {
    if (decision.action === 'show_urgency') {
      // Inject urgency banner
      const banner = `
        <div class="ssi-urgency-banner" data-countdown="${decision.params.countdown}">
          <span>${decision.params.text}</span>
          <span class="countdown"></span>
        </div>
      `;
      modifiedHtml = modifiedHtml.replace('</body>', banner + '</body>');
    }
    
    if (decision.action === 'show_discount') {
      // Inject discount popup script
      const popup = `
        <script>
          window.ssiDiscountOffer = {
            percent: ${decision.params.percent},
            code: '${decision.params.code}'
          };
        </script>
      `;
      modifiedHtml = modifiedHtml.replace('</head>', popup + '</head>');
    }
  }
  
  return modifiedHtml;
}
'''


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'PersonalizationType',
    'TargetingCriteria',
    'VisitorContext',
    'PersonalizationRule',
    'PersonalizationDecision',
    'PersonalizationResponse',
    'PersonalizationEngine',
    'TargetingEngine',
    'generate_edge_personalization_script'
]
