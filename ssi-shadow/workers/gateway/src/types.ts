// ============================================================================
// S.S.I. SHADOW - Type Definitions
// ============================================================================

// ----------------------------------------------------------------------------
// Environment Variables
// ----------------------------------------------------------------------------
export interface Env {
  // Meta CAPI
  META_PIXEL_ID: string;
  META_ACCESS_TOKEN: string;
  META_TEST_EVENT_CODE?: string;

  // Google GA4
  GA4_MEASUREMENT_ID?: string;
  GA4_API_SECRET?: string;

  // TikTok Events API
  TIKTOK_PIXEL_ID?: string;
  TIKTOK_ACCESS_TOKEN?: string;
  TIKTOK_TEST_EVENT_CODE?: string;

  // BigQuery
  GCP_PROJECT_ID?: string;
  GCP_SERVICE_ACCOUNT_KEY?: string;
  BIGQUERY_PROJECT_ID?: string;
  BIGQUERY_DATASET?: string;
  BIGQUERY_TABLE?: string;

  // KV Namespaces
  RATE_LIMIT?: KVNamespace;
  SESSION_STORE?: KVNamespace;

  // Queues (for BigQuery batch insert)
  EVENTS_QUEUE?: Queue;

  // Feature Flags
  ENABLE_META?: string;
  ENABLE_GOOGLE?: string;
  ENABLE_TIKTOK?: string;
  ENABLE_BIGQUERY?: string;
  TRUST_SCORE_THRESHOLD?: string;
}

// ----------------------------------------------------------------------------
// Incoming Event (from Ghost Script)
// ----------------------------------------------------------------------------
export interface IncomingEvent {
  // Required
  event_name: EventName;
  
  // Identifiers
  ssi_id?: string;
  session_id?: string;
  event_id?: string;
  
  // Click IDs
  fbclid?: string;
  gclid?: string;
  ttclid?: string;
  fbc?: string;
  fbp?: string;
  
  // Page Info
  url?: string;
  referrer?: string;
  title?: string;
  
  // User Data (PII - will be hashed)
  email?: string;
  phone?: string;
  first_name?: string;
  last_name?: string;
  city?: string;
  state?: string;
  zip_code?: string;
  country?: string;
  external_id?: string;
  
  // Device/Browser
  user_agent?: string;
  ip_address?: string;
  language?: string;
  timezone?: string;
  screen_width?: number;
  screen_height?: number;
  viewport_width?: number;
  viewport_height?: number;
  
  // Fingerprint
  canvas_hash?: string;
  webgl_vendor?: string;
  webgl_renderer?: string;
  plugins_hash?: string;
  touch_support?: boolean;
  
  // Behavioral
  scroll_depth?: number;
  time_on_page?: number;
  clicks?: number;
  
  // E-commerce
  value?: number;
  currency?: string;
  content_ids?: string[];
  content_type?: string;
  content_name?: string;
  content_category?: string;
  num_items?: number;
  order_id?: string;
  
  // Predictions (from ML)
  predicted_ltv?: number;
  predicted_intent?: string;
  
  // Timestamp
  timestamp?: number;
}

// ----------------------------------------------------------------------------
// Event Names
// ----------------------------------------------------------------------------
export type EventName =
  | 'PageView'
  | 'ViewContent'
  | 'Search'
  | 'AddToCart'
  | 'AddToWishlist'
  | 'InitiateCheckout'
  | 'AddPaymentInfo'
  | 'Purchase'
  | 'Lead'
  | 'CompleteRegistration'
  | 'Contact'
  | 'CustomizeProduct'
  | 'Donate'
  | 'FindLocation'
  | 'Schedule'
  | 'StartTrial'
  | 'SubmitApplication'
  | 'Subscribe';

// ----------------------------------------------------------------------------
// Meta CAPI Types
// ----------------------------------------------------------------------------
export interface MetaUserData {
  em?: string[];           // Hashed email
  ph?: string[];           // Hashed phone
  fn?: string[];           // Hashed first name
  ln?: string[];           // Hashed last name
  ct?: string[];           // Hashed city
  st?: string[];           // Hashed state
  zp?: string[];           // Hashed zip code
  country?: string[];      // Hashed country (2-letter ISO)
  external_id?: string[];  // Hashed external ID
  client_ip_address?: string;
  client_user_agent?: string;
  fbc?: string;            // Click ID cookie
  fbp?: string;            // Browser ID cookie
}

export interface MetaCustomData {
  value?: number;
  currency?: string;
  content_ids?: string[];
  content_type?: string;
  content_name?: string;
  content_category?: string;
  num_items?: number;
  order_id?: string;
  predicted_ltv?: number;
  // Custom properties
  [key: string]: unknown;
}

export interface MetaEvent {
  event_name: string;
  event_time: number;
  event_id: string;
  event_source_url?: string;
  action_source: 'website' | 'app' | 'phone_call' | 'chat' | 'email' | 'other' | 'system_generated';
  user_data: MetaUserData;
  custom_data?: MetaCustomData;
  opt_out?: boolean;
  data_processing_options?: string[];
  data_processing_options_country?: number;
  data_processing_options_state?: number;
}

export interface MetaCAPIPayload {
  data: MetaEvent[];
  access_token?: string;  // Can be in header instead
  test_event_code?: string;
}

export interface MetaCAPIResponse {
  events_received?: number;
  messages?: string[];
  fbtrace_id?: string;
  error?: {
    message: string;
    type: string;
    code: number;
    error_subcode?: number;
    fbtrace_id?: string;
  };
}

// ----------------------------------------------------------------------------
// Processed Event (internal)
// ----------------------------------------------------------------------------
export interface ProcessedEvent {
  // Core
  event_id: string;
  event_name: EventName;
  event_time: number;
  
  // Identifiers
  ssi_id: string;
  session_id?: string;
  
  // Click IDs
  fbclid?: string;
  gclid?: string;
  ttclid?: string;
  fbc?: string;
  fbp?: string;
  
  // Page
  url?: string;
  referrer?: string;
  
  // User Data (already hashed)
  email_hash?: string;
  phone_hash?: string;
  first_name_hash?: string;
  last_name_hash?: string;
  city_hash?: string;
  state_hash?: string;
  zip_hash?: string;
  country_hash?: string;
  external_id_hash?: string;
  
  // Device
  ip_address?: string;
  user_agent?: string;
  
  // E-commerce
  value?: number;
  currency?: string;
  content_ids?: string[];
  content_type?: string;
  order_id?: string;
  
  // Predictions
  predicted_ltv?: number;
  
  // Trust Score
  trust_score?: number;
  trust_reasons?: string[];
  trust_action?: 'allow' | 'challenge' | 'block';
  
  // Platform Status
  meta_sent?: boolean;
  meta_response_code?: number;
  google_sent?: boolean;
  google_response_code?: number;
  tiktok_sent?: boolean;
  tiktok_response_code?: number;
}

// ----------------------------------------------------------------------------
// API Response
// ----------------------------------------------------------------------------
export interface CollectResponse {
  success: boolean;
  event_id: string;
  ssi_id: string;
  trust_score?: number;
  trust_action?: 'allow' | 'challenge' | 'block';
  platforms: {
    meta?: PlatformResponse;
    google?: PlatformResponse;
    tiktok?: PlatformResponse;
    bigquery?: PlatformResponse;
  };
  processing_time_ms: number;
  error?: string;
}

export interface PlatformResponse {
  sent: boolean;
  status?: number;
  events_received?: number;
  error?: string;
}

// ----------------------------------------------------------------------------
// Retry Configuration
// ----------------------------------------------------------------------------
export interface RetryConfig {
  maxRetries: number;
  baseDelayMs: number;
  maxDelayMs: number;
  retryableStatuses: number[];
}

// ----------------------------------------------------------------------------
// Validation Result
// ----------------------------------------------------------------------------
export interface ValidationResult {
  valid: boolean;
  errors: string[];
  sanitizedEvent?: IncomingEvent;
}
