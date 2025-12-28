// ============================================================================
// S.S.I. SHADOW - Google Analytics 4 Measurement Protocol
// ============================================================================
// GA4 Measurement Protocol for server-side tracking
// Docs: https://developers.google.com/analytics/devguides/collection/protocol/ga4
// ============================================================================

import { IncomingEvent, Env, PlatformResponse } from './types';
import { withRetry, RetryConfig } from './utils/retry';

// ============================================================================
// Types
// ============================================================================

/**
 * GA4 standard event names
 */
type GA4EventName =
  | 'page_view'
  | 'scroll'
  | 'click'
  | 'view_search_results'
  | 'purchase'
  | 'add_to_cart'
  | 'remove_from_cart'
  | 'begin_checkout'
  | 'add_payment_info'
  | 'add_shipping_info'
  | 'view_item'
  | 'view_item_list'
  | 'select_item'
  | 'add_to_wishlist'
  | 'generate_lead'
  | 'sign_up'
  | 'login'
  | 'search'
  | 'share'
  | 'select_content';

/**
 * GA4 Item (for e-commerce)
 */
interface GA4Item {
  item_id?: string;
  item_name?: string;
  item_brand?: string;
  item_category?: string;
  item_category2?: string;
  item_category3?: string;
  item_variant?: string;
  price?: number;
  quantity?: number;
  coupon?: string;
  discount?: number;
  affiliation?: string;
  index?: number;
}

/**
 * GA4 Event parameters
 */
interface GA4EventParams {
  // Common parameters
  currency?: string;
  value?: number;
  
  // E-commerce
  items?: GA4Item[];
  transaction_id?: string;
  tax?: number;
  shipping?: number;
  coupon?: string;
  payment_type?: string;
  shipping_tier?: string;
  
  // Content
  content_type?: string;
  content_id?: string;
  content_group?: string;
  
  // Search
  search_term?: string;
  
  // Engagement
  engagement_time_msec?: number;
  
  // Page
  page_title?: string;
  page_location?: string;
  page_referrer?: string;
  
  // User
  method?: string;  // for sign_up, login
  
  // Custom parameters (up to 25)
  [key: string]: unknown;
}

/**
 * GA4 Event structure
 */
interface GA4Event {
  name: GA4EventName | string;
  params?: GA4EventParams;
}

/**
 * GA4 User properties
 */
interface GA4UserProperties {
  [key: string]: {
    value: string | number;
  };
}

/**
 * GA4 Measurement Protocol payload
 */
interface GA4Payload {
  client_id: string;
  user_id?: string;
  timestamp_micros?: string;
  non_personalized_ads?: boolean;
  events: GA4Event[];
  user_properties?: GA4UserProperties;
}

/**
 * GA4 API response
 */
interface GA4Response {
  // GA4 MP returns empty body on success (204)
  // On error, returns validation messages
  validationMessages?: Array<{
    fieldPath: string;
    description: string;
    validationCode: string;
  }>;
}

// ============================================================================
// Constants
// ============================================================================

const GA4_MP_ENDPOINT = 'https://www.google-analytics.com/mp/collect';
const GA4_DEBUG_ENDPOINT = 'https://www.google-analytics.com/debug/mp/collect';

// Retry configuration
const GA4_RETRY_CONFIG: RetryConfig = {
  maxRetries: 3,
  baseDelayMs: 1000,
  maxDelayMs: 8000,
  retryableStatuses: [429, 500, 502, 503, 504],
};

// Event name mapping (SSI → GA4)
const EVENT_NAME_MAP: Record<string, GA4EventName | string> = {
  'PageView': 'page_view',
  'ViewContent': 'view_item',
  'Search': 'search',
  'AddToCart': 'add_to_cart',
  'RemoveFromCart': 'remove_from_cart',
  'AddToWishlist': 'add_to_wishlist',
  'InitiateCheckout': 'begin_checkout',
  'AddPaymentInfo': 'add_payment_info',
  'AddShippingInfo': 'add_shipping_info',
  'Purchase': 'purchase',
  'Lead': 'generate_lead',
  'CompleteRegistration': 'sign_up',
  'Login': 'login',
  'Share': 'share',
  'ViewItemList': 'view_item_list',
  'SelectItem': 'select_item',
  'SelectContent': 'select_content',
  'Scroll': 'scroll',
  'Click': 'click',
};

// ============================================================================
// Helper Functions
// ============================================================================

/**
 * Map SSI event name to GA4 event name
 */
function mapEventName(ssiEventName: string): string {
  return EVENT_NAME_MAP[ssiEventName] || ssiEventName.toLowerCase();
}

/**
 * Generate client_id from SSI ID
 * GA4 requires client_id in format: xxxxxxxxxx.yyyyyyyyyy
 */
function generateClientId(ssiId: string): string {
  // Use SSI ID hash as base
  let hash = 0;
  for (let i = 0; i < ssiId.length; i++) {
    const char = ssiId.charCodeAt(i);
    hash = ((hash << 5) - hash) + char;
    hash = hash & hash;
  }
  
  const part1 = Math.abs(hash).toString().padStart(10, '0').slice(0, 10);
  const part2 = Date.now().toString().slice(-10);
  
  return `${part1}.${part2}`;
}

/**
 * Build GA4 items from incoming event
 */
function buildItems(event: IncomingEvent): GA4Item[] | undefined {
  if (!event.content_ids || event.content_ids.length === 0) {
    return undefined;
  }

  return event.content_ids.map((id, index) => ({
    item_id: id,
    item_name: event.content_name || undefined,
    item_category: event.content_category || undefined,
    price: event.value && event.content_ids 
      ? event.value / event.content_ids.length 
      : undefined,
    quantity: event.num_items 
      ? Math.ceil(event.num_items / event.content_ids.length) 
      : 1,
    index,
  }));
}

/**
 * Build GA4 event parameters from incoming event
 */
function buildEventParams(event: IncomingEvent): GA4EventParams {
  const params: GA4EventParams = {};

  // Value and currency
  if (event.value !== undefined && event.value !== null) {
    params.value = event.value;
    params.currency = event.currency || 'BRL';
  }

  // Items (for e-commerce events)
  const items = buildItems(event);
  if (items) {
    params.items = items;
  }

  // Transaction ID (for purchase)
  if (event.order_id) {
    params.transaction_id = event.order_id;
  }

  // Page data
  if (event.url) {
    params.page_location = event.url;
  }
  if (event.referrer) {
    params.page_referrer = event.referrer;
  }
  if (event.title) {
    params.page_title = event.title;
  }

  // Search term
  if ((event as any).search_string) {
    params.search_term = (event as any).search_string;
  }

  // Engagement time
  if (event.time_on_page) {
    params.engagement_time_msec = event.time_on_page;
  }

  // Content info
  if (event.content_type) {
    params.content_type = event.content_type;
  }
  if (event.content_name) {
    params.content_group = event.content_name;
  }

  // Custom parameters from SSI
  if (event.predicted_ltv) {
    params.predicted_ltv = event.predicted_ltv;
  }
  if (event.predicted_intent) {
    params.predicted_intent = event.predicted_intent;
  }

  // Scroll depth
  if (event.scroll_depth) {
    params.scroll_depth = event.scroll_depth;
  }

  return params;
}

/**
 * Build GA4 user properties
 */
function buildUserProperties(event: IncomingEvent): GA4UserProperties | undefined {
  const props: GA4UserProperties = {};
  let hasProps = false;

  // Add SSI ID as user property
  if (event.ssi_id) {
    props.ssi_id = { value: event.ssi_id };
    hasProps = true;
  }

  // Add external ID
  if (event.external_id) {
    props.external_id = { value: event.external_id };
    hasProps = true;
  }

  // Add predicted LTV segment
  if (event.predicted_ltv) {
    const ltvSegment = event.predicted_ltv > 1000 ? 'high' :
                       event.predicted_ltv > 100 ? 'medium' : 'low';
    props.ltv_segment = { value: ltvSegment };
    hasProps = true;
  }

  return hasProps ? props : undefined;
}

/**
 * Build complete GA4 event
 */
function buildGA4Event(event: IncomingEvent): GA4Event {
  return {
    name: mapEventName(event.event_name),
    params: buildEventParams(event),
  };
}

/**
 * Build complete GA4 payload
 */
function buildGA4Payload(
  event: IncomingEvent,
  measurementId: string
): GA4Payload {
  const payload: GA4Payload = {
    client_id: generateClientId(event.ssi_id || crypto.randomUUID()),
    events: [buildGA4Event(event)],
  };

  // User ID (if external_id is available)
  if (event.external_id) {
    payload.user_id = event.external_id;
  }

  // Timestamp in microseconds
  if (event.timestamp) {
    payload.timestamp_micros = (event.timestamp * 1000).toString();
  }

  // User properties
  const userProps = buildUserProperties(event);
  if (userProps) {
    payload.user_properties = userProps;
  }

  return payload;
}

// ============================================================================
// API Functions
// ============================================================================

/**
 * Send event to Google Analytics 4 via Measurement Protocol
 */
export async function sendToGoogle(
  event: IncomingEvent,
  request: Request,
  env: Env
): Promise<PlatformResponse> {
  // Check if Google is enabled
  if (env.ENABLE_GOOGLE !== 'true') {
    return { sent: false, error: 'Google disabled' };
  }

  // Check required credentials
  if (!env.GA4_MEASUREMENT_ID) {
    console.error('[Google] Missing GA4_MEASUREMENT_ID');
    return { sent: false, error: 'Missing measurement ID' };
  }

  if (!env.GA4_API_SECRET) {
    console.error('[Google] Missing GA4_API_SECRET');
    return { sent: false, error: 'Missing API secret' };
  }

  try {
    // Build payload
    const payload = buildGA4Payload(event, env.GA4_MEASUREMENT_ID);

    // Build URL with query params
    const url = new URL(GA4_MP_ENDPOINT);
    url.searchParams.set('measurement_id', env.GA4_MEASUREMENT_ID);
    url.searchParams.set('api_secret', env.GA4_API_SECRET);

    console.log(`[Google] Sending ${event.event_name} → ${payload.events[0].name}`);

    // Send with retry
    const response = await withRetry(
      async () => {
        const res = await fetch(url.toString(), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });

        if (!res.ok && !GA4_RETRY_CONFIG.retryableStatuses.includes(res.status)) {
          const errorText = await res.text();
          console.error(`[Google] API error ${res.status}: ${errorText}`);
          throw new Error(`GA4 API error: ${res.status}`);
        }

        return res;
      },
      GA4_RETRY_CONFIG
    );

    // GA4 returns 204 No Content on success
    if (response.status === 204 || response.status === 200) {
      console.log(`[Google] Success: ${event.event_id}`);
      return {
        sent: true,
        status: response.status,
        events_received: 1,
      };
    } else {
      // Try to parse error response
      try {
        const errorData = await response.json() as GA4Response;
        if (errorData.validationMessages) {
          const errors = errorData.validationMessages
            .map(m => `${m.fieldPath}: ${m.description}`)
            .join('; ');
          console.error(`[Google] Validation errors: ${errors}`);
          return {
            sent: false,
            status: response.status,
            error: errors,
          };
        }
      } catch {
        // Ignore parse error
      }

      return {
        sent: false,
        status: response.status,
        error: `GA4 returned status ${response.status}`,
      };
    }
  } catch (error) {
    console.error('[Google] Error:', error);
    return {
      sent: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

/**
 * Send batch of events to Google Analytics 4
 * GA4 MP supports up to 25 events per request
 */
export async function sendBatchToGoogle(
  events: IncomingEvent[],
  request: Request,
  env: Env
): Promise<PlatformResponse> {
  if (env.ENABLE_GOOGLE !== 'true') {
    return { sent: false, error: 'Google disabled' };
  }

  if (!env.GA4_MEASUREMENT_ID || !env.GA4_API_SECRET) {
    return { sent: false, error: 'Missing Google credentials' };
  }

  try {
    // GA4 allows up to 25 events per request
    const batchSize = 25;
    let totalSent = 0;
    let errors: string[] = [];

    for (let i = 0; i < events.length; i += batchSize) {
      const batch = events.slice(i, i + batchSize);

      // Group by client_id
      const eventsByClient = new Map<string, GA4Event[]>();
      
      for (const event of batch) {
        const clientId = generateClientId(event.ssi_id || crypto.randomUUID());
        const ga4Event = buildGA4Event(event);
        
        if (!eventsByClient.has(clientId)) {
          eventsByClient.set(clientId, []);
        }
        eventsByClient.get(clientId)!.push(ga4Event);
      }

      // Send one request per client_id
      for (const [clientId, clientEvents] of eventsByClient) {
        const payload: GA4Payload = {
          client_id: clientId,
          events: clientEvents,
        };

        const url = new URL(GA4_MP_ENDPOINT);
        url.searchParams.set('measurement_id', env.GA4_MEASUREMENT_ID);
        url.searchParams.set('api_secret', env.GA4_API_SECRET);

        const response = await fetch(url.toString(), {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        });

        if (response.status === 204 || response.status === 200) {
          totalSent += clientEvents.length;
        } else {
          errors.push(`Failed batch for client ${clientId}`);
        }
      }
    }

    return {
      sent: totalSent > 0,
      events_received: totalSent,
      error: errors.length > 0 ? errors.join('; ') : undefined,
    };
  } catch (error) {
    console.error('[Google] Batch error:', error);
    return {
      sent: false,
      error: error instanceof Error ? error.message : 'Unknown error',
    };
  }
}

/**
 * Validate event for GA4 using debug endpoint
 */
export async function validateGA4Event(
  event: IncomingEvent,
  env: Env
): Promise<{
  valid: boolean;
  errors: string[];
}> {
  if (!env.GA4_MEASUREMENT_ID || !env.GA4_API_SECRET) {
    return { valid: false, errors: ['Missing Google credentials'] };
  }

  try {
    const payload = buildGA4Payload(event, env.GA4_MEASUREMENT_ID);

    const url = new URL(GA4_DEBUG_ENDPOINT);
    url.searchParams.set('measurement_id', env.GA4_MEASUREMENT_ID);
    url.searchParams.set('api_secret', env.GA4_API_SECRET);

    const response = await fetch(url.toString(), {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(payload),
    });

    const data = await response.json() as GA4Response;

    if (data.validationMessages && data.validationMessages.length > 0) {
      return {
        valid: false,
        errors: data.validationMessages.map(
          m => `${m.fieldPath}: ${m.description}`
        ),
      };
    }

    return { valid: true, errors: [] };
  } catch (error) {
    return {
      valid: false,
      errors: [error instanceof Error ? error.message : 'Validation failed'],
    };
  }
}

/**
 * Validate GA4 event locally (without API call)
 */
export function validateGA4EventLocal(event: IncomingEvent): {
  valid: boolean;
  warnings: string[];
} {
  const warnings: string[] = [];

  // Event name is required
  if (!event.event_name) {
    warnings.push('event_name is required');
  }

  // For purchase, transaction_id is recommended
  if (event.event_name === 'Purchase' && !event.order_id) {
    warnings.push('order_id (transaction_id) is recommended for Purchase events');
  }

  // For e-commerce events, items are recommended
  const ecommerceEvents = ['Purchase', 'AddToCart', 'ViewContent', 'InitiateCheckout'];
  if (ecommerceEvents.includes(event.event_name) && !event.content_ids) {
    warnings.push('content_ids (items) are recommended for e-commerce events');
  }

  // Value and currency together
  if (event.value && !event.currency) {
    warnings.push('currency is recommended when value is provided');
  }

  return {
    valid: warnings.filter(w => !w.includes('recommended')).length === 0,
    warnings,
  };
}

/**
 * Generate GA4 client_id for testing
 */
export function generateTestClientId(): string {
  const random1 = Math.floor(Math.random() * 10000000000);
  const random2 = Math.floor(Math.random() * 10000000000);
  return `${random1}.${random2}`;
}
