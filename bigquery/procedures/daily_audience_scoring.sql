-- ============================================================================
-- S.S.I. SHADOW - DAILY AUDIENCE SCORING (Scheduled Query)
-- ============================================================================
--
-- Purpose: Score all active users daily for marketing audience segmentation
--
-- Schedule: Daily at 3:00 AM UTC (after feature store update at 2:00 AM)
--
-- Output: `ssi_shadow.marketing_audiences` table with LTV tiers
--
-- Tiers:
--   💎 Diamond   - Top 5% predicted LTV (highest value customers)
--   🥇 Gold      - Top 6-20% predicted LTV (high value)
--   🥈 Silver    - Top 21-50% predicted LTV (medium value)
--   🥉 Bronze    - Bottom 50% predicted LTV (lower value)
--   ⚠️  Churn Risk - High churn probability or low recency
--
-- Usage: Export tiers to ad platforms for targeted campaigns
--
-- Author: SSI Shadow Marketing Engineering Team
-- Version: 1.0.0
-- ============================================================================


-- ============================================================================
-- SECTION 1: CREATE TARGET TABLE (Run once)
-- ============================================================================

CREATE TABLE IF NOT EXISTS `ssi_shadow.marketing_audiences` (
  -- Identity
  canonical_id STRING NOT NULL OPTIONS(description="Unique user identifier"),
  
  -- LTV Prediction
  predicted_ltv_90d FLOAT64 OPTIONS(description="Predicted revenue next 90 days"),
  ltv_percentile INT64 OPTIONS(description="LTV percentile rank (1-100)"),
  
  -- Tier Classification
  tier STRING NOT NULL OPTIONS(description="Diamond, Gold, Silver, Bronze, Churn_Risk"),
  tier_rank INT64 OPTIONS(description="Rank within tier"),
  
  -- Churn Signals
  churn_probability FLOAT64 OPTIONS(description="Probability of churn 0-1"),
  is_churn_risk BOOL DEFAULT FALSE OPTIONS(description="Flagged as churn risk"),
  churn_risk_reason STRING OPTIONS(description="Why flagged as churn risk"),
  
  -- User Context (for ad targeting)
  days_since_last_purchase INT64 OPTIONS(description="Recency in days"),
  days_since_last_visit INT64 OPTIONS(description="Days since last site visit"),
  total_lifetime_spend FLOAT64 OPTIONS(description="Historical total spend"),
  purchase_count INT64 OPTIONS(description="Total purchases"),
  avg_order_value FLOAT64 OPTIONS(description="Average order value"),
  
  -- Behavioral Signals
  engagement_score FLOAT64 OPTIONS(description="Recent engagement intensity"),
  purchase_intent_score FLOAT64 OPTIONS(description="Purchase intent signal"),
  cart_abandonment_rate FLOAT64 OPTIONS(description="Cart abandonment rate"),
  
  -- Channel & Device
  primary_channel STRING OPTIONS(description="Primary acquisition channel"),
  primary_device STRING OPTIONS(description="Primary device type"),
  
  -- Recommended Actions
  recommended_campaign STRING OPTIONS(description="Suggested campaign type"),
  recommended_offer STRING OPTIONS(description="Suggested offer type"),
  
  -- Platform Export IDs
  email_hash STRING OPTIONS(description="Hashed email for matching"),
  phone_hash STRING OPTIONS(description="Hashed phone for matching"),
  
  -- Metadata
  scored_at TIMESTAMP NOT NULL OPTIONS(description="When this score was generated"),
  score_version STRING DEFAULT 'v1.0' OPTIONS(description="Scoring model version"),
  valid_until TIMESTAMP OPTIONS(description="Score expiration (next day)")
)
PARTITION BY DATE(scored_at)
CLUSTER BY tier, primary_channel
OPTIONS (
  description = 'Daily user scoring for marketing audiences - partitioned by score date, clustered by tier',
  labels = [('team', 'marketing'), ('purpose', 'audiences')],
  partition_expiration_days = 90  -- Keep 90 days of history
);


-- ============================================================================
-- SECTION 2: SCHEDULED QUERY - DAILY SCORING
-- ============================================================================
-- 
-- To schedule this query:
-- 1. Go to BigQuery Console > Scheduled Queries
-- 2. Click "Create Scheduled Query"
-- 3. Paste this query
-- 4. Set schedule: 0 3 * * * (3:00 AM UTC daily)
-- 5. Set destination table: ssi_shadow.marketing_audiences
-- 6. Write preference: WRITE_TRUNCATE (replace partition)
-- ============================================================================

-- Begin Daily Scoring Query
DECLARE score_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP();
DECLARE score_date DATE DEFAULT CURRENT_DATE();
DECLARE valid_until_timestamp TIMESTAMP DEFAULT TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 1 DAY);

-- Delete today's scores if re-running (idempotent)
DELETE FROM `ssi_shadow.marketing_audiences`
WHERE DATE(scored_at) = score_date;

-- Main scoring query
INSERT INTO `ssi_shadow.marketing_audiences` (
  canonical_id,
  predicted_ltv_90d,
  ltv_percentile,
  tier,
  tier_rank,
  churn_probability,
  is_churn_risk,
  churn_risk_reason,
  days_since_last_purchase,
  days_since_last_visit,
  total_lifetime_spend,
  purchase_count,
  avg_order_value,
  engagement_score,
  purchase_intent_score,
  cart_abandonment_rate,
  primary_channel,
  primary_device,
  recommended_campaign,
  recommended_offer,
  email_hash,
  phone_hash,
  scored_at,
  score_version,
  valid_until
)

WITH
-- ============================================================================
-- Step 1: Select Active Users (last 30 days)
-- ============================================================================
active_users AS (
  SELECT
    l.canonical_id,
    l.days_since_last_purchase,
    l.days_since_last_seen AS days_since_last_visit,
    l.total_spend AS total_lifetime_spend,
    l.total_orders AS purchase_count,
    l.avg_order_value,
    l.cart_to_purchase_rate,
    l.checkout_to_purchase_rate,
    l.spend_velocity_7d,
    l.spend_velocity_30d,
    l.engagement_trend,
    l.purchase_trend,
    l.primary_channel,
    l.primary_device,
    l.avg_trust_score,
    l.visits_7d,
    l.spend_7d,
    l.orders_7d,
    l.rfm_segment,
    
    -- Engagement intensity score
    COALESCE(l.visits_7d * 0.3 + l.spend_7d * 0.001 * 0.4 + l.orders_7d * 10 * 0.3, 0) 
      AS engagement_score,
    
    -- Purchase intent (from behavioral features)
    COALESCE(
      (SELECT SUM(daily_product_views) FROM `ssi_shadow.user_features_daily` d 
       WHERE d.canonical_id = l.canonical_id 
         AND d.feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)) * 0.2 +
      COALESCE(l.cart_to_purchase_rate, 0) * 100 * 0.4 +
      COALESCE(l.checkout_to_purchase_rate, 0) * 100 * 0.4,
      0
    ) AS purchase_intent_score,
    
    -- Cart abandonment
    1 - COALESCE(l.cart_to_purchase_rate, 0) AS cart_abandonment_rate
    
  FROM `ssi_shadow.user_features_lifetime` l
  WHERE 
    -- Active in last 30 days (visited OR purchased)
    (l.days_since_last_seen <= 30 OR l.days_since_last_purchase <= 30)
    -- Quality filter
    AND COALESCE(l.avg_trust_score, 1.0) >= 0.3
),

-- ============================================================================
-- Step 2: Get Email/Phone Hashes for Ad Platform Matching
-- ============================================================================
user_identifiers AS (
  SELECT
    COALESCE(canonical_id, ssi_id) AS canonical_id,
    -- Get most recent email/phone hash
    ARRAY_AGG(email_hash IGNORE NULLS ORDER BY event_time DESC LIMIT 1)[SAFE_OFFSET(0)] AS email_hash,
    ARRAY_AGG(phone_hash IGNORE NULLS ORDER BY event_time DESC LIMIT 1)[SAFE_OFFSET(0)] AS phone_hash
  FROM `ssi_shadow.events_raw`
  WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
    AND (email_hash IS NOT NULL OR phone_hash IS NOT NULL)
  GROUP BY 1
),

-- ============================================================================
-- Step 3: Prepare Features for ML.PREDICT
-- ============================================================================
features_for_prediction AS (
  SELECT
    au.canonical_id,
    
    -- RFM Features
    COALESCE(au.total_lifetime_spend, 0) AS lifetime_spend,
    COALESCE(au.purchase_count, 0) AS purchase_count,
    COALESCE(au.days_since_last_purchase, 999) AS days_since_last_order,
    COALESCE(au.avg_order_value, 0) AS avg_order_value,
    0.0 AS max_order_value,  -- Will be filled if available
    SAFE_DIVIDE(au.purchase_count, 
                NULLIF(DATE_DIFF(CURRENT_DATE(), 
                       DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY), DAY), 0)) * 30 
      AS purchases_per_month,
    COALESCE(au.days_since_last_visit, 0) AS days_since_last_visit,
    
    -- Behavioral Features
    COALESCE(
      (SELECT AVG(daily_time_on_site) FROM `ssi_shadow.user_features_daily` d
       WHERE d.canonical_id = au.canonical_id
         AND d.feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)),
      0
    ) AS avg_session_duration,
    COALESCE(
      (SELECT AVG(daily_pageviews / NULLIF(daily_visits, 0)) 
       FROM `ssi_shadow.user_features_daily` d
       WHERE d.canonical_id = au.canonical_id
         AND d.feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)),
      0
    ) AS pages_per_session,
    50.0 AS avg_scroll_depth,  -- Default
    
    -- Recent Activity
    COALESCE(au.visits_7d, 0) AS visits_last_7d,
    COALESCE(
      (SELECT SUM(daily_product_views) FROM `ssi_shadow.user_features_daily` d
       WHERE d.canonical_id = au.canonical_id
         AND d.feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)),
      0
    ) AS product_views_last_7d,
    COALESCE(
      (SELECT SUM(daily_category_views) FROM `ssi_shadow.user_features_daily` d
       WHERE d.canonical_id = au.canonical_id
         AND d.feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)),
      0
    ) AS category_views_last_7d,
    COALESCE(
      (SELECT SUM(daily_search_count) FROM `ssi_shadow.user_features_daily` d
       WHERE d.canonical_id = au.canonical_id
         AND d.feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)),
      0
    ) AS searches_last_7d,
    
    -- Cart & Funnel
    au.cart_abandonment_rate,
    COALESCE(au.cart_to_purchase_rate, 0) AS cart_conversion_rate,
    COALESCE(au.checkout_to_purchase_rate, 0) AS checkout_conversion_rate,
    0 AS total_add_to_carts,  -- Will be filled if available
    
    -- Velocity
    COALESCE(au.spend_velocity_7d, 0) AS spend_velocity_7d,
    COALESCE(au.spend_velocity_30d, 0) AS spend_velocity_30d,
    0.0 AS spend_acceleration,  -- Will be calculated
    
    -- Categorical
    COALESCE(au.engagement_trend, 'stable') AS engagement_trend,
    COALESCE(au.purchase_trend, 'stable') AS purchase_trend,
    COALESCE(au.primary_channel, 'direct') AS primary_channel,
    
    -- Context
    0.5 AS mobile_share,  -- Default
    COALESCE(au.avg_trust_score, 1.0) AS avg_trust_score,
    
    -- Derived (simplified)
    au.engagement_score AS engagement_intensity_7d,
    au.purchase_intent_score,
    COALESCE(au.avg_order_value, 0) AS recency_weighted_aov,
    SAFE_DIVIDE(
      COALESCE(
        (SELECT SUM(daily_product_views) FROM `ssi_shadow.user_features_daily` d
         WHERE d.canonical_id = au.canonical_id
           AND d.feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)), 0),
      NULLIF(COALESCE(au.orders_7d, 0) + 0.1, 0)
    ) AS browse_to_buy_ratio,
    IF(au.days_since_last_purchase <= 30, 1, 0) AS is_active_buyer,
    IF(
      COALESCE(
        (SELECT SUM(daily_product_views) FROM `ssi_shadow.user_features_daily` d
         WHERE d.canonical_id = au.canonical_id
           AND d.feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)), 0) > 10 
      AND COALESCE(au.orders_7d, 0) = 0, 
      1, 0
    ) AS is_high_intent_browser,
    1 AS momentum_score,  -- Default stable
    
    -- Pass-through for later
    au.total_lifetime_spend AS _total_spend,
    au.purchase_count AS _purchase_count,
    au.days_since_last_purchase AS _days_since_purchase,
    au.days_since_last_visit AS _days_since_visit,
    au.avg_order_value AS _aov,
    au.engagement_score AS _engagement_score,
    au.purchase_intent_score AS _intent_score,
    au.cart_abandonment_rate AS _cart_abandonment,
    au.primary_channel AS _channel,
    au.primary_device AS _device,
    au.rfm_segment AS _rfm_segment
    
  FROM active_users au
),

-- ============================================================================
-- Step 4: Run ML.PREDICT for LTV
-- ============================================================================
ltv_predictions AS (
  SELECT
    canonical_id,
    -- Convert log prediction back to actual value
    EXP(predicted_log_revenue_90d) - 1 AS predicted_ltv_90d,
    
    -- Pass through features
    _total_spend,
    _purchase_count,
    _days_since_purchase,
    _days_since_visit,
    _aov,
    _engagement_score,
    _intent_score,
    _cart_abandonment,
    _channel,
    _device,
    _rfm_segment
    
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_ltv_behavioral_v2`,
    (SELECT * FROM features_for_prediction)
  )
),

-- ============================================================================
-- Step 5: Calculate Churn Probability
-- ============================================================================
churn_signals AS (
  SELECT
    p.canonical_id,
    p.predicted_ltv_90d,
    p._total_spend,
    p._purchase_count,
    p._days_since_purchase,
    p._days_since_visit,
    p._aov,
    p._engagement_score,
    p._intent_score,
    p._cart_abandonment,
    p._channel,
    p._device,
    p._rfm_segment,
    
    -- Churn probability estimation (heuristic if no churn model)
    -- Higher probability = more likely to churn
    CASE
      -- Very high risk: No visit in 21+ days AND declining engagement
      WHEN p._days_since_visit > 21 AND p._engagement_score < 5 THEN 0.9
      -- High risk: No purchase in 60+ days for buyers
      WHEN p._purchase_count > 0 AND p._days_since_purchase > 60 THEN 0.75
      -- Medium-high: No visit in 14+ days
      WHEN p._days_since_visit > 14 THEN 0.6
      -- Medium: Declining from active buyer
      WHEN p._purchase_count > 3 AND p._days_since_purchase > 45 THEN 0.5
      -- Low-medium: Some inactivity
      WHEN p._days_since_visit > 7 THEN 0.3
      -- Low: Recent activity
      ELSE 0.1
    END AS churn_probability,
    
    -- Churn risk flag
    CASE
      WHEN p._days_since_visit > 21 THEN TRUE
      WHEN p._purchase_count > 0 AND p._days_since_purchase > 60 THEN TRUE
      WHEN p._rfm_segment IN ('Hibernating', 'Lost', 'At Risk', 'Cannot Lose Them') THEN TRUE
      ELSE FALSE
    END AS is_churn_risk,
    
    -- Churn reason
    CASE
      WHEN p._days_since_visit > 21 THEN 'no_visit_21d'
      WHEN p._purchase_count > 0 AND p._days_since_purchase > 60 THEN 'no_purchase_60d'
      WHEN p._rfm_segment = 'Cannot Lose Them' THEN 'high_value_at_risk'
      WHEN p._rfm_segment = 'At Risk' THEN 'rfm_at_risk'
      WHEN p._rfm_segment = 'Hibernating' THEN 'rfm_hibernating'
      WHEN p._rfm_segment = 'Lost' THEN 'rfm_lost'
      ELSE NULL
    END AS churn_risk_reason
    
  FROM ltv_predictions p
),

-- ============================================================================
-- Step 6: Calculate Percentiles & Assign Tiers
-- ============================================================================
with_percentiles AS (
  SELECT
    c.*,
    
    -- Calculate percentile (1-100, higher = better)
    NTILE(100) OVER (ORDER BY c.predicted_ltv_90d ASC) AS ltv_percentile,
    
    -- Rank within potential tier
    ROW_NUMBER() OVER (ORDER BY c.predicted_ltv_90d DESC) AS overall_rank
    
  FROM churn_signals c
),

with_tiers AS (
  SELECT
    p.*,
    
    -- Assign tier based on percentile (churn risk overrides)
    CASE
      -- Churn risk takes priority for at-risk valuable customers
      WHEN p.is_churn_risk AND p._total_spend > 0 THEN 'Churn_Risk'
      -- Diamond: Top 5% (percentile 96-100)
      WHEN p.ltv_percentile >= 96 THEN 'Diamond'
      -- Gold: Top 6-20% (percentile 81-95)
      WHEN p.ltv_percentile >= 81 THEN 'Gold'
      -- Silver: Top 21-50% (percentile 51-80)
      WHEN p.ltv_percentile >= 51 THEN 'Silver'
      -- Bronze: Bottom 50% (percentile 1-50)
      ELSE 'Bronze'
    END AS tier,
    
    -- Rank within tier
    ROW_NUMBER() OVER (
      PARTITION BY CASE
        WHEN p.is_churn_risk AND p._total_spend > 0 THEN 'Churn_Risk'
        WHEN p.ltv_percentile >= 96 THEN 'Diamond'
        WHEN p.ltv_percentile >= 81 THEN 'Gold'
        WHEN p.ltv_percentile >= 51 THEN 'Silver'
        ELSE 'Bronze'
      END
      ORDER BY p.predicted_ltv_90d DESC
    ) AS tier_rank
    
  FROM with_percentiles p
),

-- ============================================================================
-- Step 7: Generate Recommendations
-- ============================================================================
with_recommendations AS (
  SELECT
    t.*,
    
    -- Recommended campaign based on tier and signals
    CASE
      -- Churn risk campaigns
      WHEN t.tier = 'Churn_Risk' AND t._total_spend >= 500 
        THEN 'vip_win_back'
      WHEN t.tier = 'Churn_Risk' 
        THEN 're_engagement'
      
      -- Diamond campaigns
      WHEN t.tier = 'Diamond' AND t._cart_abandonment > 0.5 
        THEN 'cart_recovery_vip'
      WHEN t.tier = 'Diamond' 
        THEN 'loyalty_exclusive'
      
      -- Gold campaigns
      WHEN t.tier = 'Gold' AND t._intent_score > 50 
        THEN 'conversion_push'
      WHEN t.tier = 'Gold' 
        THEN 'upsell_cross_sell'
      
      -- Silver campaigns
      WHEN t.tier = 'Silver' AND t._purchase_count = 0 
        THEN 'first_purchase_incentive'
      WHEN t.tier = 'Silver' 
        THEN 'engagement_nurture'
      
      -- Bronze campaigns
      WHEN t.tier = 'Bronze' AND t._engagement_score > 20 
        THEN 'activation'
      ELSE 'awareness'
    END AS recommended_campaign,
    
    -- Recommended offer
    CASE
      -- High value at risk
      WHEN t.tier = 'Churn_Risk' AND t._total_spend >= 500 
        THEN 'exclusive_30_percent_off'
      WHEN t.tier = 'Churn_Risk' 
        THEN 'come_back_20_percent'
      
      -- Diamond (exclusive perks, not discounts)
      WHEN t.tier = 'Diamond' 
        THEN 'early_access_new_arrivals'
      
      -- Gold (moderate incentives)
      WHEN t.tier = 'Gold' AND t._cart_abandonment > 0.5 
        THEN 'free_shipping'
      WHEN t.tier = 'Gold' 
        THEN 'points_multiplier_2x'
      
      -- Silver (conversion focused)
      WHEN t.tier = 'Silver' AND t._purchase_count = 0 
        THEN 'first_order_15_percent'
      WHEN t.tier = 'Silver' 
        THEN 'bundle_deal'
      
      -- Bronze (awareness)
      ELSE 'welcome_10_percent'
    END AS recommended_offer
    
  FROM with_tiers t
)

-- ============================================================================
-- Final SELECT: Combine all data
-- ============================================================================
SELECT
  r.canonical_id,
  r.predicted_ltv_90d,
  r.ltv_percentile,
  r.tier,
  r.tier_rank,
  r.churn_probability,
  r.is_churn_risk,
  r.churn_risk_reason,
  CAST(r._days_since_purchase AS INT64) AS days_since_last_purchase,
  CAST(r._days_since_visit AS INT64) AS days_since_last_visit,
  r._total_spend AS total_lifetime_spend,
  CAST(r._purchase_count AS INT64) AS purchase_count,
  r._aov AS avg_order_value,
  r._engagement_score AS engagement_score,
  r._intent_score AS purchase_intent_score,
  r._cart_abandonment AS cart_abandonment_rate,
  r._channel AS primary_channel,
  r._device AS primary_device,
  r.recommended_campaign,
  r.recommended_offer,
  ui.email_hash,
  ui.phone_hash,
  score_timestamp AS scored_at,
  'v1.0' AS score_version,
  valid_until_timestamp AS valid_until

FROM with_recommendations r
LEFT JOIN user_identifiers ui ON r.canonical_id = ui.canonical_id;


-- ============================================================================
-- SECTION 3: POST-SCORING ANALYTICS VIEWS
-- ============================================================================

-- View: Tier Distribution Summary
CREATE OR REPLACE VIEW `ssi_shadow.v_audience_tier_summary` AS
SELECT
  DATE(scored_at) AS score_date,
  tier,
  COUNT(*) AS user_count,
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (PARTITION BY DATE(scored_at)), 2) AS pct_of_total,
  ROUND(AVG(predicted_ltv_90d), 2) AS avg_predicted_ltv,
  ROUND(SUM(predicted_ltv_90d), 2) AS total_predicted_ltv,
  ROUND(AVG(total_lifetime_spend), 2) AS avg_historical_spend,
  ROUND(AVG(churn_probability), 3) AS avg_churn_probability,
  COUNTIF(email_hash IS NOT NULL) AS with_email,
  COUNTIF(phone_hash IS NOT NULL) AS with_phone
FROM `ssi_shadow.marketing_audiences`
WHERE DATE(scored_at) = CURRENT_DATE()
GROUP BY 1, 2
ORDER BY 
  CASE tier 
    WHEN 'Diamond' THEN 1 
    WHEN 'Gold' THEN 2 
    WHEN 'Silver' THEN 3 
    WHEN 'Bronze' THEN 4 
    WHEN 'Churn_Risk' THEN 5 
  END;


-- View: Campaign Recommendations Summary
CREATE OR REPLACE VIEW `ssi_shadow.v_campaign_recommendations` AS
SELECT
  DATE(scored_at) AS score_date,
  tier,
  recommended_campaign,
  recommended_offer,
  COUNT(*) AS audience_size,
  ROUND(SUM(predicted_ltv_90d), 2) AS total_potential_ltv,
  COUNTIF(email_hash IS NOT NULL) AS targetable_by_email,
  COUNTIF(phone_hash IS NOT NULL) AS targetable_by_phone
FROM `ssi_shadow.marketing_audiences`
WHERE DATE(scored_at) = CURRENT_DATE()
GROUP BY 1, 2, 3, 4
ORDER BY tier, audience_size DESC;


-- View: Daily Tier Movement (for monitoring)
CREATE OR REPLACE VIEW `ssi_shadow.v_tier_movement` AS
WITH today AS (
  SELECT canonical_id, tier AS tier_today, predicted_ltv_90d AS ltv_today
  FROM `ssi_shadow.marketing_audiences`
  WHERE DATE(scored_at) = CURRENT_DATE()
),
yesterday AS (
  SELECT canonical_id, tier AS tier_yesterday, predicted_ltv_90d AS ltv_yesterday
  FROM `ssi_shadow.marketing_audiences`
  WHERE DATE(scored_at) = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
)
SELECT
  COALESCE(t.tier_today, 'Churned') AS tier_today,
  COALESCE(y.tier_yesterday, 'New') AS tier_yesterday,
  COUNT(*) AS user_count,
  ROUND(AVG(t.ltv_today - COALESCE(y.ltv_yesterday, 0)), 2) AS avg_ltv_change
FROM today t
FULL OUTER JOIN yesterday y ON t.canonical_id = y.canonical_id
GROUP BY 1, 2
ORDER BY 1, 2;


-- ============================================================================
-- SECTION 4: EXPORT QUERIES (for Ad Platforms)
-- ============================================================================

-- Export Diamond users to Meta Custom Audience
-- Run: bq extract --destination_format=CSV
CREATE OR REPLACE VIEW `ssi_shadow.export_meta_diamond` AS
SELECT
  email_hash AS email,  -- SHA256 hashed
  phone_hash AS phone   -- SHA256 hashed
FROM `ssi_shadow.marketing_audiences`
WHERE DATE(scored_at) = CURRENT_DATE()
  AND tier = 'Diamond'
  AND (email_hash IS NOT NULL OR phone_hash IS NOT NULL);


-- Export Gold users
CREATE OR REPLACE VIEW `ssi_shadow.export_meta_gold` AS
SELECT email_hash AS email, phone_hash AS phone
FROM `ssi_shadow.marketing_audiences`
WHERE DATE(scored_at) = CURRENT_DATE()
  AND tier = 'Gold'
  AND (email_hash IS NOT NULL OR phone_hash IS NOT NULL);


-- Export Churn Risk for win-back campaigns
CREATE OR REPLACE VIEW `ssi_shadow.export_meta_churn_risk` AS
SELECT 
  email_hash AS email, 
  phone_hash AS phone,
  total_lifetime_spend AS value  -- For value-based lookalikes
FROM `ssi_shadow.marketing_audiences`
WHERE DATE(scored_at) = CURRENT_DATE()
  AND tier = 'Churn_Risk'
  AND total_lifetime_spend > 0
  AND (email_hash IS NOT NULL OR phone_hash IS NOT NULL);


-- Export all tiers with metadata (for Google Ads Customer Match)
CREATE OR REPLACE VIEW `ssi_shadow.export_google_all_tiers` AS
SELECT
  email_hash AS Email,
  phone_hash AS Phone,
  tier AS Tier,
  CAST(predicted_ltv_90d AS STRING) AS ConversionValue
FROM `ssi_shadow.marketing_audiences`
WHERE DATE(scored_at) = CURRENT_DATE()
  AND (email_hash IS NOT NULL OR phone_hash IS NOT NULL);


-- ============================================================================
-- SECTION 5: STORED PROCEDURE FOR MANUAL RUNS
-- ============================================================================

CREATE OR REPLACE PROCEDURE `ssi_shadow.score_marketing_audiences`()
BEGIN
  -- This procedure wraps the daily scoring query
  -- Usage: CALL `ssi_shadow.score_marketing_audiences`();
  
  DECLARE score_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP();
  DECLARE rows_scored INT64;
  
  -- Log start
  SELECT CONCAT('Starting audience scoring at ', CAST(score_timestamp AS STRING));
  
  -- Delete existing scores for today
  DELETE FROM `ssi_shadow.marketing_audiences`
  WHERE DATE(scored_at) = CURRENT_DATE();
  
  -- Insert new scores (same query as above, simplified for procedure)
  INSERT INTO `ssi_shadow.marketing_audiences`
  SELECT
    canonical_id,
    predicted_ltv_90d,
    ltv_percentile,
    tier,
    tier_rank,
    churn_probability,
    is_churn_risk,
    churn_risk_reason,
    days_since_last_purchase,
    days_since_last_visit,
    total_lifetime_spend,
    purchase_count,
    avg_order_value,
    engagement_score,
    purchase_intent_score,
    cart_abandonment_rate,
    primary_channel,
    primary_device,
    recommended_campaign,
    recommended_offer,
    email_hash,
    phone_hash,
    CURRENT_TIMESTAMP() AS scored_at,
    'v1.0' AS score_version,
    TIMESTAMP_ADD(CURRENT_TIMESTAMP(), INTERVAL 1 DAY) AS valid_until
  FROM `ssi_shadow.v_scoring_intermediate`; -- Would need to create this view
  
  SET rows_scored = @@row_count;
  
  SELECT CONCAT('Scored ', CAST(rows_scored AS STRING), ' users');
  
END;


-- ============================================================================
-- SECTION 6: MONITORING & ALERTS
-- ============================================================================

-- Alert: Scoring job didn't run
CREATE OR REPLACE VIEW `ssi_shadow.alert_scoring_missing` AS
SELECT
  CURRENT_DATE() AS check_date,
  CASE
    WHEN NOT EXISTS (
      SELECT 1 FROM `ssi_shadow.marketing_audiences`
      WHERE DATE(scored_at) = CURRENT_DATE()
    ) THEN 'CRITICAL: No scores for today!'
    WHEN (
      SELECT COUNT(*) FROM `ssi_shadow.marketing_audiences`
      WHERE DATE(scored_at) = CURRENT_DATE()
    ) < 1000 THEN 'WARNING: Low score count today'
    ELSE 'OK'
  END AS status;


-- Alert: Tier distribution anomaly
CREATE OR REPLACE VIEW `ssi_shadow.alert_tier_anomaly` AS
WITH today_dist AS (
  SELECT tier, COUNT(*) AS cnt
  FROM `ssi_shadow.marketing_audiences`
  WHERE DATE(scored_at) = CURRENT_DATE()
  GROUP BY tier
),
yesterday_dist AS (
  SELECT tier, COUNT(*) AS cnt
  FROM `ssi_shadow.marketing_audiences`
  WHERE DATE(scored_at) = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
  GROUP BY tier
)
SELECT
  t.tier,
  t.cnt AS today_count,
  y.cnt AS yesterday_count,
  ROUND((t.cnt - y.cnt) * 100.0 / NULLIF(y.cnt, 0), 2) AS pct_change,
  CASE
    WHEN ABS((t.cnt - y.cnt) * 100.0 / NULLIF(y.cnt, 0)) > 20 
      THEN 'WARNING: >20% change'
    ELSE 'OK'
  END AS status
FROM today_dist t
LEFT JOIN yesterday_dist y ON t.tier = y.tier;


-- ============================================================================
-- USAGE EXAMPLES
-- ============================================================================

/*
-- 1. Run scoring manually
CALL `ssi_shadow.score_marketing_audiences`();

-- 2. Check tier distribution
SELECT * FROM `ssi_shadow.v_audience_tier_summary`;

-- 3. Get Diamond users for export
SELECT * FROM `ssi_shadow.export_meta_diamond`;

-- 4. Check tier movements
SELECT * FROM `ssi_shadow.v_tier_movement`;

-- 5. Get campaign recommendations
SELECT * FROM `ssi_shadow.v_campaign_recommendations`;

-- 6. Export to GCS for ad platforms
EXPORT DATA OPTIONS(
  uri='gs://ssi-shadow-audiences/diamond/*.csv',
  format='CSV',
  overwrite=true
) AS
SELECT * FROM `ssi_shadow.export_meta_diamond`;

-- 7. Query specific tier with clustering benefit
SELECT * 
FROM `ssi_shadow.marketing_audiences`
WHERE tier = 'Diamond'
  AND DATE(scored_at) = CURRENT_DATE();
-- (Clustering by tier makes this query very fast!)
*/


-- ============================================================================
-- SCHEDULING CONFIGURATION
-- ============================================================================

/*
BigQuery Scheduled Query Setup:

1. Name: daily_audience_scoring
2. Schedule: 0 3 * * * (3:00 AM UTC)
3. Query: [The INSERT query from Section 2]
4. Destination: 
   - Project: your-project
   - Dataset: ssi_shadow
   - Table: marketing_audiences
   - Write preference: WRITE_APPEND (or use DELETE + INSERT for idempotency)

5. Service Account: bigquery-scheduler@your-project.iam.gserviceaccount.com
   Required roles:
   - BigQuery Data Editor
   - BigQuery Job User

Alternative: Cloud Scheduler + Cloud Functions
gcloud scheduler jobs create http audience-scoring \
  --schedule="0 3 * * *" \
  --uri="https://us-central1-PROJECT.cloudfunctions.net/score-audiences" \
  --http-method=POST \
  --time-zone="UTC"
*/
