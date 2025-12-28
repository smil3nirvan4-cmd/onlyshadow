// ============================================================================
// S.S.I. SHADOW - Trust Score Type Definitions
// ============================================================================

/**
 * Signals extracted from request and payload for trust scoring
 */
export interface TrustSignals {
  // Request headers
  userAgent: string;
  ip: string;
  acceptLanguage: string | null;
  acceptEncoding: string | null;
  accept: string | null;
  connection: string | null;
  
  // Client Hints (Chrome 89+)
  secChUa: string | null;
  secChUaMobile: string | null;
  secChUaPlatform: string | null;
  secChUaFullVersion: string | null;
  secFetchSite: string | null;
  secFetchMode: string | null;
  secFetchDest: string | null;
  
  // Cloudflare headers
  cfRay: string | null;
  cfConnectingIp: string | null;
  cfIpCountry: string | null;
  cfIpCity: string | null;
  cfIpContinent: string | null;
  cfIpAsn: number | null;
  cfIpAsOrganization: string | null;
  cfTlsVersion: string | null;
  cfTlsCipher: string | null;
  
  // Ghost Script data
  canvasHash: string | null;
  webglVendor: string | null;
  webglRenderer: string | null;
  pluginsHash: string | null;
  pluginsCount: number | null;
  touchSupport: boolean | null;
  cookiesEnabled: boolean | null;
  
  // Behavioral data
  scrollDepth: number | null;
  timeOnPage: number | null;
  clicks: number | null;
  sessionDuration: number | null;
  sessionPageviews: number | null;
  
  // Fingerprint consistency
  screenWidth: number | null;
  screenHeight: number | null;
  viewportWidth: number | null;
  viewportHeight: number | null;
  devicePixelRatio: number | null;
  colorDepth: number | null;
  timezone: string | null;
  language: string | null;
  hardwareConcurrency: number | null;
  deviceMemory: number | null;
}

/**
 * Result of trust score calculation
 */
export interface TrustScore {
  score: number;           // 0.0 (definitely bot) to 1.0 (definitely human)
  confidence: number;      // 0.0 to 1.0 - how confident are we in this score
  action: TrustAction;     // What action to take
  reasons: TrustReason[];  // Detailed breakdown of penalties/bonuses
  category: TrustCategory; // Overall categorization
  flags: TrustFlag[];      // Specific flags detected
}

/**
 * Action to take based on trust score
 */
export type TrustAction = 'allow' | 'challenge' | 'block';

/**
 * Category of the visitor
 */
export type TrustCategory = 
  | 'human'           // Definitely human
  | 'likely_human'    // Probably human
  | 'uncertain'       // Could be either
  | 'likely_bot'      // Probably bot
  | 'bot';            // Definitely bot

/**
 * Individual reason for score adjustment
 */
export interface TrustReason {
  code: string;           // e.g., 'BOT_UA', 'DATACENTER_IP'
  description: string;    // Human-readable description
  impact: number;         // Score adjustment (negative = penalty)
  severity: 'low' | 'medium' | 'high' | 'critical';
}

/**
 * Specific flags detected
 */
export type TrustFlag = 
  | 'bot_user_agent'
  | 'headless_browser'
  | 'datacenter_ip'
  | 'missing_headers'
  | 'header_inconsistency'
  | 'suspicious_tls'
  | 'no_javascript'
  | 'no_cookies'
  | 'rate_limited'
  | 'no_behavioral'
  | 'automation_tool'
  | 'proxy_detected'
  | 'tor_exit_node'
  | 'vpn_detected';

/**
 * Rate limit entry stored in KV
 */
export interface RateLimitEntry {
  count: number;
  firstSeen: number;
  lastSeen: number;
  blocked: boolean;
}

/**
 * Rate limit check result
 */
export interface RateLimitResult {
  allowed: boolean;
  current: number;
  limit: number;
  remaining: number;
  resetAt: number;
  blocked: boolean;
}

/**
 * Known datacenter ASNs
 */
export const DATACENTER_ASNS: Set<number> = new Set([
  // Amazon AWS
  14618, 16509, 7224, 8987,
  // Google Cloud
  15169, 396982, 36040, 396986,
  // Microsoft Azure
  8075, 8068, 8069,
  // DigitalOcean
  14061,
  // Linode / Akamai
  63949, 20940,
  // Vultr
  20473, 64515,
  // OVH
  16276,
  // Hetzner
  24940, 213230,
  // Cloudflare
  13335,
  // Shadow Cloud
  31898,
  // IBM Cloud
  36351,
  // Alibaba Cloud
  45102,
  // Tencent Cloud
  132203,
  // HostGator / Endurance
  46606,
  // GoDaddy
  26496,
  // Rackspace
  33070,
  // Scaleway
  12876,
  // Contabo
  51167,
]);

/**
 * Known bot User-Agent keywords (lowercase)
 */
export const BOT_UA_KEYWORDS: string[] = [
  // Explicit bots
  'bot', 'crawler', 'spider', 'scraper', 'slurp',
  // HTTP clients
  'python', 'python-requests', 'python-urllib',
  'curl', 'wget', 'libwww',
  'httpclient', 'http-client', 'httpunit',
  'java/', 'java-', 'apache-http',
  'go-http', 'go-client', 'golang',
  'node-fetch', 'axios', 'got/',
  'ruby', 'perl', 'php/',
  // Automation tools
  'selenium', 'puppeteer', 'playwright', 'phantomjs',
  'headless', 'headlesschrome',
  'nightmare', 'casperjs', 'slimerjs',
  // API clients
  'postman', 'insomnia', 'httpie', 'rest-client',
  // Monitoring
  'pingdom', 'uptimerobot', 'newrelic', 'datadog',
  'site24x7', 'statuscake', 'gtmetrix',
  // SEO tools
  'ahrefsbot', 'semrushbot', 'mj12bot', 'dotbot',
  'baiduspider', 'yandexbot', 'sogou',
  // Social
  'facebookexternalhit', 'twitterbot', 'linkedinbot',
  'slackbot', 'telegrambot', 'whatsapp', 'discordbot',
  // Others
  'archive.org', 'wayback', 'httrack', 'webcopier',
];

/**
 * Suspicious WebGL renderers (headless/virtual)
 */
export const SUSPICIOUS_WEBGL_RENDERERS: string[] = [
  'swiftshader',
  'llvmpipe',
  'mesa',
  'virtualbox',
  'vmware',
  'parallels',
  'google swiftshader',
  'software rasterizer',
];

/**
 * Trust score thresholds
 */
export const TRUST_THRESHOLDS = {
  BLOCK: 0.3,      // Score below this = block
  CHALLENGE: 0.6,  // Score below this = challenge (but above BLOCK)
  ALLOW: 0.6,      // Score above this = allow
} as const;

/**
 * Score adjustments for each signal
 */
export const SCORE_ADJUSTMENTS = {
  // Severe penalties (high confidence bot indicators)
  BOT_USER_AGENT: -0.8,
  HEADLESS_BROWSER: -0.7,
  AUTOMATION_TOOL: -0.8,
  RATE_LIMIT_EXCEEDED: -0.9,
  
  // Moderate penalties
  DATACENTER_IP: -0.5,
  MISSING_ACCEPT_LANGUAGE: -0.2,
  MISSING_ACCEPT_ENCODING: -0.15,
  MISSING_ACCEPT: -0.1,
  SEC_CH_UA_MISMATCH: -0.4,
  OLD_TLS_VERSION: -0.3,
  SUSPICIOUS_WEBGL: -0.5,
  NO_PLUGINS: -0.15,
  
  // Light penalties
  NO_COOKIES: -0.2,
  ZERO_SCROLL_30S: -0.3,
  ZERO_CLICKS_30S: -0.2,
  VERY_SHORT_SESSION: -0.2,
  NO_BEHAVIORAL_DATA: -0.1,
  
  // Bonuses (human indicators)
  HAS_BEHAVIORAL_DATA: 0.1,
  NATURAL_SCROLL_PATTERN: 0.1,
  MULTIPLE_CLICKS: 0.1,
  CONSISTENT_FINGERPRINT: 0.1,
  RESIDENTIAL_IP: 0.15,
  VALID_CLIENT_HINTS: 0.1,
} as const;
