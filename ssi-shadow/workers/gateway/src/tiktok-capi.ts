// ============================================================================
// S.S.I. SHADOW - TikTok Events API Integration
// ============================================================================
// TikTok Events API v1.3 for server-side tracking
// Docs: https://business-api.tiktok.com/portal/docs?id=1771100865818625
// ============================================================================

import { IncomingEvent, Env, PlatformResponse } from './types';
import { withRetry, RetryConfig } from './utils/retry';
import { hashPII } from './utils/hash';

// ============================================================================
// Types
// ============================================================================

/**
 * TikTok Event names (must match exactly)
 */
type TikTokEventName =
  | 'ViewContent'
  | 'ClickButton'
  | 'Search'
  | 'AddToWishlist'
  | 'AddToCart'
  | 'InitiateCheckout'
  | 'AddPaymentInfo'
  | 'CompletePayment'
  | 'PlaceAnOrder'
  | 'Contact'
  | 'Download'
  | 'SubmitForm'
  | 'CompleteRegistration'
  | 'Subscribe';

/**
 * TikTok user data (for matching)
 */
interface TikTokUserData {
  // Hashed identifiers (SHA-256)
  sha256_email?: string;
  sha256_phone_number?: string;
  
  // External ID
  external_id?: string;
  
  // TikTok identifiers
  ttclid?: string;
  ttp?: string;  // TikTok browser ID cookie
  
  // Device info
  ip?: string;
  user_agent?: string;
  locale?: string;
}

/**
 * TikTok event properties
 */
interface TikTokProperties {
  // Content
  content_type?: 'product' | 'product_group';
  contents?: Array<{
    content_id?: string;
    content_type?: string;
    content_name?: string;
    content_category?: string;
    quantity?: number;
    price?: number;
    brand?: string;
  }>;
  content_id?: string;
  content_name?: string;
  content_category?: string;
  
  // Value
  value?: number;
  currency?: string;
  
  // Search
  query?: string;
  
  // Other
  description?: string;
  order_id?: string;
  shop_id?: string;
}

/**
 * TikTok page data
 */
interface TikTokPage {
  url?: string;
  referrer?: string;
}

/**
 * Single TikTok event
 */
interface TikTokEvent {
  event: TikTokEventName | string;
  event_id: string;
  event_time: number; // Unix timestamp in seconds
  user: TikTokUserData;
  properties?: TikTokProperties;
  page?: TikTokPage;
  
  // Optional
  test_event_code?: string;
}

/**
 * TikTok Events API request payload
 */
interface TikTokEventsPayload {
  pixel_code: string;
  event_source: 'web';
  event_source_id: string;
  data: TikTokEvent[];
  
  // Optional test mode
  test_event_code?: string;
}

/**
 * TikTok API response
 */
interface TikTokAPIResponse {
  code: number;
  message: string;
  request_id?: string;
  data?: {
    events_received?: number;
  };
}

// ============================================================================
// Constants
// ============================================================================

const TIKTOK_API_BASE = 'https://business-api.tiktok.com/open_api/v1.3';
const TIKTOK_EVENTS_ENDPOINT = '/event/track/';

// Retry configuration for TikTok API
const TIKTOK_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 8000,
  retryableStatuses: [429, 500, 502, 503, 504],
};

// Event name mapping (SSI → TikTok)
const EVENT_NAME_MAP: Record<string, TikTokEventName | string> = {
  'PageView': 'ViewContent',
  'ViewContent': 'ViewContent',
  'Search': 'Search',
  'AddToCart': 'AddToCart',
  'AddToWishlist': 'AddToWishlist',
  'InitiateCheckout': 'InitiateCheckout',
  'AddPaymentInfo': 'AddPaymentInfo',
  'Purchase': 'CompletePayment',
  'CompletePayment': 'CompletePayment',
  'PlaceAnOrder': 'PlaceAnOrder',
  'Lead': 'SubmitForm',
  'SubmitForm': 'SubmitForm',
  'CompleteRegistration': 'CompleteRegistration',
  'Subscribe': 'Subscribe',
  'Contact': 'Contact',
  'Download': 'Download',
  'ClickButton': 'ClickButton',
};

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Map SSI event name to TikTok event name
 */
function mapEventName(ssiEventName: string): string {
  return EVENT_NAME_MAP[ssiEventName] || ssiEventName;
}

/**
 * Normalize phone number for TikTok (E.164 without +)
 */
function normalizePhoneForTikTok(phone: string): string {
  // Remove all non-digits
  let normalized = phone.replace(/\D/g, '');
  
  // Add Brazil country code if not present
  if (normalized.length === 10 || normalized.length === 11) {
    normalized = '55' + normalized;
  }
  
  return normalized;
}

/**
 * Build TikTok user data from incoming event
 */
function buildUserData(
  event: IncomingEvent,
  request: Request
): TikTokUserData {
  const headers = request.headers;
  const userData: TikTokUserData = {};

  // Hashed email
  if (event.email) {
    const normalizedEmail = event.email.toLowerCase().trim();
    userData.sha256_email = hashPII(normalizedEmail);
  } else if (event.email_hash) {
    userData.sha256_email = event.email_hash;
  }

  // Hashed phone
  if (event.phone) {
    const normalizedPhone = normalizePhoneForTikTok(event.phone);
    userData.sha256_phone_number = hashPII(normalizedPhone);
  } else if (event.phone_hash) {
    userData.sha256_phone_number = event.phone_hash;
  }

  // External ID
  if (event.external_id) {
    userData.external_id = event.external_id;
  }

  // TikTok Click ID (from URL or cookie)
  if (event.ttclid) {
    userData.ttclid = event.ttclid;
  }

  // TikTok browser ID (from _ttp cookie)
  // This should be passed from Ghost Script
  if ((event as any).ttp) {
    userData.ttp = (event as any).ttp;
  }

  // IP Address
  const ip = headers.get('CF-Connecting-IP') || 
             headers.get('X-Forwarded-For')?.split(',')[0]?.trim();
  if (ip) {
    userData.ip = ip;
  }

  // User Agent
  const userAgent = event.user_agent || headers.get('User-Agent');
  if (userAgent) {
    userData.user_agent = userAgent;
  }

  // Locale
  if (event.language) {
    userData.locale = event.language;
  }

  return userData;
}

/**
 * Build TikTok properties from incoming event
 */
function buildProperties(event: IncomingEvent): TikTokProperties | undefined {
  const properties: TikTokProperties = {};
  let hasProperties = false;

  // Value and currency
  if (event.value !== undefined && event.value !== null) {
    properties.value = event.value;
    properties.currency = event.currency || 'BRL';
    hasProperties = true;
  }

  // Content IDs
  if (event.content_ids && event.content_ids.length > 0) {
    properties.contents = event.content_ids.map(id => ({
      content_id: id,
      content_type: event.content_type || 'product',
    }));
    properties.content_type = 'product';
    hasProperties = true;
  }

  // Content name and category
  if (event.content_name) {
    properties.content_name = event.content_name;
    hasProperties = true;
  }
  if (event.content_category) {
    properties.content_category = event.content_category;
    hasProperties = true;
  }

  // Order ID
  if (event.order_id) {
    properties.order_id = event.order_id;
    hasProperties = true;
  }

  // Search query (if Search event)
  if ((event as any).search_string) {
    properties.query = (event as any).search_string;
    hasProperties = true;
  }

  return hasProperties ? properties : undefined;
}

/**
 * Build TikTok page data from incoming event
 */
function buildPageData(event: IncomingEvent): TikTokPage | undefined {
  const page: TikTokPage = {};
  let hasPage = false;

  if (event.url) {
    page.url = event.url;
    hasPage = true;
  }

  if (event.referrer) {
    page.referrer = event.referrer;
    hasPage = true;
  }

  return hasPage ? page : undefined;
}

/**
 * Build complete TikTok event
 */
function buildTikTokEvent(
  event: IncomingEvent,
  request: Request,
  testEventCode?: string
): TikTokEvent {
  const tiktokEvent: TikTokEvent = {
    event: mapEventName(event.event_name),
    event_id: event.event_id || crypto.randomUUID(),
    event_time: Math.floor((event.timestamp || Date.now()) / 1000),
    user: buildUserData(event, request),
  };

  // Add properties
  const properties = buildProperties(event);
  if (properties) {
    tiktokEvent.properties = properties;
  }

  // Add page data
  const page = buildPageData(event);
  if (page) {
    tiktokEvent.page = page;
  }

  // Test event code
  if (testEventCode) {
    tiktokEvent.test_event_code = testEventCode;
  }

  return tiktokEvent;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Send event to TikTok Events API
 */
export async function sendToTikTok(
  event: IncomingEvent,
  request: Request,
  env: Env
): Promise<PlatformResponse> {
  // Check if TikTok is enabled
  if (env.ENABLE_TIKTOK !== 'true') {
    return { sent: false, error: 'TikTok disabled' };
  }

  // Check required credentials
  if (!env.TIKTOK_PIXEL_ID) {
    console.error('[TikTok] Missing TIKTOK_PIXEL_ID');
    return { sent: false, error: 'Missing pixel ID' };
  }

  if (!env.TIKTOK_ACCESS_TOKEN) {
    console.error('[TikTok] Missing TIKTOK_ACCESS_TOKEN');
    return { sent: false, error: 'Missing access token' };
  }

  try {
    // Build TikTok event
    const tiktokEvent = buildTikTokEvent(
      event,
      request,
      env.TIKTOK_TEST_EVENT_CODE
    );

    // Build payload
    const payload: TikTokEventsPayload = {
      pixel_code: env.TIKTOK_PIXEL_ID,
      event_source: 'web',
      event_source_id: env.TIKTOK_PIXEL_ID,
      data: [tiktokEvent],
    };

    if (env.TIKTOK_TEST_EVENT_CODE) {
      payload.test_event_code = env.TIKTOK_TEST_EVENT_CODE;
    }

    console.log(`[TikTok] Sending ${event.event_name} → ${tiktokEvent.event}`);

    // Send with retry
    const response = await withRetry(
      async () => {
        const res = await fetch(`${TIKTOK_API_BASE}${TIKTOK_EVENTS_ENDPOINT}`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Access-Token': env.TIKTOK_ACCESS_TOKEN!,
          },
          body: JSON.stringify(payload),
        });

        if (!res.ok && !TIKTOK_RETRY_CONFIG.retryableStatuses.includes(res.status)) {
          // Non-retryable error
          const errorText = await res.text();
          console.error(`[TikTok] API error ${res.status}: ${errorText}`);
          throw new Error(`TikTok API error: ${res.status}`);
        }

        return res;
      },
      TIKTOK_RETRY_CONFIG
    );

    const responseData = await response.json() as TikTokAPIResponse;

    // TikTok returns code 0 for success
    if (responseData.code === 0) {
      console.log(`[TikTok] Success: ${event.event_id}`);
      return {
        sent: true,
        status: response.status,
        events_received: responseData.data?.events_received || 1,
      };
    } else {
      console.error(`[TikTok] API returned error: ${responseData.code} - ${responseData.message}`);
      return {
        sent: false,
        status: response.status,
        error: `TikTok error: ${responseData.message}`,
      };
    }
  } catch (error) {
    console.error('[TikTok] Error:', error);
    return {
      sent: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

/**
 * Send batch of events to TikTok
 */
export async function sendBatchToTikTok(
  events: IncomingEvent[],
  request: Request,
  env: Env
): Promise<PlatformResponse> {
  if (env.ENABLE_TIKTOK !== 'true') {
    return { sent: false, error: 'TikTok disabled' };
  }

  if (!env.TIKTOK_PIXEL_ID || !env.TIKTOK_ACCESS_TOKEN) {
    return { sent: false, error: 'Missing TikTok credentials' };
  }

  try {
    // Build all events
    const tiktokEvents = events.map(event =>
      buildTikTokEvent(event, request, env.TIKTOK_TEST_EVENT_CODE)
    );

    // TikTok allows up to 1000 events per request
    const batchSize = 1000;
    let totalSent = 0;
    let errors: string[] = [];

    for (let i = 0; i < tiktokEvents.length; i += batchSize) {
      const batch = tiktokEvents.slice(i, i + batchSize);

      const payload: TikTokEventsPayload = {
        pixel_code: env.TIKTOK_PIXEL_ID,
        event_source: 'web',
        event_source_id: env.TIKTOK_PIXEL_ID,
        data: batch,
      };

      if (env.TIKTOK_TEST_EVENT_CODE) {
        payload.test_event_code = env.TIKTOK_TEST_EVENT_CODE;
      }

      const response = await fetch(`${TIKTOK_API_BASE}${TIKTOK_EVENTS_ENDPOINT}`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Access-Token': env.TIKTOK_ACCESS_TOKEN!,
        },
        body: JSON.stringify(payload),
      });

      const responseData = await response.json() as TikTokAPIResponse;

      if (responseData.code === 0) {
        totalSent += batch.length;
      } else {
        errors.push(responseData.message);
      }
    }

    return {
      sent: totalSent > 0,
      events_received: totalSent,
      error: errors.length > 0 ? errors.join('; ') : undefined,
    };
  } catch (error) {
    console.error('[TikTok] Batch error:', error);
    return {
      sent: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

/**
 * Validate TikTok event
 */
export function validateTikTokEvent(event: IncomingEvent): {
  valid: boolean;
  errors: string[];
} {
  const errors: string[] = [];

  // Event name is required
  if (!event.event_name) {
    errors.push('event_name is required');
  }

  // For Purchase/CompletePayment, value and currency are recommended
  if (
    event.event_name === 'Purchase' ||
    event.event_name === 'CompletePayment'
  ) {
    if (!event.value) {
      errors.push('value is recommended for Purchase events');
    }
  }

  // User data - at least one identifier is recommended
  const hasIdentifier =
    event.email ||
    event.email_hash ||
    event.phone ||
    event.phone_hash ||
    event.ttclid ||
    event.external_id;

  if (!hasIdentifier) {
    errors.push('At least one user identifier is recommended');
  }

  return {
    valid: errors.filter(e => !e.includes('recommended')).length === 0,
    errors,
  };
}

/**
 * Estimate TikTok Event Match Quality
 */
export function estimateTikTokEMQ(event: IncomingEvent): number {
  let score = 0;

  // Email: +3
  if (event.email || event.email_hash) score += 3;

  // Phone: +2
  if (event.phone || event.phone_hash) score += 2;

  // TikTok Click ID: +3
  if (event.ttclid) score += 3;

  // External ID: +1
  if (event.external_id) score += 1;

  // IP: +0.5
  if (event.ip_address) score += 0.5;

  // User Agent: +0.5
  if (event.user_agent) score += 0.5;

  return Math.min(score, 10);
}
