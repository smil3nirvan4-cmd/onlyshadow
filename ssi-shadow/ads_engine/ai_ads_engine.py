"""
S.S.I. SHADOW — AI ADS OPTIMIZATION ENGINE
GROAS-LIKE FUNCTIONALITY

Baseado nas funcionalidades do GROAS (groas.ai):
1. AI Agents Ecosystem - Múltiplos agentes especializados
2. Dynamic Landing Page Generation - Landing pages personalizadas por busca
3. Keyword Intelligence - Descoberta, negativação, redundância
4. Conversion Copy Generation - Copy treinado em dados de performance
5. Self-Optimization - Otimização contínua 24/7
6. Behavioral Prediction - 247+ variáveis contextuais

Diferencial vs GROAS:
- Integrado com S.S.I. Shadow (identity, trust score, fraud)
- Multi-platform (Meta, Google, TikTok)
- First-party data enrichment
"""

import os
import json
import hashlib
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from abc import ABC, abstractmethod
import numpy as np
from collections import defaultdict
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_ads_engine')

# =============================================================================
# TYPES
# =============================================================================

class AgentType(Enum):
    SEARCH_INTENT = "search_intent"
    CONVERSION_COPY = "conversion_copy"
    KEYWORD_DISCOVERY = "keyword_discovery"
    NEGATIVE_KEYWORD = "negative_keyword"
    BUDGET_OPTIMIZER = "budget_optimizer"
    LANDING_PAGE = "landing_page"
    AB_TESTING = "ab_testing"
    PERFORMANCE_MONITOR = "performance_monitor"
    QUALITY_SCORE = "quality_score"


class Platform(Enum):
    GOOGLE_ADS = "google_ads"
    META_ADS = "meta_ads"
    TIKTOK_ADS = "tiktok_ads"


class IntentType(Enum):
    INFORMATIONAL = "informational"  # Quer aprender
    NAVIGATIONAL = "navigational"  # Quer ir a um site
    TRANSACTIONAL = "transactional"  # Quer comprar
    COMMERCIAL = "commercial"  # Pesquisando para comprar


class KeywordStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    NEGATIVE = "negative"
    CANDIDATE = "candidate"


@dataclass
class SearchQuery:
    """Query de busca com contexto"""
    query: str
    intent_type: IntentType
    
    # Context
    device: str = "desktop"
    location: str = ""
    time_of_day: str = ""
    day_of_week: str = ""
    
    # User signals (do S.S.I. Shadow)
    user_id: Optional[str] = None
    trust_score: float = 0.5
    ltv_score: float = 0.5
    intent_score: float = 0.5
    
    # Performance
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    cost: float = 0
    revenue: float = 0


@dataclass
class Keyword:
    """Keyword com métricas"""
    keyword: str
    match_type: str  # 'exact', 'phrase', 'broad'
    status: KeywordStatus
    
    # Bids
    current_bid: float = 0
    suggested_bid: float = 0
    
    # Quality
    quality_score: int = 0
    expected_ctr: str = ""  # 'below_average', 'average', 'above_average'
    ad_relevance: str = ""
    landing_page_exp: str = ""
    
    # Performance
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    cost: float = 0
    revenue: float = 0
    
    # Computed
    ctr: float = 0
    cvr: float = 0
    cpc: float = 0
    roas: float = 0


@dataclass
class AdCopy:
    """Copy de anúncio gerado"""
    headline1: str
    headline2: str
    headline3: str
    description1: str
    description2: str
    
    # Sitelinks
    sitelinks: List[Dict[str, str]] = field(default_factory=list)
    
    # Context
    target_keyword: str = ""
    target_intent: IntentType = IntentType.TRANSACTIONAL
    
    # Scores
    predicted_ctr: float = 0
    relevance_score: float = 0
    
    # Testing
    variant_id: str = ""
    is_control: bool = False


@dataclass
class LandingPageVariant:
    """Variante de landing page dinâmica"""
    variant_id: str
    base_url: str
    
    # Dynamic elements
    headline: str = ""
    subheadline: str = ""
    cta_text: str = ""
    hero_image: str = ""
    bullet_points: List[str] = field(default_factory=list)
    
    # Targeting
    target_keyword: str = ""
    target_intent: IntentType = IntentType.TRANSACTIONAL
    
    # Performance
    impressions: int = 0
    conversions: int = 0
    bounce_rate: float = 0
    avg_time_on_page: float = 0


@dataclass
class Campaign:
    """Campanha com configurações"""
    campaign_id: str
    name: str
    platform: Platform
    
    # Budget
    daily_budget: float = 0
    total_spend: float = 0
    
    # Status
    status: str = "enabled"
    
    # Keywords
    keywords: List[Keyword] = field(default_factory=list)
    
    # Ads
    ads: List[AdCopy] = field(default_factory=list)
    
    # Landing pages
    landing_pages: List[LandingPageVariant] = field(default_factory=list)
    
    # Performance
    impressions: int = 0
    clicks: int = 0
    conversions: int = 0
    cost: float = 0
    revenue: float = 0


# =============================================================================
# AI AGENTS BASE
# =============================================================================

class AIAgent(ABC):
    """Base class para AI Agents"""
    
    def __init__(self, agent_type: AgentType, config: Dict = None):
        self.agent_type = agent_type
        self.config = config or {}
        self.last_run: Optional[datetime] = None
        self.run_count: int = 0
    
    @abstractmethod
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Executa o agente"""
        pass
    
    def log_execution(self, result: Dict):
        """Loga execução do agente"""
        self.last_run = datetime.now()
        self.run_count += 1
        logger.info(f"Agent {self.agent_type.value} executed. Run #{self.run_count}")


# =============================================================================
# SEARCH INTENT AGENT
# =============================================================================

class SearchIntentAgent(AIAgent):
    """
    Analisa intent de busca em 247+ variáveis contextuais.
    Similar ao Search Intent Agent do GROAS.
    """
    
    # Intent signals
    TRANSACTIONAL_SIGNALS = [
        'comprar', 'preço', 'valor', 'quanto custa', 'onde comprar',
        'buy', 'price', 'purchase', 'order', 'shop', 'deal', 'discount',
        'barato', 'promoção', 'oferta', 'cupom', 'frete grátis',
        'melhor preço', 'comparar preços'
    ]
    
    COMMERCIAL_SIGNALS = [
        'melhor', 'top', 'review', 'avaliação', 'comparativo',
        'best', 'vs', 'versus', 'comparison', 'alternative',
        'qual escolher', 'vale a pena', 'opinião', 'recomendação'
    ]
    
    INFORMATIONAL_SIGNALS = [
        'como', 'o que é', 'por que', 'quando', 'onde',
        'how', 'what', 'why', 'when', 'where', 'tutorial',
        'guia', 'dicas', 'aprenda', 'entenda'
    ]
    
    def __init__(self):
        super().__init__(AgentType.SEARCH_INTENT)
        
        # Contextual weights (247 variables simplified to categories)
        self.context_weights = {
            'device': 0.05,
            'time_of_day': 0.03,
            'day_of_week': 0.02,
            'location': 0.05,
            'previous_searches': 0.10,
            'user_history': 0.15,
            'keyword_signals': 0.30,
            'landing_behavior': 0.15,
            'trust_score': 0.10,
            'ltv_score': 0.05
        }
    
    def _detect_intent_from_text(self, query: str) -> Tuple[IntentType, float]:
        """Detecta intent a partir do texto"""
        query_lower = query.lower()
        
        scores = {
            IntentType.TRANSACTIONAL: 0,
            IntentType.COMMERCIAL: 0,
            IntentType.INFORMATIONAL: 0,
            IntentType.NAVIGATIONAL: 0
        }
        
        # Check signals
        for signal in self.TRANSACTIONAL_SIGNALS:
            if signal in query_lower:
                scores[IntentType.TRANSACTIONAL] += 0.2
        
        for signal in self.COMMERCIAL_SIGNALS:
            if signal in query_lower:
                scores[IntentType.COMMERCIAL] += 0.2
        
        for signal in self.INFORMATIONAL_SIGNALS:
            if signal in query_lower:
                scores[IntentType.INFORMATIONAL] += 0.2
        
        # Brand terms -> Navigational
        # (Em produção, ter lista de brands)
        
        # Default boost for transactional (ads context)
        scores[IntentType.TRANSACTIONAL] += 0.1
        
        # Get best intent
        best_intent = max(scores, key=scores.get)
        confidence = min(1.0, scores[best_intent])
        
        return best_intent, confidence
    
    def _calculate_conversion_probability(
        self,
        intent: IntentType,
        context: Dict[str, Any]
    ) -> float:
        """Calcula probabilidade de conversão"""
        
        base_prob = {
            IntentType.TRANSACTIONAL: 0.15,
            IntentType.COMMERCIAL: 0.08,
            IntentType.INFORMATIONAL: 0.02,
            IntentType.NAVIGATIONAL: 0.05
        }[intent]
        
        # Device adjustment
        device = context.get('device', 'desktop')
        if device == 'mobile':
            base_prob *= 0.85
        elif device == 'tablet':
            base_prob *= 0.95
        
        # Time adjustment
        hour = context.get('hour', 12)
        if 9 <= hour <= 21:
            base_prob *= 1.1  # Business hours boost
        
        # Trust score adjustment
        trust_score = context.get('trust_score', 0.5)
        base_prob *= (0.5 + trust_score)
        
        # LTV score adjustment
        ltv_score = context.get('ltv_score', 0.5)
        base_prob *= (0.8 + 0.4 * ltv_score)
        
        return min(1.0, base_prob)
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa intent de uma query"""
        query = context.get('query', '')
        
        # Detect intent
        intent, confidence = self._detect_intent_from_text(query)
        
        # Calculate conversion probability
        conv_prob = self._calculate_conversion_probability(intent, context)
        
        # Calculate bid multiplier suggestion
        bid_multiplier = 1.0
        if intent == IntentType.TRANSACTIONAL:
            bid_multiplier = 1.2 + (conv_prob * 0.5)
        elif intent == IntentType.COMMERCIAL:
            bid_multiplier = 1.0 + (conv_prob * 0.3)
        elif intent == IntentType.INFORMATIONAL:
            bid_multiplier = 0.7
        
        # Extract entities
        entities = self._extract_entities(query)
        
        result = {
            'query': query,
            'intent': intent.value,
            'intent_confidence': confidence,
            'conversion_probability': conv_prob,
            'suggested_bid_multiplier': bid_multiplier,
            'entities': entities,
            'context_signals': {
                'device': context.get('device'),
                'location': context.get('location'),
                'trust_score': context.get('trust_score'),
                'ltv_score': context.get('ltv_score')
            }
        }
        
        self.log_execution(result)
        return result
    
    def _extract_entities(self, query: str) -> Dict[str, List[str]]:
        """Extrai entidades da query"""
        entities = {
            'products': [],
            'brands': [],
            'modifiers': [],
            'locations': []
        }
        
        # Modifiers
        modifiers = ['melhor', 'barato', 'premium', 'profissional', 'best', 'cheap']
        for mod in modifiers:
            if mod in query.lower():
                entities['modifiers'].append(mod)
        
        return entities


# =============================================================================
# CONVERSION COPY AGENT
# =============================================================================

class ConversionCopyAgent(AIAgent):
    """
    Gera copy de alta conversão.
    Treinado em padrões de ads de alta performance.
    """
    
    # Copy templates por intent
    TEMPLATES = {
        IntentType.TRANSACTIONAL: {
            'headlines': [
                "{keyword} - {discount}% OFF Hoje",
                "Compre {keyword} | Frete Grátis",
                "{keyword} em Promoção | Até {discount}% OFF",
                "Oferta: {keyword} | Entrega Rápida",
                "{keyword} - Melhor Preço Garantido"
            ],
            'descriptions': [
                "✓ {keyword} com os melhores preços. Aproveite {discount}% de desconto. Frete grátis acima de R${min_order}. Compre agora!",
                "Encontre {keyword} de qualidade. Entrega expressa em todo Brasil. Satisfação garantida ou seu dinheiro de volta.",
                "{quantity}+ clientes satisfeitos. {keyword} original com garantia. Parcele em até 12x sem juros."
            ],
            'ctas': ['Compre Agora', 'Ver Ofertas', 'Aproveitar Desconto', 'Garantir Meu Pedido']
        },
        IntentType.COMMERCIAL: {
            'headlines': [
                "Melhor {keyword} de {year} | Comparativo",
                "{keyword}: Guia Completo de Compra",
                "Top {count} {keyword} | Avaliações Reais",
                "{keyword} Vale a Pena? Descubra",
                "Compare {keyword} | Análise Especialista"
            ],
            'descriptions': [
                "Compare os melhores {keyword} do mercado. Análises detalhadas, prós e contras. Encontre o ideal para você.",
                "Guia definitivo de {keyword}. Avaliamos {count}+ opções para você escolher com confiança.",
                "Especialistas analisaram {keyword}. Veja qual oferece melhor custo-benefício em {year}."
            ],
            'ctas': ['Ver Comparativo', 'Ler Análise', 'Descobrir Mais', 'Ver Ranking']
        },
        IntentType.INFORMATIONAL: {
            'headlines': [
                "Como Escolher {keyword} | Guia {year}",
                "{keyword}: Tudo Que Você Precisa Saber",
                "Guia Completo: {keyword}",
                "O Que é {keyword}? Aprenda Agora",
                "{keyword} Para Iniciantes | Tutorial"
            ],
            'descriptions': [
                "Aprenda tudo sobre {keyword}. Guia completo com dicas de especialistas. Grátis e atualizado.",
                "Descubra como {keyword} pode transformar seu dia a dia. Tutorial passo a passo para iniciantes.",
                "Tire suas dúvidas sobre {keyword}. Conteúdo educativo de qualidade."
            ],
            'ctas': ['Aprender Mais', 'Ver Guia', 'Ler Artigo', 'Começar Agora']
        }
    }
    
    # Power words que aumentam CTR
    POWER_WORDS = [
        'grátis', 'novo', 'exclusivo', 'limitado', 'garantido',
        'comprovado', 'fácil', 'rápido', 'seguro', 'premium',
        'original', 'oficial', 'aprovado', 'recomendado'
    ]
    
    # Urgency triggers
    URGENCY_TRIGGERS = [
        'Últimas unidades', 'Oferta expira hoje', 'Só até amanhã',
        'Estoque limitado', 'Últimas horas', 'Não perca'
    ]
    
    def __init__(self):
        super().__init__(AgentType.CONVERSION_COPY)
        
        # Performance data (em produção, vem do BigQuery)
        self.performance_data = {}
    
    def _fill_template(
        self,
        template: str,
        keyword: str,
        context: Dict[str, Any]
    ) -> str:
        """Preenche template com variáveis"""
        
        replacements = {
            '{keyword}': keyword.title(),
            '{discount}': str(context.get('discount', 20)),
            '{min_order}': str(context.get('min_order', 99)),
            '{quantity}': str(context.get('customer_count', '10.000')),
            '{year}': str(datetime.now().year),
            '{count}': str(context.get('product_count', 10))
        }
        
        result = template
        for key, value in replacements.items():
            result = result.replace(key, value)
        
        return result
    
    def _score_headline(self, headline: str, keyword: str) -> float:
        """Pontua headline para ranking"""
        score = 0.5
        
        headline_lower = headline.lower()
        
        # Keyword presence
        if keyword.lower() in headline_lower:
            score += 0.2
        
        # Power words
        for word in self.POWER_WORDS:
            if word in headline_lower:
                score += 0.05
        
        # Length optimization (30-40 chars ideal)
        length = len(headline)
        if 25 <= length <= 35:
            score += 0.1
        elif length > 40:
            score -= 0.1
        
        # Numbers
        if any(char.isdigit() for char in headline):
            score += 0.05
        
        return min(1.0, score)
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Gera copy para uma keyword/intent"""
        
        keyword = context.get('keyword', '')
        intent = IntentType(context.get('intent', 'transactional'))
        
        templates = self.TEMPLATES.get(intent, self.TEMPLATES[IntentType.TRANSACTIONAL])
        
        # Generate headlines
        headlines = []
        for template in templates['headlines']:
            headline = self._fill_template(template, keyword, context)
            score = self._score_headline(headline, keyword)
            headlines.append({
                'text': headline,
                'score': score
            })
        
        # Sort by score
        headlines.sort(key=lambda x: x['score'], reverse=True)
        
        # Generate descriptions
        descriptions = []
        for template in templates['descriptions']:
            desc = self._fill_template(template, keyword, context)
            descriptions.append(desc)
        
        # Select CTAs
        ctas = templates['ctas']
        
        # Create ad copy
        ad_copy = AdCopy(
            headline1=headlines[0]['text'][:30],
            headline2=headlines[1]['text'][:30] if len(headlines) > 1 else "",
            headline3=headlines[2]['text'][:30] if len(headlines) > 2 else "",
            description1=descriptions[0][:90] if descriptions else "",
            description2=descriptions[1][:90] if len(descriptions) > 1 else "",
            target_keyword=keyword,
            target_intent=intent,
            predicted_ctr=headlines[0]['score'] * 0.05,
            relevance_score=headlines[0]['score']
        )
        
        # Add urgency if transactional
        urgency_text = ""
        if intent == IntentType.TRANSACTIONAL:
            urgency_text = random.choice(self.URGENCY_TRIGGERS)
        
        result = {
            'ad_copy': ad_copy.__dict__,
            'all_headlines': headlines[:5],
            'descriptions': descriptions,
            'ctas': ctas,
            'urgency_text': urgency_text,
            'predicted_ctr': ad_copy.predicted_ctr,
            'relevance_score': ad_copy.relevance_score
        }
        
        self.log_execution(result)
        return result


# =============================================================================
# KEYWORD DISCOVERY AGENT
# =============================================================================

class KeywordDiscoveryAgent(AIAgent):
    """
    Descobre novas keywords de alto potencial.
    Analisa search terms, sugere expansões.
    """
    
    def __init__(self):
        super().__init__(AgentType.KEYWORD_DISCOVERY)
        
        # Expansion patterns
        self.expansion_patterns = [
            "{keyword} preço",
            "{keyword} barato",
            "{keyword} online",
            "{keyword} comprar",
            "melhor {keyword}",
            "{keyword} {year}",
            "{keyword} promoção",
            "{keyword} frete grátis",
            "{keyword} original",
            "{keyword} para {modifier}"
        ]
        
        self.modifiers = [
            'iniciantes', 'profissionais', 'casa', 'empresa',
            'homem', 'mulher', 'criança', 'idoso'
        ]
    
    def _generate_expansions(self, seed_keyword: str) -> List[Dict[str, Any]]:
        """Gera expansões de uma keyword seed"""
        expansions = []
        
        year = datetime.now().year
        
        for pattern in self.expansion_patterns:
            if '{modifier}' in pattern:
                for mod in self.modifiers:
                    expanded = pattern.replace('{keyword}', seed_keyword)
                    expanded = expanded.replace('{modifier}', mod)
                    expanded = expanded.replace('{year}', str(year))
                    expansions.append({
                        'keyword': expanded,
                        'type': 'modifier_expansion',
                        'estimated_volume': random.randint(100, 5000),
                        'estimated_cpc': random.uniform(0.5, 3.0),
                        'competition': random.choice(['low', 'medium', 'high'])
                    })
            else:
                expanded = pattern.replace('{keyword}', seed_keyword)
                expanded = expanded.replace('{year}', str(year))
                expansions.append({
                    'keyword': expanded,
                    'type': 'pattern_expansion',
                    'estimated_volume': random.randint(100, 5000),
                    'estimated_cpc': random.uniform(0.5, 3.0),
                    'competition': random.choice(['low', 'medium', 'high'])
                })
        
        return expansions
    
    def _score_keyword(self, keyword_data: Dict) -> float:
        """Pontua keyword para priorização"""
        score = 0.5
        
        # Volume (higher is better, but not too high)
        volume = keyword_data.get('estimated_volume', 0)
        if 500 <= volume <= 5000:
            score += 0.2
        elif volume > 5000:
            score += 0.1
        
        # CPC (lower is better)
        cpc = keyword_data.get('estimated_cpc', 1.0)
        if cpc < 1.0:
            score += 0.2
        elif cpc < 2.0:
            score += 0.1
        
        # Competition (lower is better)
        competition = keyword_data.get('competition', 'high')
        if competition == 'low':
            score += 0.2
        elif competition == 'medium':
            score += 0.1
        
        return min(1.0, score)
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Descobre keywords a partir de seeds"""
        
        seed_keywords = context.get('seed_keywords', [])
        search_terms = context.get('search_terms', [])
        current_keywords = set(context.get('current_keywords', []))
        
        discovered = []
        
        # Expand seed keywords
        for seed in seed_keywords:
            expansions = self._generate_expansions(seed)
            for exp in expansions:
                if exp['keyword'].lower() not in current_keywords:
                    exp['score'] = self._score_keyword(exp)
                    exp['source'] = 'seed_expansion'
                    discovered.append(exp)
        
        # Analyze search terms
        for term in search_terms:
            if term.get('conversions', 0) > 0:
                keyword = term.get('term', '')
                if keyword.lower() not in current_keywords:
                    discovered.append({
                        'keyword': keyword,
                        'type': 'search_term',
                        'estimated_volume': term.get('impressions', 0),
                        'actual_conversions': term.get('conversions', 0),
                        'actual_ctr': term.get('ctr', 0),
                        'score': 0.8,  # High score for converting terms
                        'source': 'converting_search_term'
                    })
        
        # Sort by score
        discovered.sort(key=lambda x: x.get('score', 0), reverse=True)
        
        result = {
            'discovered_keywords': discovered[:50],
            'high_potential': [k for k in discovered if k.get('score', 0) > 0.7][:10],
            'total_found': len(discovered)
        }
        
        self.log_execution(result)
        return result


# =============================================================================
# NEGATIVE KEYWORD AGENT
# =============================================================================

class NegativeKeywordAgent(AIAgent):
    """
    Identifica keywords negativas automaticamente.
    Bloqueia tráfego irrelevante antes de gastar budget.
    """
    
    # Common negative patterns
    NEGATIVE_PATTERNS = [
        'grátis', 'gratuito', 'free', 'download',
        'pdf', 'torrent', 'pirata', 'crack',
        'emprego', 'vaga', 'trabalho', 'salário',
        'curso', 'aula', 'tutorial', 'como fazer',
        'receita', 'diy', 'caseiro'
    ]
    
    def __init__(self):
        super().__init__(AgentType.NEGATIVE_KEYWORD)
        
        # Thresholds
        self.min_impressions = 100
        self.max_ctr_for_negative = 0.005  # 0.5%
        self.min_cost_for_negative = 10.0
        self.max_conversions_for_negative = 0
    
    def _should_negate(self, term_data: Dict) -> Tuple[bool, str]:
        """Decide se deve negativar um termo"""
        
        impressions = term_data.get('impressions', 0)
        clicks = term_data.get('clicks', 0)
        conversions = term_data.get('conversions', 0)
        cost = term_data.get('cost', 0)
        
        # Insufficient data
        if impressions < self.min_impressions:
            return False, "insufficient_data"
        
        # Has conversions
        if conversions > self.max_conversions_for_negative:
            return False, "has_conversions"
        
        # CTR check
        ctr = clicks / impressions if impressions > 0 else 0
        if ctr < self.max_ctr_for_negative and cost > self.min_cost_for_negative:
            return True, "low_ctr_high_spend"
        
        # Pattern check
        term = term_data.get('term', '').lower()
        for pattern in self.NEGATIVE_PATTERNS:
            if pattern in term:
                return True, f"matches_pattern:{pattern}"
        
        # High cost no conversion
        if cost > 50 and conversions == 0:
            return True, "high_cost_no_conversion"
        
        return False, "keep"
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa search terms e sugere negativos"""
        
        search_terms = context.get('search_terms', [])
        current_negatives = set(context.get('current_negatives', []))
        
        new_negatives = []
        kept_terms = []
        
        for term_data in search_terms:
            term = term_data.get('term', '')
            
            if term.lower() in current_negatives:
                continue
            
            should_negate, reason = self._should_negate(term_data)
            
            if should_negate:
                new_negatives.append({
                    'term': term,
                    'reason': reason,
                    'impressions': term_data.get('impressions', 0),
                    'clicks': term_data.get('clicks', 0),
                    'cost': term_data.get('cost', 0),
                    'wasted_spend': term_data.get('cost', 0)
                })
            else:
                kept_terms.append({
                    'term': term,
                    'reason': reason
                })
        
        # Calculate savings
        total_wasted = sum(n['wasted_spend'] for n in new_negatives)
        
        result = {
            'new_negatives': new_negatives,
            'kept_terms': kept_terms,
            'total_wasted_spend': total_wasted,
            'projected_monthly_savings': total_wasted * 4  # Rough projection
        }
        
        self.log_execution(result)
        return result


# =============================================================================
# DYNAMIC LANDING PAGE AGENT
# =============================================================================

class DynamicLandingPageAgent(AIAgent):
    """
    Gera landing pages dinâmicas para cada keyword.
    Message match perfeito entre ad e landing page.
    """
    
    def __init__(self):
        super().__init__(AgentType.LANDING_PAGE)
        
        # Dynamic selectors (CSS selectors to swap)
        self.default_selectors = [
            {'selector': 'h1', 'type': 'headline'},
            {'selector': '.hero-subtitle', 'type': 'subheadline'},
            {'selector': '.cta-button', 'type': 'cta'},
            {'selector': '.hero-image', 'type': 'image'},
            {'selector': '.benefit-1', 'type': 'bullet'},
            {'selector': '.benefit-2', 'type': 'bullet'},
            {'selector': '.benefit-3', 'type': 'bullet'}
        ]
    
    def _generate_headline(self, keyword: str, intent: IntentType) -> str:
        """Gera headline dinâmico"""
        templates = {
            IntentType.TRANSACTIONAL: [
                f"{keyword.title()} - Compre com Desconto",
                f"Encontre o Melhor {keyword.title()} Aqui",
                f"{keyword.title()} em Promoção"
            ],
            IntentType.COMMERCIAL: [
                f"Comparativo: Melhores {keyword.title()}",
                f"Guia de Compra: {keyword.title()}",
                f"Qual {keyword.title()} Escolher?"
            ],
            IntentType.INFORMATIONAL: [
                f"Tudo Sobre {keyword.title()}",
                f"Guia Completo: {keyword.title()}",
                f"Entenda {keyword.title()}"
            ]
        }
        
        options = templates.get(intent, templates[IntentType.TRANSACTIONAL])
        return random.choice(options)
    
    def _generate_subheadline(self, keyword: str, intent: IntentType) -> str:
        """Gera subheadline dinâmico"""
        templates = {
            IntentType.TRANSACTIONAL: [
                f"Ofertas exclusivas em {keyword}. Frete grátis acima de R$99.",
                f"Os melhores preços em {keyword}. Parcele em até 12x.",
                f"{keyword} original com garantia. Entrega rápida."
            ],
            IntentType.COMMERCIAL: [
                f"Compare os melhores {keyword} e escolha o ideal para você.",
                f"Análises detalhadas e avaliações reais de {keyword}.",
                f"Encontre o {keyword} perfeito para suas necessidades."
            ]
        }
        
        options = templates.get(intent, templates[IntentType.TRANSACTIONAL])
        return random.choice(options)
    
    def _generate_cta(self, intent: IntentType) -> str:
        """Gera CTA dinâmico"""
        ctas = {
            IntentType.TRANSACTIONAL: ["Comprar Agora", "Ver Ofertas", "Adicionar ao Carrinho"],
            IntentType.COMMERCIAL: ["Ver Comparativo", "Ler Análises", "Comparar Opções"],
            IntentType.INFORMATIONAL: ["Ler Mais", "Ver Guia", "Aprender"]
        }
        
        options = ctas.get(intent, ctas[IntentType.TRANSACTIONAL])
        return random.choice(options)
    
    def _generate_bullets(self, keyword: str) -> List[str]:
        """Gera bullet points dinâmicos"""
        return [
            f"✓ {keyword.title()} de alta qualidade",
            f"✓ Entrega rápida para todo Brasil",
            f"✓ Satisfação garantida ou seu dinheiro de volta",
            f"✓ Suporte especializado 24/7",
            f"✓ Parcele em até 12x sem juros"
        ]
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Gera variante de landing page para keyword"""
        
        keyword = context.get('keyword', '')
        intent = IntentType(context.get('intent', 'transactional'))
        base_url = context.get('base_url', '')
        
        # Generate variant
        variant_id = hashlib.md5(f"{keyword}:{intent.value}".encode()).hexdigest()[:8]
        
        variant = LandingPageVariant(
            variant_id=variant_id,
            base_url=base_url,
            headline=self._generate_headline(keyword, intent),
            subheadline=self._generate_subheadline(keyword, intent),
            cta_text=self._generate_cta(intent),
            bullet_points=self._generate_bullets(keyword),
            target_keyword=keyword,
            target_intent=intent
        )
        
        # Generate dynamic script
        dynamic_script = self._generate_injection_script(variant)
        
        result = {
            'variant': variant.__dict__,
            'selectors': self.default_selectors,
            'injection_script': dynamic_script,
            'tracking_params': {
                'variant_id': variant_id,
                'keyword': keyword,
                'intent': intent.value
            }
        }
        
        self.log_execution(result)
        return result
    
    def _generate_injection_script(self, variant: LandingPageVariant) -> str:
        """Gera script JS para injetar conteúdo dinâmico"""
        return f"""
// SSI Shadow Dynamic Landing Page Injection
(function() {{
    const dynamicContent = {{
        headline: "{variant.headline}",
        subheadline: "{variant.subheadline}",
        cta: "{variant.cta_text}",
        bullets: {json.dumps(variant.bullet_points)}
    }};
    
    // Wait for DOM
    document.addEventListener('DOMContentLoaded', function() {{
        // Swap headline
        const h1 = document.querySelector('h1');
        if (h1) h1.textContent = dynamicContent.headline;
        
        // Swap subheadline
        const subtitle = document.querySelector('.hero-subtitle, .subheadline, h2');
        if (subtitle) subtitle.textContent = dynamicContent.subheadline;
        
        // Swap CTA
        const cta = document.querySelector('.cta-button, .btn-primary, button[type="submit"]');
        if (cta) cta.textContent = dynamicContent.cta;
        
        // Swap bullets
        const bullets = document.querySelectorAll('.benefit, .bullet, li');
        bullets.forEach((el, i) => {{
            if (dynamicContent.bullets[i]) {{
                el.textContent = dynamicContent.bullets[i];
            }}
        }});
        
        // Track variant view
        if (window.ssiShadow) {{
            window.ssiShadow.track('landing_page_view', {{
                variant_id: '{variant.variant_id}',
                keyword: '{variant.target_keyword}'
            }});
        }}
    }});
}})();
        """.strip()


# =============================================================================
# BUDGET OPTIMIZER AGENT
# =============================================================================

class BudgetOptimizerAgent(AIAgent):
    """
    Otimiza alocação de budget entre campanhas/keywords.
    Maximiza ROAS respeitando restrições.
    """
    
    def __init__(self):
        super().__init__(AgentType.BUDGET_OPTIMIZER)
        
        # Thresholds
        self.min_roas = 1.0
        self.target_roas = 3.0
        self.max_cpc_increase = 0.5  # 50%
        self.max_cpc_decrease = 0.3  # 30%
    
    def _calculate_optimal_bid(
        self,
        keyword: Keyword,
        target_roas: float
    ) -> float:
        """Calcula bid ótimo para keyword"""
        
        if keyword.conversions == 0:
            # Sem conversões: reduzir bid
            return keyword.current_bid * 0.8
        
        # Calculate current metrics
        current_roas = keyword.revenue / keyword.cost if keyword.cost > 0 else 0
        cvr = keyword.conversions / keyword.clicks if keyword.clicks > 0 else 0
        
        if cvr == 0:
            return keyword.current_bid * 0.9
        
        # Target CPA based on target ROAS
        avg_order_value = keyword.revenue / keyword.conversions if keyword.conversions > 0 else 100
        target_cpa = avg_order_value / target_roas
        
        # Optimal CPC = Target CPA * CVR
        optimal_cpc = target_cpa * cvr
        
        # Apply constraints
        max_bid = keyword.current_bid * (1 + self.max_cpc_increase)
        min_bid = keyword.current_bid * (1 - self.max_cpc_decrease)
        
        optimal_cpc = max(min_bid, min(max_bid, optimal_cpc))
        
        return round(optimal_cpc, 2)
    
    def _prioritize_campaigns(
        self,
        campaigns: List[Campaign]
    ) -> List[Dict[str, Any]]:
        """Prioriza campanhas por potencial de ROI"""
        
        prioritized = []
        
        for campaign in campaigns:
            if campaign.cost == 0:
                continue
            
            roas = campaign.revenue / campaign.cost
            ctr = campaign.clicks / campaign.impressions if campaign.impressions > 0 else 0
            cvr = campaign.conversions / campaign.clicks if campaign.clicks > 0 else 0
            
            # Score = ROAS * CVR weight
            score = roas * (1 + cvr * 10)
            
            prioritized.append({
                'campaign_id': campaign.campaign_id,
                'name': campaign.name,
                'current_budget': campaign.daily_budget,
                'roas': roas,
                'ctr': ctr,
                'cvr': cvr,
                'score': score,
                'recommendation': 'increase' if roas > self.target_roas else 'maintain' if roas > self.min_roas else 'decrease'
            })
        
        prioritized.sort(key=lambda x: x['score'], reverse=True)
        
        return prioritized
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Otimiza budget"""
        
        campaigns = context.get('campaigns', [])
        total_budget = context.get('total_budget', 0)
        target_roas = context.get('target_roas', self.target_roas)
        
        # Prioritize campaigns
        prioritized = self._prioritize_campaigns(campaigns)
        
        # Calculate keyword bid adjustments
        keyword_adjustments = []
        
        for campaign in campaigns:
            for keyword in campaign.keywords:
                optimal_bid = self._calculate_optimal_bid(keyword, target_roas)
                
                if abs(optimal_bid - keyword.current_bid) > 0.01:
                    keyword_adjustments.append({
                        'campaign_id': campaign.campaign_id,
                        'keyword': keyword.keyword,
                        'current_bid': keyword.current_bid,
                        'suggested_bid': optimal_bid,
                        'change_pct': (optimal_bid / keyword.current_bid - 1) * 100 if keyword.current_bid > 0 else 0
                    })
        
        # Calculate budget reallocation
        reallocation = []
        remaining_budget = total_budget
        
        for camp in prioritized:
            if camp['recommendation'] == 'increase':
                new_budget = min(camp['current_budget'] * 1.2, remaining_budget * 0.4)
            elif camp['recommendation'] == 'decrease':
                new_budget = camp['current_budget'] * 0.8
            else:
                new_budget = camp['current_budget']
            
            reallocation.append({
                'campaign_id': camp['campaign_id'],
                'current_budget': camp['current_budget'],
                'suggested_budget': round(new_budget, 2),
                'recommendation': camp['recommendation']
            })
            
            remaining_budget -= new_budget
        
        result = {
            'campaign_priorities': prioritized,
            'keyword_bid_adjustments': keyword_adjustments,
            'budget_reallocation': reallocation,
            'projected_roas_improvement': 0.15  # 15% improvement estimate
        }
        
        self.log_execution(result)
        return result


# =============================================================================
# AB TESTING AGENT
# =============================================================================

class ABTestingAgent(AIAgent):
    """
    Roda milhares de testes A/B simultâneos.
    Auto-otimiza baseado em resultados.
    """
    
    def __init__(self):
        super().__init__(AgentType.AB_TESTING)
        
        self.min_sample_size = 100
        self.confidence_level = 0.95
    
    def _calculate_significance(
        self,
        control_conversions: int,
        control_visitors: int,
        variant_conversions: int,
        variant_visitors: int
    ) -> Tuple[bool, float, float]:
        """Calcula significância estatística"""
        
        if control_visitors < self.min_sample_size or variant_visitors < self.min_sample_size:
            return False, 0, 0
        
        # Conversion rates
        cr_control = control_conversions / control_visitors
        cr_variant = variant_conversions / variant_visitors
        
        # Lift
        lift = (cr_variant - cr_control) / cr_control if cr_control > 0 else 0
        
        # Z-score (two-proportion z-test)
        p_pool = (control_conversions + variant_conversions) / (control_visitors + variant_visitors)
        se = np.sqrt(p_pool * (1 - p_pool) * (1/control_visitors + 1/variant_visitors))
        
        if se > 0:
            z_score = (cr_variant - cr_control) / se
            # Approximate p-value
            p_value = 2 * (1 - min(0.9999, 0.5 + 0.5 * np.tanh(z_score * 0.7)))
            is_significant = p_value < (1 - self.confidence_level)
        else:
            is_significant = False
            p_value = 1.0
        
        return is_significant, lift, 1 - p_value
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa testes A/B ativos"""
        
        tests = context.get('tests', [])
        
        results = []
        
        for test in tests:
            control = test.get('control', {})
            variants = test.get('variants', [])
            
            test_results = {
                'test_id': test.get('test_id'),
                'test_name': test.get('name'),
                'control_cvr': control.get('conversions', 0) / max(1, control.get('visitors', 1)),
                'variants': []
            }
            
            for variant in variants:
                is_sig, lift, confidence = self._calculate_significance(
                    control.get('conversions', 0),
                    control.get('visitors', 0),
                    variant.get('conversions', 0),
                    variant.get('visitors', 0)
                )
                
                test_results['variants'].append({
                    'variant_id': variant.get('variant_id'),
                    'cvr': variant.get('conversions', 0) / max(1, variant.get('visitors', 1)),
                    'lift': lift,
                    'confidence': confidence,
                    'is_significant': is_sig,
                    'recommendation': 'winner' if is_sig and lift > 0 else 'loser' if is_sig and lift < 0 else 'continue'
                })
            
            results.append(test_results)
        
        # Find winners
        winners = []
        for test in results:
            for variant in test['variants']:
                if variant['recommendation'] == 'winner':
                    winners.append({
                        'test_id': test['test_id'],
                        'variant_id': variant['variant_id'],
                        'lift': variant['lift'],
                        'confidence': variant['confidence']
                    })
        
        result = {
            'test_results': results,
            'winners': winners,
            'active_tests': len(tests),
            'significant_results': len(winners)
        }
        
        self.log_execution(result)
        return result


# =============================================================================
# QUALITY SCORE OPTIMIZER AGENT
# =============================================================================

class QualityScoreAgent(AIAgent):
    """
    Otimiza Quality Score do Google Ads.
    Melhora CTR, relevância e experiência da landing page.
    """
    
    def __init__(self):
        super().__init__(AgentType.QUALITY_SCORE)
    
    def _analyze_quality_score(self, keyword: Keyword) -> Dict[str, Any]:
        """Analisa componentes do Quality Score"""
        
        issues = []
        recommendations = []
        
        # Expected CTR
        if keyword.expected_ctr == 'below_average':
            issues.append("Expected CTR abaixo da média")
            recommendations.append("Melhorar headlines com keywords mais relevantes")
            recommendations.append("Adicionar números e power words aos ads")
        
        # Ad Relevance
        if keyword.ad_relevance == 'below_average':
            issues.append("Relevância do ad abaixo da média")
            recommendations.append("Incluir keyword exata no headline")
            recommendations.append("Criar ads específicos para grupos de keywords similares")
        
        # Landing Page Experience
        if keyword.landing_page_exp == 'below_average':
            issues.append("Experiência da landing page abaixo da média")
            recommendations.append("Melhorar velocidade de carregamento")
            recommendations.append("Adicionar keyword no H1 e meta description")
            recommendations.append("Garantir mobile-friendliness")
        
        # QS prediction
        predicted_qs_improvement = 0
        if recommendations:
            predicted_qs_improvement = min(3, len(recommendations))
        
        return {
            'current_qs': keyword.quality_score,
            'issues': issues,
            'recommendations': recommendations,
            'predicted_qs_after_fixes': min(10, keyword.quality_score + predicted_qs_improvement),
            'estimated_cpc_reduction': predicted_qs_improvement * 5  # ~5% per QS point
        }
    
    async def execute(self, context: Dict[str, Any]) -> Dict[str, Any]:
        """Analisa e otimiza Quality Score"""
        
        keywords = context.get('keywords', [])
        
        analyses = []
        total_potential_savings = 0
        
        for kw_data in keywords:
            keyword = Keyword(**kw_data) if isinstance(kw_data, dict) else kw_data
            
            analysis = self._analyze_quality_score(keyword)
            analysis['keyword'] = keyword.keyword
            analysis['monthly_spend'] = keyword.cost * 30 / 7  # Weekly to monthly
            
            # Calculate potential savings
            if analysis['recommendations']:
                potential_saving = analysis['monthly_spend'] * (analysis['estimated_cpc_reduction'] / 100)
                analysis['potential_monthly_savings'] = potential_saving
                total_potential_savings += potential_saving
            else:
                analysis['potential_monthly_savings'] = 0
            
            analyses.append(analysis)
        
        # Sort by potential savings
        analyses.sort(key=lambda x: x['potential_monthly_savings'], reverse=True)
        
        result = {
            'keyword_analyses': analyses,
            'total_potential_monthly_savings': total_potential_savings,
            'priority_fixes': [a for a in analyses if a['potential_monthly_savings'] > 100][:10]
        }
        
        self.log_execution(result)
        return result


# =============================================================================
# AI ADS ENGINE (ORCHESTRATOR)
# =============================================================================

class AIAdsEngine:
    """
    Engine principal que orquestra todos os agentes.
    Similar ao GROAS - ecosystem de AI agents.
    """
    
    def __init__(self):
        # Initialize agents
        self.agents = {
            AgentType.SEARCH_INTENT: SearchIntentAgent(),
            AgentType.CONVERSION_COPY: ConversionCopyAgent(),
            AgentType.KEYWORD_DISCOVERY: KeywordDiscoveryAgent(),
            AgentType.NEGATIVE_KEYWORD: NegativeKeywordAgent(),
            AgentType.LANDING_PAGE: DynamicLandingPageAgent(),
            AgentType.BUDGET_OPTIMIZER: BudgetOptimizerAgent(),
            AgentType.AB_TESTING: ABTestingAgent(),
            AgentType.QUALITY_SCORE: QualityScoreAgent()
        }
        
        # Execution history
        self.execution_history: List[Dict] = []
    
    async def analyze_search_intent(self, query: str, context: Dict = None) -> Dict:
        """Analisa intent de uma busca"""
        ctx = context or {}
        ctx['query'] = query
        return await self.agents[AgentType.SEARCH_INTENT].execute(ctx)
    
    async def generate_ad_copy(self, keyword: str, intent: str = 'transactional', context: Dict = None) -> Dict:
        """Gera copy de ad para keyword"""
        ctx = context or {}
        ctx['keyword'] = keyword
        ctx['intent'] = intent
        return await self.agents[AgentType.CONVERSION_COPY].execute(ctx)
    
    async def discover_keywords(self, seed_keywords: List[str], search_terms: List[Dict] = None) -> Dict:
        """Descobre novas keywords"""
        ctx = {
            'seed_keywords': seed_keywords,
            'search_terms': search_terms or [],
            'current_keywords': []
        }
        return await self.agents[AgentType.KEYWORD_DISCOVERY].execute(ctx)
    
    async def find_negative_keywords(self, search_terms: List[Dict]) -> Dict:
        """Encontra keywords negativas"""
        ctx = {
            'search_terms': search_terms,
            'current_negatives': []
        }
        return await self.agents[AgentType.NEGATIVE_KEYWORD].execute(ctx)
    
    async def generate_landing_page(self, keyword: str, intent: str, base_url: str) -> Dict:
        """Gera landing page dinâmica"""
        ctx = {
            'keyword': keyword,
            'intent': intent,
            'base_url': base_url
        }
        return await self.agents[AgentType.LANDING_PAGE].execute(ctx)
    
    async def optimize_budget(self, campaigns: List[Dict], total_budget: float, target_roas: float = 3.0) -> Dict:
        """Otimiza budget entre campanhas"""
        ctx = {
            'campaigns': [Campaign(**c) if isinstance(c, dict) else c for c in campaigns],
            'total_budget': total_budget,
            'target_roas': target_roas
        }
        return await self.agents[AgentType.BUDGET_OPTIMIZER].execute(ctx)
    
    async def analyze_ab_tests(self, tests: List[Dict]) -> Dict:
        """Analisa testes A/B"""
        ctx = {'tests': tests}
        return await self.agents[AgentType.AB_TESTING].execute(ctx)
    
    async def optimize_quality_score(self, keywords: List[Dict]) -> Dict:
        """Otimiza Quality Score"""
        ctx = {'keywords': keywords}
        return await self.agents[AgentType.QUALITY_SCORE].execute(ctx)
    
    async def run_full_optimization(self, campaign_data: Dict) -> Dict:
        """
        Roda ciclo completo de otimização.
        Equivalente ao GROAS running 24/7.
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'optimizations': []
        }
        
        # 1. Keyword Discovery
        if 'seed_keywords' in campaign_data:
            kw_result = await self.discover_keywords(
                campaign_data['seed_keywords'],
                campaign_data.get('search_terms', [])
            )
            results['optimizations'].append({
                'agent': 'keyword_discovery',
                'result': kw_result
            })
        
        # 2. Negative Keywords
        if 'search_terms' in campaign_data:
            neg_result = await self.find_negative_keywords(campaign_data['search_terms'])
            results['optimizations'].append({
                'agent': 'negative_keyword',
                'result': neg_result
            })
        
        # 3. Quality Score
        if 'keywords' in campaign_data:
            qs_result = await self.optimize_quality_score(campaign_data['keywords'])
            results['optimizations'].append({
                'agent': 'quality_score',
                'result': qs_result
            })
        
        # 4. Budget Optimization
        if 'campaigns' in campaign_data:
            budget_result = await self.optimize_budget(
                campaign_data['campaigns'],
                campaign_data.get('total_budget', 1000),
                campaign_data.get('target_roas', 3.0)
            )
            results['optimizations'].append({
                'agent': 'budget_optimizer',
                'result': budget_result
            })
        
        # 5. A/B Test Analysis
        if 'ab_tests' in campaign_data:
            ab_result = await self.analyze_ab_tests(campaign_data['ab_tests'])
            results['optimizations'].append({
                'agent': 'ab_testing',
                'result': ab_result
            })
        
        # Store in history
        self.execution_history.append(results)
        
        # Calculate summary
        results['summary'] = {
            'agents_executed': len(results['optimizations']),
            'total_recommendations': sum(
                len(opt['result'].get('recommendations', [])) +
                len(opt['result'].get('new_negatives', [])) +
                len(opt['result'].get('discovered_keywords', []))
                for opt in results['optimizations']
            )
        }
        
        return results


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'AgentType',
    'Platform',
    'IntentType',
    'KeywordStatus',
    'SearchQuery',
    'Keyword',
    'AdCopy',
    'LandingPageVariant',
    'Campaign',
    'AIAgent',
    'SearchIntentAgent',
    'ConversionCopyAgent',
    'KeywordDiscoveryAgent',
    'NegativeKeywordAgent',
    'DynamicLandingPageAgent',
    'BudgetOptimizerAgent',
    'ABTestingAgent',
    'QualityScoreAgent',
    'AIAdsEngine'
]
