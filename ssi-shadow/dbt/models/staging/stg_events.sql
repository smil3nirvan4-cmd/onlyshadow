-- models/staging/stg_events.sql
-- Eventos limpos e validados

{{
    config(
        materialized='incremental',
        unique_key='event_id',
        partition_by={
            "field": "event_time",
            "data_type": "timestamp",
            "granularity": "day"
        },
        cluster_by=['event_name', 'ssi_id']
    )
}}

WITH source AS (
    SELECT *
    FROM {{ source('raw', 'events') }}
    {% if is_incremental() %}
    WHERE event_time > (SELECT MAX(event_time) FROM {{ this }})
    {% endif %}
),

cleaned AS (
    SELECT
        event_id,
        event_name,
        event_time,
        ssi_id,
        
        -- URLs limpas
        REGEXP_REPLACE(url, r'\?.*', '') AS url_clean,
        url AS url_full,
        referrer,
        
        -- Click IDs
        fbclid,
        gclid,
        ttclid,
        utm_source,
        utm_medium,
        utm_campaign,
        
        -- Cookies
        fbp,
        fbc,
        
        -- Device
        device_type,
        browser,
        os,
        
        -- Geo
        country,
        region,
        city,
        
        -- Fingerprints
        canvas_hash,
        webgl_hash,
        
        -- PII hashes
        email_hash,
        phone_hash,
        
        -- Scores (com default)
        COALESCE(trust_score, 0.5) AS trust_score,
        COALESCE(intent_score, 0.5) AS intent_score,
        COALESCE(ltv_score, 0.5) AS ltv_score,
        
        -- Custom data
        custom_data,
        
        -- Extrair valor se for Purchase
        CASE 
            WHEN event_name = 'Purchase' 
            THEN SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64)
            ELSE NULL 
        END AS event_value,
        
        -- Metadata
        processed_at,
        
        -- Flags derivados
        trust_score < 0.4 AS is_suspicious,
        trust_score < 0.25 AS is_blocked,
        fbclid IS NOT NULL AS has_fbclid,
        gclid IS NOT NULL AS has_gclid,
        email_hash IS NOT NULL AS has_email,
        phone_hash IS NOT NULL AS has_phone
        
    FROM source
    WHERE 
        -- Filtrar eventos inválidos
        event_id IS NOT NULL
        AND ssi_id IS NOT NULL
        AND event_time IS NOT NULL
        -- Filtrar tráfego claramente inválido
        AND (trust_score IS NULL OR trust_score >= 0.1)
)

SELECT * FROM cleaned
