-- =============================================================================
-- S.S.I. SHADOW — BIGQUERY ML NATIVE MODELS
-- =============================================================================
--
-- Modelos ML direto no BigQuery (sem Vertex AI)
-- Mais simples, mais barato, suficiente para a maioria dos casos
--
-- Modelos:
-- 1. LTV Prediction (Regression)
-- 2. Intent Prediction (Classification)
-- 3. Churn Prediction (Classification)
-- 4. Anomaly Detection (K-Means clustering)
--
-- =============================================================================

-- =============================================================================
-- 1. LTV PREDICTION MODEL
-- =============================================================================
-- Prediz valor total que usuário vai gastar

CREATE OR REPLACE MODEL `{PROJECT_ID}.ssi_shadow.bqml_ltv_model`
OPTIONS(
    model_type = 'BOOSTED_TREE_REGRESSOR',
    input_label_cols = ['total_value'],
    max_iterations = 50,
    early_stop = TRUE,
    data_split_method = 'AUTO_SPLIT',
    enable_global_explain = TRUE
) AS

WITH user_features AS (
    SELECT
        ssi_id,
        
        -- Engagement metrics
        COUNT(*) as total_events,
        COUNTIF(event_name = 'PageView') as pageviews,
        COUNTIF(event_name = 'ViewContent') as product_views,
        COUNTIF(event_name = 'AddToCart') as add_to_carts,
        COUNTIF(event_name = 'InitiateCheckout') as checkouts,
        COUNTIF(event_name = 'Purchase') as purchases,
        
        -- Funnel rates
        SAFE_DIVIDE(COUNTIF(event_name = 'ViewContent'), COUNTIF(event_name = 'PageView')) as view_rate,
        SAFE_DIVIDE(COUNTIF(event_name = 'AddToCart'), COUNTIF(event_name = 'ViewContent')) as atc_rate,
        SAFE_DIVIDE(COUNTIF(event_name = 'Purchase'), COUNTIF(event_name = 'AddToCart')) as purchase_rate,
        
        -- Quality scores
        AVG(trust_score) as avg_trust_score,
        AVG(intent_score) as avg_intent_score,
        
        -- Device & source
        COUNTIF(device_type = 'mobile') / COUNT(*) as mobile_rate,
        COUNTIF(fbclid IS NOT NULL) / COUNT(*) as paid_rate,
        
        -- Temporal
        TIMESTAMP_DIFF(MAX(event_time), MIN(event_time), HOUR) as lifespan_hours,
        COUNT(DISTINCT DATE(event_time)) as active_days,
        
        -- Target
        SUM(CASE WHEN event_name = 'Purchase' 
            THEN SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) 
            ELSE 0 END) as total_value
            
    FROM `{PROJECT_ID}.ssi_shadow.events`
    WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
    GROUP BY ssi_id
    HAVING total_events >= 3 AND total_value > 0
)

SELECT
    pageviews,
    product_views,
    add_to_carts,
    checkouts,
    purchases,
    COALESCE(view_rate, 0) as view_rate,
    COALESCE(atc_rate, 0) as atc_rate,
    COALESCE(purchase_rate, 0) as purchase_rate,
    COALESCE(avg_trust_score, 0.5) as avg_trust_score,
    COALESCE(avg_intent_score, 0.5) as avg_intent_score,
    mobile_rate,
    paid_rate,
    COALESCE(lifespan_hours, 0) as lifespan_hours,
    active_days,
    total_value
FROM user_features;

-- =============================================================================
-- 2. INTENT PREDICTION MODEL
-- =============================================================================
-- Prediz probabilidade de conversão

CREATE OR REPLACE MODEL `{PROJECT_ID}.ssi_shadow.bqml_intent_model`
OPTIONS(
    model_type = 'BOOSTED_TREE_CLASSIFIER',
    input_label_cols = ['converted'],
    max_iterations = 50,
    early_stop = TRUE,
    enable_global_explain = TRUE,
    auto_class_weights = TRUE  -- Balancear classes
) AS

SELECT
    -- Engagement
    COUNTIF(event_name = 'PageView') as pageviews,
    COUNTIF(event_name = 'ViewContent') as product_views,
    COUNTIF(event_name = 'AddToCart') as add_to_carts,
    
    -- Quality
    AVG(trust_score) as avg_trust_score,
    
    -- Behavioral
    AVG(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.scroll_depth') AS FLOAT64)) as avg_scroll_depth,
    AVG(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.time_on_page') AS FLOAT64)) as avg_time_on_page,
    MAX(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.interactions') AS INT64)) as max_interactions,
    
    -- Device
    MAX(CASE WHEN device_type = 'mobile' THEN 1 ELSE 0 END) as is_mobile,
    
    -- Source
    MAX(CASE WHEN fbclid IS NOT NULL OR gclid IS NOT NULL THEN 1 ELSE 0 END) as from_paid,
    
    -- History
    MAX(CASE WHEN purchases > 0 THEN 1 ELSE 0 END) as is_returning_buyer,
    
    -- Target: converteu nessa sessão?
    MAX(CASE WHEN event_name IN ('InitiateCheckout', 'Purchase') THEN 1 ELSE 0 END) as converted
    
FROM (
    SELECT
        e.*,
        COUNTIF(e2.event_name = 'Purchase') OVER (PARTITION BY e.ssi_id ORDER BY e.event_time ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING) as purchases
    FROM `{PROJECT_ID}.ssi_shadow.events` e
    LEFT JOIN `{PROJECT_ID}.ssi_shadow.events` e2 
        ON e.ssi_id = e2.ssi_id AND e2.event_time < e.event_time
    WHERE e.event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
)
GROUP BY ssi_id
HAVING pageviews >= 1;

-- =============================================================================
-- 3. CHURN PREDICTION MODEL
-- =============================================================================
-- Prediz se usuário vai churnar (não voltar em 14 dias)

CREATE OR REPLACE MODEL `{PROJECT_ID}.ssi_shadow.bqml_churn_model`
OPTIONS(
    model_type = 'BOOSTED_TREE_CLASSIFIER',
    input_label_cols = ['churned'],
    max_iterations = 50,
    early_stop = TRUE,
    auto_class_weights = TRUE
) AS

WITH user_activity AS (
    SELECT
        ssi_id,
        MAX(event_time) as last_activity,
        COUNT(*) as total_events,
        COUNTIF(event_name = 'Purchase') as purchases,
        AVG(trust_score) as avg_trust_score,
        COUNTIF(device_type = 'mobile') / COUNT(*) as mobile_rate
    FROM `{PROJECT_ID}.ssi_shadow.events`
    WHERE event_time BETWEEN 
        TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 60 DAY) AND
        TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
    GROUP BY ssi_id
),
future_activity AS (
    SELECT
        ssi_id,
        COUNT(*) as future_events
    FROM `{PROJECT_ID}.ssi_shadow.events`
    WHERE event_time > TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 14 DAY)
    GROUP BY ssi_id
)

SELECT
    ua.total_events,
    ua.purchases,
    COALESCE(ua.avg_trust_score, 0.5) as avg_trust_score,
    ua.mobile_rate,
    CASE WHEN fa.future_events IS NULL OR fa.future_events = 0 THEN 1 ELSE 0 END as churned
FROM user_activity ua
LEFT JOIN future_activity fa ON ua.ssi_id = fa.ssi_id;

-- =============================================================================
-- 4. ANOMALY DETECTION (K-Means)
-- =============================================================================
-- Detecta comportamento anômalo (bots, fraude)

CREATE OR REPLACE MODEL `{PROJECT_ID}.ssi_shadow.bqml_anomaly_model`
OPTIONS(
    model_type = 'KMEANS',
    num_clusters = 5,  -- Normal, Suspicious, Bot, High-Value, Power-User
    standardize_features = TRUE
) AS

SELECT
    -- Event patterns
    COUNT(*) as events_per_day,
    AVG(TIMESTAMP_DIFF(
        event_time, 
        LAG(event_time) OVER (PARTITION BY ssi_id ORDER BY event_time),
        SECOND
    )) as avg_seconds_between_events,
    
    -- Quality
    AVG(trust_score) as avg_trust_score,
    STDDEV(trust_score) as trust_score_stddev,
    
    -- Behavioral
    AVG(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.scroll_depth') AS FLOAT64)) as avg_scroll,
    AVG(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.time_on_page') AS FLOAT64)) as avg_time,
    
    -- Patterns
    COUNTIF(event_name = 'PageView') / COUNT(*) as pageview_ratio,
    COUNTIF(event_name = 'Purchase') / COUNT(*) as purchase_ratio
    
FROM `{PROJECT_ID}.ssi_shadow.events`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
GROUP BY ssi_id, DATE(event_time)
HAVING COUNT(*) >= 3;

-- =============================================================================
-- PREDICTION VIEWS
-- =============================================================================

-- View: LTV Predictions
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_ltv_predictions` AS
SELECT
    ssi_id,
    predicted_total_value as predicted_ltv,
    predicted_total_value_interval.lower_bound as ltv_lower,
    predicted_total_value_interval.upper_bound as ltv_upper,
    
    -- Segmentação
    CASE
        WHEN predicted_total_value >= 500 THEN 'whale'
        WHEN predicted_total_value >= 200 THEN 'high'
        WHEN predicted_total_value >= 50 THEN 'medium'
        ELSE 'low'
    END as ltv_segment,
    
    CURRENT_TIMESTAMP() as predicted_at
FROM ML.PREDICT(
    MODEL `{PROJECT_ID}.ssi_shadow.bqml_ltv_model`,
    (
        SELECT
            ssi_id,
            COUNTIF(event_name = 'PageView') as pageviews,
            COUNTIF(event_name = 'ViewContent') as product_views,
            COUNTIF(event_name = 'AddToCart') as add_to_carts,
            COUNTIF(event_name = 'InitiateCheckout') as checkouts,
            COUNTIF(event_name = 'Purchase') as purchases,
            SAFE_DIVIDE(COUNTIF(event_name = 'ViewContent'), COUNTIF(event_name = 'PageView')) as view_rate,
            SAFE_DIVIDE(COUNTIF(event_name = 'AddToCart'), COUNTIF(event_name = 'ViewContent')) as atc_rate,
            SAFE_DIVIDE(COUNTIF(event_name = 'Purchase'), COUNTIF(event_name = 'AddToCart')) as purchase_rate,
            AVG(trust_score) as avg_trust_score,
            AVG(intent_score) as avg_intent_score,
            COUNTIF(device_type = 'mobile') / COUNT(*) as mobile_rate,
            COUNTIF(fbclid IS NOT NULL) / COUNT(*) as paid_rate,
            TIMESTAMP_DIFF(MAX(event_time), MIN(event_time), HOUR) as lifespan_hours,
            COUNT(DISTINCT DATE(event_time)) as active_days
        FROM `{PROJECT_ID}.ssi_shadow.events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
        GROUP BY ssi_id
        HAVING COUNT(*) >= 2
    )
);

-- View: Intent Predictions
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_intent_predictions` AS
SELECT
    ssi_id,
    predicted_converted as will_convert,
    predicted_converted_probs[OFFSET(1)].prob as conversion_probability,
    
    -- Segmentação
    CASE
        WHEN predicted_converted_probs[OFFSET(1)].prob >= 0.8 THEN 'hot'
        WHEN predicted_converted_probs[OFFSET(1)].prob >= 0.5 THEN 'warm'
        WHEN predicted_converted_probs[OFFSET(1)].prob >= 0.2 THEN 'cool'
        ELSE 'cold'
    END as intent_segment,
    
    CURRENT_TIMESTAMP() as predicted_at
FROM ML.PREDICT(
    MODEL `{PROJECT_ID}.ssi_shadow.bqml_intent_model`,
    (
        SELECT
            ssi_id,
            COUNTIF(event_name = 'PageView') as pageviews,
            COUNTIF(event_name = 'ViewContent') as product_views,
            COUNTIF(event_name = 'AddToCart') as add_to_carts,
            AVG(trust_score) as avg_trust_score,
            AVG(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.scroll_depth') AS FLOAT64)) as avg_scroll_depth,
            AVG(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.time_on_page') AS FLOAT64)) as avg_time_on_page,
            MAX(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.interactions') AS INT64)) as max_interactions,
            MAX(CASE WHEN device_type = 'mobile' THEN 1 ELSE 0 END) as is_mobile,
            MAX(CASE WHEN fbclid IS NOT NULL OR gclid IS NOT NULL THEN 1 ELSE 0 END) as from_paid,
            0 as is_returning_buyer
        FROM `{PROJECT_ID}.ssi_shadow.events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
        GROUP BY ssi_id
    )
);

-- View: Anomaly Detection Results
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_anomaly_detection` AS
WITH predictions AS (
    SELECT
        *,
        CENTROID_ID as cluster_id
    FROM ML.PREDICT(
        MODEL `{PROJECT_ID}.ssi_shadow.bqml_anomaly_model`,
        (
            SELECT
                ssi_id,
                DATE(event_time) as event_date,
                COUNT(*) as events_per_day,
                AVG(TIMESTAMP_DIFF(
                    event_time, 
                    LAG(event_time) OVER (PARTITION BY ssi_id ORDER BY event_time),
                    SECOND
                )) as avg_seconds_between_events,
                AVG(trust_score) as avg_trust_score,
                STDDEV(trust_score) as trust_score_stddev,
                AVG(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.scroll_depth') AS FLOAT64)) as avg_scroll,
                AVG(SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.time_on_page') AS FLOAT64)) as avg_time,
                COUNTIF(event_name = 'PageView') / COUNT(*) as pageview_ratio,
                COUNTIF(event_name = 'Purchase') / COUNT(*) as purchase_ratio
            FROM `{PROJECT_ID}.ssi_shadow.events`
            WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
            GROUP BY ssi_id, DATE(event_time)
            HAVING COUNT(*) >= 3
        )
    )
),
cluster_stats AS (
    SELECT
        cluster_id,
        AVG(avg_trust_score) as cluster_trust_score,
        COUNT(*) as cluster_size
    FROM predictions
    GROUP BY cluster_id
)

SELECT
    p.*,
    cs.cluster_trust_score,
    CASE
        WHEN cs.cluster_trust_score < 0.3 THEN 'bot_cluster'
        WHEN cs.cluster_trust_score < 0.5 THEN 'suspicious_cluster'
        WHEN p.events_per_day > 100 THEN 'power_user'
        WHEN p.avg_trust_score > 0.8 THEN 'high_quality'
        ELSE 'normal'
    END as classification
FROM predictions p
JOIN cluster_stats cs ON p.cluster_id = cs.cluster_id;

-- =============================================================================
-- MODEL EVALUATION VIEWS
-- =============================================================================

-- View: LTV Model Metrics
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_model_eval_ltv` AS
SELECT
    'ltv_model' as model,
    *
FROM ML.EVALUATE(MODEL `{PROJECT_ID}.ssi_shadow.bqml_ltv_model`);

-- View: Intent Model Metrics
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_model_eval_intent` AS
SELECT
    'intent_model' as model,
    *
FROM ML.EVALUATE(MODEL `{PROJECT_ID}.ssi_shadow.bqml_intent_model`);

-- =============================================================================
-- FEATURE IMPORTANCE
-- =============================================================================

-- View: LTV Feature Importance
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_feature_importance_ltv` AS
SELECT *
FROM ML.GLOBAL_EXPLAIN(MODEL `{PROJECT_ID}.ssi_shadow.bqml_ltv_model`);

-- View: Intent Feature Importance
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_feature_importance_intent` AS
SELECT *
FROM ML.GLOBAL_EXPLAIN(MODEL `{PROJECT_ID}.ssi_shadow.bqml_intent_model`);

-- =============================================================================
-- UNIFIED PREDICTIONS TABLE (para uso em tempo real)
-- =============================================================================

-- Procedure: Atualiza tabela de predições
CREATE OR REPLACE PROCEDURE `{PROJECT_ID}.ssi_shadow.update_predictions`()
BEGIN
    -- LTV predictions
    MERGE INTO `{PROJECT_ID}.ssi_shadow.predictions` T
    USING (SELECT * FROM `{PROJECT_ID}.ssi_shadow.v_ltv_predictions`) S
    ON T.ssi_id = S.ssi_id AND T.model_name = 'ltv'
    WHEN MATCHED THEN
        UPDATE SET
            predicted_ltv = S.predicted_ltv,
            confidence = (S.ltv_upper - S.ltv_lower) / NULLIF(S.predicted_ltv, 0),
            predicted_at = S.predicted_at
    WHEN NOT MATCHED THEN
        INSERT (ssi_id, model_name, model_version, predicted_ltv, confidence, predicted_at)
        VALUES (S.ssi_id, 'ltv', 'bqml_v1', S.predicted_ltv, 
                (S.ltv_upper - S.ltv_lower) / NULLIF(S.predicted_ltv, 0), S.predicted_at);
    
    -- Intent predictions
    MERGE INTO `{PROJECT_ID}.ssi_shadow.predictions` T
    USING (SELECT * FROM `{PROJECT_ID}.ssi_shadow.v_intent_predictions`) S
    ON T.ssi_id = S.ssi_id AND T.model_name = 'intent'
    WHEN MATCHED THEN
        UPDATE SET
            predicted_intent = S.conversion_probability,
            confidence = S.conversion_probability,
            predicted_at = S.predicted_at
    WHEN NOT MATCHED THEN
        INSERT (ssi_id, model_name, model_version, predicted_intent, confidence, predicted_at)
        VALUES (S.ssi_id, 'intent', 'bqml_v1', S.conversion_probability, 
                S.conversion_probability, S.predicted_at);
END;

-- =============================================================================
-- SCHEDULED JOBS
-- =============================================================================

-- Nota: Criar via Cloud Scheduler ou BigQuery Scheduled Queries
-- 
-- 1. Retreinar LTV model (semanal):
--    CREATE OR REPLACE MODEL ... (executar domingo 3AM)
--
-- 2. Retreinar Intent model (diário):
--    CREATE OR REPLACE MODEL ... (executar 4AM)
--
-- 3. Atualizar predictions (a cada 4 horas):
--    CALL `{PROJECT_ID}.ssi_shadow.update_predictions`()
