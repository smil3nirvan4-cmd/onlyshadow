-- ============================================================================
-- S.S.I. SHADOW - LTV Prediction Model (BigQuery ML)
-- ============================================================================
-- Predicts customer Lifetime Value for the next 90 days
-- Uses Boosted Tree Regressor for best accuracy
-- ============================================================================

-- ============================================================================
-- Model 1: LTV Regression Model (Boosted Trees)
-- ============================================================================

CREATE OR REPLACE MODEL `ssi_shadow.model_ltv_90d`
OPTIONS (
  model_type = 'BOOSTED_TREE_REGRESSOR',
  input_label_cols = ['target_revenue_90d'],
  
  -- Hyperparameters (tuned)
  num_parallel_tree = 5,
  max_tree_depth = 8,
  min_tree_child_weight = 10,
  learn_rate = 0.1,
  l1_reg = 1.0,
  l2_reg = 1.0,
  subsample = 0.8,
  
  -- Training settings
  max_iterations = 100,
  early_stop = TRUE,
  min_rel_progress = 0.001,
  data_split_method = 'RANDOM',
  data_split_eval_fraction = 0.2,
  
  -- Enable feature importance
  enable_global_explain = TRUE
) AS
SELECT
  -- Features
  tenure_normalized,
  recency_normalized,
  recency_score,
  total_purchases,
  purchases_last_30d,
  purchases_last_90d,
  log_total_revenue,
  log_revenue_30d,
  log_revenue_90d,
  avg_order_value,
  max_order_value,
  stddev_order_value,
  log_sessions,
  log_pageviews,
  log_events,
  scroll_depth_normalized,
  time_on_page_normalized,
  pages_per_session,
  events_per_session,
  view_to_cart_rate,
  cart_to_checkout_rate,
  checkout_to_purchase_rate,
  overall_conversion_rate,
  purchase_frequency_monthly,
  revenue_per_month,
  revenue_trend,
  is_repeat_buyer,
  avg_trust_score,
  
  -- Segment as categorical
  customer_segment,
  
  -- Target
  target_revenue_90d
  
FROM `ssi_shadow.ml_training_ltv`
WHERE target_revenue_90d IS NOT NULL
  AND total_purchases > 0;  -- Only for existing customers


-- ============================================================================
-- Model 2: LTV Tier Classification (for segmentation)
-- ============================================================================

CREATE OR REPLACE MODEL `ssi_shadow.model_ltv_tier`
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['ltv_tier'],
  
  -- Hyperparameters
  num_parallel_tree = 5,
  max_tree_depth = 6,
  learn_rate = 0.1,
  
  -- Training settings
  max_iterations = 50,
  early_stop = TRUE,
  data_split_method = 'RANDOM',
  data_split_eval_fraction = 0.2,
  
  enable_global_explain = TRUE
) AS
SELECT
  -- Features
  tenure_normalized,
  recency_normalized,
  total_purchases,
  log_total_revenue,
  avg_order_value,
  purchase_frequency_monthly,
  revenue_per_month,
  is_repeat_buyer,
  avg_trust_score,
  customer_segment,
  
  -- Target: LTV Tier (derived from actual revenue)
  CASE
    WHEN target_revenue_90d >= 500 THEN 'vip'
    WHEN target_revenue_90d >= 200 THEN 'high'
    WHEN target_revenue_90d >= 50 THEN 'medium'
    ELSE 'low'
  END AS ltv_tier
  
FROM `ssi_shadow.ml_training_ltv`
WHERE target_revenue_90d IS NOT NULL;


-- ============================================================================
-- Model 3: Zero-inflated LTV (for prospects)
-- ============================================================================
-- First predicts if user will purchase, then predicts value if they do

-- Step 1: Will Purchase? (Binary classification)
CREATE OR REPLACE MODEL `ssi_shadow.model_will_purchase`
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['will_purchase'],
  
  num_parallel_tree = 5,
  max_tree_depth = 6,
  learn_rate = 0.1,
  max_iterations = 50,
  early_stop = TRUE,
  data_split_method = 'RANDOM',
  data_split_eval_fraction = 0.2,
  
  -- Handle class imbalance
  auto_class_weights = TRUE,
  
  enable_global_explain = TRUE
) AS
SELECT
  -- Features (for prospects who haven't purchased)
  tenure_normalized,
  recency_normalized,
  log_sessions,
  log_pageviews,
  log_events,
  scroll_depth_normalized,
  time_on_page_normalized,
  pages_per_session,
  view_to_cart_rate,
  cart_to_checkout_rate,
  avg_trust_score,
  
  -- Target
  CASE WHEN target_revenue_90d > 0 THEN 1 ELSE 0 END AS will_purchase
  
FROM `ssi_shadow.ml_training_ltv`
WHERE total_purchases = 0;  -- Only prospects


-- ============================================================================
-- Evaluate Models
-- ============================================================================

-- LTV Regression Evaluation
SELECT
  'model_ltv_90d' AS model,
  *
FROM ML.EVALUATE(MODEL `ssi_shadow.model_ltv_90d`);

-- LTV Tier Evaluation
SELECT
  'model_ltv_tier' AS model,
  *
FROM ML.EVALUATE(MODEL `ssi_shadow.model_ltv_tier`);

-- Will Purchase Evaluation
SELECT
  'model_will_purchase' AS model,
  *
FROM ML.EVALUATE(MODEL `ssi_shadow.model_will_purchase`);


-- ============================================================================
-- Feature Importance
-- ============================================================================

SELECT
  'model_ltv_90d' AS model,
  *
FROM ML.FEATURE_IMPORTANCE(MODEL `ssi_shadow.model_ltv_90d`)
ORDER BY importance_weight DESC
LIMIT 20;


-- ============================================================================
-- Predict LTV for Current Users
-- ============================================================================

CREATE OR REPLACE TABLE `ssi_shadow.predictions_ltv` AS
WITH predictions AS (
  SELECT
    user_id,
    customer_segment,
    
    -- Predicted LTV from regression model
    predicted_target_revenue_90d AS predicted_ltv_90d,
    
    -- Actual features for reference
    total_purchases,
    log_total_revenue,
    avg_order_value,
    purchase_frequency_monthly,
    recency_normalized
    
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_ltv_90d`,
    (SELECT * FROM `ssi_shadow.ml_features_ltv` WHERE customer_segment != 'prospect')
  )
),
tier_predictions AS (
  SELECT
    user_id,
    predicted_ltv_tier,
    predicted_ltv_tier_probs
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_ltv_tier`,
    (SELECT * FROM `ssi_shadow.ml_features_ltv` WHERE customer_segment != 'prospect')
  )
),
prospect_predictions AS (
  SELECT
    user_id,
    predicted_will_purchase,
    predicted_will_purchase_probs
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_will_purchase`,
    (SELECT * FROM `ssi_shadow.ml_features_ltv` WHERE customer_segment = 'prospect')
  )
)

SELECT
  COALESCE(p.user_id, pp.user_id) AS user_id,
  
  -- LTV Prediction
  COALESCE(p.predicted_ltv_90d, 0) AS predicted_ltv_90d,
  
  -- LTV Tier
  COALESCE(t.predicted_ltv_tier, 
           CASE WHEN pp.predicted_will_purchase = 1 THEN 'potential' ELSE 'low' END) AS predicted_ltv_tier,
  
  -- Purchase probability (for prospects)
  COALESCE(
    (SELECT prob FROM UNNEST(pp.predicted_will_purchase_probs) WHERE label = 1),
    CASE WHEN p.user_id IS NOT NULL THEN 1.0 ELSE 0 END
  ) AS purchase_probability,
  
  -- LTV Tier probabilities
  t.predicted_ltv_tier_probs,
  
  -- Segment
  COALESCE(p.customer_segment, 'prospect') AS customer_segment,
  
  -- Percentile (calculated after)
  0 AS ltv_percentile,
  
  -- Metadata
  CURRENT_TIMESTAMP() AS predicted_at

FROM predictions p
FULL OUTER JOIN tier_predictions t ON p.user_id = t.user_id
FULL OUTER JOIN prospect_predictions pp ON p.user_id = pp.user_id;


-- ============================================================================
-- Update LTV Percentiles
-- ============================================================================

UPDATE `ssi_shadow.predictions_ltv` p
SET ltv_percentile = percentile
FROM (
  SELECT
    user_id,
    CAST(NTILE(100) OVER (ORDER BY predicted_ltv_90d) AS INT64) AS percentile
  FROM `ssi_shadow.predictions_ltv`
) sub
WHERE p.user_id = sub.user_id;


-- ============================================================================
-- Create LTV Segments View
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_ltv_segments` AS
SELECT
  predicted_ltv_tier AS segment,
  COUNT(*) AS user_count,
  AVG(predicted_ltv_90d) AS avg_predicted_ltv,
  SUM(predicted_ltv_90d) AS total_predicted_ltv,
  AVG(purchase_probability) AS avg_purchase_probability,
  PERCENTILE_CONT(predicted_ltv_90d, 0.5) OVER (PARTITION BY predicted_ltv_tier) AS median_ltv
FROM `ssi_shadow.predictions_ltv`
GROUP BY segment;


-- ============================================================================
-- Schedule: Retrain Model Monthly
-- ============================================================================
-- CREATE SCHEDULED QUERY for monthly retraining with fresh data
-- Set up in BigQuery Console > Scheduled Queries
