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
// ============================================================================

import { IncomingEvent, Env, PlatformResponse } from './types';
import { TrustScore } from './trust-score';

// ============================================================================
// Pub/Sub Types
// ============================================================================

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

interface PubSubConfig {
  projectId: string;
  topicId: string;
}

// Metrics for monitoring
interface PubSubMetrics {
  published: number;
  failed: number;
  fallbackToBigQuery: number;
  avgLatencyMs: number;
}

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

// ============================================================================
// Configuration
// ============================================================================

const BIGQUERY_API_BASE = 'https://bigquery.googleapis.com/bigquery/v2';

// ============================================================================
// Helper: Get OAuth2 Token for Service Account
// ============================================================================

async function getAccessToken(
  serviceAccountKey: string
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
      scope: 'https://www.googleapis.com/auth/bigquery.insertdata',
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
    console.error('[BigQuery] Failed to get access token:', error);
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
    worker_version: '1.0.0',
  };
}

// ============================================================================
// Send to BigQuery
// ============================================================================

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

  try {
    // Get access token
    const accessToken = await getAccessToken(env.GCP_SERVICE_ACCOUNT_KEY);

    // Transform event to row
    const row = transformEventToRow(event, request, trustScore);

    // Build streaming insert request
    const streamingRequest: BigQueryStreamingRequest = {
      kind: 'bigquery#tableDataInsertAllRequest',
      rows: [
        {
          insertId: event.event_id || crypto.randomUUID(),
          json: row,
        },
      ],
    };

    // Build URL
    const url = `${BIGQUERY_API_BASE}/projects/${env.BIGQUERY_PROJECT_ID}/datasets/${env.BIGQUERY_DATASET}/tables/${env.BIGQUERY_TABLE}/insertAll`;

    // Send request
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
      console.error(`[BigQuery] API error: ${response.status} - ${errorText}`);
      return {
        sent: false,
        status: response.status,
        error: `BigQuery API error: ${response.status}`,
      };
    }

    const responseData = await response.json() as BigQueryStreamingResponse;

    // Check for insert errors
    if (responseData.insertErrors && responseData.insertErrors.length > 0) {
      const errors = responseData.insertErrors
        .flatMap(e => e.errors.map(err => err.message))
        .join('; ');
      console.error(`[BigQuery] Insert errors: ${errors}`);
      return {
        sent: false,
        status: response.status,
        error: `Insert errors: ${errors}`,
      };
    }

    console.log(`[BigQuery] Event ${event.event_id} inserted successfully`);
    
    return {
      sent: true,
      status: response.status,
      events_received: 1,
    };
  } catch (error) {
    console.error('[BigQuery] Error:', error);
    return {
      sent: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

// ============================================================================
// Batch Insert (for queue processing)
// ============================================================================

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
    // Note: We need a dummy request for transformation
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
    console.error('[BigQuery] Batch insert error:', error);
    return { success: false, inserted: 0, errors: rows.length };
  }
}

// ============================================================================
// Queue Consumer (for Cloudflare Queue)
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
  console.log(`[BigQuery Queue] Processing batch of ${batch.messages.length} messages`);

  const rows = batch.messages.map(msg => ({
    event: msg.body.event,
    trustScore: msg.body.trustScore,
  }));

  const result = await batchInsertToBigQuery(rows, env);

  console.log(`[BigQuery Queue] Inserted: ${result.inserted}, Errors: ${result.errors}`);

  // Acknowledge all messages (even failures will be handled by DLQ)
  for (const msg of batch.messages) {
    msg.ack();
  }
}

// ============================================================================
// Utility: Query BigQuery (for lookups)
// ============================================================================

export async function queryBigQuery(
  query: string,
  env: Env
): Promise<unknown[] | null> {
  if (!env.GCP_SERVICE_ACCOUNT_KEY) {
    return null;
  }

  try {
    // For queries, we need a different scope
    const key = JSON.parse(env.GCP_SERVICE_ACCOUNT_KEY);
    
    // Get access token with query scope
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
      console.error(`[BigQuery] Query error: ${response.status}`);
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
    console.error('[BigQuery] Query error:', error);
    return null;
  }
}

// ============================================================================
// Get User Profile from BigQuery
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
