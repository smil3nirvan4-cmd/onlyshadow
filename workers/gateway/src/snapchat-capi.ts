// ============================================================================
// S.S.I. SHADOW - Snapchat Conversions API
// ============================================================================
// Server-side event tracking for Snapchat Ads

import { Env, IncomingEvent, PlatformResult } from './types';
import { hashEmail, hashPhone } from './utils/hash';
import { normalizePhone } from './utils/normalize';
import { withRetry } from './utils/retry';

// ----------------------------------------------------------------------------
// Types
// ----------------------------------------------------------------------------

interface SnapchatEvent {
  event_type: string;
  event_conversion_type: string;
  event_tag?: string;
  timestamp: string;
  hashed_email?: string;
  hashed_phone_number?: string;
  hashed_ip_address?: string;
  user_agent?: string;
  click_id?: string; // ScCid
  uuid_c1?: string;  // _scid cookie
  page_url?: string;
  price?: number;
  currency?: string;
  transaction_id?: string;
  item_ids?: string[];
  item_category?: string;
  number_items?: number;
  description?: string;
}

interface SnapchatPayload {
  pixel_id: string;
  events: SnapchatEvent[];
  test_event_code?: string;
}

// ----------------------------------------------------------------------------
// Event Mapping
// ----------------------------------------------------------------------------

const EVENT_MAP: Record<string, { type: string; conversionType: string }> = {
  'PageView': { type: 'PAGE_VIEW', conversionType: 'WEB' },
  'ViewContent': { type: 'VIEW_CONTENT', conversionType: 'WEB' },
  'AddToCart': { type: 'ADD_CART', conversionType: 'WEB' },
  'InitiateCheckout': { type: 'START_CHECKOUT', conversionType: 'WEB' },
  'AddPaymentInfo': { type: 'ADD_BILLING', conversionType: 'WEB' },
  'Purchase': { type: 'PURCHASE', conversionType: 'WEB' },
  'Lead': { type: 'SIGN_UP', conversionType: 'WEB' },
  'CompleteRegistration': { type: 'SIGN_UP', conversionType: 'WEB' },
  'Search': { type: 'SEARCH', conversionType: 'WEB' },
  'Subscribe': { type: 'SUBSCRIBE', conversionType: 'WEB' },
  'AddToWishlist': { type: 'ADD_TO_WISHLIST', conversionType: 'WEB' },
};

// ----------------------------------------------------------------------------
// Build Payload
// ----------------------------------------------------------------------------

function buildPayload(
  event: IncomingEvent,
  request: Request,
  env: Env
): SnapchatPayload {
  const eventMapping = EVENT_MAP[event.event_name] || { 
    type: 'CUSTOM', 
    conversionType: 'WEB' 
  };

  const snapEvent: SnapchatEvent = {
    event_type: eventMapping.type,
    event_conversion_type: eventMapping.conversionType,
    timestamp: new Date(event.timestamp || Date.now()).toISOString(),
  };

  // Hash PII
  if (event.email) {
    snapEvent.hashed_email = hashEmail(event.email);
  }

  if (event.phone) {
    snapEvent.hashed_phone_number = hashPhone(normalizePhone(event.phone));
  }

  // Get IP and hash it
  const clientIp = request.headers.get('CF-Connecting-IP') || 
                   request.headers.get('X-Forwarded-For')?.split(',')[0];
  if (clientIp) {
    snapEvent.hashed_ip_address = hashEmail(clientIp);
  }

  // User Agent
  const userAgent = request.headers.get('User-Agent');
  if (userAgent) {
    snapEvent.user_agent = userAgent;
  }

  // Click ID (ScCid from URL)
  if (event.sccid) {
    snapEvent.click_id = event.sccid;
  }

  // Page URL
  if (event.url) {
    snapEvent.page_url = event.url;
  }

  // E-commerce data
  if (event.value) {
    snapEvent.price = event.value;
    snapEvent.currency = event.currency || 'BRL';
  }

  if (event.order_id) {
    snapEvent.transaction_id = event.order_id;
  }

  if (event.content_ids) {
    snapEvent.item_ids = event.content_ids;
  }

  if (event.content_category) {
    snapEvent.item_category = event.content_category;
  }

  if (event.num_items) {
    snapEvent.number_items = event.num_items;
  }

  if (event.content_name) {
    snapEvent.description = event.content_name;
  }

  // Custom event tag
  if (eventMapping.type === 'CUSTOM') {
    snapEvent.event_tag = event.event_name.toUpperCase();
  }

  const payload: SnapchatPayload = {
    pixel_id: env.SNAPCHAT_PIXEL_ID || '',
    events: [snapEvent],
  };

  // Test mode
  if (env.SNAPCHAT_TEST_EVENT_CODE) {
    payload.test_event_code = env.SNAPCHAT_TEST_EVENT_CODE;
  }

  return payload;
}

// ----------------------------------------------------------------------------
// Send to Snapchat
// ----------------------------------------------------------------------------

async function sendRequest(
  payload: SnapchatPayload,
  env: Env
): Promise<{ success: boolean; events_received?: number }> {
  const endpoint = 'https://tr.snapchat.com/v2/conversion';

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.SNAPCHAT_ACCESS_TOKEN}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Snapchat API error: ${response.status} - ${errorText}`);
  }

  const result = await response.json() as { status?: string; events_received?: number };
  
  return {
    success: true,
    events_received: result.events_received || 1,
  };
}

// ----------------------------------------------------------------------------
// Main Export
// ----------------------------------------------------------------------------

export async function sendToSnapchat(
  event: IncomingEvent,
  request: Request,
  env: Env
): Promise<PlatformResult> {
  if (env.ENABLE_SNAPCHAT !== 'true') {
    return { sent: false, skipped: true, reason: 'Snapchat disabled' };
  }

  if (!env.SNAPCHAT_PIXEL_ID || !env.SNAPCHAT_ACCESS_TOKEN) {
    return { sent: false, skipped: true, reason: 'Snapchat credentials not configured' };
  }

  try {
    const payload = buildPayload(event, request, env);

    console.log(`[Snapchat] Sending ${event.event_name} event`);

    const response = await withRetry(
      () => sendRequest(payload, env),
      3,
      1000
    );

    console.log(`[Snapchat] Success: ${response.events_received} events received`);

    return {
      sent: true,
      status: 200,
      events_received: response.events_received,
    };

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`[Snapchat] Error: ${errorMessage}`);
    return {
      sent: false,
      error: errorMessage,
    };
  }
}
