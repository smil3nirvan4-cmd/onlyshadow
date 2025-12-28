-- ============================================================================
-- S.S.I. SHADOW - Dashboard Views
-- ============================================================================
-- Materialized and standard views for dashboard and analytics
-- ============================================================================

-- ============================================================================
-- View: v_daily_events_summary
-- ============================================================================
-- Daily aggregation of events for high-level dashboards
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_daily_events_summary` AS
SELECT
  DATE(event_time) AS date,
  event_name,
  
  -- Volume
  COUNT(*) AS total_events,
  COUNT(DISTINCT ssi_id) AS unique_users,
  COUNT(DISTINCT session_id) AS unique_sessions,
  COUNT(DISTINCT canonical_id) AS resolved_users,
  
  -- Revenue
  SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) AS revenue,
  AVG(CASE WHEN event_name = 'Purchase' THEN value END) AS avg_order_value,
  
  -- Trust Score
  AVG(trust_score) AS avg_trust_score,
  COUNTIF(trust_action = 'block') AS blocked_events,
  COUNTIF(trust_action = 'allow') AS allowed_events,
  SAFE_DIVIDE(COUNTIF(trust_action = 'block'), COUNT(*)) AS block_rate,
  
  -- CAPI Status
  COUNTIF(meta_sent = TRUE) AS meta_sent_count,
  COUNTIF(google_sent = TRUE) AS google_sent_count,
  COUNTIF(tiktok_sent = TRUE) AS tiktok_sent_count,
  
  -- EMQ (Meta Event Match Quality estimate)
  COUNTIF(email_hash IS NOT NULL) AS events_with_email,
  COUNTIF(phone_hash IS NOT NULL) AS events_with_phone,
  COUNTIF(fbc IS NOT NULL) AS events_with_fbc,
  COUNTIF(fbp IS NOT NULL) AS events_with_fbp

FROM `ssi_shadow.events_raw`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
GROUP BY date, event_name;

-- ============================================================================
-- View: v_funnel_analysis
-- ============================================================================
-- E-commerce funnel analysis
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_funnel_analysis` AS
WITH user_funnel AS (
  SELECT
    DATE(event_time) AS date,
    COALESCE(canonical_id, ssi_id) AS user_id,
    MAX(CASE WHEN event_name = 'PageView' THEN 1 ELSE 0 END) AS has_pageview,
    MAX(CASE WHEN event_name = 'ViewContent' THEN 1 ELSE 0 END) AS has_view_content,
    MAX(CASE WHEN event_name = 'AddToCart' THEN 1 ELSE 0 END) AS has_add_to_cart,
    MAX(CASE WHEN event_name = 'InitiateCheckout' THEN 1 ELSE 0 END) AS has_checkout,
    MAX(CASE WHEN event_name = 'Purchase' THEN 1 ELSE 0 END) AS has_purchase,
    MAX(CASE WHEN event_name = 'Lead' THEN 1 ELSE 0 END) AS has_lead
  FROM `ssi_shadow.events_raw`
  WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
    AND (trust_action IS NULL OR trust_action != 'block')
  GROUP BY date, user_id
)
SELECT
  date,
  COUNT(DISTINCT user_id) AS total_users,
  SUM(has_pageview) AS pageview_users,
  SUM(has_view_content) AS view_content_users,
  SUM(has_add_to_cart) AS add_to_cart_users,
  SUM(has_checkout) AS checkout_users,
  SUM(has_purchase) AS purchase_users,
  SUM(has_lead) AS lead_users,
  
  -- Conversion rates
  SAFE_DIVIDE(SUM(has_view_content), SUM(has_pageview)) AS pageview_to_view_rate,
  SAFE_DIVIDE(SUM(has_add_to_cart), SUM(has_view_content)) AS view_to_cart_rate,
  SAFE_DIVIDE(SUM(has_checkout), SUM(has_add_to_cart)) AS cart_to_checkout_rate,
  SAFE_DIVIDE(SUM(has_purchase), SUM(has_checkout)) AS checkout_to_purchase_rate,
  SAFE_DIVIDE(SUM(has_purchase), SUM(has_pageview)) AS overall_conversion_rate
FROM user_funnel
GROUP BY date
ORDER BY date DESC;

-- ============================================================================
-- View: v_rfm_distribution
-- ============================================================================
-- RFM segment distribution
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_rfm_distribution` AS
SELECT
  rfm_segment,
  COUNT(*) AS user_count,
  SAFE_DIVIDE(COUNT(*), SUM(COUNT(*)) OVER()) AS percentage,
  AVG(total_revenue) AS avg_revenue,
  SUM(total_revenue) AS total_revenue,
  AVG(total_purchases) AS avg_purchases,
  AVG(days_since_last_seen) AS avg_recency_days,
  AVG(predicted_ltv) AS avg_predicted_ltv
FROM `ssi_shadow.user_profiles`
GROUP BY rfm_segment
ORDER BY total_revenue DESC;

-- ============================================================================
-- View: v_ltv_segments
-- ============================================================================
-- LTV segment analysis
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_ltv_segments` AS
SELECT
  ltv_segment,
  COUNT(*) AS user_count,
  AVG(predicted_ltv) AS avg_predicted_ltv,
  SUM(predicted_ltv) AS total_predicted_ltv,
  AVG(total_revenue) AS avg_historical_revenue,
  SUM(total_revenue) AS total_historical_revenue,
  AVG(total_purchases) AS avg_purchases,
  AVG(churn_probability) AS avg_churn_probability
FROM `ssi_shadow.user_profiles`
GROUP BY ltv_segment
ORDER BY avg_predicted_ltv DESC;

-- ============================================================================
-- View: v_identity_resolution_stats
-- ============================================================================
-- Identity resolution statistics
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_identity_resolution_stats` AS
SELECT
  COUNT(DISTINCT canonical_id) AS total_resolved_users,
  COUNT(DISTINCT linked_id) AS total_identifiers,
  AVG(
    SELECT COUNT(*) FROM `ssi_shadow.identity_graph` ig2 
    WHERE ig2.canonical_id = ig.canonical_id
  ) AS avg_identifiers_per_user,
  COUNTIF(match_type = 'deterministic') AS deterministic_matches,
  COUNTIF(match_type LIKE 'probabilistic%') AS probabilistic_matches,
  AVG(match_confidence) AS avg_confidence,
  
  -- Match sources
  COUNTIF(match_source = 'email_match') AS email_matches,
  COUNTIF(match_source = 'phone_match') AS phone_matches,
  COUNTIF(match_source = 'fbp_match') AS fbp_matches,
  COUNTIF(match_source = 'session_match') AS session_matches

FROM `ssi_shadow.identity_graph` ig
WHERE is_active = TRUE;

-- ============================================================================
-- View: v_bot_detection_stats
-- ============================================================================
-- Bot detection and trust score statistics
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_bot_detection_stats` AS
SELECT
  DATE(event_time) AS date,
  
  -- Volume
  COUNT(*) AS total_events,
  COUNTIF(trust_action = 'block') AS blocked_events,
  COUNTIF(trust_action = 'challenge') AS challenged_events,
  COUNTIF(trust_action = 'allow') AS allowed_events,
  
  -- Rates
  SAFE_DIVIDE(COUNTIF(trust_action = 'block'), COUNT(*)) AS block_rate,
  SAFE_DIVIDE(COUNTIF(trust_action = 'challenge'), COUNT(*)) AS challenge_rate,
  
  -- Trust score distribution
  AVG(trust_score) AS avg_trust_score,
  APPROX_QUANTILES(trust_score, 4)[OFFSET(1)] AS trust_score_25th,
  APPROX_QUANTILES(trust_score, 4)[OFFSET(2)] AS trust_score_median,
  APPROX_QUANTILES(trust_score, 4)[OFFSET(3)] AS trust_score_75th,
  
  -- Common flags (from trust_flags array)
  COUNTIF('bot_user_agent' IN UNNEST(trust_flags)) AS bot_ua_count,
  COUNTIF('datacenter_ip' IN UNNEST(trust_flags)) AS datacenter_ip_count,
  COUNTIF('headless_browser' IN UNNEST(trust_flags)) AS headless_count,
  COUNTIF('rate_limited' IN UNNEST(trust_flags)) AS rate_limited_count

FROM `ssi_shadow.events_raw`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY date
ORDER BY date DESC;

-- ============================================================================
-- View: v_capi_delivery_stats
-- ============================================================================
-- CAPI delivery statistics
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_capi_delivery_stats` AS
SELECT
  DATE(event_time) AS date,
  event_name,
  
  -- Meta
  COUNTIF(meta_sent = TRUE) AS meta_sent,
  COUNTIF(meta_sent = FALSE OR meta_sent IS NULL) AS meta_not_sent,
  SAFE_DIVIDE(COUNTIF(meta_sent = TRUE), COUNT(*)) AS meta_delivery_rate,
  AVG(CASE WHEN meta_sent THEN meta_response_code END) AS meta_avg_response_code,
  
  -- Google
  COUNTIF(google_sent = TRUE) AS google_sent,
  SAFE_DIVIDE(COUNTIF(google_sent = TRUE), COUNT(*)) AS google_delivery_rate,
  
  -- TikTok
  COUNTIF(tiktok_sent = TRUE) AS tiktok_sent,
  SAFE_DIVIDE(COUNTIF(tiktok_sent = TRUE), COUNT(*)) AS tiktok_delivery_rate,
  
  -- EMQ Estimation
  AVG(
    CASE 
      WHEN email_hash IS NOT NULL THEN 3 ELSE 0 END +
      CASE WHEN phone_hash IS NOT NULL THEN 2 ELSE 0 END +
      CASE WHEN fbc IS NOT NULL THEN 2 ELSE 0 END +
      CASE WHEN fbp IS NOT NULL THEN 1 ELSE 0 END +
      CASE WHEN external_id IS NOT NULL THEN 1 ELSE 0 END
  ) AS avg_emq_score

FROM `ssi_shadow.events_raw`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY date, event_name
ORDER BY date DESC, event_name;

-- ============================================================================
-- View: v_multi_device_users
-- ============================================================================
-- Multi-device user analysis
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_multi_device_users` AS
SELECT
  is_multi_device,
  COUNT(*) AS user_count,
  AVG(device_count) AS avg_devices,
  AVG(total_revenue) AS avg_revenue,
  AVG(total_purchases) AS avg_purchases,
  AVG(predicted_ltv) AS avg_ltv,
  AVG(conversion_rate) AS avg_conversion_rate
FROM `ssi_shadow.user_profiles`
GROUP BY is_multi_device;

-- ============================================================================
-- View: v_cohort_analysis
-- ============================================================================
-- Weekly cohort retention analysis
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_cohort_analysis` AS
WITH user_cohorts AS (
  SELECT
    COALESCE(canonical_id, ssi_id) AS user_id,
    DATE_TRUNC(DATE(MIN(event_time)), WEEK) AS cohort_week,
    DATE_TRUNC(DATE(event_time), WEEK) AS activity_week
  FROM `ssi_shadow.events_raw`
  WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
  GROUP BY user_id, activity_week
)
SELECT
  cohort_week,
  activity_week,
  DATE_DIFF(activity_week, cohort_week, WEEK) AS weeks_since_cohort,
  COUNT(DISTINCT user_id) AS active_users,
  (
    SELECT COUNT(DISTINCT user_id)
    FROM user_cohorts uc2
    WHERE uc2.cohort_week = user_cohorts.cohort_week
      AND uc2.activity_week = uc2.cohort_week
  ) AS cohort_size,
  SAFE_DIVIDE(
    COUNT(DISTINCT user_id),
    (
      SELECT COUNT(DISTINCT user_id)
      FROM user_cohorts uc2
      WHERE uc2.cohort_week = user_cohorts.cohort_week
        AND uc2.activity_week = uc2.cohort_week
    )
  ) AS retention_rate
FROM user_cohorts
GROUP BY cohort_week, activity_week
ORDER BY cohort_week DESC, activity_week;

-- ============================================================================
-- View: v_high_value_at_risk
-- ============================================================================
-- High-value users at risk of churning (for remarketing)
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_high_value_at_risk` AS
SELECT
  canonical_id,
  primary_email_hash,
  primary_phone_hash,
  rfm_segment,
  ltv_segment,
  churn_risk,
  churn_probability,
  total_revenue,
  predicted_ltv,
  days_since_last_seen,
  total_purchases,
  avg_order_value
FROM `ssi_shadow.user_profiles`
WHERE ltv_segment IN ('high', 'VIP')
  AND churn_risk IN ('high', 'medium')
ORDER BY predicted_ltv DESC;

-- ============================================================================
-- View: v_audience_segments_meta
-- ============================================================================
-- Segments formatted for Meta Custom Audiences export
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_audience_segments_meta` AS
SELECT
  canonical_id,
  primary_email_hash AS em,
  primary_phone_hash AS ph,
  rfm_segment,
  ltv_segment,
  churn_risk,
  
  -- Segment flags for audience building
  CASE WHEN rfm_segment = 'Champions' THEN TRUE ELSE FALSE END AS is_champion,
  CASE WHEN rfm_segment IN ('At Risk', 'Cannot Lose Them') THEN TRUE ELSE FALSE END AS is_at_risk,
  CASE WHEN ltv_segment IN ('high', 'VIP') THEN TRUE ELSE FALSE END AS is_high_value,
  CASE WHEN customer_type = 'new' THEN TRUE ELSE FALSE END AS is_new_customer,
  CASE WHEN total_purchases = 0 THEN TRUE ELSE FALSE END AS is_prospect,
  CASE WHEN total_purchases >= 3 THEN TRUE ELSE FALSE END AS is_repeat_buyer
  
FROM `ssi_shadow.user_profiles`
WHERE primary_email_hash IS NOT NULL OR primary_phone_hash IS NOT NULL;
