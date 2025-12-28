// ============================================================================
// S.S.I. SHADOW - Microsoft/Bing Ads Integration
// ============================================================================
// Universal Event Tracking (UET) API for server-side conversions

import { Env, IncomingEvent, PlatformResult } from './types';
import { hashEmail, hashPhone } from './utils/hash';
import { normalizePhone } from './utils/normalize';
import { withRetry } from './utils/retry';

// ----------------------------------------------------------------------------
// Types
// ----------------------------------------------------------------------------

interface UETEvent {
  event_category: string;
  event_label?: string;
  event_value?: number;
  revenue?: number;
  revenue_currency?: string;
  conversion_name?: string;
  msclkid?: string;
  user_data?: {
    em?: string; // hashed email
    ph?: string; // hashed phone
    fn?: string; // hashed first name
    ln?: string; // hashed last name
    ct?: string; // hashed city
    st?: string; // hashed state
    zp?: string; // hashed zip
    country?: string;
    external_id?: string;
  };
  custom_parameters?: Record<string, string>;
}

interface UETPayload {
  tag_id: string;
  events: UETEvent[];
  client_info: {
    ip_address?: string;
    user_agent?: string;
    page_url?: string;
    referrer?: string;
  };
}

interface UETResponse {
  status: string;
  events_received?: number;
  errors?: Array<{
    code: string;
    message: string;
  }>;
}

// ----------------------------------------------------------------------------
// Event Mapping
// ----------------------------------------------------------------------------

const EVENT_MAP: Record<string, string> = {
  'PageView': 'page_view',
  'ViewContent': 'view_item',
  'AddToCart': 'add_to_cart',
  'InitiateCheckout': 'begin_checkout',
  'AddPaymentInfo': 'add_payment_info',
  'Purchase': 'purchase',
  'Lead': 'generate_lead',
  'CompleteRegistration': 'sign_up',
  'Search': 'search',
  'Subscribe': 'subscribe',
  'Contact': 'contact',
  'Schedule': 'schedule',
};

// ----------------------------------------------------------------------------
// Build Payload
// ----------------------------------------------------------------------------

function buildPayload(
  event: IncomingEvent,
  request: Request,
  env: Env
): UETPayload {
  // Map SSI event to Microsoft event
  const eventCategory = EVENT_MAP[event.event_name] || event.event_name.toLowerCase();

  // Build user data with hashed PII
  const userData: UETEvent['user_data'] = {};

  if (event.email) {
    userData.em = hashEmail(event.email);
  }

  if (event.phone) {
    userData.ph = hashPhone(normalizePhone(event.phone));
  }

  if (event.first_name) {
    userData.fn = hashEmail(event.first_name.toLowerCase().trim());
  }

  if (event.last_name) {
    userData.ln = hashEmail(event.last_name.toLowerCase().trim());
  }

  if (event.city) {
    userData.ct = hashEmail(event.city.toLowerCase().trim());
  }

  if (event.state) {
    userData.st = hashEmail(event.state.toLowerCase().trim());
  }

  if (event.zip_code) {
    userData.zp = hashEmail(event.zip_code.replace(/\s/g, ''));
  }

  if (event.country) {
    userData.country = event.country;
  }

  if (event.external_id) {
    userData.external_id = event.external_id;
  }

  // Build the event
  const uetEvent: UETEvent = {
    event_category: eventCategory,
    event_label: event.content_name || undefined,
    event_value: event.value || undefined,
    revenue: event.value || undefined,
    revenue_currency: event.currency || 'BRL',
  };

  // Add msclkid if present
  if (event.msclkid) {
    uetEvent.msclkid = event.msclkid;
  }

  // Add conversion name for purchase/lead
  if (event.event_name === 'Purchase') {
    uetEvent.conversion_name = 'purchase';
  } else if (event.event_name === 'Lead') {
    uetEvent.conversion_name = 'lead';
  }

  // Add user data if any
  if (Object.keys(userData).length > 0) {
    uetEvent.user_data = userData;
  }

  // Add custom parameters
  if (event.content_ids || event.order_id) {
    uetEvent.custom_parameters = {};
    if (event.content_ids) {
      uetEvent.custom_parameters.content_ids = event.content_ids.join(',');
    }
    if (event.order_id) {
      uetEvent.custom_parameters.order_id = event.order_id;
    }
  }

  // Get client info from request
  const clientIp = request.headers.get('CF-Connecting-IP') || 
                   request.headers.get('X-Forwarded-For')?.split(',')[0] || 
                   '';
  const userAgent = request.headers.get('User-Agent') || '';

  return {
    tag_id: env.BING_TAG_ID || '',
    events: [uetEvent],
    client_info: {
      ip_address: clientIp,
      user_agent: userAgent,
      page_url: event.url,
      referrer: event.referrer,
    },
  };
}

// ----------------------------------------------------------------------------
// Send to Microsoft/Bing
// ----------------------------------------------------------------------------

async function sendRequest(
  payload: UETPayload,
  env: Env
): Promise<UETResponse> {
  // Microsoft UET API endpoint
  const endpoint = 'https://bat.bing.com/api/conversions/events';

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.BING_ACCESS_TOKEN}`,
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`Microsoft UET API error: ${response.status} - ${errorText}`);
  }

  return await response.json() as UETResponse;
}

// ----------------------------------------------------------------------------
// Main Export
// ----------------------------------------------------------------------------

export async function sendToMicrosoft(
  event: IncomingEvent,
  request: Request,
  env: Env
): Promise<PlatformResult> {
  // Check if Microsoft is enabled
  if (env.ENABLE_MICROSOFT !== 'true') {
    return { sent: false, skipped: true, reason: 'Microsoft disabled' };
  }

  // Check if credentials are configured
  if (!env.BING_TAG_ID || !env.BING_ACCESS_TOKEN) {
    return { sent: false, skipped: true, reason: 'Microsoft credentials not configured' };
  }

  try {
    const payload = buildPayload(event, request, env);

    console.log(`[Microsoft] Sending ${event.event_name} event`);

    const response = await withRetry(
      () => sendRequest(payload, env),
      3,
      1000
    );

    if (response.status === 'success' || response.events_received) {
      console.log(`[Microsoft] Success: ${response.events_received || 1} events received`);
      return {
        sent: true,
        status: 200,
        events_received: response.events_received || 1,
      };
    }

    // Handle errors in response
    if (response.errors && response.errors.length > 0) {
      const errorMessages = response.errors.map(e => e.message).join(', ');
      console.error(`[Microsoft] API errors: ${errorMessages}`);
      return {
        sent: false,
        error: errorMessages,
      };
    }

    return { sent: true, status: 200 };

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`[Microsoft] Error: ${errorMessage}`);
    return {
      sent: false,
      error: errorMessage,
    };
  }
}

// ----------------------------------------------------------------------------
// EMQ Estimation
// ----------------------------------------------------------------------------

export function estimateMicrosoftEMQ(event: IncomingEvent): number {
  let score = 0;

  if (event.email) score += 3;
  if (event.phone) score += 2;
  if (event.msclkid) score += 2;
  if (event.first_name || event.last_name) score += 1;
  if (event.city || event.state || event.zip_code) score += 0.5;
  if (event.external_id) score += 1;
  if (event.ip_address) score += 0.5;
  if (event.user_agent) score += 0.5;

  return Math.min(score, 10);
}
