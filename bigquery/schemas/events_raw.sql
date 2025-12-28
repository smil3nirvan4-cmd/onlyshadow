-- ============================================================================
-- S.S.I. SHADOW - BigQuery Schema: events_raw
-- ============================================================================
-- Main events table - receives all tracking events from the Worker
-- Partitioned by event_time for efficient querying and cost optimization
-- Clustered by ssi_id and event_name for common query patterns
-- ============================================================================

-- Create dataset if not exists (run manually first time)
-- CREATE SCHEMA IF NOT EXISTS `your-project.ssi_shadow`
-- OPTIONS (
--   location = 'US',
--   description = 'S.S.I. SHADOW - Server-Side Intelligence for Optimized Ads'
-- );

-- Drop and recreate table (careful in production!)
-- DROP TABLE IF EXISTS `your-project.ssi_shadow.events_raw`;

CREATE TABLE IF NOT EXISTS `ssi_shadow.events_raw` (
  -- ========================================================================
  -- Core Identifiers
  -- ========================================================================
  event_id STRING NOT NULL OPTIONS(description="Unique event identifier (UUID)"),
  ssi_id STRING NOT NULL OPTIONS(description="S.S.I. Shadow user identifier"),
  session_id STRING OPTIONS(description="Session identifier"),
  canonical_id STRING OPTIONS(description="Resolved identity from identity graph"),
  
  -- ========================================================================
  -- Event Information
  -- ========================================================================
  event_name STRING NOT NULL OPTIONS(description="Event type: PageView, Purchase, Lead, etc"),
  event_time TIMESTAMP NOT NULL OPTIONS(description="When the event occurred"),
  event_source STRING DEFAULT 'ghost' OPTIONS(description="Source: ghost, server, import, pixel"),
  
  -- ========================================================================
  -- Click IDs (Ad Platform Identifiers)
  -- ========================================================================
  fbclid STRING OPTIONS(description="Facebook Click ID from URL"),
  gclid STRING OPTIONS(description="Google Click ID from URL"),
  ttclid STRING OPTIONS(description="TikTok Click ID from URL"),
  fbc STRING OPTIONS(description="Facebook Click Cookie (_fbc)"),
  fbp STRING OPTIONS(description="Facebook Browser Cookie (_fbp)"),
  
  -- ========================================================================
  -- Page Information
  -- ========================================================================
  url STRING OPTIONS(description="Full page URL"),
  referrer STRING OPTIONS(description="HTTP referrer"),
  title STRING OPTIONS(description="Page title"),
  path STRING OPTIONS(description="URL path extracted from url"),
  query_params STRING OPTIONS(description="URL query string"),
  
  -- ========================================================================
  -- User Data (Hashed PII)
  -- ========================================================================
  email_hash STRING OPTIONS(description="SHA-256 hash of normalized email"),
  phone_hash STRING OPTIONS(description="SHA-256 hash of normalized phone (E.164)"),
  first_name_hash STRING OPTIONS(description="SHA-256 hash of normalized first name"),
  last_name_hash STRING OPTIONS(description="SHA-256 hash of normalized last name"),
  city_hash STRING OPTIONS(description="SHA-256 hash of normalized city"),
  state_hash STRING OPTIONS(description="SHA-256 hash of normalized state"),
  zip_hash STRING OPTIONS(description="SHA-256 hash of normalized zip code"),
  country_hash STRING OPTIONS(description="SHA-256 hash of normalized country"),
  external_id STRING OPTIONS(description="External user ID from client system"),
  
  -- ========================================================================
  -- Device & Browser Information
  -- ========================================================================
  user_agent STRING OPTIONS(description="Browser User-Agent string"),
  ip_hash STRING OPTIONS(description="SHA-256 hash of IP address"),
  country STRING OPTIONS(description="Country from IP geolocation"),
  city STRING OPTIONS(description="City from IP geolocation"),
  region STRING OPTIONS(description="Region/state from IP geolocation"),
  language STRING OPTIONS(description="Browser language preference"),
  timezone STRING OPTIONS(description="User timezone"),
  
  -- ========================================================================
  -- Screen & Viewport
  -- ========================================================================
  screen_width INT64 OPTIONS(description="Screen width in pixels"),
  screen_height INT64 OPTIONS(description="Screen height in pixels"),
  viewport_width INT64 OPTIONS(description="Viewport width in pixels"),
  viewport_height INT64 OPTIONS(description="Viewport height in pixels"),
  device_pixel_ratio FLOAT64 OPTIONS(description="Device pixel ratio"),
  color_depth INT64 OPTIONS(description="Screen color depth"),
  
  -- ========================================================================
  -- Device Fingerprint
  -- ========================================================================
  canvas_hash STRING OPTIONS(description="Canvas fingerprint hash"),
  webgl_vendor STRING OPTIONS(description="WebGL vendor string"),
  webgl_renderer STRING OPTIONS(description="WebGL renderer string"),
  plugins_hash STRING OPTIONS(description="Hash of installed plugins"),
  touch_support BOOL OPTIONS(description="Device has touch support"),
  hardware_concurrency INT64 OPTIONS(description="Number of CPU cores"),
  device_memory FLOAT64 OPTIONS(description="Device memory in GB"),
  
  -- ========================================================================
  -- Behavioral Data
  -- ========================================================================
  scroll_depth INT64 OPTIONS(description="Max scroll depth percentage (0-100)"),
  time_on_page INT64 OPTIONS(description="Time on page in milliseconds"),
  clicks INT64 OPTIONS(description="Number of clicks on page"),
  session_duration INT64 OPTIONS(description="Total session duration in ms"),
  session_pageviews INT64 OPTIONS(description="Number of pageviews in session"),
  
  -- ========================================================================
  -- E-commerce Data
  -- ========================================================================
  value FLOAT64 OPTIONS(description="Transaction/event value"),
  currency STRING OPTIONS(description="Currency code (ISO 4217)"),
  content_ids ARRAY<STRING> OPTIONS(description="Product/content IDs"),
  content_type STRING OPTIONS(description="Content type: product, category, etc"),
  content_name STRING OPTIONS(description="Product/content name"),
  content_category STRING OPTIONS(description="Product/content category"),
  num_items INT64 OPTIONS(description="Number of items"),
  order_id STRING OPTIONS(description="Order/transaction ID"),
  
  -- ========================================================================
  -- Trust Score (Bot Detection)
  -- ========================================================================
  trust_score FLOAT64 OPTIONS(description="Trust score 0.0 (bot) to 1.0 (human)"),
  trust_action STRING OPTIONS(description="Action taken: allow, challenge, block"),
  trust_reasons ARRAY<STRING> OPTIONS(description="Reasons for trust score"),
  trust_flags ARRAY<STRING> OPTIONS(description="Detected flags: bot_ua, datacenter_ip, etc"),
  
  -- ========================================================================
  -- ML Predictions
  -- ========================================================================
  predicted_ltv FLOAT64 OPTIONS(description="Predicted customer lifetime value"),
  predicted_intent STRING OPTIONS(description="Predicted purchase intent: high, medium, low"),
  predicted_segment STRING OPTIONS(description="Predicted customer segment"),
  anomaly_score FLOAT64 OPTIONS(description="Anomaly detection score"),
  
  -- ========================================================================
  -- CAPI Status (Platform Delivery)
  -- ========================================================================
  meta_sent BOOL DEFAULT FALSE OPTIONS(description="Event sent to Meta CAPI"),
  meta_response_code INT64 OPTIONS(description="Meta CAPI response status code"),
  meta_events_received INT64 OPTIONS(description="Events received by Meta"),
  meta_error STRING OPTIONS(description="Meta CAPI error message if any"),
  
  google_sent BOOL DEFAULT FALSE OPTIONS(description="Event sent to Google"),
  google_response_code INT64 OPTIONS(description="Google API response status code"),
  google_error STRING OPTIONS(description="Google API error message if any"),
  
  tiktok_sent BOOL DEFAULT FALSE OPTIONS(description="Event sent to TikTok"),
  tiktok_response_code INT64 OPTIONS(description="TikTok API response status code"),
  tiktok_error STRING OPTIONS(description="TikTok API error message if any"),
  
  -- ========================================================================
  -- Metadata
  -- ========================================================================
  processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() OPTIONS(description="When event was processed"),
  worker_version STRING OPTIONS(description="Worker version that processed the event"),
  
  -- ========================================================================
  -- Partitioning column (auto-generated)
  -- ========================================================================
  _PARTITIONTIME TIMESTAMP OPTIONS(description="Partition timestamp")
)
PARTITION BY DATE(event_time)
CLUSTER BY ssi_id, event_name, canonical_id
OPTIONS (
  description = 'Raw events from S.S.I. SHADOW tracking',
  labels = [('team', 'marketing'), ('system', 'ssi_shadow')],
  partition_expiration_days = 365,
  require_partition_filter = false
);

-- ============================================================================
-- Useful Indexes (BigQuery uses clustering, not traditional indexes)
-- The CLUSTER BY clause above handles this:
-- - ssi_id: For user-level queries
-- - event_name: For event-type filtering
-- - canonical_id: For identity-resolved queries
-- ============================================================================

-- ============================================================================
-- Sample Query: Get events for a specific user
-- ============================================================================
-- SELECT *
-- FROM `project.ssi_shadow.events_raw`
-- WHERE ssi_id = 'ssi_abc123'
--   AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
-- ORDER BY event_time DESC;

-- ============================================================================
-- Sample Query: Daily event counts by type
-- ============================================================================
-- SELECT
--   DATE(event_time) as date,
--   event_name,
--   COUNT(*) as count,
--   COUNT(DISTINCT ssi_id) as unique_users
-- FROM `project.ssi_shadow.events_raw`
-- WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
-- GROUP BY 1, 2
-- ORDER BY 1 DESC, 3 DESC;
