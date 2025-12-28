-- ============================================================================
-- S.S.I. SHADOW - BigQuery Schema: user_profiles
-- ============================================================================
-- Consolidated user profiles with RFM metrics, LTV predictions, and segments
-- Updated by scheduled procedures
-- ============================================================================

CREATE TABLE IF NOT EXISTS `ssi_shadow.user_profiles` (
  -- ========================================================================
  -- Core Identifier
  -- ========================================================================
  canonical_id STRING NOT NULL OPTIONS(description="Canonical user identifier from identity graph"),
  
  -- ========================================================================
  -- Known Identifiers (for matching)
  -- ========================================================================
  primary_ssi_id STRING OPTIONS(description="Primary SSI ID (most recent)"),
  primary_email_hash STRING OPTIONS(description="Primary email hash"),
  primary_phone_hash STRING OPTIONS(description="Primary phone hash"),
  external_ids ARRAY<STRING> OPTIONS(description="External IDs from client systems"),
  
  -- All linked identifiers
  all_ssi_ids ARRAY<STRING> OPTIONS(description="All linked SSI IDs"),
  all_email_hashes ARRAY<STRING> OPTIONS(description="All linked email hashes"),
  all_phone_hashes ARRAY<STRING> OPTIONS(description="All linked phone hashes"),
  
  -- ========================================================================
  -- RFM Metrics (Recency, Frequency, Monetary)
  -- ========================================================================
  -- Recency
  first_seen TIMESTAMP OPTIONS(description="First activity ever"),
  last_seen TIMESTAMP OPTIONS(description="Last activity"),
  days_since_first_seen INT64 OPTIONS(description="Days since first activity"),
  days_since_last_seen INT64 OPTIONS(description="Days since last activity"),
  
  -- Frequency
  total_sessions INT64 DEFAULT 0 OPTIONS(description="Total number of sessions"),
  total_pageviews INT64 DEFAULT 0 OPTIONS(description="Total pageviews"),
  total_events INT64 DEFAULT 0 OPTIONS(description="Total events"),
  total_purchases INT64 DEFAULT 0 OPTIONS(description="Total purchases"),
  total_leads INT64 DEFAULT 0 OPTIONS(description="Total lead submissions"),
  
  -- Monetary
  total_revenue FLOAT64 DEFAULT 0.0 OPTIONS(description="Total revenue"),
  avg_order_value FLOAT64 OPTIONS(description="Average order value"),
  max_order_value FLOAT64 OPTIONS(description="Maximum order value"),
  min_order_value FLOAT64 OPTIONS(description="Minimum order value"),
  
  -- ========================================================================
  -- RFM Scores (1-5 scale)
  -- ========================================================================
  rfm_recency_score INT64 OPTIONS(description="Recency score 1-5"),
  rfm_frequency_score INT64 OPTIONS(description="Frequency score 1-5"),
  rfm_monetary_score INT64 OPTIONS(description="Monetary score 1-5"),
  rfm_combined_score STRING OPTIONS(description="Combined RFM score e.g. '555'"),
  rfm_segment STRING OPTIONS(description="RFM segment: Champions, Loyal, At Risk, etc"),
  
  -- ========================================================================
  -- Engagement Metrics
  -- ========================================================================
  avg_session_duration INT64 OPTIONS(description="Average session duration in ms"),
  avg_pages_per_session FLOAT64 OPTIONS(description="Average pageviews per session"),
  avg_scroll_depth FLOAT64 OPTIONS(description="Average scroll depth percentage"),
  avg_time_on_page INT64 OPTIONS(description="Average time on page in ms"),
  
  -- ========================================================================
  -- Conversion Metrics
  -- ========================================================================
  conversion_rate FLOAT64 OPTIONS(description="Overall conversion rate"),
  cart_abandonment_rate FLOAT64 OPTIONS(description="Cart abandonment rate"),
  checkout_abandonment_rate FLOAT64 OPTIONS(description="Checkout abandonment rate"),
  days_to_first_purchase INT64 OPTIONS(description="Days from first visit to first purchase"),
  avg_days_between_purchases FLOAT64 OPTIONS(description="Average days between purchases"),
  
  -- ========================================================================
  -- Device & Channel Data
  -- ========================================================================
  devices ARRAY<STRUCT<
    device_type STRING,
    os STRING,
    browser STRING,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    session_count INT64
  >> OPTIONS(description="Devices used by this user"),
  
  primary_device_type STRING OPTIONS(description="Most used device type: mobile, desktop, tablet"),
  is_multi_device BOOL OPTIONS(description="User has multiple devices"),
  device_count INT64 OPTIONS(description="Number of unique devices"),
  
  -- Traffic sources
  traffic_sources ARRAY<STRUCT<
    source STRING,
    medium STRING,
    campaign STRING,
    first_seen TIMESTAMP,
    last_seen TIMESTAMP,
    session_count INT64,
    revenue FLOAT64
  >> OPTIONS(description="Traffic sources used"),
  
  primary_traffic_source STRING OPTIONS(description="Most common traffic source"),
  paid_traffic_ratio FLOAT64 OPTIONS(description="Ratio of paid vs organic traffic"),
  
  -- ========================================================================
  -- ML Predictions
  -- ========================================================================
  predicted_ltv FLOAT64 OPTIONS(description="Predicted lifetime value"),
  predicted_ltv_30d FLOAT64 OPTIONS(description="Predicted LTV next 30 days"),
  predicted_ltv_90d FLOAT64 OPTIONS(description="Predicted LTV next 90 days"),
  ltv_segment STRING OPTIONS(description="LTV segment: high, medium, low"),
  ltv_percentile INT64 OPTIONS(description="LTV percentile 1-100"),
  
  churn_probability FLOAT64 OPTIONS(description="Probability of churn 0.0-1.0"),
  churn_risk STRING OPTIONS(description="Churn risk: high, medium, low"),
  
  purchase_probability_7d FLOAT64 OPTIONS(description="Probability of purchase in 7 days"),
  purchase_probability_30d FLOAT64 OPTIONS(description="Probability of purchase in 30 days"),
  
  -- ========================================================================
  -- Segments
  -- ========================================================================
  customer_type STRING OPTIONS(description="new, returning, loyal, churned"),
  value_segment STRING OPTIONS(description="VIP, high_value, medium_value, low_value"),
  engagement_segment STRING OPTIONS(description="highly_engaged, engaged, passive, dormant"),
  lifecycle_stage STRING OPTIONS(description="awareness, consideration, purchase, retention, advocacy"),
  
  custom_segments ARRAY<STRING> OPTIONS(description="Custom segment tags"),
  
  -- ========================================================================
  -- Trust & Quality
  -- ========================================================================
  avg_trust_score FLOAT64 OPTIONS(description="Average trust score across sessions"),
  min_trust_score FLOAT64 OPTIONS(description="Minimum trust score observed"),
  bot_sessions INT64 OPTIONS(description="Number of sessions flagged as bot"),
  human_sessions INT64 OPTIONS(description="Number of sessions confirmed human"),
  
  -- ========================================================================
  -- Preferences (inferred)
  -- ========================================================================
  preferred_categories ARRAY<STRING> OPTIONS(description="Most viewed product categories"),
  preferred_brands ARRAY<STRING> OPTIONS(description="Most purchased brands"),
  price_sensitivity STRING OPTIONS(description="high, medium, low based on purchase patterns"),
  
  -- ========================================================================
  -- Metadata
  -- ========================================================================
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  profile_version INT64 DEFAULT 1 OPTIONS(description="Profile version for tracking changes"),
  last_computed TIMESTAMP OPTIONS(description="When profile was last computed")
)
CLUSTER BY canonical_id, rfm_segment, ltv_segment
OPTIONS (
  description = 'Consolidated user profiles with RFM and predictions'
);

-- ============================================================================
-- Sample Queries
-- ============================================================================

-- Get high-value users at risk of churning
-- SELECT *
-- FROM `project.ssi_shadow.user_profiles`
-- WHERE ltv_segment = 'high'
--   AND churn_risk IN ('high', 'medium')
-- ORDER BY predicted_ltv DESC
-- LIMIT 100;

-- RFM segment distribution
-- SELECT
--   rfm_segment,
--   COUNT(*) as user_count,
--   AVG(total_revenue) as avg_revenue,
--   AVG(total_purchases) as avg_purchases
-- FROM `project.ssi_shadow.user_profiles`
-- GROUP BY rfm_segment
-- ORDER BY avg_revenue DESC;

-- Multi-device users
-- SELECT
--   COUNT(*) as total_users,
--   SUM(CASE WHEN is_multi_device THEN 1 ELSE 0 END) as multi_device_users,
--   SAFE_DIVIDE(SUM(CASE WHEN is_multi_device THEN 1 ELSE 0 END), COUNT(*)) as multi_device_rate
-- FROM `project.ssi_shadow.user_profiles`;
