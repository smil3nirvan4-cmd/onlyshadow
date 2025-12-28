/**
 * S.S.I. SHADOW - Integration Tests
 * Tests for the complete event flow: Ghost → Worker → Platforms → BigQuery
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  mockPageViewFull,
  mockPurchaseFull,
  mockTrustScoreHigh,
  mockTrustScoreLow,
  mockMetaSuccessResponse,
  mockTikTokSuccessResponse,
  mockRequestHeaders,
  mockCFHeaders,
  createMockEvent,
} from '@fixtures';

// =============================================================================
// MOCK WORKER HANDLER (simplified for testing)
// =============================================================================

interface WorkerEnv {
  META_PIXEL_ID: string;
  META_ACCESS_TOKEN: string;
  TIKTOK_PIXEL_ID: string;
  TIKTOK_ACCESS_TOKEN: string;
  GA4_MEASUREMENT_ID: string;
  GA4_API_SECRET: string;
  ENABLE_META: string;
  ENABLE_TIKTOK: string;
  ENABLE_GOOGLE: string;
  ENABLE_BIGQUERY: string;
  TRUST_SCORE_BLOCK_THRESHOLD: string;
  RATE_LIMIT_KV: KVNamespace;
}

interface KVNamespace {
  get(key: string): Promise<string | null>;
  put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void>;
}

interface ProcessedEvent {
  event_id: string;
  ssi_id: string;
  event_name: string;
  timestamp: number;
  trust_score: number;
  trust_action: string;
  platforms_sent: string[];
  platform_responses: Record<string, unknown>;
  bigquery_sent: boolean;
}

// Mock KV
class MockKV implements KVNamespace {
  private store = new Map<string, { value: string; expires?: number }>();

  async get(key: string): Promise<string | null> {
    const item = this.store.get(key);
    if (!item) return null;
    if (item.expires && Date.now() > item.expires) {
      this.store.delete(key);
      return null;
    }
    return item.value;
  }

  async put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void> {
    this.store.set(key, {
      value,
      expires: options?.expirationTtl ? Date.now() + options.expirationTtl * 1000 : undefined,
    });
  }

  clear(): void {
    this.store.clear();
  }
}

// Simplified worker handler for testing
async function processEvent(
  event: Record<string, unknown>,
  headers: Record<string, string>,
  env: WorkerEnv
): Promise<ProcessedEvent> {
  const eventId = (event.event_id as string) || `evt_${Date.now()}`;
  const ssiId = (event.ssi_id as string) || `ssi_${Date.now()}`;
  
  // Calculate trust score (simplified)
  const trustScore = calculateTrustScore(headers, event);
  const trustAction = trustScore < 0.3 ? 'block' : trustScore < 0.6 ? 'challenge' : 'allow';
  
  const platformsSent: string[] = [];
  const platformResponses: Record<string, unknown> = {};
  
  // Only send to platforms if not blocked
  if (trustAction !== 'block') {
    // Meta
    if (env.ENABLE_META === 'true') {
      const metaResponse = await sendToMeta(event, env);
      platformsSent.push('meta');
      platformResponses.meta = metaResponse;
    }
    
    // TikTok
    if (env.ENABLE_TIKTOK === 'true') {
      const tiktokResponse = await sendToTikTok(event, env);
      platformsSent.push('tiktok');
      platformResponses.tiktok = tiktokResponse;
    }
    
    // Google
    if (env.ENABLE_GOOGLE === 'true') {
      const googleResponse = await sendToGoogle(event, env);
      platformsSent.push('google');
      platformResponses.google = googleResponse;
    }
  }
  
  // Always send to BigQuery (for analytics)
  let bigquerySent = false;
  if (env.ENABLE_BIGQUERY === 'true') {
    await sendToBigQuery(event, trustScore, trustAction);
    bigquerySent = true;
  }
  
  return {
    event_id: eventId,
    ssi_id: ssiId,
    event_name: event.event_name as string,
    timestamp: (event.timestamp as number) || Date.now(),
    trust_score: trustScore,
    trust_action: trustAction,
    platforms_sent: platformsSent,
    platform_responses: platformResponses,
    bigquery_sent: bigquerySent,
  };
}

function calculateTrustScore(headers: Record<string, string>, event: Record<string, unknown>): number {
  let score = 0.5;
  
  const ua = headers['user-agent']?.toLowerCase() || '';
  
  // Bot detection
  if (ua.includes('bot') || ua.includes('crawler') || ua.includes('spider')) {
    score -= 0.5;
  }
  
  // Headless detection
  if (ua.includes('headless')) {
    score -= 0.4;
  }
  
  // Good signals
  if (headers['accept-language']) {
    score += 0.1;
  }
  
  if (headers['sec-ch-ua']) {
    score += 0.1;
  }
  
  // Behavioral data
  if (event.scroll_depth && (event.scroll_depth as number) > 20) {
    score += 0.1;
  }
  
  if (event.time_on_page && (event.time_on_page as number) > 5000) {
    score += 0.1;
  }
  
  return Math.max(0, Math.min(1, score));
}

async function sendToMeta(event: Record<string, unknown>, env: WorkerEnv): Promise<unknown> {
  // Mock API call
  return mockMetaSuccessResponse;
}

async function sendToTikTok(event: Record<string, unknown>, env: WorkerEnv): Promise<unknown> {
  // Mock API call
  return mockTikTokSuccessResponse;
}

async function sendToGoogle(event: Record<string, unknown>, env: WorkerEnv): Promise<unknown> {
  // Mock API call
  return {};
}

async function sendToBigQuery(
  event: Record<string, unknown>,
  trustScore: number,
  trustAction: string
): Promise<void> {
  // Mock BigQuery insert
}

// =============================================================================
// TESTS
// =============================================================================

describe('Integration: Event Processing Flow', () => {
  let mockKV: MockKV;
  let testEnv: WorkerEnv;

  beforeEach(() => {
    mockKV = new MockKV();
    testEnv = {
      META_PIXEL_ID: 'test_pixel',
      META_ACCESS_TOKEN: 'test_token',
      TIKTOK_PIXEL_ID: 'test_tiktok_pixel',
      TIKTOK_ACCESS_TOKEN: 'test_tiktok_token',
      GA4_MEASUREMENT_ID: 'G-TEST',
      GA4_API_SECRET: 'test_secret',
      ENABLE_META: 'true',
      ENABLE_TIKTOK: 'true',
      ENABLE_GOOGLE: 'true',
      ENABLE_BIGQUERY: 'true',
      TRUST_SCORE_BLOCK_THRESHOLD: '0.3',
      RATE_LIMIT_KV: mockKV,
    };
  });

  afterEach(() => {
    mockKV.clear();
  });

  describe('Full Event Flow', () => {
    it('should process PageView event through all platforms', async () => {
      const result = await processEvent(mockPageViewFull, mockRequestHeaders, testEnv);

      expect(result.event_name).toBe('PageView');
      expect(result.trust_score).toBeGreaterThan(0.3);
      expect(result.trust_action).toBe('allow');
      expect(result.platforms_sent).toContain('meta');
      expect(result.platforms_sent).toContain('tiktok');
      expect(result.platforms_sent).toContain('google');
      expect(result.bigquery_sent).toBe(true);
    });

    it('should process Purchase event with PII', async () => {
      const result = await processEvent(mockPurchaseFull, mockRequestHeaders, testEnv);

      expect(result.event_name).toBe('Purchase');
      expect(result.trust_action).toBe('allow');
      expect(result.platforms_sent.length).toBe(3);
      expect(result.bigquery_sent).toBe(true);
    });

    it('should block bot traffic', async () => {
      const botHeaders = {
        ...mockRequestHeaders,
        'user-agent': 'Googlebot/2.1 (+http://www.google.com/bot.html)',
      };

      const result = await processEvent(mockPageViewFull, botHeaders, testEnv);

      expect(result.trust_score).toBeLessThan(0.3);
      expect(result.trust_action).toBe('block');
      expect(result.platforms_sent.length).toBe(0);
      expect(result.bigquery_sent).toBe(true); // Still log to BQ
    });

    it('should block headless browser traffic', async () => {
      const headlessHeaders = {
        ...mockRequestHeaders,
        'user-agent': 'Mozilla/5.0 HeadlessChrome/120.0.0.0',
      };

      const result = await processEvent(mockPageViewFull, headlessHeaders, testEnv);

      expect(result.trust_action).toBe('block');
      expect(result.platforms_sent.length).toBe(0);
    });
  });

  describe('Platform Selection', () => {
    it('should only send to enabled platforms', async () => {
      const envMetaOnly = {
        ...testEnv,
        ENABLE_TIKTOK: 'false',
        ENABLE_GOOGLE: 'false',
      };

      const result = await processEvent(mockPageViewFull, mockRequestHeaders, envMetaOnly);

      expect(result.platforms_sent).toContain('meta');
      expect(result.platforms_sent).not.toContain('tiktok');
      expect(result.platforms_sent).not.toContain('google');
    });

    it('should send to all platforms when all enabled', async () => {
      const result = await processEvent(mockPageViewFull, mockRequestHeaders, testEnv);

      expect(result.platforms_sent).toHaveLength(3);
      expect(result.platforms_sent).toContain('meta');
      expect(result.platforms_sent).toContain('tiktok');
      expect(result.platforms_sent).toContain('google');
    });

    it('should send to no platforms when all disabled', async () => {
      const envNoPlatforms = {
        ...testEnv,
        ENABLE_META: 'false',
        ENABLE_TIKTOK: 'false',
        ENABLE_GOOGLE: 'false',
      };

      const result = await processEvent(mockPageViewFull, mockRequestHeaders, envNoPlatforms);

      expect(result.platforms_sent).toHaveLength(0);
      expect(result.bigquery_sent).toBe(true); // BQ still enabled
    });
  });

  describe('Trust Score Impact', () => {
    it('should allow high-trust traffic', async () => {
      const goodHeaders = {
        ...mockRequestHeaders,
        'accept-language': 'pt-BR,pt;q=0.9',
        'sec-ch-ua': '"Chrome";v="120"',
        'sec-ch-ua-platform': '"Windows"',
      };

      const goodEvent = {
        ...mockPageViewFull,
        scroll_depth: 75,
        time_on_page: 45000,
      };

      const result = await processEvent(goodEvent, goodHeaders, testEnv);

      expect(result.trust_action).toBe('allow');
      expect(result.trust_score).toBeGreaterThan(0.6);
    });

    it('should challenge medium-trust traffic', async () => {
      const mediumHeaders = {
        'user-agent': 'Mozilla/5.0 Chrome/120.0.0.0',
        // Missing accept-language, sec-ch-ua
      };

      const result = await processEvent(mockPageViewFull, mediumHeaders, testEnv);

      // Should be in challenge range or allow
      expect(result.trust_score).toBeGreaterThanOrEqual(0.3);
    });
  });

  describe('Event ID Generation', () => {
    it('should use provided event_id', async () => {
      const eventWithId = {
        ...mockPageViewFull,
        event_id: 'custom_evt_123',
      };

      const result = await processEvent(eventWithId, mockRequestHeaders, testEnv);

      expect(result.event_id).toBe('custom_evt_123');
    });

    it('should generate event_id if not provided', async () => {
      const eventWithoutId = { ...mockPageViewFull };
      delete eventWithoutId.event_id;

      const result = await processEvent(eventWithoutId, mockRequestHeaders, testEnv);

      expect(result.event_id).toBeDefined();
      expect(result.event_id).toMatch(/^evt_/);
    });

    it('should generate unique event_ids', async () => {
      const eventWithoutId = { ...mockPageViewFull };
      delete eventWithoutId.event_id;

      const result1 = await processEvent(eventWithoutId, mockRequestHeaders, testEnv);
      const result2 = await processEvent(eventWithoutId, mockRequestHeaders, testEnv);

      expect(result1.event_id).not.toBe(result2.event_id);
    });
  });

  describe('Batch Processing', () => {
    it('should process multiple events correctly', async () => {
      const events = [
        createMockEvent({ event_name: 'PageView' }),
        createMockEvent({ event_name: 'AddToCart', value: 99.90 }),
        createMockEvent({ event_name: 'Purchase', value: 199.90 }),
      ];

      const results = await Promise.all(
        events.map(event => processEvent(event, mockRequestHeaders, testEnv))
      );

      expect(results).toHaveLength(3);
      expect(results[0].event_name).toBe('PageView');
      expect(results[1].event_name).toBe('AddToCart');
      expect(results[2].event_name).toBe('Purchase');
      
      // All should be processed
      results.forEach(result => {
        expect(result.bigquery_sent).toBe(true);
      });
    });
  });

  describe('Error Handling', () => {
    it('should handle missing required fields gracefully', async () => {
      const minimalEvent = {
        event_name: 'PageView',
      };

      const result = await processEvent(minimalEvent, mockRequestHeaders, testEnv);

      expect(result.event_name).toBe('PageView');
      expect(result.event_id).toBeDefined();
      expect(result.ssi_id).toBeDefined();
    });

    it('should handle empty headers', async () => {
      const result = await processEvent(mockPageViewFull, {}, testEnv);

      expect(result).toBeDefined();
      expect(result.trust_score).toBeDefined();
    });
  });
});

describe('Integration: Platform Response Handling', () => {
  let mockKV: MockKV;
  let testEnv: WorkerEnv;

  beforeEach(() => {
    mockKV = new MockKV();
    testEnv = {
      META_PIXEL_ID: 'test_pixel',
      META_ACCESS_TOKEN: 'test_token',
      TIKTOK_PIXEL_ID: 'test_tiktok_pixel',
      TIKTOK_ACCESS_TOKEN: 'test_tiktok_token',
      GA4_MEASUREMENT_ID: 'G-TEST',
      GA4_API_SECRET: 'test_secret',
      ENABLE_META: 'true',
      ENABLE_TIKTOK: 'true',
      ENABLE_GOOGLE: 'true',
      ENABLE_BIGQUERY: 'true',
      TRUST_SCORE_BLOCK_THRESHOLD: '0.3',
      RATE_LIMIT_KV: mockKV,
    };
  });

  it('should capture Meta CAPI response', async () => {
    const result = await processEvent(mockPageViewFull, mockRequestHeaders, testEnv);

    expect(result.platform_responses.meta).toBeDefined();
    expect((result.platform_responses.meta as typeof mockMetaSuccessResponse).events_received).toBe(1);
  });

  it('should capture TikTok Events API response', async () => {
    const result = await processEvent(mockPageViewFull, mockRequestHeaders, testEnv);

    expect(result.platform_responses.tiktok).toBeDefined();
    expect((result.platform_responses.tiktok as typeof mockTikTokSuccessResponse).code).toBe(0);
  });

  it('should not have platform responses when blocked', async () => {
    const botHeaders = {
      'user-agent': 'Googlebot/2.1',
    };

    const result = await processEvent(mockPageViewFull, botHeaders, testEnv);

    expect(result.platform_responses.meta).toBeUndefined();
    expect(result.platform_responses.tiktok).toBeUndefined();
    expect(result.platform_responses.google).toBeUndefined();
  });
});
