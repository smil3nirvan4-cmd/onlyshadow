-- ============================================================================
-- S.S.I. SHADOW - User Profiles Computation Procedure
-- ============================================================================
-- Computes RFM scores, LTV predictions, and user segments
-- Should run daily after stitch_identities
-- ============================================================================

CREATE OR REPLACE PROCEDURE `ssi_shadow.compute_user_profiles`()
BEGIN
  DECLARE run_id STRING DEFAULT GENERATE_UUID();
  DECLARE start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP();
  
  SELECT CONCAT('Starting user profile computation: ', run_id) AS log_message;

  -- ========================================================================
  -- STEP 1: Compute base metrics from events
  -- ========================================================================
  
  CREATE TEMP TABLE temp_user_metrics AS
  WITH event_metrics AS (
    SELECT
      COALESCE(canonical_id, ssi_id) AS user_id,
      
      -- Temporal
      MIN(event_time) AS first_seen,
      MAX(event_time) AS last_seen,
      
      -- Counts
      COUNT(DISTINCT session_id) AS total_sessions,
      COUNTIF(event_name = 'PageView') AS total_pageviews,
      COUNT(*) AS total_events,
      COUNTIF(event_name = 'Purchase') AS total_purchases,
      COUNTIF(event_name = 'Lead') AS total_leads,
      
      -- Revenue
      SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) AS total_revenue,
      AVG(CASE WHEN event_name = 'Purchase' AND value > 0 THEN value END) AS avg_order_value,
      MAX(CASE WHEN event_name = 'Purchase' THEN value END) AS max_order_value,
      MIN(CASE WHEN event_name = 'Purchase' AND value > 0 THEN value END) AS min_order_value,
      
      -- Engagement
      AVG(time_on_page) AS avg_time_on_page,
      AVG(scroll_depth) AS avg_scroll_depth,
      
      -- Trust
      AVG(trust_score) AS avg_trust_score,
      MIN(trust_score) AS min_trust_score,
      COUNTIF(trust_action = 'block') AS bot_sessions,
      COUNTIF(trust_action = 'allow') AS human_sessions,
      
      -- Identifiers
      ARRAY_AGG(DISTINCT ssi_id IGNORE NULLS) AS all_ssi_ids,
      ARRAY_AGG(DISTINCT email_hash IGNORE NULLS) AS all_email_hashes,
      ARRAY_AGG(DISTINCT phone_hash IGNORE NULLS) AS all_phone_hashes,
      
      -- Most recent identifiers
      ARRAY_AGG(ssi_id ORDER BY event_time DESC LIMIT 1)[OFFSET(0)] AS primary_ssi_id,
      ARRAY_AGG(email_hash IGNORE NULLS ORDER BY event_time DESC LIMIT 1)[SAFE_OFFSET(0)] AS primary_email_hash,
      ARRAY_AGG(phone_hash IGNORE NULLS ORDER BY event_time DESC LIMIT 1)[SAFE_OFFSET(0)] AS primary_phone_hash
      
    FROM `ssi_shadow.events_raw`
    WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
      AND (trust_action IS NULL OR trust_action != 'block')  -- Exclude blocked traffic
    GROUP BY user_id
  )
  SELECT
    *,
    DATE_DIFF(CURRENT_DATE(), DATE(first_seen), DAY) AS days_since_first_seen,
    DATE_DIFF(CURRENT_DATE(), DATE(last_seen), DAY) AS days_since_last_seen
  FROM event_metrics;

  SELECT CONCAT('Base metrics computed: ', (SELECT COUNT(*) FROM temp_user_metrics)) AS log_message;

  -- ========================================================================
  -- STEP 2: Compute RFM Scores (1-5 scale using NTILE)
  -- ========================================================================
  
  CREATE TEMP TABLE temp_rfm_scores AS
  SELECT
    user_id,
    
    -- Recency: Lower days = better (5)
    6 - NTILE(5) OVER (ORDER BY days_since_last_seen) AS rfm_recency_score,
    
    -- Frequency: Higher = better (5)
    NTILE(5) OVER (ORDER BY total_purchases) AS rfm_frequency_score,
    
    -- Monetary: Higher = better (5)
    NTILE(5) OVER (ORDER BY total_revenue) AS rfm_monetary_score
    
  FROM temp_user_metrics
  WHERE total_events > 0;

  -- ========================================================================
  -- STEP 3: Assign RFM Segments
  -- ========================================================================
  
  CREATE TEMP TABLE temp_rfm_segments AS
  SELECT
    user_id,
    rfm_recency_score,
    rfm_frequency_score,
    rfm_monetary_score,
    CONCAT(
      CAST(rfm_recency_score AS STRING),
      CAST(rfm_frequency_score AS STRING),
      CAST(rfm_monetary_score AS STRING)
    ) AS rfm_combined_score,
    CASE
      -- Champions: Best in all dimensions
      WHEN rfm_recency_score >= 4 AND rfm_frequency_score >= 4 AND rfm_monetary_score >= 4 
        THEN 'Champions'
      
      -- Loyal Customers: High frequency and monetary
      WHEN rfm_frequency_score >= 4 AND rfm_monetary_score >= 4 
        THEN 'Loyal Customers'
      
      -- Potential Loyalists: Recent, moderate frequency
      WHEN rfm_recency_score >= 4 AND rfm_frequency_score >= 3 
        THEN 'Potential Loyalists'
      
      -- Recent Customers: New customers
      WHEN rfm_recency_score >= 4 AND rfm_frequency_score <= 2 
        THEN 'Recent Customers'
      
      -- Promising: Medium in all
      WHEN rfm_recency_score >= 3 AND rfm_frequency_score >= 2 AND rfm_monetary_score >= 2 
        THEN 'Promising'
      
      -- Need Attention: Above average but slipping
      WHEN rfm_recency_score >= 3 AND rfm_frequency_score >= 3 
        THEN 'Need Attention'
      
      -- About to Sleep: Below average recency
      WHEN rfm_recency_score >= 2 AND rfm_recency_score <= 3 
        THEN 'About to Sleep'
      
      -- At Risk: High value but not recent
      WHEN rfm_monetary_score >= 4 AND rfm_recency_score <= 2 
        THEN 'At Risk'
      
      -- Cannot Lose Them: Very high value, very low recency
      WHEN rfm_monetary_score >= 4 AND rfm_recency_score = 1 
        THEN 'Cannot Lose Them'
      
      -- Hibernating: Low across the board
      WHEN rfm_recency_score <= 2 AND rfm_frequency_score <= 2 
        THEN 'Hibernating'
      
      -- Lost: Haven't been seen in a long time
      WHEN rfm_recency_score = 1 
        THEN 'Lost'
      
      ELSE 'Other'
    END AS rfm_segment
  FROM temp_rfm_scores;

  SELECT CONCAT('RFM segments computed: ', (SELECT COUNT(*) FROM temp_rfm_segments)) AS log_message;

  -- ========================================================================
  -- STEP 4: Compute Conversion Metrics
  -- ========================================================================
  
  CREATE TEMP TABLE temp_conversion_metrics AS
  WITH purchase_times AS (
    SELECT
      COALESCE(canonical_id, ssi_id) AS user_id,
      event_time AS purchase_time
    FROM `ssi_shadow.events_raw`
    WHERE event_name = 'Purchase'
      AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
  ),
  cart_events AS (
    SELECT
      COALESCE(canonical_id, ssi_id) AS user_id,
      COUNTIF(event_name = 'AddToCart') AS add_to_cart_count,
      COUNTIF(event_name = 'InitiateCheckout') AS checkout_count,
      COUNTIF(event_name = 'Purchase') AS purchase_count
    FROM `ssi_shadow.events_raw`
    WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
    GROUP BY user_id
  )
  SELECT
    c.user_id,
    SAFE_DIVIDE(c.purchase_count, NULLIF(c.add_to_cart_count, 0)) AS conversion_rate,
    1 - SAFE_DIVIDE(c.checkout_count, NULLIF(c.add_to_cart_count, 0)) AS cart_abandonment_rate,
    1 - SAFE_DIVIDE(c.purchase_count, NULLIF(c.checkout_count, 0)) AS checkout_abandonment_rate
  FROM cart_events c;

  -- ========================================================================
  -- STEP 5: Compute Device & Channel Data
  -- ========================================================================
  
  CREATE TEMP TABLE temp_device_data AS
  WITH device_sessions AS (
    SELECT
      COALESCE(canonical_id, ssi_id) AS user_id,
      CASE
        WHEN LOWER(user_agent) LIKE '%mobile%' OR LOWER(user_agent) LIKE '%android%' 
             OR LOWER(user_agent) LIKE '%iphone%' THEN 'mobile'
        WHEN LOWER(user_agent) LIKE '%tablet%' OR LOWER(user_agent) LIKE '%ipad%' THEN 'tablet'
        ELSE 'desktop'
      END AS device_type,
      MIN(event_time) AS first_seen,
      MAX(event_time) AS last_seen,
      COUNT(DISTINCT session_id) AS session_count
    FROM `ssi_shadow.events_raw`
    WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 365 DAY)
    GROUP BY user_id, device_type
  )
  SELECT
    user_id,
    COUNT(DISTINCT device_type) AS device_count,
    COUNT(DISTINCT device_type) > 1 AS is_multi_device,
    ARRAY_AGG(
      STRUCT(device_type, '' AS os, '' AS browser, first_seen, last_seen, session_count)
      ORDER BY session_count DESC
    ) AS devices,
    (
      SELECT device_type
      FROM device_sessions d2
      WHERE d2.user_id = device_sessions.user_id
      ORDER BY session_count DESC
      LIMIT 1
    ) AS primary_device_type
  FROM device_sessions
  GROUP BY user_id;

  -- ========================================================================
  -- STEP 6: Predict LTV (Simple model based on historical data)
  -- ========================================================================
  
  CREATE TEMP TABLE temp_ltv_predictions AS
  SELECT
    user_id,
    
    -- Simple LTV prediction: avg_order_value * expected_purchases
    -- Expected purchases = historical_rate * time_factor
    COALESCE(
      avg_order_value * (total_purchases / GREATEST(days_since_first_seen / 30.0, 1)) * 12,
      total_revenue * 1.5  -- Fallback: 1.5x historical revenue
    ) AS predicted_ltv,
    
    -- 30-day LTV
    COALESCE(
      avg_order_value * (total_purchases / GREATEST(days_since_first_seen / 30.0, 1)),
      total_revenue * 0.1
    ) AS predicted_ltv_30d,
    
    -- 90-day LTV
    COALESCE(
      avg_order_value * (total_purchases / GREATEST(days_since_first_seen / 30.0, 1)) * 3,
      total_revenue * 0.3
    ) AS predicted_ltv_90d,
    
    -- LTV Segment
    CASE
      WHEN total_revenue >= (SELECT APPROX_QUANTILES(total_revenue, 100)[OFFSET(90)] FROM temp_user_metrics)
        THEN 'high'
      WHEN total_revenue >= (SELECT APPROX_QUANTILES(total_revenue, 100)[OFFSET(50)] FROM temp_user_metrics)
        THEN 'medium'
      ELSE 'low'
    END AS ltv_segment,
    
    -- LTV Percentile
    CAST(NTILE(100) OVER (ORDER BY total_revenue) AS INT64) AS ltv_percentile,
    
    -- Churn probability (simple: based on recency)
    CASE
      WHEN days_since_last_seen > 90 THEN 0.8
      WHEN days_since_last_seen > 60 THEN 0.5
      WHEN days_since_last_seen > 30 THEN 0.3
      WHEN days_since_last_seen > 14 THEN 0.1
      ELSE 0.05
    END AS churn_probability,
    
    -- Churn risk
    CASE
      WHEN days_since_last_seen > 60 THEN 'high'
      WHEN days_since_last_seen > 30 THEN 'medium'
      ELSE 'low'
    END AS churn_risk
    
  FROM temp_user_metrics;

  -- ========================================================================
  -- STEP 7: Compute Customer Segments
  -- ========================================================================
  
  CREATE TEMP TABLE temp_customer_segments AS
  SELECT
    user_id,
    
    -- Customer type
    CASE
      WHEN days_since_first_seen <= 30 AND total_purchases <= 1 THEN 'new'
      WHEN total_purchases >= 3 THEN 'loyal'
      WHEN days_since_last_seen > 90 THEN 'churned'
      ELSE 'returning'
    END AS customer_type,
    
    -- Value segment
    CASE
      WHEN total_revenue >= (SELECT APPROX_QUANTILES(total_revenue, 100)[OFFSET(95)] FROM temp_user_metrics WHERE total_revenue > 0)
        THEN 'VIP'
      WHEN total_revenue >= (SELECT APPROX_QUANTILES(total_revenue, 100)[OFFSET(75)] FROM temp_user_metrics WHERE total_revenue > 0)
        THEN 'high_value'
      WHEN total_revenue >= (SELECT APPROX_QUANTILES(total_revenue, 100)[OFFSET(50)] FROM temp_user_metrics WHERE total_revenue > 0)
        THEN 'medium_value'
      ELSE 'low_value'
    END AS value_segment,
    
    -- Engagement segment
    CASE
      WHEN total_sessions >= 10 AND avg_scroll_depth >= 50 THEN 'highly_engaged'
      WHEN total_sessions >= 5 AND avg_scroll_depth >= 30 THEN 'engaged'
      WHEN total_sessions >= 2 THEN 'passive'
      ELSE 'dormant'
    END AS engagement_segment,
    
    -- Lifecycle stage
    CASE
      WHEN total_purchases = 0 AND total_pageviews <= 3 THEN 'awareness'
      WHEN total_purchases = 0 THEN 'consideration'
      WHEN total_purchases = 1 THEN 'purchase'
      WHEN total_purchases >= 2 AND days_since_last_seen <= 60 THEN 'retention'
      WHEN total_purchases >= 3 THEN 'advocacy'
      ELSE 'consideration'
    END AS lifecycle_stage
    
  FROM temp_user_metrics;

  -- ========================================================================
  -- STEP 8: Merge all data into user_profiles
  -- ========================================================================
  
  -- Delete existing profiles that will be updated
  DELETE FROM `ssi_shadow.user_profiles`
  WHERE canonical_id IN (SELECT user_id FROM temp_user_metrics);

  -- Insert updated profiles
  INSERT INTO `ssi_shadow.user_profiles` (
    canonical_id,
    primary_ssi_id,
    primary_email_hash,
    primary_phone_hash,
    all_ssi_ids,
    all_email_hashes,
    all_phone_hashes,
    first_seen,
    last_seen,
    days_since_first_seen,
    days_since_last_seen,
    total_sessions,
    total_pageviews,
    total_events,
    total_purchases,
    total_leads,
    total_revenue,
    avg_order_value,
    max_order_value,
    min_order_value,
    rfm_recency_score,
    rfm_frequency_score,
    rfm_monetary_score,
    rfm_combined_score,
    rfm_segment,
    avg_time_on_page,
    avg_scroll_depth,
    conversion_rate,
    cart_abandonment_rate,
    checkout_abandonment_rate,
    devices,
    primary_device_type,
    is_multi_device,
    device_count,
    predicted_ltv,
    predicted_ltv_30d,
    predicted_ltv_90d,
    ltv_segment,
    ltv_percentile,
    churn_probability,
    churn_risk,
    customer_type,
    value_segment,
    engagement_segment,
    lifecycle_stage,
    avg_trust_score,
    min_trust_score,
    bot_sessions,
    human_sessions,
    created_at,
    updated_at,
    last_computed
  )
  SELECT
    m.user_id AS canonical_id,
    m.primary_ssi_id,
    m.primary_email_hash,
    m.primary_phone_hash,
    m.all_ssi_ids,
    m.all_email_hashes,
    m.all_phone_hashes,
    m.first_seen,
    m.last_seen,
    m.days_since_first_seen,
    m.days_since_last_seen,
    m.total_sessions,
    m.total_pageviews,
    m.total_events,
    m.total_purchases,
    m.total_leads,
    m.total_revenue,
    m.avg_order_value,
    m.max_order_value,
    m.min_order_value,
    r.rfm_recency_score,
    r.rfm_frequency_score,
    r.rfm_monetary_score,
    r.rfm_combined_score,
    r.rfm_segment,
    CAST(m.avg_time_on_page AS INT64),
    m.avg_scroll_depth,
    c.conversion_rate,
    c.cart_abandonment_rate,
    c.checkout_abandonment_rate,
    d.devices,
    d.primary_device_type,
    d.is_multi_device,
    d.device_count,
    l.predicted_ltv,
    l.predicted_ltv_30d,
    l.predicted_ltv_90d,
    l.ltv_segment,
    l.ltv_percentile,
    l.churn_probability,
    l.churn_risk,
    s.customer_type,
    s.value_segment,
    s.engagement_segment,
    s.lifecycle_stage,
    m.avg_trust_score,
    m.min_trust_score,
    m.bot_sessions,
    m.human_sessions,
    CURRENT_TIMESTAMP(),
    CURRENT_TIMESTAMP(),
    CURRENT_TIMESTAMP()
  FROM temp_user_metrics m
  LEFT JOIN temp_rfm_segments r ON m.user_id = r.user_id
  LEFT JOIN temp_conversion_metrics c ON m.user_id = c.user_id
  LEFT JOIN temp_device_data d ON m.user_id = d.user_id
  LEFT JOIN temp_ltv_predictions l ON m.user_id = l.user_id
  LEFT JOIN temp_customer_segments s ON m.user_id = s.user_id;

  SELECT CONCAT('Profiles inserted/updated: ', @@row_count) AS log_message;

  -- ========================================================================
  -- Cleanup
  -- ========================================================================
  DROP TABLE IF EXISTS temp_user_metrics;
  DROP TABLE IF EXISTS temp_rfm_scores;
  DROP TABLE IF EXISTS temp_rfm_segments;
  DROP TABLE IF EXISTS temp_conversion_metrics;
  DROP TABLE IF EXISTS temp_device_data;
  DROP TABLE IF EXISTS temp_ltv_predictions;
  DROP TABLE IF EXISTS temp_customer_segments;

  SELECT CONCAT(
    'User profile computation completed. Run: ', run_id,
    ', Duration: ', TIMESTAMP_DIFF(CURRENT_TIMESTAMP(), start_time, SECOND), 's'
  ) AS log_message;

END;

-- ============================================================================
-- Schedule: Run daily after stitch_identities
-- ============================================================================
-- CALL `project.ssi_shadow.compute_user_profiles`();
