-- description: Add attribution and touchpoint tables
-- +migrate up

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.touchpoints` (
    touchpoint_id STRING NOT NULL,
    organization_id STRING NOT NULL,
    
    user_id STRING,
    anonymous_id STRING,
    session_id STRING,
    
    -- Touchpoint details
    event_timestamp TIMESTAMP NOT NULL,
    event_name STRING,
    channel STRING,
    source STRING,
    medium STRING,
    campaign STRING,
    content STRING,
    term STRING,
    
    -- Click IDs
    click_id STRING,
    click_id_type STRING,  -- 'gclid', 'fbclid', 'ttclid', etc.
    
    -- Landing page
    landing_page STRING,
    referrer STRING,
    
    -- Attribution weight (calculated)
    first_touch_weight FLOAT64,
    last_touch_weight FLOAT64,
    linear_weight FLOAT64,
    position_weight FLOAT64,
    time_decay_weight FLOAT64,
    
    created_at TIMESTAMP
)
PARTITION BY DATE(event_timestamp)
CLUSTER BY organization_id, user_id
OPTIONS(
    description='User touchpoints for attribution'
);

CREATE TABLE IF NOT EXISTS `{project}.{dataset}.attribution_paths` (
    path_id STRING NOT NULL,
    organization_id STRING NOT NULL,
    
    conversion_id STRING NOT NULL,
    user_id STRING,
    
    -- Path summary
    touchpoint_count INT64,
    path_duration_hours FLOAT64,
    channels ARRAY<STRING>,
    sources ARRAY<STRING>,
    campaigns ARRAY<STRING>,
    
    -- Path value
    conversion_value FLOAT64,
    
    -- Attribution by model
    first_touch_attribution STRUCT<
        channel STRING,
        source STRING,
        campaign STRING,
        weight FLOAT64
    >,
    last_touch_attribution STRUCT<
        channel STRING,
        source STRING,
        campaign STRING,
        weight FLOAT64
    >,
    
    created_at TIMESTAMP
)
PARTITION BY DATE(created_at)
CLUSTER BY organization_id
OPTIONS(
    description='Attribution paths from touchpoints to conversion'
);


-- +migrate down

DROP TABLE IF EXISTS `{project}.{dataset}.touchpoints`;
DROP TABLE IF EXISTS `{project}.{dataset}.attribution_paths`;
