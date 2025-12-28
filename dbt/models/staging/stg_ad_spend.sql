-- =============================================================================
-- S.S.I. SHADOW - Staging: Ad Platform Spend
-- =============================================================================
-- Consolidates ad spend from Meta, Google, TikTok into unified format.
-- Source: Platform API syncs or manual imports
-- =============================================================================

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

-- Meta Ads
WITH meta_spend AS (
    SELECT
        'meta' AS platform,
        account_id AS ad_account_id,
        campaign_id,
        campaign_name,
        adset_id,
        adset_name,
        ad_id,
        ad_name,
        
        DATE(date_start) AS spend_date,
        
        CAST(spend AS FLOAT64) AS spend,
        'USD' AS currency,
        
        CAST(impressions AS INT64) AS impressions,
        CAST(clicks AS INT64) AS clicks,
        CAST(COALESCE(actions.value, 0) AS INT64) AS conversions,
        CAST(COALESCE(action_values.value, 0) AS FLOAT64) AS conversion_value,
        
        -- Calculated metrics
        SAFE_DIVIDE(CAST(spend AS FLOAT64), NULLIF(CAST(clicks AS INT64), 0)) AS cpc,
        SAFE_DIVIDE(CAST(clicks AS INT64), NULLIF(CAST(impressions AS INT64), 0)) AS ctr,
        SAFE_DIVIDE(CAST(spend AS FLOAT64), NULLIF(CAST(actions.value AS INT64), 0)) AS cpa,
        SAFE_DIVIDE(CAST(action_values.value AS FLOAT64), NULLIF(CAST(spend AS FLOAT64), 0)) AS roas
        
    FROM {{ source('meta_ads', 'ad_insights') }}
    LEFT JOIN UNNEST(actions) AS actions ON actions.action_type = 'purchase'
    LEFT JOIN UNNEST(action_values) AS action_values ON action_values.action_type = 'purchase'
),

-- Google Ads
google_spend AS (
    SELECT
        'google' AS platform,
        customer_id AS ad_account_id,
        campaign_id,
        campaign_name,
        ad_group_id AS adset_id,
        ad_group_name AS adset_name,
        ad_id,
        '' AS ad_name,
        
        DATE(segments_date) AS spend_date,
        
        CAST(metrics_cost_micros AS FLOAT64) / 1000000 AS spend,
        'USD' AS currency,
        
        CAST(metrics_impressions AS INT64) AS impressions,
        CAST(metrics_clicks AS INT64) AS clicks,
        CAST(metrics_conversions AS INT64) AS conversions,
        CAST(metrics_conversions_value AS FLOAT64) AS conversion_value,
        
        -- Calculated metrics
        SAFE_DIVIDE(CAST(metrics_cost_micros AS FLOAT64) / 1000000, NULLIF(CAST(metrics_clicks AS INT64), 0)) AS cpc,
        SAFE_DIVIDE(CAST(metrics_clicks AS INT64), NULLIF(CAST(metrics_impressions AS INT64), 0)) AS ctr,
        SAFE_DIVIDE(CAST(metrics_cost_micros AS FLOAT64) / 1000000, NULLIF(CAST(metrics_conversions AS INT64), 0)) AS cpa,
        SAFE_DIVIDE(CAST(metrics_conversions_value AS FLOAT64), NULLIF(CAST(metrics_cost_micros AS FLOAT64) / 1000000, 0)) AS roas
        
    FROM {{ source('google_ads', 'ad_performance') }}
),

-- TikTok Ads
tiktok_spend AS (
    SELECT
        'tiktok' AS platform,
        advertiser_id AS ad_account_id,
        campaign_id,
        campaign_name,
        adgroup_id AS adset_id,
        adgroup_name AS adset_name,
        ad_id,
        ad_name,
        
        DATE(stat_datetime) AS spend_date,
        
        CAST(spend AS FLOAT64) AS spend,
        'USD' AS currency,
        
        CAST(impressions AS INT64) AS impressions,
        CAST(clicks AS INT64) AS clicks,
        CAST(complete_payment AS INT64) AS conversions,
        CAST(complete_payment_value AS FLOAT64) AS conversion_value,
        
        -- Calculated metrics
        SAFE_DIVIDE(CAST(spend AS FLOAT64), NULLIF(CAST(clicks AS INT64), 0)) AS cpc,
        SAFE_DIVIDE(CAST(clicks AS INT64), NULLIF(CAST(impressions AS INT64), 0)) AS ctr,
        SAFE_DIVIDE(CAST(spend AS FLOAT64), NULLIF(CAST(complete_payment AS INT64), 0)) AS cpa,
        SAFE_DIVIDE(CAST(complete_payment_value AS FLOAT64), NULLIF(CAST(spend AS FLOAT64), 0)) AS roas
        
    FROM {{ source('tiktok_ads', 'ad_insights') }}
),

-- Union all platforms
all_spend AS (
    SELECT * FROM meta_spend
    UNION ALL
    SELECT * FROM google_spend
    UNION ALL
    SELECT * FROM tiktok_spend
)

SELECT
    *,
    -- Date dimensions
    FORMAT_DATE('%Y-%m', spend_date) AS spend_month,
    EXTRACT(DAYOFWEEK FROM spend_date) AS day_of_week,
    
    -- Platform display name
    CASE platform
        WHEN 'meta' THEN 'Meta Ads'
        WHEN 'google' THEN 'Google Ads'
        WHEN 'tiktok' THEN 'TikTok Ads'
        ELSE platform
    END AS platform_name

FROM all_spend
WHERE spend > 0
