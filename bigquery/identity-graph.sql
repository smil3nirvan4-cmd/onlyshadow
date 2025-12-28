-- =============================================================================
-- S.S.I. SHADOW — Identity Graph & Attribution Recovery
-- Queries para probabilistic identity matching e recuperação de conversões
-- =============================================================================

-- =============================================================================
-- 1. IDENTITY GRAPH - Unificação de IDs
-- =============================================================================

-- Cria tabela de Identity Graph unificado
CREATE OR REPLACE TABLE `{PROJECT_ID}.ssi_shadow.identity_graph` AS

WITH raw_identities AS (
    -- Agrupa todos os identificadores por ssi_id
    SELECT
        ssi_id,
        ARRAY_AGG(DISTINCT fbp IGNORE NULLS) AS fbp_ids,
        ARRAY_AGG(DISTINCT fbc IGNORE NULLS) AS fbc_ids,
        ARRAY_AGG(DISTINCT JSON_EXTRACT_SCALAR(custom_data, '$.canvas_hash') IGNORE NULLS) AS canvas_hashes,
        ARRAY_AGG(DISTINCT JSON_EXTRACT_SCALAR(custom_data, '$.webgl_hash') IGNORE NULLS) AS webgl_hashes,
        MIN(event_time) AS first_seen,
        MAX(event_time) AS last_seen,
        COUNT(DISTINCT DATE(event_time)) AS session_count,
        COUNTIF(event_name = 'Purchase') AS purchase_count,
        SUM(CASE WHEN event_name = 'Purchase' 
            THEN CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) 
            ELSE 0 END) AS total_revenue
    FROM `{PROJECT_ID}.ssi_shadow.events`
    WHERE ssi_id IS NOT NULL
        AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
    GROUP BY ssi_id
),

-- Identifica clusters de identidade baseado em fingerprints compartilhados
canvas_clusters AS (
    SELECT
        canvas_hash,
        ARRAY_AGG(DISTINCT ssi_id) AS related_ssi_ids
    FROM `{PROJECT_ID}.ssi_shadow.events`,
    UNNEST([JSON_EXTRACT_SCALAR(custom_data, '$.canvas_hash')]) AS canvas_hash
    WHERE canvas_hash IS NOT NULL
        AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
    GROUP BY canvas_hash
    HAVING COUNT(DISTINCT ssi_id) > 1  -- Apenas se há múltiplos IDs
),

-- Merge identities que compartilham canvas_hash
merged_identities AS (
    SELECT
        r.ssi_id,
        r.fbp_ids,
        r.fbc_ids,
        r.canvas_hashes,
        r.webgl_hashes,
        r.first_seen,
        r.last_seen,
        r.session_count,
        r.purchase_count,
        r.total_revenue,
        -- IDs relacionados via canvas_hash
        (
            SELECT ARRAY_AGG(DISTINCT related_id)
            FROM canvas_clusters c,
            UNNEST(c.related_ssi_ids) AS related_id
            WHERE EXISTS (
                SELECT 1 FROM UNNEST(r.canvas_hashes) AS ch
                WHERE ch = c.canvas_hash
            )
            AND related_id != r.ssi_id
        ) AS related_ssi_ids
    FROM raw_identities r
)

SELECT
    ssi_id,
    fbp_ids,
    fbc_ids,
    canvas_hashes,
    webgl_hashes,
    first_seen,
    last_seen,
    session_count,
    purchase_count,
    total_revenue,
    COALESCE(related_ssi_ids, []) AS related_ssi_ids,
    -- Master ID (o mais antigo do cluster)
    COALESCE(
        (SELECT MIN(id) FROM UNNEST(related_ssi_ids) AS id),
        ssi_id
    ) AS master_ssi_id,
    CURRENT_TIMESTAMP() AS updated_at
FROM merged_identities;


-- =============================================================================
-- 2. RECUPERAÇÃO DE FBC (Attribution Recovery)
-- =============================================================================

-- Atualiza eventos sem fbc baseado em canvas_hash compartilhado
-- Janela: 30 minutos (evita atribuição incorreta)

CREATE OR REPLACE PROCEDURE `{PROJECT_ID}.ssi_shadow.recover_fbc_attribution`()
BEGIN
    -- Eventos com fbc que podem ser fonte de atribuição
    CREATE TEMP TABLE fbc_sources AS
    SELECT 
        JSON_EXTRACT_SCALAR(custom_data, '$.canvas_hash') AS canvas_hash,
        fbc,
        event_time,
        ssi_id
    FROM `{PROJECT_ID}.ssi_shadow.events`
    WHERE fbc IS NOT NULL
        AND JSON_EXTRACT_SCALAR(custom_data, '$.canvas_hash') IS NOT NULL
        AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR);
    
    -- Update eventos sem fbc
    UPDATE `{PROJECT_ID}.ssi_shadow.events` target
    SET 
        fbc = source.fbc,
        custom_data = JSON_SET(
            COALESCE(custom_data, '{}'),
            '$.fbc_recovered', TRUE,
            '$.fbc_source_ssi_id', source.ssi_id
        )
    FROM (
        SELECT 
            t.event_id,
            s.fbc,
            s.ssi_id,
            ROW_NUMBER() OVER (
                PARTITION BY t.event_id 
                ORDER BY ABS(TIMESTAMP_DIFF(t.event_time, s.event_time, MINUTE))
            ) AS rn
        FROM `{PROJECT_ID}.ssi_shadow.events` t
        INNER JOIN fbc_sources s
            ON JSON_EXTRACT_SCALAR(t.custom_data, '$.canvas_hash') = s.canvas_hash
        WHERE t.fbc IS NULL
            AND t.event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
            -- Janela de 30 minutos para evitar atribuição incorreta
            AND ABS(TIMESTAMP_DIFF(t.event_time, s.event_time, MINUTE)) <= 30
    ) source
    WHERE target.event_id = source.event_id
        AND source.rn = 1;  -- Apenas o match mais próximo
    
    -- Log de execução
    INSERT INTO `{PROJECT_ID}.ssi_shadow.job_logs` (job_name, executed_at, rows_affected)
    SELECT 
        'recover_fbc_attribution',
        CURRENT_TIMESTAMP(),
        @@row_count;
END;


-- =============================================================================
-- 3. PROBABILISTIC IDENTITY MATCHING
-- =============================================================================

-- View para match probabilístico quando não há fingerprint
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_probabilistic_matches` AS

WITH event_signatures AS (
    SELECT
        ssi_id,
        -- Signature baseada em IP + UA + Geo + Device
        FARM_FINGERPRINT(CONCAT(
            COALESCE(ip_hash, ''),
            '|',
            COALESCE(SUBSTR(ua, 1, 100), ''),
            '|',
            COALESCE(country, ''),
            '|',
            COALESCE(device_type, '')
        )) AS prob_signature,
        event_time,
        fbc,
        fbp
    FROM `{PROJECT_ID}.ssi_shadow.events`
    WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
),

-- Identifica matches probabilísticos
signature_clusters AS (
    SELECT
        prob_signature,
        ARRAY_AGG(DISTINCT ssi_id) AS ssi_ids,
        ARRAY_AGG(DISTINCT fbc IGNORE NULLS) AS fbc_pool,
        ARRAY_AGG(DISTINCT fbp IGNORE NULLS) AS fbp_pool,
        COUNT(DISTINCT ssi_id) AS unique_ids,
        COUNT(*) AS event_count
    FROM event_signatures
    GROUP BY prob_signature
    HAVING COUNT(DISTINCT ssi_id) > 1  -- Múltiplos IDs = possível mesmo usuário
)

SELECT
    prob_signature,
    ssi_ids,
    fbc_pool,
    fbp_pool,
    unique_ids,
    event_count,
    -- Confidence score baseado em consistência
    CASE
        WHEN ARRAY_LENGTH(fbc_pool) = 1 THEN 0.8  -- Mesmo fbc = alta confiança
        WHEN ARRAY_LENGTH(fbp_pool) = 1 THEN 0.7  -- Mesmo fbp = média-alta
        WHEN unique_ids = 2 THEN 0.5               -- Só 2 IDs = média
        ELSE 0.3                                   -- Muitos IDs = baixa
    END AS match_confidence
FROM signature_clusters
WHERE unique_ids <= 5;  -- Muitos IDs = provavelmente IP compartilhado (empresa/proxy)


-- =============================================================================
-- 4. ATTRIBUTION REPORTING
-- =============================================================================

-- View de conversões com atribuição recuperada
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_attributed_conversions` AS

SELECT
    e.event_id,
    e.event_name,
    e.event_time,
    e.ssi_id,
    
    -- Attribution IDs (original ou recuperado)
    COALESCE(e.fbc, recovered.fbc) AS attributed_fbc,
    COALESCE(e.fbp, recovered.fbp) AS attributed_fbp,
    e.gclid,
    e.ttclid,
    
    -- Source
    CASE
        WHEN e.fbc IS NOT NULL THEN 'direct_fbc'
        WHEN recovered.fbc IS NOT NULL THEN 'recovered_fbc'
        WHEN e.fbclid IS NOT NULL THEN 'fbclid'
        WHEN e.gclid IS NOT NULL THEN 'gclid'
        WHEN e.ttclid IS NOT NULL THEN 'ttclid'
        ELSE 'organic'
    END AS attribution_source,
    
    -- Recovery metadata
    JSON_EXTRACT_SCALAR(e.custom_data, '$.fbc_recovered') AS was_recovered,
    
    -- Value
    CAST(JSON_EXTRACT_SCALAR(e.custom_data, '$.value') AS FLOAT64) AS value,
    JSON_EXTRACT_SCALAR(e.custom_data, '$.currency') AS currency,
    
    -- Quality
    e.trust_score,
    
    -- Identity
    ig.master_ssi_id,
    ARRAY_LENGTH(ig.related_ssi_ids) AS identity_cluster_size

FROM `{PROJECT_ID}.ssi_shadow.events` e
LEFT JOIN `{PROJECT_ID}.ssi_shadow.identity_graph` ig
    ON e.ssi_id = ig.ssi_id
LEFT JOIN (
    -- Subquery para recuperação de fbc via identity graph
    SELECT 
        ssi_id,
        (SELECT fbc FROM UNNEST(fbc_ids) AS fbc LIMIT 1) AS fbc,
        (SELECT fbp FROM UNNEST(fbp_ids) AS fbp LIMIT 1) AS fbp
    FROM `{PROJECT_ID}.ssi_shadow.identity_graph`
    WHERE ARRAY_LENGTH(fbc_ids) > 0
) recovered
    ON e.ssi_id = recovered.ssi_id

WHERE e.event_name IN ('Purchase', 'Lead', 'InitiateCheckout', 'AddToCart')
    AND e.event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY);


-- =============================================================================
-- 5. MÉTRICAS DE IDENTITY RESOLUTION
-- =============================================================================

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_identity_metrics` AS

SELECT
    DATE(CURRENT_TIMESTAMP()) AS report_date,
    
    -- Total de identidades
    COUNT(DISTINCT ssi_id) AS total_identities,
    
    -- Com fingerprint
    COUNTIF(ARRAY_LENGTH(canvas_hashes) > 0) AS with_canvas_hash,
    COUNTIF(ARRAY_LENGTH(webgl_hashes) > 0) AS with_webgl_hash,
    
    -- Com attribution IDs
    COUNTIF(ARRAY_LENGTH(fbc_ids) > 0) AS with_fbc,
    COUNTIF(ARRAY_LENGTH(fbp_ids) > 0) AS with_fbp,
    
    -- Clusters (identidades relacionadas)
    COUNTIF(ARRAY_LENGTH(related_ssi_ids) > 0) AS in_cluster,
    AVG(CASE WHEN ARRAY_LENGTH(related_ssi_ids) > 0 
        THEN ARRAY_LENGTH(related_ssi_ids) + 1 ELSE NULL END) AS avg_cluster_size,
    
    -- Conversões
    COUNTIF(purchase_count > 0) AS converters,
    SUM(purchase_count) AS total_purchases,
    SUM(total_revenue) AS total_revenue,
    
    -- Match rate estimado
    SAFE_DIVIDE(
        COUNTIF(ARRAY_LENGTH(fbc_ids) > 0 OR ARRAY_LENGTH(canvas_hashes) > 0),
        COUNT(*)
    ) AS estimated_match_rate

FROM `{PROJECT_ID}.ssi_shadow.identity_graph`;


-- =============================================================================
-- 6. SCHEDULED JOBS
-- =============================================================================

-- Agendar no BigQuery (ou via Cloud Scheduler):

-- 1. Atualizar Identity Graph - a cada 4 horas
-- CALL `{PROJECT_ID}.ssi_shadow.update_identity_graph`();

-- 2. Recuperar atribuição FBC - a cada 1 hora
-- CALL `{PROJECT_ID}.ssi_shadow.recover_fbc_attribution`();

-- 3. Cleanup de dados antigos - diário
-- DELETE FROM `{PROJECT_ID}.ssi_shadow.events` WHERE event_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 180 DAY);


-- =============================================================================
-- 7. TABELA DE LOGS
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{PROJECT_ID}.ssi_shadow.job_logs` (
    job_name STRING,
    executed_at TIMESTAMP,
    rows_affected INT64,
    error_message STRING
);
