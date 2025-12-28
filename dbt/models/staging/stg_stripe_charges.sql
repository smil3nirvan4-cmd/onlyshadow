-- =============================================================================
-- S.S.I. SHADOW - Staging: Stripe Transactions
-- =============================================================================
-- Standardizes Stripe payment data for financial calculations.
-- Source: Stripe webhook data or API sync
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
    FROM {{ source('stripe', 'charges') }}
    WHERE status = 'succeeded'
),

cleaned AS (
    SELECT
        -- IDs
        id AS stripe_charge_id,
        payment_intent AS stripe_payment_intent_id,
        customer AS stripe_customer_id,
        COALESCE(
            JSON_EXTRACT_SCALAR(metadata, '$.order_id'),
            invoice
        ) AS order_id,
        
        -- Amounts (Stripe stores in cents)
        CAST(amount AS FLOAT64) / 100 AS gross_amount,
        CAST(amount_captured AS FLOAT64) / 100 AS captured_amount,
        CAST(amount_refunded AS FLOAT64) / 100 AS refunded_amount,
        CAST(application_fee_amount AS FLOAT64) / 100 AS platform_fee,
        
        -- Net calculation
        (CAST(amount_captured AS FLOAT64) - CAST(amount_refunded AS FLOAT64)) / 100 AS net_amount,
        
        -- Currency
        UPPER(currency) AS currency,
        
        -- Fees (from balance transaction if available)
        CAST(
            COALESCE(
                JSON_EXTRACT_SCALAR(balance_transaction, '$.fee'),
                '0'
            ) AS FLOAT64
        ) / 100 AS stripe_fee,
        
        -- Payment method
        JSON_EXTRACT_SCALAR(payment_method_details, '$.type') AS payment_method_type,
        JSON_EXTRACT_SCALAR(payment_method_details, '$.card.brand') AS card_brand,
        
        -- Status
        status,
        refunded AS is_fully_refunded,
        disputed AS is_disputed,
        
        -- Timestamps
        TIMESTAMP_SECONDS(created) AS created_at,
        
        -- Metadata for attribution
        JSON_EXTRACT_SCALAR(metadata, '$.campaign_id') AS campaign_id,
        JSON_EXTRACT_SCALAR(metadata, '$.fbclid') AS fbclid,
        JSON_EXTRACT_SCALAR(metadata, '$.gclid') AS gclid,
        JSON_EXTRACT_SCALAR(metadata, '$.utm_source') AS utm_source,
        JSON_EXTRACT_SCALAR(metadata, '$.utm_medium') AS utm_medium,
        JSON_EXTRACT_SCALAR(metadata, '$.utm_campaign') AS utm_campaign
        
    FROM source
)

SELECT
    *,
    -- Calculate actual received amount after all fees
    net_amount - COALESCE(stripe_fee, 0) - COALESCE(platform_fee, 0) AS received_amount,
    
    -- Date dimensions
    DATE(created_at) AS transaction_date,
    FORMAT_DATE('%Y-%m', DATE(created_at)) AS transaction_month,
    EXTRACT(DAYOFWEEK FROM created_at) AS day_of_week,
    EXTRACT(HOUR FROM created_at) AS hour_of_day

FROM cleaned
