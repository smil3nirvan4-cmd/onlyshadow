// ============================================================================
// S.S.I. SHADOW - Pinterest Conversions API
// ============================================================================
// Server-side event tracking for Pinterest Ads

import { Env, IncomingEvent, PlatformResult } from './types';
import { hashEmail, hashPhone } from './utils/hash';
import { normalizePhone } from './utils/normalize';
import { withRetry } from './utils/retry';

// ----------------------------------------------------------------------------
// Types
// ----------------------------------------------------------------------------

interface PinterestUserData {
  em?: string[];      // hashed emails
  ph?: string[];      // hashed phones
  client_ip_address?: string;
  client_user_agent?: string;
  external_id?: string[];
  click_id?: string;  // epik from URL
}

interface PinterestCustomData {
  currency?: string;
  value?: string;
  content_ids?: string[];
  content_name?: string;
  content_category?: string;
  content_brand?: string;
  contents?: Array<{
    id?: string;
    item_price?: string;
    quantity?: number;
  }>;
  num_items?: number;
  order_id?: string;
  search_string?: string;
}

interface PinterestEvent {
  event_name: string;
  action_source: string;
  event_time: number;
  event_id: string;
  event_source_url?: string;
  partner_name?: string;
  user_data: PinterestUserData;
  custom_data?: PinterestCustomData;
  app_id?: string;
  app_name?: string;
  app_version?: string;
  device_brand?: string;
  device_model?: string;
  device_type?: string;
  os_version?: string;
  language?: string;
}

interface PinterestPayload {
  data: PinterestEvent[];
}

// ----------------------------------------------------------------------------
// Event Mapping
// ----------------------------------------------------------------------------

const EVENT_MAP: Record<string, string> = {
  'PageView': 'page_visit',
  'ViewContent': 'view_category',
  'AddToCart': 'add_to_cart',
  'InitiateCheckout': 'checkout',
  'Purchase': 'checkout',
  'Lead': 'lead',
  'CompleteRegistration': 'signup',
  'Search': 'search',
  'AddToWishlist': 'add_to_cart',
  'Subscribe': 'signup',
  'Contact': 'lead',
};

// ----------------------------------------------------------------------------
// Build Payload
// ----------------------------------------------------------------------------

function buildPayload(
  event: IncomingEvent,
  request: Request,
  env: Env
): PinterestPayload {
  const eventName = EVENT_MAP[event.event_name] || 'custom';

  // Build user data
  const userData: PinterestUserData = {};

  if (event.email) {
    userData.em = [hashEmail(event.email)];
  }

  if (event.phone) {
    userData.ph = [hashPhone(normalizePhone(event.phone))];
  }

  if (event.external_id) {
    userData.external_id = [event.external_id];
  }

  // Get IP
  const clientIp = request.headers.get('CF-Connecting-IP') || 
                   request.headers.get('X-Forwarded-For')?.split(',')[0];
  if (clientIp) {
    userData.client_ip_address = clientIp;
  }

  // User Agent
  const userAgent = request.headers.get('User-Agent');
  if (userAgent) {
    userData.client_user_agent = userAgent;
  }

  // Click ID (epik from URL)
  if (event.epik) {
    userData.click_id = event.epik;
  }

  // Build custom data
  const customData: PinterestCustomData = {};

  if (event.value) {
    customData.value = event.value.toString();
    customData.currency = event.currency || 'BRL';
  }

  if (event.content_ids) {
    customData.content_ids = event.content_ids;
    customData.contents = event.content_ids.map(id => ({
      id,
      quantity: 1,
    }));
  }

  if (event.content_name) {
    customData.content_name = event.content_name;
  }

  if (event.content_category) {
    customData.content_category = event.content_category;
  }

  if (event.num_items) {
    customData.num_items = event.num_items;
  }

  if (event.order_id) {
    customData.order_id = event.order_id;
  }

  // Build the event
  const pinterestEvent: PinterestEvent = {
    event_name: eventName,
    action_source: 'web',
    event_time: Math.floor((event.timestamp || Date.now()) / 1000),
    event_id: event.event_id || `pin_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    user_data: userData,
  };

  if (event.url) {
    pinterestEvent.event_source_url = event.url;
  }

  if (Object.keys(customData).length > 0) {
    pinterestEvent.custom_data = customData;
  }

  if (event.language) {
    pinterestEvent.language = event.language;
  }

  return {
    data: [pinterestEvent],
  };
}

// ----------------------------------------------------------------------------
// Send to Pinterest
// ----------------------------------------------------------------------------

async function sendRequest(
  payload: PinterestPayload,
  env: Env
): Promise<{ success: boolean; num_events_received?: number }> {
  const endpoint = `https://api.pinterest.com/v5/ad_accounts/${env.PINTEREST_AD_ACCOUNT_ID}/events`;

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.PINTEREST_ACCESS_TOKEN}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Pinterest API error: ${response.status} - ${errorText}`);
  }

  const result = await response.json() as { num_events_received?: number };
  
  return {
    success: true,
    num_events_received: result.num_events_received || 1,
  };
}

// ----------------------------------------------------------------------------
// Main Export
// ----------------------------------------------------------------------------

export async function sendToPinterest(
  event: IncomingEvent,
  request: Request,
  env: Env
): Promise<PlatformResult> {
  if (env.ENABLE_PINTEREST !== 'true') {
    return { sent: false, skipped: true, reason: 'Pinterest disabled' };
  }

  if (!env.PINTEREST_AD_ACCOUNT_ID || !env.PINTEREST_ACCESS_TOKEN) {
    return { sent: false, skipped: true, reason: 'Pinterest credentials not configured' };
  }

  try {
    const payload = buildPayload(event, request, env);

    console.log(`[Pinterest] Sending ${event.event_name} event`);

    const response = await withRetry(
      () => sendRequest(payload, env),
      3,
      1000
    );

    console.log(`[Pinterest] Success: ${response.num_events_received} events received`);

    return {
      sent: true,
      status: 200,
      events_received: response.num_events_received,
    };

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`[Pinterest] Error: ${errorMessage}`);
    return {
      sent: false,
      error: errorMessage,
    };
  }
}
