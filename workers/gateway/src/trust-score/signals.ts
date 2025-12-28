// ============================================================================
// S.S.I. SHADOW - Trust Score Signal Extraction
// ============================================================================

import { TrustSignals } from '../types/trust';
import { IncomingEvent } from '../types';

/**
 * Extract all available signals from request and event payload
 */
export function extractSignals(
  request: Request,
  event: IncomingEvent
): TrustSignals {
  const headers = request.headers;

  return {
    // Request headers
    userAgent: headers.get('User-Agent') || '',
    ip: getClientIP(request),
    acceptLanguage: headers.get('Accept-Language'),
    acceptEncoding: headers.get('Accept-Encoding'),
    accept: headers.get('Accept'),
    connection: headers.get('Connection'),

    // Client Hints (Chrome 89+)
    secChUa: headers.get('Sec-CH-UA'),
    secChUaMobile: headers.get('Sec-CH-UA-Mobile'),
    secChUaPlatform: headers.get('Sec-CH-UA-Platform'),
    secChUaFullVersion: headers.get('Sec-CH-UA-Full-Version'),
    secFetchSite: headers.get('Sec-Fetch-Site'),
    secFetchMode: headers.get('Sec-Fetch-Mode'),
    secFetchDest: headers.get('Sec-Fetch-Dest'),

    // Cloudflare headers
    cfRay: headers.get('CF-Ray'),
    cfConnectingIp: headers.get('CF-Connecting-IP'),
    cfIpCountry: headers.get('CF-IPCountry'),
    cfIpCity: headers.get('CF-IPCity'),
    cfIpContinent: headers.get('CF-IPContinent'),
    cfIpAsn: parseIntOrNull(headers.get('CF-IPAsn')),
    cfIpAsOrganization: headers.get('CF-IPAsOrganization'),
    cfTlsVersion: headers.get('CF-TLS-Version') || (request as any).cf?.tlsVersion,
    cfTlsCipher: headers.get('CF-TLS-Cipher') || (request as any).cf?.tlsCipher,

    // Ghost Script data
    canvasHash: event.canvas_hash || null,
    webglVendor: event.webgl_vendor || null,
    webglRenderer: event.webgl_renderer || null,
    pluginsHash: event.plugins_hash || null,
    pluginsCount: null, // Not directly available
    touchSupport: event.touch_support ?? null,
    cookiesEnabled: null, // Inferred from cookies presence

    // Behavioral data
    scrollDepth: event.scroll_depth ?? null,
    timeOnPage: event.time_on_page ?? null,
    clicks: event.clicks ?? null,
    sessionDuration: null, // Could be calculated from session
    sessionPageviews: null, // Could be calculated from session

    // Fingerprint data
    screenWidth: event.screen_width ?? null,
    screenHeight: event.screen_height ?? null,
    viewportWidth: event.viewport_width ?? null,
    viewportHeight: event.viewport_height ?? null,
    devicePixelRatio: null, // Not in current event structure
    colorDepth: null, // Not in current event structure
    timezone: event.timezone || null,
    language: event.language || null,
    hardwareConcurrency: null, // Not in current event structure
    deviceMemory: null, // Not in current event structure
  };
}

/**
 * Get client IP from request headers
 */
function getClientIP(request: Request): string {
  const headers = request.headers;
  
  // Cloudflare provides the real IP
  const cfIp = headers.get('CF-Connecting-IP');
  if (cfIp) return cfIp;
  
  // Fallback to X-Forwarded-For
  const xForwardedFor = headers.get('X-Forwarded-For');
  if (xForwardedFor) {
    // Take the first IP in the chain
    return xForwardedFor.split(',')[0].trim();
  }
  
  // Fallback to X-Real-IP
  const xRealIp = headers.get('X-Real-IP');
  if (xRealIp) return xRealIp;
  
  // No IP found
  return '';
}

/**
 * Parse string to integer or return null
 */
function parseIntOrNull(value: string | null): number | null {
  if (!value) return null;
  const parsed = parseInt(value, 10);
  return isNaN(parsed) ? null : parsed;
}

/**
 * Check if User-Agent indicates a mobile device
 */
export function isMobileUA(userAgent: string): boolean {
  const mobileKeywords = [
    'mobile', 'android', 'iphone', 'ipad', 'ipod',
    'blackberry', 'windows phone', 'opera mini', 'iemobile'
  ];
  const ua = userAgent.toLowerCase();
  return mobileKeywords.some(keyword => ua.includes(keyword));
}

/**
 * Check if User-Agent indicates Windows
 */
export function isWindowsUA(userAgent: string): boolean {
  return userAgent.toLowerCase().includes('windows');
}

/**
 * Check if User-Agent indicates macOS
 */
export function isMacUA(userAgent: string): boolean {
  const ua = userAgent.toLowerCase();
  return ua.includes('macintosh') || ua.includes('mac os');
}

/**
 * Check if User-Agent indicates Linux
 */
export function isLinuxUA(userAgent: string): boolean {
  const ua = userAgent.toLowerCase();
  return ua.includes('linux') && !ua.includes('android');
}

/**
 * Extract browser name from User-Agent
 */
export function getBrowserFromUA(userAgent: string): string | null {
  const ua = userAgent.toLowerCase();
  
  if (ua.includes('edg/')) return 'edge';
  if (ua.includes('chrome/') && !ua.includes('chromium/')) return 'chrome';
  if (ua.includes('chromium/')) return 'chromium';
  if (ua.includes('firefox/')) return 'firefox';
  if (ua.includes('safari/') && !ua.includes('chrome/')) return 'safari';
  if (ua.includes('opera/') || ua.includes('opr/')) return 'opera';
  if (ua.includes('msie') || ua.includes('trident/')) return 'ie';
  
  return null;
}

/**
 * Parse Sec-CH-UA header to extract browser info
 */
export function parseSecChUa(secChUa: string | null): { browser: string; version: string }[] {
  if (!secChUa) return [];
  
  const result: { browser: string; version: string }[] = [];
  
  // Format: "Google Chrome";v="120", "Chromium";v="120", "Not_A Brand";v="24"
  const regex = /"([^"]+)";v="([^"]+)"/g;
  let match;
  
  while ((match = regex.exec(secChUa)) !== null) {
    const browser = match[1];
    const version = match[2];
    
    // Skip fake/placeholder brands
    if (!browser.includes('Not') && !browser.includes('Brand')) {
      result.push({ browser, version });
    }
  }
  
  return result;
}

/**
 * Validate Sec-CH-UA consistency with User-Agent
 */
export function validateSecChUaConsistency(
  userAgent: string,
  secChUa: string | null,
  secChUaMobile: string | null,
  secChUaPlatform: string | null
): { consistent: boolean; issues: string[] } {
  const issues: string[] = [];
  
  // No Client Hints to validate
  if (!secChUa) {
    return { consistent: true, issues: [] };
  }
  
  const uaBrowser = getBrowserFromUA(userAgent);
  const chBrowsers = parseSecChUa(secChUa);
  
  // Check browser consistency
  if (uaBrowser && chBrowsers.length > 0) {
    const chBrowserNames = chBrowsers.map(b => b.browser.toLowerCase());
    const uaBrowserLower = uaBrowser.toLowerCase();
    
    // Chrome should be in Client Hints if User-Agent says Chrome
    if (uaBrowserLower === 'chrome' && !chBrowserNames.some(b => b.includes('chrome'))) {
      issues.push('UA indicates Chrome but Sec-CH-UA does not');
    }
  }
  
  // Check mobile consistency
  if (secChUaMobile) {
    const isMobile = isMobileUA(userAgent);
    const chMobile = secChUaMobile === '?1';
    
    if (isMobile !== chMobile) {
      issues.push('Mobile flag mismatch between UA and Sec-CH-UA-Mobile');
    }
  }
  
  // Check platform consistency
  if (secChUaPlatform) {
    const platform = secChUaPlatform.replace(/"/g, '').toLowerCase();
    
    if (platform.includes('windows') && !isWindowsUA(userAgent)) {
      issues.push('Sec-CH-UA-Platform indicates Windows but UA does not');
    }
    if (platform.includes('macos') && !isMacUA(userAgent)) {
      issues.push('Sec-CH-UA-Platform indicates macOS but UA does not');
    }
    if (platform.includes('linux') && !isLinuxUA(userAgent) && !isMobileUA(userAgent)) {
      issues.push('Sec-CH-UA-Platform indicates Linux but UA does not');
    }
    if (platform.includes('android') && !userAgent.toLowerCase().includes('android')) {
      issues.push('Sec-CH-UA-Platform indicates Android but UA does not');
    }
  }
  
  return {
    consistent: issues.length === 0,
    issues
  };
}

/**
 * Check if IP is likely IPv6
 */
export function isIPv6(ip: string): boolean {
  return ip.includes(':');
}

/**
 * Normalize IP for comparison
 */
export function normalizeIP(ip: string): string {
  return ip.trim().toLowerCase();
}

/**
 * Hash IP for rate limiting (privacy-preserving)
 */
export function hashIP(ip: string): string {
  // Simple hash for rate limiting purposes
  let hash = 0;
  for (let i = 0; i < ip.length; i++) {
    const char = ip.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash; // Convert to 32bit integer
  }
  return 'ip_' + Math.abs(hash).toString(16);
}
