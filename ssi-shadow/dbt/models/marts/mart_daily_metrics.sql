-- models/marts/mart_daily_metrics.sql
-- Métricas agregadas por dia para dashboard

{{
    config(
        materialized='table',
        partition_by={
            "field": "date",
            "data_type": "date",
            "granularity": "month"
        }
    )
}}

WITH events AS (
    SELECT * FROM {{ ref('stg_events') }}
),

daily_agg AS (
    SELECT
        DATE(event_time) AS date,
        
        -- Volume
        COUNT(*) AS total_events,
        COUNT(DISTINCT ssi_id) AS unique_visitors,
        COUNTIF(event_name = 'PageView') AS pageviews,
        COUNTIF(event_name = 'ViewContent') AS product_views,
        COUNTIF(event_name = 'AddToCart') AS add_to_carts,
        COUNTIF(event_name = 'InitiateCheckout') AS checkouts,
        COUNTIF(event_name = 'Purchase') AS purchases,
        COUNTIF(event_name = 'Lead') AS leads,
        
        -- Revenue
        SUM(event_value) AS revenue,
        AVG(CASE WHEN event_name = 'Purchase' THEN event_value END) AS aov,
        
        -- Funnel
        SAFE_DIVIDE(COUNTIF(event_name = 'Purchase'), COUNT(DISTINCT ssi_id)) AS conversion_rate,
        
        -- Quality
        AVG(trust_score) AS avg_trust_score,
        AVG(intent_score) AS avg_intent_score,
        COUNTIF(is_suspicious) / COUNT(*) AS suspicious_rate,
        COUNTIF(is_blocked) / COUNT(*) AS blocked_rate,
        
        -- Attribution
        COUNTIF(has_fbclid) / COUNT(*) AS fbclid_rate,
        COUNTIF(has_gclid) / COUNT(*) AS gclid_rate,
        COUNTIF(has_email) / COUNT(*) AS email_rate,
        COUNTIF(has_phone) / COUNT(*) AS phone_rate,
        COUNTIF(fbp IS NOT NULL) / COUNT(*) AS fbp_rate,
        COUNTIF(fbc IS NOT NULL) / COUNT(*) AS fbc_rate,
        
        -- Match rate estimado
        SAFE_DIVIDE(
            COUNTIF(fbc IS NOT NULL OR fbp IS NOT NULL OR has_email OR has_phone),
            COUNT(*)
        ) AS estimated_match_rate,
        
        -- Device
        COUNTIF(device_type = 'mobile') / COUNT(*) AS mobile_rate,
        COUNTIF(device_type = 'desktop') / COUNT(*) AS desktop_rate,
        
        -- Source
        COUNTIF(utm_source IS NOT NULL) / COUNT(*) AS tracked_source_rate
        
    FROM events
    GROUP BY DATE(event_time)
)

SELECT
    *,
    
    -- Derived metrics
    SAFE_DIVIDE(purchases, unique_visitors) * 100 AS purchase_rate_pct,
    SAFE_DIVIDE(add_to_carts, product_views) AS view_to_cart_rate,
    SAFE_DIVIDE(purchases, add_to_carts) AS cart_to_purchase_rate,
    
    -- Quality score composto
    (avg_trust_score * 0.4) + 
    ((1 - suspicious_rate) * 0.3) + 
    (estimated_match_rate * 0.3) AS quality_score,
    
    -- EMQ estimado (1-10)
    LEAST(10, GREATEST(1,
        3 +  -- Baseline
        (email_rate * 3) +  -- +3 para emails
        (fbc_rate * 2) +  -- +2 para FBC
        (fbp_rate * 1.5) +  -- +1.5 para FBP
        (phone_rate * 0.5)  -- +0.5 para phone
    )) AS estimated_emq

FROM daily_agg
ORDER BY date DESC
