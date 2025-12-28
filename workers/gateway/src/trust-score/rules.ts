// ============================================================================
// S.S.I. SHADOW - Trust Score Rules Engine
// ============================================================================

import {
  TrustSignals,
  TrustReason,
  TrustFlag,
  BOT_UA_KEYWORDS,
  DATACENTER_ASNS,
  SUSPICIOUS_WEBGL_RENDERERS,
  SCORE_ADJUSTMENTS,
} from '../types/trust';
import {
  validateSecChUaConsistency,
  isMobileUA,
} from './signals';

/**
 * Apply all scoring rules and return reasons/flags
 */
export function applyRules(signals: TrustSignals): {
  reasons: TrustReason[];
  flags: TrustFlag[];
  totalAdjustment: number;
} {
  const reasons: TrustReason[] = [];
  const flags: TrustFlag[] = [];
  let totalAdjustment = 0;

  // ========================================================================
  // USER-AGENT CHECKS
  // ========================================================================

  // Check for bot keywords in User-Agent
  const botUACheck = checkBotUserAgent(signals.userAgent);
  if (botUACheck.isBot) {
    reasons.push({
      code: 'BOT_USER_AGENT',
      description: `Bot keyword detected: ${botUACheck.keyword}`,
      impact: SCORE_ADJUSTMENTS.BOT_USER_AGENT,
      severity: 'critical',
    });
    flags.push('bot_user_agent');
    totalAdjustment += SCORE_ADJUSTMENTS.BOT_USER_AGENT;
  }

  // Check for headless browser indicators
  const headlessCheck = checkHeadlessBrowser(signals);
  if (headlessCheck.isHeadless) {
    reasons.push({
      code: 'HEADLESS_BROWSER',
      description: headlessCheck.reason,
      impact: SCORE_ADJUSTMENTS.HEADLESS_BROWSER,
      severity: 'critical',
    });
    flags.push('headless_browser');
    totalAdjustment += SCORE_ADJUSTMENTS.HEADLESS_BROWSER;
  }

  // Check for automation tools
  const automationCheck = checkAutomationTools(signals.userAgent);
  if (automationCheck.isAutomation) {
    reasons.push({
      code: 'AUTOMATION_TOOL',
      description: `Automation tool detected: ${automationCheck.tool}`,
      impact: SCORE_ADJUSTMENTS.AUTOMATION_TOOL,
      severity: 'critical',
    });
    flags.push('automation_tool');
    totalAdjustment += SCORE_ADJUSTMENTS.AUTOMATION_TOOL;
  }

  // ========================================================================
  // IP / ASN CHECKS
  // ========================================================================

  // Check for datacenter IP
  if (signals.cfIpAsn && DATACENTER_ASNS.has(signals.cfIpAsn)) {
    reasons.push({
      code: 'DATACENTER_IP',
      description: `Datacenter ASN detected: ${signals.cfIpAsn} (${signals.cfIpAsOrganization || 'Unknown'})`,
      impact: SCORE_ADJUSTMENTS.DATACENTER_IP,
      severity: 'high',
    });
    flags.push('datacenter_ip');
    totalAdjustment += SCORE_ADJUSTMENTS.DATACENTER_IP;
  } else if (signals.cfIpAsn) {
    // Non-datacenter IP is a slight positive signal
    reasons.push({
      code: 'RESIDENTIAL_IP',
      description: 'Residential/ISP IP detected',
      impact: SCORE_ADJUSTMENTS.RESIDENTIAL_IP,
      severity: 'low',
    });
    totalAdjustment += SCORE_ADJUSTMENTS.RESIDENTIAL_IP;
  }

  // ========================================================================
  // HEADER CHECKS
  // ========================================================================

  // Missing Accept-Language
  if (!signals.acceptLanguage) {
    reasons.push({
      code: 'MISSING_ACCEPT_LANGUAGE',
      description: 'Accept-Language header missing',
      impact: SCORE_ADJUSTMENTS.MISSING_ACCEPT_LANGUAGE,
      severity: 'medium',
    });
    flags.push('missing_headers');
    totalAdjustment += SCORE_ADJUSTMENTS.MISSING_ACCEPT_LANGUAGE;
  }

  // Missing Accept-Encoding
  if (!signals.acceptEncoding) {
    reasons.push({
      code: 'MISSING_ACCEPT_ENCODING',
      description: 'Accept-Encoding header missing',
      impact: SCORE_ADJUSTMENTS.MISSING_ACCEPT_ENCODING,
      severity: 'low',
    });
    totalAdjustment += SCORE_ADJUSTMENTS.MISSING_ACCEPT_ENCODING;
  }

  // Missing Accept
  if (!signals.accept) {
    reasons.push({
      code: 'MISSING_ACCEPT',
      description: 'Accept header missing',
      impact: SCORE_ADJUSTMENTS.MISSING_ACCEPT,
      severity: 'low',
    });
    totalAdjustment += SCORE_ADJUSTMENTS.MISSING_ACCEPT;
  }

  // ========================================================================
  // CLIENT HINTS CONSISTENCY
  // ========================================================================

  if (signals.secChUa) {
    const consistency = validateSecChUaConsistency(
      signals.userAgent,
      signals.secChUa,
      signals.secChUaMobile,
      signals.secChUaPlatform
    );

    if (!consistency.consistent) {
      reasons.push({
        code: 'SEC_CH_UA_MISMATCH',
        description: `Client Hints inconsistency: ${consistency.issues.join('; ')}`,
        impact: SCORE_ADJUSTMENTS.SEC_CH_UA_MISMATCH,
        severity: 'high',
      });
      flags.push('header_inconsistency');
      totalAdjustment += SCORE_ADJUSTMENTS.SEC_CH_UA_MISMATCH;
    } else {
      // Valid Client Hints is a positive signal
      reasons.push({
        code: 'VALID_CLIENT_HINTS',
        description: 'Client Hints present and consistent',
        impact: SCORE_ADJUSTMENTS.VALID_CLIENT_HINTS,
        severity: 'low',
      });
      totalAdjustment += SCORE_ADJUSTMENTS.VALID_CLIENT_HINTS;
    }
  }

  // ========================================================================
  // TLS CHECKS
  // ========================================================================

  if (signals.cfTlsVersion) {
    const tlsVersion = signals.cfTlsVersion.toLowerCase();
    
    // TLS 1.0 or 1.1 is suspicious (deprecated)
    if (tlsVersion.includes('1.0') || tlsVersion.includes('1.1')) {
      reasons.push({
        code: 'OLD_TLS_VERSION',
        description: `Deprecated TLS version: ${signals.cfTlsVersion}`,
        impact: SCORE_ADJUSTMENTS.OLD_TLS_VERSION,
        severity: 'medium',
      });
      flags.push('suspicious_tls');
      totalAdjustment += SCORE_ADJUSTMENTS.OLD_TLS_VERSION;
    }
  }

  // ========================================================================
  // FINGERPRINT CHECKS
  // ========================================================================

  // Suspicious WebGL renderer
  if (signals.webglRenderer) {
    const rendererLower = signals.webglRenderer.toLowerCase();
    const suspicious = SUSPICIOUS_WEBGL_RENDERERS.some(s => 
      rendererLower.includes(s.toLowerCase())
    );
    
    if (suspicious) {
      reasons.push({
        code: 'SUSPICIOUS_WEBGL',
        description: `Suspicious WebGL renderer: ${signals.webglRenderer}`,
        impact: SCORE_ADJUSTMENTS.SUSPICIOUS_WEBGL,
        severity: 'high',
      });
      flags.push('headless_browser');
      totalAdjustment += SCORE_ADJUSTMENTS.SUSPICIOUS_WEBGL;
    }
  }

  // No plugins (suspicious in desktop browsers)
  if (signals.pluginsHash === null && !isMobileUA(signals.userAgent)) {
    reasons.push({
      code: 'NO_PLUGINS',
      description: 'No browser plugins detected (desktop)',
      impact: SCORE_ADJUSTMENTS.NO_PLUGINS,
      severity: 'low',
    });
    totalAdjustment += SCORE_ADJUSTMENTS.NO_PLUGINS;
  }

  // No cookies
  if (signals.cookiesEnabled === false) {
    reasons.push({
      code: 'NO_COOKIES',
      description: 'Cookies disabled',
      impact: SCORE_ADJUSTMENTS.NO_COOKIES,
      severity: 'medium',
    });
    flags.push('no_cookies');
    totalAdjustment += SCORE_ADJUSTMENTS.NO_COOKIES;
  }

  // ========================================================================
  // BEHAVIORAL CHECKS
  // ========================================================================

  const hasBehavioral = signals.scrollDepth !== null || 
                        signals.timeOnPage !== null || 
                        signals.clicks !== null;

  if (hasBehavioral) {
    // Has behavioral data - positive signal
    reasons.push({
      code: 'HAS_BEHAVIORAL_DATA',
      description: 'Behavioral data present',
      impact: SCORE_ADJUSTMENTS.HAS_BEHAVIORAL_DATA,
      severity: 'low',
    });
    totalAdjustment += SCORE_ADJUSTMENTS.HAS_BEHAVIORAL_DATA;

    // Check for suspicious patterns
    const timeOnPage = signals.timeOnPage || 0;
    const scrollDepth = signals.scrollDepth || 0;
    const clicks = signals.clicks || 0;

    // Zero scroll after 30+ seconds
    if (timeOnPage >= 30000 && scrollDepth === 0) {
      reasons.push({
        code: 'ZERO_SCROLL_30S',
        description: 'No scrolling after 30+ seconds',
        impact: SCORE_ADJUSTMENTS.ZERO_SCROLL_30S,
        severity: 'medium',
      });
      flags.push('no_behavioral');
      totalAdjustment += SCORE_ADJUSTMENTS.ZERO_SCROLL_30S;
    }

    // Zero clicks after 30+ seconds
    if (timeOnPage >= 30000 && clicks === 0) {
      reasons.push({
        code: 'ZERO_CLICKS_30S',
        description: 'No clicks after 30+ seconds',
        impact: SCORE_ADJUSTMENTS.ZERO_CLICKS_30S,
        severity: 'medium',
      });
      totalAdjustment += SCORE_ADJUSTMENTS.ZERO_CLICKS_30S;
    }

    // Very short session (< 1 second)
    if (timeOnPage < 1000 && timeOnPage > 0) {
      reasons.push({
        code: 'VERY_SHORT_SESSION',
        description: 'Very short session (< 1 second)',
        impact: SCORE_ADJUSTMENTS.VERY_SHORT_SESSION,
        severity: 'medium',
      });
      totalAdjustment += SCORE_ADJUSTMENTS.VERY_SHORT_SESSION;
    }

    // Natural scroll pattern (good sign)
    if (scrollDepth > 25 && scrollDepth < 100) {
      reasons.push({
        code: 'NATURAL_SCROLL_PATTERN',
        description: 'Natural scroll pattern detected',
        impact: SCORE_ADJUSTMENTS.NATURAL_SCROLL_PATTERN,
        severity: 'low',
      });
      totalAdjustment += SCORE_ADJUSTMENTS.NATURAL_SCROLL_PATTERN;
    }

    // Multiple clicks (good sign)
    if (clicks >= 2) {
      reasons.push({
        code: 'MULTIPLE_CLICKS',
        description: 'Multiple clicks detected',
        impact: SCORE_ADJUSTMENTS.MULTIPLE_CLICKS,
        severity: 'low',
      });
      totalAdjustment += SCORE_ADJUSTMENTS.MULTIPLE_CLICKS;
    }
  } else {
    // No behavioral data at all
    reasons.push({
      code: 'NO_BEHAVIORAL_DATA',
      description: 'No behavioral data available',
      impact: SCORE_ADJUSTMENTS.NO_BEHAVIORAL_DATA,
      severity: 'low',
    });
    totalAdjustment += SCORE_ADJUSTMENTS.NO_BEHAVIORAL_DATA;
  }

  // ========================================================================
  // FINGERPRINT CONSISTENCY
  // ========================================================================

  if (signals.canvasHash && signals.webglVendor) {
    // Has consistent fingerprint
    reasons.push({
      code: 'CONSISTENT_FINGERPRINT',
      description: 'Consistent fingerprint data',
      impact: SCORE_ADJUSTMENTS.CONSISTENT_FINGERPRINT,
      severity: 'low',
    });
    totalAdjustment += SCORE_ADJUSTMENTS.CONSISTENT_FINGERPRINT;
  }

  return { reasons, flags, totalAdjustment };
}

/**
 * Check if User-Agent contains bot keywords
 */
function checkBotUserAgent(userAgent: string): { isBot: boolean; keyword: string | null } {
  const uaLower = userAgent.toLowerCase();
  
  for (const keyword of BOT_UA_KEYWORDS) {
    if (uaLower.includes(keyword)) {
      return { isBot: true, keyword };
    }
  }
  
  return { isBot: false, keyword: null };
}

/**
 * Check for headless browser indicators
 */
function checkHeadlessBrowser(signals: TrustSignals): { isHeadless: boolean; reason: string } {
  const ua = signals.userAgent.toLowerCase();
  
  // Explicit headless indicators
  if (ua.includes('headless')) {
    return { isHeadless: true, reason: 'HeadlessChrome in User-Agent' };
  }
  
  // Check WebGL renderer for headless indicators
  if (signals.webglRenderer) {
    const renderer = signals.webglRenderer.toLowerCase();
    if (renderer.includes('swiftshader') || renderer.includes('llvmpipe')) {
      return { isHeadless: true, reason: `Headless WebGL renderer: ${signals.webglRenderer}` };
    }
  }
  
  // PhantomJS detection
  if (ua.includes('phantomjs')) {
    return { isHeadless: true, reason: 'PhantomJS detected' };
  }
  
  return { isHeadless: false, reason: '' };
}

/**
 * Check for automation tool indicators
 */
function checkAutomationTools(userAgent: string): { isAutomation: boolean; tool: string | null } {
  const ua = userAgent.toLowerCase();
  
  const automationKeywords = [
    { keyword: 'selenium', name: 'Selenium' },
    { keyword: 'puppeteer', name: 'Puppeteer' },
    { keyword: 'playwright', name: 'Playwright' },
    { keyword: 'webdriver', name: 'WebDriver' },
    { keyword: 'cypress', name: 'Cypress' },
    { keyword: 'nightwatch', name: 'Nightwatch' },
    { keyword: 'testcafe', name: 'TestCafe' },
  ];
  
  for (const { keyword, name } of automationKeywords) {
    if (ua.includes(keyword)) {
      return { isAutomation: true, tool: name };
    }
  }
  
  return { isAutomation: false, tool: null };
}

/**
 * Get severity weight for sorting/display
 */
export function getSeverityWeight(severity: string): number {
  switch (severity) {
    case 'critical': return 4;
    case 'high': return 3;
    case 'medium': return 2;
    case 'low': return 1;
    default: return 0;
  }
}

/**
 * Sort reasons by severity (most severe first)
 */
export function sortReasonsBySeverity(reasons: TrustReason[]): TrustReason[] {
  return [...reasons].sort((a, b) => 
    getSeverityWeight(b.severity) - getSeverityWeight(a.severity)
  );
}
