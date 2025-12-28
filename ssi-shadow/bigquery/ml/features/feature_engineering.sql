-- ============================================================================
-- S.S.I. SHADOW - Feature Engineering for ML Models
-- ============================================================================
-- Creates feature tables for LTV, Churn, and Propensity models
-- Run daily after user_profiles is computed
-- ============================================================================

-- ============================================================================
-- Feature Table: ml_features_ltv
-- ============================================================================
-- Features for LTV prediction model
-- ============================================================================

CREATE OR REPLACE TABLE `ssi_shadow.ml_features_ltv` AS
WITH 
-- Base user metrics from last 365 days
user_base AS (
  SELECT
    COALESCE(canonical_id, ssi_id) AS user_id,
    
    -- Temporal features
    MIN(event_time) AS first_event_time,
    MAX(event_time) AS last_event_time,
    DATE_DIFF(CURRENT_DATE(), DATE(MIN(event_time)), DAY) AS days_since_first_event,
    DATE_DIFF(CURRENT_DATE(), DATE(MAX(event_time)), DAY) AS days_since_last_event,
    DATE_DIFF(DATE(MAX(event_time)), DATE(MIN(event_time)), DAY) AS customer_tenure_days,
    
    -- Transaction features
    COUNTIF(event_name = 'Purchase') AS total_purchases,
    COUNTIF(event_name = 'Purchase' AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)) AS purchases_last_30d,
    COUNTIF(event_name = 'Purchase' AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)) AS purchases_last_90d,
    
    -- Revenue features
    SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) AS total_revenue,
    SUM(CASE WHEN event_name = 'Purchase' AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY) THEN value ELSE 0 END) AS revenue_last_30d,
    SUM(CASE WHEN event_name = 'Purchase' AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY) THEN value ELSE 0 END) AS revenue_last_90d,
    AVG(CASE WHEN event_name = 'Purchase' AND value > 0 THEN value END) AS avg_order_value,
    MAX(CASE WHEN event_name = 'Purchase' THEN value END) AS max_order_value,
    MIN(CASE WHEN event_name = 'Purchase' AND value > 0 THEN value END) AS min_order_value,
    STDDEV(CASE WHEN event_name = 'Purchase' AND value > 0 THEN value END) AS stddev_order_value,
    
    -- Engagement features
    COUNT(DISTINCT session_id) AS total_sessions,
    COUNTIF(event_name = 'PageView') AS total_pageviews,
    COUNT(*) AS total_events,
    AVG(scroll_depth) AS avg_scroll_depth,
    AVG(time_on_page) AS avg_time_on_page,
    
    -- Funnel features
    COUNTIF(event_name = 'ViewContent') AS view_content_count,
    COUNTIF(event_name = 'AddToCart') AS add_to_cart_count,
    COUNTIF(event_name = 'InitiateCheckout') AS checkout_count,
    
    -- Trust features
    AVG(trust_score) AS avg_trust_score,
    MIN(trust_score) AS min_trust_score
    
  FROM `ssi_shadow.events_raw`
  WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
    AND (trust_action IS NULL OR trust_action != 'block')
  GROUP BY user_id
),

-- Calculate derived features
derived_features AS (
  SELECT
    user_id,
    
    -- Base features
    days_since_first_event,
    days_since_last_event,
    customer_tenure_days,
    total_purchases,
    purchases_last_30d,
    purchases_last_90d,
    total_revenue,
    revenue_last_30d,
    revenue_last_90d,
    avg_order_value,
    max_order_value,
    min_order_value,
    COALESCE(stddev_order_value, 0) AS stddev_order_value,
    total_sessions,
    total_pageviews,
    total_events,
    COALESCE(avg_scroll_depth, 0) AS avg_scroll_depth,
    COALESCE(avg_time_on_page, 0) AS avg_time_on_page,
    view_content_count,
    add_to_cart_count,
    checkout_count,
    COALESCE(avg_trust_score, 0.5) AS avg_trust_score,
    
    -- Derived ratios
    SAFE_DIVIDE(total_purchases, GREATEST(customer_tenure_days, 1)) * 30 AS purchase_frequency_monthly,
    SAFE_DIVIDE(total_revenue, GREATEST(customer_tenure_days, 1)) * 30 AS revenue_per_month,
    SAFE_DIVIDE(total_pageviews, total_sessions) AS pages_per_session,
    SAFE_DIVIDE(total_events, total_sessions) AS events_per_session,
    SAFE_DIVIDE(add_to_cart_count, NULLIF(view_content_count, 0)) AS view_to_cart_rate,
    SAFE_DIVIDE(checkout_count, NULLIF(add_to_cart_count, 0)) AS cart_to_checkout_rate,
    SAFE_DIVIDE(total_purchases, NULLIF(checkout_count, 0)) AS checkout_to_purchase_rate,
    SAFE_DIVIDE(total_purchases, NULLIF(view_content_count, 0)) AS overall_conversion_rate,
    
    -- Recency score (exponential decay)
    EXP(-0.05 * days_since_last_event) AS recency_score,
    
    -- Revenue trend
    SAFE_DIVIDE(revenue_last_30d, NULLIF(revenue_last_90d - revenue_last_30d, 0) / 2) AS revenue_trend_30_vs_60,
    
    -- Is repeat buyer
    CASE WHEN total_purchases > 1 THEN 1 ELSE 0 END AS is_repeat_buyer,
    
    -- Customer segment (for stratification)
    CASE
      WHEN total_revenue = 0 THEN 'prospect'
      WHEN total_purchases = 1 THEN 'one_time'
      WHEN total_purchases <= 3 THEN 'occasional'
      ELSE 'frequent'
    END AS customer_segment

  FROM user_base
  WHERE customer_tenure_days >= 0  -- Sanity check
)

SELECT
  user_id,
  
  -- Temporal features (scaled)
  LEAST(days_since_first_event / 365.0, 1.0) AS tenure_normalized,
  LEAST(days_since_last_event / 90.0, 1.0) AS recency_normalized,
  recency_score,
  
  -- Transaction features
  total_purchases,
  purchases_last_30d,
  purchases_last_90d,
  LOG(1 + total_revenue) AS log_total_revenue,
  LOG(1 + revenue_last_30d) AS log_revenue_30d,
  LOG(1 + revenue_last_90d) AS log_revenue_90d,
  COALESCE(avg_order_value, 0) AS avg_order_value,
  COALESCE(max_order_value, 0) AS max_order_value,
  stddev_order_value,
  
  -- Engagement features
  LOG(1 + total_sessions) AS log_sessions,
  LOG(1 + total_pageviews) AS log_pageviews,
  LOG(1 + total_events) AS log_events,
  avg_scroll_depth / 100.0 AS scroll_depth_normalized,
  LEAST(avg_time_on_page / 300000.0, 1.0) AS time_on_page_normalized,  -- 5 min max
  
  -- Conversion features
  COALESCE(pages_per_session, 0) AS pages_per_session,
  COALESCE(events_per_session, 0) AS events_per_session,
  COALESCE(view_to_cart_rate, 0) AS view_to_cart_rate,
  COALESCE(cart_to_checkout_rate, 0) AS cart_to_checkout_rate,
  COALESCE(checkout_to_purchase_rate, 0) AS checkout_to_purchase_rate,
  COALESCE(overall_conversion_rate, 0) AS overall_conversion_rate,
  
  -- Derived features
  COALESCE(purchase_frequency_monthly, 0) AS purchase_frequency_monthly,
  COALESCE(revenue_per_month, 0) AS revenue_per_month,
  COALESCE(revenue_trend_30_vs_60, 1.0) AS revenue_trend,
  is_repeat_buyer,
  avg_trust_score,
  
  -- Segment
  customer_segment,
  
  -- Target variable: Next 90 days revenue (for training)
  -- This will be populated by a separate process for training data
  CAST(NULL AS FLOAT64) AS target_revenue_90d,
  
  -- Metadata
  CURRENT_TIMESTAMP() AS feature_timestamp

FROM derived_features
WHERE total_events > 0;  -- Only users with activity


-- ============================================================================
-- Feature Table: ml_features_churn
-- ============================================================================
-- Features for churn prediction model
-- ============================================================================

CREATE OR REPLACE TABLE `ssi_shadow.ml_features_churn` AS
WITH user_activity AS (
  SELECT
    COALESCE(canonical_id, ssi_id) AS user_id,
    
    -- Activity patterns
    DATE_DIFF(CURRENT_DATE(), DATE(MAX(event_time)), DAY) AS days_since_last_activity,
    COUNT(DISTINCT DATE(event_time)) AS active_days,
    COUNT(DISTINCT FORMAT_DATE('%Y-%W', DATE(event_time))) AS active_weeks,
    
    -- Activity by period
    COUNTIF(event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS events_last_7d,
    COUNTIF(event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)) AS events_last_14d,
    COUNTIF(event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)) AS events_last_30d,
    COUNTIF(event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)) AS events_last_60d,
    
    -- Session patterns
    COUNT(DISTINCT session_id) AS total_sessions,
    COUNT(DISTINCT CASE WHEN event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY) THEN session_id END) AS sessions_last_30d,
    
    -- Purchase patterns
    COUNTIF(event_name = 'Purchase') AS total_purchases,
    COUNTIF(event_name = 'Purchase' AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)) AS purchases_last_30d,
    MAX(CASE WHEN event_name = 'Purchase' THEN event_time END) AS last_purchase_time,
    
    -- Engagement
    AVG(scroll_depth) AS avg_scroll_depth,
    AVG(time_on_page) AS avg_time_on_page,
    
    -- Customer tenure
    DATE_DIFF(CURRENT_DATE(), DATE(MIN(event_time)), DAY) AS customer_age_days
    
  FROM `ssi_shadow.events_raw`
  WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
    AND (trust_action IS NULL OR trust_action != 'block')
  GROUP BY user_id
)

SELECT
  user_id,
  
  -- Recency features
  days_since_last_activity,
  CASE WHEN last_purchase_time IS NOT NULL 
       THEN DATE_DIFF(CURRENT_DATE(), DATE(last_purchase_time), DAY) 
       ELSE 999 END AS days_since_last_purchase,
  
  -- Activity frequency
  SAFE_DIVIDE(active_days, GREATEST(customer_age_days, 1)) AS activity_rate,
  SAFE_DIVIDE(active_weeks, GREATEST(customer_age_days / 7, 1)) AS weekly_activity_rate,
  
  -- Activity trend (declining = churn risk)
  SAFE_DIVIDE(events_last_7d, NULLIF((events_last_14d - events_last_7d), 0)) AS activity_trend_7d,
  SAFE_DIVIDE(events_last_30d, NULLIF((events_last_60d - events_last_30d), 0)) AS activity_trend_30d,
  SAFE_DIVIDE(sessions_last_30d, NULLIF(total_sessions - sessions_last_30d, 0) / 11) AS session_trend,
  
  -- Purchase behavior
  total_purchases,
  purchases_last_30d,
  CASE WHEN total_purchases > 0 THEN 1 ELSE 0 END AS has_purchased,
  
  -- Engagement quality
  COALESCE(avg_scroll_depth, 0) / 100.0 AS scroll_engagement,
  LEAST(COALESCE(avg_time_on_page, 0) / 60000.0, 5.0) AS time_engagement_minutes,
  
  -- Customer maturity
  LEAST(customer_age_days / 365.0, 1.0) AS customer_maturity,
  
  -- Risk indicators
  CASE WHEN days_since_last_activity > 30 THEN 1 ELSE 0 END AS inactive_30d,
  CASE WHEN days_since_last_activity > 60 THEN 1 ELSE 0 END AS inactive_60d,
  CASE WHEN events_last_30d < events_last_60d - events_last_30d THEN 1 ELSE 0 END AS declining_activity,
  
  -- Target: Churned in next 30 days (for training)
  -- A user is considered churned if no activity for 60+ days
  CAST(NULL AS INT64) AS target_churned,
  
  -- Metadata
  CURRENT_TIMESTAMP() AS feature_timestamp

FROM user_activity
WHERE customer_age_days >= 14;  -- At least 2 weeks of history


-- ============================================================================
-- Feature Table: ml_features_propensity
-- ============================================================================
-- Features for purchase propensity model (next 7 days)
-- ============================================================================

CREATE OR REPLACE TABLE `ssi_shadow.ml_features_propensity` AS
WITH recent_behavior AS (
  SELECT
    COALESCE(canonical_id, ssi_id) AS user_id,
    
    -- Recent activity (last 7 days focus)
    COUNTIF(event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS events_7d,
    COUNTIF(event_name = 'PageView' AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS pageviews_7d,
    COUNTIF(event_name = 'ViewContent' AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS product_views_7d,
    COUNTIF(event_name = 'AddToCart' AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS add_to_cart_7d,
    COUNTIF(event_name = 'InitiateCheckout' AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS checkout_7d,
    COUNTIF(event_name = 'Search' AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)) AS searches_7d,
    
    -- Recent sessions
    COUNT(DISTINCT CASE WHEN event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) THEN session_id END) AS sessions_7d,
    COUNT(DISTINCT CASE WHEN event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY) THEN session_id END) AS sessions_1d,
    
    -- Historical purchase behavior
    COUNTIF(event_name = 'Purchase') AS total_purchases,
    SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) AS total_revenue,
    
    -- Recency
    DATE_DIFF(CURRENT_DATE(), DATE(MAX(event_time)), DAY) AS days_since_last_activity,
    
    -- Engagement quality
    AVG(CASE WHEN event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) THEN scroll_depth END) AS avg_scroll_7d,
    AVG(CASE WHEN event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY) THEN time_on_page END) AS avg_time_7d
    
  FROM `ssi_shadow.events_raw`
  WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
    AND (trust_action IS NULL OR trust_action != 'block')
  GROUP BY user_id
  HAVING events_7d > 0  -- Active in last 7 days
)

SELECT
  user_id,
  
  -- Activity intensity
  events_7d,
  pageviews_7d,
  product_views_7d,
  sessions_7d,
  sessions_1d,
  
  -- Purchase intent signals
  add_to_cart_7d,
  checkout_7d,
  searches_7d,
  CASE WHEN add_to_cart_7d > 0 THEN 1 ELSE 0 END AS has_cart_activity,
  CASE WHEN checkout_7d > 0 THEN 1 ELSE 0 END AS has_checkout_activity,
  
  -- Funnel progression
  SAFE_DIVIDE(add_to_cart_7d, NULLIF(product_views_7d, 0)) AS view_to_cart_rate_7d,
  SAFE_DIVIDE(checkout_7d, NULLIF(add_to_cart_7d, 0)) AS cart_to_checkout_rate_7d,
  
  -- Historical behavior
  total_purchases,
  LOG(1 + total_revenue) AS log_revenue,
  CASE WHEN total_purchases > 0 THEN 1 ELSE 0 END AS is_customer,
  CASE WHEN total_purchases > 1 THEN 1 ELSE 0 END AS is_repeat_customer,
  
  -- Recency
  days_since_last_activity,
  CASE WHEN days_since_last_activity <= 1 THEN 1 ELSE 0 END AS active_today,
  
  -- Engagement
  COALESCE(avg_scroll_7d, 0) / 100.0 AS scroll_engagement,
  LEAST(COALESCE(avg_time_7d, 0) / 60000.0, 5.0) AS time_engagement,
  
  -- Combined intent score (rule-based)
  (CASE WHEN add_to_cart_7d > 0 THEN 0.3 ELSE 0 END +
   CASE WHEN checkout_7d > 0 THEN 0.4 ELSE 0 END +
   CASE WHEN product_views_7d > 3 THEN 0.1 ELSE 0 END +
   CASE WHEN sessions_7d > 2 THEN 0.1 ELSE 0 END +
   CASE WHEN total_purchases > 0 THEN 0.1 ELSE 0 END) AS rule_based_intent_score,
  
  -- Target: Purchased in next 7 days (for training)
  CAST(NULL AS INT64) AS target_purchased_7d,
  
  -- Metadata
  CURRENT_TIMESTAMP() AS feature_timestamp

FROM recent_behavior;


-- ============================================================================
-- Procedure: Prepare Training Data
-- ============================================================================
-- Creates training datasets with actual outcomes
-- Run on historical data for model training
-- ============================================================================

CREATE OR REPLACE PROCEDURE `ssi_shadow.prepare_training_data`(
  training_end_date DATE
)
BEGIN
  DECLARE training_start_date DATE DEFAULT DATE_SUB(training_end_date, INTERVAL 180 DAY);
  DECLARE outcome_window_days INT64 DEFAULT 90;
  
  -- LTV Training Data
  CREATE OR REPLACE TABLE `ssi_shadow.ml_training_ltv` AS
  WITH feature_snapshot AS (
    SELECT
      COALESCE(canonical_id, ssi_id) AS user_id,
      
      -- All features from ml_features_ltv logic
      -- ... (simplified for brevity)
      DATE_DIFF(training_end_date, DATE(MIN(event_time)), DAY) AS tenure_days,
      COUNTIF(event_name = 'Purchase') AS total_purchases,
      SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) AS total_revenue,
      COUNT(*) AS total_events
      
    FROM `ssi_shadow.events_raw`
    WHERE DATE(event_time) BETWEEN training_start_date AND training_end_date
    GROUP BY user_id
  ),
  outcomes AS (
    SELECT
      COALESCE(canonical_id, ssi_id) AS user_id,
      SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) AS actual_revenue_90d
    FROM `ssi_shadow.events_raw`
    WHERE DATE(event_time) BETWEEN training_end_date AND DATE_ADD(training_end_date, INTERVAL outcome_window_days DAY)
    GROUP BY user_id
  )
  SELECT
    f.*,
    COALESCE(o.actual_revenue_90d, 0) AS target_revenue_90d
  FROM feature_snapshot f
  LEFT JOIN outcomes o ON f.user_id = o.user_id;

  SELECT CONCAT('Training data prepared with ', 
                (SELECT COUNT(*) FROM `ssi_shadow.ml_training_ltv`), 
                ' records') AS status;
END;
