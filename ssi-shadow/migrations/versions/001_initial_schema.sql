-- description: Create core tables for SSI Shadow
-- +migrate up

-- Events raw table (partitioned by date)
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.events_raw` (
    event_id STRING NOT NULL,
    event_name STRING NOT NULL,
    event_timestamp TIMESTAMP NOT NULL,
    received_at TIMESTAMP NOT NULL,
    
    -- User identification
    user_id STRING,
    anonymous_id STRING,
    device_id STRING,
    
    -- Session
    session_id STRING,
    
    -- Event properties (JSON)
    properties STRING,  -- JSON encoded
    
    -- Context
    ip_address STRING,
    user_agent STRING,
    referrer STRING,
    page_url STRING,
    page_title STRING,
    
    -- Device info
    device_type STRING,
    device_brand STRING,
    device_model STRING,
    os_name STRING,
    os_version STRING,
    browser_name STRING,
    browser_version STRING,
    
    -- Geo
    country STRING,
    region STRING,
    city STRING,
    postal_code STRING,
    latitude FLOAT64,
    longitude FLOAT64,
    timezone STRING,
    
    -- UTM parameters
    utm_source STRING,
    utm_medium STRING,
    utm_campaign STRING,
    utm_term STRING,
    utm_content STRING,
    
    -- Platform tracking IDs
    fbclid STRING,
    gclid STRING,
    ttclid STRING,
    msclkid STRING,
    li_fat_id STRING,
    
    -- Trust & Quality
    trust_score FLOAT64,
    ivt_probability FLOAT64,
    is_bot BOOL,
    
    -- Processing metadata
    processed_at TIMESTAMP,
    platform_sent ARRAY<STRING>,  -- ['meta', 'google', 'tiktok']
    
    -- Tenant
    organization_id STRING NOT NULL
)
PARTITION BY DATE(event_timestamp)
CLUSTER BY organization_id, event_name, user_id
OPTIONS(
    description='Raw events table with all tracking data',
    partition_expiration_days=730,  -- 2 years
    require_partition_filter=true
);

-- User profiles table
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.user_profiles` (
    user_id STRING NOT NULL,
    organization_id STRING NOT NULL,
    
    -- Identification
    anonymous_ids ARRAY<STRING>,
    device_ids ARRAY<STRING>,
    email STRING,
    phone STRING,
    
    -- First/Last seen
    first_seen_at TIMESTAMP,
    last_seen_at TIMESTAMP,
    
    -- Engagement metrics
    total_sessions INT64,
    total_events INT64,
    total_pageviews INT64,
    
    -- Conversion metrics
    total_purchases INT64,
    total_revenue FLOAT64,
    first_purchase_at TIMESTAMP,
    last_purchase_at TIMESTAMP,
    avg_order_value FLOAT64,
    
    -- ML predictions
    ltv_predicted FLOAT64,
    ltv_confidence FLOAT64,
    churn_probability FLOAT64,
    conversion_probability FLOAT64,
    segment STRING,
    
    -- Attribution
    first_touch_source STRING,
    first_touch_medium STRING,
    first_touch_campaign STRING,
    last_touch_source STRING,
    last_touch_medium STRING,
    last_touch_campaign STRING,
    
    -- Custom properties (JSON)
    custom_properties STRING,
    
    -- Timestamps
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)
CLUSTER BY organization_id, user_id
OPTIONS(
    description='Unified user profiles with ML predictions'
);

-- Conversions table
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.conversions` (
    conversion_id STRING NOT NULL,
    organization_id STRING NOT NULL,
    
    -- Event reference
    event_id STRING NOT NULL,
    event_name STRING NOT NULL,
    event_timestamp TIMESTAMP NOT NULL,
    
    -- User
    user_id STRING,
    anonymous_id STRING,
    
    -- Value
    value FLOAT64,
    currency STRING,
    quantity INT64,
    
    -- Products
    product_ids ARRAY<STRING>,
    product_names ARRAY<STRING>,
    categories ARRAY<STRING>,
    
    -- Attribution
    attribution_model STRING,  -- 'first_touch', 'last_touch', 'linear', 'position_based', 'data_driven'
    attributed_source STRING,
    attributed_medium STRING,
    attributed_campaign STRING,
    attributed_campaign_id STRING,
    attributed_adset_id STRING,
    attributed_ad_id STRING,
    attributed_keyword STRING,
    attribution_weight FLOAT64,
    
    -- Click/touchpoint that led to conversion
    touchpoint_id STRING,
    click_timestamp TIMESTAMP,
    time_to_conversion INT64,  -- seconds
    
    -- Platform sync status
    sent_to_meta BOOL,
    sent_to_google BOOL,
    sent_to_tiktok BOOL,
    meta_event_id STRING,
    google_transaction_id STRING,
    
    -- Timestamps
    created_at TIMESTAMP
)
PARTITION BY DATE(event_timestamp)
CLUSTER BY organization_id, attributed_campaign_id
OPTIONS(
    description='Attributed conversions with multi-touch support'
);

-- Ad spend table
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.ad_spend` (
    date DATE NOT NULL,
    organization_id STRING NOT NULL,
    
    -- Platform
    platform STRING NOT NULL,  -- 'meta', 'google', 'tiktok', etc.
    account_id STRING NOT NULL,
    
    -- Campaign hierarchy
    campaign_id STRING,
    campaign_name STRING,
    adset_id STRING,
    adset_name STRING,
    ad_id STRING,
    ad_name STRING,
    
    -- Metrics
    spend FLOAT64,
    impressions INT64,
    clicks INT64,
    conversions INT64,
    conversion_value FLOAT64,
    
    -- Calculated metrics
    cpm FLOAT64,
    cpc FLOAT64,
    ctr FLOAT64,
    cpa FLOAT64,
    roas FLOAT64,
    
    -- Currency
    currency STRING,
    
    -- Timestamps
    synced_at TIMESTAMP
)
PARTITION BY date
CLUSTER BY organization_id, platform, campaign_id
OPTIONS(
    description='Daily ad spend aggregated from all platforms'
);

-- Campaigns table
CREATE TABLE IF NOT EXISTS `{project}.{dataset}.campaigns` (
    campaign_id STRING NOT NULL,
    organization_id STRING NOT NULL,
    
    -- Platform info
    platform STRING NOT NULL,
    account_id STRING NOT NULL,
    
    -- Campaign details
    name STRING,
    status STRING,
    objective STRING,
    
    -- Budget
    daily_budget FLOAT64,
    lifetime_budget FLOAT64,
    budget_remaining FLOAT64,
    
    -- Targeting (JSON)
    targeting STRING,
    
    -- Dates
    start_date DATE,
    end_date DATE,
    
    -- Performance
    total_spend FLOAT64,
    total_conversions INT64,
    total_revenue FLOAT64,
    
    -- Optimization
    bid_strategy STRING,
    bid_amount FLOAT64,
    optimization_goal STRING,
    
    -- SSI Shadow specific
    groas_enabled BOOL,
    auto_optimization BOOL,
    weather_bidding BOOL,
    
    -- Timestamps
    created_at TIMESTAMP,
    updated_at TIMESTAMP,
    synced_at TIMESTAMP
)
CLUSTER BY organization_id, platform
OPTIONS(
    description='Campaign metadata from all platforms'
);

-- Migrations tracking table
CREATE TABLE IF NOT EXISTS `{project}.{dataset}._migrations` (
    version STRING NOT NULL,
    name STRING NOT NULL,
    description STRING,
    checksum STRING NOT NULL,
    applied_at TIMESTAMP NOT NULL,
    status STRING NOT NULL,
    execution_time_ms INT64
)
OPTIONS(
    description='Migration history tracking'
);


-- +migrate down

DROP TABLE IF EXISTS `{project}.{dataset}.events_raw`;
DROP TABLE IF EXISTS `{project}.{dataset}.user_profiles`;
DROP TABLE IF EXISTS `{project}.{dataset}.conversions`;
DROP TABLE IF EXISTS `{project}.{dataset}.ad_spend`;
DROP TABLE IF EXISTS `{project}.{dataset}.campaigns`;
DROP TABLE IF EXISTS `{project}.{dataset}._migrations`;
