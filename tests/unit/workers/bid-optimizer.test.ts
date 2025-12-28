/**
 * S.S.I. SHADOW - Bid Optimizer Tests
 * Tests for bid strategy calculation and recommendations
 */

import { describe, it, expect } from 'vitest';
import {
  mockMLPredictionVIP,
  mockMLPredictionHigh,
  mockMLPredictionMedium,
  mockMLPredictionLow,
  mockMLPredictionChurnRisk,
  mockTrustScoreHigh,
  mockTrustScoreLow,
  mockBidAggressive,
  mockBidRetention,
  mockBidExclude,
} from '@fixtures';

// =============================================================================
// TYPES
// =============================================================================

type BidStrategy = 'aggressive' | 'retention' | 'acquisition' | 'nurture' | 'conservative' | 'exclude';

interface BidSignals {
  ltv_score: number;
  propensity_score: number;
  churn_risk: number;
  recency_score: number;
  engagement_score: number;
  trust_score: number;
}

interface BidConfig {
  min_multiplier: number;
  max_multiplier: number;
  exclude_trust_below: number;
  platform_adjustments: {
    meta: number;
    tiktok: number;
    google: number;
  };
}

interface BidRecommendation {
  strategy: BidStrategy;
  multiplier: number;
  confidence: number;
  reasons: string[];
  signals: BidSignals;
  platforms: {
    meta: { multiplier: number; audience_signal: string };
    tiktok: { multiplier: number; audience_signal: string };
    google: { multiplier: number; audience_signal: string };
  };
}

// =============================================================================
// BID OPTIMIZER IMPLEMENTATION
// =============================================================================

const DEFAULT_BID_CONFIG: BidConfig = {
  min_multiplier: 0.5,
  max_multiplier: 2.0,
  exclude_trust_below: 0.3,
  platform_adjustments: {
    meta: 1.0,
    tiktok: 0.95,
    google: 1.05,
  },
};

const STRATEGY_CONFIG = {
  aggressive: { min: 1.5, max: 2.0 },
  retention: { min: 1.3, max: 1.5 },
  acquisition: { min: 1.1, max: 1.3 },
  nurture: { min: 0.9, max: 1.1 },
  conservative: { min: 0.7, max: 0.9 },
  exclude: { min: 0, max: 0 },
};

const AUDIENCE_SIGNALS = {
  aggressive: {
    meta: 'high_value_intent',
    tiktok: 'purchase_intent',
    google: 'in_market_high_intent',
  },
  retention: {
    meta: 'loyal_at_risk',
    tiktok: 'existing_customers',
    google: 'customer_match_high_value',
  },
  acquisition: {
    meta: 'lookalike_high_value',
    tiktok: 'similar_to_purchasers',
    google: 'similar_audiences',
  },
  nurture: {
    meta: 'engaged_prospects',
    tiktok: 'interest_based',
    google: 'affinity_audiences',
  },
  conservative: {
    meta: 'broad',
    tiktok: 'interest_based',
    google: 'affinity_audiences',
  },
  exclude: {
    meta: 'exclude',
    tiktok: 'exclude',
    google: 'exclude',
  },
};

function calculateBidSignals(
  prediction: typeof mockMLPredictionVIP | null,
  trustScore: number,
  engagementData: { scroll_depth?: number; time_on_page?: number; clicks?: number } = {}
): BidSignals {
  // Default signals for new users
  const defaultSignals: BidSignals = {
    ltv_score: 0.3,
    propensity_score: 0.3,
    churn_risk: 0.3,
    recency_score: 0.5,
    engagement_score: 0,
    trust_score: trustScore,
  };

  if (!prediction) {
    // Calculate engagement score from behavioral data
    let engagementScore = 0;
    if (engagementData.scroll_depth) {
      engagementScore += Math.min(engagementData.scroll_depth / 100, 0.4);
    }
    if (engagementData.time_on_page) {
      engagementScore += Math.min(engagementData.time_on_page / 60000, 0.3); // max at 60s
    }
    if (engagementData.clicks) {
      engagementScore += Math.min(engagementData.clicks / 10, 0.3);
    }
    
    defaultSignals.engagement_score = Math.min(engagementScore, 1);
    return defaultSignals;
  }

  // Map prediction to signals
  return {
    ltv_score: prediction.ltv_percentile / 100,
    propensity_score: prediction.propensity_7d,
    churn_risk: prediction.churn_probability,
    recency_score: 0.8, // From prediction freshness
    engagement_score: 0.7, // Has history = engaged
    trust_score: trustScore,
  };
}

function determineStrategy(signals: BidSignals, config: BidConfig = DEFAULT_BID_CONFIG): BidStrategy {
  // Exclude if trust score is too low
  if (signals.trust_score < config.exclude_trust_below) {
    return 'exclude';
  }

  // Aggressive: High LTV + High propensity
  if (signals.ltv_score >= 0.7 && signals.propensity_score >= 0.5) {
    return 'aggressive';
  }

  // Retention: High LTV + High churn risk
  if (signals.ltv_score >= 0.7 && signals.churn_risk >= 0.6) {
    return 'retention';
  }

  // Acquisition: New user + High engagement
  if (signals.ltv_score < 0.4 && signals.engagement_score >= 0.6) {
    return 'acquisition';
  }

  // Nurture: Medium signals
  if (signals.propensity_score >= 0.3 || signals.ltv_score >= 0.4) {
    return 'nurture';
  }

  // Conservative: Low signals
  return 'conservative';
}

function calculateMultiplier(
  signals: BidSignals,
  strategy: BidStrategy,
  config: BidConfig = DEFAULT_BID_CONFIG
): number {
  if (strategy === 'exclude') {
    return 0;
  }

  // Weighted combination of signals
  const weightedScore = 
    signals.ltv_score * 0.35 +
    signals.propensity_score * 0.35 +
    (1 - signals.churn_risk) * 0.15 +
    signals.recency_score * 0.15;

  // Get strategy range
  const { min, max } = STRATEGY_CONFIG[strategy];
  
  // Map weighted score to strategy range
  const multiplier = min + (weightedScore * (max - min));

  // Clamp to config limits
  return Math.max(config.min_multiplier, Math.min(config.max_multiplier, multiplier));
}

function calculateConfidence(signals: BidSignals): number {
  // Confidence based on data availability
  const dataPoints = [
    signals.ltv_score > 0 ? 1 : 0,
    signals.propensity_score > 0 ? 1 : 0,
    signals.engagement_score > 0 ? 1 : 0,
    signals.trust_score > 0.5 ? 1 : 0,
  ];

  const baseConfidence = dataPoints.reduce((a, b) => a + b, 0) / dataPoints.length;
  
  // Adjust confidence based on trust score
  return Math.round(baseConfidence * signals.trust_score * 100) / 100;
}

function generateReasons(signals: BidSignals, strategy: BidStrategy): string[] {
  const reasons: string[] = [];

  if (strategy === 'exclude') {
    reasons.push(`Traffic blocked due to low trust score (${signals.trust_score.toFixed(2)})`);
    reasons.push('Bot or invalid traffic detected');
    reasons.push('Do not spend budget on this user');
    return reasons;
  }

  // LTV-based reasons
  if (signals.ltv_score >= 0.9) {
    reasons.push(`VIP user (top 10% LTV)`);
  } else if (signals.ltv_score >= 0.7) {
    reasons.push(`High-value user (top 30% LTV)`);
  } else if (signals.ltv_score >= 0.5) {
    reasons.push('Medium-value user');
  }

  // Propensity-based reasons
  if (signals.propensity_score >= 0.7) {
    reasons.push(`Very high purchase probability (${Math.round(signals.propensity_score * 100)}%)`);
  } else if (signals.propensity_score >= 0.5) {
    reasons.push(`High purchase probability (${Math.round(signals.propensity_score * 100)}%)`);
  }

  // Churn-based reasons
  if (signals.churn_risk >= 0.7) {
    reasons.push(`High churn risk (${Math.round(signals.churn_risk * 100)}%) - retention campaign recommended`);
  }

  // Engagement-based reasons
  if (signals.engagement_score >= 0.6) {
    reasons.push('High engagement detected');
  }

  // Trust-based reasons
  if (signals.trust_score >= 0.8) {
    reasons.push('High trust score - quality traffic');
  }

  return reasons;
}

function getBidRecommendation(
  prediction: typeof mockMLPredictionVIP | null,
  trustScore: number,
  engagementData: { scroll_depth?: number; time_on_page?: number; clicks?: number } = {},
  config: BidConfig = DEFAULT_BID_CONFIG
): BidRecommendation {
  const signals = calculateBidSignals(prediction, trustScore, engagementData);
  const strategy = determineStrategy(signals, config);
  const multiplier = calculateMultiplier(signals, strategy, config);
  const confidence = calculateConfidence(signals);
  const reasons = generateReasons(signals, strategy);

  // Platform-specific multipliers
  const platformMultipliers = {
    meta: {
      multiplier: Math.round(multiplier * config.platform_adjustments.meta * 100) / 100,
      audience_signal: AUDIENCE_SIGNALS[strategy].meta,
    },
    tiktok: {
      multiplier: Math.round(multiplier * config.platform_adjustments.tiktok * 100) / 100,
      audience_signal: AUDIENCE_SIGNALS[strategy].tiktok,
    },
    google: {
      multiplier: Math.round(multiplier * config.platform_adjustments.google * 100) / 100,
      audience_signal: AUDIENCE_SIGNALS[strategy].google,
    },
  };

  return {
    strategy,
    multiplier: Math.round(multiplier * 100) / 100,
    confidence,
    reasons,
    signals,
    platforms: platformMultipliers,
  };
}

// =============================================================================
// TESTS
// =============================================================================

describe('Bid Optimizer', () => {
  describe('Signal Calculation', () => {
    it('should calculate signals from ML prediction', () => {
      const signals = calculateBidSignals(mockMLPredictionVIP, 0.9);
      
      expect(signals.ltv_score).toBe(0.95); // 95th percentile
      expect(signals.propensity_score).toBe(0.85);
      expect(signals.churn_risk).toBe(0.05);
      expect(signals.trust_score).toBe(0.9);
    });

    it('should return default signals for new users (no prediction)', () => {
      const signals = calculateBidSignals(null, 0.8);
      
      expect(signals.ltv_score).toBe(0.3);
      expect(signals.propensity_score).toBe(0.3);
      expect(signals.churn_risk).toBe(0.3);
      expect(signals.trust_score).toBe(0.8);
    });

    it('should calculate engagement score from behavioral data', () => {
      const signals = calculateBidSignals(null, 0.8, {
        scroll_depth: 75,
        time_on_page: 45000,
        clicks: 5,
      });
      
      expect(signals.engagement_score).toBeGreaterThan(0.5);
    });

    it('should cap engagement score at 1', () => {
      const signals = calculateBidSignals(null, 0.9, {
        scroll_depth: 100,
        time_on_page: 120000, // 2 minutes
        clicks: 20,
      });
      
      expect(signals.engagement_score).toBeLessThanOrEqual(1);
    });
  });

  describe('Strategy Determination', () => {
    it('should return exclude for low trust score', () => {
      const signals: BidSignals = {
        ltv_score: 0.9,
        propensity_score: 0.9,
        churn_risk: 0.1,
        recency_score: 0.9,
        engagement_score: 0.9,
        trust_score: 0.2, // Below threshold
      };
      
      const strategy = determineStrategy(signals);
      expect(strategy).toBe('exclude');
    });

    it('should return aggressive for high LTV + high propensity', () => {
      const signals: BidSignals = {
        ltv_score: 0.8,
        propensity_score: 0.7,
        churn_risk: 0.1,
        recency_score: 0.8,
        engagement_score: 0.8,
        trust_score: 0.9,
      };
      
      const strategy = determineStrategy(signals);
      expect(strategy).toBe('aggressive');
    });

    it('should return retention for high LTV + high churn risk', () => {
      const signals: BidSignals = {
        ltv_score: 0.8,
        propensity_score: 0.2,
        churn_risk: 0.7,
        recency_score: 0.4,
        engagement_score: 0.3,
        trust_score: 0.85,
      };
      
      const strategy = determineStrategy(signals);
      expect(strategy).toBe('retention');
    });

    it('should return acquisition for new user with high engagement', () => {
      const signals: BidSignals = {
        ltv_score: 0.3, // Low (new user)
        propensity_score: 0.4,
        churn_risk: 0.3,
        recency_score: 0.5,
        engagement_score: 0.8, // High engagement
        trust_score: 0.85,
      };
      
      const strategy = determineStrategy(signals);
      expect(strategy).toBe('acquisition');
    });

    it('should return nurture for medium signals', () => {
      const signals: BidSignals = {
        ltv_score: 0.5,
        propensity_score: 0.4,
        churn_risk: 0.3,
        recency_score: 0.5,
        engagement_score: 0.4,
        trust_score: 0.8,
      };
      
      const strategy = determineStrategy(signals);
      expect(strategy).toBe('nurture');
    });

    it('should return conservative for low signals', () => {
      const signals: BidSignals = {
        ltv_score: 0.2,
        propensity_score: 0.2,
        churn_risk: 0.3,
        recency_score: 0.3,
        engagement_score: 0.3,
        trust_score: 0.6,
      };
      
      const strategy = determineStrategy(signals);
      expect(strategy).toBe('conservative');
    });
  });

  describe('Multiplier Calculation', () => {
    it('should return 0 for exclude strategy', () => {
      const signals: BidSignals = {
        ltv_score: 0.9,
        propensity_score: 0.9,
        churn_risk: 0.1,
        recency_score: 0.9,
        engagement_score: 0.9,
        trust_score: 0.1,
      };
      
      const multiplier = calculateMultiplier(signals, 'exclude');
      expect(multiplier).toBe(0);
    });

    it('should return multiplier between 1.5-2.0 for aggressive', () => {
      const signals: BidSignals = {
        ltv_score: 0.95,
        propensity_score: 0.85,
        churn_risk: 0.05,
        recency_score: 0.9,
        engagement_score: 0.9,
        trust_score: 0.95,
      };
      
      const multiplier = calculateMultiplier(signals, 'aggressive');
      expect(multiplier).toBeGreaterThanOrEqual(1.5);
      expect(multiplier).toBeLessThanOrEqual(2.0);
    });

    it('should return multiplier between 1.3-1.5 for retention', () => {
      const signals: BidSignals = {
        ltv_score: 0.75,
        propensity_score: 0.25,
        churn_risk: 0.75,
        recency_score: 0.3,
        engagement_score: 0.4,
        trust_score: 0.85,
      };
      
      const multiplier = calculateMultiplier(signals, 'retention');
      expect(multiplier).toBeGreaterThanOrEqual(1.3);
      expect(multiplier).toBeLessThanOrEqual(1.5);
    });

    it('should return multiplier between 0.7-0.9 for conservative', () => {
      const signals: BidSignals = {
        ltv_score: 0.2,
        propensity_score: 0.2,
        churn_risk: 0.3,
        recency_score: 0.3,
        engagement_score: 0.3,
        trust_score: 0.6,
      };
      
      const multiplier = calculateMultiplier(signals, 'conservative');
      expect(multiplier).toBeGreaterThanOrEqual(0.5); // min config
      expect(multiplier).toBeLessThanOrEqual(0.9);
    });

    it('should respect config min_multiplier', () => {
      const signals: BidSignals = {
        ltv_score: 0.1,
        propensity_score: 0.1,
        churn_risk: 0.9,
        recency_score: 0.1,
        engagement_score: 0.1,
        trust_score: 0.4,
      };
      
      const config = { ...DEFAULT_BID_CONFIG, min_multiplier: 0.5 };
      const multiplier = calculateMultiplier(signals, 'conservative', config);
      expect(multiplier).toBeGreaterThanOrEqual(0.5);
    });

    it('should respect config max_multiplier', () => {
      const signals: BidSignals = {
        ltv_score: 1.0,
        propensity_score: 1.0,
        churn_risk: 0,
        recency_score: 1.0,
        engagement_score: 1.0,
        trust_score: 1.0,
      };
      
      const config = { ...DEFAULT_BID_CONFIG, max_multiplier: 1.8 };
      const multiplier = calculateMultiplier(signals, 'aggressive', config);
      expect(multiplier).toBeLessThanOrEqual(1.8);
    });
  });

  describe('Confidence Calculation', () => {
    it('should have high confidence with full data + high trust', () => {
      const signals: BidSignals = {
        ltv_score: 0.9,
        propensity_score: 0.8,
        churn_risk: 0.1,
        recency_score: 0.9,
        engagement_score: 0.8,
        trust_score: 0.95,
      };
      
      const confidence = calculateConfidence(signals);
      expect(confidence).toBeGreaterThan(0.7);
    });

    it('should have low confidence with missing data', () => {
      const signals: BidSignals = {
        ltv_score: 0,
        propensity_score: 0,
        churn_risk: 0.3,
        recency_score: 0.5,
        engagement_score: 0,
        trust_score: 0.6,
      };
      
      const confidence = calculateConfidence(signals);
      expect(confidence).toBeLessThan(0.5);
    });

    it('should scale confidence with trust score', () => {
      const signalsHighTrust: BidSignals = {
        ltv_score: 0.5,
        propensity_score: 0.5,
        churn_risk: 0.3,
        recency_score: 0.5,
        engagement_score: 0.5,
        trust_score: 0.9,
      };
      
      const signalsLowTrust: BidSignals = {
        ...signalsHighTrust,
        trust_score: 0.4,
      };
      
      const highTrustConfidence = calculateConfidence(signalsHighTrust);
      const lowTrustConfidence = calculateConfidence(signalsLowTrust);
      
      expect(highTrustConfidence).toBeGreaterThan(lowTrustConfidence);
    });
  });

  describe('Full Bid Recommendation', () => {
    it('should generate aggressive recommendation for VIP user', () => {
      const recommendation = getBidRecommendation(mockMLPredictionVIP, 0.92);
      
      expect(recommendation.strategy).toBe('aggressive');
      expect(recommendation.multiplier).toBeGreaterThanOrEqual(1.5);
      expect(recommendation.confidence).toBeGreaterThan(0.7);
      expect(recommendation.reasons.length).toBeGreaterThan(0);
      expect(recommendation.platforms.meta.audience_signal).toBe('high_value_intent');
    });

    it('should generate retention recommendation for churn risk user', () => {
      const recommendation = getBidRecommendation(mockMLPredictionChurnRisk, 0.88);
      
      expect(recommendation.strategy).toBe('retention');
      expect(recommendation.multiplier).toBeGreaterThanOrEqual(1.3);
      expect(recommendation.reasons.some(r => r.includes('churn'))).toBe(true);
      expect(recommendation.platforms.meta.audience_signal).toBe('loyal_at_risk');
    });

    it('should generate exclude recommendation for low trust', () => {
      const recommendation = getBidRecommendation(mockMLPredictionVIP, 0.15);
      
      expect(recommendation.strategy).toBe('exclude');
      expect(recommendation.multiplier).toBe(0);
      expect(recommendation.platforms.meta.multiplier).toBe(0);
      expect(recommendation.platforms.meta.audience_signal).toBe('exclude');
    });

    it('should generate acquisition recommendation for new engaged user', () => {
      const recommendation = getBidRecommendation(null, 0.85, {
        scroll_depth: 80,
        time_on_page: 60000,
        clicks: 5,
      });
      
      expect(recommendation.strategy).toBe('acquisition');
      expect(recommendation.multiplier).toBeGreaterThanOrEqual(1.1);
      expect(recommendation.platforms.meta.audience_signal).toBe('lookalike_high_value');
    });

    it('should apply platform adjustments correctly', () => {
      const recommendation = getBidRecommendation(mockMLPredictionHigh, 0.85);
      
      // TikTok should be 0.95x of base
      expect(recommendation.platforms.tiktok.multiplier)
        .toBeLessThan(recommendation.platforms.meta.multiplier);
      
      // Google should be 1.05x of base
      expect(recommendation.platforms.google.multiplier)
        .toBeGreaterThan(recommendation.platforms.meta.multiplier);
    });

    it('should include all required fields', () => {
      const recommendation = getBidRecommendation(mockMLPredictionMedium, 0.8);
      
      expect(recommendation).toHaveProperty('strategy');
      expect(recommendation).toHaveProperty('multiplier');
      expect(recommendation).toHaveProperty('confidence');
      expect(recommendation).toHaveProperty('reasons');
      expect(recommendation).toHaveProperty('signals');
      expect(recommendation).toHaveProperty('platforms');
      expect(recommendation.platforms).toHaveProperty('meta');
      expect(recommendation.platforms).toHaveProperty('tiktok');
      expect(recommendation.platforms).toHaveProperty('google');
    });
  });

  describe('Custom Configuration', () => {
    it('should respect custom exclude threshold', () => {
      const config: BidConfig = {
        ...DEFAULT_BID_CONFIG,
        exclude_trust_below: 0.5, // Higher threshold
      };
      
      const recommendation = getBidRecommendation(mockMLPredictionVIP, 0.45, {}, config);
      
      expect(recommendation.strategy).toBe('exclude');
    });

    it('should respect custom multiplier limits', () => {
      const config: BidConfig = {
        ...DEFAULT_BID_CONFIG,
        min_multiplier: 0.8,
        max_multiplier: 1.5,
      };
      
      const recommendation = getBidRecommendation(mockMLPredictionVIP, 0.95, {}, config);
      
      expect(recommendation.multiplier).toBeGreaterThanOrEqual(0.8);
      expect(recommendation.multiplier).toBeLessThanOrEqual(1.5);
    });

    it('should respect custom platform adjustments', () => {
      const config: BidConfig = {
        ...DEFAULT_BID_CONFIG,
        platform_adjustments: {
          meta: 0.9,
          tiktok: 1.0,
          google: 1.1,
        },
      };
      
      const recommendation = getBidRecommendation(mockMLPredictionHigh, 0.85, {}, config);
      
      // With custom adjustments, ratios should change
      expect(recommendation.platforms.meta.multiplier)
        .toBeLessThan(recommendation.platforms.tiktok.multiplier);
    });
  });

  describe('Edge Cases', () => {
    it('should handle all zero signals', () => {
      const recommendation = getBidRecommendation(null, 0.4);
      
      expect(recommendation.strategy).not.toBe('exclude'); // 0.4 > 0.3 threshold
      expect(recommendation.multiplier).toBeGreaterThan(0);
    });

    it('should handle perfect signals', () => {
      const perfectPrediction = {
        ...mockMLPredictionVIP,
        ltv_percentile: 100,
        propensity_7d: 1.0,
        churn_probability: 0,
      };
      
      const recommendation = getBidRecommendation(perfectPrediction, 1.0);
      
      expect(recommendation.strategy).toBe('aggressive');
      expect(recommendation.multiplier).toBe(2.0); // Max
      expect(recommendation.confidence).toBeGreaterThan(0.9);
    });

    it('should handle borderline trust score', () => {
      // Exactly at threshold
      const atThreshold = getBidRecommendation(mockMLPredictionVIP, 0.3);
      expect(atThreshold.strategy).not.toBe('exclude');
      
      // Just below threshold
      const belowThreshold = getBidRecommendation(mockMLPredictionVIP, 0.29);
      expect(belowThreshold.strategy).toBe('exclude');
    });
  });
});
