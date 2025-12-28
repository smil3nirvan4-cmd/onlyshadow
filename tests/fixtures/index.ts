/**
 * S.S.I. SHADOW - Test Fixtures
 * Mock data for unit, integration, and e2e tests
 */

// =============================================================================
// MOCK EVENTS
// =============================================================================

export interface MockEvent {
  event_name: string;
  event_id?: string;
  ssi_id?: string;
  timestamp?: number;
  url?: string;
  referrer?: string;
  user_agent?: string;
  ip_address?: string;
  email?: string;
  phone?: string;
  first_name?: string;
  last_name?: string;
  fbclid?: string;
  gclid?: string;
  ttclid?: string;
  fbc?: string;
  fbp?: string;
  value?: number;
  currency?: string;
  content_ids?: string[];
  content_type?: string;
  content_name?: string;
  order_id?: string;
  num_items?: number;
  scroll_depth?: number;
  time_on_page?: number;
  clicks?: number;
  canvas_hash?: string;
  webgl_vendor?: string;
  webgl_renderer?: string;
  screen_width?: number;
  screen_height?: number;
  viewport_width?: number;
  viewport_height?: number;
  language?: string;
  timezone?: string;
  touch_support?: boolean;
  [key: string]: unknown;
}

// PageView Events
export const mockPageViewBasic: MockEvent = {
  event_name: 'PageView',
  url: 'https://example.com/product/123',
  referrer: 'https://google.com',
  user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  timestamp: Date.now(),
};

export const mockPageViewWithPII: MockEvent = {
  ...mockPageViewBasic,
  event_name: 'PageView',
  email: 'test@example.com',
  phone: '+5511999999999',
  first_name: 'João',
  last_name: 'Silva',
  fbclid: 'fb.1.1234567890.abcdefghij',
  fbp: 'fb.1.1234567890.1234567890',
  fbc: 'fb.1.1234567890.AbCdEfGhIj',
};

export const mockPageViewWithFingerprint: MockEvent = {
  ...mockPageViewBasic,
  event_name: 'PageView',
  canvas_hash: 'a1b2c3d4e5f6',
  webgl_vendor: 'Google Inc. (NVIDIA)',
  webgl_renderer: 'ANGLE (NVIDIA, NVIDIA GeForce GTX 1080 Direct3D11 vs_5_0 ps_5_0)',
  screen_width: 1920,
  screen_height: 1080,
  viewport_width: 1920,
  viewport_height: 969,
  language: 'pt-BR',
  timezone: 'America/Sao_Paulo',
  touch_support: false,
};

export const mockPageViewFull: MockEvent = {
  ...mockPageViewWithPII,
  ...mockPageViewWithFingerprint,
  ssi_id: 'ssi_test123456',
  event_id: 'evt_test123456',
  scroll_depth: 75,
  time_on_page: 45000,
  clicks: 3,
};

// Purchase Events
export const mockPurchaseBasic: MockEvent = {
  event_name: 'Purchase',
  value: 299.90,
  currency: 'BRL',
  content_ids: ['SKU-001', 'SKU-002'],
  order_id: 'ORD-2024-001',
  num_items: 2,
  url: 'https://example.com/checkout/success',
  timestamp: Date.now(),
};

export const mockPurchaseFull: MockEvent = {
  ...mockPurchaseBasic,
  ...mockPageViewWithPII,
  ...mockPageViewWithFingerprint,
  content_type: 'product',
  content_name: 'Kit Premium',
};

// Lead Events
export const mockLeadBasic: MockEvent = {
  event_name: 'Lead',
  email: 'lead@example.com',
  phone: '+5511888888888',
  first_name: 'Maria',
  last_name: 'Santos',
  url: 'https://example.com/landing-page',
  timestamp: Date.now(),
};

export const mockLeadFull: MockEvent = {
  ...mockLeadBasic,
  ...mockPageViewWithFingerprint,
  value: 50,
  currency: 'BRL',
};

// AddToCart Events
export const mockAddToCart: MockEvent = {
  event_name: 'AddToCart',
  value: 149.90,
  currency: 'BRL',
  content_ids: ['SKU-001'],
  content_type: 'product',
  content_name: 'Produto Teste',
  url: 'https://example.com/product/123',
  timestamp: Date.now(),
};

// InitiateCheckout Events
export const mockInitiateCheckout: MockEvent = {
  event_name: 'InitiateCheckout',
  value: 299.90,
  currency: 'BRL',
  content_ids: ['SKU-001', 'SKU-002'],
  num_items: 2,
  url: 'https://example.com/checkout',
  timestamp: Date.now(),
};

// ViewContent Events
export const mockViewContent: MockEvent = {
  event_name: 'ViewContent',
  content_ids: ['SKU-001'],
  content_type: 'product',
  content_name: 'Produto Teste',
  value: 149.90,
  currency: 'BRL',
  url: 'https://example.com/product/123',
  timestamp: Date.now(),
};

// All standard events
export const mockEvents: Record<string, MockEvent> = {
  pageViewBasic: mockPageViewBasic,
  pageViewWithPII: mockPageViewWithPII,
  pageViewWithFingerprint: mockPageViewWithFingerprint,
  pageViewFull: mockPageViewFull,
  purchaseBasic: mockPurchaseBasic,
  purchaseFull: mockPurchaseFull,
  leadBasic: mockLeadBasic,
  leadFull: mockLeadFull,
  addToCart: mockAddToCart,
  initiateCheckout: mockInitiateCheckout,
  viewContent: mockViewContent,
};

// =============================================================================
// MOCK TRUST SCORES
// =============================================================================

export interface MockTrustScore {
  score: number;
  action: 'allow' | 'challenge' | 'block';
  confidence: number;
  reasons: Array<{
    code: string;
    description: string;
    impact: number;
    severity: 'low' | 'medium' | 'high' | 'critical';
  }>;
  flags: string[];
  signals: Record<string, unknown>;
}

export const mockTrustScoreHigh: MockTrustScore = {
  score: 0.92,
  action: 'allow',
  confidence: 0.95,
  reasons: [
    { code: 'RESIDENTIAL_IP', description: 'Residential IP detected', impact: 0.1, severity: 'low' },
    { code: 'VALID_CLIENT_HINTS', description: 'Client Hints present and consistent', impact: 0.1, severity: 'low' },
    { code: 'HAS_BEHAVIORAL_DATA', description: 'Behavioral data present', impact: 0.05, severity: 'low' },
    { code: 'NATURAL_SCROLL_PATTERN', description: 'Natural scroll pattern detected', impact: 0.1, severity: 'low' },
    { code: 'CONSISTENT_FINGERPRINT', description: 'Consistent fingerprint data', impact: 0.15, severity: 'low' },
  ],
  flags: [],
  signals: {
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    acceptLanguage: 'pt-BR,pt;q=0.9,en;q=0.8',
    scrollDepth: 75,
    timeOnPage: 45000,
    clicks: 5,
  },
};

export const mockTrustScoreMedium: MockTrustScore = {
  score: 0.55,
  action: 'challenge',
  confidence: 0.70,
  reasons: [
    { code: 'DATACENTER_IP', description: 'Datacenter ASN detected: 14618 (Amazon)', impact: -0.3, severity: 'high' },
    { code: 'HAS_BEHAVIORAL_DATA', description: 'Behavioral data present', impact: 0.05, severity: 'low' },
  ],
  flags: ['datacenter_ip'],
  signals: {
    userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    cfIpAsn: '14618',
    cfIpAsOrganization: 'Amazon',
  },
};

export const mockTrustScoreLow: MockTrustScore = {
  score: 0.15,
  action: 'block',
  confidence: 0.98,
  reasons: [
    { code: 'BOT_USER_AGENT', description: 'Bot keyword detected: bot', impact: -0.5, severity: 'critical' },
    { code: 'DATACENTER_IP', description: 'Datacenter ASN detected: 15169 (Google)', impact: -0.3, severity: 'high' },
    { code: 'NO_BEHAVIORAL_DATA', description: 'No behavioral data available', impact: -0.05, severity: 'low' },
  ],
  flags: ['bot_user_agent', 'datacenter_ip', 'no_behavioral'],
  signals: {
    userAgent: 'Googlebot/2.1 (+http://www.google.com/bot.html)',
    cfIpAsn: '15169',
  },
};

export const mockTrustScoreHeadless: MockTrustScore = {
  score: 0.08,
  action: 'block',
  confidence: 0.99,
  reasons: [
    { code: 'HEADLESS_BROWSER', description: 'HeadlessChrome in User-Agent', impact: -0.5, severity: 'critical' },
    { code: 'SUSPICIOUS_WEBGL', description: 'Suspicious WebGL renderer: SwiftShader', impact: -0.3, severity: 'high' },
    { code: 'NO_PLUGINS', description: 'No browser plugins detected (desktop)', impact: -0.05, severity: 'low' },
  ],
  flags: ['headless_browser', 'suspicious_webgl'],
  signals: {
    userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/120.0.0.0 Safari/537.36',
    webglRenderer: 'Google SwiftShader',
  },
};

export const mockTrustScores: Record<string, MockTrustScore> = {
  high: mockTrustScoreHigh,
  medium: mockTrustScoreMedium,
  low: mockTrustScoreLow,
  headless: mockTrustScoreHeadless,
};

// =============================================================================
// MOCK ML PREDICTIONS
// =============================================================================

export interface MockMLPrediction {
  user_id: string;
  predicted_ltv_90d: number;
  ltv_tier: 'VIP' | 'High' | 'Medium' | 'Low';
  ltv_percentile: number;
  churn_probability: number;
  churn_risk: 'Critical' | 'High' | 'Medium' | 'Low';
  propensity_7d: number;
  propensity_tier: 'Very High' | 'High' | 'Medium' | 'Low';
  confidence: number;
  features_used: number;
  last_updated: string;
}

export const mockMLPredictionVIP: MockMLPrediction = {
  user_id: 'ssi_vip_user_001',
  predicted_ltv_90d: 2500.00,
  ltv_tier: 'VIP',
  ltv_percentile: 95,
  churn_probability: 0.05,
  churn_risk: 'Low',
  propensity_7d: 0.85,
  propensity_tier: 'Very High',
  confidence: 0.92,
  features_used: 25,
  last_updated: new Date().toISOString(),
};

export const mockMLPredictionHigh: MockMLPrediction = {
  user_id: 'ssi_high_user_001',
  predicted_ltv_90d: 800.00,
  ltv_tier: 'High',
  ltv_percentile: 75,
  churn_probability: 0.15,
  churn_risk: 'Low',
  propensity_7d: 0.65,
  propensity_tier: 'High',
  confidence: 0.85,
  features_used: 20,
  last_updated: new Date().toISOString(),
};

export const mockMLPredictionMedium: MockMLPrediction = {
  user_id: 'ssi_medium_user_001',
  predicted_ltv_90d: 250.00,
  ltv_tier: 'Medium',
  ltv_percentile: 50,
  churn_probability: 0.35,
  churn_risk: 'Medium',
  propensity_7d: 0.40,
  propensity_tier: 'Medium',
  confidence: 0.75,
  features_used: 15,
  last_updated: new Date().toISOString(),
};

export const mockMLPredictionLow: MockMLPrediction = {
  user_id: 'ssi_low_user_001',
  predicted_ltv_90d: 50.00,
  ltv_tier: 'Low',
  ltv_percentile: 20,
  churn_probability: 0.70,
  churn_risk: 'High',
  propensity_7d: 0.15,
  propensity_tier: 'Low',
  confidence: 0.60,
  features_used: 8,
  last_updated: new Date().toISOString(),
};

export const mockMLPredictionChurnRisk: MockMLPrediction = {
  user_id: 'ssi_churn_user_001',
  predicted_ltv_90d: 600.00,
  ltv_tier: 'High',
  ltv_percentile: 70,
  churn_probability: 0.85,
  churn_risk: 'Critical',
  propensity_7d: 0.10,
  propensity_tier: 'Low',
  confidence: 0.88,
  features_used: 22,
  last_updated: new Date().toISOString(),
};

export const mockMLPredictions: Record<string, MockMLPrediction> = {
  vip: mockMLPredictionVIP,
  high: mockMLPredictionHigh,
  medium: mockMLPredictionMedium,
  low: mockMLPredictionLow,
  churnRisk: mockMLPredictionChurnRisk,
};

// =============================================================================
// MOCK BID RECOMMENDATIONS
// =============================================================================

export interface MockBidRecommendation {
  event_id: string;
  ssi_id: string;
  strategy: 'aggressive' | 'retention' | 'acquisition' | 'nurture' | 'conservative' | 'exclude';
  multiplier: number;
  confidence: number;
  reasons: string[];
  signals: {
    ltv_score: number;
    propensity_score: number;
    churn_risk: number;
    recency_score: number;
    engagement_score: number;
    trust_score: number;
  };
  platforms: {
    meta: { multiplier: number; audience_signal: string };
    tiktok: { multiplier: number; audience_signal: string };
    google: { multiplier: number; audience_signal: string };
  };
}

export const mockBidAggressive: MockBidRecommendation = {
  event_id: 'evt_aggressive_001',
  ssi_id: 'ssi_aggressive_001',
  strategy: 'aggressive',
  multiplier: 1.8,
  confidence: 0.92,
  reasons: [
    'High-value user (top 10% LTV) with strong purchase intent',
    'Very high purchase probability (85%)',
    'Expected 90-day value: R$2,500',
  ],
  signals: {
    ltv_score: 0.95,
    propensity_score: 0.85,
    churn_risk: 0.05,
    recency_score: 0.90,
    engagement_score: 0.88,
    trust_score: 0.92,
  },
  platforms: {
    meta: { multiplier: 1.8, audience_signal: 'high_value_intent' },
    tiktok: { multiplier: 1.71, audience_signal: 'purchase_intent' },
    google: { multiplier: 1.89, audience_signal: 'in_market_high_intent' },
  },
};

export const mockBidRetention: MockBidRecommendation = {
  event_id: 'evt_retention_001',
  ssi_id: 'ssi_retention_001',
  strategy: 'retention',
  multiplier: 1.4,
  confidence: 0.88,
  reasons: [
    'Valuable customer at risk of churning',
    'High LTV but elevated churn probability (75%)',
    'Retention campaign recommended',
  ],
  signals: {
    ltv_score: 0.75,
    propensity_score: 0.25,
    churn_risk: 0.75,
    recency_score: 0.30,
    engagement_score: 0.40,
    trust_score: 0.85,
  },
  platforms: {
    meta: { multiplier: 1.4, audience_signal: 'loyal_at_risk' },
    tiktok: { multiplier: 1.33, audience_signal: 'existing_customers' },
    google: { multiplier: 1.47, audience_signal: 'customer_match_high_value' },
  },
};

export const mockBidExclude: MockBidRecommendation = {
  event_id: 'evt_exclude_001',
  ssi_id: 'ssi_exclude_001',
  strategy: 'exclude',
  multiplier: 0,
  confidence: 0.98,
  reasons: [
    'Traffic blocked due to low trust score (0.15)',
    'Bot or invalid traffic detected',
    'Do not spend budget on this user',
  ],
  signals: {
    ltv_score: 0,
    propensity_score: 0,
    churn_risk: 0,
    recency_score: 0,
    engagement_score: 0,
    trust_score: 0.15,
  },
  platforms: {
    meta: { multiplier: 0, audience_signal: 'exclude' },
    tiktok: { multiplier: 0, audience_signal: 'exclude' },
    google: { multiplier: 0, audience_signal: 'exclude' },
  },
};

export const mockBidRecommendations: Record<string, MockBidRecommendation> = {
  aggressive: mockBidAggressive,
  retention: mockBidRetention,
  exclude: mockBidExclude,
};

// =============================================================================
// MOCK REQUEST/RESPONSE
// =============================================================================

export interface MockRequest {
  method: string;
  url: string;
  headers: Record<string, string>;
  body?: string;
}

export const mockRequestHeaders: Record<string, string> = {
  'content-type': 'application/json',
  'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
  'accept': 'application/json, text/plain, */*',
  'accept-language': 'pt-BR,pt;q=0.9,en;q=0.8',
  'accept-encoding': 'gzip, deflate, br',
  'sec-ch-ua': '"Not_A Brand";v="8", "Chromium";v="120", "Google Chrome";v="120"',
  'sec-ch-ua-mobile': '?0',
  'sec-ch-ua-platform': '"Windows"',
  'origin': 'https://example.com',
  'referer': 'https://example.com/',
};

export const mockBotRequestHeaders: Record<string, string> = {
  'content-type': 'application/json',
  'user-agent': 'Googlebot/2.1 (+http://www.google.com/bot.html)',
  'accept': '*/*',
};

export const mockHeadlessRequestHeaders: Record<string, string> = {
  'content-type': 'application/json',
  'user-agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) HeadlessChrome/120.0.0.0 Safari/537.36',
  'accept': 'application/json',
};

// =============================================================================
// MOCK PLATFORM RESPONSES
// =============================================================================

export const mockMetaSuccessResponse = {
  events_received: 1,
  messages: [],
  fbtrace_id: 'A1b2C3d4E5f6G7h8I9j0',
};

export const mockMetaErrorResponse = {
  error: {
    message: 'Invalid OAuth access token.',
    type: 'OAuthException',
    code: 190,
    fbtrace_id: 'A1b2C3d4E5f6G7h8I9j0',
  },
};

export const mockTikTokSuccessResponse = {
  code: 0,
  message: 'OK',
  data: {
    failed_events: [],
  },
};

export const mockTikTokErrorResponse = {
  code: 40001,
  message: 'Invalid access token',
  data: null,
};

export const mockGoogleSuccessResponse = {
  // Google MP returns empty on success
};

// =============================================================================
// MOCK CLOUDFLARE HEADERS (from CF Workers)
// =============================================================================

export const mockCFHeaders = {
  'cf-connecting-ip': '189.40.100.50',
  'cf-ipcountry': 'BR',
  'cf-ray': '1234567890abcdef-GRU',
  'cf-visitor': '{"scheme":"https"}',
  'x-real-ip': '189.40.100.50',
};

export const mockCFHeadersDatacenter = {
  'cf-connecting-ip': '35.192.0.1',
  'cf-ipcountry': 'US',
  'cf-ray': '1234567890abcdef-IAD',
  'cf-visitor': '{"scheme":"https"}',
  'x-real-ip': '35.192.0.1',
};

// =============================================================================
// HELPER FUNCTIONS
// =============================================================================

export function createMockEvent(overrides: Partial<MockEvent> = {}): MockEvent {
  return {
    ...mockPageViewFull,
    event_id: `evt_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    ssi_id: `ssi_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    timestamp: Date.now(),
    ...overrides,
  };
}

export function createMockRequest(
  body: MockEvent,
  headers: Record<string, string> = mockRequestHeaders
): MockRequest {
  return {
    method: 'POST',
    url: 'https://ssi.example.com/api/collect',
    headers,
    body: JSON.stringify(body),
  };
}

export function generateMockEvents(count: number, eventType: string = 'PageView'): MockEvent[] {
  return Array.from({ length: count }, (_, i) => createMockEvent({
    event_name: eventType,
    event_id: `evt_batch_${i}_${Date.now()}`,
  }));
}

// Export all
export default {
  events: mockEvents,
  trustScores: mockTrustScores,
  mlPredictions: mockMLPredictions,
  bidRecommendations: mockBidRecommendations,
  requestHeaders: mockRequestHeaders,
  cfHeaders: mockCFHeaders,
  platformResponses: {
    meta: { success: mockMetaSuccessResponse, error: mockMetaErrorResponse },
    tiktok: { success: mockTikTokSuccessResponse, error: mockTikTokErrorResponse },
    google: { success: mockGoogleSuccessResponse },
  },
  helpers: {
    createMockEvent,
    createMockRequest,
    generateMockEvents,
  },
};
