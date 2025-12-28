/**
 * S.S.I. SHADOW - Trust Score Tests
 * Tests for bot detection and trust score calculation
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import {
  mockTrustScoreHigh,
  mockTrustScoreLow,
  mockTrustScoreHeadless,
  mockRequestHeaders,
  mockBotRequestHeaders,
  mockHeadlessRequestHeaders,
  mockCFHeaders,
  mockCFHeadersDatacenter,
} from '@fixtures';

// =============================================================================
// TRUST SCORE TYPES (mirror from actual implementation)
// =============================================================================

interface TrustSignals {
  userAgent: string;
  acceptLanguage: string | null;
  acceptEncoding: string | null;
  accept: string | null;
  secChUa: string | null;
  secChUaMobile: string | null;
  secChUaPlatform: string | null;
  cfIpAsn: string | null;
  cfIpAsOrganization: string | null;
  cfTlsVersion: string | null;
  scrollDepth: number | null;
  timeOnPage: number | null;
  clicks: number | null;
  canvasHash: string | null;
  webglVendor: string | null;
  webglRenderer: string | null;
  pluginsHash: string | null;
  cookiesEnabled: boolean | null;
}

interface TrustReason {
  code: string;
  description: string;
  impact: number;
  severity: 'low' | 'medium' | 'high' | 'critical';
}

interface TrustScore {
  score: number;
  action: 'allow' | 'challenge' | 'block';
  confidence: number;
  reasons: TrustReason[];
  flags: string[];
}

// =============================================================================
// TRUST SCORE IMPLEMENTATION (simplified for testing)
// =============================================================================

const BOT_UA_KEYWORDS = [
  'bot', 'crawler', 'spider', 'scraper', 'curl', 'wget', 'python-requests',
  'axios', 'node-fetch', 'go-http-client', 'java', 'httpclient',
  'selenium', 'puppeteer', 'playwright', 'phantomjs', 'headless',
  'googlebot', 'bingbot', 'yandexbot', 'baiduspider', 'facebookexternalhit',
];

const DATACENTER_ASNS = new Set([
  '15169', // Google
  '14618', // Amazon
  '8075',  // Microsoft
  '13335', // Cloudflare
  '16509', // Amazon EC2
  '14061', // DigitalOcean
  '20473', // Vultr
  '63949', // Linode
]);

const SCORE_ADJUSTMENTS = {
  BOT_USER_AGENT: -0.5,
  HEADLESS_BROWSER: -0.5,
  DATACENTER_IP: -0.3,
  RESIDENTIAL_IP: 0.1,
  MISSING_ACCEPT_LANGUAGE: -0.1,
  VALID_CLIENT_HINTS: 0.1,
  HAS_BEHAVIORAL_DATA: 0.05,
  NATURAL_SCROLL_PATTERN: 0.1,
  SUSPICIOUS_WEBGL: -0.3,
};

function extractSignals(headers: Record<string, string>, body: Record<string, unknown>): TrustSignals {
  return {
    userAgent: headers['user-agent'] || '',
    acceptLanguage: headers['accept-language'] || null,
    acceptEncoding: headers['accept-encoding'] || null,
    accept: headers['accept'] || null,
    secChUa: headers['sec-ch-ua'] || null,
    secChUaMobile: headers['sec-ch-ua-mobile'] || null,
    secChUaPlatform: headers['sec-ch-ua-platform'] || null,
    cfIpAsn: headers['cf-asn'] || null,
    cfIpAsOrganization: headers['cf-asorganization'] || null,
    cfTlsVersion: headers['cf-tls-version'] || null,
    scrollDepth: typeof body.scroll_depth === 'number' ? body.scroll_depth : null,
    timeOnPage: typeof body.time_on_page === 'number' ? body.time_on_page : null,
    clicks: typeof body.clicks === 'number' ? body.clicks : null,
    canvasHash: typeof body.canvas_hash === 'string' ? body.canvas_hash : null,
    webglVendor: typeof body.webgl_vendor === 'string' ? body.webgl_vendor : null,
    webglRenderer: typeof body.webgl_renderer === 'string' ? body.webgl_renderer : null,
    pluginsHash: typeof body.plugins_hash === 'string' ? body.plugins_hash : null,
    cookiesEnabled: typeof body.cookies_enabled === 'boolean' ? body.cookies_enabled : null,
  };
}

function checkBotUserAgent(userAgent: string): { isBot: boolean; keyword: string | null } {
  const uaLower = userAgent.toLowerCase();
  for (const keyword of BOT_UA_KEYWORDS) {
    if (uaLower.includes(keyword)) {
      return { isBot: true, keyword };
    }
  }
  return { isBot: false, keyword: null };
}

function calculateTrustScore(signals: TrustSignals): TrustScore {
  let score = 0.5; // Base score
  const reasons: TrustReason[] = [];
  const flags: string[] = [];

  // Bot User-Agent check
  const botCheck = checkBotUserAgent(signals.userAgent);
  if (botCheck.isBot) {
    score += SCORE_ADJUSTMENTS.BOT_USER_AGENT;
    reasons.push({
      code: 'BOT_USER_AGENT',
      description: `Bot keyword detected: ${botCheck.keyword}`,
      impact: SCORE_ADJUSTMENTS.BOT_USER_AGENT,
      severity: 'critical',
    });
    flags.push('bot_user_agent');
  }

  // Headless browser check
  if (signals.userAgent.toLowerCase().includes('headless')) {
    score += SCORE_ADJUSTMENTS.HEADLESS_BROWSER;
    reasons.push({
      code: 'HEADLESS_BROWSER',
      description: 'HeadlessChrome detected in User-Agent',
      impact: SCORE_ADJUSTMENTS.HEADLESS_BROWSER,
      severity: 'critical',
    });
    flags.push('headless_browser');
  }

  // Suspicious WebGL
  if (signals.webglRenderer) {
    const renderer = signals.webglRenderer.toLowerCase();
    if (renderer.includes('swiftshader') || renderer.includes('llvmpipe')) {
      score += SCORE_ADJUSTMENTS.SUSPICIOUS_WEBGL;
      reasons.push({
        code: 'SUSPICIOUS_WEBGL',
        description: `Suspicious WebGL renderer: ${signals.webglRenderer}`,
        impact: SCORE_ADJUSTMENTS.SUSPICIOUS_WEBGL,
        severity: 'high',
      });
      flags.push('suspicious_webgl');
    }
  }

  // Datacenter IP check
  if (signals.cfIpAsn && DATACENTER_ASNS.has(signals.cfIpAsn)) {
    score += SCORE_ADJUSTMENTS.DATACENTER_IP;
    reasons.push({
      code: 'DATACENTER_IP',
      description: `Datacenter ASN: ${signals.cfIpAsn}`,
      impact: SCORE_ADJUSTMENTS.DATACENTER_IP,
      severity: 'high',
    });
    flags.push('datacenter_ip');
  } else if (signals.cfIpAsn) {
    score += SCORE_ADJUSTMENTS.RESIDENTIAL_IP;
    reasons.push({
      code: 'RESIDENTIAL_IP',
      description: 'Residential IP detected',
      impact: SCORE_ADJUSTMENTS.RESIDENTIAL_IP,
      severity: 'low',
    });
  }

  // Missing Accept-Language
  if (!signals.acceptLanguage) {
    score += SCORE_ADJUSTMENTS.MISSING_ACCEPT_LANGUAGE;
    reasons.push({
      code: 'MISSING_ACCEPT_LANGUAGE',
      description: 'Accept-Language header missing',
      impact: SCORE_ADJUSTMENTS.MISSING_ACCEPT_LANGUAGE,
      severity: 'medium',
    });
  }

  // Valid Client Hints
  if (signals.secChUa) {
    score += SCORE_ADJUSTMENTS.VALID_CLIENT_HINTS;
    reasons.push({
      code: 'VALID_CLIENT_HINTS',
      description: 'Client Hints present',
      impact: SCORE_ADJUSTMENTS.VALID_CLIENT_HINTS,
      severity: 'low',
    });
  }

  // Behavioral data
  const hasBehavioral = signals.scrollDepth !== null || signals.timeOnPage !== null || signals.clicks !== null;
  if (hasBehavioral) {
    score += SCORE_ADJUSTMENTS.HAS_BEHAVIORAL_DATA;
    reasons.push({
      code: 'HAS_BEHAVIORAL_DATA',
      description: 'Behavioral data present',
      impact: SCORE_ADJUSTMENTS.HAS_BEHAVIORAL_DATA,
      severity: 'low',
    });

    // Natural scroll pattern
    if (signals.scrollDepth && signals.scrollDepth > 25 && signals.scrollDepth < 100) {
      score += SCORE_ADJUSTMENTS.NATURAL_SCROLL_PATTERN;
      reasons.push({
        code: 'NATURAL_SCROLL_PATTERN',
        description: 'Natural scroll pattern detected',
        impact: SCORE_ADJUSTMENTS.NATURAL_SCROLL_PATTERN,
        severity: 'low',
      });
    }
  }

  // Clamp score between 0 and 1
  score = Math.max(0, Math.min(1, score));

  // Determine action
  let action: 'allow' | 'challenge' | 'block' = 'allow';
  if (score < 0.3) {
    action = 'block';
  } else if (score < 0.6) {
    action = 'challenge';
  }

  // Calculate confidence based on data available
  const dataPoints = [
    signals.userAgent ? 1 : 0,
    signals.acceptLanguage ? 1 : 0,
    signals.secChUa ? 1 : 0,
    signals.cfIpAsn ? 1 : 0,
    hasBehavioral ? 1 : 0,
    signals.canvasHash ? 1 : 0,
    signals.webglRenderer ? 1 : 0,
  ];
  const confidence = dataPoints.reduce((a, b) => a + b, 0) / dataPoints.length;

  return {
    score: Math.round(score * 100) / 100,
    action,
    confidence: Math.round(confidence * 100) / 100,
    reasons,
    flags,
  };
}

// =============================================================================
// TESTS
// =============================================================================

describe('Trust Score Engine', () => {
  describe('Signal Extraction', () => {
    it('should extract all signals from headers and body', () => {
      const headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'accept-language': 'pt-BR,pt;q=0.9',
        'accept-encoding': 'gzip, deflate, br',
        'accept': 'application/json',
        'sec-ch-ua': '"Chrome";v="120"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'cf-asn': '12345',
      };
      const body = {
        scroll_depth: 50,
        time_on_page: 30000,
        clicks: 3,
        canvas_hash: 'abc123',
        webgl_renderer: 'NVIDIA GeForce GTX 1080',
      };

      const signals = extractSignals(headers, body);

      expect(signals.userAgent).toBe('Mozilla/5.0 (Windows NT 10.0; Win64; x64)');
      expect(signals.acceptLanguage).toBe('pt-BR,pt;q=0.9');
      expect(signals.secChUa).toBe('"Chrome";v="120"');
      expect(signals.scrollDepth).toBe(50);
      expect(signals.timeOnPage).toBe(30000);
      expect(signals.clicks).toBe(3);
      expect(signals.canvasHash).toBe('abc123');
    });

    it('should handle missing optional fields', () => {
      const headers = { 'user-agent': 'Test' };
      const body = {};

      const signals = extractSignals(headers, body);

      expect(signals.userAgent).toBe('Test');
      expect(signals.acceptLanguage).toBeNull();
      expect(signals.scrollDepth).toBeNull();
      expect(signals.canvasHash).toBeNull();
    });
  });

  describe('Bot Detection', () => {
    it('should detect Googlebot', () => {
      const result = checkBotUserAgent('Googlebot/2.1 (+http://www.google.com/bot.html)');
      expect(result.isBot).toBe(true);
      expect(result.keyword).toBe('googlebot');
    });

    it('should detect generic bot keyword', () => {
      const result = checkBotUserAgent('SomeRandomBot/1.0');
      expect(result.isBot).toBe(true);
      expect(result.keyword).toBe('bot');
    });

    it('should detect Python requests', () => {
      const result = checkBotUserAgent('python-requests/2.28.0');
      expect(result.isBot).toBe(true);
      expect(result.keyword).toBe('python-requests');
    });

    it('should detect Selenium', () => {
      const result = checkBotUserAgent('Mozilla/5.0 Selenium/3.141');
      expect(result.isBot).toBe(true);
      expect(result.keyword).toBe('selenium');
    });

    it('should detect Puppeteer', () => {
      const result = checkBotUserAgent('Mozilla/5.0 Puppeteer');
      expect(result.isBot).toBe(true);
      expect(result.keyword).toBe('puppeteer');
    });

    it('should NOT flag legitimate Chrome browser', () => {
      const result = checkBotUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36');
      expect(result.isBot).toBe(false);
      expect(result.keyword).toBeNull();
    });

    it('should NOT flag legitimate Firefox browser', () => {
      const result = checkBotUserAgent('Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0');
      expect(result.isBot).toBe(false);
      expect(result.keyword).toBeNull();
    });

    it('should NOT flag legitimate Safari browser', () => {
      const result = checkBotUserAgent('Mozilla/5.0 (Macintosh; Intel Mac OS X 14_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15');
      expect(result.isBot).toBe(false);
      expect(result.keyword).toBeNull();
    });

    it('should be case insensitive', () => {
      const result = checkBotUserAgent('GOOGLEBOT/2.1');
      expect(result.isBot).toBe(true);
    });
  });

  describe('Trust Score Calculation', () => {
    it('should give high score to legitimate browser with behavioral data', () => {
      const signals: TrustSignals = {
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        acceptLanguage: 'pt-BR,pt;q=0.9',
        acceptEncoding: 'gzip, deflate, br',
        accept: 'application/json',
        secChUa: '"Chrome";v="120"',
        secChUaMobile: '?0',
        secChUaPlatform: '"Windows"',
        cfIpAsn: '12345', // Non-datacenter ASN
        cfIpAsOrganization: 'Vivo',
        cfTlsVersion: 'TLSv1.3',
        scrollDepth: 50,
        timeOnPage: 30000,
        clicks: 3,
        canvasHash: 'abc123',
        webglVendor: 'Google Inc.',
        webglRenderer: 'NVIDIA GeForce GTX 1080',
        pluginsHash: 'def456',
        cookiesEnabled: true,
      };

      const result = calculateTrustScore(signals);

      expect(result.score).toBeGreaterThan(0.6);
      expect(result.action).toBe('allow');
      expect(result.flags).not.toContain('bot_user_agent');
    });

    it('should give low score to known bot', () => {
      const signals: TrustSignals = {
        userAgent: 'Googlebot/2.1 (+http://www.google.com/bot.html)',
        acceptLanguage: null,
        acceptEncoding: null,
        accept: '*/*',
        secChUa: null,
        secChUaMobile: null,
        secChUaPlatform: null,
        cfIpAsn: '15169', // Google ASN
        cfIpAsOrganization: 'Google',
        cfTlsVersion: 'TLSv1.2',
        scrollDepth: null,
        timeOnPage: null,
        clicks: null,
        canvasHash: null,
        webglVendor: null,
        webglRenderer: null,
        pluginsHash: null,
        cookiesEnabled: null,
      };

      const result = calculateTrustScore(signals);

      expect(result.score).toBeLessThan(0.3);
      expect(result.action).toBe('block');
      expect(result.flags).toContain('bot_user_agent');
      expect(result.flags).toContain('datacenter_ip');
    });

    it('should give low score to headless browser', () => {
      const signals: TrustSignals = {
        userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 HeadlessChrome/120.0.0.0',
        acceptLanguage: 'en-US',
        acceptEncoding: 'gzip',
        accept: 'application/json',
        secChUa: null,
        secChUaMobile: null,
        secChUaPlatform: null,
        cfIpAsn: '14618', // Amazon ASN
        cfIpAsOrganization: 'Amazon',
        cfTlsVersion: 'TLSv1.3',
        scrollDepth: null,
        timeOnPage: null,
        clicks: null,
        canvasHash: null,
        webglVendor: null,
        webglRenderer: 'Google SwiftShader',
        pluginsHash: null,
        cookiesEnabled: true,
      };

      const result = calculateTrustScore(signals);

      expect(result.score).toBeLessThan(0.3);
      expect(result.action).toBe('block');
      expect(result.flags).toContain('headless_browser');
      expect(result.flags).toContain('datacenter_ip');
      expect(result.flags).toContain('suspicious_webgl');
    });

    it('should give medium score to datacenter IP with normal browser', () => {
      const signals: TrustSignals = {
        userAgent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        acceptLanguage: 'en-US',
        acceptEncoding: 'gzip',
        accept: '*/*',
        secChUa: null,
        secChUaMobile: null,
        secChUaPlatform: null,
        cfIpAsn: '14618', // Amazon ASN
        cfIpAsOrganization: 'Amazon',
        cfTlsVersion: 'TLSv1.3',
        scrollDepth: 10,
        timeOnPage: 5000,
        clicks: 1,
        canvasHash: null,
        webglVendor: null,
        webglRenderer: 'NVIDIA GeForce GTX 1080',
        pluginsHash: null,
        cookiesEnabled: true,
      };

      const result = calculateTrustScore(signals);

      expect(result.score).toBeGreaterThanOrEqual(0.3);
      expect(result.score).toBeLessThan(0.6);
      expect(result.action).toBe('challenge');
      expect(result.flags).toContain('datacenter_ip');
      expect(result.flags).not.toContain('bot_user_agent');
    });

    it('should clamp score between 0 and 1', () => {
      // Very bad signals
      const badSignals: TrustSignals = {
        userAgent: 'curl/7.68.0',
        acceptLanguage: null,
        acceptEncoding: null,
        accept: null,
        secChUa: null,
        secChUaMobile: null,
        secChUaPlatform: null,
        cfIpAsn: '15169',
        cfIpAsOrganization: null,
        cfTlsVersion: null,
        scrollDepth: null,
        timeOnPage: null,
        clicks: null,
        canvasHash: null,
        webglVendor: null,
        webglRenderer: 'SwiftShader',
        pluginsHash: null,
        cookiesEnabled: null,
      };

      const result = calculateTrustScore(badSignals);

      expect(result.score).toBeGreaterThanOrEqual(0);
      expect(result.score).toBeLessThanOrEqual(1);
    });
  });

  describe('Action Thresholds', () => {
    it('should block when score < 0.3', () => {
      const signals: TrustSignals = {
        userAgent: 'bot',
        acceptLanguage: null,
        acceptEncoding: null,
        accept: null,
        secChUa: null,
        secChUaMobile: null,
        secChUaPlatform: null,
        cfIpAsn: '15169',
        cfIpAsOrganization: null,
        cfTlsVersion: null,
        scrollDepth: null,
        timeOnPage: null,
        clicks: null,
        canvasHash: null,
        webglVendor: null,
        webglRenderer: null,
        pluginsHash: null,
        cookiesEnabled: null,
      };

      const result = calculateTrustScore(signals);
      expect(result.action).toBe('block');
    });

    it('should allow when score >= 0.6', () => {
      const signals: TrustSignals = {
        userAgent: 'Mozilla/5.0 Chrome/120.0.0.0',
        acceptLanguage: 'pt-BR',
        acceptEncoding: 'gzip',
        accept: '*/*',
        secChUa: '"Chrome";v="120"',
        secChUaMobile: '?0',
        secChUaPlatform: '"Windows"',
        cfIpAsn: '12345',
        cfIpAsOrganization: 'Vivo',
        cfTlsVersion: 'TLSv1.3',
        scrollDepth: 50,
        timeOnPage: 30000,
        clicks: 3,
        canvasHash: 'abc',
        webglVendor: 'NVIDIA',
        webglRenderer: 'GeForce GTX 1080',
        pluginsHash: 'def',
        cookiesEnabled: true,
      };

      const result = calculateTrustScore(signals);
      expect(result.action).toBe('allow');
    });
  });

  describe('Confidence Calculation', () => {
    it('should have high confidence with full data', () => {
      const signals: TrustSignals = {
        userAgent: 'Mozilla/5.0',
        acceptLanguage: 'pt-BR',
        acceptEncoding: 'gzip',
        accept: '*/*',
        secChUa: '"Chrome"',
        secChUaMobile: '?0',
        secChUaPlatform: '"Windows"',
        cfIpAsn: '12345',
        cfIpAsOrganization: null,
        cfTlsVersion: null,
        scrollDepth: 50,
        timeOnPage: 30000,
        clicks: 3,
        canvasHash: 'abc',
        webglVendor: null,
        webglRenderer: 'GeForce',
        pluginsHash: null,
        cookiesEnabled: null,
      };

      const result = calculateTrustScore(signals);
      expect(result.confidence).toBeGreaterThan(0.7);
    });

    it('should have low confidence with minimal data', () => {
      const signals: TrustSignals = {
        userAgent: 'Mozilla/5.0',
        acceptLanguage: null,
        acceptEncoding: null,
        accept: null,
        secChUa: null,
        secChUaMobile: null,
        secChUaPlatform: null,
        cfIpAsn: null,
        cfIpAsOrganization: null,
        cfTlsVersion: null,
        scrollDepth: null,
        timeOnPage: null,
        clicks: null,
        canvasHash: null,
        webglVendor: null,
        webglRenderer: null,
        pluginsHash: null,
        cookiesEnabled: null,
      };

      const result = calculateTrustScore(signals);
      expect(result.confidence).toBeLessThan(0.5);
    });
  });

  describe('Reason Tracking', () => {
    it('should track all reasons for score adjustments', () => {
      const signals: TrustSignals = {
        userAgent: 'Googlebot/2.1',
        acceptLanguage: null,
        acceptEncoding: null,
        accept: null,
        secChUa: null,
        secChUaMobile: null,
        secChUaPlatform: null,
        cfIpAsn: '15169',
        cfIpAsOrganization: 'Google',
        cfTlsVersion: null,
        scrollDepth: null,
        timeOnPage: null,
        clicks: null,
        canvasHash: null,
        webglVendor: null,
        webglRenderer: null,
        pluginsHash: null,
        cookiesEnabled: null,
      };

      const result = calculateTrustScore(signals);

      expect(result.reasons.length).toBeGreaterThan(0);
      expect(result.reasons.some(r => r.code === 'BOT_USER_AGENT')).toBe(true);
      expect(result.reasons.some(r => r.code === 'DATACENTER_IP')).toBe(true);
      expect(result.reasons.some(r => r.code === 'MISSING_ACCEPT_LANGUAGE')).toBe(true);
    });

    it('should include severity in reasons', () => {
      const signals: TrustSignals = {
        userAgent: 'bot',
        acceptLanguage: null,
        acceptEncoding: null,
        accept: null,
        secChUa: null,
        secChUaMobile: null,
        secChUaPlatform: null,
        cfIpAsn: null,
        cfIpAsOrganization: null,
        cfTlsVersion: null,
        scrollDepth: null,
        timeOnPage: null,
        clicks: null,
        canvasHash: null,
        webglVendor: null,
        webglRenderer: null,
        pluginsHash: null,
        cookiesEnabled: null,
      };

      const result = calculateTrustScore(signals);
      const botReason = result.reasons.find(r => r.code === 'BOT_USER_AGENT');

      expect(botReason).toBeDefined();
      expect(botReason?.severity).toBe('critical');
    });
  });
});
