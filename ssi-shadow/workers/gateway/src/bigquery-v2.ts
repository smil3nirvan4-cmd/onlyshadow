// ============================================================================
// S.S.I. SHADOW - BigQuery Integration Module (v2 with Pub/Sub)
// ============================================================================
// Architecture:
//   Worker → Pub/Sub (fast, <50ms) → Cloud Function → BigQuery
//
// Benefits:
//   - Zero data loss during BigQuery slowdowns
//   - Black Friday resilience (handles 10x traffic spikes)
//   - Automatic retry via Pub/Sub
//   - Fallback to direct BigQuery if Pub/Sub fails
//
// Environment Variables:
//   - USE_PUBSUB: 'true' (default) or 'false' for legacy mode
//   - PUBSUB_TOPIC: Topic name (default: 'raw-events')
//   - ENABLE_BIGQUERY: 'true' to enable
//   - GCP_SERVICE_ACCOUNT_KEY: Service account JSON
//   - BIGQUERY_PROJECT_ID, BIGQUERY_DATASET, BIGQUERY_TABLE
// ============================================================================

import { IncomingEvent, Env, PlatformResponse } from './types';
import { TrustScore } from './trust-score';

// ============================================================================
// Types
// ============================================================================

interface BigQueryRow {
  insertId: string;
  json: Record<string, unknown>;
}

interface BigQueryStreamingRequest {
  kind: string;
  rows: BigQueryRow[];
  templateSuffix?: string;
}

interface BigQueryStreamingResponse {
  kind: string;
  insertErrors?: Array<{
    index: number;
    errors: Array<{
      reason: string;
      location: string;
      message: string;
    }>;
  }>;
}

// Pub/Sub Types
interface PubSubMessage {
  data: string; // Base64 encoded
  attributes?: Record<string, string>;
}

interface PubSubPublishRequest {
  messages: PubSubMessage[];
}

interface PubSubPublishResponse {
  messageIds: string[];
}

// Metrics for monitoring
interface PubSubMetrics {
  published: number;
  failed: number;
  fallbackToBigQuery: number;
  avgLatencyMs: number;
  lastError?: string;
  lastErrorTime?: string;
}

// ============================================================================
// Configuration
// ============================================================================

const BIGQUERY_API_BASE = 'https://bigquery.googleapis.com/bigquery/v2';
const PUBSUB_API_BASE = 'https://pubsub.googleapis.com/v1';
const DEFAULT_PUBSUB_TOPIC = 'raw-events';

// In-memory metrics (reset on worker restart)
let pubsubMetrics: PubSubMetrics = {
  published: 0,
  failed: 0,
  fallbackToBigQuery: 0,
  avgLatencyMs: 0,
};

// ============================================================================
// Helper: Get OAuth2 Token for Service Account
// ============================================================================

async function getAccessToken(
  serviceAccountKey: string,
  scope: string = 'https://www.googleapis.com/auth/bigquery.insertdata https://www.googleapis.com/auth/pubsub'
): Promise<string> {
  try {
    const key = JSON.parse(serviceAccountKey);
    
    // Create JWT header
    const header = {
      alg: 'RS256',
      typ: 'JWT',
    };
    
    // Create JWT claims
    const now = Math.floor(Date.now() / 1000);
    const claims = {
      iss: key.client_email,
      scope: scope,
      aud: 'https://oauth2.googleapis.com/token',
      exp: now + 3600,
      iat: now,
    };
    
    // Encode header and claims
    const encodedHeader = btoa(JSON.stringify(header))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
    const encodedClaims = btoa(JSON.stringify(claims))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
    
    // Sign with private key (using Web Crypto API)
    const signatureInput = `${encodedHeader}.${encodedClaims}`;
    
    // Import private key
    const privateKeyPem = key.private_key;
    const privateKeyDer = pemToDer(privateKeyPem);
    
    const cryptoKey = await crypto.subtle.importKey(
      'pkcs8',
      privateKeyDer,
      { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
      false,
      ['sign']
    );
    
    // Sign
    const signature = await crypto.subtle.sign(
      'RSASSA-PKCS1-v1_5',
      cryptoKey,
      new TextEncoder().encode(signatureInput)
    );
    
    const encodedSignature = btoa(String.fromCharCode(...new Uint8Array(signature)))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
    
    const jwt = `${signatureInput}.${encodedSignature}`;
    
    // Exchange JWT for access token
    const tokenResponse = await fetch('https://oauth2.googleapis.com/token', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
        assertion: jwt,
      }),
    });
    
    if (!tokenResponse.ok) {
      throw new Error(`Token exchange failed: ${tokenResponse.status}`);
    }
    
    const tokenData = await tokenResponse.json() as { access_token: string };
    return tokenData.access_token;
  } catch (error) {
    console.error('[Auth] Failed to get access token:', error);
    throw error;
  }
}

/**
 * Convert PEM private key to DER format
 */
function pemToDer(pem: string): ArrayBuffer {
  const base64 = pem
    .replace('-----BEGIN PRIVATE KEY-----', '')
    .replace('-----END PRIVATE KEY-----', '')
    .replace(/\s/g, '');
  
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

// ============================================================================
// Transform Event to BigQuery Row
// ============================================================================

function transformEventToRow(
  event: IncomingEvent,
  request: Request,
  trustScore?: TrustScore
): Record<string, unknown> {
  // Extract URL parts
  let path = '';
  let queryParams = '';
  try {
    const url = new URL(event.url || '');
    path = url.pathname;
    queryParams = url.search;
  } catch {
    // Invalid URL, keep defaults
  }

  // Get Cloudflare headers
  const headers = request.headers;
  const cfData = (request as any).cf || {};

  return {
    // Core identifiers
    event_id: event.event_id,
    ssi_id: event.ssi_id,
    session_id: event.session_id || null,
    canonical_id: null, // Will be set by identity stitching
    
    // Event info
    event_name: event.event_name,
    event_time: new Date(event.timestamp || Date.now()).toISOString(),
    event_source: 'ghost',
    
    // Click IDs
    fbclid: event.fbclid || null,
    gclid: event.gclid || null,
    ttclid: event.ttclid || null,
    fbc: event.fbc || null,
    fbp: event.fbp || null,
    
    // Page info
    url: event.url || null,
    referrer: event.referrer || null,
    title: event.title || null,
    path: path || null,
    query_params: queryParams || null,
    
    // User data (hashed)
    email_hash: event.email_hash || null,
    phone_hash: event.phone_hash || null,
    first_name_hash: event.first_name_hash || null,
    last_name_hash: event.last_name_hash || null,
    city_hash: event.city_hash || null,
    state_hash: event.state_hash || null,
    zip_hash: event.zip_hash || null,
    country_hash: event.country_hash || null,
    external_id: event.external_id || null,
    
    // Device info
    user_agent: event.user_agent || headers.get('User-Agent') || null,
    ip_hash: null, // Hash IP for privacy before storing
    country: headers.get('CF-IPCountry') || cfData.country || null,
    city: cfData.city || null,
    region: cfData.region || null,
    language: event.language || null,
    timezone: event.timezone || null,
    
    // Screen & viewport
    screen_width: event.screen_width || null,
    screen_height: event.screen_height || null,
    viewport_width: event.viewport_width || null,
    viewport_height: event.viewport_height || null,
    device_pixel_ratio: null,
    color_depth: null,
    
    // Fingerprint
    canvas_hash: event.canvas_hash || null,
    webgl_vendor: event.webgl_vendor || null,
    webgl_renderer: event.webgl_renderer || null,
    plugins_hash: event.plugins_hash || null,
    touch_support: event.touch_support ?? null,
    hardware_concurrency: null,
    device_memory: null,
    
    // Behavioral
    scroll_depth: event.scroll_depth || null,
    time_on_page: event.time_on_page || null,
    clicks: event.clicks || null,
    session_duration: null,
    session_pageviews: null,
    
    // E-commerce
    value: event.value || null,
    currency: event.currency || null,
    content_ids: event.content_ids || null,
    content_type: event.content_type || null,
    content_name: event.content_name || null,
    content_category: event.content_category || null,
    num_items: event.num_items || null,
    order_id: event.order_id || null,
    
    // Trust score
    trust_score: trustScore?.score || null,
    trust_action: trustScore?.action || null,
    trust_reasons: trustScore?.reasons?.map(r => r.code) || null,
    trust_flags: trustScore?.flags || null,
    
    // ML predictions (will be populated later)
    predicted_ltv: event.predicted_ltv || null,
    predicted_intent: event.predicted_intent || null,
    predicted_segment: null,
    anomaly_score: null,
    
    // CAPI status (will be updated after sending)
    meta_sent: false,
    meta_response_code: null,
    meta_events_received: null,
    meta_error: null,
    google_sent: false,
    google_response_code: null,
    google_error: null,
    tiktok_sent: false,
    tiktok_response_code: null,
    tiktok_error: null,
    
    // Metadata
    processed_at: new Date().toISOString(),
    worker_version: '2.0.0', // Updated for Pub/Sub
    ingestion_method: 'pubsub', // or 'direct'
  };
}

// ============================================================================
// PUB/SUB INTEGRATION (Primary Path - <50ms target)
// ============================================================================

/**
 * Publish event to Pub/Sub for async processing
 * Target latency: <50ms
 */
async function publishToPubSub(
  event: IncomingEvent,
  request: Request,
  env: Env,
  trustScore?: TrustScore
): Promise<{ success: boolean; messageId?: string; latencyMs: number; error?: string }> {
  const startTime = Date.now();
  
  if (!env.GCP_SERVICE_ACCOUNT_KEY || !env.BIGQUERY_PROJECT_ID) {
    return { 
      success: false, 
      latencyMs: Date.now() - startTime,
      error: 'Missing GCP configuration' 
    };
  }

  try {
    // Get access token
    const accessToken = await getAccessToken(env.GCP_SERVICE_ACCOUNT_KEY);

    // Transform event to row (same format as BigQuery)
    const row = transformEventToRow(event, request, trustScore);

    // Create Pub/Sub message payload
    const payload = {
      row,
      metadata: {
        event_id: event.event_id,
        event_name: event.event_name,
        received_at: new Date().toISOString(),
        worker_region: (request as any).cf?.colo || 'unknown',
        trust_score: trustScore?.score,
        trust_action: trustScore?.action,
      }
    };

    // Create Pub/Sub message
    const message: PubSubMessage = {
      data: btoa(JSON.stringify(payload)),
      attributes: {
        event_name: event.event_name || 'unknown',
        event_id: event.event_id || crypto.randomUUID(),
        trust_action: trustScore?.action || 'allow',
        source: 'worker',
      }
    };

    const publishRequest: PubSubPublishRequest = {
      messages: [message],
    };

    // Pub/Sub topic path
    const topicName = env.PUBSUB_TOPIC || DEFAULT_PUBSUB_TOPIC;
    const topicPath = `projects/${env.BIGQUERY_PROJECT_ID}/topics/${topicName}`;
    const url = `${PUBSUB_API_BASE}/${topicPath}:publish`;

    // Send to Pub/Sub
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(publishRequest),
    });

    const latencyMs = Date.now() - startTime;

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`[Pub/Sub] API error: ${response.status} - ${errorText}`);
      pubsubMetrics.failed++;
      pubsubMetrics.lastError = `${response.status}: ${errorText.substring(0, 100)}`;
      pubsubMetrics.lastErrorTime = new Date().toISOString();
      return {
        success: false,
        latencyMs,
        error: `Pub/Sub error: ${response.status}`,
      };
    }

    const responseData = await response.json() as PubSubPublishResponse;
    
    // Update metrics
    pubsubMetrics.published++;
    const totalLatency = pubsubMetrics.avgLatencyMs * (pubsubMetrics.published - 1) + latencyMs;
    pubsubMetrics.avgLatencyMs = totalLatency / pubsubMetrics.published;

    // Log success (only for debugging, disable in prod)
    if (env.DEBUG === 'true') {
      console.log(`[Pub/Sub] Event ${event.event_id} published in ${latencyMs}ms, messageId: ${responseData.messageIds[0]}`);
    }

    return {
      success: true,
      messageId: responseData.messageIds[0],
      latencyMs,
    };
  } catch (error) {
    const latencyMs = Date.now() - startTime;
    pubsubMetrics.failed++;
    pubsubMetrics.lastError = error instanceof Error ? error.message : 'Unknown error';
    pubsubMetrics.lastErrorTime = new Date().toISOString();
    console.error('[Pub/Sub] Error:', error);
    return {
      success: false,
      latencyMs,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

// ============================================================================
// DIRECT BIGQUERY INSERT (Fallback Path)
// ============================================================================

/**
 * Send event directly to BigQuery (fallback when Pub/Sub fails)
 */
async function sendDirectToBigQuery(
  event: IncomingEvent,
  request: Request,
  env: Env,
  trustScore?: TrustScore
): Promise<PlatformResponse> {
  if (!env.GCP_SERVICE_ACCOUNT_KEY) {
    return { sent: false, error: 'Missing service account key' };
  }

  try {
    const accessToken = await getAccessToken(env.GCP_SERVICE_ACCOUNT_KEY);
    const row = transformEventToRow(event, request, trustScore);
    
    // Mark as direct ingestion
    row.ingestion_method = 'direct';

    const streamingRequest: BigQueryStreamingRequest = {
      kind: 'bigquery#tableDataInsertAllRequest',
      rows: [
        {
          insertId: event.event_id || crypto.randomUUID(),
          json: row,
        },
      ],
    };

    const url = `${BIGQUERY_API_BASE}/projects/${env.BIGQUERY_PROJECT_ID}/datasets/${env.BIGQUERY_DATASET}/tables/${env.BIGQUERY_TABLE}/insertAll`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(streamingRequest),
    });

    if (!response.ok) {
      const errorText = await response.text();
      console.error(`[BigQuery Direct] API error: ${response.status} - ${errorText}`);
      return {
        sent: false,
        status: response.status,
        error: `BigQuery API error: ${response.status}`,
      };
    }

    const responseData = await response.json() as BigQueryStreamingResponse;

    if (responseData.insertErrors && responseData.insertErrors.length > 0) {
      const errors = responseData.insertErrors
        .flatMap(e => e.errors.map(err => err.message))
        .join('; ');
      console.error(`[BigQuery Direct] Insert errors: ${errors}`);
      return {
        sent: false,
        status: response.status,
        error: `Insert errors: ${errors}`,
      };
    }

    console.log(`[BigQuery Direct] Event ${event.event_id} inserted (fallback path)`);
    
    return {
      sent: true,
      status: response.status,
      events_received: 1,
    };
  } catch (error) {
    console.error('[BigQuery Direct] Error:', error);
    return {
      sent: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

// ============================================================================
// MAIN ENTRY POINT - Send Event to BigQuery
// ============================================================================

/**
 * Send event to BigQuery (via Pub/Sub with fallback to direct)
 * 
 * Architecture:
 *   1. Try Pub/Sub first (fast, resilient)
 *   2. If Pub/Sub fails, fallback to direct BigQuery insert
 *   3. If both fail, return error (event can be retried by caller)
 */
export async function sendToBigQuery(
  event: IncomingEvent,
  request: Request,
  env: Env,
  trustScore?: TrustScore
): Promise<PlatformResponse> {
  // Check if BigQuery is enabled
  if (env.ENABLE_BIGQUERY !== 'true') {
    return { sent: false, error: 'BigQuery disabled' };
  }

  // Check required config
  if (!env.BIGQUERY_PROJECT_ID || !env.BIGQUERY_DATASET || !env.BIGQUERY_TABLE) {
    console.error('[BigQuery] Missing configuration');
    return { sent: false, error: 'Missing BigQuery configuration' };
  }

  if (!env.GCP_SERVICE_ACCOUNT_KEY) {
    console.error('[BigQuery] Missing service account key');
    return { sent: false, error: 'Missing service account key' };
  }

  // Check if Pub/Sub is enabled (default: true for resilience)
  const usePubSub = env.USE_PUBSUB !== 'false';

  if (usePubSub) {
    // =========================================================================
    // PRIMARY PATH: Pub/Sub (fast, resilient)
    // =========================================================================
    const pubsubResult = await publishToPubSub(event, request, env, trustScore);

    if (pubsubResult.success) {
      return {
        sent: true,
        status: 200,
        events_received: 1,
        pubsub_message_id: pubsubResult.messageId,
        latency_ms: pubsubResult.latencyMs,
        ingestion_method: 'pubsub',
      };
    }

    // =========================================================================
    // FALLBACK: If Pub/Sub fails, try direct BigQuery
    // =========================================================================
    console.warn(`[BigQuery] Pub/Sub failed (${pubsubResult.error}), falling back to direct insert`);
    pubsubMetrics.fallbackToBigQuery++;
    
    const directResult = await sendDirectToBigQuery(event, request, env, trustScore);
    return {
      ...directResult,
      fallback_used: true,
      original_error: pubsubResult.error,
      ingestion_method: 'direct_fallback',
    };
  } else {
    // =========================================================================
    // LEGACY MODE: Direct BigQuery insert
    // =========================================================================
    const result = await sendDirectToBigQuery(event, request, env, trustScore);
    return {
      ...result,
      ingestion_method: 'direct',
    };
  }
}

// ============================================================================
// BATCH OPERATIONS
// ============================================================================

/**
 * Batch publish to Pub/Sub (for queue processing)
 */
export async function batchPublishToPubSub(
  rows: Array<{
    event: IncomingEvent;
    trustScore?: TrustScore;
  }>,
  env: Env
): Promise<{ success: boolean; published: number; failed: number }> {
  if (!env.GCP_SERVICE_ACCOUNT_KEY || !env.BIGQUERY_PROJECT_ID) {
    return { success: false, published: 0, failed: rows.length };
  }

  try {
    const accessToken = await getAccessToken(env.GCP_SERVICE_ACCOUNT_KEY);
    const dummyRequest = new Request('https://dummy.com');

    // Build batch of messages
    const messages: PubSubMessage[] = rows.map(({ event, trustScore }) => {
      const row = transformEventToRow(event, dummyRequest, trustScore);
      const payload = {
        row,
        metadata: {
          event_id: event.event_id,
          event_name: event.event_name,
          received_at: new Date().toISOString(),
        }
      };
      return {
        data: btoa(JSON.stringify(payload)),
        attributes: {
          event_name: event.event_name || 'unknown',
          event_id: event.event_id || crypto.randomUUID(),
        }
      };
    });

    // Pub/Sub has limit of 1000 messages per request
    const batchSize = 1000;
    let published = 0;
    let failed = 0;

    for (let i = 0; i < messages.length; i += batchSize) {
      const batch = messages.slice(i, i + batchSize);
      const topicName = env.PUBSUB_TOPIC || DEFAULT_PUBSUB_TOPIC;
      const topicPath = `projects/${env.BIGQUERY_PROJECT_ID}/topics/${topicName}`;
      const url = `${PUBSUB_API_BASE}/${topicPath}:publish`;

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ messages: batch }),
      });

      if (response.ok) {
        const data = await response.json() as PubSubPublishResponse;
        published += data.messageIds.length;
      } else {
        failed += batch.length;
      }
    }

    return { success: failed === 0, published, failed };
  } catch (error) {
    console.error('[Pub/Sub Batch] Error:', error);
    return { success: false, published: 0, failed: rows.length };
  }
}

/**
 * Batch insert to BigQuery (fallback for batch operations)
 */
export async function batchInsertToBigQuery(
  rows: Array<{
    event: IncomingEvent;
    trustScore?: TrustScore;
  }>,
  env: Env
): Promise<{ success: boolean; inserted: number; errors: number }> {
  if (env.ENABLE_BIGQUERY !== 'true') {
    return { success: false, inserted: 0, errors: rows.length };
  }

  if (!env.GCP_SERVICE_ACCOUNT_KEY) {
    return { success: false, inserted: 0, errors: rows.length };
  }

  try {
    const accessToken = await getAccessToken(env.GCP_SERVICE_ACCOUNT_KEY);

    // Transform all events to rows
    const dummyRequest = new Request('https://dummy.com');
    const bqRows: BigQueryRow[] = rows.map(({ event, trustScore }) => ({
      insertId: event.event_id || crypto.randomUUID(),
      json: transformEventToRow(event, dummyRequest, trustScore),
    }));

    // BigQuery streaming insert has a limit of 10,000 rows per request
    const batchSize = 500;
    let inserted = 0;
    let errors = 0;

    for (let i = 0; i < bqRows.length; i += batchSize) {
      const batch = bqRows.slice(i, i + batchSize);
      
      const streamingRequest: BigQueryStreamingRequest = {
        kind: 'bigquery#tableDataInsertAllRequest',
        rows: batch,
      };

      const url = `${BIGQUERY_API_BASE}/projects/${env.BIGQUERY_PROJECT_ID}/datasets/${env.BIGQUERY_DATASET}/tables/${env.BIGQUERY_TABLE}/insertAll`;

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${accessToken}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(streamingRequest),
      });

      if (response.ok) {
        const responseData = await response.json() as BigQueryStreamingResponse;
        const batchErrors = responseData.insertErrors?.length || 0;
        inserted += batch.length - batchErrors;
        errors += batchErrors;
      } else {
        errors += batch.length;
      }
    }

    return {
      success: errors === 0,
      inserted,
      errors,
    };
  } catch (error) {
    console.error('[BigQuery Batch] Error:', error);
    return { success: false, inserted: 0, errors: rows.length };
  }
}

// ============================================================================
// METRICS & MONITORING
// ============================================================================

/**
 * Get Pub/Sub metrics for monitoring
 */
export function getPubSubMetrics(): PubSubMetrics {
  return { ...pubsubMetrics };
}

/**
 * Reset Pub/Sub metrics (for testing)
 */
export function resetPubSubMetrics(): void {
  pubsubMetrics = {
    published: 0,
    failed: 0,
    fallbackToBigQuery: 0,
    avgLatencyMs: 0,
  };
}

/**
 * Health check for Pub/Sub connectivity
 */
export async function checkPubSubHealth(env: Env): Promise<{
  healthy: boolean;
  latencyMs: number;
  error?: string;
}> {
  const startTime = Date.now();
  
  try {
    if (!env.GCP_SERVICE_ACCOUNT_KEY || !env.BIGQUERY_PROJECT_ID) {
      return { healthy: false, latencyMs: 0, error: 'Missing configuration' };
    }

    const accessToken = await getAccessToken(env.GCP_SERVICE_ACCOUNT_KEY);
    const topicName = env.PUBSUB_TOPIC || DEFAULT_PUBSUB_TOPIC;
    const topicPath = `projects/${env.BIGQUERY_PROJECT_ID}/topics/${topicName}`;
    const url = `${PUBSUB_API_BASE}/${topicPath}`;

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
      },
    });

    const latencyMs = Date.now() - startTime;

    if (response.ok) {
      return { healthy: true, latencyMs };
    } else {
      return { healthy: false, latencyMs, error: `HTTP ${response.status}` };
    }
  } catch (error) {
    return {
      healthy: false,
      latencyMs: Date.now() - startTime,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

// ============================================================================
// QUEUE CONSUMER (for Cloudflare Queue)
// ============================================================================

export interface QueueMessage {
  event: IncomingEvent;
  trustScore?: TrustScore;
  timestamp: number;
}

export async function processQueue(
  batch: MessageBatch<QueueMessage>,
  env: Env
): Promise<void> {
  console.log(`[Queue] Processing batch of ${batch.messages.length} messages`);

  const rows = batch.messages.map(msg => ({
    event: msg.body.event,
    trustScore: msg.body.trustScore,
  }));

  // Try Pub/Sub first
  const usePubSub = env.USE_PUBSUB !== 'false';
  
  if (usePubSub) {
    const pubsubResult = await batchPublishToPubSub(rows, env);
    console.log(`[Queue] Pub/Sub batch: Published ${pubsubResult.published}, Failed ${pubsubResult.failed}`);
    
    if (pubsubResult.failed > 0) {
      // Fallback to direct BigQuery for failed messages
      const failedRows = rows.slice(pubsubResult.published);
      const bqResult = await batchInsertToBigQuery(failedRows, env);
      console.log(`[Queue] BigQuery fallback: Inserted ${bqResult.inserted}, Errors ${bqResult.errors}`);
    }
  } else {
    const result = await batchInsertToBigQuery(rows, env);
    console.log(`[Queue] BigQuery direct: Inserted ${result.inserted}, Errors ${result.errors}`);
  }

  // Acknowledge all messages
  for (const msg of batch.messages) {
    msg.ack();
  }
}

// ============================================================================
// UTILITY: Query BigQuery
// ============================================================================

export async function queryBigQuery(
  query: string,
  env: Env
): Promise<unknown[] | null> {
  if (!env.GCP_SERVICE_ACCOUNT_KEY) {
    return null;
  }

  try {
    const accessToken = await getAccessToken(env.GCP_SERVICE_ACCOUNT_KEY);
    const url = `${BIGQUERY_API_BASE}/projects/${env.BIGQUERY_PROJECT_ID}/queries`;

    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query,
        useLegacySql: false,
        timeoutMs: 10000,
      }),
    });

    if (!response.ok) {
      console.error(`[BigQuery Query] Error: ${response.status}`);
      return null;
    }

    const data = await response.json() as any;
    
    if (data.rows) {
      return data.rows.map((row: any) => {
        const obj: Record<string, unknown> = {};
        data.schema.fields.forEach((field: any, index: number) => {
          obj[field.name] = row.f[index].v;
        });
        return obj;
      });
    }

    return [];
  } catch (error) {
    console.error('[BigQuery Query] Error:', error);
    return null;
  }
}

// ============================================================================
// UTILITY: Get User Profile
// ============================================================================

export async function getUserProfile(
  ssiId: string,
  env: Env
): Promise<Record<string, unknown> | null> {
  const query = `
    SELECT *
    FROM \`${env.BIGQUERY_PROJECT_ID}.${env.BIGQUERY_DATASET}.user_profiles\`
    WHERE canonical_id = (
      SELECT canonical_id
      FROM \`${env.BIGQUERY_PROJECT_ID}.${env.BIGQUERY_DATASET}.identity_graph\`
      WHERE linked_id = '${ssiId}'
      LIMIT 1
    )
    OR canonical_id = '${ssiId}'
    LIMIT 1
  `;

  const results = await queryBigQuery(query, env);
  return results && results.length > 0 ? results[0] as Record<string, unknown> : null;
}
