-- =============================================================================
-- S.S.I. SHADOW — BigQuery Schema
-- Dataset: ssi_shadow
-- =============================================================================

-- =============================================================================
-- TABELA: events
-- Eventos de tracking capturados pelo sistema
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{PROJECT_ID}.ssi_shadow.events` (
  -- Identificadores
  event_id STRING NOT NULL,
  ssi_id STRING,
  
  -- Evento
  event_name STRING NOT NULL,
  event_time TIMESTAMP NOT NULL,
  event_source_url STRING,
  
  -- User Data (hashed)
  ip_hash STRING,
  ua STRING,
  device_type STRING,  -- mobile, tablet, desktop
  
  -- Geo
  country STRING,
  city STRING,
  region STRING,
  
  -- Scores
  trust_score FLOAT64,
  ltv_score FLOAT64,
  intent_score FLOAT64,
  
  -- Attribution IDs
  fbclid STRING,
  gclid STRING,
  ttclid STRING,
  fbp STRING,
  fbc STRING,
  
  -- Flags
  is_returning BOOL DEFAULT FALSE,
  is_bot BOOL DEFAULT FALSE,
  
  -- Custom Data (JSON)
  custom_data STRING,  -- JSON string
  
  -- CAPI Status
  meta_capi_sent BOOL DEFAULT FALSE,
  google_ec_sent BOOL DEFAULT FALSE,
  tiktok_sent BOOL DEFAULT FALSE,
  
  -- Metadata
  processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  
  -- Partitioning column
  _PARTITIONTIME TIMESTAMP
)
PARTITION BY DATE(event_time)
CLUSTER BY event_name, ssi_id, country
OPTIONS (
  description = 'Eventos de tracking do S.S.I. Shadow',
  labels = [('env', 'production'), ('team', 'marketing')]
);

-- =============================================================================
-- TABELA: identities
-- Graph de identidades para stitching
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{PROJECT_ID}.ssi_shadow.identities` (
  -- Identity
  ssi_id STRING NOT NULL,
  
  -- Linked IDs
  fbp_ids ARRAY<STRING>,
  fbc_ids ARRAY<STRING>,
  email_hashes ARRAY<STRING>,
  phone_hashes ARRAY<STRING>,
  external_ids ARRAY<STRING>,
  
  -- Profile
  first_seen TIMESTAMP,
  last_seen TIMESTAMP,
  total_sessions INT64 DEFAULT 0,
  total_pageviews INT64 DEFAULT 0,
  total_events INT64 DEFAULT 0,
  
  -- Device Profile
  primary_device STRING,
  devices ARRAY<STRING>,
  countries ARRAY<STRING>,
  
  -- Value
  total_purchase_value FLOAT64 DEFAULT 0,
  purchase_count INT64 DEFAULT 0,
  predicted_ltv FLOAT64,
  
  -- Flags
  is_customer BOOL DEFAULT FALSE,
  is_lead BOOL DEFAULT FALSE,
  
  -- Metadata
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP(),
  updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
CLUSTER BY ssi_id
OPTIONS (
  description = 'Identity graph do S.S.I. Shadow'
);

-- =============================================================================
-- TABELA: predictions
-- Histórico de predições ML
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{PROJECT_ID}.ssi_shadow.predictions` (
  prediction_id STRING NOT NULL,
  ssi_id STRING NOT NULL,
  
  -- Prediction Type
  prediction_type STRING NOT NULL,  -- ltv, intent, churn, anomaly
  
  -- Values
  predicted_value FLOAT64,
  confidence FLOAT64,
  
  -- Features used
  features STRING,  -- JSON
  
  -- Validation
  actual_value FLOAT64,
  error FLOAT64,
  validated_at TIMESTAMP,
  
  -- Metadata
  model_version STRING,
  predicted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(predicted_at)
CLUSTER BY prediction_type, ssi_id
OPTIONS (
  description = 'Histórico de predições ML'
);

-- =============================================================================
-- TABELA: trends
-- Dados do Oráculo - tendências de mercado
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{PROJECT_ID}.ssi_shadow.trends` (
  trend_id STRING NOT NULL,
  
  -- Keyword
  keyword STRING NOT NULL,
  
  -- Metrics
  search_volume INT64,
  trend_score FLOAT64,  -- -100 a +100 (variação)
  competition_score FLOAT64,  -- 0 a 1
  cpc_estimate FLOAT64,
  
  -- Blue Ocean Score
  bos_score FLOAT64,
  bos_components STRING,  -- JSON com breakdown
  
  -- Forecast
  forecast_7d FLOAT64,
  forecast_30d FLOAT64,
  forecast_confidence FLOAT64,
  
  -- Classification
  category STRING,
  is_opportunity BOOL DEFAULT FALSE,
  urgency STRING,  -- high, medium, low
  
  -- Metadata
  source STRING,  -- google_trends, semrush, etc
  collected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(collected_at)
CLUSTER BY keyword, category
OPTIONS (
  description = 'Dados de trends do Oráculo'
);

-- =============================================================================
-- TABELA: alerts
-- Alertas gerados pelo sistema
-- =============================================================================

CREATE TABLE IF NOT EXISTS `{PROJECT_ID}.ssi_shadow.alerts` (
  alert_id STRING NOT NULL,
  
  -- Alert Info
  alert_type STRING NOT NULL,  -- trend_spike, anomaly, opportunity, etc
  severity STRING,  -- critical, high, medium, low
  title STRING,
  message STRING,
  
  -- Related Data
  related_keyword STRING,
  related_ssi_id STRING,
  related_data STRING,  -- JSON
  
  -- Status
  status STRING DEFAULT 'new',  -- new, acknowledged, resolved
  acknowledged_at TIMESTAMP,
  resolved_at TIMESTAMP,
  
  -- Notifications
  telegram_sent BOOL DEFAULT FALSE,
  email_sent BOOL DEFAULT FALSE,
  
  -- Metadata
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
)
PARTITION BY DATE(created_at)
CLUSTER BY alert_type, status
OPTIONS (
  description = 'Alertas do sistema'
);

-- =============================================================================
-- VIEWS
-- =============================================================================

-- Dashboard: Métricas diárias
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_daily_metrics` AS
SELECT
  DATE(event_time) as date,
  event_name,
  COUNT(*) as event_count,
  COUNT(DISTINCT ssi_id) as unique_users,
  AVG(trust_score) as avg_trust_score,
  AVG(ltv_score) as avg_ltv_score,
  AVG(intent_score) as avg_intent_score,
  COUNTIF(fbclid IS NOT NULL) as from_meta,
  COUNTIF(gclid IS NOT NULL) as from_google,
  COUNTIF(ttclid IS NOT NULL) as from_tiktok,
  COUNTIF(is_returning = TRUE) as returning_users,
  COUNTIF(is_bot = TRUE) as bot_traffic
FROM `{PROJECT_ID}.ssi_shadow.events`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
GROUP BY 1, 2
ORDER BY 1 DESC, 2;

-- Dashboard: Funnel de conversão
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_funnel` AS
WITH funnel_events AS (
  SELECT
    DATE(event_time) as date,
    ssi_id,
    MAX(CASE WHEN event_name = 'PageView' THEN 1 ELSE 0 END) as pageview,
    MAX(CASE WHEN event_name = 'ViewContent' THEN 1 ELSE 0 END) as view_content,
    MAX(CASE WHEN event_name = 'AddToCart' THEN 1 ELSE 0 END) as add_to_cart,
    MAX(CASE WHEN event_name = 'InitiateCheckout' THEN 1 ELSE 0 END) as checkout,
    MAX(CASE WHEN event_name = 'Purchase' THEN 1 ELSE 0 END) as purchase
  FROM `{PROJECT_ID}.ssi_shadow.events`
  WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
  GROUP BY 1, 2
)
SELECT
  date,
  SUM(pageview) as pageviews,
  SUM(view_content) as view_content,
  SUM(add_to_cart) as add_to_cart,
  SUM(checkout) as checkout,
  SUM(purchase) as purchase,
  SAFE_DIVIDE(SUM(view_content), SUM(pageview)) * 100 as pv_to_vc_rate,
  SAFE_DIVIDE(SUM(add_to_cart), SUM(view_content)) * 100 as vc_to_atc_rate,
  SAFE_DIVIDE(SUM(checkout), SUM(add_to_cart)) * 100 as atc_to_co_rate,
  SAFE_DIVIDE(SUM(purchase), SUM(checkout)) * 100 as co_to_purchase_rate,
  SAFE_DIVIDE(SUM(purchase), SUM(pageview)) * 100 as overall_cvr
FROM funnel_events
GROUP BY 1
ORDER BY 1 DESC;

-- Dashboard: Attribution
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_attribution` AS
SELECT
  DATE(event_time) as date,
  CASE 
    WHEN fbclid IS NOT NULL THEN 'Meta Ads'
    WHEN gclid IS NOT NULL THEN 'Google Ads'
    WHEN ttclid IS NOT NULL THEN 'TikTok Ads'
    WHEN REGEXP_CONTAINS(event_source_url, r'utm_source=') THEN 'Organic/UTM'
    ELSE 'Direct'
  END as source,
  COUNT(*) as events,
  COUNT(DISTINCT ssi_id) as users,
  SUM(CASE WHEN event_name = 'Purchase' THEN 1 ELSE 0 END) as purchases,
  SUM(CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64)) as revenue
FROM `{PROJECT_ID}.ssi_shadow.events`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY 1, 2
ORDER BY 1 DESC, events DESC;

-- Dashboard: Oráculo - Oportunidades
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_opportunities` AS
SELECT
  keyword,
  bos_score,
  search_volume,
  cpc_estimate,
  competition_score,
  forecast_7d,
  forecast_30d,
  urgency,
  collected_at
FROM `{PROJECT_ID}.ssi_shadow.trends`
WHERE is_opportunity = TRUE
  AND collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
ORDER BY bos_score DESC
LIMIT 50;

-- =============================================================================
-- PROCEDURES
-- =============================================================================

-- Procedure: Atualizar Identity Graph
CREATE OR REPLACE PROCEDURE `{PROJECT_ID}.ssi_shadow.update_identity_graph`()
BEGIN
  -- Merge novos eventos no identity graph
  MERGE `{PROJECT_ID}.ssi_shadow.identities` T
  USING (
    SELECT
      ssi_id,
      ARRAY_AGG(DISTINCT fbp IGNORE NULLS) as fbp_ids,
      ARRAY_AGG(DISTINCT fbc IGNORE NULLS) as fbc_ids,
      MIN(event_time) as first_seen,
      MAX(event_time) as last_seen,
      COUNT(DISTINCT DATE(event_time)) as total_sessions,
      COUNTIF(event_name = 'PageView') as total_pageviews,
      COUNT(*) as total_events,
      ARRAY_AGG(DISTINCT device_type IGNORE NULLS) as devices,
      ARRAY_AGG(DISTINCT country IGNORE NULLS) as countries,
      SUM(CASE WHEN event_name = 'Purchase' THEN CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) ELSE 0 END) as total_purchase_value,
      COUNTIF(event_name = 'Purchase') as purchase_count,
      MAX(CASE WHEN event_name = 'Purchase' THEN TRUE ELSE FALSE END) as is_customer,
      MAX(CASE WHEN event_name = 'Lead' THEN TRUE ELSE FALSE END) as is_lead
    FROM `{PROJECT_ID}.ssi_shadow.events`
    WHERE ssi_id IS NOT NULL
      AND event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 DAY)
    GROUP BY ssi_id
  ) S
  ON T.ssi_id = S.ssi_id
  WHEN MATCHED THEN
    UPDATE SET
      fbp_ids = ARRAY_CONCAT(IFNULL(T.fbp_ids, []), S.fbp_ids),
      fbc_ids = ARRAY_CONCAT(IFNULL(T.fbc_ids, []), S.fbc_ids),
      last_seen = S.last_seen,
      total_sessions = T.total_sessions + S.total_sessions,
      total_pageviews = T.total_pageviews + S.total_pageviews,
      total_events = T.total_events + S.total_events,
      devices = ARRAY_CONCAT(IFNULL(T.devices, []), S.devices),
      countries = ARRAY_CONCAT(IFNULL(T.countries, []), S.countries),
      total_purchase_value = T.total_purchase_value + S.total_purchase_value,
      purchase_count = T.purchase_count + S.purchase_count,
      is_customer = T.is_customer OR S.is_customer,
      is_lead = T.is_lead OR S.is_lead,
      updated_at = CURRENT_TIMESTAMP()
  WHEN NOT MATCHED THEN
    INSERT (ssi_id, fbp_ids, fbc_ids, first_seen, last_seen, total_sessions, total_pageviews, total_events, devices, countries, total_purchase_value, purchase_count, is_customer, is_lead, created_at, updated_at)
    VALUES (S.ssi_id, S.fbp_ids, S.fbc_ids, S.first_seen, S.last_seen, S.total_sessions, S.total_pageviews, S.total_events, S.devices, S.countries, S.total_purchase_value, S.purchase_count, S.is_customer, S.is_lead, CURRENT_TIMESTAMP(), CURRENT_TIMESTAMP());
END;

-- =============================================================================
-- SCHEDULED QUERIES (configurar no BigQuery UI)
-- =============================================================================

-- Agendar update_identity_graph para rodar a cada hora
-- Schedule: Every 1 hour
-- Query: CALL `{PROJECT_ID}.ssi_shadow.update_identity_graph`();
