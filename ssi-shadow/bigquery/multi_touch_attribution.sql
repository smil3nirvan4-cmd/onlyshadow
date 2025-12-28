-- =============================================================================
-- S.S.I. SHADOW — MULTI-TOUCH ATTRIBUTION (MTA)
-- =============================================================================
--
-- Modelos de Atribuição:
-- 1. Last Touch (baseline)
-- 2. First Touch
-- 3. Linear
-- 4. Time Decay
-- 5. Position Based (U-Shaped)
-- 6. Shapley Value (data-driven)
-- 7. Markov Chain (probabilistic)
--
-- =============================================================================

-- =============================================================================
-- 1. VIEW: JORNADAS DE CONVERSÃO
-- =============================================================================

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_conversion_journeys` AS
WITH 
-- Identificar touchpoints por usuário
user_touchpoints AS (
    SELECT
        ssi_id,
        event_time,
        event_name,
        
        -- Canal de aquisição
        CASE
            WHEN fbclid IS NOT NULL THEN 'meta_paid'
            WHEN gclid IS NOT NULL THEN 'google_paid'
            WHEN ttclid IS NOT NULL THEN 'tiktok_paid'
            WHEN utm_source = 'google' AND utm_medium = 'organic' THEN 'google_organic'
            WHEN utm_source = 'facebook' THEN 'meta_organic'
            WHEN referrer LIKE '%google%' THEN 'google_organic'
            WHEN referrer LIKE '%facebook%' OR referrer LIKE '%fb.%' THEN 'meta_organic'
            WHEN referrer IS NULL OR referrer = '' THEN 'direct'
            ELSE 'other'
        END as channel,
        
        -- Campanha
        COALESCE(
            JSON_EXTRACT_SCALAR(custom_data, '$.campaign_id'),
            utm_campaign
        ) as campaign_id,
        
        -- Valor da conversão
        CASE WHEN event_name = 'Purchase' 
            THEN SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64)
            ELSE NULL 
        END as conversion_value
        
    FROM `{PROJECT_ID}.ssi_shadow.events`
    WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
),

-- Ordenar touchpoints por usuário
ordered_touchpoints AS (
    SELECT
        *,
        ROW_NUMBER() OVER (PARTITION BY ssi_id ORDER BY event_time) as touchpoint_order,
        COUNT(*) OVER (PARTITION BY ssi_id) as total_touchpoints,
        MAX(conversion_value) OVER (PARTITION BY ssi_id) as journey_value,
        MAX(CASE WHEN event_name = 'Purchase' THEN 1 ELSE 0 END) 
            OVER (PARTITION BY ssi_id) as converted
    FROM user_touchpoints
    WHERE channel != 'other'  -- Filtrar touchpoints sem canal identificável
)

SELECT
    ssi_id,
    channel,
    campaign_id,
    touchpoint_order,
    total_touchpoints,
    event_time,
    journey_value,
    converted,
    
    -- Posição relativa (0 = primeiro, 1 = último)
    SAFE_DIVIDE(touchpoint_order - 1, total_touchpoints - 1) as relative_position,
    
    -- Tempo até conversão (para time decay)
    TIMESTAMP_DIFF(
        MAX(CASE WHEN event_name = 'Purchase' THEN event_time END) OVER (PARTITION BY ssi_id),
        event_time,
        HOUR
    ) as hours_to_conversion
    
FROM ordered_touchpoints
WHERE total_touchpoints >= 1;

-- =============================================================================
-- 2. VIEW: ATRIBUIÇÃO LAST-TOUCH
-- =============================================================================

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_attribution_last_touch` AS
SELECT
    channel,
    campaign_id,
    
    -- Métricas
    COUNT(DISTINCT ssi_id) as conversions,
    SUM(journey_value) as attributed_value,
    AVG(journey_value) as avg_order_value
    
FROM `{PROJECT_ID}.ssi_shadow.v_conversion_journeys`
WHERE converted = 1
  AND touchpoint_order = total_touchpoints  -- Último touchpoint
GROUP BY channel, campaign_id;

-- =============================================================================
-- 3. VIEW: ATRIBUIÇÃO FIRST-TOUCH
-- =============================================================================

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_attribution_first_touch` AS
SELECT
    channel,
    campaign_id,
    
    COUNT(DISTINCT ssi_id) as conversions,
    SUM(journey_value) as attributed_value,
    AVG(journey_value) as avg_order_value
    
FROM `{PROJECT_ID}.ssi_shadow.v_conversion_journeys`
WHERE converted = 1
  AND touchpoint_order = 1  -- Primeiro touchpoint
GROUP BY channel, campaign_id;

-- =============================================================================
-- 4. VIEW: ATRIBUIÇÃO LINEAR
-- =============================================================================

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_attribution_linear` AS
SELECT
    channel,
    campaign_id,
    
    -- Crédito dividido igualmente entre touchpoints
    COUNT(DISTINCT ssi_id) / AVG(total_touchpoints) as fractional_conversions,
    SUM(journey_value / total_touchpoints) as attributed_value
    
FROM `{PROJECT_ID}.ssi_shadow.v_conversion_journeys`
WHERE converted = 1
GROUP BY channel, campaign_id;

-- =============================================================================
-- 5. VIEW: ATRIBUIÇÃO TIME DECAY
-- =============================================================================

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_attribution_time_decay` AS
WITH decay_weights AS (
    SELECT
        *,
        -- Peso exponencial: mais recente = mais peso
        -- Half-life de 7 dias (168 horas)
        EXP(-0.693 * hours_to_conversion / 168) as decay_weight
    FROM `{PROJECT_ID}.ssi_shadow.v_conversion_journeys`
    WHERE converted = 1
),
normalized_weights AS (
    SELECT
        *,
        decay_weight / SUM(decay_weight) OVER (PARTITION BY ssi_id) as normalized_weight
    FROM decay_weights
)
SELECT
    channel,
    campaign_id,
    
    SUM(normalized_weight) as fractional_conversions,
    SUM(journey_value * normalized_weight) as attributed_value
    
FROM normalized_weights
GROUP BY channel, campaign_id;

-- =============================================================================
-- 6. VIEW: ATRIBUIÇÃO POSITION-BASED (U-SHAPED)
-- =============================================================================
-- 40% primeiro, 40% último, 20% dividido entre intermediários

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_attribution_position_based` AS
WITH position_weights AS (
    SELECT
        *,
        CASE
            WHEN touchpoint_order = 1 THEN 0.4
            WHEN touchpoint_order = total_touchpoints THEN 0.4
            ELSE 0.2 / (total_touchpoints - 2)
        END as position_weight
    FROM `{PROJECT_ID}.ssi_shadow.v_conversion_journeys`
    WHERE converted = 1
      AND total_touchpoints >= 2
)
SELECT
    channel,
    campaign_id,
    
    SUM(position_weight) as fractional_conversions,
    SUM(journey_value * position_weight) as attributed_value
    
FROM position_weights
GROUP BY channel, campaign_id;

-- =============================================================================
-- 7. VIEW: ATRIBUIÇÃO SHAPLEY VALUE (Data-Driven)
-- =============================================================================
-- Shapley calcula a contribuição marginal de cada canal
-- considerando todas as combinações possíveis

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_attribution_shapley` AS
WITH 
-- Identificar jornadas únicas (combinações de canais)
journey_paths AS (
    SELECT
        ssi_id,
        journey_value,
        ARRAY_AGG(DISTINCT channel ORDER BY channel) as channels,
        ARRAY_LENGTH(ARRAY_AGG(DISTINCT channel)) as num_channels
    FROM `{PROJECT_ID}.ssi_shadow.v_conversion_journeys`
    WHERE converted = 1
    GROUP BY ssi_id, journey_value
),

-- Conversion rate por combinação de canais
coalition_values AS (
    SELECT
        channels,
        COUNT(*) as conversions,
        SUM(journey_value) as total_value,
        AVG(journey_value) as avg_value
    FROM journey_paths
    GROUP BY channels
),

-- Calcular contribuição marginal (simplificado)
-- Para cada canal, compara jornadas com vs sem o canal
marginal_contributions AS (
    SELECT
        channel,
        
        -- Contribuição quando canal está presente vs ausente
        AVG(CASE WHEN channel IN UNNEST(channels) THEN avg_value ELSE 0 END) as value_with,
        AVG(CASE WHEN channel NOT IN UNNEST(channels) THEN avg_value ELSE 0 END) as value_without
        
    FROM coalition_values
    CROSS JOIN (
        SELECT DISTINCT channel 
        FROM `{PROJECT_ID}.ssi_shadow.v_conversion_journeys`
    )
    GROUP BY channel
)

SELECT
    channel,
    
    -- Shapley value simplificado
    value_with - value_without as marginal_contribution,
    
    -- Normalizar para % do total
    (value_with - value_without) / NULLIF(SUM(value_with - value_without) OVER (), 0) as shapley_weight
    
FROM marginal_contributions
WHERE value_with > value_without;

-- =============================================================================
-- 8. VIEW: ATRIBUIÇÃO MARKOV CHAIN
-- =============================================================================
-- Modelo probabilístico baseado em transições entre canais

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_attribution_markov` AS
WITH 
-- Transições entre canais
transitions AS (
    SELECT
        ssi_id,
        channel as from_channel,
        LEAD(channel) OVER (PARTITION BY ssi_id ORDER BY event_time) as to_channel,
        converted
    FROM `{PROJECT_ID}.ssi_shadow.v_conversion_journeys`
),

-- Matriz de transição
transition_matrix AS (
    SELECT
        from_channel,
        to_channel,
        COUNT(*) as transitions,
        SUM(COUNT(*)) OVER (PARTITION BY from_channel) as total_from_channel
    FROM transitions
    WHERE to_channel IS NOT NULL
    GROUP BY from_channel, to_channel
),

-- Probabilidades de transição
transition_probabilities AS (
    SELECT
        from_channel,
        to_channel,
        SAFE_DIVIDE(transitions, total_from_channel) as probability
    FROM transition_matrix
),

-- Taxa de conversão por canal (probabilidade de ir para "conversion")
conversion_rates AS (
    SELECT
        from_channel as channel,
        SAFE_DIVIDE(
            COUNTIF(to_channel IS NULL AND converted = 1),  -- Conversão
            COUNT(*)
        ) as conversion_probability
    FROM transitions
    GROUP BY from_channel
),

-- Removal effect: taxa de conversão se removermos o canal
-- (aproximação simplificada)
removal_effect AS (
    SELECT
        channel,
        conversion_probability,
        1 - (1 - conversion_probability) * 0.8 as effect_multiplier  -- Simplificado
    FROM conversion_rates
)

SELECT
    channel,
    conversion_probability,
    effect_multiplier as removal_effect,
    
    -- Atribuição baseada no efeito de remoção
    effect_multiplier / NULLIF(SUM(effect_multiplier) OVER (), 0) as markov_attribution
    
FROM removal_effect;

-- =============================================================================
-- 9. VIEW: COMPARATIVO DE MODELOS
-- =============================================================================

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_attribution_comparison` AS
SELECT
    COALESCE(lt.channel, ft.channel, li.channel, td.channel, pb.channel) as channel,
    
    -- Last Touch
    lt.conversions as last_touch_conversions,
    lt.attributed_value as last_touch_value,
    
    -- First Touch
    ft.conversions as first_touch_conversions,
    ft.attributed_value as first_touch_value,
    
    -- Linear
    li.fractional_conversions as linear_conversions,
    li.attributed_value as linear_value,
    
    -- Time Decay
    td.fractional_conversions as time_decay_conversions,
    td.attributed_value as time_decay_value,
    
    -- Position Based
    pb.fractional_conversions as position_based_conversions,
    pb.attributed_value as position_based_value,
    
    -- Shapley
    sh.shapley_weight,
    
    -- Markov
    mk.markov_attribution
    
FROM `{PROJECT_ID}.ssi_shadow.v_attribution_last_touch` lt
FULL OUTER JOIN `{PROJECT_ID}.ssi_shadow.v_attribution_first_touch` ft 
    ON lt.channel = ft.channel
FULL OUTER JOIN `{PROJECT_ID}.ssi_shadow.v_attribution_linear` li 
    ON COALESCE(lt.channel, ft.channel) = li.channel
FULL OUTER JOIN `{PROJECT_ID}.ssi_shadow.v_attribution_time_decay` td 
    ON COALESCE(lt.channel, ft.channel, li.channel) = td.channel
FULL OUTER JOIN `{PROJECT_ID}.ssi_shadow.v_attribution_position_based` pb 
    ON COALESCE(lt.channel, ft.channel, li.channel, td.channel) = pb.channel
FULL OUTER JOIN `{PROJECT_ID}.ssi_shadow.v_attribution_shapley` sh 
    ON COALESCE(lt.channel, ft.channel, li.channel, td.channel, pb.channel) = sh.channel
FULL OUTER JOIN `{PROJECT_ID}.ssi_shadow.v_attribution_markov` mk 
    ON COALESCE(lt.channel, ft.channel, li.channel, td.channel, pb.channel) = mk.channel;

-- =============================================================================
-- 10. VIEW: ROAS POR MODELO DE ATRIBUIÇÃO
-- =============================================================================
-- Cruza com dados de custo das plataformas

CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_roas_by_attribution_model` AS
WITH costs AS (
    -- Custo por canal (preencher via API ou manualmente)
    SELECT
        channel,
        SUM(cost) as total_cost
    FROM `{PROJECT_ID}.ssi_shadow.platform_costs`
    WHERE date >= DATE_SUB(CURRENT_DATE(), INTERVAL 90 DAY)
    GROUP BY channel
)
SELECT
    a.channel,
    c.total_cost,
    
    -- ROAS por modelo
    SAFE_DIVIDE(a.last_touch_value, c.total_cost) as roas_last_touch,
    SAFE_DIVIDE(a.first_touch_value, c.total_cost) as roas_first_touch,
    SAFE_DIVIDE(a.linear_value, c.total_cost) as roas_linear,
    SAFE_DIVIDE(a.time_decay_value, c.total_cost) as roas_time_decay,
    SAFE_DIVIDE(a.position_based_value, c.total_cost) as roas_position_based,
    
    -- Média de todos os modelos
    SAFE_DIVIDE(
        (COALESCE(a.last_touch_value, 0) + COALESCE(a.linear_value, 0) + 
         COALESCE(a.time_decay_value, 0) + COALESCE(a.position_based_value, 0)) / 4,
        c.total_cost
    ) as roas_blended
    
FROM `{PROJECT_ID}.ssi_shadow.v_attribution_comparison` a
LEFT JOIN costs c ON a.channel = c.channel;

-- =============================================================================
-- 11. TABELA: CUSTOS DAS PLATAFORMAS (para ROAS)
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{PROJECT_ID}.ssi_shadow.platform_costs` (
    date DATE NOT NULL,
    channel STRING NOT NULL,
    campaign_id STRING,
    cost FLOAT64,
    impressions INT64,
    clicks INT64,
    source STRING,  -- 'meta_api', 'google_api', 'manual'
    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
);

-- =============================================================================
-- NOTAS DE IMPLEMENTAÇÃO
-- =============================================================================
--
-- 1. Substituir {PROJECT_ID} pelo ID do seu projeto GCP
--
-- 2. Para Shapley completo, considerar usar BigQuery ML ou Python
--    A versão aqui é uma aproximação simplificada
--
-- 3. Para Markov completo, calcular matriz de transição com:
--    - Estado inicial (primeiro touchpoint)
--    - Estados intermediários
--    - Estado de conversão
--    - Estado de não-conversão
--
-- 4. Sync de custos deve ser feito via:
--    - Meta Marketing API: /insights com spend
--    - Google Ads API: CampaignService com metrics
--    - TikTok Ads API: /report/integrated/get/
--
-- =============================================================================
