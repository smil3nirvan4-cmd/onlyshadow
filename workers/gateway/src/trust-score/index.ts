// ============================================================================
// S.S.I. SHADOW - Trust Score Module
// ============================================================================
// Heuristic bot detection and trust scoring
// 
// Usage:
//   const trustResult = await calculateTrustScore(request, event, env);
//   if (trustResult.action === 'block') {
//     // Don't send to CAPI
//   }

import { IncomingEvent, Env } from '../types';
import {
  TrustScore,
  TrustSignals,
  TrustAction,
  TrustCategory,
  TrustReason,
  TrustFlag,
  TRUST_THRESHOLDS,
  SCORE_ADJUSTMENTS,
} from '../types/trust';
import { extractSignals, hashIP } from './signals';
import { applyRules, sortReasonsBySeverity } from './rules';
import {
  checkRateLimit,
  RATE_LIMIT_CONFIGS,
  getRateLimitKeyIP,
  getRateLimitKeyFingerprint,
  logRateLimitEvent,
} from './rate-limit';

// Re-export types and utilities
export * from '../types/trust';
export * from './signals';
export * from './rules';
export * from './rate-limit';

/**
 * Calculate trust score for a request
 */
export async function calculateTrustScore(
  request: Request,
  event: IncomingEvent,
  env: Env
): Promise<TrustScore> {
  const startTime = Date.now();

  // Extract signals from request and event
  const signals = extractSignals(request, event);

  // Apply scoring rules
  const { reasons, flags, totalAdjustment } = applyRules(signals);

  // Check rate limits
  const rateLimitResult = await checkRateLimits(signals, env, reasons, flags);

  // Calculate base score (start at 1.0 = fully trusted)
  let score = 1.0 + totalAdjustment + rateLimitResult.adjustment;

  // Clamp score to [0, 1]
  score = Math.max(0, Math.min(1, score));

  // Determine action based on thresholds
  const action = determineAction(score);

  // Determine category
  const category = determineCategory(score);

  // Calculate confidence based on number of signals
  const confidence = calculateConfidence(signals, reasons);

  // Sort reasons by severity
  const sortedReasons = sortReasonsBySeverity([...reasons, ...rateLimitResult.reasons]);

  const trustScore: TrustScore = {
    score: Math.round(score * 1000) / 1000, // Round to 3 decimals
    confidence: Math.round(confidence * 100) / 100,
    action,
    category,
    reasons: sortedReasons,
    flags: [...new Set([...flags, ...rateLimitResult.flags])], // Dedupe flags
  };

  // Log for debugging/monitoring
  logTrustScore(trustScore, signals, Date.now() - startTime);

  return trustScore;
}

/**
 * Check rate limits and return adjustment
 */
async function checkRateLimits(
  signals: TrustSignals,
  env: Env,
  reasons: TrustReason[],
  flags: TrustFlag[]
): Promise<{
  adjustment: number;
  reasons: TrustReason[];
  flags: TrustFlag[];
}> {
  const kv = env.RATE_LIMIT;
  const newReasons: TrustReason[] = [];
  const newFlags: TrustFlag[] = [];
  let adjustment = 0;

  // Check IP rate limit
  if (signals.ip) {
    const ipKey = getRateLimitKeyIP(signals.ip);
    const ipResult = await checkRateLimit(kv, ipKey, RATE_LIMIT_CONFIGS.IP);

    if (!ipResult.allowed) {
      adjustment += SCORE_ADJUSTMENTS.RATE_LIMIT_EXCEEDED;
      newReasons.push({
        code: 'RATE_LIMIT_EXCEEDED',
        description: `IP rate limit exceeded: ${ipResult.current}/${ipResult.limit} requests`,
        impact: SCORE_ADJUSTMENTS.RATE_LIMIT_EXCEEDED,
        severity: 'critical',
      });
      newFlags.push('rate_limited');
      logRateLimitEvent(ipKey, ipResult, signals.userAgent);
    }
  }

  // Check fingerprint rate limit (if available)
  if (signals.canvasHash || signals.webglRenderer) {
    const fpKey = getRateLimitKeyFingerprint(signals.canvasHash, signals.webglRenderer);
    const fpResult = await checkRateLimit(kv, fpKey, RATE_LIMIT_CONFIGS.FINGERPRINT);

    if (!fpResult.allowed && !newFlags.includes('rate_limited')) {
      adjustment += SCORE_ADJUSTMENTS.RATE_LIMIT_EXCEEDED * 0.5; // Less severe than IP
      newReasons.push({
        code: 'FINGERPRINT_RATE_LIMIT',
        description: `Fingerprint rate limit exceeded: ${fpResult.current}/${fpResult.limit} requests`,
        impact: SCORE_ADJUSTMENTS.RATE_LIMIT_EXCEEDED * 0.5,
        severity: 'high',
      });
      newFlags.push('rate_limited');
    }
  }

  return { adjustment, reasons: newReasons, flags: newFlags };
}

/**
 * Determine action based on score
 */
function determineAction(score: number): TrustAction {
  if (score < TRUST_THRESHOLDS.BLOCK) {
    return 'block';
  } else if (score < TRUST_THRESHOLDS.CHALLENGE) {
    return 'challenge';
  } else {
    return 'allow';
  }
}

/**
 * Determine category based on score
 */
function determineCategory(score: number): TrustCategory {
  if (score >= 0.9) return 'human';
  if (score >= 0.7) return 'likely_human';
  if (score >= 0.5) return 'uncertain';
  if (score >= 0.3) return 'likely_bot';
  return 'bot';
}

/**
 * Calculate confidence in the score
 * Higher when we have more signals to work with
 */
function calculateConfidence(signals: TrustSignals, reasons: TrustReason[]): number {
  let signalCount = 0;
  const maxSignals = 20;

  // Count available signals
  if (signals.userAgent) signalCount++;
  if (signals.ip) signalCount++;
  if (signals.acceptLanguage) signalCount++;
  if (signals.acceptEncoding) signalCount++;
  if (signals.secChUa) signalCount += 2; // Client hints are valuable
  if (signals.cfIpAsn) signalCount++;
  if (signals.cfTlsVersion) signalCount++;
  if (signals.canvasHash) signalCount++;
  if (signals.webglRenderer) signalCount++;
  if (signals.scrollDepth !== null) signalCount += 2;
  if (signals.timeOnPage !== null) signalCount++;
  if (signals.clicks !== null) signalCount++;

  // More reasons = more confidence in the assessment
  const reasonBonus = Math.min(reasons.length * 0.05, 0.2);

  // Calculate base confidence from signal count
  const baseConfidence = Math.min(signalCount / maxSignals, 1);

  return Math.min(baseConfidence + reasonBonus, 1);
}

/**
 * Log trust score for monitoring
 */
function logTrustScore(
  trustScore: TrustScore,
  signals: TrustSignals,
  processingTimeMs: number
): void {
  const logData = {
    score: trustScore.score,
    action: trustScore.action,
    category: trustScore.category,
    confidence: trustScore.confidence,
    flags: trustScore.flags,
    reasonCodes: trustScore.reasons.map(r => r.code),
    processingTimeMs,
    ip: signals.ip ? hashIP(signals.ip) : null, // Hash IP for privacy
    asn: signals.cfIpAsn,
    country: signals.cfIpCountry,
  };

  if (trustScore.action === 'block') {
    console.warn('[TrustScore] Blocked:', JSON.stringify(logData));
  } else if (trustScore.action === 'challenge') {
    console.log('[TrustScore] Challenge:', JSON.stringify(logData));
  } else if (process.env.SSI_DEBUG) {
    console.log('[TrustScore] Allowed:', JSON.stringify(logData));
  }
}

/**
 * Quick check if request should be immediately blocked
 * Use this for fast rejection before full scoring
 */
export function quickBotCheck(request: Request): { isBot: boolean; reason: string | null } {
  const userAgent = request.headers.get('User-Agent') || '';
  const uaLower = userAgent.toLowerCase();

  // Check for obvious bot indicators
  const criticalBotKeywords = [
    'bot', 'crawler', 'spider', 'curl', 'wget',
    'python-requests', 'python-urllib', 'scrapy',
    'headlesschrome', 'phantomjs',
  ];

  for (const keyword of criticalBotKeywords) {
    if (uaLower.includes(keyword)) {
      return { isBot: true, reason: `Bot keyword: ${keyword}` };
    }
  }

  // Check for missing User-Agent
  if (!userAgent) {
    return { isBot: true, reason: 'Missing User-Agent' };
  }

  return { isBot: false, reason: null };
}

/**
 * Create a minimal trust score for blocked requests
 */
export function createBlockedTrustScore(reason: string): TrustScore {
  return {
    score: 0,
    confidence: 1,
    action: 'block',
    category: 'bot',
    reasons: [{
      code: 'QUICK_BLOCK',
      description: reason,
      impact: -1,
      severity: 'critical',
    }],
    flags: ['bot_user_agent'],
  };
}

/**
 * Should this event be sent to CAPI?
 * Combines trust score with configuration
 */
export function shouldSendToCAPI(
  trustScore: TrustScore,
  env: Env
): { send: boolean; reason: string } {
  const threshold = parseFloat(env.TRUST_SCORE_THRESHOLD || '0.3');

  if (trustScore.action === 'block') {
    return {
      send: false,
      reason: `Blocked: score ${trustScore.score} < threshold ${threshold}`,
    };
  }

  if (trustScore.action === 'challenge') {
    // For challenge, we might still send but flag it
    return {
      send: true,
      reason: `Challenge: score ${trustScore.score}, sending with flag`,
    };
  }

  return {
    send: true,
    reason: 'Allowed',
  };
}

/**
 * Get summary stats for trust scores (for dashboard)
 */
export function getTrustScoreSummary(trustScore: TrustScore): {
  isBot: boolean;
  isSuspicious: boolean;
  isHuman: boolean;
  topReasons: string[];
} {
  return {
    isBot: trustScore.category === 'bot' || trustScore.category === 'likely_bot',
    isSuspicious: trustScore.category === 'uncertain' || trustScore.action === 'challenge',
    isHuman: trustScore.category === 'human' || trustScore.category === 'likely_human',
    topReasons: trustScore.reasons
      .filter(r => r.severity === 'critical' || r.severity === 'high')
      .slice(0, 3)
      .map(r => r.code),
  };
}
