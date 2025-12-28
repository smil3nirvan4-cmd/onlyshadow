// ============================================================================
// S.S.I. SHADOW - Meta Conversions API Module
// ============================================================================
// Documentation: https://developers.facebook.com/docs/marketing-api/conversions-api

import {
  Env,
  IncomingEvent,
  ProcessedEvent,
  MetaEvent,
  MetaUserData,
  MetaCustomData,
  MetaCAPIPayload,
  MetaCAPIResponse,
  PlatformResponse,
} from './types';

import { sha256, hashToArray, generateEventId, generateSSIId } from './utils/hash';
import {
  normalizeEmail,
  normalizePhone,
  normalizeName,
  normalizeCity,
  normalizeState,
  normalizeZip,
  normalizeCountry,
  normalizeExternalId,
  parseFBC,
  generateFBP,
  extractFBCLID,
} from './utils/normalize';
import { withRetry, META_RETRY_CONFIG } from './utils/retry';

// Meta Graph API version
const META_API_VERSION = 'v21.0';
const META_API_BASE_URL = 'https://graph.facebook.com';

/**
 * Build the Meta CAPI endpoint URL
 */
function buildMetaEndpoint(pixelId: string): string {
  return `${META_API_BASE_URL}/${META_API_VERSION}/${pixelId}/events`;
}

/**
 * Process and hash user data for Meta CAPI
 */
async function buildUserData(
  event: IncomingEvent,
  request: Request
): Promise<MetaUserData> {
  const userData: MetaUserData = {};

  // Hash PII fields
  const [
    emailHash,
    phoneHash,
    firstNameHash,
    lastNameHash,
    cityHash,
    stateHash,
    zipHash,
    countryHash,
    externalIdHash,
  ] = await Promise.all([
    hashToArray(normalizeEmail(event.email)),
    hashToArray(normalizePhone(event.phone)),
    hashToArray(normalizeName(event.first_name)),
    hashToArray(normalizeName(event.last_name)),
    hashToArray(normalizeCity(event.city)),
    hashToArray(normalizeState(event.state)),
    hashToArray(normalizeZip(event.zip_code)),
    hashToArray(normalizeCountry(event.country)),
    hashToArray(normalizeExternalId(event.external_id || event.ssi_id)),
  ]);

  // Assign hashed values
  if (emailHash) userData.em = emailHash;
  if (phoneHash) userData.ph = phoneHash;
  if (firstNameHash) userData.fn = firstNameHash;
  if (lastNameHash) userData.ln = lastNameHash;
  if (cityHash) userData.ct = cityHash;
  if (stateHash) userData.st = stateHash;
  if (zipHash) userData.zp = zipHash;
  if (countryHash) userData.country = countryHash;
  if (externalIdHash) userData.external_id = externalIdHash;

  // Client IP - get from request headers (Cloudflare provides this)
  const clientIp =
    event.ip_address ||
    request.headers.get('CF-Connecting-IP') ||
    request.headers.get('X-Forwarded-For')?.split(',')[0]?.trim() ||
    request.headers.get('X-Real-IP');

  if (clientIp) {
    userData.client_ip_address = clientIp;
  }

  // User Agent - get from request headers
  const userAgent =
    event.user_agent || request.headers.get('User-Agent');

  if (userAgent) {
    userData.client_user_agent = userAgent;
  }

  // FBC (Click ID Cookie) - build from fbclid if provided
  if (event.fbc) {
    userData.fbc = event.fbc;
  } else if (event.fbclid) {
    userData.fbc = parseFBC(event.fbclid);
  } else if (event.url) {
    const extractedFbclid = extractFBCLID(event.url);
    if (extractedFbclid) {
      userData.fbc = parseFBC(extractedFbclid);
    }
  }

  // FBP (Browser ID Cookie)
  if (event.fbp) {
    userData.fbp = event.fbp;
  } else {
    // Generate FBP if not provided (for new users)
    userData.fbp = generateFBP();
  }

  return userData;
}

/**
 * Build custom data for e-commerce events
 */
function buildCustomData(event: IncomingEvent): MetaCustomData | undefined {
  const customData: MetaCustomData = {};
  let hasData = false;

  if (event.value !== undefined && event.value !== null) {
    customData.value = event.value;
    hasData = true;
  }

  if (event.currency) {
    customData.currency = event.currency.toUpperCase();
    hasData = true;
  }

  if (event.content_ids && event.content_ids.length > 0) {
    customData.content_ids = event.content_ids;
    hasData = true;
  }

  if (event.content_type) {
    customData.content_type = event.content_type;
    hasData = true;
  }

  if (event.content_name) {
    customData.content_name = event.content_name;
    hasData = true;
  }

  if (event.content_category) {
    customData.content_category = event.content_category;
    hasData = true;
  }

  if (event.num_items !== undefined) {
    customData.num_items = event.num_items;
    hasData = true;
  }

  if (event.order_id) {
    customData.order_id = event.order_id;
    hasData = true;
  }

  // Predicted LTV for value-based bidding
  if (event.predicted_ltv !== undefined) {
    customData.predicted_ltv = event.predicted_ltv;
    hasData = true;
  }

  return hasData ? customData : undefined;
}

/**
 * Build Meta event from incoming event
 */
async function buildMetaEvent(
  event: IncomingEvent,
  request: Request
): Promise<MetaEvent> {
  const eventId = event.event_id || generateEventId();
  const eventTime = event.timestamp
    ? Math.floor(event.timestamp / 1000) // Convert ms to seconds
    : Math.floor(Date.now() / 1000);

  const userData = await buildUserData(event, request);
  const customData = buildCustomData(event);

  const metaEvent: MetaEvent = {
    event_name: event.event_name,
    event_time: eventTime,
    event_id: eventId,
    action_source: 'website',
    user_data: userData,
  };

  if (event.url) {
    metaEvent.event_source_url = event.url;
  }

  if (customData) {
    metaEvent.custom_data = customData;
  }

  // Data Processing Options (for CCPA compliance)
  // Uncomment if needed for US users
  // metaEvent.data_processing_options = [];
  // metaEvent.data_processing_options_country = 0;
  // metaEvent.data_processing_options_state = 0;

  return metaEvent;
}

/**
 * Send event to Meta Conversions API
 */
export async function sendToMeta(
  event: IncomingEvent,
  request: Request,
  env: Env
): Promise<PlatformResponse> {
  // Check if Meta is enabled
  if (env.ENABLE_META === 'false') {
    return {
      sent: false,
      error: 'Meta CAPI disabled',
    };
  }

  // Validate required environment variables
  if (!env.META_PIXEL_ID || !env.META_ACCESS_TOKEN) {
    console.error('[Meta CAPI] Missing META_PIXEL_ID or META_ACCESS_TOKEN');
    return {
      sent: false,
      error: 'Missing Meta configuration',
    };
  }

  try {
    // Build Meta event
    const metaEvent = await buildMetaEvent(event, request);

    // Build payload
    const payload: MetaCAPIPayload = {
      data: [metaEvent],
      access_token: env.META_ACCESS_TOKEN,
    };

    // Add test event code if in test mode
    if (env.META_TEST_EVENT_CODE) {
      payload.test_event_code = env.META_TEST_EVENT_CODE;
    }

    const endpoint = buildMetaEndpoint(env.META_PIXEL_ID);

    console.log(`[Meta CAPI] Sending ${event.event_name} to ${endpoint}`);
    console.log(`[Meta CAPI] Event ID: ${metaEvent.event_id}`);

    // Send with retry logic
    const result = await withRetry<MetaCAPIResponse>(
      () =>
        fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        }),
      META_RETRY_CONFIG
    );

    if (result.success && result.data) {
      console.log(
        `[Meta CAPI] Success: ${result.data.events_received} events received`
      );
      return {
        sent: true,
        status: result.lastStatus,
        events_received: result.data.events_received,
      };
    } else {
      console.error(`[Meta CAPI] Failed after ${result.attempts} attempts: ${result.error}`);
      return {
        sent: false,
        status: result.lastStatus,
        error: result.error,
      };
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`[Meta CAPI] Exception: ${errorMessage}`);
    return {
      sent: false,
      error: errorMessage,
    };
  }
}

/**
 * Send multiple events to Meta CAPI in batch
 * Meta supports up to 1000 events per request
 */
export async function sendBatchToMeta(
  events: IncomingEvent[],
  request: Request,
  env: Env
): Promise<PlatformResponse> {
  if (events.length === 0) {
    return {
      sent: false,
      error: 'No events to send',
    };
  }

  // Validate required environment variables
  if (!env.META_PIXEL_ID || !env.META_ACCESS_TOKEN) {
    return {
      sent: false,
      error: 'Missing Meta configuration',
    };
  }

  try {
    // Build all Meta events
    const metaEvents = await Promise.all(
      events.map((event) => buildMetaEvent(event, request))
    );

    // Build payload
    const payload: MetaCAPIPayload = {
      data: metaEvents,
      access_token: env.META_ACCESS_TOKEN,
    };

    if (env.META_TEST_EVENT_CODE) {
      payload.test_event_code = env.META_TEST_EVENT_CODE;
    }

    const endpoint = buildMetaEndpoint(env.META_PIXEL_ID);

    console.log(`[Meta CAPI] Sending batch of ${events.length} events`);

    const result = await withRetry<MetaCAPIResponse>(
      () =>
        fetch(endpoint, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
          },
          body: JSON.stringify(payload),
        }),
      META_RETRY_CONFIG
    );

    if (result.success && result.data) {
      console.log(
        `[Meta CAPI] Batch success: ${result.data.events_received} events received`
      );
      return {
        sent: true,
        status: result.lastStatus,
        events_received: result.data.events_received,
      };
    } else {
      console.error(`[Meta CAPI] Batch failed: ${result.error}`);
      return {
        sent: false,
        status: result.lastStatus,
        error: result.error,
      };
    }
  } catch (error) {
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`[Meta CAPI] Batch exception: ${errorMessage}`);
    return {
      sent: false,
      error: errorMessage,
    };
  }
}

/**
 * Validate incoming event for Meta CAPI requirements
 */
export function validateMetaEvent(event: IncomingEvent): string[] {
  const errors: string[] = [];

  // Required: event_name
  if (!event.event_name) {
    errors.push('event_name is required');
  }

  // Validate event_name is a known type
  const validEventNames = [
    'PageView',
    'ViewContent',
    'Search',
    'AddToCart',
    'AddToWishlist',
    'InitiateCheckout',
    'AddPaymentInfo',
    'Purchase',
    'Lead',
    'CompleteRegistration',
    'Contact',
    'CustomizeProduct',
    'Donate',
    'FindLocation',
    'Schedule',
    'StartTrial',
    'SubmitApplication',
    'Subscribe',
  ];

  if (event.event_name && !validEventNames.includes(event.event_name)) {
    errors.push(`Invalid event_name: ${event.event_name}`);
  }

  // For Purchase events, value and currency are strongly recommended
  if (event.event_name === 'Purchase') {
    if (event.value === undefined || event.value === null) {
      // This is a warning, not an error
      console.warn('[Meta CAPI] Purchase event without value');
    }
    if (!event.currency) {
      console.warn('[Meta CAPI] Purchase event without currency');
    }
  }

  // At least one user identifier is recommended for Event Match Quality
  const hasUserIdentifier =
    event.email ||
    event.phone ||
    event.external_id ||
    event.ssi_id ||
    event.fbc ||
    event.fbp ||
    event.fbclid;

  if (!hasUserIdentifier) {
    // This is a warning, not an error
    console.warn('[Meta CAPI] No user identifiers provided. EMQ will be low.');
  }

  return errors;
}

/**
 * Get Event Match Quality score estimate
 * Returns 1-10 based on available data
 */
export function estimateEMQ(event: IncomingEvent): number {
  let score = 1; // Base score

  // Email (+3)
  if (event.email) score += 3;

  // Phone (+2)
  if (event.phone) score += 2;

  // Click ID (+2)
  if (event.fbc || event.fbclid) score += 2;

  // Browser ID (+1)
  if (event.fbp) score += 1;

  // External ID (+1)
  if (event.external_id || event.ssi_id) score += 1;

  // IP and User Agent (implicit, usually present) (+0)

  // Name, City, etc. (+0.5 each, max +1)
  let extraScore = 0;
  if (event.first_name) extraScore += 0.25;
  if (event.last_name) extraScore += 0.25;
  if (event.city) extraScore += 0.25;
  if (event.state) extraScore += 0.25;
  score += Math.min(extraScore, 1);

  return Math.min(score, 10);
}
