-- ============================================================================
-- S.S.I. SHADOW - ADVANCED LTV MODEL WITH BEHAVIORAL FEATURES
-- ============================================================================
--
-- Purpose: Predict 90-day revenue using RFM + Behavioral signals
--
-- Innovation: Traditional LTV models use only RFM (Recency, Frequency, Monetary)
-- This model adds BEHAVIORAL features to capture purchase INTENT:
--   - Session duration patterns
--   - Product browsing intensity
--   - Cart abandonment behavior
--   - Engagement velocity
--
-- The hypothesis is that browsing behavior predicts future purchases better
-- than historical purchases alone, especially for:
--   - New customers (low RFM data)
--   - Customers about to churn (behavior changes before purchases stop)
--   - High-intent browsers (lots of research before big purchases)
--
-- Author: SSI Shadow ML Team
-- Version: 2.0.0
-- ============================================================================


-- ============================================================================
-- SECTION 1: TRAINING DATA PREPARATION
-- ============================================================================

-- Create training dataset with behavioral features
CREATE OR REPLACE TABLE `ssi_shadow.ml_training_ltv_behavioral` AS
WITH
-- Base: Users with at least 30 days of history
users_base AS (
  SELECT
    canonical_id,
    MIN(first_seen_date) AS first_seen_date,
    MAX(last_seen_date) AS last_seen_date,
    DATE_DIFF(CURRENT_DATE(), MIN(first_seen_date), DAY) AS tenure_days
  FROM `ssi_shadow.user_features_lifetime`
  WHERE first_seen_date <= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)  -- Need 90d lookahead
  GROUP BY canonical_id
  HAVING tenure_days >= 30
),

-- RFM Features (Traditional)
rfm_features AS (
  SELECT
    l.canonical_id,
    
    -- Monetary
    COALESCE(l.total_spend, 0) AS lifetime_spend,
    COALESCE(l.avg_order_value, 0) AS avg_order_value,
    COALESCE(l.max_order_value, 0) AS max_order_value,
    
    -- Frequency
    COALESCE(l.total_orders, 0) AS purchase_count,
    COALESCE(l.purchase_frequency, 0) AS purchase_frequency,
    SAFE_DIVIDE(l.total_orders, NULLIF(DATE_DIFF(CURRENT_DATE(), l.first_purchase_date, DAY), 0)) * 30 AS purchases_per_month,
    
    -- Recency
    COALESCE(l.days_since_last_purchase, 999) AS days_since_last_order,
    COALESCE(l.days_since_last_seen, 0) AS days_since_last_visit,
    l.first_purchase_date,
    l.last_purchase_date
    
  FROM `ssi_shadow.user_features_lifetime` l
  JOIN users_base u ON l.canonical_id = u.canonical_id
),

-- Behavioral Features (The Innovation!)
behavioral_features AS (
  SELECT
    l.canonical_id,
    
    -- Session Behavior (Engagement Depth)
    COALESCE(l.avg_time_per_visit, 0) AS avg_session_duration,
    COALESCE(l.avg_pages_per_visit, 0) AS pages_per_session,
    COALESCE(l.avg_scroll_depth, 0) AS avg_scroll_depth,
    
    -- Recent Activity (Last 7 days - Recency Signal)
    COALESCE(l.visits_7d, 0) AS visits_last_7d,
    COALESCE(l.spend_7d, 0) AS spend_last_7d,
    COALESCE(l.orders_7d, 0) AS orders_last_7d,
    
    -- Product Interest (Intent Signal)
    COALESCE(d.product_views_7d, 0) AS product_views_last_7d,
    COALESCE(d.category_views_7d, 0) AS category_views_last_7d,
    COALESCE(d.search_count_7d, 0) AS searches_last_7d,
    
    -- Cart Behavior (Purchase Intent)
    COALESCE(l.total_add_to_carts, 0) AS total_add_to_carts,
    COALESCE(l.cart_to_purchase_rate, 0) AS cart_conversion_rate,
    -- Cart abandonment = 1 - cart_to_purchase_rate
    1 - COALESCE(l.cart_to_purchase_rate, 0) AS cart_abandonment_rate,
    
    -- Checkout Behavior
    COALESCE(l.total_checkouts_started, 0) AS checkouts_started,
    COALESCE(l.checkout_to_purchase_rate, 0) AS checkout_conversion_rate,
    
    -- Velocity (Engagement Trend)
    COALESCE(l.spend_velocity_7d, 0) AS spend_velocity_7d,
    COALESCE(l.spend_velocity_30d, 0) AS spend_velocity_30d,
    COALESCE(l.spend_acceleration, 0) AS spend_acceleration,
    
    -- Engagement Trend (Categorical)
    COALESCE(l.engagement_trend, 'stable') AS engagement_trend,
    COALESCE(l.purchase_trend, 'stable') AS purchase_trend,
    
    -- Device & Channel (Context)
    COALESCE(l.mobile_share, 0) AS mobile_share,
    l.primary_channel,
    l.is_multi_device,
    
    -- Trust (Quality Signal)
    COALESCE(l.avg_trust_score, 1.0) AS avg_trust_score
    
  FROM `ssi_shadow.user_features_lifetime` l
  JOIN users_base u ON l.canonical_id = u.canonical_id
  LEFT JOIN (
    -- 7-day product engagement from daily features
    SELECT
      canonical_id,
      SUM(daily_product_views) AS product_views_7d,
      SUM(daily_category_views) AS category_views_7d,
      SUM(daily_search_count) AS search_count_7d
    FROM `ssi_shadow.user_features_daily`
    WHERE feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 97 DAY)  -- 90d ago + 7d
      AND feature_date < DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)   -- Before lookahead
    GROUP BY canonical_id
  ) d ON l.canonical_id = d.canonical_id
),

-- Target: Revenue in the NEXT 90 days
target_revenue AS (
  SELECT
    canonical_id,
    SUM(daily_spend) AS revenue_90d
  FROM `ssi_shadow.user_features_daily`
  WHERE feature_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    AND feature_date < CURRENT_DATE()
  GROUP BY canonical_id
),

-- Derived Features (Ratios & Interactions)
derived_features AS (
  SELECT
    r.canonical_id,
    
    -- Engagement Intensity Score
    (COALESCE(b.visits_last_7d, 0) * 0.3 + 
     COALESCE(b.product_views_last_7d, 0) * 0.4 + 
     COALESCE(b.searches_last_7d, 0) * 0.3) AS engagement_intensity_7d,
    
    -- Purchase Intent Score (behavioral signals)
    (COALESCE(b.product_views_last_7d, 0) * 0.2 +
     COALESCE(1 - b.cart_abandonment_rate, 0) * 100 * 0.4 +
     COALESCE(b.checkout_conversion_rate, 0) * 100 * 0.4) AS purchase_intent_score,
    
    -- Recency-Weighted AOV
    SAFE_DIVIDE(
      COALESCE(b.spend_last_7d, 0) * 4 + COALESCE(r.lifetime_spend, 0),
      COALESCE(b.orders_last_7d, 0) * 4 + COALESCE(r.purchase_count, 0)
    ) AS recency_weighted_aov,
    
    -- Browse-to-Buy Ratio (how much research before purchase)
    SAFE_DIVIDE(b.product_views_last_7d, NULLIF(b.orders_last_7d + 0.1, 0)) AS browse_to_buy_ratio,
    
    -- Is Active Buyer (bought in last 30 days)
    IF(r.days_since_last_order <= 30, 1, 0) AS is_active_buyer,
    
    -- Is High Intent (lots of browsing, few purchases)
    IF(b.product_views_last_7d > 10 AND b.orders_last_7d = 0, 1, 0) AS is_high_intent_browser,
    
    -- Momentum Score (acceleration direction)
    CASE 
      WHEN b.spend_acceleration > 0.1 THEN 2   -- Accelerating
      WHEN b.spend_acceleration < -0.1 THEN 0  -- Decelerating
      ELSE 1                                    -- Stable
    END AS momentum_score
    
  FROM rfm_features r
  JOIN behavioral_features b ON r.canonical_id = b.canonical_id
)

-- Final Training Dataset
SELECT
  -- Identity (not used in training)
  r.canonical_id,
  
  -- ========================================================================
  -- RFM FEATURES (Traditional)
  -- ========================================================================
  r.lifetime_spend,
  r.purchase_count,
  r.days_since_last_order,
  r.avg_order_value,
  r.max_order_value,
  r.purchases_per_month,
  r.days_since_last_visit,
  
  -- ========================================================================
  -- BEHAVIORAL FEATURES (The Innovation!)
  -- ========================================================================
  -- Session Engagement
  b.avg_session_duration,
  b.pages_per_session,
  b.avg_scroll_depth,
  
  -- Recent Activity
  b.visits_last_7d,
  b.product_views_last_7d,
  b.category_views_last_7d,
  b.searches_last_7d,
  
  -- Cart & Checkout Behavior
  b.cart_abandonment_rate,
  b.cart_conversion_rate,
  b.checkout_conversion_rate,
  b.total_add_to_carts,
  
  -- Velocity & Trends
  b.spend_velocity_7d,
  b.spend_velocity_30d,
  b.spend_acceleration,
  b.engagement_trend,
  b.purchase_trend,
  
  -- Context
  b.mobile_share,
  b.primary_channel,
  b.avg_trust_score,
  
  -- ========================================================================
  -- DERIVED FEATURES (Interactions)
  -- ========================================================================
  d.engagement_intensity_7d,
  d.purchase_intent_score,
  d.recency_weighted_aov,
  d.browse_to_buy_ratio,
  d.is_active_buyer,
  d.is_high_intent_browser,
  d.momentum_score,
  
  -- ========================================================================
  -- TARGET
  -- ========================================================================
  COALESCE(t.revenue_90d, 0) AS revenue_90d

FROM rfm_features r
JOIN behavioral_features b ON r.canonical_id = b.canonical_id
JOIN derived_features d ON r.canonical_id = d.canonical_id
LEFT JOIN target_revenue t ON r.canonical_id = t.canonical_id;


-- ============================================================================
-- SECTION 2: MODEL CREATION WITH TRANSFORM
-- ============================================================================

CREATE OR REPLACE MODEL `ssi_shadow.model_ltv_behavioral_v2`

-- ============================================================================
-- TRANSFORM: Automatic Feature Preprocessing
-- Min-Max scaling normalizes features to [0,1] range
-- This improves model convergence and interpretability
-- ============================================================================
TRANSFORM(
  -- Pass through identity (excluded from training)
  canonical_id,
  
  -- ========================================================================
  -- RFM FEATURES - Normalized
  -- ========================================================================
  -- Monetary: Log transform + MinMax (handles right skew)
  ML.MIN_MAX_SCALER(LOG1P(lifetime_spend)) OVER() AS lifetime_spend_norm,
  ML.MIN_MAX_SCALER(LOG1P(avg_order_value)) OVER() AS aov_norm,
  ML.MIN_MAX_SCALER(LOG1P(max_order_value)) OVER() AS max_order_norm,
  
  -- Frequency: MinMax scaling
  ML.MIN_MAX_SCALER(purchase_count) OVER() AS purchase_count_norm,
  ML.MIN_MAX_SCALER(purchases_per_month) OVER() AS purchases_per_month_norm,
  
  -- Recency: Inverse transform (lower is better)
  ML.MIN_MAX_SCALER(1.0 / (1.0 + days_since_last_order)) OVER() AS recency_score,
  ML.MIN_MAX_SCALER(1.0 / (1.0 + days_since_last_visit)) OVER() AS visit_recency_score,
  
  -- ========================================================================
  -- BEHAVIORAL FEATURES - Normalized
  -- ========================================================================
  -- Session Engagement
  ML.MIN_MAX_SCALER(LOG1P(avg_session_duration)) OVER() AS session_duration_norm,
  ML.MIN_MAX_SCALER(pages_per_session) OVER() AS pages_per_session_norm,
  ML.MIN_MAX_SCALER(avg_scroll_depth / 100.0) OVER() AS scroll_depth_norm,
  
  -- Recent Activity (Critical for intent!)
  ML.MIN_MAX_SCALER(LOG1P(visits_last_7d)) OVER() AS visits_7d_norm,
  ML.MIN_MAX_SCALER(LOG1P(product_views_last_7d)) OVER() AS product_views_7d_norm,
  ML.MIN_MAX_SCALER(LOG1P(category_views_last_7d)) OVER() AS category_views_7d_norm,
  ML.MIN_MAX_SCALER(LOG1P(searches_last_7d)) OVER() AS searches_7d_norm,
  
  -- Cart Behavior (Already 0-1 range, but ensure bounds)
  ML.MIN_MAX_SCALER(cart_abandonment_rate) OVER() AS cart_abandonment_norm,
  ML.MIN_MAX_SCALER(cart_conversion_rate) OVER() AS cart_conversion_norm,
  ML.MIN_MAX_SCALER(checkout_conversion_rate) OVER() AS checkout_conversion_norm,
  ML.MIN_MAX_SCALER(LOG1P(total_add_to_carts)) OVER() AS add_to_carts_norm,
  
  -- Velocity Features (Can be negative, use StandardScaler approach)
  ML.MIN_MAX_SCALER(spend_velocity_7d) OVER() AS velocity_7d_norm,
  ML.MIN_MAX_SCALER(spend_velocity_30d) OVER() AS velocity_30d_norm,
  ML.MIN_MAX_SCALER(spend_acceleration + 10) OVER() AS acceleration_norm,  -- Shift to positive
  
  -- Categorical: One-hot encoding handled automatically
  engagement_trend,
  purchase_trend,
  primary_channel,
  
  -- Context
  mobile_share AS mobile_share,  -- Already 0-1
  avg_trust_score AS trust_score,  -- Already 0-1
  
  -- ========================================================================
  -- DERIVED FEATURES - Normalized
  -- ========================================================================
  ML.MIN_MAX_SCALER(LOG1P(engagement_intensity_7d)) OVER() AS engagement_intensity_norm,
  ML.MIN_MAX_SCALER(purchase_intent_score) OVER() AS purchase_intent_norm,
  ML.MIN_MAX_SCALER(LOG1P(recency_weighted_aov)) OVER() AS rw_aov_norm,
  ML.MIN_MAX_SCALER(LOG1P(browse_to_buy_ratio)) OVER() AS browse_buy_ratio_norm,
  
  -- Binary flags (no transformation needed)
  is_active_buyer,
  is_high_intent_browser,
  momentum_score,
  
  -- ========================================================================
  -- TARGET (Log transform for better regression on skewed data)
  -- ========================================================================
  LOG1P(revenue_90d) AS log_revenue_90d
)

-- ============================================================================
-- MODEL OPTIONS
-- ============================================================================
OPTIONS (
  -- Model Type: Gradient Boosted Trees (best for tabular data)
  model_type = 'BOOSTED_TREE_REGRESSOR',
  
  -- Target Column
  input_label_cols = ['log_revenue_90d'],
  
  -- ========================================================================
  -- HYPERPARAMETERS (Tuned for this use case)
  -- ========================================================================
  -- Tree structure
  num_parallel_tree = 5,        -- Number of trees built in parallel (like Random Forest)
  max_tree_depth = 8,           -- Deeper trees capture more interactions
  min_tree_child_weight = 10,   -- Minimum samples per leaf (prevents overfitting)
  
  -- Learning
  learn_rate = 0.05,            -- Lower rate = more trees needed but better generalization
  max_iterations = 200,         -- More iterations since lower learn rate
  
  -- Regularization (prevents overfitting)
  l1_reg = 0.5,                 -- L1 regularization (feature selection)
  l2_reg = 1.0,                 -- L2 regularization (weight decay)
  
  -- Sampling (reduces overfitting)
  subsample = 0.8,              -- Use 80% of data per tree
  colsample_bytree = 0.8,       -- Use 80% of features per tree
  colsample_bylevel = 0.8,      -- Use 80% of features per level
  
  -- ========================================================================
  -- TRAINING SETTINGS
  -- ========================================================================
  early_stop = TRUE,
  min_rel_progress = 0.001,
  
  -- Data split for evaluation
  data_split_method = 'RANDOM',
  data_split_eval_fraction = 0.2,
  
  -- ========================================================================
  -- EXPLAINABILITY (Critical for understanding!)
  -- ========================================================================
  enable_global_explain = TRUE
  
) AS

-- ============================================================================
-- TRAINING DATA SELECTION
-- ============================================================================
SELECT
  *
FROM `ssi_shadow.ml_training_ltv_behavioral`
WHERE 
  -- Quality filters
  purchase_count > 0 OR visits_last_7d > 0  -- Has some activity
  AND avg_trust_score >= 0.3;                -- Not a bot


-- ============================================================================
-- SECTION 3: MODEL EVALUATION
-- ============================================================================

-- Regression Metrics
SELECT
  'model_ltv_behavioral_v2' AS model_name,
  CURRENT_TIMESTAMP() AS evaluated_at,
  *
FROM ML.EVALUATE(MODEL `ssi_shadow.model_ltv_behavioral_v2`);

/*
Expected Output:
+-------------------+-------------+--------------+------------+------------------+
| mean_squared_error | r2_score   | mean_abs_error | explained_variance | ...  |
+-------------------+-------------+--------------+------------+------------------+
| 0.45              | 0.72       | 0.52          | 0.73       | ...              |
+-------------------+-------------+--------------+------------+------------------+

Target R² > 0.65 for production use
*/


-- ============================================================================
-- SECTION 4: FEATURE IMPORTANCE (Global Explain)
-- ============================================================================

-- Top 20 most important features
SELECT
  feature,
  ROUND(importance_weight, 4) AS importance,
  ROUND(importance_weight / SUM(importance_weight) OVER() * 100, 2) AS importance_pct,
  
  -- Categorize feature type
  CASE
    WHEN feature LIKE '%_7d%' OR feature LIKE '%velocity%' OR feature LIKE '%intent%' THEN 'Behavioral'
    WHEN feature LIKE '%spend%' OR feature LIKE '%purchase%' OR feature LIKE '%order%' THEN 'RFM'
    WHEN feature LIKE '%session%' OR feature LIKE '%page%' OR feature LIKE '%scroll%' THEN 'Engagement'
    WHEN feature LIKE '%cart%' OR feature LIKE '%checkout%' THEN 'Funnel'
    ELSE 'Other'
  END AS feature_category

FROM ML.FEATURE_IMPORTANCE(MODEL `ssi_shadow.model_ltv_behavioral_v2`)
ORDER BY importance_weight DESC
LIMIT 20;

/*
Expected Output (Hypothesis: Behavioral features should be in top 10):
+-------------------------+------------+----------------+------------------+
| feature                 | importance | importance_pct | feature_category |
+-------------------------+------------+----------------+------------------+
| lifetime_spend_norm     | 0.1823     | 18.23%         | RFM              |
| product_views_7d_norm   | 0.1456     | 14.56%         | Behavioral       | ← Innovation!
| purchase_intent_norm    | 0.1234     | 12.34%         | Behavioral       | ← Innovation!
| recency_score           | 0.0987     | 9.87%          | RFM              |
| cart_abandonment_norm   | 0.0876     | 8.76%          | Behavioral       | ← Innovation!
| velocity_7d_norm        | 0.0765     | 7.65%          | Behavioral       | ← Innovation!
| ...                     | ...        | ...            | ...              |
+-------------------------+------------+----------------+------------------+

If behavioral features rank high → our hypothesis is validated!
*/

-- Feature importance by category
SELECT
  feature_category,
  COUNT(*) AS feature_count,
  SUM(importance_pct) AS total_importance_pct
FROM (
  SELECT
    feature,
    importance_weight / SUM(importance_weight) OVER() * 100 AS importance_pct,
    CASE
      WHEN feature LIKE '%_7d%' OR feature LIKE '%velocity%' OR feature LIKE '%intent%' THEN 'Behavioral'
      WHEN feature LIKE '%spend%' OR feature LIKE '%purchase%' OR feature LIKE '%order%' THEN 'RFM'
      WHEN feature LIKE '%session%' OR feature LIKE '%page%' OR feature LIKE '%scroll%' THEN 'Engagement'
      WHEN feature LIKE '%cart%' OR feature LIKE '%checkout%' THEN 'Funnel'
      ELSE 'Other'
    END AS feature_category
  FROM ML.FEATURE_IMPORTANCE(MODEL `ssi_shadow.model_ltv_behavioral_v2`)
)
GROUP BY feature_category
ORDER BY total_importance_pct DESC;


-- ============================================================================
-- SECTION 5: PREDICTIONS
-- ============================================================================

-- Create predictions table
CREATE OR REPLACE TABLE `ssi_shadow.predictions_ltv_behavioral` AS
WITH predictions AS (
  SELECT
    canonical_id,
    
    -- Predicted log revenue → Convert back to actual revenue
    EXP(predicted_log_revenue_90d) - 1 AS predicted_revenue_90d,
    
    -- Original features for analysis
    lifetime_spend,
    purchase_count,
    days_since_last_order,
    product_views_last_7d,
    cart_abandonment_rate,
    avg_session_duration
    
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_ltv_behavioral_v2`,
    (SELECT * FROM `ssi_shadow.ml_training_ltv_behavioral`)
  )
)
SELECT
  p.*,
  
  -- LTV Tier based on prediction
  CASE
    WHEN predicted_revenue_90d >= 500 THEN 'VIP'
    WHEN predicted_revenue_90d >= 200 THEN 'High'
    WHEN predicted_revenue_90d >= 50 THEN 'Medium'
    WHEN predicted_revenue_90d > 0 THEN 'Low'
    ELSE 'Dormant'
  END AS predicted_ltv_tier,
  
  -- Percentile rank
  NTILE(100) OVER (ORDER BY predicted_revenue_90d) AS ltv_percentile,
  
  -- Action recommendation
  CASE
    WHEN predicted_revenue_90d >= 200 AND cart_abandonment_rate > 0.5 
      THEN 'cart_recovery_priority'
    WHEN predicted_revenue_90d >= 100 AND days_since_last_order > 30 
      THEN 'win_back_campaign'
    WHEN predicted_revenue_90d >= 50 AND product_views_last_7d > 10 
      THEN 'conversion_opportunity'
    WHEN predicted_revenue_90d < 10 AND purchase_count > 0 
      THEN 'churn_prevention'
    ELSE 'standard_nurture'
  END AS recommended_action,
  
  CURRENT_TIMESTAMP() AS predicted_at

FROM predictions p;


-- ============================================================================
-- SECTION 6: MODEL COMPARISON (Behavioral vs Traditional)
-- ============================================================================

-- Compare with a baseline RFM-only model
CREATE OR REPLACE MODEL `ssi_shadow.model_ltv_rfm_only`
TRANSFORM(
  canonical_id,
  ML.MIN_MAX_SCALER(LOG1P(lifetime_spend)) OVER() AS lifetime_spend_norm,
  ML.MIN_MAX_SCALER(purchase_count) OVER() AS purchase_count_norm,
  ML.MIN_MAX_SCALER(1.0 / (1.0 + days_since_last_order)) OVER() AS recency_score,
  ML.MIN_MAX_SCALER(LOG1P(avg_order_value)) OVER() AS aov_norm,
  LOG1P(revenue_90d) AS log_revenue_90d
)
OPTIONS (
  model_type = 'BOOSTED_TREE_REGRESSOR',
  input_label_cols = ['log_revenue_90d'],
  num_parallel_tree = 5,
  max_tree_depth = 8,
  learn_rate = 0.05,
  max_iterations = 200,
  data_split_method = 'RANDOM',
  data_split_eval_fraction = 0.2,
  enable_global_explain = TRUE
) AS
SELECT
  canonical_id,
  lifetime_spend,
  purchase_count,
  days_since_last_order,
  avg_order_value,
  revenue_90d
FROM `ssi_shadow.ml_training_ltv_behavioral`
WHERE purchase_count > 0;


-- Compare model performance
SELECT
  'Behavioral + RFM' AS model,
  (SELECT r2_score FROM ML.EVALUATE(MODEL `ssi_shadow.model_ltv_behavioral_v2`)) AS r2_score,
  (SELECT mean_absolute_error FROM ML.EVALUATE(MODEL `ssi_shadow.model_ltv_behavioral_v2`)) AS mae
UNION ALL
SELECT
  'RFM Only' AS model,
  (SELECT r2_score FROM ML.EVALUATE(MODEL `ssi_shadow.model_ltv_rfm_only`)) AS r2_score,
  (SELECT mean_absolute_error FROM ML.EVALUATE(MODEL `ssi_shadow.model_ltv_rfm_only`)) AS mae;

/*
Expected: Behavioral model should have higher R² and lower MAE
+-------------------+----------+-------+
| model             | r2_score | mae   |
+-------------------+----------+-------+
| Behavioral + RFM  | 0.72     | 45.23 | ← Better!
| RFM Only          | 0.58     | 67.89 | ← Baseline
+-------------------+----------+-------+

The behavioral features should improve R² by ~10-15%
*/


-- ============================================================================
-- SECTION 7: INFERENCE FOR NEW DATA
-- ============================================================================

-- Procedure to predict LTV for a specific user
CREATE OR REPLACE PROCEDURE `ssi_shadow.predict_user_ltv`(
  IN user_id STRING,
  OUT predicted_ltv FLOAT64,
  OUT ltv_tier STRING,
  OUT top_features ARRAY<STRUCT<feature STRING, contribution FLOAT64>>
)
BEGIN
  -- Get prediction
  SET (predicted_ltv, ltv_tier) = (
    SELECT AS STRUCT
      EXP(predicted_log_revenue_90d) - 1,
      CASE
        WHEN EXP(predicted_log_revenue_90d) - 1 >= 500 THEN 'VIP'
        WHEN EXP(predicted_log_revenue_90d) - 1 >= 200 THEN 'High'
        WHEN EXP(predicted_log_revenue_90d) - 1 >= 50 THEN 'Medium'
        ELSE 'Low'
      END
    FROM ML.PREDICT(
      MODEL `ssi_shadow.model_ltv_behavioral_v2`,
      (SELECT * FROM `ssi_shadow.ml_training_ltv_behavioral` WHERE canonical_id = user_id)
    )
    LIMIT 1
  );
  
  -- Get local feature explanation (top contributing features for this user)
  SET top_features = (
    SELECT ARRAY_AGG(STRUCT(feature, attribution) ORDER BY ABS(attribution) DESC LIMIT 5)
    FROM ML.EXPLAIN_PREDICT(
      MODEL `ssi_shadow.model_ltv_behavioral_v2`,
      (SELECT * FROM `ssi_shadow.ml_training_ltv_behavioral` WHERE canonical_id = user_id)
    ),
    UNNEST(feature_attributions)
  );
END;


-- ============================================================================
-- SECTION 8: BATCH SCORING (Daily Job)
-- ============================================================================

CREATE OR REPLACE PROCEDURE `ssi_shadow.score_all_users_ltv`()
BEGIN
  -- Recreate predictions table with latest data
  CREATE OR REPLACE TABLE `ssi_shadow.predictions_ltv_current` AS
  SELECT
    canonical_id,
    EXP(predicted_log_revenue_90d) - 1 AS predicted_ltv_90d,
    CASE
      WHEN EXP(predicted_log_revenue_90d) - 1 >= 500 THEN 'VIP'
      WHEN EXP(predicted_log_revenue_90d) - 1 >= 200 THEN 'High'
      WHEN EXP(predicted_log_revenue_90d) - 1 >= 50 THEN 'Medium'
      ELSE 'Low'
    END AS ltv_tier,
    NTILE(100) OVER (ORDER BY predicted_log_revenue_90d) AS ltv_percentile,
    CURRENT_TIMESTAMP() AS scored_at
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_ltv_behavioral_v2`,
    (SELECT * FROM `ssi_shadow.ml_training_ltv_behavioral`)
  );
  
  SELECT CONCAT('Scored ', CAST(@@row_count AS STRING), ' users');
END;


-- ============================================================================
-- SECTION 9: MONITORING & RETRAINING
-- ============================================================================

-- Create model performance tracking table
CREATE TABLE IF NOT EXISTS `ssi_shadow.model_performance_log` (
  model_name STRING,
  trained_at TIMESTAMP,
  r2_score FLOAT64,
  mae FLOAT64,
  mse FLOAT64,
  training_rows INT64,
  feature_count INT64
);

-- Log current model performance
INSERT INTO `ssi_shadow.model_performance_log`
SELECT
  'model_ltv_behavioral_v2' AS model_name,
  CURRENT_TIMESTAMP() AS trained_at,
  r2_score,
  mean_absolute_error AS mae,
  mean_squared_error AS mse,
  (SELECT COUNT(*) FROM `ssi_shadow.ml_training_ltv_behavioral`) AS training_rows,
  (SELECT COUNT(*) FROM ML.FEATURE_INFO(MODEL `ssi_shadow.model_ltv_behavioral_v2`)) AS feature_count
FROM ML.EVALUATE(MODEL `ssi_shadow.model_ltv_behavioral_v2`);

-- Alert if model performance degrades
CREATE OR REPLACE VIEW `ssi_shadow.model_performance_alerts` AS
SELECT
  model_name,
  trained_at,
  r2_score,
  LAG(r2_score) OVER (PARTITION BY model_name ORDER BY trained_at) AS prev_r2_score,
  r2_score - LAG(r2_score) OVER (PARTITION BY model_name ORDER BY trained_at) AS r2_change,
  CASE
    WHEN r2_score < 0.5 THEN 'CRITICAL: R² below 0.5'
    WHEN r2_score - LAG(r2_score) OVER (PARTITION BY model_name ORDER BY trained_at) < -0.1 
      THEN 'WARNING: R² dropped >10%'
    ELSE 'OK'
  END AS status
FROM `ssi_shadow.model_performance_log`
ORDER BY trained_at DESC;


-- ============================================================================
-- USAGE EXAMPLES
-- ============================================================================

/*
-- 1. View feature importance
SELECT * FROM ML.FEATURE_IMPORTANCE(MODEL `ssi_shadow.model_ltv_behavioral_v2`)
ORDER BY importance_weight DESC LIMIT 10;

-- 2. Score all users
CALL `ssi_shadow.score_all_users_ltv`();

-- 3. Predict for specific user
DECLARE ltv FLOAT64;
DECLARE tier STRING;
DECLARE features ARRAY<STRUCT<feature STRING, contribution FLOAT64>>;
CALL `ssi_shadow.predict_user_ltv`('canonical_abc123', ltv, tier, features);
SELECT ltv, tier, features;

-- 4. Find high-LTV users with cart abandonment (marketing opportunity)
SELECT 
  canonical_id,
  predicted_ltv_90d,
  cart_abandonment_rate,
  product_views_last_7d
FROM `ssi_shadow.predictions_ltv_behavioral`
WHERE predicted_ltv_tier IN ('VIP', 'High')
  AND cart_abandonment_rate > 0.6
ORDER BY predicted_revenue_90d DESC
LIMIT 100;

-- 5. Compare behavioral vs RFM importance
-- (Validates our hypothesis that behavioral features matter)
SELECT
  CASE 
    WHEN feature LIKE '%_7d%' OR feature LIKE '%cart%' OR feature LIKE '%intent%' THEN 'Behavioral'
    ELSE 'RFM/Other'
  END AS feature_type,
  SUM(importance_weight) AS total_importance
FROM ML.FEATURE_IMPORTANCE(MODEL `ssi_shadow.model_ltv_behavioral_v2`)
GROUP BY 1;
*/
