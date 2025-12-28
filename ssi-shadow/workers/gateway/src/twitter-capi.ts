// ============================================================================
// S.S.I. SHADOW - Twitter/X Conversions API
// ============================================================================
// Server-side event tracking for Twitter/X Ads

import { Env, IncomingEvent, PlatformResult } from './types';
import { hashEmail, hashPhone } from './utils/hash';
import { normalizePhone } from './utils/normalize';
import { withRetry } from './utils/retry';

// ----------------------------------------------------------------------------
// Types
// ----------------------------------------------------------------------------

interface TwitterConversion {
  conversion_time: string;
  event_id: string;
  identifiers: Array<{
    hashed_email?: string;
    hashed_phone_number?: string;
    twclid?: string;
  }>;
  conversion_id: string;
  description?: string;
  number_items?: number;
  price_currency?: string;
  value?: string;
  contents?: Array<{
    content_id?: string;
    content_name?: string;
    content_price?: string;
    num_items?: number;
    content_group_id?: string;
  }>;
}

interface TwitterPayload {
  conversions: TwitterConversion[];
}

// ----------------------------------------------------------------------------
// Event Mapping
// ----------------------------------------------------------------------------

const EVENT_MAP: Record<string, string> = {
  'PageView': 'page_view',
  'ViewContent': 'content_view',
  'AddToCart': 'add_to_cart',
  'InitiateCheckout': 'checkout_initiated',
  'Purchase': 'purchase',
  'Lead': 'sign_up',
  'CompleteRegistration': 'sign_up',
  'Search': 'search',
  'Subscribe': 'subscribe',
  'Download': 'download',
  'AddToWishlist': 'add_to_wishlist',
};

// ----------------------------------------------------------------------------
// Build Payload
// ----------------------------------------------------------------------------

function buildPayload(
  event: IncomingEvent,
  request: Request,
  env: Env
): TwitterPayload {
  const identifiers: TwitterConversion['identifiers'] = [];

  // Add hashed email
  if (event.email) {
    identifiers.push({
      hashed_email: hashEmail(event.email),
    });
  }

  // Add hashed phone
  if (event.phone) {
    identifiers.push({
      hashed_phone_number: hashPhone(normalizePhone(event.phone)),
    });
  }

  // Add twclid
  if (event.twclid) {
    identifiers.push({
      twclid: event.twclid,
    });
  }

  const conversion: TwitterConversion = {
    conversion_time: new Date(event.timestamp || Date.now()).toISOString(),
    event_id: event.event_id || `tw_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    identifiers,
    conversion_id: env.TWITTER_CONVERSION_ID || '',
  };

  // Add value
  if (event.value) {
    conversion.value = event.value.toString();
    conversion.price_currency = event.currency || 'BRL';
  }

  // Add description
  if (event.content_name) {
    conversion.description = event.content_name;
  }

  // Add number of items
  if (event.num_items) {
    conversion.number_items = event.num_items;
  }

  // Add contents
  if (event.content_ids) {
    conversion.contents = event.content_ids.map(id => ({
      content_id: id,
      num_items: 1,
    }));
  }

  return {
    conversions: [conversion],
  };
}

// ----------------------------------------------------------------------------
// Send to Twitter
// ----------------------------------------------------------------------------

async function sendRequest(
  payload: TwitterPayload,
  env: Env
): Promise<{ success: boolean }> {
  const endpoint = `https://ads-api.twitter.com/12/measurement/conversions/${env.TWITTER_PIXEL_ID}`;

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.TWITTER_ACCESS_TOKEN}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Twitter API error: ${response.status} - ${errorText}`);
  }

  return { success: true };
}

// ----------------------------------------------------------------------------
// Main Export
// ----------------------------------------------------------------------------

export async function sendToTwitter(
  event: IncomingEvent,
  request: Request,
  env: Env
): Promise<PlatformResult> {
  if (env.ENABLE_TWITTER !== 'true') {
    return { sent: false, skipped: true, reason: 'Twitter disabled' };
  }

  if (!env.TWITTER_PIXEL_ID || !env.TWITTER_ACCESS_TOKEN) {
    return { sent: false, skipped: true, reason: 'Twitter credentials not configured' };
  }

  try {
    const payload = buildPayload(event, request, env);

    console.log(`[Twitter] Sending ${event.event_name} event`);

    await withRetry(
      () => sendRequest(payload, env),
      3,
      1000
    );

    console.log(`[Twitter] Success`);

    return {
      sent: true,
      status: 200,
      events_received: 1,
    };

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`[Twitter] Error: ${errorMessage}`);
    return {
      sent: false,
      error: errorMessage,
    };
  }
}
