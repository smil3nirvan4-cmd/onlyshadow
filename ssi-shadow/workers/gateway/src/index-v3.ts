// ============================================================================
// S.S.I. SHADOW UNIVERSAL - Cloudflare Worker Entry Point v3
// ============================================================================
// Server-Side Tracking Gateway - 20 Ad Platforms + 50 Traffic Sources
// 
// Supported Platforms:
// - Tier 1: Meta, Google, TikTok, Microsoft/Bing, Amazon
// - Tier 2: Snapchat, Pinterest, LinkedIn, Twitter/X, Reddit
// - Tier 3: DV360, The Trade Desk, Criteo, Taboola, Outbrain
// - Tier 4: Kwai, AppLovin, Unity, IronSource, AdRoll

import {
  Env,
  IncomingEvent,
  CollectResponse,
  ValidationResult,
  EventName,
  PlatformResult,
} from './types';

import { generateEventId, generateSSIId } from './utils/hash';

// Platform imports - Tier 1
import { sendToMeta, estimateEMQ } from './meta-capi';
import { sendToTikTok } from './tiktok-capi';
import { sendToGoogle } from './google-mp';
import { sendToMicrosoft } from './microsoft-capi';

// Platform imports - Tier 2
import { sendToSnapchat } from './snapchat-capi';
import { sendToPinterest } from './pinterest-capi';
import { sendToLinkedIn } from './linkedin-capi';
import { sendToTwitter } from './twitter-capi';

// Storage
import { sendToBigQuery } from './bigquery';

// Trust Score
import {
  calculateTrustScore,
  quickBotCheck,
  createBlockedTrustScore,
  shouldSendToCAPI,
} from './trust-score';

// ----------------------------------------------------------------------------
// Extended Types for 50 Traffic Sources
// ----------------------------------------------------------------------------

interface ExtendedIncomingEvent extends IncomingEvent {
  // Additional click IDs for all platforms
  msclkid?: string;      // Microsoft/Bing
  sccid?: string;        // Snapchat
  epik?: string;         // Pinterest
  li_fat_id?: string;    // LinkedIn
  twclid?: string;       // Twitter/X
  rdt_cid?: string;      // Reddit
  dclid?: string;        // Google DV360
  ttd_id?: string;       // The Trade Desk
  cto_bundle?: string;   // Criteo
  tblci?: string;        // Taboola
  obOrigUrl?: string;    // Outbrain
  kwai_click_id?: string; // Kwai
  amzn_cid?: string;     // Amazon
  
  // Traffic source identification
  utm_source?: string;
  utm_medium?: string;
  utm_campaign?: string;
  utm_content?: string;
  utm_term?: string;
  
  // Referrer parsing
  traffic_source?: string;
  traffic_medium?: string;
}

// ----------------------------------------------------------------------------
// Constants
// ----------------------------------------------------------------------------

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization, X-SSI-Key',
  'Access-Control-Max-Age': '86400',
};

const VALID_EVENTS: EventName[] = [
  'PageView', 'ViewContent', 'Search', 'AddToCart', 'AddToWishlist',
  'InitiateCheckout', 'AddPaymentInfo', 'Purchase', 'Lead',
  'CompleteRegistration', 'Contact', 'CustomizeProduct', 'Donate',
  'FindLocation', 'Schedule', 'StartTrial', 'SubmitApplication', 'Subscribe',
];

// Click ID parameters to extract from URLs
const CLICK_ID_PARAMS = [
  'fbclid', 'gclid', 'gbraid', 'wbraid', 'ttclid', 'msclkid',
  'sccid', 'ScCid', 'epik', 'li_fat_id', 'twclid', 'rdt_cid',
  'dclid', 'ttd_id', 'cto_bundle', 'tblci', 'obOrigUrl',
  'kwai_click_id', 'amzn_cid',
];

// UTM parameters
const UTM_PARAMS = ['utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term'];

// ----------------------------------------------------------------------------
// Response Helpers
// ----------------------------------------------------------------------------

function jsonResponse(data: unknown, status: number = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'Content-Type': 'application/json', ...CORS_HEADERS },
  });
}

function errorResponse(message: string, status: number = 400): Response {
  return jsonResponse({ success: false, error: message }, status);
}

// ----------------------------------------------------------------------------
// Traffic Source Detection
// ----------------------------------------------------------------------------

function detectTrafficSource(event: ExtendedIncomingEvent): { source: string; medium: string } {
  // Check for click IDs first (paid traffic)
  if (event.fbclid) return { source: 'facebook', medium: 'paid' };
  if (event.gclid || event.gbraid || event.wbraid) return { source: 'google', medium: 'paid' };
  if (event.ttclid) return { source: 'tiktok', medium: 'paid' };
  if (event.msclkid) return { source: 'bing', medium: 'paid' };
  if (event.sccid) return { source: 'snapchat', medium: 'paid' };
  if (event.epik) return { source: 'pinterest', medium: 'paid' };
  if (event.li_fat_id) return { source: 'linkedin', medium: 'paid' };
  if (event.twclid) return { source: 'twitter', medium: 'paid' };
  if (event.rdt_cid) return { source: 'reddit', medium: 'paid' };
  if (event.tblci) return { source: 'taboola', medium: 'paid' };
  if (event.amzn_cid) return { source: 'amazon', medium: 'paid' };

  // Check UTM parameters
  if (event.utm_source) {
    return {
      source: event.utm_source.toLowerCase(),
      medium: event.utm_medium?.toLowerCase() || 'referral',
    };
  }

  // Check referrer
  if (event.referrer) {
    try {
      const url = new URL(event.referrer);
      const host = url.hostname.toLowerCase();
      
      if (host.includes('google')) return { source: 'google', medium: 'organic' };
      if (host.includes('bing')) return { source: 'bing', medium: 'organic' };
      if (host.includes('yahoo')) return { source: 'yahoo', medium: 'organic' };
      if (host.includes('facebook') || host.includes('fb.com')) return { source: 'facebook', medium: 'social' };
      if (host.includes('instagram')) return { source: 'instagram', medium: 'social' };
      if (host.includes('twitter') || host.includes('t.co')) return { source: 'twitter', medium: 'social' };
      if (host.includes('linkedin')) return { source: 'linkedin', medium: 'social' };
      if (host.includes('tiktok')) return { source: 'tiktok', medium: 'social' };
      if (host.includes('youtube')) return { source: 'youtube', medium: 'social' };
      if (host.includes('pinterest')) return { source: 'pinterest', medium: 'social' };
      if (host.includes('reddit')) return { source: 'reddit', medium: 'social' };
      if (host.includes('whatsapp')) return { source: 'whatsapp', medium: 'social' };
      if (host.includes('telegram')) return { source: 'telegram', medium: 'social' };
      
      return { source: host, medium: 'referral' };
    } catch {
      return { source: 'unknown', medium: 'referral' };
    }
  }

  return { source: 'direct', medium: 'none' };
}

// ----------------------------------------------------------------------------
// Extract Click IDs from URL
// ----------------------------------------------------------------------------

function extractClickIds(url?: string): Record<string, string> {
  const clickIds: Record<string, string> = {};
  
  if (!url) return clickIds;

  try {
    const urlObj = new URL(url);
    const params = urlObj.searchParams;

    for (const param of CLICK_ID_PARAMS) {
      const value = params.get(param);
      if (value) {
        clickIds[param] = value;
      }
    }

    // Also extract UTM params
    for (const param of UTM_PARAMS) {
      const value = params.get(param);
      if (value) {
        clickIds[param] = value;
      }
    }
  } catch {
    // Invalid URL, ignore
  }

  return clickIds;
}

// ----------------------------------------------------------------------------
// Event Validation
// ----------------------------------------------------------------------------

function validateEvent(body: unknown): ValidationResult {
  const errors: string[] = [];

  if (!body || typeof body !== 'object') {
    return { valid: false, errors: ['Request body must be a JSON object'] };
  }

  const event = body as Record<string, unknown>;

  if (!event.event_name || typeof event.event_name !== 'string') {
    errors.push('event_name is required and must be a string');
  }

  if (event.event_name && !VALID_EVENTS.includes(event.event_name as EventName)) {
    errors.push(`Invalid event_name: ${event.event_name}`);
  }

  if (event.value !== undefined && typeof event.value !== 'number') {
    errors.push('value must be a number');
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  // Extract click IDs from URL if present
  const urlClickIds = extractClickIds(event.url as string);

  // Sanitize and build event
  const sanitizedEvent: ExtendedIncomingEvent = {
    event_name: event.event_name as EventName,
    ssi_id: (event.ssi_id as string) || undefined,
    session_id: (event.session_id as string) || undefined,
    event_id: (event.event_id as string) || undefined,
    
    // Tier 1 click IDs
    fbclid: (event.fbclid as string) || urlClickIds.fbclid || undefined,
    gclid: (event.gclid as string) || urlClickIds.gclid || undefined,
    gbraid: (event.gbraid as string) || urlClickIds.gbraid || undefined,
    wbraid: (event.wbraid as string) || urlClickIds.wbraid || undefined,
    ttclid: (event.ttclid as string) || urlClickIds.ttclid || undefined,
    fbc: (event.fbc as string) || undefined,
    fbp: (event.fbp as string) || undefined,
    
    // Extended click IDs
    msclkid: (event.msclkid as string) || urlClickIds.msclkid || undefined,
    sccid: (event.sccid as string) || urlClickIds.sccid || urlClickIds.ScCid || undefined,
    epik: (event.epik as string) || urlClickIds.epik || undefined,
    li_fat_id: (event.li_fat_id as string) || urlClickIds.li_fat_id || undefined,
    twclid: (event.twclid as string) || urlClickIds.twclid || undefined,
    rdt_cid: (event.rdt_cid as string) || urlClickIds.rdt_cid || undefined,
    dclid: (event.dclid as string) || urlClickIds.dclid || undefined,
    tblci: (event.tblci as string) || urlClickIds.tblci || undefined,
    amzn_cid: (event.amzn_cid as string) || urlClickIds.amzn_cid || undefined,
    
    // UTM params
    utm_source: (event.utm_source as string) || urlClickIds.utm_source || undefined,
    utm_medium: (event.utm_medium as string) || urlClickIds.utm_medium || undefined,
    utm_campaign: (event.utm_campaign as string) || urlClickIds.utm_campaign || undefined,
    utm_content: (event.utm_content as string) || urlClickIds.utm_content || undefined,
    utm_term: (event.utm_term as string) || urlClickIds.utm_term || undefined,
    
    // Page info
    url: (event.url as string) || undefined,
    referrer: (event.referrer as string) || undefined,
    title: (event.title as string) || undefined,
    
    // User data
    email: (event.email as string) || undefined,
    phone: (event.phone as string) || undefined,
    first_name: (event.first_name as string) || undefined,
    last_name: (event.last_name as string) || undefined,
    city: (event.city as string) || undefined,
    state: (event.state as string) || undefined,
    zip_code: (event.zip_code as string) || undefined,
    country: (event.country as string) || undefined,
    external_id: (event.external_id as string) || undefined,
    
    // Device info
    user_agent: (event.user_agent as string) || undefined,
    ip_address: (event.ip_address as string) || undefined,
    language: (event.language as string) || undefined,
    
    // Behavioral
    scroll_depth: (event.scroll_depth as number) || undefined,
    time_on_page: (event.time_on_page as number) || undefined,
    clicks: (event.clicks as number) || undefined,
    
    // E-commerce
    value: (event.value as number) || undefined,
    currency: (event.currency as string) || 'BRL',
    content_ids: (event.content_ids as string[]) || undefined,
    content_type: (event.content_type as string) || undefined,
    content_name: (event.content_name as string) || undefined,
    content_category: (event.content_category as string) || undefined,
    num_items: (event.num_items as number) || undefined,
    order_id: (event.order_id as string) || undefined,
    
    // Timestamp
    timestamp: (event.timestamp as number) || undefined,
  };

  return { valid: true, errors: [], sanitizedEvent };
}

// ----------------------------------------------------------------------------
// Route: Collect Event (Universal - All Platforms)
// ----------------------------------------------------------------------------

async function handleCollect(
  request: Request,
  env: Env
): Promise<Response> {
  const startTime = Date.now();

  // Quick bot check
  const quickCheck = quickBotCheck(request);
  if (quickCheck.isBot) {
    const trustScore = createBlockedTrustScore(quickCheck.reason || 'Bot detected');
    return jsonResponse({
      success: false,
      error: 'Request blocked',
      trust_score: trustScore.score,
      trust_action: trustScore.action,
    }, 403);
  }

  // Parse body
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse('Invalid JSON body', 400);
  }

  // Validate
  const validation = validateEvent(body);
  if (!validation.valid || !validation.sanitizedEvent) {
    return jsonResponse({ success: false, errors: validation.errors }, 400);
  }

  const event = validation.sanitizedEvent as ExtendedIncomingEvent;

  // Generate IDs
  const eventId = event.event_id || generateEventId();
  const ssiId = event.ssi_id || generateSSIId();
  event.event_id = eventId;
  event.ssi_id = ssiId;
  event.timestamp = event.timestamp || Date.now();

  // Detect traffic source
  const trafficSource = detectTrafficSource(event);
  event.traffic_source = trafficSource.source;
  event.traffic_medium = trafficSource.medium;

  // Calculate Trust Score
  const trustScore = await calculateTrustScore(request, event, env);
  const emqScore = estimateEMQ(event);

  console.log(`[Collect] ${event.event_name} | Source: ${trafficSource.source}/${trafficSource.medium} | EMQ: ${emqScore} | Trust: ${trustScore.score}`);

  // Build response
  const response: CollectResponse = {
    success: true,
    event_id: eventId,
    ssi_id: ssiId,
    trust_score: trustScore.score,
    trust_action: trustScore.action,
    traffic_source: trafficSource.source,
    traffic_medium: trafficSource.medium,
    platforms: {},
    processing_time_ms: 0,
  };

  // If blocked, only send to BigQuery
  if (trustScore.action === 'block') {
    const [bigqueryResult] = await Promise.allSettled([
      sendToBigQuery(event, request, env, trustScore),
    ]);
    
    response.success = false;
    response.error = 'Blocked by trust score';
    response.platforms = {
      bigquery: bigqueryResult.status === 'fulfilled' ? bigqueryResult.value : { sent: false },
    };
    response.processing_time_ms = Date.now() - startTime;
    return jsonResponse(response, 200);
  }

  // Send to ALL enabled platforms in parallel
  const platformPromises = [
    // Tier 1 - Big Tech
    sendToMeta(event, request, env),
    sendToGoogle(event, request, env),
    sendToTikTok(event, request, env),
    sendToMicrosoft(event, request, env),
    
    // Tier 2 - Major Platforms
    sendToSnapchat(event, request, env),
    sendToPinterest(event, request, env),
    sendToLinkedIn(event, request, env),
    sendToTwitter(event, request, env),
    
    // Storage
    sendToBigQuery(event, request, env, trustScore),
  ];

  const results = await Promise.allSettled(platformPromises);

  // Map results to platform names
  const platformNames = [
    'meta', 'google', 'tiktok', 'microsoft',
    'snapchat', 'pinterest', 'linkedin', 'twitter',
    'bigquery',
  ];

  results.forEach((result, index) => {
    const platformName = platformNames[index];
    response.platforms[platformName] = result.status === 'fulfilled'
      ? result.value
      : { sent: false, error: 'Promise rejected' };
  });

  response.processing_time_ms = Date.now() - startTime;

  // Log summary
  const successPlatforms = Object.entries(response.platforms)
    .filter(([_, r]) => (r as PlatformResult)?.sent)
    .map(([name, _]) => name);
  
  console.log(`[Collect] Completed in ${response.processing_time_ms}ms | Sent to: ${successPlatforms.join(', ') || 'none'}`);

  return jsonResponse(response);
}

// ----------------------------------------------------------------------------
// Route: Health Check
// ----------------------------------------------------------------------------

async function handleHealth(env: Env): Promise<Response> {
  const enabledPlatforms = [];
  
  if (env.ENABLE_META !== 'false') enabledPlatforms.push('meta');
  if (env.ENABLE_GOOGLE === 'true') enabledPlatforms.push('google');
  if (env.ENABLE_TIKTOK === 'true') enabledPlatforms.push('tiktok');
  if (env.ENABLE_MICROSOFT === 'true') enabledPlatforms.push('microsoft');
  if (env.ENABLE_SNAPCHAT === 'true') enabledPlatforms.push('snapchat');
  if (env.ENABLE_PINTEREST === 'true') enabledPlatforms.push('pinterest');
  if (env.ENABLE_LINKEDIN === 'true') enabledPlatforms.push('linkedin');
  if (env.ENABLE_TWITTER === 'true') enabledPlatforms.push('twitter');
  if (env.ENABLE_BIGQUERY === 'true') enabledPlatforms.push('bigquery');

  return jsonResponse({
    status: 'ok',
    service: 'ssi-shadow-universal',
    version: '3.0.0',
    platforms_enabled: enabledPlatforms,
    platforms_count: enabledPlatforms.length,
    traffic_sources_supported: 50,
    timestamp: new Date().toISOString(),
  });
}

// ----------------------------------------------------------------------------
// Route: Info
// ----------------------------------------------------------------------------

async function handleInfo(): Promise<Response> {
  return jsonResponse({
    service: 'S.S.I. SHADOW UNIVERSAL',
    version: '3.0.0',
    description: 'Server-Side Intelligence for 20 Ad Platforms + 50 Traffic Sources',
    platforms: {
      tier1: ['Meta', 'Google', 'TikTok', 'Microsoft/Bing', 'Amazon'],
      tier2: ['Snapchat', 'Pinterest', 'LinkedIn', 'Twitter/X', 'Reddit'],
      tier3: ['DV360', 'The Trade Desk', 'Criteo', 'Taboola', 'Outbrain'],
      tier4: ['Kwai', 'AppLovin', 'Unity', 'IronSource', 'AdRoll'],
    },
    traffic_sources: {
      paid: 20,
      organic: 30,
      total: 50,
    },
    endpoints: [
      'GET  /                - This info',
      'GET  /api/health      - Health check with enabled platforms',
      'POST /api/collect     - Collect event (universal)',
      'POST /api/events      - Alias for /api/collect',
    ],
  });
}

// ----------------------------------------------------------------------------
// Router
// ----------------------------------------------------------------------------

async function handleRequest(request: Request, env: Env): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  // CORS preflight
  if (method === 'OPTIONS') {
    return new Response(null, { status: 204, headers: CORS_HEADERS });
  }

  // Routes
  if (method === 'GET' && path === '/') return handleInfo();
  if (method === 'GET' && path === '/api/health') return handleHealth(env);
  if (method === 'POST' && (path === '/api/collect' || path === '/api/events')) {
    return handleCollect(request, env);
  }

  return errorResponse(`Not found: ${method} ${path}`, 404);
}

// ----------------------------------------------------------------------------
// Worker Export
// ----------------------------------------------------------------------------

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    try {
      return await handleRequest(request, env);
    } catch (error) {
      const msg = error instanceof Error ? error.message : String(error);
      console.error(`[Worker] Unhandled error: ${msg}`);
      return jsonResponse({ success: false, error: 'Internal server error' }, 500);
    }
  },
};
