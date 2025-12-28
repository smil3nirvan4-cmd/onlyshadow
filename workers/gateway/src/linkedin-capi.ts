// ============================================================================
// S.S.I. SHADOW - LinkedIn Conversions API
// ============================================================================
// Server-side event tracking for LinkedIn Ads

import { Env, IncomingEvent, PlatformResult } from './types';
import { hashEmail } from './utils/hash';
import { withRetry } from './utils/retry';

// ----------------------------------------------------------------------------
// Types
// ----------------------------------------------------------------------------

interface LinkedInUserInfo {
  sha256_email?: string;
  linkedin_first_party_ads_tracking_uuid?: string;
  acct_id?: string;
}

interface LinkedInConversion {
  conversion: string;
  conversionHappenedAt: number;
  conversionValue?: {
    currencyCode: string;
    amount: string;
  };
  eventId?: string;
  user: {
    userIds: Array<{
      idType: string;
      idValue: string;
    }>;
    userInfo?: LinkedInUserInfo;
  };
}

interface LinkedInPayload {
  elements: LinkedInConversion[];
}

// ----------------------------------------------------------------------------
// Event Mapping
// ----------------------------------------------------------------------------

const EVENT_MAP: Record<string, string> = {
  'PageView': 'PAGE_VISIT',
  'ViewContent': 'VIEW_CONTENT',
  'AddToCart': 'ADD_TO_CART',
  'InitiateCheckout': 'START_CHECKOUT',
  'Purchase': 'PURCHASE',
  'Lead': 'LEAD',
  'CompleteRegistration': 'SIGN_UP',
  'Subscribe': 'SUBSCRIBE',
  'Contact': 'CONTACT',
  'Schedule': 'BOOK_APPOINTMENT',
  'StartTrial': 'START_TRIAL',
  'SubmitApplication': 'SUBMIT_APPLICATION',
};

// ----------------------------------------------------------------------------
// Build Payload
// ----------------------------------------------------------------------------

function buildPayload(
  event: IncomingEvent,
  request: Request,
  env: Env
): LinkedInPayload {
  const conversionName = EVENT_MAP[event.event_name] || 'OTHER';

  // Build user IDs
  const userIds: Array<{ idType: string; idValue: string }> = [];

  if (event.email) {
    userIds.push({
      idType: 'SHA256_EMAIL',
      idValue: hashEmail(event.email),
    });
  }

  if (event.li_fat_id) {
    userIds.push({
      idType: 'LINKEDIN_FIRST_PARTY_ADS_TRACKING_UUID',
      idValue: event.li_fat_id,
    });
  }

  if (event.external_id) {
    userIds.push({
      idType: 'ACCT_ID',
      idValue: event.external_id,
    });
  }

  const conversion: LinkedInConversion = {
    conversion: `urn:lla:llaPartnerConversion:${env.LINKEDIN_CONVERSION_ID}`,
    conversionHappenedAt: event.timestamp || Date.now(),
    user: {
      userIds,
    },
  };

  // Add conversion value
  if (event.value) {
    conversion.conversionValue = {
      currencyCode: event.currency || 'BRL',
      amount: event.value.toString(),
    };
  }

  // Add event ID for deduplication
  if (event.event_id) {
    conversion.eventId = event.event_id;
  }

  return {
    elements: [conversion],
  };
}

// ----------------------------------------------------------------------------
// Send to LinkedIn
// ----------------------------------------------------------------------------

async function sendRequest(
  payload: LinkedInPayload,
  env: Env
): Promise<{ success: boolean }> {
  const endpoint = 'https://api.linkedin.com/rest/conversionEvents';

  const response = await fetch(endpoint, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${env.LINKEDIN_ACCESS_TOKEN}`,
      'LinkedIn-Version': '202401',
      'X-Restli-Protocol-Version': '2.0.0',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errorText = await response.text();
    throw new Error(`LinkedIn API error: ${response.status} - ${errorText}`);
  }

  return { success: true };
}

// ----------------------------------------------------------------------------
// Main Export
// ----------------------------------------------------------------------------

export async function sendToLinkedIn(
  event: IncomingEvent,
  request: Request,
  env: Env
): Promise<PlatformResult> {
  if (env.ENABLE_LINKEDIN !== 'true') {
    return { sent: false, skipped: true, reason: 'LinkedIn disabled' };
  }

  if (!env.LINKEDIN_CONVERSION_ID || !env.LINKEDIN_ACCESS_TOKEN) {
    return { sent: false, skipped: true, reason: 'LinkedIn credentials not configured' };
  }

  try {
    const payload = buildPayload(event, request, env);

    console.log(`[LinkedIn] Sending ${event.event_name} event`);

    await withRetry(
      () => sendRequest(payload, env),
      3,
      1000
    );

    console.log(`[LinkedIn] Success`);

    return {
      sent: true,
      status: 200,
      events_received: 1,
    };

  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`[LinkedIn] Error: ${errorMessage}`);
    return {
      sent: false,
      error: errorMessage,
    };
  }
}
