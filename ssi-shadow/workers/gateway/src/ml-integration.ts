// ============================================================================
// S.S.I. SHADOW - BigQuery ML Integration
// ============================================================================
// Fetches ML predictions from BigQuery for real-time bid optimization
// ============================================================================

import { Env, IncomingEvent } from './types';

// ============================================================================
// Types
// ============================================================================

export interface MLPredictions {
  // LTV Predictions
  ltv: {
    predicted_ltv_90d: number;
    ltv_tier: 'vip' | 'high' | 'medium' | 'low';
    ltv_percentile: number;
    purchase_probability: number;
  };
  
  // Churn Predictions
  churn: {
    churn_probability: number;
    churn_risk_tier: 'critical' | 'high' | 'medium' | 'low';
    estimated_days_to_churn: number;
  };
  
  // Propensity Predictions
  propensity: {
    purchase_probability: number;
    propensity_tier: 'very_high' | 'high' | 'medium' | 'low' | 'very_low';
    bid_multiplier: number;
    predicted_next_action: string;
  };
  
  // Combined Signals
  combined: {
    recommended_bid_multiplier: number;
    expected_value: number;
    priority_score: number;
    targeting_segment: string;
  };
}

export interface BidSignal {
  user_id: string;
  bid_multiplier: number;
  propensity: number;
  ltv: number;
  segment: string;
  confidence: number;
}

// ============================================================================
// Cache for ML Predictions
// ============================================================================

interface CacheEntry {
  predictions: MLPredictions;
  timestamp: number;
  ttl: number;
}

// In-memory cache (per worker instance)
const predictionsCache = new Map<string, CacheEntry>();

// Cache TTL in milliseconds
const CACHE_TTL_MS = 5 * 60 * 1000; // 5 minutes

// ============================================================================
// BigQuery Query Functions
// ============================================================================

/**
 * Get OAuth2 access token for BigQuery
 */
async function getAccessToken(serviceAccountKey: string): Promise<string> {
  const key = JSON.parse(serviceAccountKey);
  
  // Create JWT
  const header = { alg: 'RS256', typ: 'JWT' };
  const now = Math.floor(Date.now() / 1000);
  const claims = {
    iss: key.client_email,
    scope: 'https://www.googleapis.com/auth/bigquery.readonly',
    aud: 'https://oauth2.googleapis.com/token',
    exp: now + 3600,
    iat: now,
  };
  
  const encodedHeader = btoa(JSON.stringify(header))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  const encodedClaims = btoa(JSON.stringify(claims))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  
  const signatureInput = `${encodedHeader}.${encodedClaims}`;
  
  // Sign with private key
  const privateKeyPem = key.private_key;
  const privateKeyDer = pemToDer(privateKeyPem);
  
  const cryptoKey = await crypto.subtle.importKey(
    'pkcs8',
    privateKeyDer,
    { name: 'RSASSA-PKCS1-v1_5', hash: 'SHA-256' },
    false,
    ['sign']
  );
  
  const signature = await crypto.subtle.sign(
    'RSASSA-PKCS1-v1_5',
    cryptoKey,
    new TextEncoder().encode(signatureInput)
  );
  
  const encodedSignature = btoa(String.fromCharCode(...new Uint8Array(signature)))
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
  
  const jwt = `${signatureInput}.${encodedSignature}`;
  
  // Exchange for access token
  const response = await fetch('https://oauth2.googleapis.com/token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: new URLSearchParams({
      grant_type: 'urn:ietf:params:oauth:grant-type:jwt-bearer',
      assertion: jwt,
    }),
  });
  
  const data = await response.json() as { access_token: string };
  return data.access_token;
}

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

/**
 * Execute BigQuery query
 */
async function queryBigQuery(
  query: string,
  env: Env
): Promise<Record<string, unknown>[] | null> {
  if (!env.GCP_SERVICE_ACCOUNT_KEY || !env.BIGQUERY_PROJECT_ID) {
    return null;
  }

  try {
    const accessToken = await getAccessToken(env.GCP_SERVICE_ACCOUNT_KEY);
    
    const url = `https://bigquery.googleapis.com/bigquery/v2/projects/${env.BIGQUERY_PROJECT_ID}/queries`;
    
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${accessToken}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        query,
        useLegacySql: false,
        timeoutMs: 5000, // 5 second timeout for real-time queries
        maxResults: 1,
      }),
    });

    if (!response.ok) {
      console.error(`[ML] BigQuery error: ${response.status}`);
      return null;
    }

    const data = await response.json() as any;
    
    if (!data.rows || data.rows.length === 0) {
      return [];
    }

    return data.rows.map((row: any) => {
      const obj: Record<string, unknown> = {};
      data.schema.fields.forEach((field: any, index: number) => {
        obj[field.name] = row.f[index].v;
      });
      return obj;
    });
  } catch (error) {
    console.error('[ML] Query error:', error);
    return null;
  }
}

// ============================================================================
// ML Prediction Functions
// ============================================================================

/**
 * Get ML predictions for a user
 */
export async function getMLPredictions(
  userId: string,
  env: Env
): Promise<MLPredictions | null> {
  // Check cache first
  const cached = predictionsCache.get(userId);
  if (cached && Date.now() - cached.timestamp < cached.ttl) {
    return cached.predictions;
  }

  // Query BigQuery for predictions
  const query = `
    SELECT
      -- LTV
      l.predicted_ltv_90d,
      l.predicted_ltv_tier AS ltv_tier,
      l.ltv_percentile,
      l.purchase_probability AS ltv_purchase_prob,
      
      -- Churn
      c.churn_probability,
      c.churn_risk_tier,
      c.estimated_days_to_churn,
      
      -- Propensity
      p.purchase_probability AS propensity,
      p.propensity_tier,
      p.bid_multiplier,
      p.predicted_next_action,
      
      -- Combined
      b.recommended_bid_multiplier,
      p.purchase_probability * COALESCE(l.predicted_ltv_90d, 50) AS expected_value
      
    FROM \`${env.BIGQUERY_PROJECT_ID}.${env.BIGQUERY_DATASET}.predictions_ltv\` l
    LEFT JOIN \`${env.BIGQUERY_PROJECT_ID}.${env.BIGQUERY_DATASET}.predictions_churn\` c 
      ON l.user_id = c.user_id
    LEFT JOIN \`${env.BIGQUERY_PROJECT_ID}.${env.BIGQUERY_DATASET}.predictions_propensity\` p 
      ON l.user_id = p.user_id
    LEFT JOIN \`${env.BIGQUERY_PROJECT_ID}.${env.BIGQUERY_DATASET}.v_realtime_bid_signals\` b 
      ON l.user_id = b.user_id
    WHERE l.user_id = '${userId}'
    LIMIT 1
  `;

  const results = await queryBigQuery(query, env);
  
  if (!results || results.length === 0) {
    // Return default predictions for unknown users
    return getDefaultPredictions();
  }

  const row = results[0];
  
  const predictions: MLPredictions = {
    ltv: {
      predicted_ltv_90d: parseFloat(row.predicted_ltv_90d as string) || 0,
      ltv_tier: (row.ltv_tier as any) || 'low',
      ltv_percentile: parseInt(row.ltv_percentile as string) || 50,
      purchase_probability: parseFloat(row.ltv_purchase_prob as string) || 0.5,
    },
    churn: {
      churn_probability: parseFloat(row.churn_probability as string) || 0,
      churn_risk_tier: (row.churn_risk_tier as any) || 'low',
      estimated_days_to_churn: parseInt(row.estimated_days_to_churn as string) || 60,
    },
    propensity: {
      purchase_probability: parseFloat(row.propensity as string) || 0,
      propensity_tier: (row.propensity_tier as any) || 'medium',
      bid_multiplier: parseFloat(row.bid_multiplier as string) || 1.0,
      predicted_next_action: (row.predicted_next_action as string) || 'browse',
    },
    combined: {
      recommended_bid_multiplier: parseFloat(row.recommended_bid_multiplier as string) || 1.0,
      expected_value: parseFloat(row.expected_value as string) || 0,
      priority_score: 0,
      targeting_segment: determineSegment(row),
    },
  };

  // Calculate priority score
  predictions.combined.priority_score = 
    predictions.propensity.purchase_probability * 0.4 +
    (predictions.ltv.predicted_ltv_90d / 500) * 0.3 +
    (1 - predictions.churn.churn_probability) * 0.3;

  // Cache the predictions
  predictionsCache.set(userId, {
    predictions,
    timestamp: Date.now(),
    ttl: CACHE_TTL_MS,
  });

  return predictions;
}

/**
 * Get default predictions for unknown users
 */
function getDefaultPredictions(): MLPredictions {
  return {
    ltv: {
      predicted_ltv_90d: 0,
      ltv_tier: 'low',
      ltv_percentile: 50,
      purchase_probability: 0.1,
    },
    churn: {
      churn_probability: 0.3,
      churn_risk_tier: 'medium',
      estimated_days_to_churn: 30,
    },
    propensity: {
      purchase_probability: 0.1,
      propensity_tier: 'low',
      bid_multiplier: 1.0,
      predicted_next_action: 'browse',
    },
    combined: {
      recommended_bid_multiplier: 1.0,
      expected_value: 0,
      priority_score: 0.3,
      targeting_segment: 'new_visitor',
    },
  };
}

/**
 * Determine targeting segment based on predictions
 */
function determineSegment(row: Record<string, unknown>): string {
  const ltvTier = row.ltv_tier as string;
  const propensityTier = row.propensity_tier as string;
  const churnRisk = row.churn_risk_tier as string;

  // VIP at risk
  if (ltvTier === 'vip' && churnRisk === 'critical') {
    return 'vip_at_risk';
  }
  
  // High value ready to buy
  if ((ltvTier === 'vip' || ltvTier === 'high') && 
      (propensityTier === 'very_high' || propensityTier === 'high')) {
    return 'high_value_hot';
  }
  
  // High propensity
  if (propensityTier === 'very_high' || propensityTier === 'high') {
    return 'high_intent';
  }
  
  // At risk
  if (churnRisk === 'critical' || churnRisk === 'high') {
    return 'at_risk';
  }
  
  // Engaged
  if (propensityTier === 'medium') {
    return 'engaged';
  }
  
  // Default
  return 'standard';
}

/**
 * Get bid signal for an event (fast path)
 */
export async function getBidSignal(
  event: IncomingEvent,
  env: Env
): Promise<BidSignal> {
  const userId = event.ssi_id || '';
  
  // Try to get predictions
  const predictions = await getMLPredictions(userId, env);
  
  if (!predictions) {
    // Return default signal
    return {
      user_id: userId,
      bid_multiplier: 1.0,
      propensity: 0.1,
      ltv: 0,
      segment: 'unknown',
      confidence: 0.3,
    };
  }

  return {
    user_id: userId,
    bid_multiplier: predictions.combined.recommended_bid_multiplier,
    propensity: predictions.propensity.purchase_probability,
    ltv: predictions.ltv.predicted_ltv_90d,
    segment: predictions.combined.targeting_segment,
    confidence: Math.min(predictions.ltv.ltv_percentile / 100, 1),
  };
}

/**
 * Enrich event with ML predictions
 */
export async function enrichEventWithML(
  event: IncomingEvent,
  env: Env
): Promise<IncomingEvent> {
  const userId = event.ssi_id || '';
  
  const predictions = await getMLPredictions(userId, env);
  
  if (!predictions) {
    return event;
  }

  return {
    ...event,
    predicted_ltv: predictions.ltv.predicted_ltv_90d,
    predicted_intent: predictions.propensity.propensity_tier,
    // Add custom fields for platform targeting
    custom_data: {
      ...(event as any).custom_data,
      ml_segment: predictions.combined.targeting_segment,
      ml_priority: predictions.combined.priority_score,
      ml_bid_multiplier: predictions.combined.recommended_bid_multiplier,
    },
  };
}

/**
 * Get batch predictions for multiple users
 */
export async function getBatchPredictions(
  userIds: string[],
  env: Env
): Promise<Map<string, MLPredictions>> {
  const results = new Map<string, MLPredictions>();
  
  // Check cache first
  const uncached: string[] = [];
  for (const userId of userIds) {
    const cached = predictionsCache.get(userId);
    if (cached && Date.now() - cached.timestamp < cached.ttl) {
      results.set(userId, cached.predictions);
    } else {
      uncached.push(userId);
    }
  }
  
  if (uncached.length === 0) {
    return results;
  }

  // Query BigQuery for uncached users (batch)
  const userIdList = uncached.map(id => `'${id}'`).join(',');
  
  const query = `
    SELECT
      l.user_id,
      l.predicted_ltv_90d,
      l.predicted_ltv_tier AS ltv_tier,
      l.ltv_percentile,
      c.churn_probability,
      c.churn_risk_tier,
      p.purchase_probability AS propensity,
      p.propensity_tier,
      p.bid_multiplier,
      b.recommended_bid_multiplier
    FROM \`${env.BIGQUERY_PROJECT_ID}.${env.BIGQUERY_DATASET}.predictions_ltv\` l
    LEFT JOIN \`${env.BIGQUERY_PROJECT_ID}.${env.BIGQUERY_DATASET}.predictions_churn\` c 
      ON l.user_id = c.user_id
    LEFT JOIN \`${env.BIGQUERY_PROJECT_ID}.${env.BIGQUERY_DATASET}.predictions_propensity\` p 
      ON l.user_id = p.user_id
    LEFT JOIN \`${env.BIGQUERY_PROJECT_ID}.${env.BIGQUERY_DATASET}.v_realtime_bid_signals\` b 
      ON l.user_id = b.user_id
    WHERE l.user_id IN (${userIdList})
  `;

  const rows = await queryBigQuery(query, env);
  
  if (rows) {
    for (const row of rows) {
      const userId = row.user_id as string;
      const predictions: MLPredictions = {
        ltv: {
          predicted_ltv_90d: parseFloat(row.predicted_ltv_90d as string) || 0,
          ltv_tier: (row.ltv_tier as any) || 'low',
          ltv_percentile: parseInt(row.ltv_percentile as string) || 50,
          purchase_probability: 0.5,
        },
        churn: {
          churn_probability: parseFloat(row.churn_probability as string) || 0,
          churn_risk_tier: (row.churn_risk_tier as any) || 'low',
          estimated_days_to_churn: 30,
        },
        propensity: {
          purchase_probability: parseFloat(row.propensity as string) || 0,
          propensity_tier: (row.propensity_tier as any) || 'medium',
          bid_multiplier: parseFloat(row.bid_multiplier as string) || 1.0,
          predicted_next_action: 'browse',
        },
        combined: {
          recommended_bid_multiplier: parseFloat(row.recommended_bid_multiplier as string) || 1.0,
          expected_value: 0,
          priority_score: 0,
          targeting_segment: determineSegment(row),
        },
      };
      
      results.set(userId, predictions);
      
      // Cache
      predictionsCache.set(userId, {
        predictions,
        timestamp: Date.now(),
        ttl: CACHE_TTL_MS,
      });
    }
  }
  
  // Add defaults for users not found
  for (const userId of uncached) {
    if (!results.has(userId)) {
      results.set(userId, getDefaultPredictions());
    }
  }
  
  return results;
}

/**
 * Clear predictions cache
 */
export function clearPredictionsCache(): void {
  predictionsCache.clear();
}

/**
 * Get cache stats
 */
export function getCacheStats(): { size: number; hitRate: number } {
  return {
    size: predictionsCache.size,
    hitRate: 0, // Would need to track hits/misses
  };
}
