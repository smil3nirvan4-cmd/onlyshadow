/**
 * S.S.I. SHADOW - Test Setup
 * Global setup for all test suites
 */

import { vi, beforeAll, afterAll, afterEach } from 'vitest';

// =============================================================================
// GLOBAL MOCKS
// =============================================================================

// Mock crypto.subtle for SHA-256 hashing
const mockSubtle = {
  digest: vi.fn(async (algorithm: string, data: ArrayBuffer) => {
    // Simple mock hash - in real tests use actual crypto
    const view = new Uint8Array(data);
    const hash = new Uint8Array(32);
    for (let i = 0; i < view.length; i++) {
      hash[i % 32] ^= view[i];
    }
    return hash.buffer;
  }),
};

// Mock crypto.randomUUID
const mockRandomUUID = vi.fn(() => {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = Math.random() * 16 | 0;
    const v = c === 'x' ? r : (r & 0x3 | 0x8);
    return v.toString(16);
  });
});

// Global crypto mock
global.crypto = {
  subtle: mockSubtle as unknown as SubtleCrypto,
  randomUUID: mockRandomUUID,
  getRandomValues: <T extends ArrayBufferView | null>(array: T): T => {
    if (array) {
      const view = new Uint8Array(array.buffer, array.byteOffset, array.byteLength);
      for (let i = 0; i < view.length; i++) {
        view[i] = Math.floor(Math.random() * 256);
      }
    }
    return array;
  },
} as Crypto;

// =============================================================================
// FETCH MOCKS
// =============================================================================

// Store original fetch
const originalFetch = global.fetch;

// Mock fetch responses
const mockFetchResponses = new Map<string, { status: number; body: unknown }>();

export function mockFetch(url: string, response: { status: number; body: unknown }) {
  mockFetchResponses.set(url, response);
}

export function clearFetchMocks() {
  mockFetchResponses.clear();
}

// Mock fetch implementation
global.fetch = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
  const url = typeof input === 'string' ? input : input.toString();
  
  // Check for mocked response
  for (const [pattern, response] of mockFetchResponses) {
    if (url.includes(pattern)) {
      return new Response(JSON.stringify(response.body), {
        status: response.status,
        headers: { 'content-type': 'application/json' },
      });
    }
  }
  
  // Default responses for known APIs
  if (url.includes('graph.facebook.com')) {
    return new Response(JSON.stringify({
      events_received: 1,
      messages: [],
      fbtrace_id: 'test_trace_id',
    }), { status: 200 });
  }
  
  if (url.includes('business-api.tiktok.com')) {
    return new Response(JSON.stringify({
      code: 0,
      message: 'OK',
      data: { failed_events: [] },
    }), { status: 200 });
  }
  
  if (url.includes('google-analytics.com') || url.includes('analytics.google.com')) {
    return new Response('', { status: 204 });
  }
  
  if (url.includes('bigquery.googleapis.com')) {
    return new Response(JSON.stringify({
      kind: 'bigquery#tableDataInsertAllResponse',
      insertErrors: [],
    }), { status: 200 });
  }
  
  // Fallback to original fetch for unmocked URLs (or throw)
  console.warn(`[Test] Unmocked fetch to: ${url}`);
  return new Response(JSON.stringify({ error: 'Not mocked' }), { status: 500 });
}) as typeof fetch;

// =============================================================================
// CLOUDFLARE WORKERS MOCKS
// =============================================================================

// Mock Request with CF properties
export function createMockCFRequest(
  url: string,
  init?: RequestInit & { cf?: Record<string, unknown> }
): Request {
  const request = new Request(url, init);
  
  // Add CF-specific properties
  Object.defineProperty(request, 'cf', {
    value: {
      asn: 12345,
      asOrganization: 'Test ISP',
      city: 'São Paulo',
      country: 'BR',
      continent: 'SA',
      latitude: '-23.5505',
      longitude: '-46.6333',
      region: 'São Paulo',
      regionCode: 'SP',
      timezone: 'America/Sao_Paulo',
      tlsVersion: 'TLSv1.3',
      tlsCipher: 'AEAD-AES256-GCM-SHA384',
      httpProtocol: 'HTTP/2',
      ...init?.cf,
    },
    writable: false,
  });
  
  return request;
}

// Mock KV Namespace
export class MockKVNamespace {
  private store = new Map<string, { value: string; expiration?: number }>();
  
  async get(key: string, options?: { type?: 'text' | 'json' | 'arrayBuffer' | 'stream' }): Promise<string | null> {
    const item = this.store.get(key);
    if (!item) return null;
    if (item.expiration && Date.now() > item.expiration) {
      this.store.delete(key);
      return null;
    }
    return item.value;
  }
  
  async put(key: string, value: string, options?: { expirationTtl?: number }): Promise<void> {
    const expiration = options?.expirationTtl 
      ? Date.now() + options.expirationTtl * 1000 
      : undefined;
    this.store.set(key, { value, expiration });
  }
  
  async delete(key: string): Promise<void> {
    this.store.delete(key);
  }
  
  async list(options?: { prefix?: string; limit?: number }): Promise<{ keys: Array<{ name: string }> }> {
    const keys = Array.from(this.store.keys())
      .filter(k => !options?.prefix || k.startsWith(options.prefix))
      .slice(0, options?.limit || 1000)
      .map(name => ({ name }));
    return { keys };
  }
  
  // Helper for tests
  clear(): void {
    this.store.clear();
  }
}

// =============================================================================
// ENVIRONMENT MOCKS
// =============================================================================

export const mockEnv = {
  // Meta
  META_PIXEL_ID: 'test_pixel_id',
  META_ACCESS_TOKEN: 'test_access_token',
  META_TEST_EVENT_CODE: 'TEST12345',
  ENABLE_META: 'true',
  
  // TikTok
  TIKTOK_PIXEL_ID: 'test_tiktok_pixel',
  TIKTOK_ACCESS_TOKEN: 'test_tiktok_token',
  TIKTOK_TEST_EVENT_CODE: 'TEST_TIKTOK',
  ENABLE_TIKTOK: 'true',
  
  // Google
  GA4_MEASUREMENT_ID: 'G-TESTID',
  GA4_API_SECRET: 'test_ga4_secret',
  ENABLE_GOOGLE: 'true',
  
  // BigQuery
  GCP_PROJECT_ID: 'test-project',
  BQ_DATASET_ID: 'ssi_shadow',
  GCP_SERVICE_ACCOUNT: '{}',
  ENABLE_BIGQUERY: 'true',
  
  // Trust Score
  TRUST_SCORE_BLOCK_THRESHOLD: '0.3',
  TRUST_SCORE_CHALLENGE_THRESHOLD: '0.6',
  
  // KV Namespaces
  RATE_LIMIT_KV: new MockKVNamespace(),
  
  // Feature flags
  ENABLE_ML_PREDICTIONS: 'true',
  ENABLE_BID_OPTIMIZATION: 'true',
};

// =============================================================================
// LIFECYCLE HOOKS
// =============================================================================

beforeAll(() => {
  // Setup before all tests
  console.log('[Test Setup] Initializing test environment...');
});

afterEach(() => {
  // Clear mocks after each test
  vi.clearAllMocks();
  clearFetchMocks();
  
  // Clear KV
  if (mockEnv.RATE_LIMIT_KV instanceof MockKVNamespace) {
    mockEnv.RATE_LIMIT_KV.clear();
  }
});

afterAll(() => {
  // Cleanup after all tests
  global.fetch = originalFetch;
  console.log('[Test Setup] Test environment cleaned up.');
});

// =============================================================================
// EXPORTS
// =============================================================================

export { vi, mockFetchResponses };
