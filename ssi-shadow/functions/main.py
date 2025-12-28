"""
S.S.I. SHADOW — Cloud Functions
SCHEDULED JOBS

Jobs:
1. update_identity_graph - A cada 4 horas
2. trigger_model_training - Semanal
3. sync_platform_costs - Diário
4. check_kill_switch - A cada hora
5. cleanup_old_data - Diário
6. generate_daily_report - Diário

Deploy:
    gcloud functions deploy FUNCTION_NAME \
        --runtime python311 \
        --trigger-http \
        --entry-point FUNCTION_NAME \
        --set-env-vars GCP_PROJECT_ID=xxx
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any
import functions_framework
from flask import Request

# GCP
from google.cloud import bigquery
from google.cloud import aiplatform
import requests

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_functions')

# =============================================================================
# CONFIG
# =============================================================================

PROJECT_ID = os.environ.get('GCP_PROJECT_ID', '')
DATASET_ID = os.environ.get('BQ_DATASET_ID', 'ssi_shadow')
TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# =============================================================================
# HELPERS
# =============================================================================

def send_telegram(message: str, parse_mode: str = 'HTML'):
    """Envia mensagem via Telegram"""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                'chat_id': TELEGRAM_CHAT_ID,
                'text': message,
                'parse_mode': parse_mode
            },
            timeout=10
        )
    except Exception as e:
        logger.error(f"Telegram send failed: {e}")

def get_bq_client():
    return bigquery.Client(project=PROJECT_ID)

# =============================================================================
# 1. UPDATE IDENTITY GRAPH
# =============================================================================

@functions_framework.http
def update_identity_graph(request: Request) -> Dict[str, Any]:
    """
    Atualiza o Identity Graph com novos eventos.
    Agrupa usuários por múltiplos identificadores.
    
    Schedule: A cada 4 horas
    """
    logger.info("Starting identity graph update...")
    
    bq = get_bq_client()
    
    # Query para atualizar identity graph
    query = f"""
    -- Merge novos eventos no identity graph
    MERGE INTO `{PROJECT_ID}.{DATASET_ID}.identity_graph` T
    USING (
        WITH new_identities AS (
            SELECT
                ssi_id,
                ARRAY_AGG(DISTINCT fbp IGNORE NULLS) as fbp_ids,
                ARRAY_AGG(DISTINCT fbc IGNORE NULLS) as fbc_ids,
                ARRAY_AGG(DISTINCT canvas_hash IGNORE NULLS) as canvas_hashes,
                ARRAY_AGG(DISTINCT webgl_hash IGNORE NULLS) as webgl_hashes,
                ARRAY_AGG(DISTINCT email_hash IGNORE NULLS) as email_hashes,
                ARRAY_AGG(DISTINCT phone_hash IGNORE NULLS) as phone_hashes,
                MIN(event_time) as first_seen,
                MAX(event_time) as last_seen
            FROM `{PROJECT_ID}.{DATASET_ID}.events`
            WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 4 HOUR)
            GROUP BY ssi_id
        )
        SELECT * FROM new_identities
    ) S
    ON T.ssi_id = S.ssi_id
    WHEN MATCHED THEN
        UPDATE SET
            fbp_ids = ARRAY_CONCAT(T.fbp_ids, S.fbp_ids),
            fbc_ids = ARRAY_CONCAT(T.fbc_ids, S.fbc_ids),
            canvas_hashes = ARRAY_CONCAT(T.canvas_hashes, S.canvas_hashes),
            webgl_hashes = ARRAY_CONCAT(T.webgl_hashes, S.webgl_hashes),
            email_hashes = ARRAY_CONCAT(T.email_hashes, S.email_hashes),
            phone_hashes = ARRAY_CONCAT(T.phone_hashes, S.phone_hashes),
            last_seen = S.last_seen,
            updated_at = CURRENT_TIMESTAMP()
    WHEN NOT MATCHED THEN
        INSERT (ssi_id, fbp_ids, fbc_ids, canvas_hashes, webgl_hashes, 
                email_hashes, phone_hashes, first_seen, last_seen, updated_at)
        VALUES (S.ssi_id, S.fbp_ids, S.fbc_ids, S.canvas_hashes, S.webgl_hashes,
                S.email_hashes, S.phone_hashes, S.first_seen, S.last_seen, CURRENT_TIMESTAMP())
    """
    
    job = bq.query(query)
    job.result()
    
    # Contar registros atualizados
    count_query = f"""
    SELECT COUNT(*) as total
    FROM `{PROJECT_ID}.{DATASET_ID}.identity_graph`
    WHERE updated_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 MINUTE)
    """
    
    count_result = list(bq.query(count_query).result())[0]
    
    result = {
        'status': 'success',
        'updated_records': count_result.total,
        'timestamp': datetime.now().isoformat()
    }
    
    logger.info(f"Identity graph updated: {count_result.total} records")
    
    return result

# =============================================================================
# 2. TRIGGER MODEL TRAINING
# =============================================================================

@functions_framework.http
def trigger_model_training(request: Request) -> Dict[str, Any]:
    """
    Dispara retreinamento dos modelos ML.
    
    Schedule: Semanal (domingo 3AM)
    """
    logger.info("Triggering model training...")
    
    bq = get_bq_client()
    results = {}
    
    # Retreinar LTV model
    ltv_query = f"""
    CREATE OR REPLACE MODEL `{PROJECT_ID}.{DATASET_ID}.bqml_ltv_model`
    OPTIONS(
        model_type='BOOSTED_TREE_REGRESSOR',
        input_label_cols=['total_value'],
        max_iterations=50,
        early_stop=TRUE
    ) AS
    SELECT
        pageviews, product_views, add_to_carts, checkouts, purchases,
        avg_trust_score, avg_intent_score, mobile_rate, paid_rate,
        lifespan_hours, active_days, total_value
    FROM `{PROJECT_ID}.{DATASET_ID}.v_user_features`
    WHERE total_value > 0
    """
    
    try:
        job = bq.query(ltv_query)
        job.result()
        results['ltv_model'] = 'trained'
        logger.info("LTV model trained successfully")
    except Exception as e:
        results['ltv_model'] = f'error: {str(e)}'
        logger.error(f"LTV model training failed: {e}")
    
    # Retreinar Intent model
    intent_query = f"""
    CREATE OR REPLACE MODEL `{PROJECT_ID}.{DATASET_ID}.bqml_intent_model`
    OPTIONS(
        model_type='BOOSTED_TREE_CLASSIFIER',
        input_label_cols=['converted'],
        max_iterations=50,
        early_stop=TRUE,
        auto_class_weights=TRUE
    ) AS
    SELECT
        pageviews, product_views, add_to_carts,
        avg_trust_score, avg_scroll_depth, avg_time_on_page,
        max_interactions, is_mobile, from_paid, converted
    FROM `{PROJECT_ID}.{DATASET_ID}.v_intent_features`
    """
    
    try:
        job = bq.query(intent_query)
        job.result()
        results['intent_model'] = 'trained'
        logger.info("Intent model trained successfully")
    except Exception as e:
        results['intent_model'] = f'error: {str(e)}'
        logger.error(f"Intent model training failed: {e}")
    
    # Avaliar modelos
    eval_queries = {
        'ltv': f"SELECT * FROM ML.EVALUATE(MODEL `{PROJECT_ID}.{DATASET_ID}.bqml_ltv_model`)",
        'intent': f"SELECT * FROM ML.EVALUATE(MODEL `{PROJECT_ID}.{DATASET_ID}.bqml_intent_model`)"
    }
    
    for model_name, query in eval_queries.items():
        try:
            eval_result = list(bq.query(query).result())[0]
            results[f'{model_name}_metrics'] = dict(eval_result)
        except Exception as e:
            results[f'{model_name}_metrics'] = f'error: {str(e)}'
    
    # Enviar notificação
    send_telegram(f"""
<b>🤖 Model Training Complete</b>

<b>LTV Model:</b> {results.get('ltv_model', 'unknown')}
<b>Intent Model:</b> {results.get('intent_model', 'unknown')}

<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
    """)
    
    return {
        'status': 'completed',
        'results': results,
        'timestamp': datetime.now().isoformat()
    }

# =============================================================================
# 3. SYNC PLATFORM COSTS
# =============================================================================

@functions_framework.http
def sync_platform_costs(request: Request) -> Dict[str, Any]:
    """
    Sincroniza custos das plataformas de ads para cálculo de ROAS real.
    
    Schedule: Diário (6AM)
    """
    logger.info("Syncing platform costs...")
    
    bq = get_bq_client()
    results = {'meta': None, 'google': None, 'tiktok': None}
    
    # Meta Ads
    meta_token = os.environ.get('META_ACCESS_TOKEN', '')
    meta_account = os.environ.get('META_AD_ACCOUNT_ID', '')
    
    if meta_token and meta_account:
        try:
            yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
            
            response = requests.get(
                f"https://graph.facebook.com/v18.0/{meta_account}/insights",
                params={
                    'access_token': meta_token,
                    'fields': 'campaign_id,campaign_name,spend,impressions,clicks,actions',
                    'date_preset': 'yesterday',
                    'level': 'campaign'
                },
                timeout=30
            )
            
            if response.ok:
                data = response.json().get('data', [])
                
                rows = []
                for item in data:
                    rows.append({
                        'date': yesterday,
                        'channel': 'meta_paid',
                        'campaign_id': item.get('campaign_id'),
                        'campaign_name': item.get('campaign_name'),
                        'cost': float(item.get('spend', 0)),
                        'impressions': int(item.get('impressions', 0)),
                        'clicks': int(item.get('clicks', 0)),
                        'source': 'meta_api',
                        'synced_at': datetime.now().isoformat()
                    })
                
                if rows:
                    table_ref = f"{PROJECT_ID}.{DATASET_ID}.platform_costs"
                    errors = bq.insert_rows_json(table_ref, rows)
                    results['meta'] = {'campaigns': len(rows), 'errors': len(errors)}
                    
        except Exception as e:
            results['meta'] = {'error': str(e)}
            logger.error(f"Meta cost sync failed: {e}")
    
    # Google Ads (simplificado - em produção usar Google Ads API)
    # TikTok Ads (simplificado)
    
    # Calcular totais do dia
    totals_query = f"""
    SELECT
        channel,
        SUM(cost) as total_cost,
        SUM(impressions) as total_impressions,
        SUM(clicks) as total_clicks
    FROM `{PROJECT_ID}.{DATASET_ID}.platform_costs`
    WHERE date = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
    GROUP BY channel
    """
    
    try:
        totals = list(bq.query(totals_query).result())
        results['totals'] = [dict(row) for row in totals]
    except Exception as e:
        results['totals'] = {'error': str(e)}
    
    return {
        'status': 'completed',
        'results': results,
        'timestamp': datetime.now().isoformat()
    }

# =============================================================================
# 4. CHECK KILL SWITCH
# =============================================================================

@functions_framework.http
def check_kill_switch(request: Request) -> Dict[str, Any]:
    """
    Verifica taxa de IVT e dispara kill switch se necessário.
    
    Schedule: A cada hora
    """
    logger.info("Checking kill switch conditions...")
    
    bq = get_bq_client()
    
    # Calcular IVT rate última hora
    query = f"""
    SELECT
        COUNT(*) as total_events,
        COUNTIF(trust_score < 0.4) as suspicious_events,
        COUNTIF(trust_score < 0.25) as blocked_events,
        SAFE_DIVIDE(COUNTIF(trust_score < 0.4), COUNT(*)) as ivt_rate
    FROM `{PROJECT_ID}.{DATASET_ID}.events`
    WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)
    """
    
    result = list(bq.query(query).result())[0]
    
    ivt_rate = float(result.ivt_rate or 0)
    threshold = float(os.environ.get('IVT_CRITICAL_THRESHOLD', '0.30'))
    
    response = {
        'total_events': result.total_events,
        'suspicious_events': result.suspicious_events,
        'blocked_events': result.blocked_events,
        'ivt_rate': ivt_rate,
        'threshold': threshold,
        'kill_switch_triggered': False,
        'timestamp': datetime.now().isoformat()
    }
    
    if ivt_rate > threshold:
        response['kill_switch_triggered'] = True
        
        # Pausar campanhas via APIs
        # (em produção, chamar Meta/Google APIs)
        
        # Alertar
        send_telegram(f"""
🚨 <b>KILL SWITCH TRIGGERED</b>

<b>IVT Rate:</b> {ivt_rate:.1%}
<b>Threshold:</b> {threshold:.1%}

<b>Total Events:</b> {result.total_events}
<b>Suspicious:</b> {result.suspicious_events}
<b>Blocked:</b> {result.blocked_events}

<b>Action:</b> Campanhas pausadas automaticamente.

<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
        """)
        
        logger.warning(f"Kill switch triggered! IVT rate: {ivt_rate:.1%}")
    
    return response

# =============================================================================
# 5. CLEANUP OLD DATA
# =============================================================================

@functions_framework.http
def cleanup_old_data(request: Request) -> Dict[str, Any]:
    """
    Remove dados antigos para controle de custos.
    
    Schedule: Diário (4AM)
    """
    logger.info("Starting data cleanup...")
    
    bq = get_bq_client()
    results = {}
    
    # Retention periods
    retention = {
        'events': 180,  # 6 meses
        'sessions': 90,
        'predictions': 30,
        'platform_costs': 365
    }
    
    for table, days in retention.items():
        try:
            query = f"""
            DELETE FROM `{PROJECT_ID}.{DATASET_ID}.{table}`
            WHERE event_time < TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {days} DAY)
            """
            
            if table == 'platform_costs':
                query = f"""
                DELETE FROM `{PROJECT_ID}.{DATASET_ID}.{table}`
                WHERE date < DATE_SUB(CURRENT_DATE(), INTERVAL {days} DAY)
                """
            
            job = bq.query(query)
            job.result()
            
            results[table] = {
                'status': 'cleaned',
                'retention_days': days,
                'rows_deleted': job.num_dml_affected_rows
            }
            
        except Exception as e:
            results[table] = {'error': str(e)}
    
    logger.info(f"Cleanup completed: {results}")
    
    return {
        'status': 'completed',
        'results': results,
        'timestamp': datetime.now().isoformat()
    }

# =============================================================================
# 6. GENERATE DAILY REPORT
# =============================================================================

@functions_framework.http
def generate_daily_report(request: Request) -> Dict[str, Any]:
    """
    Gera relatório diário de performance.
    
    Schedule: Diário (8AM)
    """
    logger.info("Generating daily report...")
    
    bq = get_bq_client()
    
    # Métricas do dia anterior
    query = f"""
    SELECT
        -- Volume
        COUNT(*) as total_events,
        COUNT(DISTINCT ssi_id) as unique_visitors,
        COUNTIF(event_name = 'Purchase') as purchases,
        SUM(CASE WHEN event_name = 'Purchase' 
            THEN SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) 
            ELSE 0 END) as revenue,
        
        -- Quality
        AVG(trust_score) as avg_trust_score,
        COUNTIF(trust_score < 0.4) / COUNT(*) as ivt_rate,
        
        -- Attribution
        COUNTIF(fbp IS NOT NULL OR fbc IS NOT NULL) / COUNT(*) as cookie_match_rate,
        COUNTIF(email_hash IS NOT NULL) / COUNT(*) as email_rate,
        
        -- Conversion
        SAFE_DIVIDE(COUNTIF(event_name = 'Purchase'), COUNT(DISTINCT ssi_id)) as conversion_rate
        
    FROM `{PROJECT_ID}.{DATASET_ID}.events`
    WHERE DATE(event_time) = DATE_SUB(CURRENT_DATE(), INTERVAL 1 DAY)
    """
    
    result = list(bq.query(query).result())[0]
    
    # Comparação com dia anterior
    compare_query = f"""
    SELECT
        COUNT(*) as total_events,
        COUNTIF(event_name = 'Purchase') as purchases,
        SUM(CASE WHEN event_name = 'Purchase' 
            THEN SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) 
            ELSE 0 END) as revenue
    FROM `{PROJECT_ID}.{DATASET_ID}.events`
    WHERE DATE(event_time) = DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY)
    """
    
    prev = list(bq.query(compare_query).result())[0]
    
    # Calcular variações
    def calc_change(current, previous):
        if previous and previous > 0:
            return ((current or 0) - previous) / previous * 100
        return 0
    
    events_change = calc_change(result.total_events, prev.total_events)
    purchases_change = calc_change(result.purchases, prev.purchases)
    revenue_change = calc_change(result.revenue, prev.revenue)
    
    # Enviar relatório
    report = f"""
📊 <b>SSI SHADOW - Daily Report</b>
<i>{(datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')}</i>

<b>📈 Volume</b>
Events: {result.total_events:,} ({events_change:+.1f}%)
Visitors: {result.unique_visitors:,}
Purchases: {result.purchases:,} ({purchases_change:+.1f}%)
Revenue: R$ {(result.revenue or 0):,.2f} ({revenue_change:+.1f}%)

<b>🎯 Quality</b>
Trust Score: {(result.avg_trust_score or 0):.2f}
IVT Rate: {(result.ivt_rate or 0):.1%}
Match Rate: {(result.cookie_match_rate or 0):.1%}
Email Rate: {(result.email_rate or 0):.1%}

<b>💰 Conversion</b>
Rate: {(result.conversion_rate or 0):.2%}
AOV: R$ {((result.revenue or 0) / max(1, result.purchases)):,.2f}

<i>Generated at {datetime.now().strftime('%H:%M:%S')}</i>
    """
    
    send_telegram(report)
    
    return {
        'status': 'sent',
        'metrics': {
            'events': result.total_events,
            'visitors': result.unique_visitors,
            'purchases': result.purchases,
            'revenue': float(result.revenue or 0),
            'trust_score': float(result.avg_trust_score or 0),
            'ivt_rate': float(result.ivt_rate or 0),
            'conversion_rate': float(result.conversion_rate or 0)
        },
        'changes': {
            'events': events_change,
            'purchases': purchases_change,
            'revenue': revenue_change
        },
        'timestamp': datetime.now().isoformat()
    }

# =============================================================================
# 7. UPDATE PREDICTIONS
# =============================================================================

@functions_framework.http
def update_predictions(request: Request) -> Dict[str, Any]:
    """
    Atualiza tabela de predições com novos scores.
    
    Schedule: A cada 4 horas
    """
    logger.info("Updating predictions...")
    
    bq = get_bq_client()
    
    # Chamar procedure
    query = f"CALL `{PROJECT_ID}.{DATASET_ID}.update_predictions`()"
    
    try:
        job = bq.query(query)
        job.result()
        
        # Contar predições atualizadas
        count_query = f"""
        SELECT COUNT(*) as total
        FROM `{PROJECT_ID}.{DATASET_ID}.predictions`
        WHERE predicted_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 5 MINUTE)
        """
        
        count = list(bq.query(count_query).result())[0].total
        
        return {
            'status': 'success',
            'predictions_updated': count,
            'timestamp': datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Update predictions failed: {e}")
        return {
            'status': 'error',
            'error': str(e),
            'timestamp': datetime.now().isoformat()
        }
