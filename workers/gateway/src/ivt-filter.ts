/**
 * S.S.I. SHADOW — Invalid Traffic Filter (IVT)
 * 
 * Objetivo: PROTEGER dados de tracking, não enganar plataformas
 * 
 * Benefícios legítimos:
 * - Reduz CPA ao filtrar cliques de bots
 * - Melhora aprendizado do pixel (dados limpos)
 * - Evita desperdício de budget com IVT
 * - Aumenta confiabilidade das métricas
 * 
 * NÃO é usado para:
 * - Detectar revisores de anúncios
 * - Servir conteúdo diferente
 * - Qualquer forma de cloaking
 */

// =============================================================================
// TIPOS
// =============================================================================

export interface IVTSignals {
  // Request
  ip: string;
  userAgent: string;
  acceptLanguage: string | null;
  acceptEncoding: string | null;
  
  // TLS
  tlsVersion: string | null;
  tlsCipher: string | null;
  
  // Cloudflare
  asn: number | null;
  asnOrg: string | null;
  country: string | null;
  botScore: number | null;  // Enterprise only
  
  // Behavioral (do Ghost Script)
  hasScrolled: boolean;
  hasClicked: boolean;
  hasMoved: boolean;
  timeOnPage: number;  // seconds
  scrollDepth: number;  // percentage
  
  // Fingerprint
  canvasHash: string | null;
  webglHash: string | null;
}

export interface IVTResult {
  isValid: boolean;
  category: 'human' | 'suspicious' | 'bot' | 'datacenter' | 'crawler';
  confidence: number;  // 0-1
  
  // Detalhes
  signals: IVTBreakdown;
  
  // Ação recomendada
  action: 'process' | 'process_low_priority' | 'skip' | 'block';
  
  // Para tracking
  ivtFlags: string[];
}

export interface IVTBreakdown {
  // Scores por categoria (0-1, maior = mais humano)
  networkScore: number;
  behavioralScore: number;
  consistencyScore: number;
  
  // Flags detectados
  flags: string[];
  
  // Bônus
  bonuses: string[];
}

// =============================================================================
// LISTAS DE CONHECIMENTO
// =============================================================================

// ASNs de datacenters (tráfego não-humano comum)
const DATACENTER_ASNS: Set<number> = new Set([
  // Cloud Providers
  14061,   // DigitalOcean
  16509,   // Amazon AWS
  15169,   // Google Cloud
  8075,    // Microsoft Azure
  13335,   // Cloudflare
  20473,   // Vultr
  14618,   // Amazon EC2
  396982,  // Google Cloud
  45102,   // Alibaba Cloud
  16276,   // OVH
  24940,   // Hetzner
  
  // VPN/Proxy conhecidos
  // (adicionar conforme identificados)
]);

// ASNs de crawlers legítimos (Google, Bing, etc)
const CRAWLER_ASNS: Set<number> = new Set([
  15169,   // Googlebot
  8075,    // Bingbot (Microsoft)
  // Meta não usa ASN específico para crawlers
]);

// Padrões de User-Agent de bots conhecidos
const BOT_UA_PATTERNS: RegExp[] = [
  // Crawlers de search engines (legítimos, mas não são clientes)
  /googlebot/i,
  /bingbot/i,
  /yandexbot/i,
  /baiduspider/i,
  /duckduckbot/i,
  
  // Ferramentas de automação
  /selenium/i,
  /puppeteer/i,
  /playwright/i,
  /phantomjs/i,
  /headless/i,
  
  // HTTP libraries
  /python-requests/i,
  /python-urllib/i,
  /go-http-client/i,
  /java\//i,
  /axios/i,
  /node-fetch/i,
  /curl/i,
  /wget/i,
  /libwww/i,
  /httpie/i,
  
  // Scrapers genéricos
  /scrapy/i,
  /crawl/i,
  /spider/i,
  /bot/i,
  
  // Ferramentas de SEO/monitoring
  /semrushbot/i,
  /ahrefsbot/i,
  /mj12bot/i,
  /dotbot/i,
  /petalbot/i,
  
  // Ferramentas de teste
  /lighthouse/i,
  /pagespeed/i,
  /gtmetrix/i,
];

// Padrões de UA de browsers legítimos
const BROWSER_UA_PATTERNS: RegExp[] = [
  /Mozilla\/5\.0.*Chrome\/\d+/i,
  /Mozilla\/5\.0.*Firefox\/\d+/i,
  /Mozilla\/5\.0.*Safari\/\d+/i,
  /Mozilla\/5\.0.*Edge\/\d+/i,
];

// =============================================================================
// IVT DETECTOR
// =============================================================================

export class IVTDetector {
  
  /**
   * Analisa tráfego e determina se é válido
   */
  analyze(signals: IVTSignals): IVTResult {
    const breakdown: IVTBreakdown = {
      networkScore: 0,
      behavioralScore: 0,
      consistencyScore: 0,
      flags: [],
      bonuses: []
    };
    
    // =========================================================================
    // 1. ANÁLISE DE REDE
    // =========================================================================
    
    let networkScore = 0.7;  // Default: assume ok
    
    // ASN de datacenter
    if (signals.asn && DATACENTER_ASNS.has(signals.asn)) {
      networkScore -= 0.5;
      breakdown.flags.push(`datacenter_asn:${signals.asn}`);
    }
    
    // ASN de crawler
    if (signals.asn && CRAWLER_ASNS.has(signals.asn)) {
      networkScore -= 0.3;
      breakdown.flags.push(`crawler_asn:${signals.asn}`);
    }
    
    // Accept-Language ausente (browsers sempre enviam)
    if (!signals.acceptLanguage) {
      networkScore -= 0.15;
      breakdown.flags.push('no_accept_language');
    }
    
    // Accept-Encoding inconsistente
    if (signals.acceptEncoding) {
      const hasBrotli = signals.acceptEncoding.includes('br');
      const isChrome = /Chrome\/\d+/.test(signals.userAgent);
      
      // Chrome moderno sempre suporta brotli
      if (isChrome && !hasBrotli) {
        networkScore -= 0.2;
        breakdown.flags.push('chrome_no_brotli');
      }
    }
    
    // TLS version antiga (bots frequentemente usam TLS 1.2)
    if (signals.tlsVersion && !['TLSv1.3', '1.3'].includes(signals.tlsVersion)) {
      networkScore -= 0.1;
      breakdown.flags.push('old_tls');
    }
    
    // Cloudflare Bot Score (se disponível)
    if (signals.botScore !== null) {
      if (signals.botScore < 30) {
        networkScore -= 0.4;
        breakdown.flags.push(`cf_bot_score:${signals.botScore}`);
      } else if (signals.botScore > 80) {
        networkScore += 0.2;
        breakdown.bonuses.push('cf_verified_human');
      }
    }
    
    breakdown.networkScore = Math.max(0, Math.min(1, networkScore));
    
    // =========================================================================
    // 2. ANÁLISE DE USER-AGENT
    // =========================================================================
    
    let uaScore = 0.5;
    
    // Check contra padrões de bot
    for (const pattern of BOT_UA_PATTERNS) {
      if (pattern.test(signals.userAgent)) {
        uaScore -= 0.6;
        breakdown.flags.push(`bot_ua:${pattern.source.slice(0, 20)}`);
        break;
      }
    }
    
    // Bônus se parece browser legítimo
    for (const pattern of BROWSER_UA_PATTERNS) {
      if (pattern.test(signals.userAgent)) {
        uaScore += 0.3;
        breakdown.bonuses.push('valid_browser_ua');
        break;
      }
    }
    
    // UA muito curto (bots frequentemente têm UA mínimo)
    if (signals.userAgent.length < 50) {
      uaScore -= 0.2;
      breakdown.flags.push('short_ua');
    }
    
    // =========================================================================
    // 3. ANÁLISE COMPORTAMENTAL
    // =========================================================================
    
    let behavioralScore = 0.3;  // Começa baixo, precisa provar humanidade
    
    // Scroll (humanos scrollam)
    if (signals.hasScrolled && signals.scrollDepth > 10) {
      behavioralScore += 0.25;
      breakdown.bonuses.push('has_scroll');
    }
    
    // Movimento de mouse
    if (signals.hasMoved) {
      behavioralScore += 0.15;
      breakdown.bonuses.push('has_mouse_movement');
    }
    
    // Clique
    if (signals.hasClicked) {
      behavioralScore += 0.2;
      breakdown.bonuses.push('has_click');
    }
    
    // Tempo na página
    if (signals.timeOnPage > 5) {
      behavioralScore += 0.1;
    }
    if (signals.timeOnPage > 30) {
      behavioralScore += 0.1;
      breakdown.bonuses.push('engaged_time');
    }
    
    // Scroll muito rápido (bot scroller)
    if (signals.scrollDepth > 90 && signals.timeOnPage < 3) {
      behavioralScore -= 0.3;
      breakdown.flags.push('fast_scroll');
    }
    
    // Nenhuma interação (suspeito)
    if (!signals.hasScrolled && !signals.hasMoved && !signals.hasClicked) {
      behavioralScore -= 0.2;
      breakdown.flags.push('no_interaction');
    }
    
    breakdown.behavioralScore = Math.max(0, Math.min(1, behavioralScore));
    
    // =========================================================================
    // 4. ANÁLISE DE CONSISTÊNCIA
    // =========================================================================
    
    let consistencyScore = 0.6;
    
    // Fingerprint presente (prova de JS execution)
    if (signals.canvasHash) {
      consistencyScore += 0.2;
      breakdown.bonuses.push('has_canvas');
    }
    
    if (signals.webglHash) {
      consistencyScore += 0.1;
      breakdown.bonuses.push('has_webgl');
    }
    
    // Sem fingerprint E sem comportamento = muito suspeito
    if (!signals.canvasHash && !signals.hasScrolled && !signals.hasMoved) {
      consistencyScore -= 0.3;
      breakdown.flags.push('no_js_evidence');
    }
    
    breakdown.consistencyScore = Math.max(0, Math.min(1, consistencyScore));
    
    // =========================================================================
    // CÁLCULO FINAL
    // =========================================================================
    
    // Média ponderada
    const totalScore = (
      breakdown.networkScore * 0.35 +
      uaScore * 0.25 +
      breakdown.behavioralScore * 0.25 +
      breakdown.consistencyScore * 0.15
    );
    
    // Determinar categoria
    let category: IVTResult['category'];
    let action: IVTResult['action'];
    
    if (breakdown.flags.includes('datacenter_asn') || 
        breakdown.flags.some(f => f.startsWith('bot_ua:'))) {
      // Bot ou datacenter claro
      if (breakdown.flags.includes('datacenter_asn')) {
        category = 'datacenter';
      } else if (breakdown.flags.some(f => f.includes('crawler') || f.includes('bot'))) {
        category = 'crawler';
      } else {
        category = 'bot';
      }
      action = 'skip';
    } else if (totalScore >= 0.7) {
      category = 'human';
      action = 'process';
    } else if (totalScore >= 0.4) {
      category = 'suspicious';
      action = 'process_low_priority';
    } else {
      category = 'bot';
      action = 'skip';
    }
    
    return {
      isValid: totalScore >= 0.4,
      category,
      confidence: Math.round(totalScore * 1000) / 1000,
      signals: breakdown,
      action,
      ivtFlags: breakdown.flags
    };
  }
  
  /**
   * Versão rápida para filtering inicial
   * Usa apenas sinais de request (sem behavioral)
   */
  quickCheck(signals: Pick<IVTSignals, 'ip' | 'userAgent' | 'asn' | 'acceptLanguage'>): boolean {
    // ASN de datacenter = provavelmente bot
    if (signals.asn && DATACENTER_ASNS.has(signals.asn)) {
      return false;
    }
    
    // UA de bot conhecido
    for (const pattern of BOT_UA_PATTERNS) {
      if (pattern.test(signals.userAgent)) {
        return false;
      }
    }
    
    // Sem Accept-Language = suspeito
    if (!signals.acceptLanguage) {
      return false;
    }
    
    return true;
  }
}

// =============================================================================
// HELPER: Construir signals a partir de Request
// =============================================================================

export function buildIVTSignals(
  request: Request,
  cfData: any,
  ghostData?: {
    hasScrolled?: boolean;
    hasClicked?: boolean;
    hasMoved?: boolean;
    timeOnPage?: number;
    scrollDepth?: number;
    canvasHash?: string;
    webglHash?: string;
  }
): IVTSignals {
  return {
    ip: request.headers.get('cf-connecting-ip') || '0.0.0.0',
    userAgent: request.headers.get('user-agent') || '',
    acceptLanguage: request.headers.get('accept-language'),
    acceptEncoding: request.headers.get('accept-encoding'),
    
    tlsVersion: cfData?.tlsVersion || null,
    tlsCipher: cfData?.tlsCipher || null,
    
    asn: cfData?.asn || null,
    asnOrg: cfData?.asOrganization || null,
    country: cfData?.country || null,
    botScore: cfData?.botManagement?.score || null,
    
    hasScrolled: ghostData?.hasScrolled || false,
    hasClicked: ghostData?.hasClicked || false,
    hasMoved: ghostData?.hasMoved || false,
    timeOnPage: ghostData?.timeOnPage || 0,
    scrollDepth: ghostData?.scrollDepth || 0,
    
    canvasHash: ghostData?.canvasHash || null,
    webglHash: ghostData?.webglHash || null
  };
}

// =============================================================================
// EXPORT
// =============================================================================

export const ivtDetector = new IVTDetector();

export default {
  IVTDetector,
  ivtDetector,
  buildIVTSignals,
  DATACENTER_ASNS,
  BOT_UA_PATTERNS
};
