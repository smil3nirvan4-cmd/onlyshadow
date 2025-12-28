-- description: Add ML prediction and feature tables
-- +migrate up

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.ml_predictions` (
    prediction_id STRING NOT NULL,
    organization_id STRING NOT NULL,
    
    -- Target
    user_id STRING,
    
    -- Model info
    model_name STRING NOT NULL,
    model_version STRING,
    
    -- Predictions
    prediction_type STRING,  -- 'ltv', 'churn', 'conversion', 'fraud'
    predicted_value FLOAT64,
    confidence FLOAT64,
    probabilities STRING,  -- JSON for multi-class
    
    -- Features used (for explainability)
    feature_importance STRING,  -- JSON
    
    -- Timestamps
    predicted_at TIMESTAMP NOT NULL,
    valid_until TIMESTAMP
)
PARTITION BY DATE(predicted_at)
CLUSTER BY organization_id, model_name, user_id
OPTIONS(
    description='ML model predictions'
);

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.anomaly_detections` (
    anomaly_id STRING NOT NULL,
    organization_id STRING NOT NULL,
    
    -- What was anomalous
    metric_name STRING NOT NULL,
    metric_value FLOAT64,
    expected_value FLOAT64,
    deviation FLOAT64,
    
    -- Context
    dimension STRING,
    dimension_value STRING,
    
    -- Severity
    severity STRING,  -- 'low', 'medium', 'high', 'critical'
    z_score FLOAT64,
    
    -- Status
    acknowledged BOOL DEFAULT FALSE,
    acknowledged_by STRING,
    acknowledged_at TIMESTAMP,
    
    detected_at TIMESTAMP NOT NULL
)
PARTITION BY DATE(detected_at)
CLUSTER BY organization_id, metric_name
OPTIONS(
    description='Detected anomalies in metrics'
);


-- +migrate down

DROP TABLE IF EXISTS `{project}.{dataset}.ml_predictions`;
DROP TABLE IF EXISTS `{project}.{dataset}.anomaly_detections`;
