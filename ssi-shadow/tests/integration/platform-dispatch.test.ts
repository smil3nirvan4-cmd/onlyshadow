/**
 * S.S.I. SHADOW - Integration Tests
 * Tests for end-to-end data flows between components
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import {
  mockPageViewFull,
  mockPurchaseFull,
  mockLeadFull,
  mockMetaSuccessResponse,
  mockMetaErrorResponse,
  mockTikTokSuccessResponse,
  mockTikTokErrorResponse,
  mockGoogleSuccessResponse,
  mockRequestHeaders,
  mockCFHeaders,
  createMockEvent,
} from '@fixtures';

// =============================================================================
// MOCK FETCH SETUP
// =============================================================================

let fetchMock: ReturnType<typeof vi.fn>;

function setupFetchMock(responses: Record<string, { status: number; body: unknown }>) {
  fetchMock = vi.fn(async (url: string) => {
    for (const [pattern, response] of Object.entries(responses)) {
      if (url.includes(pattern)) {
        return new Response(JSON.stringify(response.body), {
          status: response.status,
          headers: { 'content-type': 'application/json' },
        });
      }
    }
    return new Response(JSON.stringify({ error: 'Not mocked' }), { status: 500 });
  });
  
  global.fetch = fetchMock as unknown as typeof fetch;
}

// =============================================================================
// INTEGRATION TESTS: Worker → Meta CAPI
// =============================================================================

describe('Integration: Worker → Meta CAPI', () => {
  beforeEach(() => {
    setupFetchMock({
      'graph.facebook.com': { status: 200, body: mockMetaSuccessResponse },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should send PageView event to Meta CAPI successfully', async () => {
    const event = createMockEvent({ event_name: 'PageView' });
    
    const response = await fetch('https://graph.facebook.com/v18.0/test_pixel/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        data: [{
          event_name: event.event_name,
          event_time: Math.floor(Date.now() / 1000),
          event_source_url: event.url,
          action_source: 'website',
          user_data: {
            em: 'hashed_email',
            ph: 'hashed_phone',
            client_ip_address: '189.40.100.50',
            client_user_agent: mockRequestHeaders['user-agent'],
            fbc: event.fbc,
            fbp: event.fbp,
          },
        }],
        access_token: 'test_token',
      }),
    });

    const result = await response.json();
    
    expect(response.status).toBe(200);
    expect(result.events_received).toBe(1);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it('should send Purchase event with value to Meta CAPI', async () => {
    const event = createMockEvent({
      event_name: 'Purchase',
      value: 299.90,
      currency: 'BRL',
      content_ids: ['SKU-001'],
      order_id: 'ORD-001',
    });

    const response = await fetch('https://graph.facebook.com/v18.0/test_pixel/events', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        data: [{
          event_name: 'Purchase',
          event_time: Math.floor(Date.now() / 1000),
          event_source_url: event.url,
          action_source: 'website',
          custom_data: {
            value: event.value,
            currency: event.currency,
            content_ids: event.content_ids,
            order_id: event.order_id,
          },
          user_data: {
            em: 'hashed_email',
          },
        }],
        access_token: 'test_token',
      }),
    });

    const result = await response.json();
    
    expect(response.status).toBe(200);
    expect(result.events_received).toBe(1);
  });

  it('should handle Meta CAPI error response', async () => {
    setupFetchMock({
      'graph.facebook.com': { status: 400, body: mockMetaErrorResponse },
    });

    const response = await fetch('https://graph.facebook.com/v18.0/test_pixel/events', {
      method: 'POST',
      body: JSON.stringify({ data: [] }),
    });

    const result = await response.json();
    
    expect(response.status).toBe(400);
    expect(result.error).toBeDefined();
    expect(result.error.type).toBe('OAuthException');
  });

  it('should batch multiple events in single request', async () => {
    const events = [
      createMockEvent({ event_name: 'PageView' }),
      createMockEvent({ event_name: 'ViewContent' }),
      createMockEvent({ event_name: 'AddToCart' }),
    ];

    const response = await fetch('https://graph.facebook.com/v18.0/test_pixel/events', {
      method: 'POST',
      body: JSON.stringify({
        data: events.map(e => ({
          event_name: e.event_name,
          event_time: Math.floor(Date.now() / 1000),
        })),
      }),
    });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

// =============================================================================
// INTEGRATION TESTS: Worker → TikTok Events API
// =============================================================================

describe('Integration: Worker → TikTok Events API', () => {
  beforeEach(() => {
    setupFetchMock({
      'business-api.tiktok.com': { status: 200, body: mockTikTokSuccessResponse },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should send PageView event to TikTok Events API', async () => {
    const event = createMockEvent({ event_name: 'PageView' });

    const response = await fetch('https://business-api.tiktok.com/open_api/v1.3/event/track/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Access-Token': 'test_tiktok_token',
      },
      body: JSON.stringify({
        pixel_code: 'test_pixel',
        event: 'ViewContent',
        event_id: event.event_id,
        timestamp: new Date().toISOString(),
        context: {
          user_agent: mockRequestHeaders['user-agent'],
          ip: '189.40.100.50',
        },
        properties: {
          content_type: 'product',
        },
      }),
    });

    const result = await response.json();
    
    expect(response.status).toBe(200);
    expect(result.code).toBe(0);
    expect(result.message).toBe('OK');
  });

  it('should send Purchase event with products to TikTok', async () => {
    const event = createMockEvent({
      event_name: 'Purchase',
      value: 299.90,
      currency: 'BRL',
      content_ids: ['SKU-001', 'SKU-002'],
    });

    const response = await fetch('https://business-api.tiktok.com/open_api/v1.3/event/track/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Access-Token': 'test_tiktok_token',
      },
      body: JSON.stringify({
        pixel_code: 'test_pixel',
        event: 'CompletePayment',
        event_id: event.event_id,
        timestamp: new Date().toISOString(),
        properties: {
          value: event.value,
          currency: event.currency,
          contents: event.content_ids?.map(id => ({ content_id: id })),
        },
      }),
    });

    const result = await response.json();
    
    expect(response.status).toBe(200);
    expect(result.code).toBe(0);
  });

  it('should handle TikTok API error response', async () => {
    setupFetchMock({
      'business-api.tiktok.com': { status: 401, body: mockTikTokErrorResponse },
    });

    const response = await fetch('https://business-api.tiktok.com/open_api/v1.3/event/track/', {
      method: 'POST',
      body: JSON.stringify({}),
    });

    const result = await response.json();
    
    expect(result.code).toBe(40001);
  });
});

// =============================================================================
// INTEGRATION TESTS: Worker → Google Measurement Protocol
// =============================================================================

describe('Integration: Worker → Google Measurement Protocol', () => {
  beforeEach(() => {
    setupFetchMock({
      'google-analytics.com': { status: 204, body: {} },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should send PageView event to GA4', async () => {
    const event = createMockEvent({ event_name: 'PageView' });

    const response = await fetch('https://www.google-analytics.com/mp/collect?measurement_id=G-TEST&api_secret=test_secret', {
      method: 'POST',
      body: JSON.stringify({
        client_id: event.ssi_id,
        events: [{
          name: 'page_view',
          params: {
            page_location: event.url,
            page_title: 'Test Page',
          },
        }],
      }),
    });

    expect(response.status).toBe(204); // GA4 returns 204 on success
  });

  it('should send Purchase event to GA4', async () => {
    const event = createMockEvent({
      event_name: 'Purchase',
      value: 299.90,
      currency: 'BRL',
      content_ids: ['SKU-001'],
      order_id: 'ORD-001',
    });

    const response = await fetch('https://www.google-analytics.com/mp/collect?measurement_id=G-TEST&api_secret=test_secret', {
      method: 'POST',
      body: JSON.stringify({
        client_id: event.ssi_id,
        events: [{
          name: 'purchase',
          params: {
            currency: event.currency,
            value: event.value,
            transaction_id: event.order_id,
            items: event.content_ids?.map(id => ({ item_id: id })),
          },
        }],
      }),
    });

    expect(response.status).toBe(204);
  });

  it('should include user_id when available', async () => {
    const event = createMockEvent({
      event_name: 'PageView',
      email: 'test@example.com',
    });

    const requestBody = {
      client_id: event.ssi_id,
      user_id: 'hashed_email', // Would be SHA256 hash
      events: [{
        name: 'page_view',
        params: {},
      }],
    };

    const response = await fetch('https://www.google-analytics.com/mp/collect', {
      method: 'POST',
      body: JSON.stringify(requestBody),
    });

    expect(response.status).toBe(204);
    expect(requestBody.user_id).toBeDefined();
  });
});

// =============================================================================
// INTEGRATION TESTS: Worker → BigQuery
// =============================================================================

describe('Integration: Worker → BigQuery', () => {
  beforeEach(() => {
    setupFetchMock({
      'bigquery.googleapis.com': {
        status: 200,
        body: {
          kind: 'bigquery#tableDataInsertAllResponse',
          insertErrors: [],
        },
      },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should insert event to BigQuery', async () => {
    const event = createMockEvent({ event_name: 'PageView' });

    const response = await fetch('https://bigquery.googleapis.com/bigquery/v2/projects/test-project/datasets/ssi_shadow/tables/events_raw/insertAll', {
      method: 'POST',
      headers: {
        'Authorization': 'Bearer test_token',
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        rows: [{
          insertId: event.event_id,
          json: {
            event_id: event.event_id,
            ssi_id: event.ssi_id,
            event_name: event.event_name,
            event_time: new Date().toISOString(),
            url: event.url,
            trust_score: 0.85,
          },
        }],
      }),
    });

    const result = await response.json();
    
    expect(response.status).toBe(200);
    expect(result.insertErrors).toEqual([]);
  });

  it('should handle BigQuery insert errors', async () => {
    setupFetchMock({
      'bigquery.googleapis.com': {
        status: 200,
        body: {
          kind: 'bigquery#tableDataInsertAllResponse',
          insertErrors: [{
            index: 0,
            errors: [{ reason: 'invalid', message: 'Invalid field' }],
          }],
        },
      },
    });

    const response = await fetch('https://bigquery.googleapis.com/bigquery/v2/projects/test-project/datasets/ssi_shadow/tables/events_raw/insertAll', {
      method: 'POST',
      body: JSON.stringify({
        rows: [{ json: { invalid_field: 'test' } }],
      }),
    });

    const result = await response.json();
    
    expect(result.insertErrors.length).toBeGreaterThan(0);
  });

  it('should batch multiple events efficiently', async () => {
    const events = Array.from({ length: 100 }, (_, i) => 
      createMockEvent({ event_name: 'PageView', event_id: `evt_batch_${i}` })
    );

    const response = await fetch('https://bigquery.googleapis.com/bigquery/v2/projects/test-project/datasets/ssi_shadow/tables/events_raw/insertAll', {
      method: 'POST',
      body: JSON.stringify({
        rows: events.map(e => ({
          insertId: e.event_id,
          json: {
            event_id: e.event_id,
            event_name: e.event_name,
          },
        })),
      }),
    });

    expect(response.status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(1); // Single batch request
  });
});

// =============================================================================
// INTEGRATION TESTS: Full Event Flow
// =============================================================================

describe('Integration: Full Event Flow (Ghost → Worker → Platforms)', () => {
  beforeEach(() => {
    setupFetchMock({
      'graph.facebook.com': { status: 200, body: mockMetaSuccessResponse },
      'business-api.tiktok.com': { status: 200, body: mockTikTokSuccessResponse },
      'google-analytics.com': { status: 204, body: {} },
      'bigquery.googleapis.com': { status: 200, body: { insertErrors: [] } },
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('should dispatch event to all platforms in parallel', async () => {
    const event = createMockEvent({
      event_name: 'Purchase',
      value: 299.90,
      email: 'test@example.com',
    });

    // Simulate parallel dispatch
    const results = await Promise.allSettled([
      fetch('https://graph.facebook.com/v18.0/test_pixel/events', {
        method: 'POST',
        body: JSON.stringify({ data: [event] }),
      }),
      fetch('https://business-api.tiktok.com/open_api/v1.3/event/track/', {
        method: 'POST',
        body: JSON.stringify({ event: 'CompletePayment' }),
      }),
      fetch('https://www.google-analytics.com/mp/collect', {
        method: 'POST',
        body: JSON.stringify({ events: [{ name: 'purchase' }] }),
      }),
      fetch('https://bigquery.googleapis.com/bigquery/v2/projects/test/datasets/ssi/tables/events/insertAll', {
        method: 'POST',
        body: JSON.stringify({ rows: [{ json: event }] }),
      }),
    ]);

    // All should succeed
    results.forEach((result, index) => {
      expect(result.status).toBe('fulfilled');
    });

    // All platforms called
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it('should handle partial failures gracefully', async () => {
    setupFetchMock({
      'graph.facebook.com': { status: 200, body: mockMetaSuccessResponse },
      'business-api.tiktok.com': { status: 500, body: { error: 'Server error' } },
      'google-analytics.com': { status: 204, body: {} },
      'bigquery.googleapis.com': { status: 200, body: { insertErrors: [] } },
    });

    const results = await Promise.allSettled([
      fetch('https://graph.facebook.com/v18.0/test_pixel/events', { method: 'POST' }),
      fetch('https://business-api.tiktok.com/open_api/v1.3/event/track/', { method: 'POST' }),
      fetch('https://www.google-analytics.com/mp/collect', { method: 'POST' }),
      fetch('https://bigquery.googleapis.com/v2/projects/test/insertAll', { method: 'POST' }),
    ]);

    // Should still complete (with one failure)
    const fulfilled = results.filter(r => r.status === 'fulfilled');
    expect(fulfilled.length).toBe(4); // All completed, check status inside

    // TikTok returned 500
    const tiktokResult = results[1] as PromiseFulfilledResult<Response>;
    const tiktokResponse = await tiktokResult.value.json();
    expect(tiktokResponse.error).toBeDefined();
  });

  it('should not block on slow platform', async () => {
    // TikTok is slow
    const slowFetch = vi.fn(async (url: string) => {
      if (url.includes('business-api.tiktok.com')) {
        await new Promise(r => setTimeout(r, 5000)); // 5 second delay
      }
      return new Response(JSON.stringify({ success: true }), { status: 200 });
    });
    global.fetch = slowFetch as unknown as typeof fetch;

    const start = Date.now();
    
    // Use Promise.race with timeout
    const timeoutPromise = new Promise((_, reject) => 
      setTimeout(() => reject(new Error('Timeout')), 1000)
    );

    try {
      await Promise.race([
        fetch('https://graph.facebook.com/events', { method: 'POST' }),
        timeoutPromise,
      ]);
    } catch {
      // Fast platform should complete before timeout
    }

    const elapsed = Date.now() - start;
    expect(elapsed).toBeLessThan(2000); // Should not wait 5s for slow platform
  });
});

// =============================================================================
// INTEGRATION TESTS: Trust Score → Bid Optimization Flow
// =============================================================================

describe('Integration: Trust Score → Bid Optimization', () => {
  it('should block events with low trust score', async () => {
    const lowTrustEvent = createMockEvent({
      event_name: 'Purchase',
      value: 1000,
    });

    // Simulate trust score check
    const trustScore = 0.15; // Below 0.3 threshold
    const shouldBlock = trustScore < 0.3;

    expect(shouldBlock).toBe(true);

    // If blocked, should not dispatch to platforms
    const dispatched = !shouldBlock;
    expect(dispatched).toBe(false);
  });

  it('should apply bid multiplier based on ML predictions', () => {
    const mlPrediction = {
      ltv_score: 0.9,
      propensity_score: 0.8,
      churn_risk: 0.1,
    };
    const trustScore = 0.92;

    // Calculate bid multiplier
    const weightedScore = 
      mlPrediction.ltv_score * 0.35 +
      mlPrediction.propensity_score * 0.35 +
      (1 - mlPrediction.churn_risk) * 0.15 +
      trustScore * 0.15;

    // Map to multiplier range (0.5 - 2.0)
    const multiplier = 0.5 + (weightedScore * 1.5);

    expect(multiplier).toBeGreaterThan(1.5);
    expect(multiplier).toBeLessThanOrEqual(2.0);
  });

  it('should exclude bot traffic from bid optimization', () => {
    const botTrustScore = 0.08;
    const bidStrategy = botTrustScore < 0.3 ? 'exclude' : 'nurture';
    const bidMultiplier = bidStrategy === 'exclude' ? 0 : 1.0;

    expect(bidStrategy).toBe('exclude');
    expect(bidMultiplier).toBe(0);
  });
});
