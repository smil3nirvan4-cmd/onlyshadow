-- =============================================================================
-- S.S.I. SHADOW - Staging: Shopify Orders
-- =============================================================================
-- Standardizes Shopify order data including COGS (Cost of Goods Sold).
-- Source: Shopify webhook data or API sync
-- =============================================================================

{{
  config(
    materialized='view',
    schema='staging'
  )
}}

WITH source AS (
    SELECT
        *
    FROM {{ source('shopify', 'orders') }}
    WHERE cancelled_at IS NULL
      AND financial_status IN ('paid', 'partially_refunded')
),

-- Extract line items to calculate COGS
line_items AS (
    SELECT
        order_id,
        SUM(CAST(JSON_EXTRACT_SCALAR(item, '$.quantity') AS INT64)) AS total_items,
        SUM(
            CAST(JSON_EXTRACT_SCALAR(item, '$.quantity') AS INT64) *
            COALESCE(
                CAST(JSON_EXTRACT_SCALAR(item, '$.cost') AS FLOAT64),
                -- Fallback: estimate COGS as 40% of price
                CAST(JSON_EXTRACT_SCALAR(item, '$.price') AS FLOAT64) * 0.4
            )
        ) AS total_cogs,
        SUM(
            CAST(JSON_EXTRACT_SCALAR(item, '$.quantity') AS INT64) *
            CAST(JSON_EXTRACT_SCALAR(item, '$.price') AS FLOAT64)
        ) AS total_line_item_value
    FROM source,
    UNNEST(JSON_EXTRACT_ARRAY(line_items, '$')) AS item
    GROUP BY order_id
),

-- Extract discount codes
discounts AS (
    SELECT
        order_id,
        STRING_AGG(JSON_EXTRACT_SCALAR(dc, '$.code'), ', ') AS discount_codes,
        SUM(CAST(JSON_EXTRACT_SCALAR(dc, '$.amount') AS FLOAT64)) AS total_discount
    FROM source,
    UNNEST(JSON_EXTRACT_ARRAY(discount_codes, '$')) AS dc
    GROUP BY order_id
),

cleaned AS (
    SELECT
        -- IDs
        o.id AS shopify_order_id,
        o.order_number,
        o.name AS order_name,
        o.checkout_id,
        JSON_EXTRACT_SCALAR(o.customer, '$.id') AS customer_id,
        JSON_EXTRACT_SCALAR(o.customer, '$.email') AS customer_email,
        
        -- Amounts
        CAST(o.total_price AS FLOAT64) AS gross_revenue,
        CAST(o.subtotal_price AS FLOAT64) AS subtotal,
        CAST(o.total_tax AS FLOAT64) AS tax_collected,
        CAST(o.total_discounts AS FLOAT64) AS total_discounts,
        CAST(o.total_shipping_price_set.shop_money.amount AS FLOAT64) AS shipping_collected,
        
        -- Refunds
        COALESCE(
            (SELECT SUM(CAST(r.amount AS FLOAT64)) 
             FROM UNNEST(JSON_EXTRACT_ARRAY(o.refunds, '$')) AS r),
            0
        ) AS total_refunded,
        
        -- COGS from line items
        COALESCE(li.total_cogs, 0) AS cogs,
        li.total_items,
        
        -- Discounts
        d.discount_codes,
        COALESCE(d.total_discount, 0) AS discount_amount,
        
        -- Currency
        o.currency,
        
        -- Status
        o.financial_status,
        o.fulfillment_status,
        
        -- Timestamps
        TIMESTAMP(o.created_at) AS created_at,
        TIMESTAMP(o.processed_at) AS processed_at,
        
        -- Attribution
        o.landing_site,
        o.referring_site,
        JSON_EXTRACT_SCALAR(o.note_attributes, '$.campaign_id') AS campaign_id,
        JSON_EXTRACT_SCALAR(o.note_attributes, '$.fbclid') AS fbclid,
        JSON_EXTRACT_SCALAR(o.note_attributes, '$.gclid') AS gclid,
        o.source_name,
        
        -- UTM params
        REGEXP_EXTRACT(o.landing_site, r'utm_source=([^&]+)') AS utm_source,
        REGEXP_EXTRACT(o.landing_site, r'utm_medium=([^&]+)') AS utm_medium,
        REGEXP_EXTRACT(o.landing_site, r'utm_campaign=([^&]+)') AS utm_campaign
        
    FROM source o
    LEFT JOIN line_items li ON o.id = li.order_id
    LEFT JOIN discounts d ON o.id = d.order_id
)

SELECT
    *,
    -- Net revenue after refunds and discounts
    gross_revenue - total_refunded AS net_revenue,
    
    -- Gross margin
    (gross_revenue - total_refunded - cogs) AS gross_profit,
    
    -- Margin percentage
    SAFE_DIVIDE(
        (gross_revenue - total_refunded - cogs),
        (gross_revenue - total_refunded)
    ) AS gross_margin_pct,
    
    -- Date dimensions
    DATE(created_at) AS order_date,
    FORMAT_DATE('%Y-%m', DATE(created_at)) AS order_month,
    EXTRACT(DAYOFWEEK FROM created_at) AS day_of_week,
    EXTRACT(HOUR FROM created_at) AS hour_of_day,
    
    -- First order flag (requires customer history)
    -- Will be enriched in intermediate model
    FALSE AS is_first_order

FROM cleaned
