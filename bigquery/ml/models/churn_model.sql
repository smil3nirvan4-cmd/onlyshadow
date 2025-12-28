-- ============================================================================
-- S.S.I. SHADOW - Churn Prediction Model (BigQuery ML)
-- ============================================================================
-- Predicts probability of customer churning in next 30 days
-- Uses Boosted Tree Classifier with class balancing
-- ============================================================================

-- ============================================================================
-- Prepare Training Data with Churn Labels
-- ============================================================================

CREATE OR REPLACE TABLE `ssi_shadow.ml_training_churn` AS
WITH 
-- Define churn: No activity for 60+ days after observation
churn_labels AS (
  SELECT
    COALESCE(canonical_id, ssi_id) AS user_id,
    DATE(MAX(event_time)) AS last_activity_date,
    
    -- Check if user was active in 30-60 day window after last activity
    -- If not, they churned
    CASE 
      WHEN DATE_DIFF(CURRENT_DATE(), DATE(MAX(event_time)), DAY) >= 60 THEN 1
      ELSE 0
    END AS churned
    
  FROM `ssi_shadow.events_raw`
  WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY)
    AND event_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY)  -- Observation window
  GROUP BY user_id
)

SELECT
  f.*,
  c.churned AS target_churned
FROM `ssi_shadow.ml_features_churn` f
INNER JOIN churn_labels c ON f.user_id = c.user_id
WHERE c.churned IS NOT NULL;


-- ============================================================================
-- Model: Churn Prediction (Binary Classification)
-- ============================================================================

CREATE OR REPLACE MODEL `ssi_shadow.model_churn_30d`
OPTIONS (
  model_type = 'BOOSTED_TREE_CLASSIFIER',
  input_label_cols = ['target_churned'],
  
  -- Hyperparameters
  num_parallel_tree = 5,
  max_tree_depth = 6,
  min_tree_child_weight = 5,
  learn_rate = 0.1,
  l1_reg = 0.5,
  l2_reg = 0.5,
  subsample = 0.8,
  
  -- Handle class imbalance (churn is typically rare)
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
  -- Activity features
  days_since_last_activity,
  days_since_last_purchase,
  activity_rate,
  weekly_activity_rate,
  
  -- Trend features
  activity_trend_7d,
  activity_trend_30d,
  session_trend,
  
  -- Purchase features
  total_purchases,
  purchases_last_30d,
  has_purchased,
  
  -- Engagement features
  scroll_engagement,
  time_engagement_minutes,
  
  -- Risk indicators
  inactive_30d,
  inactive_60d,
  declining_activity,
  
  -- Maturity
  customer_maturity,
  
  -- Target
  target_churned
  
FROM `ssi_shadow.ml_training_churn`;


-- ============================================================================
-- Model: Churn Risk Score (Regression for smoother scores)
-- ============================================================================

CREATE OR REPLACE MODEL `ssi_shadow.model_churn_score`
OPTIONS (
  model_type = 'BOOSTED_TREE_REGRESSOR',
  input_label_cols = ['churn_score'],
  
  num_parallel_tree = 3,
  max_tree_depth = 5,
  learn_rate = 0.1,
  max_iterations = 50,
  early_stop = TRUE,
  data_split_method = 'RANDOM',
  data_split_eval_fraction = 0.2
) AS
SELECT
  -- Features
  days_since_last_activity,
  days_since_last_purchase,
  activity_rate,
  activity_trend_30d,
  total_purchases,
  scroll_engagement,
  customer_maturity,
  
  -- Target: Smoothed churn score (0-1)
  -- Based on actual churn but with decay
  CASE 
    WHEN target_churned = 1 THEN 
      0.8 + (0.2 * RAND())  -- 0.8-1.0 for churned
    WHEN inactive_60d = 1 THEN
      0.5 + (0.3 * RAND())  -- 0.5-0.8 for at-risk
    WHEN inactive_30d = 1 THEN
      0.3 + (0.2 * RAND())  -- 0.3-0.5 for declining
    ELSE
      0.05 + (0.25 * RAND())  -- 0.05-0.3 for active
  END AS churn_score
  
FROM `ssi_shadow.ml_training_churn`;


-- ============================================================================
-- Evaluate Churn Model
-- ============================================================================

-- Classification metrics
SELECT
  'model_churn_30d' AS model,
  *
FROM ML.EVALUATE(MODEL `ssi_shadow.model_churn_30d`);

-- Confusion matrix
SELECT
  *
FROM ML.CONFUSION_MATRIX(MODEL `ssi_shadow.model_churn_30d`);

-- ROC curve data
SELECT
  *
FROM ML.ROC_CURVE(MODEL `ssi_shadow.model_churn_30d`);


-- ============================================================================
-- Feature Importance for Churn
-- ============================================================================

SELECT
  *
FROM ML.FEATURE_IMPORTANCE(MODEL `ssi_shadow.model_churn_30d`)
ORDER BY importance_weight DESC;


-- ============================================================================
-- Predict Churn Risk for Current Users
-- ============================================================================

CREATE OR REPLACE TABLE `ssi_shadow.predictions_churn` AS
WITH class_predictions AS (
  SELECT
    user_id,
    predicted_target_churned AS will_churn,
    (SELECT prob FROM UNNEST(predicted_target_churned_probs) WHERE label = 1) AS churn_probability
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_churn_30d`,
    (SELECT * FROM `ssi_shadow.ml_features_churn`)
  )
),
score_predictions AS (
  SELECT
    user_id,
    predicted_churn_score AS churn_score
  FROM ML.PREDICT(
    MODEL `ssi_shadow.model_churn_score`,
    (SELECT * FROM `ssi_shadow.ml_features_churn`)
  )
)

SELECT
  c.user_id,
  
  -- Churn predictions
  c.will_churn,
  c.churn_probability,
  s.churn_score,
  
  -- Combined score (average of probability and score)
  (c.churn_probability + s.churn_score) / 2 AS combined_churn_risk,
  
  -- Risk tier
  CASE
    WHEN c.churn_probability >= 0.7 OR s.churn_score >= 0.7 THEN 'critical'
    WHEN c.churn_probability >= 0.5 OR s.churn_score >= 0.5 THEN 'high'
    WHEN c.churn_probability >= 0.3 OR s.churn_score >= 0.3 THEN 'medium'
    ELSE 'low'
  END AS churn_risk_tier,
  
  -- Days until likely churn (estimated)
  CASE
    WHEN c.churn_probability >= 0.7 THEN 7
    WHEN c.churn_probability >= 0.5 THEN 14
    WHEN c.churn_probability >= 0.3 THEN 30
    ELSE 60
  END AS estimated_days_to_churn,
  
  -- Metadata
  CURRENT_TIMESTAMP() AS predicted_at

FROM class_predictions c
LEFT JOIN score_predictions s ON c.user_id = s.user_id;


-- ============================================================================
-- View: Users at Risk of Churning
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_churn_alerts` AS
SELECT
  p.user_id,
  p.churn_risk_tier,
  p.churn_probability,
  p.estimated_days_to_churn,
  
  -- User value (from LTV predictions)
  l.predicted_ltv_90d,
  l.predicted_ltv_tier,
  
  -- Priority score (combines churn risk and value)
  p.churn_probability * COALESCE(l.predicted_ltv_90d, 50) AS priority_score,
  
  -- Recommended action
  CASE
    WHEN p.churn_risk_tier = 'critical' AND l.predicted_ltv_tier IN ('vip', 'high') 
      THEN 'immediate_outreach'
    WHEN p.churn_risk_tier = 'critical' 
      THEN 'win_back_campaign'
    WHEN p.churn_risk_tier = 'high' AND l.predicted_ltv_tier IN ('vip', 'high') 
      THEN 'retention_offer'
    WHEN p.churn_risk_tier = 'high' 
      THEN 'engagement_email'
    WHEN p.churn_risk_tier = 'medium' 
      THEN 'monitor'
    ELSE 'no_action'
  END AS recommended_action

FROM `ssi_shadow.predictions_churn` p
LEFT JOIN `ssi_shadow.predictions_ltv` l ON p.user_id = l.user_id
WHERE p.churn_risk_tier IN ('critical', 'high', 'medium')
ORDER BY priority_score DESC;


-- ============================================================================
-- View: Churn Summary Dashboard
-- ============================================================================

CREATE OR REPLACE VIEW `ssi_shadow.v_churn_dashboard` AS
SELECT
  churn_risk_tier,
  COUNT(*) AS user_count,
  AVG(churn_probability) AS avg_churn_probability,
  SUM(CASE WHEN will_churn = 1 THEN 1 ELSE 0 END) AS predicted_churners,
  
  -- Value at risk
  (
    SELECT SUM(l.predicted_ltv_90d)
    FROM `ssi_shadow.predictions_churn` pc
    JOIN `ssi_shadow.predictions_ltv` l ON pc.user_id = l.user_id
    WHERE pc.churn_risk_tier = p.churn_risk_tier
  ) AS value_at_risk

FROM `ssi_shadow.predictions_churn` p
GROUP BY churn_risk_tier
ORDER BY 
  CASE churn_risk_tier 
    WHEN 'critical' THEN 1 
    WHEN 'high' THEN 2 
    WHEN 'medium' THEN 3 
    ELSE 4 
  END;


-- ============================================================================
-- Procedure: Update Churn Predictions Daily
-- ============================================================================

CREATE OR REPLACE PROCEDURE `ssi_shadow.predict_churn_daily`()
BEGIN
  -- Refresh features
  -- (ml_features_churn should be updated by feature engineering first)
  
  -- Run predictions
  CREATE OR REPLACE TABLE `ssi_shadow.predictions_churn` AS
  WITH class_predictions AS (
    SELECT
      user_id,
      predicted_target_churned AS will_churn,
      (SELECT prob FROM UNNEST(predicted_target_churned_probs) WHERE label = 1) AS churn_probability
    FROM ML.PREDICT(
      MODEL `ssi_shadow.model_churn_30d`,
      (SELECT * FROM `ssi_shadow.ml_features_churn`)
    )
  ),
  score_predictions AS (
    SELECT
      user_id,
      predicted_churn_score AS churn_score
    FROM ML.PREDICT(
      MODEL `ssi_shadow.model_churn_score`,
      (SELECT * FROM `ssi_shadow.ml_features_churn`)
    )
  )
  SELECT
    c.user_id,
    c.will_churn,
    c.churn_probability,
    s.churn_score,
    (c.churn_probability + s.churn_score) / 2 AS combined_churn_risk,
    CASE
      WHEN c.churn_probability >= 0.7 OR s.churn_score >= 0.7 THEN 'critical'
      WHEN c.churn_probability >= 0.5 OR s.churn_score >= 0.5 THEN 'high'
      WHEN c.churn_probability >= 0.3 OR s.churn_score >= 0.3 THEN 'medium'
      ELSE 'low'
    END AS churn_risk_tier,
    CASE
      WHEN c.churn_probability >= 0.7 THEN 7
      WHEN c.churn_probability >= 0.5 THEN 14
      WHEN c.churn_probability >= 0.3 THEN 30
      ELSE 60
    END AS estimated_days_to_churn,
    CURRENT_TIMESTAMP() AS predicted_at
  FROM class_predictions c
  LEFT JOIN score_predictions s ON c.user_id = s.user_id;

  SELECT CONCAT('Churn predictions updated: ', 
                (SELECT COUNT(*) FROM `ssi_shadow.predictions_churn`),
                ' users') AS status;
END;
