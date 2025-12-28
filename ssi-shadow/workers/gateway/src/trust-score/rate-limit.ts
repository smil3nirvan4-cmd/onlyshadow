// ============================================================================
// S.S.I. SHADOW - Rate Limiting with Cloudflare KV
// ============================================================================

import { RateLimitEntry, RateLimitResult } from '../types/trust';

/**
 * Rate limit configuration
 */
export interface RateLimitConfig {
  windowMs: number;      // Time window in milliseconds
  maxRequests: number;   // Max requests per window
  blockDuration: number; // How long to block (ms) after limit exceeded
}

/**
 * Default rate limit configurations
 */
export const RATE_LIMIT_CONFIGS = {
  // Per-IP rate limiting
  IP: {
    windowMs: 60 * 1000,        // 1 minute window
    maxRequests: 100,           // 100 requests per minute
    blockDuration: 5 * 60 * 1000, // Block for 5 minutes
  },
  
  // Per-fingerprint rate limiting (stricter)
  FINGERPRINT: {
    windowMs: 60 * 1000,        // 1 minute window
    maxRequests: 60,            // 60 requests per minute
    blockDuration: 10 * 60 * 1000, // Block for 10 minutes
  },
  
  // Burst protection (very short window)
  BURST: {
    windowMs: 1000,             // 1 second window
    maxRequests: 10,            // 10 requests per second
    blockDuration: 60 * 1000,   // Block for 1 minute
  },
} as const;

/**
 * Check rate limit for a given key
 * Uses Cloudflare KV for storage
 */
export async function checkRateLimit(
  kv: KVNamespace | undefined,
  key: string,
  config: RateLimitConfig
): Promise<RateLimitResult> {
  // If KV is not available, allow all
  if (!kv) {
    return {
      allowed: true,
      current: 0,
      limit: config.maxRequests,
      remaining: config.maxRequests,
      resetAt: Date.now() + config.windowMs,
      blocked: false,
    };
  }

  const now = Date.now();
  const kvKey = `rate:${key}`;

  try {
    // Get current entry
    const entryJson = await kv.get(kvKey);
    let entry: RateLimitEntry;

    if (entryJson) {
      entry = JSON.parse(entryJson);

      // Check if we're still blocked
      if (entry.blocked && now - entry.lastSeen < config.blockDuration) {
        return {
          allowed: false,
          current: entry.count,
          limit: config.maxRequests,
          remaining: 0,
          resetAt: entry.lastSeen + config.blockDuration,
          blocked: true,
        };
      }

      // Check if window has expired
      if (now - entry.firstSeen > config.windowMs) {
        // Start new window
        entry = {
          count: 1,
          firstSeen: now,
          lastSeen: now,
          blocked: false,
        };
      } else {
        // Increment count in current window
        entry.count++;
        entry.lastSeen = now;

        // Check if limit exceeded
        if (entry.count > config.maxRequests) {
          entry.blocked = true;
          
          await kv.put(kvKey, JSON.stringify(entry), {
            expirationTtl: Math.ceil(config.blockDuration / 1000) + 60,
          });

          return {
            allowed: false,
            current: entry.count,
            limit: config.maxRequests,
            remaining: 0,
            resetAt: now + config.blockDuration,
            blocked: true,
          };
        }
      }
    } else {
      // First request
      entry = {
        count: 1,
        firstSeen: now,
        lastSeen: now,
        blocked: false,
      };
    }

    // Store updated entry
    await kv.put(kvKey, JSON.stringify(entry), {
      expirationTtl: Math.ceil(config.windowMs / 1000) + 60,
    });

    const remaining = Math.max(0, config.maxRequests - entry.count);
    const resetAt = entry.firstSeen + config.windowMs;

    return {
      allowed: true,
      current: entry.count,
      limit: config.maxRequests,
      remaining,
      resetAt,
      blocked: false,
    };
  } catch (error) {
    // On error, allow the request but log
    console.error(`[RateLimit] Error checking rate limit: ${error}`);
    
    return {
      allowed: true,
      current: 0,
      limit: config.maxRequests,
      remaining: config.maxRequests,
      resetAt: now + config.windowMs,
      blocked: false,
    };
  }
}

/**
 * Check multiple rate limits in parallel
 */
export async function checkMultipleRateLimits(
  kv: KVNamespace | undefined,
  checks: Array<{ key: string; config: RateLimitConfig }>
): Promise<{ allowed: boolean; results: Map<string, RateLimitResult> }> {
  const results = new Map<string, RateLimitResult>();
  
  const checkPromises = checks.map(async ({ key, config }) => {
    const result = await checkRateLimit(kv, key, config);
    results.set(key, result);
    return result;
  });

  const allResults = await Promise.all(checkPromises);
  const allowed = allResults.every(r => r.allowed);

  return { allowed, results };
}

/**
 * Generate rate limit key for IP
 */
export function getRateLimitKeyIP(ip: string): string {
  return `ip:${ip}`;
}

/**
 * Generate rate limit key for fingerprint
 */
export function getRateLimitKeyFingerprint(
  canvasHash: string | null,
  webglRenderer: string | null
): string {
  const fingerprint = [canvasHash, webglRenderer].filter(Boolean).join(':');
  return `fp:${fingerprint || 'unknown'}`;
}

/**
 * Generate rate limit key for session
 */
export function getRateLimitKeySession(sessionId: string): string {
  return `sess:${sessionId}`;
}

/**
 * Clear rate limit for a key (for testing/admin)
 */
export async function clearRateLimit(
  kv: KVNamespace,
  key: string
): Promise<void> {
  await kv.delete(`rate:${key}`);
}

/**
 * Get current rate limit status without incrementing
 */
export async function getRateLimitStatus(
  kv: KVNamespace | undefined,
  key: string,
  config: RateLimitConfig
): Promise<RateLimitResult | null> {
  if (!kv) return null;

  try {
    const kvKey = `rate:${key}`;
    const entryJson = await kv.get(kvKey);
    
    if (!entryJson) return null;

    const entry: RateLimitEntry = JSON.parse(entryJson);
    const now = Date.now();

    // Check if window has expired
    if (now - entry.firstSeen > config.windowMs) {
      return null; // Window expired
    }

    return {
      allowed: entry.count <= config.maxRequests && !entry.blocked,
      current: entry.count,
      limit: config.maxRequests,
      remaining: Math.max(0, config.maxRequests - entry.count),
      resetAt: entry.firstSeen + config.windowMs,
      blocked: entry.blocked,
    };
  } catch {
    return null;
  }
}

/**
 * Log rate limit event for analytics
 */
export function logRateLimitEvent(
  key: string,
  result: RateLimitResult,
  userAgent: string
): void {
  if (!result.allowed) {
    console.log(`[RateLimit] Blocked: ${key}`, {
      current: result.current,
      limit: result.limit,
      blocked: result.blocked,
      userAgent: userAgent.substring(0, 100),
    });
  }
}
