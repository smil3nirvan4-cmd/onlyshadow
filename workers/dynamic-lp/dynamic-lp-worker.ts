/**
 * S.S.I. SHADOW — DYNAMIC LANDING PAGE WORKER
 * GROAS-STYLE EDGE PERSONALIZATION
 * 
 * Este Worker intercepta requests para landing pages e:
 * 1. Extrai keyword/intent dos parâmetros UTM ou gclid
 * 2. Consulta API do Shadow para obter conteúdo dinâmico
 * 3. Injeta conteúdo personalizado na página
 * 4. Serve página com message match perfeito
 * 
 * Deploy: wrangler publish
 */

// =============================================================================
// TYPES
// =============================================================================

interface DynamicContent {
  headline: string;
  subheadline: string;
  cta_text: string;
  bullets: string[];
  urgency_text: string;
  social_proof: string;
  meta_title: string;
  meta_description: string;
  variant_id: string;
}

interface SearchContext {
  keyword: string;
  intent: 'purchase' | 'comparison' | 'research' | 'navigation';
  urgency: 'low' | 'medium' | 'high' | 'immediate';
  device: string;
  trust_score: number;
}

// =============================================================================
// CONTENT TEMPLATES
// =============================================================================

const HEADLINE_TEMPLATES = {
  purchase: {
    urgency: [
      "{keyword} - Só Hoje com {discount}% OFF",
      "⚡ {keyword} em Promoção | Aproveite",
      "🔥 Últimas Unidades de {keyword}",
    ],
    value: [
      "{keyword} - Melhor Preço Garantido",
      "Compre {keyword} | Frete Grátis",
      "{keyword} Original | Parcele em 12x",
    ],
  },
  comparison: {
    default: [
      "Melhor {keyword} de 2024 | Comparativo",
      "Top 10 {keyword} | Análise Completa",
      "Compare {keyword} | Guia Atualizado",
    ],
  },
  research: {
    default: [
      "Tudo Sobre {keyword} | Guia Completo",
      "{keyword}: O Que Você Precisa Saber",
      "Como Escolher {keyword} | Dicas",
    ],
  },
};

const SUBHEADLINE_TEMPLATES = {
  purchase: [
    "Ofertas exclusivas com até {discount}% de desconto. Parcele em 12x sem juros. Frete grátis!",
    "Os melhores preços em {keyword}. Entrega expressa. Satisfação garantida ou seu dinheiro de volta.",
    "{reviews}+ clientes satisfeitos. {keyword} original com garantia. Compra 100% segura.",
  ],
  comparison: [
    "Compare os melhores {keyword} do mercado. Análises detalhadas de especialistas.",
    "Guia completo de {keyword}: prós, contras e custo-benefício. Avaliações reais.",
  ],
  research: [
    "Aprenda tudo sobre {keyword}. Guia completo e atualizado. 100% gratuito.",
    "Descubra como {keyword} pode ajudar você. Tutorial passo a passo.",
  ],
};

const CTA_TEMPLATES = {
  purchase: ["Comprar Agora", "Ver Ofertas", "Garantir Desconto", "Adicionar ao Carrinho"],
  comparison: ["Ver Comparativo", "Ler Análises", "Comparar Preços"],
  research: ["Ler Mais", "Ver Guia", "Aprender Agora"],
};

const BULLET_TEMPLATES = {
  purchase: [
    "✓ {keyword} com garantia de 1 ano",
    "✓ Frete grátis acima de R$99",
    "✓ Parcele em até 12x sem juros",
    "✓ Entrega expressa em 3 dias",
    "✓ Satisfação garantida ou dinheiro de volta",
  ],
  comparison: [
    "✓ Comparativo atualizado 2024",
    "✓ Avaliações de especialistas",
    "✓ Prós e contras detalhados",
    "✓ Melhor opção para cada perfil",
  ],
  research: [
    "✓ Guia completo e atualizado",
    "✓ Explicações simples e diretas",
    "✓ Dicas de especialistas",
    "✓ Conteúdo 100% gratuito",
  ],
};

// =============================================================================
// INTENT DETECTION
// =============================================================================

const PURCHASE_SIGNALS = [
  'comprar', 'buy', 'preço', 'price', 'quanto custa', 'valor',
  'onde comprar', 'loja', 'shop', 'desconto', 'promoção', 'oferta'
];

const COMPARISON_SIGNALS = [
  'vs', 'versus', 'comparar', 'compare', 'diferença',
  'qual melhor', 'alternativa', 'review', 'avaliação'
];

const RESEARCH_SIGNALS = [
  'o que é', 'what is', 'como funciona', 'how does',
  'por que', 'guia', 'tutorial', 'tipos de'
];

const URGENCY_SIGNALS = {
  immediate: ['agora', 'now', 'hoje', 'today', 'urgente', 'já'],
  high: ['amanhã', 'tomorrow', 'esta semana', 'próximo', 'soon'],
};

function detectIntent(keyword: string): 'purchase' | 'comparison' | 'research' | 'navigation' {
  const kw = keyword.toLowerCase();
  
  for (const signal of PURCHASE_SIGNALS) {
    if (kw.includes(signal)) return 'purchase';
  }
  
  for (const signal of COMPARISON_SIGNALS) {
    if (kw.includes(signal)) return 'comparison';
  }
  
  for (const signal of RESEARCH_SIGNALS) {
    if (kw.includes(signal)) return 'research';
  }
  
  // Default to purchase for ads context
  return 'purchase';
}

function detectUrgency(keyword: string): 'low' | 'medium' | 'high' | 'immediate' {
  const kw = keyword.toLowerCase();
  
  for (const signal of URGENCY_SIGNALS.immediate) {
    if (kw.includes(signal)) return 'immediate';
  }
  
  for (const signal of URGENCY_SIGNALS.high) {
    if (kw.includes(signal)) return 'high';
  }
  
  return 'medium';
}

// =============================================================================
// CONTENT GENERATION
// =============================================================================

function generateContent(context: SearchContext): DynamicContent {
  const { keyword, intent, urgency } = context;
  
  // Select templates
  const headlineTemplates = HEADLINE_TEMPLATES[intent] || HEADLINE_TEMPLATES.purchase;
  const subheadlineTemplates = SUBHEADLINE_TEMPLATES[intent] || SUBHEADLINE_TEMPLATES.purchase;
  const ctaTemplates = CTA_TEMPLATES[intent] || CTA_TEMPLATES.purchase;
  const bulletTemplates = BULLET_TEMPLATES[intent] || BULLET_TEMPLATES.purchase;
  
  // Pick headline based on urgency
  let headlines: string[];
  if (intent === 'purchase') {
    headlines = urgency === 'immediate' || urgency === 'high' 
      ? headlineTemplates.urgency 
      : headlineTemplates.value;
  } else {
    headlines = headlineTemplates.default || [];
  }
  
  // Fill templates
  const fillTemplate = (template: string) => {
    return template
      .replace(/{keyword}/g, titleCase(keyword))
      .replace(/{discount}/g, '20')
      .replace(/{reviews}/g, '10.000')
      .replace(/{year}/g, new Date().getFullYear().toString());
  };
  
  const headline = fillTemplate(randomPick(headlines));
  const subheadline = fillTemplate(randomPick(subheadlineTemplates));
  const cta = randomPick(ctaTemplates);
  const bullets = bulletTemplates.slice(0, 4).map(fillTemplate);
  
  // Urgency text
  let urgencyText = '';
  if (intent === 'purchase' && (urgency === 'immediate' || urgency === 'high')) {
    const hours = Math.floor(Math.random() * 12) + 2;
    urgencyText = `⏰ Oferta expira em ${hours}h`;
  }
  
  // Social proof
  const socialProof = '★★★★★ 4.8/5 (10.000+ avaliações)';
  
  // Generate variant ID
  const variantId = generateVariantId(keyword, intent);
  
  return {
    headline,
    subheadline,
    cta_text: cta,
    bullets,
    urgency_text: urgencyText,
    social_proof: socialProof,
    meta_title: `${titleCase(keyword)} | ${headline.slice(0, 30)}`,
    meta_description: subheadline.slice(0, 150),
    variant_id: variantId,
  };
}

// =============================================================================
// HTML TRANSFORMATION
// =============================================================================

function generateInjectionScript(content: DynamicContent): string {
  return `
<script data-ssi-dynamic="true">
(function() {
  'use strict';
  
  var content = ${JSON.stringify(content)};
  
  function inject() {
    // Headline
    var h1 = document.querySelector('h1, .hero-headline, .main-title');
    if (h1) h1.textContent = content.headline;
    
    // Subheadline
    var sub = document.querySelector('.hero-subtitle, .subheadline, h2.subtitle, .hero p');
    if (sub) sub.textContent = content.subheadline;
    
    // CTA
    var ctas = document.querySelectorAll('.cta-button, .btn-primary, .btn-cta, button[type="submit"]');
    ctas.forEach(function(cta) {
      cta.textContent = content.cta_text;
    });
    
    // Bullets
    var bullets = document.querySelectorAll('.benefit, .bullet, .feature-item, ul.benefits li');
    bullets.forEach(function(el, i) {
      if (content.bullets[i]) {
        el.textContent = content.bullets[i];
      }
    });
    
    // Urgency
    if (content.urgency_text) {
      var urgency = document.querySelector('.urgency-banner, .countdown, .limited-offer');
      if (urgency) {
        urgency.textContent = content.urgency_text;
        urgency.style.display = 'block';
      }
    }
    
    // Social proof
    var proof = document.querySelector('.social-proof, .reviews-badge, .rating');
    if (proof) proof.textContent = content.social_proof;
    
    // Add tracking attributes
    document.body.setAttribute('data-ssi-variant', content.variant_id);
    
    // Dispatch event
    window.dispatchEvent(new CustomEvent('ssi:personalized', { detail: content }));
    
    console.log('[SSI Shadow] Page personalized:', content.variant_id);
  }
  
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', inject);
  } else {
    inject();
  }
})();
</script>
`;
}

function generateTrackingScript(content: DynamicContent, keyword: string): string {
  return `
<script data-ssi-tracking="true">
(function() {
  // Track variant view
  if (window.ssiShadow) {
    window.ssiShadow.track('dynamic_lp_view', {
      variant_id: '${content.variant_id}',
      keyword: '${keyword}',
      headline: '${content.headline.replace(/'/g, "\\'")}'
    });
  }
  
  // Track CTA clicks
  document.addEventListener('click', function(e) {
    var cta = e.target.closest('.cta-button, .btn-primary, button[type="submit"]');
    if (cta && window.ssiShadow) {
      window.ssiShadow.track('dynamic_lp_cta_click', {
        variant_id: '${content.variant_id}',
        keyword: '${keyword}',
        cta_text: cta.textContent
      });
    }
  });
})();
</script>
`;
}

class HTMLRewriter {
  private content: DynamicContent;
  private keyword: string;
  
  constructor(content: DynamicContent, keyword: string) {
    this.content = content;
    this.keyword = keyword;
  }
  
  transform(html: string): string {
    // Update title
    html = html.replace(
      /<title>.*?<\/title>/i,
      `<title>${this.content.meta_title}</title>`
    );
    
    // Update meta description
    html = html.replace(
      /<meta name="description" content=".*?">/i,
      `<meta name="description" content="${this.content.meta_description}">`
    );
    
    // Inject scripts before </body>
    const injectionScript = generateInjectionScript(this.content);
    const trackingScript = generateTrackingScript(this.content, this.keyword);
    
    html = html.replace(
      '</body>',
      `${injectionScript}\n${trackingScript}\n</body>`
    );
    
    return html;
  }
}

// =============================================================================
// MAIN WORKER
// =============================================================================

export default {
  async fetch(request: Request, env: any, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    
    // Check if dynamic personalization is enabled
    const enableDynamic = url.searchParams.get('ssi_dynamic') === '1' ||
                          url.searchParams.has('gclid') ||
                          url.searchParams.has('utm_source');
    
    if (!enableDynamic) {
      // Pass through to origin
      return fetch(request);
    }
    
    // Extract keyword from various sources
    let keyword = url.searchParams.get('keyword') ||
                  url.searchParams.get('utm_term') ||
                  url.searchParams.get('q') ||
                  '';
    
    // If no keyword, try to extract from path or referrer
    if (!keyword) {
      const referer = request.headers.get('Referer') || '';
      const refUrl = new URL(referer, url.origin);
      keyword = refUrl.searchParams.get('q') || '';
    }
    
    // Default keyword from path
    if (!keyword) {
      const pathParts = url.pathname.split('/').filter(Boolean);
      if (pathParts.length > 0) {
        keyword = pathParts[pathParts.length - 1].replace(/-/g, ' ');
      }
    }
    
    // If still no keyword, pass through
    if (!keyword) {
      return fetch(request);
    }
    
    // Detect intent and urgency
    const intent = detectIntent(keyword);
    const urgency = detectUrgency(keyword);
    
    // Get device type
    const ua = request.headers.get('User-Agent') || '';
    const device = /mobile/i.test(ua) ? 'mobile' : 'desktop';
    
    // Build context
    const context: SearchContext = {
      keyword,
      intent,
      urgency,
      device,
      trust_score: 0.5, // Would come from SSI Shadow cookie
    };
    
    // Generate dynamic content
    const content = generateContent(context);
    
    // Fetch original page
    const cleanUrl = new URL(url);
    cleanUrl.searchParams.delete('ssi_dynamic');
    cleanUrl.searchParams.delete('keyword');
    
    const response = await fetch(cleanUrl.toString(), {
      headers: request.headers,
    });
    
    if (!response.ok) {
      return response;
    }
    
    // Get HTML
    let html = await response.text();
    
    // Transform HTML
    const rewriter = new HTMLRewriter(content, keyword);
    html = rewriter.transform(html);
    
    // Return modified response
    return new Response(html, {
      status: 200,
      headers: {
        'Content-Type': 'text/html; charset=utf-8',
        'X-SSI-Variant': content.variant_id,
        'X-SSI-Keyword': keyword,
        'X-SSI-Intent': intent,
        'Cache-Control': 'private, no-cache',
      },
    });
  },
};

// =============================================================================
// UTILITIES
// =============================================================================

function randomPick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)];
}

function titleCase(str: string): string {
  return str.replace(/\w\S*/g, (txt) => 
    txt.charAt(0).toUpperCase() + txt.substr(1).toLowerCase()
  );
}

function generateVariantId(keyword: string, intent: string): string {
  const hash = simpleHash(`${keyword}:${intent}:${Date.now()}`);
  return hash.toString(16).slice(0, 8);
}

function simpleHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    const char = str.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash);
}
