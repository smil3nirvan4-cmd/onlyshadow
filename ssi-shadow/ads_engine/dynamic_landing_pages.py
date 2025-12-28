"""
S.S.I. SHADOW — DYNAMIC LANDING PAGE SYSTEM
GROAS-STYLE PERSONALIZED LANDING PAGES

Similar ao GROAS Dynamic Landing Pages:
1. Single-page framework com variações dinâmicas
2. CSS selectors para swap de conteúdo
3. Message match perfeito ad → landing page
4. Edge delivery via Cloudflare Workers
5. A/B testing automático de variações

Fluxo:
1. Usuário clica no ad
2. Request passa pelo Cloudflare Worker
3. Worker injeta conteúdo dinâmico baseado em:
   - Keyword do ad
   - Intent detectado
   - Dados do S.S.I. Shadow (trust score, LTV)
4. Página personalizada é servida
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_dynamic_lp')

# =============================================================================
# TYPES
# =============================================================================

class SelectorType(Enum):
    TEXT = "text"
    HTML = "html"
    ATTRIBUTE = "attribute"
    IMAGE = "image"
    STYLE = "style"


class PersonalizationType(Enum):
    KEYWORD = "keyword"
    INTENT = "intent"
    AUDIENCE = "audience"
    GEO = "geo"
    DEVICE = "device"
    TIME = "time"


@dataclass
class Selector:
    """CSS selector para swap de conteúdo"""
    id: str
    css_selector: str
    selector_type: SelectorType
    
    # Content variations
    default_content: str = ""
    variations: Dict[str, str] = field(default_factory=dict)
    
    # Personalization
    personalization_type: PersonalizationType = PersonalizationType.KEYWORD
    
    # Attribute for ATTRIBUTE type
    attribute_name: str = ""
    
    # Description
    description: str = ""


@dataclass
class LandingPageTemplate:
    """Template de landing page"""
    template_id: str
    name: str
    base_url: str
    
    # Selectors
    selectors: List[Selector] = field(default_factory=list)
    
    # Meta
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    
    # Stats
    total_variations: int = 0
    total_views: int = 0
    total_conversions: int = 0


@dataclass
class DynamicContent:
    """Conteúdo dinâmico para uma página"""
    keyword: str
    intent: str
    
    # Personalized content
    headline: str = ""
    subheadline: str = ""
    cta_text: str = ""
    hero_image: str = ""
    bullets: List[str] = field(default_factory=list)
    
    # Additional
    urgency_text: str = ""
    social_proof: str = ""
    offer_text: str = ""
    
    # Meta
    meta_title: str = ""
    meta_description: str = ""
    
    # Tracking
    variant_id: str = ""
    experiment_id: str = ""


@dataclass
class PageView:
    """View de página para analytics"""
    view_id: str
    template_id: str
    variant_id: str
    
    # Context
    keyword: str
    intent: str
    device: str
    geo: str
    
    # User
    user_id: Optional[str] = None
    session_id: Optional[str] = None
    
    # Timing
    timestamp: datetime = field(default_factory=datetime.now)
    
    # Behavior
    scroll_depth: float = 0
    time_on_page: float = 0
    converted: bool = False


# =============================================================================
# CONTENT GENERATOR
# =============================================================================

class DynamicContentGenerator:
    """
    Gera conteúdo dinâmico para landing pages.
    Similar ao Conversion Copy Agent do GROAS.
    """
    
    # Templates por intent
    HEADLINE_TEMPLATES = {
        'transactional': [
            "{keyword} - Melhor Preço Garantido",
            "Compre {keyword} com Desconto",
            "{keyword} em Promoção | Frete Grátis",
            "Oferta Especial: {keyword}",
            "{keyword} - Entrega Expressa"
        ],
        'commercial': [
            "Melhor {keyword} de 2024 | Guia Completo",
            "Compare {keyword} - Encontre o Ideal",
            "{keyword}: Análises e Avaliações",
            "Top {keyword} do Mercado",
            "Qual {keyword} Escolher?"
        ],
        'informational': [
            "Tudo Sobre {keyword}",
            "Guia Completo: {keyword}",
            "{keyword} - O Que Você Precisa Saber",
            "Entenda {keyword} em 5 Minutos",
            "Como Escolher {keyword}"
        ]
    }
    
    SUBHEADLINE_TEMPLATES = {
        'transactional': [
            "Ofertas exclusivas com até {discount}% de desconto. Parcele em 12x sem juros.",
            "Entrega rápida para todo Brasil. Satisfação garantida ou seu dinheiro de volta.",
            "Os melhores preços do mercado. Compre agora e economize.",
            "{count}+ clientes satisfeitos. Qualidade comprovada."
        ],
        'commercial': [
            "Comparamos os melhores {keyword} para você escolher com confiança.",
            "Análises detalhadas de especialistas. Encontre o produto ideal.",
            "Avaliações reais de quem já comprou. Tome a melhor decisão."
        ],
        'informational': [
            "Guia completo e atualizado. Aprenda tudo sobre {keyword}.",
            "Conteúdo criado por especialistas. Tire suas dúvidas agora."
        ]
    }
    
    CTA_TEMPLATES = {
        'transactional': ["Comprar Agora", "Ver Ofertas", "Garantir Desconto", "Adicionar ao Carrinho"],
        'commercial': ["Ver Comparativo", "Ler Análises", "Comparar Preços", "Ver Ranking"],
        'informational': ["Ler Mais", "Ver Guia", "Aprender Agora", "Começar"]
    }
    
    BULLET_TEMPLATES = {
        'transactional': [
            "✓ {keyword} com garantia de {warranty}",
            "✓ Frete grátis acima de R${min_order}",
            "✓ Parcele em até 12x sem juros",
            "✓ Entrega expressa em {days} dias",
            "✓ {count}+ avaliações 5 estrelas",
            "✓ Satisfação garantida ou dinheiro de volta"
        ],
        'commercial': [
            "✓ Comparativo atualizado {year}",
            "✓ Avaliações de especialistas",
            "✓ Prós e contras detalhados",
            "✓ Análise de custo-benefício",
            "✓ Melhor opção para cada perfil"
        ],
        'informational': [
            "✓ Guia completo e atualizado",
            "✓ Explicações simples e diretas",
            "✓ Dicas de especialistas",
            "✓ Exemplos práticos",
            "✓ Conteúdo 100% gratuito"
        ]
    }
    
    URGENCY_TEMPLATES = [
        "⏰ Oferta expira em {hours}h",
        "🔥 Últimas {count} unidades",
        "⚡ Só até {day}!",
        "🏷️ {discount}% OFF por tempo limitado"
    ]
    
    SOCIAL_PROOF_TEMPLATES = [
        "★★★★★ {rating}/5 ({count} avaliações)",
        "👥 {count}+ clientes satisfeitos",
        "🏆 Melhor avaliado de {year}",
        "📈 {count}+ vendidos este mês"
    ]
    
    def __init__(self):
        self.default_values = {
            'discount': '20',
            'count': '10.000',
            'warranty': '1 ano',
            'min_order': '99',
            'days': '3',
            'year': str(datetime.now().year),
            'hours': '24',
            'day': 'domingo',
            'rating': '4.8'
        }
    
    def _fill_template(self, template: str, keyword: str, context: Dict = None) -> str:
        """Preenche template com variáveis"""
        result = template.replace('{keyword}', keyword.title())
        
        values = {**self.default_values, **(context or {})}
        
        for key, value in values.items():
            result = result.replace(f'{{{key}}}', str(value))
        
        return result
    
    def generate(
        self,
        keyword: str,
        intent: str = 'transactional',
        context: Dict = None
    ) -> DynamicContent:
        """Gera conteúdo dinâmico completo"""
        
        ctx = context or {}
        
        # Select templates
        headlines = self.HEADLINE_TEMPLATES.get(intent, self.HEADLINE_TEMPLATES['transactional'])
        subheadlines = self.SUBHEADLINE_TEMPLATES.get(intent, self.SUBHEADLINE_TEMPLATES['transactional'])
        ctas = self.CTA_TEMPLATES.get(intent, self.CTA_TEMPLATES['transactional'])
        bullets = self.BULLET_TEMPLATES.get(intent, self.BULLET_TEMPLATES['transactional'])
        
        # Generate content
        import random
        
        headline = self._fill_template(random.choice(headlines), keyword, ctx)
        subheadline = self._fill_template(random.choice(subheadlines), keyword, ctx)
        cta = random.choice(ctas)
        
        # Generate bullets
        bullet_texts = [
            self._fill_template(b, keyword, ctx)
            for b in random.sample(bullets, min(4, len(bullets)))
        ]
        
        # Urgency and social proof (for transactional)
        urgency = ""
        social_proof = ""
        
        if intent == 'transactional':
            urgency = self._fill_template(random.choice(self.URGENCY_TEMPLATES), keyword, ctx)
            social_proof = self._fill_template(random.choice(self.SOCIAL_PROOF_TEMPLATES), keyword, ctx)
        
        # Meta tags
        meta_title = f"{keyword.title()} | {headline[:30]}"
        meta_description = subheadline[:150]
        
        # Generate variant ID
        variant_id = hashlib.md5(f"{keyword}:{intent}:{datetime.now().isoformat()}".encode()).hexdigest()[:8]
        
        return DynamicContent(
            keyword=keyword,
            intent=intent,
            headline=headline,
            subheadline=subheadline,
            cta_text=cta,
            bullets=bullet_texts,
            urgency_text=urgency,
            social_proof=social_proof,
            meta_title=meta_title,
            meta_description=meta_description,
            variant_id=variant_id
        )


# =============================================================================
# LANDING PAGE ENGINE
# =============================================================================

class DynamicLandingPageEngine:
    """
    Engine principal para landing pages dinâmicas.
    Similar ao sistema de Dynamic Landing Pages do GROAS.
    """
    
    def __init__(self):
        self.content_generator = DynamicContentGenerator()
        self.templates: Dict[str, LandingPageTemplate] = {}
        self.page_views: List[PageView] = []
    
    def create_template(
        self,
        template_id: str,
        name: str,
        base_url: str,
        selectors: List[Dict] = None
    ) -> LandingPageTemplate:
        """Cria template de landing page"""
        
        # Default selectors (similar to GROAS)
        default_selectors = [
            Selector(
                id='headline',
                css_selector='h1, .hero-headline, .main-title',
                selector_type=SelectorType.TEXT,
                description='Headline principal'
            ),
            Selector(
                id='subheadline',
                css_selector='.hero-subtitle, .subheadline, h2.subtitle',
                selector_type=SelectorType.TEXT,
                description='Subtítulo'
            ),
            Selector(
                id='cta_button',
                css_selector='.cta-button, .btn-primary, button[type="submit"]',
                selector_type=SelectorType.TEXT,
                description='Botão de CTA'
            ),
            Selector(
                id='cta_button_href',
                css_selector='.cta-button, .btn-primary',
                selector_type=SelectorType.ATTRIBUTE,
                attribute_name='href',
                description='Link do CTA'
            ),
            Selector(
                id='bullet_1',
                css_selector='.benefit-1, .bullet:nth-child(1), li:nth-child(1)',
                selector_type=SelectorType.TEXT,
                description='Bullet 1'
            ),
            Selector(
                id='bullet_2',
                css_selector='.benefit-2, .bullet:nth-child(2), li:nth-child(2)',
                selector_type=SelectorType.TEXT,
                description='Bullet 2'
            ),
            Selector(
                id='bullet_3',
                css_selector='.benefit-3, .bullet:nth-child(3), li:nth-child(3)',
                selector_type=SelectorType.TEXT,
                description='Bullet 3'
            ),
            Selector(
                id='bullet_4',
                css_selector='.benefit-4, .bullet:nth-child(4), li:nth-child(4)',
                selector_type=SelectorType.TEXT,
                description='Bullet 4'
            ),
            Selector(
                id='urgency',
                css_selector='.urgency-banner, .countdown, .limited-offer',
                selector_type=SelectorType.HTML,
                description='Banner de urgência'
            ),
            Selector(
                id='social_proof',
                css_selector='.social-proof, .testimonials-count, .reviews-badge',
                selector_type=SelectorType.TEXT,
                description='Social proof'
            ),
            Selector(
                id='meta_title',
                css_selector='title',
                selector_type=SelectorType.TEXT,
                description='Meta title'
            ),
            Selector(
                id='meta_description',
                css_selector='meta[name="description"]',
                selector_type=SelectorType.ATTRIBUTE,
                attribute_name='content',
                description='Meta description'
            )
        ]
        
        # Merge with custom selectors
        if selectors:
            for sel_dict in selectors:
                custom_selector = Selector(**sel_dict)
                default_selectors.append(custom_selector)
        
        template = LandingPageTemplate(
            template_id=template_id,
            name=name,
            base_url=base_url,
            selectors=default_selectors
        )
        
        self.templates[template_id] = template
        
        logger.info(f"Created template '{name}' with {len(default_selectors)} selectors")
        
        return template
    
    def generate_variation(
        self,
        template_id: str,
        keyword: str,
        intent: str = 'transactional',
        context: Dict = None
    ) -> Dict[str, Any]:
        """
        Gera variação de página para keyword.
        """
        template = self.templates.get(template_id)
        
        if not template:
            raise ValueError(f"Template {template_id} not found")
        
        # Generate content
        content = self.content_generator.generate(keyword, intent, context)
        
        # Map content to selectors
        selector_values = {}
        
        for selector in template.selectors:
            if selector.id == 'headline':
                selector_values[selector.id] = content.headline
            elif selector.id == 'subheadline':
                selector_values[selector.id] = content.subheadline
            elif selector.id == 'cta_button':
                selector_values[selector.id] = content.cta_text
            elif selector.id.startswith('bullet_'):
                idx = int(selector.id.split('_')[1]) - 1
                if idx < len(content.bullets):
                    selector_values[selector.id] = content.bullets[idx]
            elif selector.id == 'urgency':
                selector_values[selector.id] = content.urgency_text
            elif selector.id == 'social_proof':
                selector_values[selector.id] = content.social_proof
            elif selector.id == 'meta_title':
                selector_values[selector.id] = content.meta_title
            elif selector.id == 'meta_description':
                selector_values[selector.id] = content.meta_description
        
        # Generate injection script
        injection_script = self._generate_injection_script(template, selector_values, content)
        
        # Generate tracking snippet
        tracking_snippet = self._generate_tracking_snippet(content)
        
        return {
            'template_id': template_id,
            'variant_id': content.variant_id,
            'keyword': keyword,
            'intent': intent,
            'content': content.__dict__,
            'selector_values': selector_values,
            'injection_script': injection_script,
            'tracking_snippet': tracking_snippet,
            'base_url': template.base_url
        }
    
    def _generate_injection_script(
        self,
        template: LandingPageTemplate,
        values: Dict[str, str],
        content: DynamicContent
    ) -> str:
        """Gera script JS para injetar conteúdo dinâmico"""
        
        # Build selector operations
        operations = []
        
        for selector in template.selectors:
            if selector.id not in values or not values[selector.id]:
                continue
            
            value = values[selector.id].replace("'", "\\'").replace("\n", "\\n")
            
            if selector.selector_type == SelectorType.TEXT:
                operations.append(f"""
                    els = document.querySelectorAll('{selector.css_selector}');
                    els.forEach(el => el.textContent = '{value}');
                """)
            elif selector.selector_type == SelectorType.HTML:
                operations.append(f"""
                    els = document.querySelectorAll('{selector.css_selector}');
                    els.forEach(el => el.innerHTML = '{value}');
                """)
            elif selector.selector_type == SelectorType.ATTRIBUTE:
                operations.append(f"""
                    els = document.querySelectorAll('{selector.css_selector}');
                    els.forEach(el => el.setAttribute('{selector.attribute_name}', '{value}'));
                """)
        
        operations_js = '\n'.join(operations)
        
        return f"""
// S.S.I. Shadow Dynamic Landing Page v1.0
// Variant: {content.variant_id}
// Keyword: {content.keyword}
// Intent: {content.intent}

(function() {{
    'use strict';
    
    var dynamicData = {{
        variantId: '{content.variant_id}',
        keyword: '{content.keyword}',
        intent: '{content.intent}'
    }};
    
    function injectContent() {{
        var els;
        
        {operations_js}
        
        // Add variant tracking attribute
        document.body.setAttribute('data-ssi-variant', dynamicData.variantId);
        document.body.setAttribute('data-ssi-keyword', dynamicData.keyword);
        
        // Dispatch event for integrations
        window.dispatchEvent(new CustomEvent('ssi:pagePersonalized', {{
            detail: dynamicData
        }}));
        
        console.log('[SSI Shadow] Page personalized for:', dynamicData.keyword);
    }}
    
    // Execute when DOM ready
    if (document.readyState === 'loading') {{
        document.addEventListener('DOMContentLoaded', injectContent);
    }} else {{
        injectContent();
    }}
    
    // Expose for debugging
    window.__ssiDynamic = dynamicData;
}})();
        """.strip()
    
    def _generate_tracking_snippet(self, content: DynamicContent) -> str:
        """Gera snippet de tracking"""
        
        return f"""
<!-- S.S.I. Shadow Dynamic LP Tracking -->
<script>
(function() {{
    // Track page view
    if (window.ssiShadow) {{
        window.ssiShadow.track('dynamic_lp_view', {{
            variant_id: '{content.variant_id}',
            keyword: '{content.keyword}',
            intent: '{content.intent}'
        }});
    }}
    
    // Track CTA clicks
    document.addEventListener('click', function(e) {{
        var cta = e.target.closest('.cta-button, .btn-primary, button[type="submit"]');
        if (cta && window.ssiShadow) {{
            window.ssiShadow.track('dynamic_lp_cta_click', {{
                variant_id: '{content.variant_id}',
                keyword: '{content.keyword}',
                cta_text: cta.textContent
            }});
        }}
    }});
}})();
</script>
        """.strip()
    
    def generate_cloudflare_worker(self) -> str:
        """
        Gera código do Cloudflare Worker para servir páginas dinâmicas.
        """
        
        return '''
// S.S.I. Shadow Dynamic Landing Page Worker
// Deploy to Cloudflare Workers

export default {
    async fetch(request, env, ctx) {
        const url = new URL(request.url);
        
        // Check if dynamic LP request
        if (!url.searchParams.has('ssi_dynamic')) {
            // Pass through to origin
            return fetch(request);
        }
        
        // Extract parameters
        const keyword = url.searchParams.get('keyword') || '';
        const intent = url.searchParams.get('intent') || 'transactional';
        const templateId = url.searchParams.get('template') || 'default';
        
        // Get UTM parameters for tracking
        const utm = {
            source: url.searchParams.get('utm_source'),
            medium: url.searchParams.get('utm_medium'),
            campaign: url.searchParams.get('utm_campaign'),
            term: url.searchParams.get('utm_term') || keyword
        };
        
        // Fetch original page
        const cleanUrl = new URL(url);
        cleanUrl.searchParams.delete('ssi_dynamic');
        cleanUrl.searchParams.delete('keyword');
        cleanUrl.searchParams.delete('intent');
        cleanUrl.searchParams.delete('template');
        
        const response = await fetch(cleanUrl.toString());
        
        if (!response.ok) {
            return response;
        }
        
        // Get HTML
        let html = await response.text();
        
        // Generate dynamic content
        const content = generateDynamicContent(keyword, intent);
        
        // Generate injection script
        const script = generateInjectionScript(content);
        
        // Inject script before </body>
        html = html.replace('</body>', script + '</body>');
        
        // Update meta tags
        html = updateMetaTags(html, content);
        
        // Return modified response
        return new Response(html, {
            headers: {
                'Content-Type': 'text/html',
                'X-SSI-Variant': content.variantId,
                'Cache-Control': 'private, max-age=0'
            }
        });
    }
};

function generateDynamicContent(keyword, intent) {
    const templates = {
        transactional: {
            headlines: [
                `${keyword} - Melhor Preço Garantido`,
                `Compre ${keyword} com Desconto`,
                `${keyword} em Promoção | Frete Grátis`
            ],
            subheadlines: [
                `Ofertas exclusivas com até 20% de desconto. Parcele em 12x sem juros.`,
                `Entrega rápida para todo Brasil. Satisfação garantida.`
            ],
            ctas: ['Comprar Agora', 'Ver Ofertas', 'Garantir Desconto']
        },
        commercial: {
            headlines: [
                `Melhor ${keyword} de 2024`,
                `Compare ${keyword} - Encontre o Ideal`
            ],
            subheadlines: [
                `Comparamos os melhores ${keyword} para você escolher.`
            ],
            ctas: ['Ver Comparativo', 'Ler Análises']
        },
        informational: {
            headlines: [
                `Tudo Sobre ${keyword}`,
                `Guia Completo: ${keyword}`
            ],
            subheadlines: [
                `Guia completo e atualizado. Aprenda tudo sobre ${keyword}.`
            ],
            ctas: ['Ler Mais', 'Ver Guia']
        }
    };
    
    const t = templates[intent] || templates.transactional;
    
    const randomPick = arr => arr[Math.floor(Math.random() * arr.length)];
    
    return {
        variantId: crypto.randomUUID().slice(0, 8),
        keyword: keyword,
        intent: intent,
        headline: randomPick(t.headlines),
        subheadline: randomPick(t.subheadlines),
        cta: randomPick(t.ctas)
    };
}

function generateInjectionScript(content) {
    return `
<script>
(function() {
    document.addEventListener('DOMContentLoaded', function() {
        // Inject headline
        var h1 = document.querySelector('h1, .hero-headline');
        if (h1) h1.textContent = '${content.headline}';
        
        // Inject subheadline
        var sub = document.querySelector('.hero-subtitle, h2');
        if (sub) sub.textContent = '${content.subheadline}';
        
        // Inject CTA
        var cta = document.querySelector('.cta-button, .btn-primary');
        if (cta) cta.textContent = '${content.cta}';
        
        // Track
        document.body.dataset.ssiVariant = '${content.variantId}';
    });
})();
</script>
`;
}

function updateMetaTags(html, content) {
    // Update title
    html = html.replace(
        /<title>.*?<\\/title>/i,
        `<title>${content.keyword} | ${content.headline.slice(0, 30)}</title>`
    );
    
    // Update meta description
    html = html.replace(
        /<meta name="description" content=".*?">/i,
        `<meta name="description" content="${content.subheadline.slice(0, 150)}">`
    );
    
    return html;
}
        '''.strip()
    
    def record_page_view(
        self,
        template_id: str,
        variant_id: str,
        keyword: str,
        intent: str,
        device: str,
        geo: str,
        user_id: str = None
    ) -> PageView:
        """Registra view de página"""
        
        view = PageView(
            view_id=hashlib.md5(f"{datetime.now().isoformat()}:{variant_id}".encode()).hexdigest()[:12],
            template_id=template_id,
            variant_id=variant_id,
            keyword=keyword,
            intent=intent,
            device=device,
            geo=geo,
            user_id=user_id
        )
        
        self.page_views.append(view)
        
        # Update template stats
        if template_id in self.templates:
            self.templates[template_id].total_views += 1
        
        return view
    
    def get_variant_performance(
        self,
        template_id: str,
        days: int = 30
    ) -> Dict[str, Any]:
        """Retorna performance de variantes"""
        
        cutoff = datetime.now() - timedelta(days=days)
        
        recent_views = [
            v for v in self.page_views
            if v.template_id == template_id and v.timestamp >= cutoff
        ]
        
        # Group by variant
        variant_stats = {}
        
        for view in recent_views:
            if view.variant_id not in variant_stats:
                variant_stats[view.variant_id] = {
                    'views': 0,
                    'conversions': 0,
                    'keywords': set(),
                    'devices': {}
                }
            
            stats = variant_stats[view.variant_id]
            stats['views'] += 1
            stats['keywords'].add(view.keyword)
            
            if view.converted:
                stats['conversions'] += 1
            
            if view.device not in stats['devices']:
                stats['devices'][view.device] = 0
            stats['devices'][view.device] += 1
        
        # Calculate CVR
        results = []
        for variant_id, stats in variant_stats.items():
            cvr = stats['conversions'] / stats['views'] if stats['views'] > 0 else 0
            results.append({
                'variant_id': variant_id,
                'views': stats['views'],
                'conversions': stats['conversions'],
                'cvr': cvr,
                'unique_keywords': len(stats['keywords']),
                'device_breakdown': stats['devices']
            })
        
        results.sort(key=lambda x: x['cvr'], reverse=True)
        
        return {
            'template_id': template_id,
            'period_days': days,
            'total_views': len(recent_views),
            'total_conversions': sum(1 for v in recent_views if v.converted),
            'variants': results
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'SelectorType',
    'PersonalizationType',
    'Selector',
    'LandingPageTemplate',
    'DynamicContent',
    'PageView',
    'DynamicContentGenerator',
    'DynamicLandingPageEngine'
]
