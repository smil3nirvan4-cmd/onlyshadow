-- =============================================================================
-- S.S.I. SHADOW - Fact: Daily P&L with CM3
-- =============================================================================
-- Calculates real Contribution Margin (CM1, CM2, CM3) - not just ROAS.
--
-- Margin Levels:
--   CM1 (Gross Margin) = Revenue - COGS
--   CM2 (After Marketing) = CM1 - Ad Spend
--   CM3 (Net Contribution) = CM2 - Payment Fees - Shipping - Other Variable Costs
--
-- This is the TRUE profitability metric, not the misleading ROAS!
--
-- Example:
--   ROAS = 3.0x (looks good!)
--   But CM3 = -5% (actually losing money on every sale)
--
-- =============================================================================

{{
  config(
    materialized='table',
    schema='finance',
    partition_by={
      'field': 'date',
      'data_type': 'date',
      'granularity': 'month'
    },
    cluster_by=['platform', 'campaign_id']
  )
}}

-- Get date spine
WITH date_spine AS (
    SELECT date
    FROM UNNEST(
        GENERATE_DATE_ARRAY(
            DATE_SUB(CURRENT_DATE(), INTERVAL 365 DAY),
            CURRENT_DATE()
        )
    ) AS date
),

-- Aggregate orders by date and attribution
orders_agg AS (
    SELECT
        order_date AS date,
        COALESCE(utm_source, 'organic') AS source,
        COALESCE(utm_medium, 'none') AS medium,
        COALESCE(campaign_id, 'unknown') AS campaign_id,
        
        -- Revenue metrics
        COUNT(*) AS orders,
        SUM(gross_revenue) AS gross_revenue,
        SUM(net_revenue) AS net_revenue,
        SUM(total_refunded) AS refunds,
        SUM(total_discounts) AS discounts,
        
        -- Cost metrics
        SUM(cogs) AS cogs,
        SUM(shipping_collected) AS shipping_revenue,
        SUM(tax_collected) AS tax_collected,
        
        -- Item metrics
        SUM(total_items) AS items_sold,
        
        -- Customer metrics
        COUNT(DISTINCT customer_id) AS unique_customers,
        COUNTIF(is_first_order) AS new_customers
        
    FROM {{ ref('stg_shopify_orders') }}
    GROUP BY 1, 2, 3, 4
),

-- Aggregate payment fees by date
payment_fees_agg AS (
    SELECT
        transaction_date AS date,
        COALESCE(campaign_id, 'unknown') AS campaign_id,
        
        SUM(stripe_fee) AS payment_processing_fees,
        SUM(platform_fee) AS platform_fees,
        COUNT(*) AS transactions
        
    FROM {{ ref('stg_stripe_charges') }}
    GROUP BY 1, 2
),

-- Aggregate ad spend by date and campaign
ad_spend_agg AS (
    SELECT
        spend_date AS date,
        platform,
        campaign_id,
        campaign_name,
        
        SUM(spend) AS ad_spend,
        SUM(impressions) AS impressions,
        SUM(clicks) AS clicks,
        SUM(conversions) AS platform_conversions,
        SUM(conversion_value) AS platform_conversion_value
        
    FROM {{ ref('stg_ad_spend') }}
    GROUP BY 1, 2, 3, 4
),

-- Join everything together
combined AS (
    SELECT
        d.date,
        
        -- Attribution
        COALESCE(a.platform, o.source) AS platform,
        COALESCE(a.campaign_id, o.campaign_id, 'unknown') AS campaign_id,
        COALESCE(a.campaign_name, 'Unknown Campaign') AS campaign_name,
        
        -- Revenue (from orders)
        COALESCE(o.orders, 0) AS orders,
        COALESCE(o.gross_revenue, 0) AS gross_revenue,
        COALESCE(o.net_revenue, 0) AS net_revenue,
        COALESCE(o.refunds, 0) AS refunds,
        COALESCE(o.discounts, 0) AS discounts,
        
        -- COGS
        COALESCE(o.cogs, 0) AS cogs,
        
        -- Ad Spend
        COALESCE(a.ad_spend, 0) AS ad_spend,
        
        -- Payment Fees
        COALESCE(p.payment_processing_fees, 0) AS payment_processing_fees,
        COALESCE(p.platform_fees, 0) AS platform_fees,
        
        -- Shipping costs (estimate as 10% of shipping revenue if not tracked)
        COALESCE(o.shipping_revenue, 0) * 0.9 AS shipping_cost_estimate,
        
        -- Platform metrics
        COALESCE(a.impressions, 0) AS impressions,
        COALESCE(a.clicks, 0) AS clicks,
        COALESCE(a.platform_conversions, 0) AS platform_reported_conversions,
        
        -- Customer metrics
        COALESCE(o.unique_customers, 0) AS unique_customers,
        COALESCE(o.new_customers, 0) AS new_customers,
        COALESCE(o.items_sold, 0) AS items_sold
        
    FROM date_spine d
    LEFT JOIN ad_spend_agg a ON d.date = a.date
    LEFT JOIN orders_agg o ON d.date = o.date 
        AND (
            o.campaign_id = a.campaign_id 
            OR (a.campaign_id IS NULL AND o.campaign_id = 'unknown')
        )
    LEFT JOIN payment_fees_agg p ON d.date = p.date 
        AND p.campaign_id = COALESCE(a.campaign_id, o.campaign_id, 'unknown')
    WHERE d.date <= CURRENT_DATE()
)

SELECT
    date,
    platform,
    campaign_id,
    campaign_name,
    
    -- ==========================================================================
    -- REVENUE METRICS
    -- ==========================================================================
    orders,
    gross_revenue,
    net_revenue,
    refunds,
    discounts,
    
    -- ==========================================================================
    -- COST METRICS
    -- ==========================================================================
    cogs,
    ad_spend,
    payment_processing_fees,
    platform_fees,
    shipping_cost_estimate,
    
    -- Total variable costs
    cogs + payment_processing_fees + platform_fees + shipping_cost_estimate AS total_variable_costs,
    
    -- ==========================================================================
    -- CONTRIBUTION MARGINS
    -- ==========================================================================
    
    -- CM1: Gross Margin (Revenue - COGS)
    net_revenue - cogs AS cm1_gross_margin,
    SAFE_DIVIDE(net_revenue - cogs, net_revenue) AS cm1_pct,
    
    -- CM2: After Marketing (CM1 - Ad Spend)
    net_revenue - cogs - ad_spend AS cm2_after_marketing,
    SAFE_DIVIDE(net_revenue - cogs - ad_spend, net_revenue) AS cm2_pct,
    
    -- CM3: Net Contribution (CM2 - All Variable Costs)
    net_revenue - cogs - ad_spend - payment_processing_fees - platform_fees - shipping_cost_estimate AS cm3_net_contribution,
    SAFE_DIVIDE(
        net_revenue - cogs - ad_spend - payment_processing_fees - platform_fees - shipping_cost_estimate,
        net_revenue
    ) AS cm3_pct,
    
    -- ==========================================================================
    -- EFFICIENCY METRICS
    -- ==========================================================================
    
    -- Traditional ROAS (for comparison)
    SAFE_DIVIDE(gross_revenue, ad_spend) AS roas,
    
    -- Real ROAS (based on CM3)
    -- This is what actually matters!
    SAFE_DIVIDE(cm3_net_contribution + ad_spend, ad_spend) AS real_roas,
    
    -- Cost per Order
    SAFE_DIVIDE(ad_spend, orders) AS cpo,
    
    -- Customer Acquisition Cost (only new customers)
    SAFE_DIVIDE(ad_spend, NULLIF(new_customers, 0)) AS cac,
    
    -- Average Order Value
    SAFE_DIVIDE(net_revenue, orders) AS aov,
    
    -- Profit per Order
    SAFE_DIVIDE(cm3_net_contribution, orders) AS profit_per_order,
    
    -- ==========================================================================
    -- PLATFORM METRICS
    -- ==========================================================================
    impressions,
    clicks,
    platform_reported_conversions,
    
    -- CTR
    SAFE_DIVIDE(clicks, impressions) AS ctr,
    
    -- CVR (Conversion Rate)
    SAFE_DIVIDE(orders, clicks) AS cvr,
    
    -- CPC
    SAFE_DIVIDE(ad_spend, clicks) AS cpc,
    
    -- CPM
    SAFE_DIVIDE(ad_spend, impressions) * 1000 AS cpm,
    
    -- ==========================================================================
    -- CUSTOMER METRICS
    -- ==========================================================================
    unique_customers,
    new_customers,
    items_sold,
    
    -- Items per Order
    SAFE_DIVIDE(items_sold, orders) AS items_per_order,
    
    -- ==========================================================================
    -- DATE DIMENSIONS
    -- ==========================================================================
    FORMAT_DATE('%Y-%m', date) AS month,
    FORMAT_DATE('%Y-W%V', date) AS week,
    EXTRACT(DAYOFWEEK FROM date) AS day_of_week,
    
    -- ==========================================================================
    -- FLAGS
    -- ==========================================================================
    
    -- Is this campaign profitable?
    cm3_net_contribution > 0 AS is_profitable,
    
    -- Red flags
    CASE
        WHEN cm3_pct < -0.2 THEN 'critical_loss'
        WHEN cm3_pct < 0 THEN 'losing_money'
        WHEN cm3_pct < 0.1 THEN 'low_margin'
        WHEN cm3_pct < 0.2 THEN 'acceptable'
        ELSE 'healthy'
    END AS profitability_status,
    
    -- ROAS vs Reality gap (how misleading is ROAS?)
    SAFE_DIVIDE(roas, real_roas) - 1 AS roas_gap_pct,
    
    -- Metadata
    CURRENT_TIMESTAMP() AS updated_at

FROM combined
WHERE gross_revenue > 0 OR ad_spend > 0

-- Final column aliases for clarity
