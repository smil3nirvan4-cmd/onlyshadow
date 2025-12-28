// ============================================================================
// S.S.I. SHADOW - Bid Optimization Engine
// ============================================================================
// Real-time bid optimization based on ML predictions and business rules
// Recommends bid multipliers for Meta, TikTok, and Google ads
// ============================================================================

import { Env, IncomingEvent } from './types';
import { MLPredictions, getMLPredictions } from './ml-integration';

// ============================================================================
// Types
// ============================================================================

export interface BidRecommendation {
  // Overall recommendation
  multiplier: number;
  confidence: number;
  strategy: BidStrategy;
  
  // Platform-specific multipliers
  platforms: {
    meta: PlatformBid;
    tiktok: PlatformBid;
    google: PlatformBid;
  };
  
  // Signals used
  signals: BidSignals;
  
  // Explanation
  reasons: string[];
}

export interface PlatformBid {
  multiplier: number;
  min_bid?: number;
  max_bid?: number;
  audience_signal?: string;
}

export interface BidSignals {
  ltv_score: number;
  propensity_score: number;
  churn_risk: number;
  recency_score: number;
  engagement_score: number;
  trust_score: number;
}

export type BidStrategy = 
  | 'aggressive'      // High LTV + High propensity
  | 'retention'       // High LTV + High churn risk
  | 'acquisition'     // New user with good signals
  | 'nurture'         // Medium propensity, build relationship
  | 'conservative'    // Low signals, minimize spend
  | 'exclude';        // Bot or very low value

export interface BidConfig {
  // Base multiplier range
  min_multiplier: number;
  max_multiplier: number;
  
  // Strategy weights
  ltv_weight: number;
  propensity_weight: number;
  churn_weight: number;
  recency_weight: number;
  
  // Thresholds
  exclude_trust_below: number;
  aggressive_ltv_above: number;
  retention_churn_above: number;
  
  // Platform adjustments
  meta_adjustment: number;
  tiktok_adjustment: number;
  google_adjustment: number;
}

// ============================================================================
// Default Configuration
// ============================================================================

const DEFAULT_BID_CONFIG: BidConfig = {
  // Multiplier range (0.5x to 2.0x)
  min_multiplier: 0.5,
  max_multiplier: 2.0,
  
  // Weight factors (must sum to 1.0)
  ltv_weight: 0.35,
  propensity_weight: 0.35,
  churn_weight: 0.15,
  recency_weight: 0.15,
  
  // Thresholds
  exclude_trust_below: 0.3,
  aggressive_ltv_above: 0.7, // Top 30% LTV
  retention_churn_above: 0.6,
  
  // Platform adjustments
  meta_adjustment: 1.0,
  tiktok_adjustment: 0.95,  // Slightly lower for TikTok
  google_adjustment: 1.05,  // Slightly higher for Google
};

// ============================================================================
// Bid Calculation Engine
// ============================================================================

/**
 * Calculate bid signals from ML predictions
 */
function calculateSignals(
  predictions: MLPredictions,
  event: IncomingEvent
): BidSignals {
  return {
    // LTV score (normalized 0-1)
    ltv_score: Math.min(predictions.ltv.ltv_percentile / 100, 1),
    
    // Propensity score
    propensity_score: predictions.propensity.purchase_probability,
    
    // Churn risk (inverted - higher = more risk)
    churn_risk: predictions.churn.churn_probability,
    
    // Recency score (from event data)
    recency_score: calculateRecencyScore(event),
    
    // Engagement score (from event data)
    engagement_score: calculateEngagementScore(event),
    
    // Trust score
    trust_score: event.trust_score || 0.5,
  };
}

/**
 * Calculate recency score from event timing
 */
function calculateRecencyScore(event: IncomingEvent): number {
  // If we have time_on_page, user is actively engaged
  if (event.time_on_page && event.time_on_page > 30000) {
    return 0.9; // Very recent
  }
  if (event.time_on_page && event.time_on_page > 10000) {
    return 0.7;
  }
  return 0.5; // Default
}

/**
 * Calculate engagement score from behavioral data
 */
function calculateEngagementScore(event: IncomingEvent): number {
  let score = 0.3; // Base score
  
  // Scroll depth
  if (event.scroll_depth) {
    score += (event.scroll_depth / 100) * 0.2;
  }
  
  // Clicks
  if (event.clicks && event.clicks > 0) {
    score += Math.min(event.clicks * 0.1, 0.2);
  }
  
  // Time on page
  if (event.time_on_page && event.time_on_page > 60000) {
    score += 0.2;
  }
  
  // Cart activity
  if (event.event_name === 'AddToCart' || event.event_name === 'InitiateCheckout') {
    score += 0.1;
  }
  
  return Math.min(score, 1.0);
}

/**
 * Determine bid strategy based on signals
 */
function determineStrategy(
  signals: BidSignals,
  predictions: MLPredictions,
  config: BidConfig
): BidStrategy {
  // Exclude bots and very low trust
  if (signals.trust_score < config.exclude_trust_below) {
    return 'exclude';
  }
  
  const isHighLTV = signals.ltv_score >= config.aggressive_ltv_above;
  const isHighPropensity = signals.propensity_score >= 0.5;
  const isHighChurnRisk = signals.churn_risk >= config.retention_churn_above;
  const isNewUser = predictions.ltv.predicted_ltv_90d === 0;
  
  // High value + High propensity = Aggressive
  if (isHighLTV && isHighPropensity) {
    return 'aggressive';
  }
  
  // High value + High churn risk = Retention
  if (isHighLTV && isHighChurnRisk) {
    return 'retention';
  }
  
  // New user with good engagement = Acquisition
  if (isNewUser && signals.engagement_score >= 0.6) {
    return 'acquisition';
  }
  
  // Medium signals = Nurture
  if (signals.propensity_score >= 0.3 || signals.ltv_score >= 0.4) {
    return 'nurture';
  }
  
  // Low signals = Conservative
  return 'conservative';
}

/**
 * Calculate base multiplier from signals
 */
function calculateBaseMultiplier(
  signals: BidSignals,
  config: BidConfig
): number {
  // Weighted combination of signals
  const weightedScore = 
    signals.ltv_score * config.ltv_weight +
    signals.propensity_score * config.propensity_weight +
    (1 - signals.churn_risk) * config.churn_weight +
    signals.recency_score * config.recency_weight;
  
  // Map to multiplier range
  // Score 0 = min_multiplier, Score 1 = max_multiplier
  const range = config.max_multiplier - config.min_multiplier;
  const multiplier = config.min_multiplier + (weightedScore * range);
  
  return Math.round(multiplier * 100) / 100; // Round to 2 decimals
}

/**
 * Apply strategy adjustments to multiplier
 */
function applyStrategyAdjustment(
  baseMultiplier: number,
  strategy: BidStrategy,
  config: BidConfig
): number {
  let adjustment = 1.0;
  
  switch (strategy) {
    case 'aggressive':
      adjustment = 1.3; // +30%
      break;
    case 'retention':
      adjustment = 1.2; // +20% for retention campaigns
      break;
    case 'acquisition':
      adjustment = 1.1; // +10% for new users
      break;
    case 'nurture':
      adjustment = 1.0; // No adjustment
      break;
    case 'conservative':
      adjustment = 0.8; // -20%
      break;
    case 'exclude':
      return 0; // No bid
  }
  
  const adjusted = baseMultiplier * adjustment;
  
  // Clamp to config limits
  return Math.max(
    config.min_multiplier,
    Math.min(config.max_multiplier, adjusted)
  );
}

/**
 * Calculate platform-specific bids
 */
function calculatePlatformBids(
  baseMultiplier: number,
  strategy: BidStrategy,
  predictions: MLPredictions,
  config: BidConfig
): BidRecommendation['platforms'] {
  return {
    meta: {
      multiplier: Math.round(baseMultiplier * config.meta_adjustment * 100) / 100,
      audience_signal: getMetaAudienceSignal(predictions, strategy),
    },
    tiktok: {
      multiplier: Math.round(baseMultiplier * config.tiktok_adjustment * 100) / 100,
      audience_signal: getTikTokAudienceSignal(predictions, strategy),
    },
    google: {
      multiplier: Math.round(baseMultiplier * config.google_adjustment * 100) / 100,
      audience_signal: getGoogleAudienceSignal(predictions, strategy),
    },
  };
}

/**
 * Get Meta audience signal for targeting
 */
function getMetaAudienceSignal(
  predictions: MLPredictions,
  strategy: BidStrategy
): string {
  // These can be used with Meta Value Optimization
  switch (strategy) {
    case 'aggressive':
      return 'high_value_intent';
    case 'retention':
      return 'loyal_at_risk';
    case 'acquisition':
      return 'lookalike_high_value';
    case 'nurture':
      return 'engaged_prospects';
    default:
      return 'broad';
  }
}

/**
 * Get TikTok audience signal
 */
function getTikTokAudienceSignal(
  predictions: MLPredictions,
  strategy: BidStrategy
): string {
  switch (strategy) {
    case 'aggressive':
      return 'purchase_intent';
    case 'retention':
      return 'existing_customers';
    case 'acquisition':
      return 'similar_to_purchasers';
    default:
      return 'interest_based';
  }
}

/**
 * Get Google audience signal
 */
function getGoogleAudienceSignal(
  predictions: MLPredictions,
  strategy: BidStrategy
): string {
  switch (strategy) {
    case 'aggressive':
      return 'in_market_high_intent';
    case 'retention':
      return 'customer_match_high_value';
    case 'acquisition':
      return 'similar_audiences';
    default:
      return 'affinity_audiences';
  }
}

/**
 * Generate explanation reasons
 */
function generateReasons(
  signals: BidSignals,
  strategy: BidStrategy,
  predictions: MLPredictions
): string[] {
  const reasons: string[] = [];
  
  // Strategy reason
  switch (strategy) {
    case 'aggressive':
      reasons.push(`High-value user (top ${Math.round((1 - signals.ltv_score) * 100)}% LTV) with strong purchase intent`);
      break;
    case 'retention':
      reasons.push(`Valuable customer at risk of churning (${Math.round(signals.churn_risk * 100)}% risk)`);
      break;
    case 'acquisition':
      reasons.push('New visitor showing strong engagement signals');
      break;
    case 'nurture':
      reasons.push('Moderate intent, opportunity to build relationship');
      break;
    case 'conservative':
      reasons.push('Lower signals, optimizing for efficiency');
      break;
    case 'exclude':
      reasons.push('Excluded due to low trust score or bot signals');
      break;
  }
  
  // Propensity reason
  if (signals.propensity_score >= 0.7) {
    reasons.push(`Very high purchase probability (${Math.round(signals.propensity_score * 100)}%)`);
  } else if (signals.propensity_score >= 0.5) {
    reasons.push(`Good purchase probability (${Math.round(signals.propensity_score * 100)}%)`);
  }
  
  // LTV reason
  if (predictions.ltv.predicted_ltv_90d > 200) {
    reasons.push(`Expected 90-day value: R$${Math.round(predictions.ltv.predicted_ltv_90d)}`);
  }
  
  // Engagement reason
  if (signals.engagement_score >= 0.7) {
    reasons.push('Highly engaged in current session');
  }
  
  return reasons;
}

/**
 * Calculate confidence score
 */
function calculateConfidence(
  signals: BidSignals,
  predictions: MLPredictions
): number {
  let confidence = 0.5; // Base confidence
  
  // More data = higher confidence
  if (predictions.ltv.ltv_percentile > 0) {
    confidence += 0.15; // Has LTV prediction
  }
  
  if (predictions.propensity.purchase_probability > 0) {
    confidence += 0.15; // Has propensity prediction
  }
  
  // High engagement = more signal
  if (signals.engagement_score >= 0.6) {
    confidence += 0.1;
  }
  
  // Trust score affects confidence
  confidence *= Math.max(signals.trust_score, 0.5);
  
  return Math.min(confidence, 1.0);
}

// ============================================================================
// Main Export Functions
// ============================================================================

/**
 * Get bid recommendation for an event
 */
export async function getBidRecommendation(
  event: IncomingEvent,
  env: Env,
  config: BidConfig = DEFAULT_BID_CONFIG
): Promise<BidRecommendation> {
  // Get ML predictions
  const predictions = await getMLPredictions(event.ssi_id || '', env);
  
  if (!predictions) {
    // Return conservative recommendation for unknown users
    return getDefaultRecommendation(event, config);
  }
  
  // Calculate signals
  const signals = calculateSignals(predictions, event);
  
  // Check for exclusion
  if (signals.trust_score < config.exclude_trust_below) {
    return createExcludeRecommendation(signals);
  }
  
  // Determine strategy
  const strategy = determineStrategy(signals, predictions, config);
  
  // Calculate base multiplier
  const baseMultiplier = calculateBaseMultiplier(signals, config);
  
  // Apply strategy adjustment
  const finalMultiplier = applyStrategyAdjustment(baseMultiplier, strategy, config);
  
  // Calculate platform-specific bids
  const platforms = calculatePlatformBids(finalMultiplier, strategy, predictions, config);
  
  // Generate reasons
  const reasons = generateReasons(signals, strategy, predictions);
  
  // Calculate confidence
  const confidence = calculateConfidence(signals, predictions);
  
  return {
    multiplier: finalMultiplier,
    confidence,
    strategy,
    platforms,
    signals,
    reasons,
  };
}

/**
 * Get default recommendation for unknown users
 */
function getDefaultRecommendation(
  event: IncomingEvent,
  config: BidConfig
): BidRecommendation {
  const signals: BidSignals = {
    ltv_score: 0.5,
    propensity_score: 0.2,
    churn_risk: 0.3,
    recency_score: calculateRecencyScore(event),
    engagement_score: calculateEngagementScore(event),
    trust_score: event.trust_score || 0.5,
  };
  
  // Check for exclusion
  if (signals.trust_score < config.exclude_trust_below) {
    return createExcludeRecommendation(signals);
  }
  
  const strategy: BidStrategy = signals.engagement_score >= 0.6 ? 'acquisition' : 'conservative';
  const multiplier = strategy === 'acquisition' ? 1.1 : 0.9;
  
  return {
    multiplier,
    confidence: 0.3, // Low confidence for unknown users
    strategy,
    platforms: {
      meta: { multiplier, audience_signal: 'broad' },
      tiktok: { multiplier: multiplier * 0.95, audience_signal: 'interest_based' },
      google: { multiplier: multiplier * 1.05, audience_signal: 'affinity_audiences' },
    },
    signals,
    reasons: ['New visitor with limited data, using engagement signals'],
  };
}

/**
 * Create exclude recommendation
 */
function createExcludeRecommendation(signals: BidSignals): BidRecommendation {
  return {
    multiplier: 0,
    confidence: 0.9, // High confidence in exclusion
    strategy: 'exclude',
    platforms: {
      meta: { multiplier: 0, audience_signal: 'exclude' },
      tiktok: { multiplier: 0, audience_signal: 'exclude' },
      google: { multiplier: 0, audience_signal: 'exclude' },
    },
    signals,
    reasons: [`Excluded: trust score ${Math.round(signals.trust_score * 100)}% below threshold`],
  };
}

/**
 * Quick bid multiplier (for performance-critical paths)
 */
export function getQuickBidMultiplier(
  trustScore: number,
  propensity?: number,
  ltvPercentile?: number
): number {
  // Quick exclusion check
  if (trustScore < 0.3) {
    return 0;
  }
  
  // Default base
  let multiplier = 1.0;
  
  // Adjust for propensity
  if (propensity !== undefined) {
    if (propensity >= 0.7) multiplier *= 1.3;
    else if (propensity >= 0.5) multiplier *= 1.15;
    else if (propensity < 0.2) multiplier *= 0.85;
  }
  
  // Adjust for LTV
  if (ltvPercentile !== undefined) {
    if (ltvPercentile >= 90) multiplier *= 1.2;
    else if (ltvPercentile >= 70) multiplier *= 1.1;
    else if (ltvPercentile < 30) multiplier *= 0.9;
  }
  
  // Clamp
  return Math.max(0.5, Math.min(2.0, Math.round(multiplier * 100) / 100));
}

/**
 * Get bid config from environment
 */
export function getBidConfig(env: Env): BidConfig {
  return {
    ...DEFAULT_BID_CONFIG,
    // Override with env vars if present
    min_multiplier: parseFloat(env.BID_MIN_MULTIPLIER || '0.5'),
    max_multiplier: parseFloat(env.BID_MAX_MULTIPLIER || '2.0'),
    exclude_trust_below: parseFloat(env.TRUST_SCORE_THRESHOLD || '0.3'),
  };
}

// ============================================================================
// Batch Processing
// ============================================================================

/**
 * Get bid recommendations for multiple events (batch)
 */
export async function getBatchBidRecommendations(
  events: IncomingEvent[],
  env: Env,
  config: BidConfig = DEFAULT_BID_CONFIG
): Promise<Map<string, BidRecommendation>> {
  const results = new Map<string, BidRecommendation>();
  
  // Process in parallel with limit
  const batchSize = 10;
  
  for (let i = 0; i < events.length; i += batchSize) {
    const batch = events.slice(i, i + batchSize);
    const promises = batch.map(async (event) => {
      const recommendation = await getBidRecommendation(event, env, config);
      return { eventId: event.event_id || '', recommendation };
    });
    
    const batchResults = await Promise.all(promises);
    
    for (const { eventId, recommendation } of batchResults) {
      if (eventId) {
        results.set(eventId, recommendation);
      }
    }
  }
  
  return results;
}

// ============================================================================
// Analytics
// ============================================================================

/**
 * Get bid strategy distribution
 */
export function analyzeStrategyDistribution(
  recommendations: BidRecommendation[]
): Record<BidStrategy, number> {
  const distribution: Record<BidStrategy, number> = {
    aggressive: 0,
    retention: 0,
    acquisition: 0,
    nurture: 0,
    conservative: 0,
    exclude: 0,
  };
  
  for (const rec of recommendations) {
    distribution[rec.strategy]++;
  }
  
  return distribution;
}

/**
 * Calculate average multiplier by strategy
 */
export function analyzeMultipliersByStrategy(
  recommendations: BidRecommendation[]
): Record<BidStrategy, number> {
  const sums: Record<BidStrategy, { total: number; count: number }> = {
    aggressive: { total: 0, count: 0 },
    retention: { total: 0, count: 0 },
    acquisition: { total: 0, count: 0 },
    nurture: { total: 0, count: 0 },
    conservative: { total: 0, count: 0 },
    exclude: { total: 0, count: 0 },
  };
  
  for (const rec of recommendations) {
    sums[rec.strategy].total += rec.multiplier;
    sums[rec.strategy].count++;
  }
  
  const averages: Record<BidStrategy, number> = {
    aggressive: 0,
    retention: 0,
    acquisition: 0,
    nurture: 0,
    conservative: 0,
    exclude: 0,
  };
  
  for (const strategy of Object.keys(sums) as BidStrategy[]) {
    if (sums[strategy].count > 0) {
      averages[strategy] = Math.round(
        (sums[strategy].total / sums[strategy].count) * 100
      ) / 100;
    }
  }
  
  return averages;
}
