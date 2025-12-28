/**
 * S.S.I. SHADOW — Gateway Worker v2
 * ENTERPRISE EDITION - FULL INTEGRATION
 * 
 * Integra todos os módulos:
 * - Trust Score v3 (IPQS + FingerprintJS)
 * - Cookie Manager (ITP bypass)
 * - IVT Filter
 * - Real-time ML Inference (ONNX)
 * - CAPI Multi-platform
 * - BigQuery Streaming
 * - Bid Optimization signals
 */

import { 
  TrustScoreV3Engine, 
  createTrustScoreV3,
  EnrichedSignals,
  TrustScoreV3Result 
} from './trust-score-v3';

import { 
  ServerSideCookieManager, 
  withCookieManagement,
  ExtractedCookies 
} from './cookie-manager';

import { 
  IVTDetector, 
  IVTSignals, 
  IVTResult 
} from './ivt-filter';

// =============================================================================
// TYPES
// =============================================================================

export interface Env {
  // KV Namespaces
  SSI_SESSIONS: KVNamespace;
  SSI_IDENTITIES: KVNamespace;
  SSI_CACHE: KVNamespace;
  SSI_MODELS: KVNamespace;
  
  // Secrets - Core
  META_PIXEL_ID: string;
  META_ACCESS_TOKEN: string;
  GOOGLE_MEASUREMENT_ID?: string;
  GOOGLE_API_SECRET?: string;
  TIKTOK_PIXEL_ID?: string;
  TIKTOK_ACCESS_TOKEN?: string;
  
  // Secrets - Enterprise
  IPQS_API_KEY?: string;
  FPJS_API_KEY?: string;
  FPJS_API_SECRET?: string;
  
  // Secrets - GCP
  GCP_PROJECT_ID: string;
  GCP_SERVICE_ACCOUNT_KEY?: string;
  
  // Config
  COOKIE_DOMAIN?: string;
  DEBUG?: string;
}

interface IncomingEvent {
  event_name: string;
  event_id?: string;
  timestamp?: number;
  
  // URL data
  url?: string;
  referrer?: string;
  
  // Click IDs
  fbclid?: string;
  gclid?: string;
  ttclid?: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  
  // Cookies
  fbp?: string;
  fbc?: string;
  ssi_id?: string;
  
  // Identity (from Ghost v4)
  visitor_id?: string;
  fp_confidence?: number;
  fp_method?: string;
  fp_request_id?: string;
  bot_probability?: number;
  
  // Fingerprints
  canvas_hash?: string;
  webgl_hash?: string;
  
  // PII (hashed on client)
  email_hash?: string;
  phone_hash?: string;
  
  // Behavioral
  scroll_depth?: number;
  time_on_page?: number;
  interactions?: number;
  is_hydrated?: boolean;
  biometric_score?: number;
  
  // Device
  screen?: { w: number; h: number };
  viewport?: { w: number; h: number };
  
  // Custom data
  custom_data?: Record<string, any>;
}

interface ProcessedEvent {
  // Original
  event_name: string;
  event_id: string;
  event_time: number;
  
  // Identity
  ssi_id: string;
  visitor_id?: string;
  identity_method: string;
  identity_confidence: number;
  
  // URL
  url: string;
  referrer?: string;
  
  // Attribution
  fbclid?: string;
  gclid?: string;
  ttclid?: string;
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  fbp?: string;
  fbc?: string;
  
  // Fingerprints
  canvas_hash?: string;
  webgl_hash?: string;
  
  // PII
  email_hash?: string;
  phone_hash?: string;
  
  // Device
  ip_hash: string;
  ua: string;
  device_type: string;
  browser: string;
  os: string;
  country: string;
  region?: string;
  city?: string;
  
  // Scores
  trust_score: number;
  trust_classification: string;
  intent_score: number;
  ltv_score: number;
  
  // Quality flags
  ivt_category: string;
  ivt_action: string;
  flags: string[];
  bonuses: string[];
  
  // Custom
  custom_data?: Record<string, any>;
  
  // Metadata
  processed_at: number;
  worker_version: string;
}

// =============================================================================
// CONSTANTS
// =============================================================================

const WORKER_VERSION = '2.0.0';
const CAPI_VERSION = 'v18.0';

// =============================================================================
// HELPERS
// =============================================================================

function generateEventId(): string {
  return `evt_${Date.now().toString(36)}_${Math.random().toString(36).substr(2, 9)}`;
}

function generateSSIId(): string {
  return `ssi_${Date.now().toString(36)}_${Math.random().toString(36).substr(2, 11)}`;
}

function hashIP(ip: string): string {
  // Simple hash for privacy
  let hash = 0;
  for (let i = 0; i < ip.length; i++) {
    const char = ip.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  return Math.abs(hash).toString(16);
}

function parseUserAgent(ua: string): { device: string; browser: string; os: string } {
  const device = /Mobile|Android|iPhone|iPad/i.test(ua) ? 'mobile' : 
                 /Tablet/i.test(ua) ? 'tablet' : 'desktop';
  
  let browser = 'unknown';
  if (/Chrome/i.test(ua) && !/Chromium|Edge/i.test(ua)) browser = 'chrome';
  else if (/Safari/i.test(ua) && !/Chrome/i.test(ua)) browser = 'safari';
  else if (/Firefox/i.test(ua)) browser = 'firefox';
  else if (/Edge/i.test(ua)) browser = 'edge';
  
  let os = 'unknown';
  if (/Windows/i.test(ua)) os = 'windows';
  else if (/Mac OS/i.test(ua)) os = 'macos';
  else if (/Linux/i.test(ua)) os = 'linux';
  else if (/Android/i.test(ua)) os = 'android';
  else if (/iOS|iPhone|iPad/i.test(ua)) os = 'ios';
  
  return { device, browser, os };
}

// =============================================================================
// ONNX INFERENCE (Real-time ML)
// =============================================================================

interface ONNXModel {
  predict(features: number[]): Promise<number>;
}

async function loadONNXModel(
  kv: KVNamespace, 
  modelName: string
): Promise<ONNXModel | null> {
  try {
    // Carregar modelo do KV
    const modelB64 = await kv.get(`model:${modelName}:onnx`);
    if (!modelB64) return null;
    
    // Em produção, usar onnxruntime-web
    // Por simplicidade, retornamos um mock que usa os coeficientes armazenados
    const metaStr = await kv.get(`model:${modelName}:meta`);
    const meta = metaStr ? JSON.parse(metaStr) : {};
    
    return {
      predict: async (features: number[]) => {
        // Simplified linear prediction
        // Em produção: usar onnxruntime-web para inferência real
        const weights = meta.feature_importance || {};
        const featureNames = meta.feature_names || [];
        
        let score = 0.5; // baseline
        features.forEach((val, idx) => {
          const name = featureNames[idx];
          const weight = weights[name] || 0.1;
          score += val * weight * 0.1;
        });
        
        return Math.max(0, Math.min(1, score));
      }
    };
  } catch (e) {
    console.error('Failed to load ONNX model:', e);
    return null;
  }
}

async function predictScores(
  env: Env,
  event: IncomingEvent,
  trustResult: TrustScoreV3Result
): Promise<{ intent_score: number; ltv_score: number }> {
  // Features para predição
  const features = [
    event.scroll_depth || 0,
    event.time_on_page || 0,
    event.interactions || 0,
    trustResult.score,
    event.biometric_score || 0.5,
    event.is_hydrated ? 1 : 0,
    event.fbclid ? 1 : 0,
    event.email_hash ? 1 : 0
  ];
  
  // Tentar carregar modelos
  const intentModel = await loadONNXModel(env.SSI_MODELS, 'intent');
  const ltvModel = await loadONNXModel(env.SSI_MODELS, 'ltv');
  
  let intent_score = 0.5;
  let ltv_score = 0.5;
  
  if (intentModel) {
    intent_score = await intentModel.predict(features);
  } else {
    // Fallback heuristic
    intent_score = (
      (event.scroll_depth || 0) * 0.003 +
      Math.min(1, (event.time_on_page || 0) / 60) * 0.3 +
      Math.min(1, (event.interactions || 0) / 5) * 0.2 +
      trustResult.score * 0.2 +
      (event.is_hydrated ? 0.1 : 0)
    );
  }
  
  if (ltvModel) {
    ltv_score = await ltvModel.predict(features);
  } else {
    // Fallback: intent * quality
    ltv_score = intent_score * trustResult.score;
  }
  
  return {
    intent_score: Math.max(0, Math.min(1, intent_score)),
    ltv_score: Math.max(0, Math.min(1, ltv_score))
  };
}

// =============================================================================
// IDENTITY RESOLUTION
// =============================================================================

interface IdentityRecord {
  ssi_id: string;
  visitor_ids: string[];
  fbp_ids: string[];
  fbc_ids: string[];
  canvas_hashes: string[];
  email_hashes: string[];
  phone_hashes: string[];
  first_seen: number;
  last_seen: number;
  event_count: number;
  total_value: number;
}

async function resolveIdentity(
  env: Env,
  event: IncomingEvent,
  cookies: ExtractedCookies,
  trustResult: TrustScoreV3Result
): Promise<{ ssi_id: string; is_new: boolean; record: IdentityRecord }> {
  
  // Prioridade de identificação:
  // 1. visitor_id do FingerprintJS Pro
  // 2. ssi_id do cookie
  // 3. email_hash
  // 4. canvas_hash + outros sinais
  // 5. Novo ID
  
  let lookupKey: string | null = null;
  let lookupType = 'new';
  
  // 1. FingerprintJS visitor_id
  if (trustResult.identity.visitorId && trustResult.identity.confidence >= 0.8) {
    lookupKey = `fpjs:${trustResult.identity.visitorId}`;
    lookupType = 'fpjs';
  }
  // 2. SSI ID do cookie
  else if (cookies.ssi_id) {
    lookupKey = `ssi:${cookies.ssi_id}`;
    lookupType = 'cookie';
  }
  // 3. Email hash
  else if (event.email_hash) {
    lookupKey = `email:${event.email_hash}`;
    lookupType = 'email';
  }
  // 4. Canvas hash
  else if (event.canvas_hash) {
    lookupKey = `canvas:${event.canvas_hash}`;
    lookupType = 'canvas';
  }
  
  // Buscar registro existente
  let record: IdentityRecord | null = null;
  let ssi_id: string;
  let is_new = false;
  
  if (lookupKey) {
    const existing = await env.SSI_IDENTITIES.get(lookupKey);
    if (existing) {
      record = JSON.parse(existing);
      ssi_id = record.ssi_id;
    }
  }
  
  // Criar novo se não encontrado
  if (!record) {
    ssi_id = cookies.ssi_id || generateSSIId();
    is_new = true;
    
    record = {
      ssi_id,
      visitor_ids: [],
      fbp_ids: [],
      fbc_ids: [],
      canvas_hashes: [],
      email_hashes: [],
      phone_hashes: [],
      first_seen: Date.now(),
      last_seen: Date.now(),
      event_count: 0,
      total_value: 0
    };
  }
  
  // Atualizar registro
  record.last_seen = Date.now();
  record.event_count++;
  
  // Adicionar novos identificadores
  if (trustResult.identity.visitorId && !record.visitor_ids.includes(trustResult.identity.visitorId)) {
    record.visitor_ids.push(trustResult.identity.visitorId);
  }
  if (cookies.fbp && !record.fbp_ids.includes(cookies.fbp)) {
    record.fbp_ids.push(cookies.fbp);
  }
  if (cookies.fbc && !record.fbc_ids.includes(cookies.fbc)) {
    record.fbc_ids.push(cookies.fbc);
  }
  if (event.canvas_hash && !record.canvas_hashes.includes(event.canvas_hash)) {
    record.canvas_hashes.push(event.canvas_hash);
  }
  if (event.email_hash && !record.email_hashes.includes(event.email_hash)) {
    record.email_hashes.push(event.email_hash);
  }
  if (event.phone_hash && !record.phone_hashes.includes(event.phone_hash)) {
    record.phone_hashes.push(event.phone_hash);
  }
  
  // Atualizar valor total se for Purchase
  if (event.event_name === 'Purchase' && event.custom_data?.value) {
    record.total_value += parseFloat(event.custom_data.value) || 0;
  }
  
  // Salvar registro
  const recordJson = JSON.stringify(record);
  
  // Salvar em todos os índices
  await env.SSI_IDENTITIES.put(`ssi:${ssi_id}`, recordJson, { expirationTtl: 365 * 24 * 60 * 60 });
  
  if (trustResult.identity.visitorId) {
    await env.SSI_IDENTITIES.put(`fpjs:${trustResult.identity.visitorId}`, recordJson, { expirationTtl: 365 * 24 * 60 * 60 });
  }
  if (event.email_hash) {
    await env.SSI_IDENTITIES.put(`email:${event.email_hash}`, recordJson, { expirationTtl: 365 * 24 * 60 * 60 });
  }
  if (event.canvas_hash) {
    await env.SSI_IDENTITIES.put(`canvas:${event.canvas_hash}`, recordJson, { expirationTtl: 90 * 24 * 60 * 60 });
  }
  
  return { ssi_id, is_new, record };
}

// =============================================================================
// CAPI SENDERS
// =============================================================================

async function sendToMetaCAPI(
  env: Env,
  event: ProcessedEvent,
  request: Request
): Promise<{ success: boolean; response?: any; error?: string }> {
  if (!env.META_PIXEL_ID || !env.META_ACCESS_TOKEN) {
    return { success: false, error: 'Meta credentials not configured' };
  }
  
  // Não enviar se IVT
  if (event.ivt_action === 'block' || event.ivt_action === 'skip') {
    return { success: false, error: `Skipped due to IVT: ${event.ivt_category}` };
  }
  
  const payload = {
    data: [{
      event_name: event.event_name,
      event_time: Math.floor(event.event_time / 1000),
      event_id: event.event_id,
      event_source_url: event.url,
      action_source: 'website',
      
      user_data: {
        client_ip_address: request.headers.get('CF-Connecting-IP'),
        client_user_agent: event.ua,
        fbc: event.fbc || undefined,
        fbp: event.fbp || undefined,
        em: event.email_hash ? [event.email_hash] : undefined,
        ph: event.phone_hash ? [event.phone_hash] : undefined,
        external_id: [event.ssi_id],
        country: event.country ? [event.country.toLowerCase()] : undefined
      },
      
      custom_data: {
        ...event.custom_data,
        ssi_trust_score: event.trust_score,
        ssi_intent_score: event.intent_score,
        ssi_ltv_score: event.ltv_score
      }
    }],
    
    // Test event code (remover em produção)
    // test_event_code: 'TEST12345'
  };
  
  // Remover campos undefined
  payload.data[0].user_data = Object.fromEntries(
    Object.entries(payload.data[0].user_data).filter(([_, v]) => v !== undefined)
  );
  
  try {
    const response = await fetch(
      `https://graph.facebook.com/${CAPI_VERSION}/${env.META_PIXEL_ID}/events?access_token=${env.META_ACCESS_TOKEN}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }
    );
    
    const result = await response.json();
    
    return {
      success: response.ok,
      response: result
    };
    
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

async function sendToGoogleEC(
  env: Env,
  event: ProcessedEvent
): Promise<{ success: boolean; error?: string }> {
  if (!env.GOOGLE_MEASUREMENT_ID || !env.GOOGLE_API_SECRET) {
    return { success: false, error: 'Google credentials not configured' };
  }
  
  // Map event names
  const eventNameMap: Record<string, string> = {
    'PageView': 'page_view',
    'ViewContent': 'view_item',
    'AddToCart': 'add_to_cart',
    'InitiateCheckout': 'begin_checkout',
    'Purchase': 'purchase',
    'Lead': 'generate_lead'
  };
  
  const gaEventName = eventNameMap[event.event_name] || event.event_name.toLowerCase();
  
  const payload = {
    client_id: event.ssi_id,
    events: [{
      name: gaEventName,
      params: {
        session_id: event.ssi_id,
        engagement_time_msec: (event.custom_data?.time_on_page || 0) * 1000,
        ...event.custom_data
      }
    }]
  };
  
  try {
    const response = await fetch(
      `https://www.google-analytics.com/mp/collect?measurement_id=${env.GOOGLE_MEASUREMENT_ID}&api_secret=${env.GOOGLE_API_SECRET}`,
      {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      }
    );
    
    return { success: response.ok };
    
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

async function sendToTikTokEvents(
  env: Env,
  event: ProcessedEvent,
  request: Request
): Promise<{ success: boolean; error?: string }> {
  if (!env.TIKTOK_PIXEL_ID || !env.TIKTOK_ACCESS_TOKEN) {
    return { success: false, error: 'TikTok credentials not configured' };
  }
  
  const eventNameMap: Record<string, string> = {
    'PageView': 'ViewContent',
    'ViewContent': 'ViewContent',
    'AddToCart': 'AddToCart',
    'InitiateCheckout': 'InitiateCheckout',
    'Purchase': 'CompletePayment',
    'Lead': 'SubmitForm'
  };
  
  const payload = {
    pixel_code: env.TIKTOK_PIXEL_ID,
    event: eventNameMap[event.event_name] || event.event_name,
    event_id: event.event_id,
    timestamp: new Date(event.event_time).toISOString(),
    context: {
      user_agent: event.ua,
      ip: request.headers.get('CF-Connecting-IP')
    },
    properties: {
      ...event.custom_data
    }
  };
  
  if (event.ttclid) {
    payload.context['ad'] = { callback: event.ttclid };
  }
  
  try {
    const response = await fetch(
      'https://business-api.tiktok.com/open_api/v1.3/pixel/track/',
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Access-Token': env.TIKTOK_ACCESS_TOKEN
        },
        body: JSON.stringify(payload)
      }
    );
    
    return { success: response.ok };
    
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

// =============================================================================
// BIGQUERY STREAMING
// =============================================================================

async function streamToBigQuery(
  env: Env,
  event: ProcessedEvent
): Promise<{ success: boolean; error?: string }> {
  if (!env.GCP_PROJECT_ID) {
    return { success: false, error: 'GCP not configured' };
  }
  
  // Em produção, usar Google Auth Library
  // Por simplicidade, assumimos que o Worker tem acesso via service account
  
  const row = {
    insertId: event.event_id,
    json: {
      event_id: event.event_id,
      event_name: event.event_name,
      event_time: new Date(event.event_time).toISOString(),
      ssi_id: event.ssi_id,
      visitor_id: event.visitor_id,
      url: event.url,
      referrer: event.referrer,
      fbclid: event.fbclid,
      gclid: event.gclid,
      ttclid: event.ttclid,
      utm_source: event.utm_source,
      utm_medium: event.utm_medium,
      utm_campaign: event.utm_campaign,
      fbp: event.fbp,
      fbc: event.fbc,
      ip_hash: event.ip_hash,
      ua: event.ua,
      device_type: event.device_type,
      browser: event.browser,
      os: event.os,
      country: event.country,
      region: event.region,
      city: event.city,
      canvas_hash: event.canvas_hash,
      webgl_hash: event.webgl_hash,
      email_hash: event.email_hash,
      phone_hash: event.phone_hash,
      trust_score: event.trust_score,
      intent_score: event.intent_score,
      ltv_score: event.ltv_score,
      custom_data: JSON.stringify(event.custom_data),
      processed_at: new Date(event.processed_at).toISOString()
    }
  };
  
  try {
    // BigQuery streaming insert
    const response = await fetch(
      `https://bigquery.googleapis.com/bigquery/v2/projects/${env.GCP_PROJECT_ID}/datasets/ssi_shadow/tables/events/insertAll`,
      {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          // Em produção: adicionar Authorization header com JWT
        },
        body: JSON.stringify({ rows: [row] })
      }
    );
    
    return { success: response.ok };
    
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

// =============================================================================
// MAIN HANDLER
// =============================================================================

async function handleIngest(
  request: Request,
  env: Env,
  ctx: ExecutionContext
): Promise<Response> {
  const startTime = Date.now();
  
  try {
    // Parse body
    const event: IncomingEvent = await request.json();
    
    // Get Cloudflare data
    const cf = request.cf || {};
    const ip = request.headers.get('CF-Connecting-IP') || '';
    const ua = request.headers.get('User-Agent') || '';
    const { device, browser, os } = parseUserAgent(ua);
    
    // 1. Cookie Management
    const cookieManager = new ServerSideCookieManager(env.COOKIE_DOMAIN || new URL(request.url).hostname);
    const { cookies, setCookieHeaders, isNew: isNewVisitor } = cookieManager.processRequest(request);
    
    // 2. Build enriched signals
    const signals: EnrichedSignals = {
      ip,
      userAgent: ua,
      visitorId: event.visitor_id,
      fpConfidence: event.fp_confidence,
      fpMethod: event.fp_method,
      fpRequestId: event.fp_request_id,
      botProbability: event.bot_probability,
      biometricScore: event.biometric_score,
      canvasHash: event.canvas_hash,
      webglHash: event.webgl_hash,
      scrollDepth: event.scroll_depth,
      timeOnPage: event.time_on_page,
      interactions: event.interactions,
      isHydrated: event.is_hydrated,
      country: cf.country as string,
      asn: cf.asn as number,
      tlsVersion: cf.tlsVersion as string
    };
    
    // 3. Trust Score v3 (IPQS + FingerprintJS)
    const trustEngine = createTrustScoreV3({
      IPQS_API_KEY: env.IPQS_API_KEY,
      FPJS_API_KEY: env.FPJS_API_KEY,
      FPJS_API_SECRET: env.FPJS_API_SECRET
    });
    
    const trustResult = await trustEngine.calculateTrustScore(signals);
    
    // 4. IVT Filter
    const ivtDetector = new IVTDetector();
    const ivtSignals: IVTSignals = {
      ip,
      asn: cf.asn as number,
      asnOrg: cf.asOrganization as string,
      userAgent: ua,
      acceptLanguage: request.headers.get('Accept-Language'),
      acceptEncoding: request.headers.get('Accept-Encoding'),
      tlsVersion: cf.tlsVersion as string,
      cfBotScore: cf.botManagement?.score as number,
      scrollDepth: event.scroll_depth,
      mouseMovement: (event.interactions || 0) > 0,
      clicks: event.is_hydrated,
      timeOnPage: event.time_on_page,
      canvasHash: event.canvas_hash,
      webglHash: event.webgl_hash
    };
    
    const ivtResult = ivtDetector.analyze(ivtSignals);
    
    // 5. Identity Resolution
    const { ssi_id, is_new, record } = await resolveIdentity(
      env, 
      event, 
      cookies, 
      trustResult
    );
    
    // 6. ML Predictions
    const { intent_score, ltv_score } = await predictScores(env, event, trustResult);
    
    // 7. Build processed event
    const processedEvent: ProcessedEvent = {
      event_name: event.event_name,
      event_id: event.event_id || generateEventId(),
      event_time: event.timestamp || Date.now(),
      
      ssi_id,
      visitor_id: trustResult.identity.visitorId,
      identity_method: trustResult.identity.method,
      identity_confidence: trustResult.identity.confidence,
      
      url: event.url || '',
      referrer: event.referrer,
      
      fbclid: event.fbclid || cookies.fbclid,
      gclid: event.gclid || cookies.gclid,
      ttclid: event.ttclid || cookies.ttclid,
      utm_source: event.utm_source,
      utm_medium: event.utm_medium,
      utm_campaign: event.utm_campaign,
      fbp: event.fbp || cookies.fbp,
      fbc: event.fbc || cookies.fbc,
      
      canvas_hash: event.canvas_hash,
      webgl_hash: event.webgl_hash,
      email_hash: event.email_hash,
      phone_hash: event.phone_hash,
      
      ip_hash: hashIP(ip),
      ua,
      device_type: device,
      browser,
      os,
      country: cf.country as string || '',
      region: cf.region as string,
      city: cf.city as string,
      
      trust_score: trustResult.score,
      trust_classification: trustResult.classification,
      intent_score,
      ltv_score,
      
      ivt_category: ivtResult.category,
      ivt_action: ivtResult.action,
      flags: trustResult.flags,
      bonuses: trustResult.bonuses,
      
      custom_data: event.custom_data,
      
      processed_at: Date.now(),
      worker_version: WORKER_VERSION
    };
    
    // 8. Send to platforms (parallel)
    const sendPromises: Promise<any>[] = [];
    
    // Meta CAPI
    if (trustResult.action !== 'block') {
      sendPromises.push(
        sendToMetaCAPI(env, processedEvent, request)
          .then(r => ({ platform: 'meta', ...r }))
      );
    }
    
    // Google EC
    if (env.GOOGLE_MEASUREMENT_ID) {
      sendPromises.push(
        sendToGoogleEC(env, processedEvent)
          .then(r => ({ platform: 'google', ...r }))
      );
    }
    
    // TikTok Events
    if (env.TIKTOK_PIXEL_ID && event.ttclid) {
      sendPromises.push(
        sendToTikTokEvents(env, processedEvent, request)
          .then(r => ({ platform: 'tiktok', ...r }))
      );
    }
    
    // BigQuery (sempre, para analytics)
    sendPromises.push(
      streamToBigQuery(env, processedEvent)
        .then(r => ({ platform: 'bigquery', ...r }))
    );
    
    // Wait for all sends (with waitUntil for non-blocking)
    const sendResults = await Promise.allSettled(sendPromises);
    
    // 9. Build response
    const response = new Response(JSON.stringify({
      success: true,
      event_id: processedEvent.event_id,
      ssi_id,
      scores: {
        trust: processedEvent.trust_score,
        intent: processedEvent.intent_score,
        ltv: processedEvent.ltv_score
      },
      classification: trustResult.classification,
      processing_time_ms: Date.now() - startTime,
      debug: env.DEBUG === 'true' ? {
        identity: trustResult.identity,
        ivt: ivtResult,
        flags: trustResult.flags,
        bonuses: trustResult.bonuses,
        sends: sendResults.map((r, i) => ({
          ...(r.status === 'fulfilled' ? r.value : { error: r.reason })
        }))
      } : undefined
    }), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });
    
    // Apply cookies
    return cookieManager.applyToResponse(response, setCookieHeaders);
    
  } catch (error) {
    console.error('Ingest error:', error);
    
    return new Response(JSON.stringify({
      success: false,
      error: 'Internal error',
      processing_time_ms: Date.now() - startTime
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

// =============================================================================
// GHOST SCRIPT SERVER
// =============================================================================

async function handleGhostScript(env: Env): Promise<Response> {
  // Serve Ghost Script v4
  // Em produção, servir do KV ou R2
  
  const script = `
// Ghost Script v4 - Enterprise Edition
// Loaded from: ${env.COOKIE_DOMAIN || 'ssi worker'}
(function(w,d){
  // [Script content seria carregado do KV em produção]
  console.log('[SSI] Ghost v4 loaded');
})(window,document);
  `.trim();
  
  return new Response(script, {
    headers: {
      'Content-Type': 'application/javascript',
      'Cache-Control': 'public, max-age=3600'
    }
  });
}

// =============================================================================
// HEALTH CHECK
// =============================================================================

async function handleHealth(env: Env): Promise<Response> {
  const health = {
    status: 'healthy',
    version: WORKER_VERSION,
    timestamp: new Date().toISOString(),
    checks: {
      kv_sessions: false,
      kv_identities: false,
      meta_capi: !!env.META_PIXEL_ID,
      google_ec: !!env.GOOGLE_MEASUREMENT_ID,
      ipqs: !!env.IPQS_API_KEY,
      fpjs: !!env.FPJS_API_KEY
    }
  };
  
  // Test KV
  try {
    await env.SSI_SESSIONS.put('health_check', Date.now().toString());
    health.checks.kv_sessions = true;
  } catch {}
  
  try {
    await env.SSI_IDENTITIES.put('health_check', Date.now().toString());
    health.checks.kv_identities = true;
  } catch {}
  
  return new Response(JSON.stringify(health, null, 2), {
    headers: { 'Content-Type': 'application/json' }
  });
}

// =============================================================================
// ROUTER
// =============================================================================

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    
    // CORS
    if (request.method === 'OPTIONS') {
      return new Response(null, {
        headers: {
          'Access-Control-Allow-Origin': '*',
          'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
          'Access-Control-Allow-Headers': 'Content-Type',
          'Access-Control-Max-Age': '86400'
        }
      });
    }
    
    // Routes
    if (url.pathname === '/ingest' && request.method === 'POST') {
      return handleIngest(request, env, ctx);
    }
    
    if (url.pathname === '/ghost.js' || url.pathname === '/ghost-v4.js') {
      return handleGhostScript(env);
    }
    
    if (url.pathname === '/health') {
      return handleHealth(env);
    }
    
    // 404
    return new Response('Not Found', { status: 404 });
  }
};
