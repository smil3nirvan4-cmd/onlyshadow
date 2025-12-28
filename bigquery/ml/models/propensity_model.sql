-- ============================================================================
-- S.S.I. SHADOW - Purchase Propensity Model (BigQuery ML)
-- ============================================================================
-- Predicts probability of purchase in next 7 days
-- Used for real-time bid optimization and personalization
-- ============================================================================

-- ============================================================================
-- Prepare Training Data with Purchase Outcomes
-- ============================================================================

CREATE OR REPLACE TABLE `ssi_shadow.ml_training_propensity` AS
WITH 
-- Get users who were active 7+ days ago and track if they purchased
observation_window AS (
  SELECT
    COALESCE(canonical_id, ssi_id) AS user_id,
    DATE(MAX(event_time)) AS observation_date
  FROM `ssi_shadow.events_raw`
  WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)
    AND event_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
  GROUP BY user_id
),
-- Check if they purchased in the 7 days after observation
purchase_outcomes AS (
  SELECT
    o.user_id,
    o.observation_date,
    MAX(CASE 
      WHEN e.event_name = 'Purchase' 
           AND DATE(e.event_time) BETWEEN o.observation_date AND DATE_ADD(o.observation_date, INTERVAL 7 DAY)
      THEN 1 ELSE 0 
    END) AS purchased_7d
  FROM observation_window o
  LEFT JOIN `ssi_shadow.events_raw` e ON o.user_id = COALESCE(e.canonical_id, e.ssi_id)
  GROUP BY o.user_id, o.observation_date
)

SELECT
  f.*,
  p.purchased_7d AS target_purchased_7d
FROM `ssi_shadow.ml_features_propensity` f
INNER JOIN purchase_outcomes p ON f.user_id = p.user_id
WHERE p.purchased_7d IS NOT NULL;


-- ============================================================================
-- Model: Purchase Propensity (Binary Classification)
-- ============================================================================

CREATE OR REPLACE MODEL `ssi_shadow.model_propensity_7d`
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['target_purchased_7d'],
  
  -- Hyperparameters optimized for propensity
  num_parallel_tree = 5,
  max_tree_depth = 6,
  min_tree_child_weight = 3,
  learn_rate = 0.1,
  subsample = 0.8,
  colsample_bytree = 0.8,
  
  -- Handle class imbalance
  auto_class_weights = TRUE,
  
  -- Training settings
  max_iterations = 100,
  early_stop = TRUE,
  min_rel_progress = 0.001,
  data_split_method = 'RANDOM',
  data_split_eval_fraction = 0.2,
  
  enable_global_explain = TRUE
) AS
SELECT
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
  has_cart_activity,
  has_checkout_activity,
  
  -- Funnel metrics
  view_to_cart_rate_7d,
  cart_to_checkout_rate_7d,
  
  -- Historical behavior
  total_purchases,
  log_revenue,
  is_customer,
  is_repeat_customer,
  
  -- Engagement
  days_since_last_activity,
  active_today,
  scroll_engagement,
  time_engagement,
  
  -- Target
  target_purchased_7d
  
FROM `ssi_shadow.ml_training_propensity`;


-- ============================================================================
-- Model: Propensity Score (Regression for smoother ranking)
-- ============================================================================

CREATE OR REPLACE MODEL `ssi_shadow.model_propensity_score`
OPTIONS (
  model_type = 'BOOSTED_TREE_REGRESSOR',
  input_label_cols = ['propensity_score'],
  
  num_parallel_tree = 3,
  max_tree_depth = 5,
  learn_rate = 0.1,
  max_iterations = 50,
  early_stop = TRUE,
  data_split_method = 'RANDOM',
  data_split_eval_fraction = 0.2
) AS
SELECT
  -- Key features
  events_7d,
  product_views_7d,
  add_to_cart_7d,
  checkout_7d,
  has_cart_activity,
  has_checkout_activity,
  is_customer,
  rule_based_intent_score,
  
  -- Target: Propensity score
  -- Combines actual outcome with rule-based signals
  (target_purchased_7d * 0.7) + (rule_based_intent_score * 0.3) AS propensity_score
  
FROM `ssi_shadow.ml_training_propensity`;


-- ============================================================================
-- Model: Next Best Action (Multi-class)
-- ============================================================================

CREATE OR REPLACE MODEL `ssi_shadow.model_next_action`
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['next_action'],
  
  num_parallel_tree = 3,
  max_tree_depth = 5,
  learn_rate = 0.1,
  max_iterations = 50,
  early_stop = TRUE,
  auto_class_weights = TRUE,
  data_split_method = 'RANDOM',
  data_split_eval_fraction = 0.2
) AS
SELECT
  -- Features
  events_7d,
  product_views_7d,
  add_to_cart_7d,
  checkout_7d,
  is_customer,
  is_repeat_customer,
  days_since_last_activity,
  
  -- Target: What action did they take?
  CASE
    WHEN target_purchased_7d = 1 THEN 'purchase'
    WHEN checkout_7d > 0 THEN 'checkout_abandon'
    WHEN add_to_cart_7d > 0 THEN 'cart_abandon'
    WHEN product_views_7d > 0 THEN 'browse'
    ELSE 'inactive'
  END AS next_action
  
FROM `ssi_shadow.ml_training_propensity`;


-- ============================================================================
-- Evaluate Propensity Model
-- ============================================================================

SELECT
  'model_propensity_7d' AS model,
  *
FROM ML.EVALUATE(MODEL `ssi_shadow.model_propensity_7d`);

-- ROC Curve for threshold optimization
SELECT
  *
FROM ML.ROC_CURVE(MODEL `ssi_shadow.model_propensity_7d`)
ORDER BY threshold;

-- Feature importance
SELECT
  *
FROM ML.FEATURE_IMPORTANCE(MODEL `ssi_shadow.model_propensity_7d`)
ORDER BY importance_weight DESC;


-- ============================================================================
-- Predict Propensity for Current Active Users
-- ============================================================================

CREATE OR REPLACE TABLE `ssi_shadow.predictions_propensity` AS
WITH class_predictions AS (
  SELECT
    user_id,
    predicted_target_purchased_7d AS will_purchase,
    (SELECT prob FROM UNNEST(predicted_target_purchased_7d_probs) WHERE label = 1) AS purchase_probability
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_propensity_7d`,
    (SELECT * FROM `ssi_shadow.ml_features_propensity`)
  )
),
score_predictions AS (
  SELECT
    user_id,
    predicted_propensity_score AS propensity_score
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_propensity_score`,
    (SELECT * FROM `ssi_shadow.ml_features_propensity`)
  )
),
action_predictions AS (
  SELECT
    user_id,
    predicted_next_action,
    predicted_next_action_probs
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_next_action`,
    (SELECT * FROM `ssi_shadow.ml_features_propensity`)
  )
)

SELECT
  c.user_id,
  
  -- Propensity predictions
  c.will_purchase,
  c.purchase_probability,
  s.propensity_score,
  
  -- Combined score
  (c.purchase_probability * 0.6 + s.propensity_score * 0.4) AS combined_propensity,
  
  -- Propensity tier
  CASE
    WHEN c.purchase_probability >= 0.7 THEN 'very_high'
    WHEN c.purchase_probability >= 0.5 THEN 'high'
    WHEN c.purchase_probability >= 0.3 THEN 'medium'
    WHEN c.purchase_probability >= 0.1 THEN 'low'
    ELSE 'very_low'
  END AS propensity_tier,
  
  -- Next action prediction
  a.predicted_next_action,
  
  -- Bid multiplier recommendation
  CASE
    WHEN c.purchase_probability >= 0.7 THEN 1.5
    WHEN c.purchase_probability >= 0.5 THEN 1.3
    WHEN c.purchase_probability >= 0.3 THEN 1.1
    WHEN c.purchase_probability >= 0.1 THEN 1.0
    ELSE 0.8
  END AS bid_multiplier,
  
  -- Percentile rank
  CAST(PERCENT_RANK() OVER (ORDER BY c.purchase_probability) * 100 AS INT64) AS propensity_percentile,
  
  -- Metadata
  CURRENT_TIMESTAMP() AS predicted_at

FROM class_predictions c
LEFT JOIN score_predictions s ON c.user_id = s.user_id
LEFT JOIN action_predictions a ON c.user_id = a.user_id;


-- ============================================================================
-- View: High Propensity Users for Targeting
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_high_propensity_users` AS
SELECT
  p.user_id,
  p.purchase_probability,
  p.propensity_tier,
  p.bid_multiplier,
  p.predicted_next_action,
  
  -- LTV for prioritization
  l.predicted_ltv_90d,
  l.predicted_ltv_tier,
  
  -- Expected value (probability * predicted LTV)
  p.purchase_probability * COALESCE(l.predicted_ltv_90d, 50) AS expected_value,
  
  -- Priority rank
  ROW_NUMBER() OVER (ORDER BY p.purchase_probability * COALESCE(l.predicted_ltv_90d, 50) DESC) AS priority_rank

FROM `ssi_shadow.predictions_propensity` p
LEFT JOIN `ssi_shadow.predictions_ltv` l ON p.user_id = l.user_id
WHERE p.propensity_tier IN ('very_high', 'high')
ORDER BY expected_value DESC;


-- ============================================================================
-- View: Propensity Dashboard
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_propensity_dashboard` AS
SELECT
  propensity_tier,
  COUNT(*) AS user_count,
  AVG(purchase_probability) AS avg_probability,
  AVG(bid_multiplier) AS avg_bid_multiplier,
  
  -- Distribution
  ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) AS pct_of_total,
  
  -- Expected conversions (sum of probabilities)
  SUM(purchase_probability) AS expected_conversions

FROM `ssi_shadow.predictions_propensity`
GROUP BY propensity_tier
ORDER BY 
  CASE propensity_tier 
    WHEN 'very_high' THEN 1 
    WHEN 'high' THEN 2 
    WHEN 'medium' THEN 3 
    WHEN 'low' THEN 4 
    ELSE 5 
  END;


-- ============================================================================
-- View: Real-time Bid Signals
-- ============================================================================
-- This view can be queried by the Worker for real-time bid optimization

CREATE OR REPLACE VIEW `ssi_shadow.v_realtime_bid_signals` AS
SELECT
  p.user_id,
  
  -- Propensity signal
  p.purchase_probability AS propensity,
  p.bid_multiplier,
  
  -- LTV signal
  l.predicted_ltv_90d AS ltv,
  l.predicted_ltv_tier AS ltv_tier,
  
  -- Churn signal
  c.churn_probability,
  c.churn_risk_tier,
  
  -- Combined bid recommendation
  CASE
    -- High LTV + High propensity = aggressive bidding
    WHEN l.predicted_ltv_tier IN ('vip', 'high') AND p.propensity_tier IN ('very_high', 'high')
      THEN p.bid_multiplier * 1.2
    
    -- High churn risk + High LTV = retention focus
    WHEN c.churn_risk_tier IN ('critical', 'high') AND l.predicted_ltv_tier IN ('vip', 'high')
      THEN 1.3
    
    -- Normal propensity-based
    ELSE p.bid_multiplier
  END AS recommended_bid_multiplier,
  
  -- Audience signals for platform targeting
  STRUCT(
    p.propensity_tier,
    l.predicted_ltv_tier,
    c.churn_risk_tier,
    p.predicted_next_action
  ) AS targeting_signals

FROM `ssi_shadow.predictions_propensity` p
LEFT JOIN `ssi_shadow.predictions_ltv` l ON p.user_id = l.user_id
LEFT JOIN `ssi_shadow.predictions_churn` c ON p.user_id = c.user_id;


-- ============================================================================
-- Procedure: Update Propensity Predictions (Hourly)
-- ============================================================================

CREATE OR REPLACE PROCEDURE `ssi_shadow.predict_propensity_hourly`()
BEGIN
  -- Update features for active users
  -- (ml_features_propensity should be updated first)
  
  -- Run predictions
  CREATE OR REPLACE TABLE `ssi_shadow.predictions_propensity` AS
  WITH class_predictions AS (
    SELECT
      user_id,
      predicted_target_purchased_7d AS will_purchase,
      (SELECT prob FROM UNNEST(predicted_target_purchased_7d_probs) WHERE label = 1) AS purchase_probability
    FROM ML.PREDICT(
      MODEL `ssi_shadow.model_propensity_7d`,
      (SELECT * FROM `ssi_shadow.ml_features_propensity`)
    )
  ),
  score_predictions AS (
    SELECT
      user_id,
      predicted_propensity_score AS propensity_score
    FROM ML.PREDICT(
      MODEL `ssi_shadow.model_propensity_score`,
      (SELECT * FROM `ssi_shadow.ml_features_propensity`)
    )
  )
  SELECT
    c.user_id,
    c.will_purchase,
    c.purchase_probability,
    s.propensity_score,
    (c.purchase_probability * 0.6 + s.propensity_score * 0.4) AS combined_propensity,
    CASE
      WHEN c.purchase_probability >= 0.7 THEN 'very_high'
      WHEN c.purchase_probability >= 0.5 THEN 'high'
      WHEN c.purchase_probability >= 0.3 THEN 'medium'
      WHEN c.purchase_probability >= 0.1 THEN 'low'
      ELSE 'very_low'
    END AS propensity_tier,
    CAST(NULL AS STRING) AS predicted_next_action,
    CASE
      WHEN c.purchase_probability >= 0.7 THEN 1.5
      WHEN c.purchase_probability >= 0.5 THEN 1.3
      WHEN c.purchase_probability >= 0.3 THEN 1.1
      WHEN c.purchase_probability >= 0.1 THEN 1.0
      ELSE 0.8
    END AS bid_multiplier,
    0 AS propensity_percentile,
    CURRENT_TIMESTAMP() AS predicted_at
  FROM class_predictions c
  LEFT JOIN score_predictions s ON c.user_id = s.user_id;

  SELECT CONCAT('Propensity predictions updated: ', 
                (SELECT COUNT(*) FROM `ssi_shadow.predictions_propensity`),
                ' users') AS status;
END;
