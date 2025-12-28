-- ============================================================================
-- S.S.I. SHADOW - FEATURE STORE (Incremental Updates)
-- ============================================================================
-- 
-- Purpose: Create and maintain a Feature Store for ML models with
--          incremental updates to minimize BigQuery processing costs.
--
-- Architecture:
--   1. user_features_daily   - Daily aggregations (partitioned by date)
--   2. user_features_lifetime - Lifetime aggregations (incrementally updated)
--   3. user_features_snapshot - Point-in-time feature snapshots for ML training
--
-- Cost Optimization:
--   - Only processes previous day's data (not full history)
--   - Uses MERGE for efficient upserts
--   - Partitioned tables to minimize scanned bytes
--   - Clustered by canonical_id for efficient lookups
--
-- Scheduling: Run daily at 2:00 AM UTC via Cloud Scheduler
--
-- Author: SSI Shadow Data Engineering Team
-- Version: 1.0.0
-- ============================================================================


-- ============================================================================
-- SECTION 1: SCHEMA DEFINITIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Table: user_features_daily
-- Daily feature aggregations, partitioned by date
-- Each row represents one user's activity for one day
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `ssi_shadow.user_features_daily` (
  -- Identity
  canonical_id STRING NOT NULL OPTIONS(description="Resolved user identity"),
  feature_date DATE NOT NULL OPTIONS(description="Date of the features"),
  
  -- Daily Engagement Metrics
  daily_visits INT64 DEFAULT 0 OPTIONS(description="Number of sessions"),
  daily_pageviews INT64 DEFAULT 0 OPTIONS(description="Number of page views"),
  daily_unique_pages INT64 DEFAULT 0 OPTIONS(description="Unique pages visited"),
  daily_time_on_site INT64 DEFAULT 0 OPTIONS(description="Total time on site (seconds)"),
  daily_avg_time_per_page FLOAT64 DEFAULT 0 OPTIONS(description="Avg time per page (seconds)"),
  daily_avg_scroll_depth FLOAT64 DEFAULT 0 OPTIONS(description="Avg scroll depth (0-100)"),
  daily_clicks INT64 DEFAULT 0 OPTIONS(description="Total clicks"),
  
  -- Daily Conversion Metrics
  daily_spend FLOAT64 DEFAULT 0 OPTIONS(description="Total spend for the day"),
  daily_orders INT64 DEFAULT 0 OPTIONS(description="Number of orders"),
  daily_items INT64 DEFAULT 0 OPTIONS(description="Total items purchased"),
  daily_avg_order_value FLOAT64 DEFAULT 0 OPTIONS(description="Avg order value"),
  daily_leads INT64 DEFAULT 0 OPTIONS(description="Number of leads generated"),
  daily_add_to_carts INT64 DEFAULT 0 OPTIONS(description="Add to cart events"),
  daily_checkouts_started INT64 DEFAULT 0 OPTIONS(description="Checkout initiations"),
  
  -- Daily Content Engagement
  daily_product_views INT64 DEFAULT 0 OPTIONS(description="Product page views"),
  daily_category_views INT64 DEFAULT 0 OPTIONS(description="Category page views"),
  daily_search_count INT64 DEFAULT 0 OPTIONS(description="Search queries"),
  most_viewed_category STRING OPTIONS(description="Most viewed category"),
  most_viewed_product STRING OPTIONS(description="Most viewed product"),
  
  -- Daily Device/Channel Info
  primary_device STRING OPTIONS(description="Most used device type"),
  primary_channel STRING OPTIONS(description="Primary traffic source"),
  is_mobile BOOL DEFAULT FALSE OPTIONS(description="Majority mobile visits"),
  
  -- Daily Trust/Quality
  avg_trust_score FLOAT64 OPTIONS(description="Average trust score"),
  low_trust_events INT64 DEFAULT 0 OPTIONS(description="Events with trust < 0.5"),
  
  -- Metadata
  ssi_ids ARRAY<STRING> OPTIONS(description="All SSI IDs for this user"),
  event_count INT64 DEFAULT 0 OPTIONS(description="Total events processed"),
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY feature_date
CLUSTER BY canonical_id
OPTIONS (
  description = 'Daily user feature aggregations for ML',
  labels = [('team', 'data_science'), ('purpose', 'feature_store')],
  partition_expiration_days = 730,  -- 2 years retention
  require_partition_filter = true
);


-- ----------------------------------------------------------------------------
-- Table: user_features_lifetime
-- Lifetime aggregations, incrementally updated daily via MERGE
-- Single row per user with all-time statistics
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS `ssi_shadow.user_features_lifetime` (
  -- Identity
  canonical_id STRING NOT NULL OPTIONS(description="Resolved user identity"),
  
  -- ========================================================================
  -- ENGAGEMENT FEATURES (Lifetime)
  -- ========================================================================
  total_visits INT64 DEFAULT 0 OPTIONS(description="All-time session count"),
  total_pageviews INT64 DEFAULT 0 OPTIONS(description="All-time pageview count"),
  total_time_on_site INT64 DEFAULT 0 OPTIONS(description="All-time time on site (seconds)"),
  total_clicks INT64 DEFAULT 0 OPTIONS(description="All-time clicks"),
  avg_time_per_visit FLOAT64 DEFAULT 0 OPTIONS(description="Avg session duration"),
  avg_pages_per_visit FLOAT64 DEFAULT 0 OPTIONS(description="Avg pages per session"),
  avg_scroll_depth FLOAT64 DEFAULT 0 OPTIONS(description="Avg scroll depth"),
  
  -- ========================================================================
  -- MONETARY FEATURES (Lifetime)
  -- ========================================================================
  total_spend FLOAT64 DEFAULT 0 OPTIONS(description="All-time total spend"),
  total_orders INT64 DEFAULT 0 OPTIONS(description="All-time order count"),
  total_items INT64 DEFAULT 0 OPTIONS(description="All-time items purchased"),
  avg_order_value FLOAT64 DEFAULT 0 OPTIONS(description="Average order value"),
  max_order_value FLOAT64 DEFAULT 0 OPTIONS(description="Largest order value"),
  min_order_value FLOAT64 DEFAULT 0 OPTIONS(description="Smallest order value"),
  stddev_order_value FLOAT64 DEFAULT 0 OPTIONS(description="Order value std deviation"),
  
  -- ========================================================================
  -- RFM FEATURES (Recency, Frequency, Monetary)
  -- ========================================================================
  -- Recency
  first_seen_date DATE OPTIONS(description="First interaction date"),
  last_seen_date DATE OPTIONS(description="Most recent interaction date"),
  first_purchase_date DATE OPTIONS(description="First purchase date"),
  last_purchase_date DATE OPTIONS(description="Most recent purchase date"),
  days_since_first_seen INT64 OPTIONS(description="Days since first seen"),
  days_since_last_seen INT64 OPTIONS(description="Days since last seen"),
  days_since_first_purchase INT64 OPTIONS(description="Days since first purchase"),
  days_since_last_purchase INT64 OPTIONS(description="Days since last purchase"),
  
  -- Frequency
  purchase_frequency FLOAT64 DEFAULT 0 OPTIONS(description="Purchases per active day"),
  visit_frequency FLOAT64 DEFAULT 0 OPTIONS(description="Visits per week (avg)"),
  days_between_purchases FLOAT64 OPTIONS(description="Avg days between purchases"),
  days_between_visits FLOAT64 OPTIONS(description="Avg days between visits"),
  active_days INT64 DEFAULT 0 OPTIONS(description="Days with any activity"),
  purchase_days INT64 DEFAULT 0 OPTIONS(description="Days with purchases"),
  
  -- Monetary
  revenue_per_visit FLOAT64 DEFAULT 0 OPTIONS(description="Revenue per visit"),
  revenue_per_day FLOAT64 DEFAULT 0 OPTIONS(description="Revenue per active day"),
  
  -- ========================================================================
  -- VELOCITY & ACCELERATION FEATURES (Derivatives)
  -- ========================================================================
  -- 7-day rolling metrics
  spend_7d FLOAT64 DEFAULT 0 OPTIONS(description="Spend in last 7 days"),
  orders_7d INT64 DEFAULT 0 OPTIONS(description="Orders in last 7 days"),
  visits_7d INT64 DEFAULT 0 OPTIONS(description="Visits in last 7 days"),
  
  -- 30-day rolling metrics
  spend_30d FLOAT64 DEFAULT 0 OPTIONS(description="Spend in last 30 days"),
  orders_30d INT64 DEFAULT 0 OPTIONS(description="Orders in last 30 days"),
  visits_30d INT64 DEFAULT 0 OPTIONS(description="Visits in last 30 days"),
  
  -- 90-day rolling metrics
  spend_90d FLOAT64 DEFAULT 0 OPTIONS(description="Spend in last 90 days"),
  orders_90d INT64 DEFAULT 0 OPTIONS(description="Orders in last 90 days"),
  visits_90d INT64 DEFAULT 0 OPTIONS(description="Visits in last 90 days"),
  
  -- Velocity (rate of change)
  spend_velocity_7d FLOAT64 DEFAULT 0 OPTIONS(description="Daily spend rate (7d)"),
  spend_velocity_30d FLOAT64 DEFAULT 0 OPTIONS(description="Daily spend rate (30d)"),
  order_velocity_7d FLOAT64 DEFAULT 0 OPTIONS(description="Daily order rate (7d)"),
  order_velocity_30d FLOAT64 DEFAULT 0 OPTIONS(description="Daily order rate (30d)"),
  
  -- Acceleration (change in velocity)
  spend_acceleration FLOAT64 DEFAULT 0 OPTIONS(description="Spend velocity change"),
  order_acceleration FLOAT64 DEFAULT 0 OPTIONS(description="Order velocity change"),
  engagement_trend STRING OPTIONS(description="increasing, stable, decreasing"),
  purchase_trend STRING OPTIONS(description="increasing, stable, decreasing"),
  
  -- ========================================================================
  -- FUNNEL FEATURES
  -- ========================================================================
  total_add_to_carts INT64 DEFAULT 0 OPTIONS(description="All-time add to carts"),
  total_checkouts_started INT64 DEFAULT 0 OPTIONS(description="All-time checkout starts"),
  total_leads INT64 DEFAULT 0 OPTIONS(description="All-time leads"),
  cart_to_purchase_rate FLOAT64 DEFAULT 0 OPTIONS(description="Carts that became purchases"),
  checkout_to_purchase_rate FLOAT64 DEFAULT 0 OPTIONS(description="Checkouts completed"),
  view_to_cart_rate FLOAT64 DEFAULT 0 OPTIONS(description="Views that became carts"),
  
  -- ========================================================================
  -- CONTENT PREFERENCE FEATURES
  -- ========================================================================
  favorite_category STRING OPTIONS(description="Most purchased category"),
  favorite_product STRING OPTIONS(description="Most purchased product"),
  category_diversity INT64 DEFAULT 0 OPTIONS(description="Unique categories browsed"),
  product_diversity INT64 DEFAULT 0 OPTIONS(description="Unique products viewed"),
  brand_affinity STRING OPTIONS(description="Preferred brand if any"),
  price_sensitivity STRING OPTIONS(description="low, medium, high"),
  
  -- ========================================================================
  -- CHANNEL & DEVICE FEATURES
  -- ========================================================================
  primary_device STRING OPTIONS(description="Most used device"),
  primary_channel STRING OPTIONS(description="Primary acquisition channel"),
  device_diversity INT64 DEFAULT 0 OPTIONS(description="Unique devices used"),
  channel_diversity INT64 DEFAULT 0 OPTIONS(description="Unique channels used"),
  is_multi_device BOOL DEFAULT FALSE OPTIONS(description="Uses multiple devices"),
  mobile_share FLOAT64 DEFAULT 0 OPTIONS(description="% of visits from mobile"),
  
  -- ========================================================================
  -- QUALITY & TRUST FEATURES
  -- ========================================================================
  avg_trust_score FLOAT64 OPTIONS(description="Average trust score"),
  min_trust_score FLOAT64 OPTIONS(description="Minimum trust score"),
  is_verified_email BOOL DEFAULT FALSE OPTIONS(description="Has verified email"),
  is_verified_phone BOOL DEFAULT FALSE OPTIONS(description="Has verified phone"),
  has_external_id BOOL DEFAULT FALSE OPTIONS(description="Has external ID linked"),
  
  -- ========================================================================
  -- PREDICTIVE FEATURES (from BQML)
  -- ========================================================================
  predicted_ltv FLOAT64 OPTIONS(description="Predicted lifetime value"),
  predicted_churn_risk FLOAT64 OPTIONS(description="Churn probability 0-1"),
  predicted_next_purchase_days INT64 OPTIONS(description="Days until next purchase"),
  customer_segment STRING OPTIONS(description="ML-derived segment"),
  
  -- ========================================================================
  -- RFM SCORES (Normalized 1-5)
  -- ========================================================================
  rfm_recency_score INT64 OPTIONS(description="Recency score 1-5"),
  rfm_frequency_score INT64 OPTIONS(description="Frequency score 1-5"),
  rfm_monetary_score INT64 OPTIONS(description="Monetary score 1-5"),
  rfm_combined_score INT64 OPTIONS(description="Combined RFM score 3-15"),
  rfm_segment STRING OPTIONS(description="RFM segment name"),
  
  -- ========================================================================
  -- METADATA
  -- ========================================================================
  first_processed_at TIMESTAMP OPTIONS(description="When first processed"),
  last_processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP() OPTIONS(description="Last update"),
  feature_version STRING DEFAULT 'v1.0' OPTIONS(description="Feature schema version"),
  processing_errors ARRAY<STRING> OPTIONS(description="Any processing errors")
)
CLUSTER BY canonical_id
OPTIONS (
  description = 'Lifetime user features for ML - incrementally updated',
  labels = [('team', 'data_science'), ('purpose', 'feature_store')]
);


-- ============================================================================
-- SECTION 2: HELPER FUNCTIONS
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Function: Calculate trend direction
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION `ssi_shadow.calculate_trend`(
  current_velocity FLOAT64,
  previous_velocity FLOAT64
) RETURNS STRING
AS (
  CASE
    WHEN current_velocity IS NULL OR previous_velocity IS NULL THEN 'unknown'
    WHEN current_velocity > previous_velocity * 1.1 THEN 'increasing'
    WHEN current_velocity < previous_velocity * 0.9 THEN 'decreasing'
    ELSE 'stable'
  END
);

-- ----------------------------------------------------------------------------
-- Function: Calculate RFM score (1-5 quintiles)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION `ssi_shadow.rfm_score`(
  value FLOAT64,
  p20 FLOAT64,
  p40 FLOAT64,
  p60 FLOAT64,
  p80 FLOAT64,
  higher_is_better BOOL
) RETURNS INT64
AS (
  CASE
    WHEN value IS NULL THEN 1
    WHEN higher_is_better THEN
      CASE
        WHEN value >= p80 THEN 5
        WHEN value >= p60 THEN 4
        WHEN value >= p40 THEN 3
        WHEN value >= p20 THEN 2
        ELSE 1
      END
    ELSE  -- Lower is better (e.g., recency)
      CASE
        WHEN value <= p20 THEN 5
        WHEN value <= p40 THEN 4
        WHEN value <= p60 THEN 3
        WHEN value <= p80 THEN 2
        ELSE 1
      END
  END
);

-- ----------------------------------------------------------------------------
-- Function: Calculate price sensitivity
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION `ssi_shadow.price_sensitivity`(
  avg_order_value FLOAT64,
  global_avg_order_value FLOAT64
) RETURNS STRING
AS (
  CASE
    WHEN avg_order_value IS NULL OR global_avg_order_value IS NULL THEN 'unknown'
    WHEN avg_order_value < global_avg_order_value * 0.7 THEN 'high'
    WHEN avg_order_value > global_avg_order_value * 1.3 THEN 'low'
    ELSE 'medium'
  END
);

-- ----------------------------------------------------------------------------
-- Function: Classify RFM segment
-- ----------------------------------------------------------------------------
CREATE OR REPLACE FUNCTION `ssi_shadow.rfm_segment_name`(
  r INT64,  -- Recency score
  f INT64,  -- Frequency score
  m INT64   -- Monetary score
) RETURNS STRING
AS (
  CASE
    -- Champions: Best customers
    WHEN r >= 4 AND f >= 4 AND m >= 4 THEN 'Champions'
    -- Loyal Customers: High frequency and monetary
    WHEN f >= 4 AND m >= 4 THEN 'Loyal Customers'
    -- Potential Loyalists: Recent with decent frequency
    WHEN r >= 4 AND f >= 3 THEN 'Potential Loyalists'
    -- New Customers: Very recent, low frequency
    WHEN r >= 4 AND f <= 2 THEN 'New Customers'
    -- Promising: Recent, medium everything
    WHEN r >= 3 AND f >= 2 AND m >= 2 THEN 'Promising'
    -- Needs Attention: Above average but slipping
    WHEN r >= 3 AND f >= 3 THEN 'Needs Attention'
    -- About to Sleep: Below average recency
    WHEN r >= 2 AND f >= 2 THEN 'About to Sleep'
    -- At Risk: High value but not recent
    WHEN r <= 2 AND f >= 4 AND m >= 4 THEN 'At Risk'
    -- Cannot Lose Them: Very high value, very low recency
    WHEN r <= 2 AND f >= 4 AND m >= 5 THEN 'Cannot Lose Them'
    -- Hibernating: Low everything
    WHEN r <= 2 AND f <= 2 THEN 'Hibernating'
    -- Lost: Very old, very low engagement
    WHEN r = 1 AND f = 1 THEN 'Lost'
    ELSE 'Other'
  END
);


-- ============================================================================
-- SECTION 3: MAIN PROCEDURES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Procedure: Update Daily Features
-- Calculates features for a specific date from events_raw
-- Only processes events from that single day (cost efficient!)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE `ssi_shadow.update_daily_features`(
  IN process_date DATE
)
BEGIN
  DECLARE rows_affected INT64;
  
  -- Log start
  SELECT CONCAT('Starting daily features for: ', CAST(process_date AS STRING));
  
  -- Delete existing data for this date (idempotent)
  DELETE FROM `ssi_shadow.user_features_daily`
  WHERE feature_date = process_date;
  
  -- Insert new daily features
  -- This only scans the partition for process_date!
  INSERT INTO `ssi_shadow.user_features_daily` (
    canonical_id,
    feature_date,
    daily_visits,
    daily_pageviews,
    daily_unique_pages,
    daily_time_on_site,
    daily_avg_time_per_page,
    daily_avg_scroll_depth,
    daily_clicks,
    daily_spend,
    daily_orders,
    daily_items,
    daily_avg_order_value,
    daily_leads,
    daily_add_to_carts,
    daily_checkouts_started,
    daily_product_views,
    daily_category_views,
    daily_search_count,
    most_viewed_category,
    most_viewed_product,
    primary_device,
    primary_channel,
    is_mobile,
    avg_trust_score,
    low_trust_events,
    ssi_ids,
    event_count
  )
  WITH 
  -- Base events for the day (partition-pruned)
  day_events AS (
    SELECT
      COALESCE(canonical_id, ssi_id) AS user_id,
      *
    FROM `ssi_shadow.events_raw`
    WHERE DATE(event_time) = process_date
      AND COALESCE(canonical_id, ssi_id) IS NOT NULL
  ),
  
  -- Session-level aggregations
  sessions AS (
    SELECT
      user_id,
      session_id,
      COUNT(*) AS pageviews,
      MAX(session_duration) AS duration,
      MAX(scroll_depth) AS max_scroll
    FROM day_events
    WHERE session_id IS NOT NULL
    GROUP BY user_id, session_id
  ),
  
  -- Engagement metrics
  engagement AS (
    SELECT
      user_id,
      COUNT(DISTINCT session_id) AS visits,
      COUNT(CASE WHEN event_name = 'PageView' THEN 1 END) AS pageviews,
      COUNT(DISTINCT path) AS unique_pages,
      SUM(COALESCE(time_on_page, 0)) / 1000 AS time_on_site_sec,
      AVG(scroll_depth) AS avg_scroll,
      SUM(COALESCE(clicks, 0)) AS total_clicks
    FROM day_events
    GROUP BY user_id
  ),
  
  -- Conversion metrics
  conversions AS (
    SELECT
      user_id,
      SUM(CASE WHEN event_name = 'Purchase' THEN COALESCE(value, 0) ELSE 0 END) AS spend,
      COUNT(CASE WHEN event_name = 'Purchase' THEN 1 END) AS orders,
      SUM(CASE WHEN event_name = 'Purchase' THEN COALESCE(num_items, 0) ELSE 0 END) AS items,
      COUNT(CASE WHEN event_name = 'Lead' THEN 1 END) AS leads,
      COUNT(CASE WHEN event_name = 'AddToCart' THEN 1 END) AS add_to_carts,
      COUNT(CASE WHEN event_name = 'InitiateCheckout' THEN 1 END) AS checkouts
    FROM day_events
    GROUP BY user_id
  ),
  
  -- Content engagement
  content AS (
    SELECT
      user_id,
      COUNT(CASE WHEN event_name = 'ViewContent' AND content_type = 'product' THEN 1 END) AS product_views,
      COUNT(CASE WHEN event_name = 'ViewContent' AND content_type = 'category' THEN 1 END) AS category_views,
      COUNT(CASE WHEN event_name = 'Search' THEN 1 END) AS searches,
      -- Most viewed category (mode)
      ARRAY_AGG(content_category IGNORE NULLS ORDER BY content_category LIMIT 1)[SAFE_OFFSET(0)] AS top_category,
      -- Most viewed product (mode)
      ARRAY_AGG(content_name IGNORE NULLS ORDER BY content_name LIMIT 1)[SAFE_OFFSET(0)] AS top_product
    FROM day_events
    GROUP BY user_id
  ),
  
  -- Device/channel info
  device_channel AS (
    SELECT
      user_id,
      -- Primary device (most events)
      APPROX_TOP_COUNT(
        CASE 
          WHEN REGEXP_CONTAINS(LOWER(user_agent), 'mobile|android|iphone') THEN 'mobile'
          WHEN REGEXP_CONTAINS(LOWER(user_agent), 'tablet|ipad') THEN 'tablet'
          ELSE 'desktop'
        END, 1
      )[SAFE_OFFSET(0)].value AS primary_device,
      -- Primary channel
      APPROX_TOP_COUNT(
        CASE
          WHEN fbclid IS NOT NULL THEN 'facebook'
          WHEN gclid IS NOT NULL THEN 'google'
          WHEN ttclid IS NOT NULL THEN 'tiktok'
          WHEN REGEXP_CONTAINS(LOWER(referrer), 'google') THEN 'organic_search'
          WHEN REGEXP_CONTAINS(LOWER(referrer), 'facebook|instagram') THEN 'social'
          WHEN referrer IS NULL OR referrer = '' THEN 'direct'
          ELSE 'referral'
        END, 1
      )[SAFE_OFFSET(0)].value AS primary_channel,
      -- Mobile share
      COUNTIF(REGEXP_CONTAINS(LOWER(user_agent), 'mobile|android|iphone')) / COUNT(*) AS mobile_share
    FROM day_events
    GROUP BY user_id
  ),
  
  -- Trust metrics
  trust_metrics AS (
    SELECT
      user_id,
      AVG(trust_score) AS avg_trust,
      COUNTIF(trust_score < 0.5) AS low_trust_count
    FROM day_events
    GROUP BY user_id
  ),
  
  -- SSI IDs collection
  ssi_collection AS (
    SELECT
      user_id,
      ARRAY_AGG(DISTINCT ssi_id) AS ssi_ids,
      COUNT(*) AS event_count
    FROM day_events
    GROUP BY user_id
  )
  
  -- Final SELECT combining all CTEs
  SELECT
    e.user_id AS canonical_id,
    process_date AS feature_date,
    COALESCE(e.visits, 0) AS daily_visits,
    COALESCE(e.pageviews, 0) AS daily_pageviews,
    COALESCE(e.unique_pages, 0) AS daily_unique_pages,
    CAST(COALESCE(e.time_on_site_sec, 0) AS INT64) AS daily_time_on_site,
    SAFE_DIVIDE(e.time_on_site_sec, NULLIF(e.pageviews, 0)) AS daily_avg_time_per_page,
    COALESCE(e.avg_scroll, 0) AS daily_avg_scroll_depth,
    COALESCE(e.total_clicks, 0) AS daily_clicks,
    COALESCE(c.spend, 0) AS daily_spend,
    COALESCE(c.orders, 0) AS daily_orders,
    COALESCE(c.items, 0) AS daily_items,
    SAFE_DIVIDE(c.spend, NULLIF(c.orders, 0)) AS daily_avg_order_value,
    COALESCE(c.leads, 0) AS daily_leads,
    COALESCE(c.add_to_carts, 0) AS daily_add_to_carts,
    COALESCE(c.checkouts, 0) AS daily_checkouts_started,
    COALESCE(cn.product_views, 0) AS daily_product_views,
    COALESCE(cn.category_views, 0) AS daily_category_views,
    COALESCE(cn.searches, 0) AS daily_search_count,
    cn.top_category AS most_viewed_category,
    cn.top_product AS most_viewed_product,
    dc.primary_device,
    dc.primary_channel,
    dc.mobile_share > 0.5 AS is_mobile,
    tm.avg_trust AS avg_trust_score,
    COALESCE(tm.low_trust_count, 0) AS low_trust_events,
    sc.ssi_ids,
    sc.event_count
  FROM engagement e
  LEFT JOIN conversions c ON e.user_id = c.user_id
  LEFT JOIN content cn ON e.user_id = cn.user_id
  LEFT JOIN device_channel dc ON e.user_id = dc.user_id
  LEFT JOIN trust_metrics tm ON e.user_id = tm.user_id
  LEFT JOIN ssi_collection sc ON e.user_id = sc.user_id;
  
  -- Get row count
  SET rows_affected = @@row_count;
  
  SELECT CONCAT('Daily features updated: ', CAST(rows_affected AS STRING), ' users');
  
END;


-- ----------------------------------------------------------------------------
-- Procedure: Update Lifetime Features
-- Uses MERGE to incrementally update lifetime features from daily features
-- This is the key to cost efficiency - we don't reprocess history!
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE `ssi_shadow.update_lifetime_features`(
  IN process_date DATE
)
BEGIN
  DECLARE global_avg_order_value FLOAT64;
  DECLARE rows_merged INT64;
  
  -- Calculate global AOV for price sensitivity
  SET global_avg_order_value = (
    SELECT SAFE_DIVIDE(SUM(daily_spend), NULLIF(SUM(daily_orders), 0))
    FROM `ssi_shadow.user_features_daily`
    WHERE feature_date >= DATE_SUB(process_date, INTERVAL 90 DAY)
  );
  
  -- Calculate RFM percentiles for scoring
  CREATE OR REPLACE TEMP TABLE rfm_percentiles AS
  SELECT
    -- Recency percentiles (days since last purchase)
    APPROX_QUANTILES(DATE_DIFF(process_date, last_purchase_date, DAY), 100)[OFFSET(20)] AS recency_p20,
    APPROX_QUANTILES(DATE_DIFF(process_date, last_purchase_date, DAY), 100)[OFFSET(40)] AS recency_p40,
    APPROX_QUANTILES(DATE_DIFF(process_date, last_purchase_date, DAY), 100)[OFFSET(60)] AS recency_p60,
    APPROX_QUANTILES(DATE_DIFF(process_date, last_purchase_date, DAY), 100)[OFFSET(80)] AS recency_p80,
    -- Frequency percentiles (total orders)
    APPROX_QUANTILES(total_orders, 100)[OFFSET(20)] AS frequency_p20,
    APPROX_QUANTILES(total_orders, 100)[OFFSET(40)] AS frequency_p40,
    APPROX_QUANTILES(total_orders, 100)[OFFSET(60)] AS frequency_p60,
    APPROX_QUANTILES(total_orders, 100)[OFFSET(80)] AS frequency_p80,
    -- Monetary percentiles (total spend)
    APPROX_QUANTILES(total_spend, 100)[OFFSET(20)] AS monetary_p20,
    APPROX_QUANTILES(total_spend, 100)[OFFSET(40)] AS monetary_p40,
    APPROX_QUANTILES(total_spend, 100)[OFFSET(60)] AS monetary_p60,
    APPROX_QUANTILES(total_spend, 100)[OFFSET(80)] AS monetary_p80
  FROM `ssi_shadow.user_features_lifetime`
  WHERE total_orders > 0;
  
  -- Main MERGE: Update existing users or insert new ones
  MERGE INTO `ssi_shadow.user_features_lifetime` AS L
  USING (
    WITH 
    -- Get today's daily features
    today AS (
      SELECT * 
      FROM `ssi_shadow.user_features_daily`
      WHERE feature_date = process_date
    ),
    
    -- Get rolling window features (7d, 30d, 90d)
    rolling AS (
      SELECT
        canonical_id,
        -- 7-day
        SUM(CASE WHEN feature_date >= DATE_SUB(process_date, INTERVAL 7 DAY) 
            THEN daily_spend ELSE 0 END) AS spend_7d,
        SUM(CASE WHEN feature_date >= DATE_SUB(process_date, INTERVAL 7 DAY) 
            THEN daily_orders ELSE 0 END) AS orders_7d,
        SUM(CASE WHEN feature_date >= DATE_SUB(process_date, INTERVAL 7 DAY) 
            THEN daily_visits ELSE 0 END) AS visits_7d,
        -- 30-day
        SUM(CASE WHEN feature_date >= DATE_SUB(process_date, INTERVAL 30 DAY) 
            THEN daily_spend ELSE 0 END) AS spend_30d,
        SUM(CASE WHEN feature_date >= DATE_SUB(process_date, INTERVAL 30 DAY) 
            THEN daily_orders ELSE 0 END) AS orders_30d,
        SUM(CASE WHEN feature_date >= DATE_SUB(process_date, INTERVAL 30 DAY) 
            THEN daily_visits ELSE 0 END) AS visits_30d,
        -- 90-day
        SUM(daily_spend) AS spend_90d,
        SUM(daily_orders) AS orders_90d,
        SUM(daily_visits) AS visits_90d
      FROM `ssi_shadow.user_features_daily`
      WHERE feature_date >= DATE_SUB(process_date, INTERVAL 90 DAY)
        AND feature_date <= process_date
      GROUP BY canonical_id
    ),
    
    -- Previous period velocities (for acceleration)
    prev_velocity AS (
      SELECT
        canonical_id,
        SAFE_DIVIDE(
          SUM(CASE WHEN feature_date BETWEEN DATE_SUB(process_date, INTERVAL 14 DAY) 
                                         AND DATE_SUB(process_date, INTERVAL 8 DAY)
              THEN daily_spend ELSE 0 END), 7
        ) AS prev_spend_velocity_7d,
        SAFE_DIVIDE(
          SUM(CASE WHEN feature_date BETWEEN DATE_SUB(process_date, INTERVAL 60 DAY) 
                                         AND DATE_SUB(process_date, INTERVAL 31 DAY)
              THEN daily_spend ELSE 0 END), 30
        ) AS prev_spend_velocity_30d
      FROM `ssi_shadow.user_features_daily`
      WHERE feature_date >= DATE_SUB(process_date, INTERVAL 60 DAY)
      GROUP BY canonical_id
    )
    
    SELECT
      t.canonical_id,
      t.feature_date,
      -- Daily metrics
      t.daily_visits,
      t.daily_pageviews,
      t.daily_time_on_site,
      t.daily_clicks,
      t.daily_spend,
      t.daily_orders,
      t.daily_items,
      t.daily_leads,
      t.daily_add_to_carts,
      t.daily_checkouts_started,
      t.most_viewed_category,
      t.most_viewed_product,
      t.primary_device,
      t.primary_channel,
      t.is_mobile,
      t.avg_trust_score,
      -- Rolling metrics
      COALESCE(r.spend_7d, t.daily_spend) AS spend_7d,
      COALESCE(r.orders_7d, t.daily_orders) AS orders_7d,
      COALESCE(r.visits_7d, t.daily_visits) AS visits_7d,
      COALESCE(r.spend_30d, t.daily_spend) AS spend_30d,
      COALESCE(r.orders_30d, t.daily_orders) AS orders_30d,
      COALESCE(r.visits_30d, t.daily_visits) AS visits_30d,
      COALESCE(r.spend_90d, t.daily_spend) AS spend_90d,
      COALESCE(r.orders_90d, t.daily_orders) AS orders_90d,
      COALESCE(r.visits_90d, t.daily_visits) AS visits_90d,
      -- Previous velocities
      pv.prev_spend_velocity_7d,
      pv.prev_spend_velocity_30d
    FROM today t
    LEFT JOIN rolling r ON t.canonical_id = r.canonical_id
    LEFT JOIN prev_velocity pv ON t.canonical_id = pv.canonical_id
  ) AS D
  ON L.canonical_id = D.canonical_id
  
  -- ========================================================================
  -- WHEN MATCHED: Incrementally update existing user
  -- ========================================================================
  WHEN MATCHED THEN UPDATE SET
    -- Engagement: Add daily to lifetime totals
    L.total_visits = L.total_visits + D.daily_visits,
    L.total_pageviews = L.total_pageviews + D.daily_pageviews,
    L.total_time_on_site = L.total_time_on_site + D.daily_time_on_site,
    L.total_clicks = L.total_clicks + D.daily_clicks,
    
    -- Monetary: Add daily to lifetime totals
    L.total_spend = L.total_spend + D.daily_spend,
    L.total_orders = L.total_orders + D.daily_orders,
    L.total_items = L.total_items + D.daily_items,
    
    -- Funnel: Add daily to lifetime totals
    L.total_add_to_carts = L.total_add_to_carts + D.daily_add_to_carts,
    L.total_checkouts_started = L.total_checkouts_started + D.daily_checkouts_started,
    L.total_leads = L.total_leads + D.daily_leads,
    
    -- Recency: Update dates
    L.last_seen_date = D.feature_date,
    L.last_purchase_date = IF(D.daily_orders > 0, D.feature_date, L.last_purchase_date),
    L.days_since_last_seen = 0,
    L.days_since_last_purchase = IF(D.daily_orders > 0, 0, 
                                    DATE_DIFF(D.feature_date, L.last_purchase_date, DAY)),
    L.days_since_first_seen = DATE_DIFF(D.feature_date, L.first_seen_date, DAY),
    L.days_since_first_purchase = IF(L.first_purchase_date IS NOT NULL,
                                      DATE_DIFF(D.feature_date, L.first_purchase_date, DAY),
                                      NULL),
    
    -- Active days tracking
    L.active_days = L.active_days + 1,
    L.purchase_days = L.purchase_days + IF(D.daily_orders > 0, 1, 0),
    
    -- Calculated averages (after incrementing totals)
    L.avg_order_value = SAFE_DIVIDE(L.total_spend + D.daily_spend, 
                                    NULLIF(L.total_orders + D.daily_orders, 0)),
    L.avg_time_per_visit = SAFE_DIVIDE(L.total_time_on_site + D.daily_time_on_site,
                                       NULLIF(L.total_visits + D.daily_visits, 0)),
    L.avg_pages_per_visit = SAFE_DIVIDE(L.total_pageviews + D.daily_pageviews,
                                        NULLIF(L.total_visits + D.daily_visits, 0)),
    L.max_order_value = IF(D.daily_spend > 0 AND D.daily_orders > 0,
                           GREATEST(COALESCE(L.max_order_value, 0), 
                                    D.daily_spend / D.daily_orders),
                           L.max_order_value),
    
    -- Frequency metrics
    L.purchase_frequency = SAFE_DIVIDE(L.total_orders + D.daily_orders,
                                       NULLIF(L.active_days + 1, 0)),
    L.visit_frequency = SAFE_DIVIDE((L.total_visits + D.daily_visits) * 7,
                                    NULLIF(DATE_DIFF(D.feature_date, L.first_seen_date, DAY), 0)),
    L.days_between_purchases = SAFE_DIVIDE(
      DATE_DIFF(D.feature_date, L.first_purchase_date, DAY),
      NULLIF(L.total_orders + D.daily_orders - 1, 0)
    ),
    
    -- Revenue metrics
    L.revenue_per_visit = SAFE_DIVIDE(L.total_spend + D.daily_spend,
                                      NULLIF(L.total_visits + D.daily_visits, 0)),
    L.revenue_per_day = SAFE_DIVIDE(L.total_spend + D.daily_spend,
                                    NULLIF(L.active_days + 1, 0)),
    
    -- Funnel rates
    L.cart_to_purchase_rate = SAFE_DIVIDE(L.total_orders + D.daily_orders,
                                          NULLIF(L.total_add_to_carts + D.daily_add_to_carts, 0)),
    L.checkout_to_purchase_rate = SAFE_DIVIDE(L.total_orders + D.daily_orders,
                                              NULLIF(L.total_checkouts_started + D.daily_checkouts_started, 0)),
    
    -- Rolling window metrics
    L.spend_7d = D.spend_7d,
    L.orders_7d = D.orders_7d,
    L.visits_7d = D.visits_7d,
    L.spend_30d = D.spend_30d,
    L.orders_30d = D.orders_30d,
    L.visits_30d = D.visits_30d,
    L.spend_90d = D.spend_90d,
    L.orders_90d = D.orders_90d,
    L.visits_90d = D.visits_90d,
    
    -- Velocity (rate per day)
    L.spend_velocity_7d = SAFE_DIVIDE(D.spend_7d, 7),
    L.spend_velocity_30d = SAFE_DIVIDE(D.spend_30d, 30),
    L.order_velocity_7d = SAFE_DIVIDE(D.orders_7d, 7),
    L.order_velocity_30d = SAFE_DIVIDE(D.orders_30d, 30),
    
    -- Acceleration (change in velocity)
    L.spend_acceleration = SAFE_DIVIDE(D.spend_7d, 7) - COALESCE(D.prev_spend_velocity_7d, 0),
    L.order_acceleration = SAFE_DIVIDE(D.orders_7d, 7) - 
                           SAFE_DIVIDE(D.orders_30d - D.orders_7d, 23),
    
    -- Trends
    L.engagement_trend = `ssi_shadow.calculate_trend`(
      SAFE_DIVIDE(D.visits_7d, 7),
      SAFE_DIVIDE(D.visits_30d - D.visits_7d, 23)
    ),
    L.purchase_trend = `ssi_shadow.calculate_trend`(
      SAFE_DIVIDE(D.spend_7d, 7),
      D.prev_spend_velocity_7d
    ),
    
    -- Content preferences (update if significant activity)
    L.favorite_category = IF(D.daily_orders > 0, 
                             COALESCE(D.most_viewed_category, L.favorite_category),
                             L.favorite_category),
    L.favorite_product = IF(D.daily_orders > 0,
                            COALESCE(D.most_viewed_product, L.favorite_product),
                            L.favorite_product),
    
    -- Device/channel (update rolling)
    L.primary_device = IF(D.daily_visits >= 2, D.primary_device, L.primary_device),
    L.primary_channel = IF(D.daily_visits >= 2, D.primary_channel, L.primary_channel),
    L.mobile_share = (L.mobile_share * L.total_visits + IF(D.is_mobile, D.daily_visits, 0)) 
                     / (L.total_visits + D.daily_visits),
    L.is_multi_device = L.is_multi_device OR (L.primary_device != D.primary_device),
    
    -- Trust metrics
    L.avg_trust_score = (COALESCE(L.avg_trust_score, 1) * L.total_visits + 
                         COALESCE(D.avg_trust_score, 1) * D.daily_visits) 
                        / (L.total_visits + D.daily_visits),
    L.min_trust_score = LEAST(COALESCE(L.min_trust_score, 1), 
                              COALESCE(D.avg_trust_score, 1)),
    
    -- Price sensitivity
    L.price_sensitivity = `ssi_shadow.price_sensitivity`(
      SAFE_DIVIDE(L.total_spend + D.daily_spend, NULLIF(L.total_orders + D.daily_orders, 0)),
      global_avg_order_value
    ),
    
    -- Metadata
    L.last_processed_at = CURRENT_TIMESTAMP()
  
  -- ========================================================================
  -- WHEN NOT MATCHED: Insert new user
  -- ========================================================================
  WHEN NOT MATCHED THEN INSERT (
    canonical_id,
    -- Engagement
    total_visits,
    total_pageviews,
    total_time_on_site,
    total_clicks,
    avg_time_per_visit,
    avg_pages_per_visit,
    -- Monetary
    total_spend,
    total_orders,
    total_items,
    avg_order_value,
    max_order_value,
    -- Recency
    first_seen_date,
    last_seen_date,
    first_purchase_date,
    last_purchase_date,
    days_since_first_seen,
    days_since_last_seen,
    days_since_first_purchase,
    days_since_last_purchase,
    -- Frequency
    active_days,
    purchase_days,
    purchase_frequency,
    visit_frequency,
    -- Revenue
    revenue_per_visit,
    revenue_per_day,
    -- Funnel
    total_add_to_carts,
    total_checkouts_started,
    total_leads,
    cart_to_purchase_rate,
    checkout_to_purchase_rate,
    -- Rolling
    spend_7d, orders_7d, visits_7d,
    spend_30d, orders_30d, visits_30d,
    spend_90d, orders_90d, visits_90d,
    -- Velocity
    spend_velocity_7d, spend_velocity_30d,
    order_velocity_7d, order_velocity_30d,
    -- Trends
    engagement_trend, purchase_trend,
    -- Content
    favorite_category, favorite_product,
    -- Device/Channel
    primary_device, primary_channel,
    mobile_share, is_multi_device,
    -- Trust
    avg_trust_score, min_trust_score,
    -- Price
    price_sensitivity,
    -- Metadata
    first_processed_at, last_processed_at, feature_version
  )
  VALUES (
    D.canonical_id,
    -- Engagement
    D.daily_visits,
    D.daily_pageviews,
    D.daily_time_on_site,
    D.daily_clicks,
    SAFE_DIVIDE(D.daily_time_on_site, NULLIF(D.daily_visits, 0)),
    SAFE_DIVIDE(D.daily_pageviews, NULLIF(D.daily_visits, 0)),
    -- Monetary
    D.daily_spend,
    D.daily_orders,
    D.daily_items,
    SAFE_DIVIDE(D.daily_spend, NULLIF(D.daily_orders, 0)),
    SAFE_DIVIDE(D.daily_spend, NULLIF(D.daily_orders, 0)),
    -- Recency
    D.feature_date,
    D.feature_date,
    IF(D.daily_orders > 0, D.feature_date, NULL),
    IF(D.daily_orders > 0, D.feature_date, NULL),
    0,
    0,
    IF(D.daily_orders > 0, 0, NULL),
    IF(D.daily_orders > 0, 0, NULL),
    -- Frequency
    1,
    IF(D.daily_orders > 0, 1, 0),
    SAFE_DIVIDE(D.daily_orders, 1),
    D.daily_visits,
    -- Revenue
    SAFE_DIVIDE(D.daily_spend, NULLIF(D.daily_visits, 0)),
    D.daily_spend,
    -- Funnel
    D.daily_add_to_carts,
    D.daily_checkouts_started,
    D.daily_leads,
    SAFE_DIVIDE(D.daily_orders, NULLIF(D.daily_add_to_carts, 0)),
    SAFE_DIVIDE(D.daily_orders, NULLIF(D.daily_checkouts_started, 0)),
    -- Rolling
    D.spend_7d, D.orders_7d, D.visits_7d,
    D.spend_30d, D.orders_30d, D.visits_30d,
    D.spend_90d, D.orders_90d, D.visits_90d,
    -- Velocity
    SAFE_DIVIDE(D.spend_7d, 7), SAFE_DIVIDE(D.spend_30d, 30),
    SAFE_DIVIDE(D.orders_7d, 7), SAFE_DIVIDE(D.orders_30d, 30),
    -- Trends
    'unknown', 'unknown',
    -- Content
    D.most_viewed_category, D.most_viewed_product,
    -- Device/Channel
    D.primary_device, D.primary_channel,
    IF(D.is_mobile, 1.0, 0.0), FALSE,
    -- Trust
    D.avg_trust_score, D.avg_trust_score,
    -- Price
    `ssi_shadow.price_sensitivity`(
      SAFE_DIVIDE(D.daily_spend, NULLIF(D.daily_orders, 0)),
      global_avg_order_value
    ),
    -- Metadata
    CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP(), 'v1.0'
  );
  
  SET rows_merged = @@row_count;
  SELECT CONCAT('Lifetime features merged: ', CAST(rows_merged AS STRING), ' users');
  
END;


-- ----------------------------------------------------------------------------
-- Procedure: Update RFM Scores
-- Separate procedure to calculate RFM after all updates
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE `ssi_shadow.update_rfm_scores`(
  IN process_date DATE
)
BEGIN
  -- Calculate RFM percentiles from current data
  CREATE OR REPLACE TEMP TABLE rfm_percentiles AS
  SELECT
    APPROX_QUANTILES(days_since_last_purchase, 100)[OFFSET(20)] AS r_p20,
    APPROX_QUANTILES(days_since_last_purchase, 100)[OFFSET(40)] AS r_p40,
    APPROX_QUANTILES(days_since_last_purchase, 100)[OFFSET(60)] AS r_p60,
    APPROX_QUANTILES(days_since_last_purchase, 100)[OFFSET(80)] AS r_p80,
    APPROX_QUANTILES(total_orders, 100)[OFFSET(20)] AS f_p20,
    APPROX_QUANTILES(total_orders, 100)[OFFSET(40)] AS f_p40,
    APPROX_QUANTILES(total_orders, 100)[OFFSET(60)] AS f_p60,
    APPROX_QUANTILES(total_orders, 100)[OFFSET(80)] AS f_p80,
    APPROX_QUANTILES(total_spend, 100)[OFFSET(20)] AS m_p20,
    APPROX_QUANTILES(total_spend, 100)[OFFSET(40)] AS m_p40,
    APPROX_QUANTILES(total_spend, 100)[OFFSET(60)] AS m_p60,
    APPROX_QUANTILES(total_spend, 100)[OFFSET(80)] AS m_p80
  FROM `ssi_shadow.user_features_lifetime`
  WHERE total_orders > 0;
  
  -- Update RFM scores for users who had activity today
  UPDATE `ssi_shadow.user_features_lifetime` L
  SET
    rfm_recency_score = `ssi_shadow.rfm_score`(
      L.days_since_last_purchase,
      p.r_p20, p.r_p40, p.r_p60, p.r_p80,
      FALSE  -- Lower is better for recency
    ),
    rfm_frequency_score = `ssi_shadow.rfm_score`(
      CAST(L.total_orders AS FLOAT64),
      p.f_p20, p.f_p40, p.f_p60, p.f_p80,
      TRUE  -- Higher is better
    ),
    rfm_monetary_score = `ssi_shadow.rfm_score`(
      L.total_spend,
      p.m_p20, p.m_p40, p.m_p60, p.m_p80,
      TRUE  -- Higher is better
    )
  FROM rfm_percentiles p
  WHERE L.last_processed_at >= TIMESTAMP(process_date);
  
  -- Update combined score and segment
  UPDATE `ssi_shadow.user_features_lifetime`
  SET
    rfm_combined_score = rfm_recency_score + rfm_frequency_score + rfm_monetary_score,
    rfm_segment = `ssi_shadow.rfm_segment_name`(
      rfm_recency_score,
      rfm_frequency_score,
      rfm_monetary_score
    )
  WHERE last_processed_at >= TIMESTAMP(process_date)
    AND rfm_recency_score IS NOT NULL;
  
  SELECT 'RFM scores updated';
  
END;


-- ----------------------------------------------------------------------------
-- Procedure: Decay Inactive Users
-- Update recency features for users who had no activity
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE `ssi_shadow.decay_inactive_users`(
  IN process_date DATE
)
BEGIN
  -- Update days_since metrics for inactive users
  UPDATE `ssi_shadow.user_features_lifetime`
  SET
    days_since_last_seen = DATE_DIFF(process_date, last_seen_date, DAY),
    days_since_last_purchase = IF(last_purchase_date IS NOT NULL,
                                   DATE_DIFF(process_date, last_purchase_date, DAY),
                                   NULL),
    -- Decay rolling windows (subtract oldest day)
    spend_7d = GREATEST(0, spend_7d - COALESCE(
      (SELECT daily_spend 
       FROM `ssi_shadow.user_features_daily` d
       WHERE d.canonical_id = canonical_id 
         AND d.feature_date = DATE_SUB(process_date, INTERVAL 7 DAY)), 0)),
    orders_7d = GREATEST(0, orders_7d - COALESCE(
      (SELECT daily_orders 
       FROM `ssi_shadow.user_features_daily` d
       WHERE d.canonical_id = canonical_id 
         AND d.feature_date = DATE_SUB(process_date, INTERVAL 7 DAY)), 0)),
    visits_7d = GREATEST(0, visits_7d - COALESCE(
      (SELECT daily_visits 
       FROM `ssi_shadow.user_features_daily` d
       WHERE d.canonical_id = canonical_id 
         AND d.feature_date = DATE_SUB(process_date, INTERVAL 7 DAY)), 0))
  WHERE DATE(last_processed_at) < process_date
    AND last_seen_date >= DATE_SUB(process_date, INTERVAL 90 DAY);  -- Only recent users
  
  SELECT 'Inactive users decayed';
  
END;


-- ============================================================================
-- SECTION 4: MAIN ORCHESTRATION PROCEDURE
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Procedure: update_features (Main Entry Point)
-- Orchestrates all feature updates for a given date
-- Run this daily via Cloud Scheduler
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE `ssi_shadow.update_features`(
  IN process_date DATE DEFAULT NULL
)
BEGIN
  DECLARE effective_date DATE;
  DECLARE start_time TIMESTAMP;
  DECLARE end_time TIMESTAMP;
  
  -- Default to yesterday
  SET effective_date = COALESCE(process_date, DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY));
  SET start_time = CURRENT_TIMESTAMP();
  
  -- Log start
  SELECT CONCAT(
    '========================================\n',
    'Feature Store Update Starting\n',
    'Processing Date: ', CAST(effective_date AS STRING), '\n',
    'Start Time: ', CAST(start_time AS STRING), '\n',
    '========================================'
  );
  
  -- Step 1: Calculate daily features from events_raw
  -- This only scans one partition of events_raw!
  CALL `ssi_shadow.update_daily_features`(effective_date);
  
  -- Step 2: Update lifetime features incrementally
  -- Uses MERGE to add daily metrics to lifetime totals
  CALL `ssi_shadow.update_lifetime_features`(effective_date);
  
  -- Step 3: Update RFM scores
  CALL `ssi_shadow.update_rfm_scores`(effective_date);
  
  -- Step 4: Decay inactive users
  CALL `ssi_shadow.decay_inactive_users`(effective_date);
  
  -- Log completion
  SET end_time = CURRENT_TIMESTAMP();
  
  SELECT CONCAT(
    '========================================\n',
    'Feature Store Update Complete\n',
    'Duration: ', CAST(TIMESTAMP_DIFF(end_time, start_time, SECOND) AS STRING), ' seconds\n',
    '========================================'
  );
  
END;


-- ============================================================================
-- SECTION 5: UTILITY PROCEDURES & QUERIES
-- ============================================================================

-- ----------------------------------------------------------------------------
-- Procedure: Get User Features (for ML inference)
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE `ssi_shadow.get_user_features`(
  IN user_id STRING,
  OUT features STRUCT<
    canonical_id STRING,
    total_spend FLOAT64,
    total_orders INT64,
    days_since_last_purchase INT64,
    purchase_frequency FLOAT64,
    avg_order_value FLOAT64,
    spend_velocity_30d FLOAT64,
    rfm_segment STRING,
    predicted_churn_risk FLOAT64
  >
)
BEGIN
  SET features = (
    SELECT AS STRUCT
      canonical_id,
      total_spend,
      total_orders,
      days_since_last_purchase,
      purchase_frequency,
      avg_order_value,
      spend_velocity_30d,
      rfm_segment,
      predicted_churn_risk
    FROM `ssi_shadow.user_features_lifetime`
    WHERE canonical_id = user_id
  );
END;


-- ----------------------------------------------------------------------------
-- Procedure: Backfill Features
-- For initial setup or recovering from issues
-- WARNING: This scans full history and is expensive!
-- ----------------------------------------------------------------------------
CREATE OR REPLACE PROCEDURE `ssi_shadow.backfill_features`(
  IN start_date DATE,
  IN end_date DATE
)
BEGIN
  DECLARE current_date DATE;
  
  SET current_date = start_date;
  
  WHILE current_date <= end_date DO
    SELECT CONCAT('Backfilling: ', CAST(current_date AS STRING));
    CALL `ssi_shadow.update_features`(current_date);
    SET current_date = DATE_ADD(current_date, INTERVAL 1 DAY);
  END WHILE;
  
  SELECT 'Backfill complete';
END;


-- ============================================================================
-- SECTION 6: MONITORING & OBSERVABILITY
-- ============================================================================

-- Daily feature quality check
CREATE OR REPLACE VIEW `ssi_shadow.feature_quality_daily` AS
SELECT
  feature_date,
  COUNT(*) AS total_users,
  COUNT(CASE WHEN daily_spend > 0 THEN 1 END) AS users_with_spend,
  SUM(daily_spend) AS total_daily_spend,
  SUM(daily_orders) AS total_daily_orders,
  AVG(daily_visits) AS avg_visits,
  AVG(daily_pageviews) AS avg_pageviews,
  -- Data quality indicators
  COUNTIF(daily_visits = 0) AS zero_visit_users,
  COUNTIF(event_count < 5) AS low_event_users,
  COUNTIF(avg_trust_score < 0.5) AS low_trust_users
FROM `ssi_shadow.user_features_daily`
WHERE feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
GROUP BY feature_date
ORDER BY feature_date DESC;


-- Lifetime feature distribution
CREATE OR REPLACE VIEW `ssi_shadow.feature_distribution` AS
SELECT
  rfm_segment,
  COUNT(*) AS user_count,
  AVG(total_spend) AS avg_lifetime_spend,
  AVG(total_orders) AS avg_orders,
  AVG(days_since_last_purchase) AS avg_recency,
  AVG(purchase_frequency) AS avg_frequency,
  AVG(avg_order_value) AS avg_aov
FROM `ssi_shadow.user_features_lifetime`
WHERE total_orders > 0
GROUP BY rfm_segment
ORDER BY avg_lifetime_spend DESC;


-- Processing cost estimation
CREATE OR REPLACE VIEW `ssi_shadow.feature_processing_stats` AS
SELECT
  DATE(last_processed_at) AS process_date,
  COUNT(*) AS users_processed,
  SUM(total_orders) AS total_orders_in_system,
  SUM(total_spend) AS total_revenue_tracked
FROM `ssi_shadow.user_features_lifetime`
WHERE last_processed_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY 1
ORDER BY 1 DESC;


-- ============================================================================
-- SECTION 7: SCHEDULING
-- ============================================================================

/*
-- Cloud Scheduler Configuration (run via console or gcloud)

-- Option 1: BigQuery Scheduled Query (Console)
-- 1. Go to BigQuery Console > Scheduled Queries
-- 2. Create new scheduled query
-- 3. Query: CALL `project.ssi_shadow.update_features`();
-- 4. Schedule: 0 2 * * * (2:00 AM UTC daily)

-- Option 2: Cloud Scheduler + Cloud Functions
-- gcloud scheduler jobs create http feature-store-update \
--   --schedule="0 2 * * *" \
--   --uri="https://us-central1-PROJECT.cloudfunctions.net/update-features" \
--   --http-method=POST \
--   --time-zone="UTC"

-- Option 3: Using BigQuery Scripting with ASSERT for monitoring
-- This runs as a scheduled query with error handling:

DECLARE success BOOL DEFAULT FALSE;

BEGIN
  CALL `ssi_shadow.update_features`();
  SET success = TRUE;
EXCEPTION WHEN ERROR THEN
  -- Log error to a monitoring table
  INSERT INTO `ssi_shadow.processing_errors` (
    process_name,
    error_message,
    error_time
  ) VALUES (
    'update_features',
    @@error.message,
    CURRENT_TIMESTAMP()
  );
  -- Re-raise to fail the job
  RAISE;
END;

ASSERT success;
*/


-- ============================================================================
-- SECTION 8: EXAMPLE USAGE
-- ============================================================================

/*
-- Run daily update (for yesterday)
CALL `ssi_shadow.update_features`();

-- Run for specific date
CALL `ssi_shadow.update_features`(DATE '2024-12-26');

-- Backfill last 30 days (expensive!)
CALL `ssi_shadow.backfill_features`(
  DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY),
  DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
);

-- Get features for a specific user
DECLARE user_features STRUCT<...>;
CALL `ssi_shadow.get_user_features`('canonical_abc123', user_features);
SELECT user_features.*;

-- Check feature quality
SELECT * FROM `ssi_shadow.feature_quality_daily` LIMIT 7;

-- Check RFM segments
SELECT * FROM `ssi_shadow.feature_distribution`;

-- Export features for ML training
EXPORT DATA OPTIONS(
  uri='gs://bucket/ml-features/*.parquet',
  format='PARQUET',
  overwrite=true
) AS
SELECT *
FROM `ssi_shadow.user_features_lifetime`
WHERE last_seen_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY);
*/
