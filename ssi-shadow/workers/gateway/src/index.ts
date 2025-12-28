// ============================================================================
// S.S.I. SHADOW - Cloudflare Worker Entry Point
// ============================================================================
// Server-Side Tracking Gateway
// Receives events from Ghost Script and forwards to CAPIs

import {
  Env,
  IncomingEvent,
  CollectResponse,
  ValidationResult,
  EventName,
} from './types';

import { generateEventId, generateSSIId } from './utils/hash';
import { sendToMeta, validateMetaEvent, estimateEMQ } from './meta-capi';
import { sendToTikTok, estimateTikTokEMQ } from './tiktok-capi';
import { sendToGoogle } from './google-mp';
import { sendToBigQuery } from './bigquery';
import {
  calculateTrustScore,
  quickBotCheck,
  createBlockedTrustScore,
  shouldSendToCAPI,
  TrustScore,
} from './trust-score';

// ----------------------------------------------------------------------------
// CORS Headers
// ----------------------------------------------------------------------------
const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type, Authorization',
  'Access-Control-Max-Age': '86400',
};

// ----------------------------------------------------------------------------
// Response Helpers
// ----------------------------------------------------------------------------
function jsonResponse(data: unknown, status: number = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: {
      'Content-Type': 'application/json',
      ...CORS_HEADERS,
    },
  });
}

function errorResponse(message: string, status: number = 400): Response {
  return jsonResponse({ success: false, error: message }, status);
}

// ----------------------------------------------------------------------------
// Event Validation
// ----------------------------------------------------------------------------
function validateEvent(body: unknown): ValidationResult {
  const errors: string[] = [];

  // Check if body is an object
  if (!body || typeof body !== 'object') {
    return {
      valid: false,
      errors: ['Request body must be a JSON object'],
    };
  }

  const event = body as Record<string, unknown>;

  // Required: event_name
  if (!event.event_name || typeof event.event_name !== 'string') {
    errors.push('event_name is required and must be a string');
  }

  // Validate event_name is a known type
  const validEventNames: EventName[] = [
    'PageView',
    'ViewContent',
    'Search',
    'AddToCart',
    'AddToWishlist',
    'InitiateCheckout',
    'AddPaymentInfo',
    'Purchase',
    'Lead',
    'CompleteRegistration',
    'Contact',
    'CustomizeProduct',
    'Donate',
    'FindLocation',
    'Schedule',
    'StartTrial',
    'SubmitApplication',
    'Subscribe',
  ];

  if (
    event.event_name &&
    typeof event.event_name === 'string' &&
    !validEventNames.includes(event.event_name as EventName)
  ) {
    errors.push(`Invalid event_name: ${event.event_name}`);
  }

  // Validate value is a number if present
  if (event.value !== undefined && typeof event.value !== 'number') {
    errors.push('value must be a number');
  }

  // Validate currency is a string if present
  if (event.currency !== undefined && typeof event.currency !== 'string') {
    errors.push('currency must be a string');
  }

  // Validate content_ids is an array if present
  if (event.content_ids !== undefined && !Array.isArray(event.content_ids)) {
    errors.push('content_ids must be an array');
  }

  // Validate URL format if present
  if (event.url && typeof event.url === 'string') {
    try {
      new URL(event.url);
    } catch {
      errors.push('url must be a valid URL');
    }
  }

  // Validate email format if present
  if (event.email && typeof event.email === 'string') {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    if (!emailRegex.test(event.email)) {
      errors.push('email must be a valid email address');
    }
  }

  // Validate timestamp if present
  if (event.timestamp !== undefined) {
    if (typeof event.timestamp !== 'number') {
      errors.push('timestamp must be a number');
    } else {
      // Check if timestamp is reasonable (within last 7 days and not in future)
      const now = Date.now();
      const sevenDaysAgo = now - 7 * 24 * 60 * 60 * 1000;
      if (event.timestamp < sevenDaysAgo || event.timestamp > now + 60000) {
        errors.push('timestamp must be within the last 7 days');
      }
    }
  }

  if (errors.length > 0) {
    return { valid: false, errors };
  }

  // Sanitize and return valid event
  const sanitizedEvent: IncomingEvent = {
    event_name: event.event_name as EventName,
    ssi_id: (event.ssi_id as string) || undefined,
    session_id: (event.session_id as string) || undefined,
    event_id: (event.event_id as string) || undefined,
    fbclid: (event.fbclid as string) || undefined,
    gclid: (event.gclid as string) || undefined,
    ttclid: (event.ttclid as string) || undefined,
    fbc: (event.fbc as string) || undefined,
    fbp: (event.fbp as string) || undefined,
    url: (event.url as string) || undefined,
    referrer: (event.referrer as string) || undefined,
    title: (event.title as string) || undefined,
    email: (event.email as string) || undefined,
    phone: (event.phone as string) || undefined,
    first_name: (event.first_name as string) || undefined,
    last_name: (event.last_name as string) || undefined,
    city: (event.city as string) || undefined,
    state: (event.state as string) || undefined,
    zip_code: (event.zip_code as string) || undefined,
    country: (event.country as string) || undefined,
    external_id: (event.external_id as string) || undefined,
    user_agent: (event.user_agent as string) || undefined,
    ip_address: (event.ip_address as string) || undefined,
    language: (event.language as string) || undefined,
    timezone: (event.timezone as string) || undefined,
    screen_width: (event.screen_width as number) || undefined,
    screen_height: (event.screen_height as number) || undefined,
    viewport_width: (event.viewport_width as number) || undefined,
    viewport_height: (event.viewport_height as number) || undefined,
    canvas_hash: (event.canvas_hash as string) || undefined,
    webgl_vendor: (event.webgl_vendor as string) || undefined,
    webgl_renderer: (event.webgl_renderer as string) || undefined,
    plugins_hash: (event.plugins_hash as string) || undefined,
    touch_support: (event.touch_support as boolean) || undefined,
    scroll_depth: (event.scroll_depth as number) || undefined,
    time_on_page: (event.time_on_page as number) || undefined,
    clicks: (event.clicks as number) || undefined,
    value: (event.value as number) || undefined,
    currency: (event.currency as string) || undefined,
    content_ids: (event.content_ids as string[]) || undefined,
    content_type: (event.content_type as string) || undefined,
    content_name: (event.content_name as string) || undefined,
    content_category: (event.content_category as string) || undefined,
    num_items: (event.num_items as number) || undefined,
    order_id: (event.order_id as string) || undefined,
    predicted_ltv: (event.predicted_ltv as number) || undefined,
    predicted_intent: (event.predicted_intent as string) || undefined,
    timestamp: (event.timestamp as number) || undefined,
  };

  return { valid: true, errors: [], sanitizedEvent };
}

// ----------------------------------------------------------------------------
// Route: Health Check
// ----------------------------------------------------------------------------
async function handleHealth(): Promise<Response> {
  return jsonResponse({
    status: 'ok',
    service: 'ssi-shadow',
    version: '1.0.0',
    timestamp: new Date().toISOString(),
  });
}

// ----------------------------------------------------------------------------
// Route: Config (public info for debugging)
// ----------------------------------------------------------------------------
async function handleConfig(env: Env): Promise<Response> {
  return jsonResponse({
    meta: {
      enabled: env.ENABLE_META !== 'false',
      pixel_id: env.META_PIXEL_ID ? `${env.META_PIXEL_ID.substring(0, 4)}...` : null,
      test_mode: !!env.META_TEST_EVENT_CODE,
    },
    google: {
      enabled: env.ENABLE_GOOGLE === 'true',
      measurement_id: env.GA4_MEASUREMENT_ID ? `${env.GA4_MEASUREMENT_ID.substring(0, 4)}...` : null,
    },
    tiktok: {
      enabled: env.ENABLE_TIKTOK === 'true',
      pixel_id: env.TIKTOK_PIXEL_ID ? `${env.TIKTOK_PIXEL_ID.substring(0, 4)}...` : null,
      test_mode: !!env.TIKTOK_TEST_EVENT_CODE,
    },
    bigquery: {
      enabled: env.ENABLE_BIGQUERY === 'true',
      project: env.BIGQUERY_PROJECT_ID ? `${env.BIGQUERY_PROJECT_ID.substring(0, 8)}...` : null,
      dataset: env.BIGQUERY_DATASET || null,
    },
    features: {
      trust_score_threshold: parseFloat(env.TRUST_SCORE_THRESHOLD || '0.3'),
      rate_limiting: !!env.RATE_LIMIT,
    },
  });
}

// ----------------------------------------------------------------------------
// Route: Collect Event
// ----------------------------------------------------------------------------
async function handleCollect(
  request: Request,
  env: Env
): Promise<Response> {
  const startTime = Date.now();

  // Quick bot check (fast rejection)
  const quickCheck = quickBotCheck(request);
  if (quickCheck.isBot) {
    const trustScore = createBlockedTrustScore(quickCheck.reason || 'Bot detected');
    console.log(`[Collect] Quick blocked: ${quickCheck.reason}`);
    return jsonResponse({
      success: false,
      error: 'Request blocked',
      trust_score: trustScore.score,
      trust_action: trustScore.action,
    }, 403);
  }

  // Parse JSON body
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return errorResponse('Invalid JSON body', 400);
  }

  // Validate event
  const validation = validateEvent(body);
  if (!validation.valid || !validation.sanitizedEvent) {
    return jsonResponse(
      {
        success: false,
        errors: validation.errors,
      },
      400
    );
  }

  const event = validation.sanitizedEvent;

  // Generate IDs if not provided
  const eventId = event.event_id || generateEventId();
  const ssiId = event.ssi_id || generateSSIId();

  // Update event with generated IDs
  event.event_id = eventId;
  event.ssi_id = ssiId;

  // Set timestamp if not provided
  if (!event.timestamp) {
    event.timestamp = Date.now();
  }

  // Calculate Trust Score
  const trustScore = await calculateTrustScore(request, event, env);
  
  // Check if we should send to CAPI
  const capiDecision = shouldSendToCAPI(trustScore, env);

  // Estimate EMQ for Meta
  const emqScore = estimateEMQ(event);

  console.log(`[Collect] Processing ${event.event_name} | ID: ${eventId} | SSI: ${ssiId} | EMQ: ${emqScore} | Trust: ${trustScore.score} (${trustScore.action})`);

  // Build response base
  const response: CollectResponse = {
    success: true,
    event_id: eventId,
    ssi_id: ssiId,
    trust_score: trustScore.score,
    trust_action: trustScore.action,
    platforms: {},
    processing_time_ms: 0,
  };

  // If blocked, don't send to any platform
  if (trustScore.action === 'block') {
    response.success = false;
    response.error = 'Blocked by trust score';
    response.processing_time_ms = Date.now() - startTime;
    
    console.log(`[Collect] Blocked event ${eventId} | Reasons: ${trustScore.reasons.map(r => r.code).join(', ')}`);
    
    return jsonResponse(response, 200); // Return 200 to not break client
  }

  // Send to all platforms in parallel
  const [metaResult, tiktokResult, googleResult, bigqueryResult] = await Promise.allSettled([
    sendToMeta(event, request, env),
    sendToTikTok(event, request, env),
    sendToGoogle(event, request, env),
    sendToBigQuery(event, request, env, trustScore),
  ]);

  // Build final response
  response.platforms = {
    meta:
      metaResult.status === 'fulfilled'
        ? metaResult.value
        : { sent: false, error: 'Promise rejected' },
    tiktok:
      tiktokResult.status === 'fulfilled'
        ? tiktokResult.value
        : { sent: false, error: 'Promise rejected' },
    google:
      googleResult.status === 'fulfilled'
        ? googleResult.value
        : { sent: false, error: 'Promise rejected' },
    bigquery:
      bigqueryResult.status === 'fulfilled'
        ? bigqueryResult.value
        : { sent: false, error: 'Promise rejected' },
  };
  response.processing_time_ms = Date.now() - startTime;

  // Check if any CAPI platform succeeded (excluding BigQuery which is storage)
  const capiPlatforms = ['meta', 'tiktok', 'google'];
  const anyCapiSuccess = capiPlatforms.some(
    (p) => response.platforms[p as keyof typeof response.platforms]?.sent
  );

  if (!anyCapiSuccess && (env.ENABLE_META === 'true' || env.ENABLE_TIKTOK === 'true' || env.ENABLE_GOOGLE === 'true')) {
    response.success = false;
    console.error(`[Collect] All CAPI platforms failed for event ${eventId}`);
  }

  // Log platform results
  const platformStatus = Object.entries(response.platforms)
    .map(([name, result]) => `${name}:${result?.sent ? '✓' : '✗'}`)
    .join(' ');
  
  console.log(`[Collect] Completed in ${response.processing_time_ms}ms | ${platformStatus}`);

  return jsonResponse(response);
}

// ----------------------------------------------------------------------------
// Route: Test Event (uses test_event_code)
// ----------------------------------------------------------------------------
async function handleTest(
  request: Request,
  env: Env
): Promise<Response> {
  // Ensure test mode is enabled
  if (!env.META_TEST_EVENT_CODE) {
    return errorResponse('Test mode not configured. Set META_TEST_EVENT_CODE in wrangler.toml', 400);
  }

  return handleCollect(request, env);
}

// ----------------------------------------------------------------------------
// Router
// ----------------------------------------------------------------------------
async function handleRequest(
  request: Request,
  env: Env
): Promise<Response> {
  const url = new URL(request.url);
  const path = url.pathname;
  const method = request.method;

  // Handle CORS preflight
  if (method === 'OPTIONS') {
    return new Response(null, {
      status: 204,
      headers: CORS_HEADERS,
    });
  }

  // Route: GET /api/health
  if (method === 'GET' && path === '/api/health') {
    return handleHealth();
  }

  // Route: GET /api/config
  if (method === 'GET' && path === '/api/config') {
    return handleConfig(env);
  }

  // Route: POST /api/collect or /api/events
  if (method === 'POST' && (path === '/api/collect' || path === '/api/events')) {
    return handleCollect(request, env);
  }

  // Route: POST /api/test
  if (method === 'POST' && path === '/api/test') {
    return handleTest(request, env);
  }

  // Route: GET / (root - simple info)
  if (method === 'GET' && path === '/') {
    return jsonResponse({
      service: 'S.S.I. SHADOW',
      version: '1.0.0',
      endpoints: [
        'GET  /api/health  - Health check',
        'GET  /api/config  - Public configuration',
        'POST /api/collect - Collect event',
        'POST /api/events  - Collect event (alias)',
        'POST /api/test    - Test event (requires META_TEST_EVENT_CODE)',
      ],
    });
  }

  // 404 Not Found
  return errorResponse(`Not found: ${method} ${path}`, 404);
}

// ----------------------------------------------------------------------------
// Worker Export
// ----------------------------------------------------------------------------
export default {
  async fetch(
    request: Request,
    env: Env,
    ctx: ExecutionContext
  ): Promise<Response> {
    try {
      return await handleRequest(request, env);
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : String(error);
      console.error(`[Worker] Unhandled error: ${errorMessage}`);

      return jsonResponse(
        {
          success: false,
          error: 'Internal server error',
          request_id: crypto.randomUUID(),
        },
        500
      );
    }
  },
};
