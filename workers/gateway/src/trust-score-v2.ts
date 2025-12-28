/**
 * S.S.I. SHADOW — Trust Score Module v2
 * 
 * Melhorias:
 * - JA4 Fingerprinting (TLS signature analysis)
 * - Behavioral validation
 * - Canvas hash integration
 * - Probabilistic identity matching
 */

// =============================================================================
// TIPOS
// =============================================================================

export interface TrustSignals {
  // Request básico
  ip: string;
  ua: string;
  acceptLanguage: string;
  acceptEncoding: string;
  
  // TLS/JA4
  tlsVersion?: string;
  tlsCipher?: string;
  ja4Fingerprint?: string;
  
  // Cloudflare
  botScore?: number;  // Apenas Enterprise
  asn?: number;
  asnOrg?: string;
  country?: string;
  
  // Behavioral (do Ghost Script)
  canvasHash?: string;
  webglHash?: string;
  scrollDepth?: number;
  timeOnPage?: number;
  interactions?: number;
  
  // Histórico
  isReturning: boolean;
  previousSessions?: number;
  previousPurchases?: number;
}

export interface TrustResult {
  score: number;           // 0-1
  classification: 'verified' | 'standard' | 'suspicious' | 'blocked';
  signals: TrustBreakdown;
  recommendation: 'send_capi' | 'send_capi_low_value' | 'skip_capi' | 'block';
}

export interface TrustBreakdown {
  ja4: number;
  behavioral: number;
  fingerprint: number;
  network: number;
  history: number;
  penalties: string[];
  bonuses: string[];
}

// =============================================================================
// CONSTANTES
// =============================================================================

// ASNs de datacenters conhecidos (bots frequentes)
const DATACENTER_ASNS = new Set([
  14061,  // DigitalOcean
  16509,  // Amazon AWS
  15169,  // Google Cloud
  8075,   // Microsoft Azure
  13335,  // Cloudflare
  20473,  // Vultr
  14618,  // Amazon EC2
  396982, // Google Cloud
  45102,  // Alibaba
  16276,  // OVH
]);

// ASNs de proxies residenciais (suspeitos mas não bloqueados)
const RESIDENTIAL_PROXY_ASNS = new Set([
  // Bright Data, Oxylabs, etc - adicionar conforme identificados
]);

// User Agents de bots óbvios
const BOT_UA_PATTERNS = [
  /bot/i, /crawler/i, /spider/i, /scraper/i,
  /curl/i, /wget/i, /python/i, /java\//i,
  /go-http/i, /axios/i, /node-fetch/i,
  /headless/i, /phantom/i, /selenium/i, /puppeteer/i,
  /lighthouse/i, /pagespeed/i
];

// TLS Ciphers comuns de bibliotecas de automação
// Bots em Python/Go/Node geralmente usam ciphers diferentes de browsers
const SUSPICIOUS_TLS_CIPHERS = new Set([
  // Ciphers comuns de requests/urllib
  'TLS_AES_256_GCM_SHA384',  // Pode ser legítimo, mas raro em browsers
]);

// TLS Versions - browsers modernos usam TLS 1.3
const MODERN_TLS_VERSIONS = new Set(['TLSv1.3', '1.3', 'TLS 1.3']);

// =============================================================================
// JA4 FINGERPRINTING
// =============================================================================

/**
 * Gera JA4-like fingerprint baseado em sinais TLS disponíveis
 * 
 * JA4 real requer dados que só Enterprise tem,
 * mas podemos aproximar com tlsVersion + tlsCipher + headers
 */
export function generateJA4Fingerprint(signals: Partial<TrustSignals>, headers: Headers): string {
  const parts: string[] = [];
  
  // Protocol indicator
  const isHTTP2 = headers.get('x-http2') === '1' || 
                  headers.get(':method') !== undefined;
  parts.push(isHTTP2 ? 'h2' : 'h1');
  
  // TLS Version
  const tlsVersion = signals.tlsVersion || 'unknown';
  if (tlsVersion.includes('1.3')) {
    parts.push('13');
  } else if (tlsVersion.includes('1.2')) {
    parts.push('12');
  } else {
    parts.push('00');
  }
  
  // Cipher (primeiros 4 chars do hash)
  const cipher = signals.tlsCipher || 'unknown';
  const cipherHash = simpleHash(cipher).toString(16).slice(0, 4);
  parts.push(cipherHash);
  
  // Accept-Language presence (browsers reais sempre têm)
  parts.push(signals.acceptLanguage ? 'l' : 'n');
  
  // Accept-Encoding consistency
  const acceptEnc = signals.acceptEncoding || '';
  const hasBrotli = acceptEnc.includes('br');
  const hasGzip = acceptEnc.includes('gzip');
  parts.push(hasBrotli ? 'b' : (hasGzip ? 'g' : 'n'));
  
  return parts.join('_');
}

function simpleHash(str: string): number {
  let hash = 0;
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash) + str.charCodeAt(i);
    hash |= 0;
  }
  return Math.abs(hash);
}

// =============================================================================
// TRUST SCORE CALCULATION
// =============================================================================

export function calculateTrustScore(signals: TrustSignals, headers: Headers): TrustResult {
  const breakdown: TrustBreakdown = {
    ja4: 0,
    behavioral: 0,
    fingerprint: 0,
    network: 0,
    history: 0,
    penalties: [],
    bonuses: []
  };
  
  // =========================================================================
  // 1. JA4 / TLS Analysis (max 0.25)
  // =========================================================================
  
  let ja4Score = 0.25;
  
  // TLS Version
  if (signals.tlsVersion) {
    if (MODERN_TLS_VERSIONS.has(signals.tlsVersion)) {
      ja4Score += 0.05;
      breakdown.bonuses.push('TLS 1.3');
    } else if (signals.tlsVersion.includes('1.2')) {
      // OK, mas não ideal
    } else {
      ja4Score -= 0.15;
      breakdown.penalties.push('TLS outdated');
    }
  }
  
  // TLS Cipher
  if (signals.tlsCipher && SUSPICIOUS_TLS_CIPHERS.has(signals.tlsCipher)) {
    ja4Score -= 0.1;
    breakdown.penalties.push('Suspicious cipher');
  }
  
  // Consistency check: Chrome deve ter brotli
  const ua = signals.ua.toLowerCase();
  const isChrome = ua.includes('chrome') && !ua.includes('edge');
  const hasBrotli = signals.acceptEncoding?.includes('br');
  
  if (isChrome && !hasBrotli) {
    ja4Score -= 0.15;
    breakdown.penalties.push('Chrome without brotli');
  }
  
  breakdown.ja4 = Math.max(0, Math.min(0.3, ja4Score));
  
  // =========================================================================
  // 2. Behavioral Analysis (max 0.25)
  // =========================================================================
  
  let behavioralScore = 0.15;
  
  // Scroll depth (humanos scrollam)
  if (signals.scrollDepth !== undefined) {
    if (signals.scrollDepth > 50) {
      behavioralScore += 0.05;
      breakdown.bonuses.push('Good scroll');
    } else if (signals.scrollDepth === 0) {
      behavioralScore -= 0.1;
      breakdown.penalties.push('No scroll');
    }
  }
  
  // Time on page
  if (signals.timeOnPage !== undefined) {
    if (signals.timeOnPage > 30) {
      behavioralScore += 0.05;
      breakdown.bonuses.push('Time engaged');
    } else if (signals.timeOnPage < 2) {
      behavioralScore -= 0.1;
      breakdown.penalties.push('Bounce');
    }
  }
  
  // Interactions
  if (signals.interactions !== undefined && signals.interactions > 0) {
    behavioralScore += 0.05;
    breakdown.bonuses.push('Interactions');
  }
  
  breakdown.behavioral = Math.max(0, Math.min(0.25, behavioralScore));
  
  // =========================================================================
  // 3. Fingerprint Analysis (max 0.15)
  // =========================================================================
  
  let fingerprintScore = 0.1;
  
  if (signals.canvasHash) {
    fingerprintScore += 0.05;
    breakdown.bonuses.push('Canvas hash');
  }
  
  if (signals.webglHash) {
    fingerprintScore += 0.03;
    breakdown.bonuses.push('WebGL hash');
  }
  
  breakdown.fingerprint = Math.min(0.15, fingerprintScore);
  
  // =========================================================================
  // 4. Network Analysis (max 0.20)
  // =========================================================================
  
  let networkScore = 0.15;
  
  // ASN check
  if (signals.asn) {
    if (DATACENTER_ASNS.has(signals.asn)) {
      networkScore -= 0.2;
      breakdown.penalties.push(`Datacenter ASN: ${signals.asn}`);
    } else if (RESIDENTIAL_PROXY_ASNS.has(signals.asn)) {
      networkScore -= 0.1;
      breakdown.penalties.push('Residential proxy ASN');
    }
  }
  
  // Accept-Language (bots frequentemente omitem)
  if (!signals.acceptLanguage) {
    networkScore -= 0.05;
    breakdown.penalties.push('No Accept-Language');
  }
  
  // User-Agent patterns
  for (const pattern of BOT_UA_PATTERNS) {
    if (pattern.test(signals.ua)) {
      networkScore -= 0.3;
      breakdown.penalties.push(`Bot UA pattern: ${pattern.source}`);
      break;
    }
  }
  
  // Cloudflare bot score (se disponível - Enterprise)
  if (signals.botScore !== undefined) {
    if (signals.botScore < 30) {
      networkScore -= 0.2;
      breakdown.penalties.push(`CF bot score: ${signals.botScore}`);
    } else if (signals.botScore > 80) {
      networkScore += 0.05;
      breakdown.bonuses.push('CF verified human');
    }
  }
  
  breakdown.network = Math.max(-0.3, Math.min(0.2, networkScore));
  
  // =========================================================================
  // 5. History Analysis (max 0.15)
  // =========================================================================
  
  let historyScore = 0.05;
  
  if (signals.isReturning) {
    historyScore += 0.05;
    breakdown.bonuses.push('Returning visitor');
  }
  
  if (signals.previousPurchases && signals.previousPurchases > 0) {
    historyScore += 0.1;
    breakdown.bonuses.push('Previous customer');
  }
  
  if (signals.previousSessions && signals.previousSessions > 3) {
    historyScore += 0.03;
    breakdown.bonuses.push('Multiple sessions');
  }
  
  breakdown.history = Math.min(0.15, historyScore);
  
  // =========================================================================
  // FINAL CALCULATION
  // =========================================================================
  
  const totalScore = Math.max(0, Math.min(1,
    breakdown.ja4 +
    breakdown.behavioral +
    breakdown.fingerprint +
    breakdown.network +
    breakdown.history
  ));
  
  // Classification
  let classification: TrustResult['classification'];
  let recommendation: TrustResult['recommendation'];
  
  if (totalScore >= 0.7) {
    classification = 'verified';
    recommendation = 'send_capi';
  } else if (totalScore >= 0.5) {
    classification = 'standard';
    recommendation = 'send_capi';
  } else if (totalScore >= 0.3) {
    classification = 'suspicious';
    recommendation = 'send_capi_low_value';
  } else {
    classification = 'blocked';
    recommendation = 'skip_capi';
  }
  
  return {
    score: Math.round(totalScore * 1000) / 1000,
    classification,
    signals: breakdown,
    recommendation
  };
}

// =============================================================================
// IDENTITY MATCHING
// =============================================================================

export interface IdentityMatch {
  ssiId: string;
  confidence: number;
  matchMethod: 'exact_cookie' | 'canvas_hash' | 'webgl_hash' | 'probabilistic' | 'new';
  linkedIds: {
    fbp?: string[];
    fbc?: string[];
    canvasHashes?: string[];
  };
}

/**
 * Resolve identity usando múltiplos sinais
 * Prioridade: cookie > canvas_hash > webgl_hash > probabilistic
 */
export async function resolveIdentityProbabilistic(
  kv: KVNamespace,
  signals: {
    existingSsiId?: string;
    fbp?: string;
    fbc?: string;
    canvasHash?: string;
    webglHash?: string;
    ip?: string;
    ua?: string;
  }
): Promise<IdentityMatch> {
  
  // 1. Exact match por SSI ID existente
  if (signals.existingSsiId) {
    const exists = await kv.get(`identity:${signals.existingSsiId}`);
    if (exists) {
      return {
        ssiId: signals.existingSsiId,
        confidence: 1.0,
        matchMethod: 'exact_cookie',
        linkedIds: JSON.parse(exists).linkedIds || {}
      };
    }
  }
  
  // 2. Match por FBP
  if (signals.fbp) {
    const match = await kv.get(`fbp:${signals.fbp}`);
    if (match) {
      return {
        ssiId: match,
        confidence: 0.95,
        matchMethod: 'exact_cookie',
        linkedIds: {}
      };
    }
  }
  
  // 3. Match por FBC
  if (signals.fbc) {
    const match = await kv.get(`fbc:${signals.fbc}`);
    if (match) {
      return {
        ssiId: match,
        confidence: 0.95,
        matchMethod: 'exact_cookie',
        linkedIds: {}
      };
    }
  }
  
  // 4. Match por Canvas Hash (hardware fingerprint)
  if (signals.canvasHash) {
    const match = await kv.get(`canvas:${signals.canvasHash}`);
    if (match) {
      return {
        ssiId: match,
        confidence: 0.85,
        matchMethod: 'canvas_hash',
        linkedIds: {}
      };
    }
  }
  
  // 5. Match por WebGL Hash
  if (signals.webglHash) {
    const match = await kv.get(`webgl:${signals.webglHash}`);
    if (match) {
      return {
        ssiId: match,
        confidence: 0.80,
        matchMethod: 'webgl_hash',
        linkedIds: {}
      };
    }
  }
  
  // 6. Match probabilístico (IP + UA) - último recurso
  if (signals.ip && signals.ua) {
    const probKey = `prob:${simpleHash(signals.ip + signals.ua).toString(16)}`;
    const match = await kv.get(probKey);
    if (match) {
      const data = JSON.parse(match);
      // Só aceita se visto nas últimas 24h
      if (Date.now() - data.lastSeen < 24 * 60 * 60 * 1000) {
        return {
          ssiId: data.ssiId,
          confidence: 0.60,
          matchMethod: 'probabilistic',
          linkedIds: {}
        };
      }
    }
  }
  
  // 7. Novo visitante
  const newSsiId = crypto.randomUUID();
  
  return {
    ssiId: newSsiId,
    confidence: 0,
    matchMethod: 'new',
    linkedIds: {}
  };
}

/**
 * Persiste mappings de identity no KV
 */
export async function persistIdentityMappings(
  kv: KVNamespace,
  ssiId: string,
  signals: {
    fbp?: string;
    fbc?: string;
    canvasHash?: string;
    webglHash?: string;
    ip?: string;
    ua?: string;
  },
  ttlSeconds: number = 90 * 24 * 60 * 60 // 90 dias
): Promise<void> {
  const promises: Promise<void>[] = [];
  
  // Identity principal
  promises.push(
    kv.put(`identity:${ssiId}`, JSON.stringify({
      created: Date.now(),
      linkedIds: {
        fbp: signals.fbp ? [signals.fbp] : [],
        fbc: signals.fbc ? [signals.fbc] : [],
        canvasHashes: signals.canvasHash ? [signals.canvasHash] : [],
        webglHashes: signals.webglHash ? [signals.webglHash] : []
      }
    }), { expirationTtl: ttlSeconds })
  );
  
  // Indexes
  if (signals.fbp) {
    promises.push(kv.put(`fbp:${signals.fbp}`, ssiId, { expirationTtl: ttlSeconds }));
  }
  
  if (signals.fbc) {
    promises.push(kv.put(`fbc:${signals.fbc}`, ssiId, { expirationTtl: ttlSeconds }));
  }
  
  if (signals.canvasHash) {
    promises.push(kv.put(`canvas:${signals.canvasHash}`, ssiId, { expirationTtl: ttlSeconds }));
  }
  
  if (signals.webglHash) {
    promises.push(kv.put(`webgl:${signals.webglHash}`, ssiId, { expirationTtl: ttlSeconds }));
  }
  
  // Probabilistic (TTL curto - 24h)
  if (signals.ip && signals.ua) {
    const probKey = `prob:${simpleHash(signals.ip + signals.ua).toString(16)}`;
    promises.push(kv.put(probKey, JSON.stringify({
      ssiId,
      lastSeen: Date.now()
    }), { expirationTtl: 24 * 60 * 60 }));
  }
  
  await Promise.all(promises);
}

// =============================================================================
// EXPORT
// =============================================================================

export default {
  generateJA4Fingerprint,
  calculateTrustScore,
  resolveIdentityProbabilistic,
  persistIdentityMappings
};
