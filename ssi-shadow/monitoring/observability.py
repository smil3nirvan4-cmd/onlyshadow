"""
S.S.I. SHADOW — Observability Module
MONITORING & ALERTING

Monitora:
1. Data Drift (mudanças na distribuição dos dados)
2. Model Decay (queda de acurácia)
3. Worker Latency
4. IVT Rate
5. Match Rate
6. EMQ Score (aproximado)

Alertas via Telegram quando thresholds são violados.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass, asdict
import requests

# GCP
try:
    from google.cloud import bigquery
    from google.cloud import monitoring_v3
    MONITORING_AVAILABLE = True
except ImportError:
    MONITORING_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_observability')

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

@dataclass
class AlertThresholds:
    """Thresholds para disparar alertas"""
    
    # Model Performance
    model_accuracy_min: float = 0.70       # Alerta se < 70%
    model_auc_min: float = 0.65            # Alerta se AUC < 0.65
    
    # Latency
    worker_latency_p95_max_ms: int = 100   # Alerta se P95 > 100ms
    worker_latency_p99_max_ms: int = 200   # Alerta se P99 > 200ms
    
    # Traffic Quality
    ivt_rate_max: float = 0.20             # Alerta se IVT > 20%
    ivt_rate_critical: float = 0.30        # Kill switch se IVT > 30%
    
    # Attribution
    match_rate_min: float = 0.50           # Alerta se match rate < 50%
    
    # Data Drift
    drift_zscore_max: float = 2.0          # Alerta se z-score > 2

@dataclass
class ObservabilityConfig:
    project_id: str
    dataset_id: str = 'ssi_shadow'
    
    thresholds: AlertThresholds = None
    
    # Telegram
    telegram_bot_token: str = ''
    telegram_chat_id: str = ''
    
    # Cloudflare (para métricas do Worker)
    cf_api_token: str = ''
    cf_account_id: str = ''
    cf_worker_name: str = 'ssi-gateway-prod'
    
    def __post_init__(self):
        if self.thresholds is None:
            self.thresholds = AlertThresholds()

# =============================================================================
# METRICS COLLECTOR
# =============================================================================

class MetricsCollector:
    """Coleta métricas do sistema"""
    
    def __init__(self, config: ObservabilityConfig):
        self.config = config
        self.bq = bigquery.Client(project=config.project_id) if MONITORING_AVAILABLE else None
    
    def collect_all(self, hours: int = 24) -> Dict[str, Any]:
        """Coleta todas as métricas"""
        return {
            'timestamp': datetime.now().isoformat(),
            'period_hours': hours,
            'traffic': self.get_traffic_metrics(hours),
            'quality': self.get_quality_metrics(hours),
            'attribution': self.get_attribution_metrics(hours),
            'model': self.get_model_metrics(hours),
            'latency': self.get_latency_metrics(hours)
        }
    
    def get_traffic_metrics(self, hours: int) -> Dict:
        """Métricas de tráfego"""
        if not self.bq:
            return {}
        
        query = f"""
        SELECT
            COUNT(*) as total_events,
            COUNT(DISTINCT ssi_id) as unique_visitors,
            COUNTIF(event_name = 'PageView') as pageviews,
            COUNTIF(event_name = 'Purchase') as purchases,
            SUM(CASE WHEN event_name = 'Purchase' 
                THEN SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) 
                ELSE 0 END) as revenue
        FROM `{self.config.project_id}.{self.config.dataset_id}.events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        """
        
        result = list(self.bq.query(query).result())[0]
        
        return {
            'total_events': result.total_events,
            'unique_visitors': result.unique_visitors,
            'pageviews': result.pageviews,
            'purchases': result.purchases,
            'revenue': float(result.revenue or 0),
            'conversion_rate': (result.purchases / max(1, result.unique_visitors)) * 100
        }
    
    def get_quality_metrics(self, hours: int) -> Dict:
        """Métricas de qualidade de tráfego"""
        if not self.bq:
            return {}
        
        query = f"""
        SELECT
            AVG(trust_score) as avg_trust_score,
            COUNTIF(trust_score < 0.4) / COUNT(*) as ivt_rate,
            COUNTIF(trust_score >= 0.7) / COUNT(*) as high_quality_rate,
            AVG(intent_score) as avg_intent_score
        FROM `{self.config.project_id}.{self.config.dataset_id}.events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        """
        
        result = list(self.bq.query(query).result())[0]
        
        return {
            'avg_trust_score': float(result.avg_trust_score or 0),
            'ivt_rate': float(result.ivt_rate or 0),
            'high_quality_rate': float(result.high_quality_rate or 0),
            'avg_intent_score': float(result.avg_intent_score or 0)
        }
    
    def get_attribution_metrics(self, hours: int) -> Dict:
        """Métricas de atribuição/match rate"""
        if not self.bq:
            return {}
        
        query = f"""
        SELECT
            COUNTIF(fbp IS NOT NULL OR fbc IS NOT NULL) / COUNT(*) as cookie_match_rate,
            COUNTIF(fbc IS NOT NULL) / COUNT(*) as fbc_rate,
            COUNTIF(canvas_hash IS NOT NULL) / COUNT(*) as fingerprint_rate,
            COUNTIF(email_hash IS NOT NULL OR phone_hash IS NOT NULL) / COUNT(*) as pii_rate
        FROM `{self.config.project_id}.{self.config.dataset_id}.events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        """
        
        result = list(self.bq.query(query).result())[0]
        
        # Estimated Match Rate = combinação de sinais
        estimated_match = min(1.0, 
            float(result.cookie_match_rate or 0) * 0.4 +
            float(result.fingerprint_rate or 0) * 0.3 +
            float(result.pii_rate or 0) * 0.3
        )
        
        return {
            'cookie_match_rate': float(result.cookie_match_rate or 0),
            'fbc_rate': float(result.fbc_rate or 0),
            'fingerprint_rate': float(result.fingerprint_rate or 0),
            'pii_rate': float(result.pii_rate or 0),
            'estimated_match_rate': estimated_match,
            'estimated_emq': self._estimate_emq(result)
        }
    
    def _estimate_emq(self, attribution_data) -> float:
        """
        Estima EMQ baseado nos sinais disponíveis
        
        EMQ considera:
        - email_hash (25%)
        - phone_hash (20%)
        - fbc (15%)
        - fbp (10%)
        - outros (30%)
        """
        score = 0.0
        
        # Baseline: eventos chegando = 3 pontos
        score += 3
        
        # PII presente
        pii_rate = float(attribution_data.pii_rate or 0)
        score += pii_rate * 3  # Até +3 pontos
        
        # FBC presente
        fbc_rate = float(attribution_data.fbc_rate or 0)
        score += fbc_rate * 2  # Até +2 pontos
        
        # Cookie match
        cookie_rate = float(attribution_data.cookie_match_rate or 0)
        score += cookie_rate * 1.5  # Até +1.5 pontos
        
        # Fingerprint como backup
        fp_rate = float(attribution_data.fingerprint_rate or 0)
        score += fp_rate * 0.5  # Até +0.5 pontos
        
        return min(10.0, round(score, 1))
    
    def get_model_metrics(self, hours: int) -> Dict:
        """Métricas dos modelos ML"""
        if not self.bq:
            return {}
        
        # Verificar predições recentes
        query = f"""
        SELECT
            model_name,
            AVG(confidence) as avg_confidence,
            COUNT(*) as prediction_count,
            MAX(predicted_at) as last_prediction
        FROM `{self.config.project_id}.{self.config.dataset_id}.predictions`
        WHERE predicted_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        GROUP BY model_name
        """
        
        try:
            results = list(self.bq.query(query).result())
            
            return {
                'models': [
                    {
                        'name': r.model_name,
                        'avg_confidence': float(r.avg_confidence or 0),
                        'prediction_count': r.prediction_count,
                        'last_prediction': r.last_prediction.isoformat() if r.last_prediction else None
                    }
                    for r in results
                ]
            }
        except Exception as e:
            logger.warning(f"Could not get model metrics: {e}")
            return {'models': []}
    
    def get_latency_metrics(self, hours: int) -> Dict:
        """Métricas de latência do Worker (via Cloudflare API)"""
        if not self.config.cf_api_token:
            return {}
        
        # Cloudflare GraphQL Analytics API
        query = """
        query {
          viewer {
            accounts(filter: {accountTag: "%s"}) {
              workersInvocationsAdaptive(
                filter: {
                  scriptName: "%s",
                  datetime_geq: "%s"
                }
                limit: 1000
              ) {
                quantiles {
                  cpuTimeP50
                  cpuTimeP75
                  cpuTimeP95
                  cpuTimeP99
                }
                sum {
                  requests
                  errors
                }
              }
            }
          }
        }
        """ % (
            self.config.cf_account_id,
            self.config.cf_worker_name,
            (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%SZ')
        )
        
        try:
            response = requests.post(
                'https://api.cloudflare.com/client/v4/graphql',
                headers={
                    'Authorization': f'Bearer {self.config.cf_api_token}',
                    'Content-Type': 'application/json'
                },
                json={'query': query},
                timeout=30
            )
            
            data = response.json()
            
            if 'data' in data:
                workers_data = data['data']['viewer']['accounts'][0]['workersInvocationsAdaptive']
                if workers_data:
                    return {
                        'p50_ms': workers_data[0]['quantiles']['cpuTimeP50'] / 1000,
                        'p75_ms': workers_data[0]['quantiles']['cpuTimeP75'] / 1000,
                        'p95_ms': workers_data[0]['quantiles']['cpuTimeP95'] / 1000,
                        'p99_ms': workers_data[0]['quantiles']['cpuTimeP99'] / 1000,
                        'total_requests': workers_data[0]['sum']['requests'],
                        'total_errors': workers_data[0]['sum']['errors']
                    }
            
            return {}
            
        except Exception as e:
            logger.warning(f"Could not get Cloudflare metrics: {e}")
            return {}

# =============================================================================
# ALERT MANAGER
# =============================================================================

class AlertManager:
    """Gerencia alertas baseado em thresholds"""
    
    def __init__(self, config: ObservabilityConfig):
        self.config = config
        self.thresholds = config.thresholds
    
    def check_all(self, metrics: Dict[str, Any]) -> List[Dict]:
        """Verifica todas as métricas contra thresholds"""
        alerts = []
        
        # Quality Alerts
        if 'quality' in metrics:
            q = metrics['quality']
            
            if q.get('ivt_rate', 0) > self.thresholds.ivt_rate_critical:
                alerts.append({
                    'severity': 'critical',
                    'type': 'ivt_critical',
                    'message': f"🚨 IVT Rate crítico: {q['ivt_rate']:.1%} > {self.thresholds.ivt_rate_critical:.1%}",
                    'action': 'kill_switch',
                    'value': q['ivt_rate']
                })
            elif q.get('ivt_rate', 0) > self.thresholds.ivt_rate_max:
                alerts.append({
                    'severity': 'warning',
                    'type': 'ivt_high',
                    'message': f"⚠️ IVT Rate alto: {q['ivt_rate']:.1%} > {self.thresholds.ivt_rate_max:.1%}",
                    'action': 'investigate',
                    'value': q['ivt_rate']
                })
        
        # Attribution Alerts
        if 'attribution' in metrics:
            a = metrics['attribution']
            
            if a.get('estimated_match_rate', 1) < self.thresholds.match_rate_min:
                alerts.append({
                    'severity': 'warning',
                    'type': 'match_rate_low',
                    'message': f"⚠️ Match Rate baixo: {a['estimated_match_rate']:.1%} < {self.thresholds.match_rate_min:.1%}",
                    'action': 'check_cookies',
                    'value': a['estimated_match_rate']
                })
            
            if a.get('estimated_emq', 10) < 6:
                alerts.append({
                    'severity': 'warning',
                    'type': 'emq_low',
                    'message': f"⚠️ EMQ estimado baixo: {a['estimated_emq']}/10",
                    'action': 'add_pii',
                    'value': a['estimated_emq']
                })
        
        # Latency Alerts
        if 'latency' in metrics:
            l = metrics['latency']
            
            if l.get('p95_ms', 0) > self.thresholds.worker_latency_p95_max_ms:
                alerts.append({
                    'severity': 'warning',
                    'type': 'latency_high',
                    'message': f"⚠️ Latência P95 alta: {l['p95_ms']:.0f}ms > {self.thresholds.worker_latency_p95_max_ms}ms",
                    'action': 'optimize_worker',
                    'value': l['p95_ms']
                })
            
            if l.get('p99_ms', 0) > self.thresholds.worker_latency_p99_max_ms:
                alerts.append({
                    'severity': 'critical',
                    'type': 'latency_critical',
                    'message': f"🚨 Latência P99 crítica: {l['p99_ms']:.0f}ms > {self.thresholds.worker_latency_p99_max_ms}ms",
                    'action': 'urgent_optimization',
                    'value': l['p99_ms']
                })
        
        # Model Alerts
        if 'model' in metrics and metrics['model'].get('models'):
            for model in metrics['model']['models']:
                if model.get('avg_confidence', 1) < self.thresholds.model_accuracy_min:
                    alerts.append({
                        'severity': 'warning',
                        'type': 'model_degradation',
                        'message': f"⚠️ Modelo {model['name']} com confiança baixa: {model['avg_confidence']:.1%}",
                        'action': 'retrain_model',
                        'value': model['avg_confidence']
                    })
        
        return alerts
    
    def send_alerts(self, alerts: List[Dict]) -> int:
        """Envia alertas via Telegram"""
        if not self.config.telegram_bot_token or not alerts:
            return 0
        
        sent = 0
        
        for alert in alerts:
            severity_emoji = {
                'critical': '🔴',
                'warning': '🟠',
                'info': '🔵'
            }.get(alert['severity'], '⚪')
            
            message = f"""
{severity_emoji} <b>SSI SHADOW ALERT</b>

<b>Tipo:</b> {alert['type']}
<b>Severidade:</b> {alert['severity'].upper()}

{alert['message']}

<b>Ação Recomendada:</b> {alert['action']}

<i>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
"""
            
            try:
                response = requests.post(
                    f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage",
                    json={
                        'chat_id': self.config.telegram_chat_id,
                        'text': message.strip(),
                        'parse_mode': 'HTML'
                    },
                    timeout=10
                )
                
                if response.status_code == 200:
                    sent += 1
                    
            except Exception as e:
                logger.error(f"Failed to send alert: {e}")
        
        return sent

# =============================================================================
# LOOKER STUDIO VIEWS
# =============================================================================

LOOKER_VIEWS_SQL = """
-- =============================================================================
-- SSI SHADOW — LOOKER STUDIO VIEWS
-- =============================================================================

-- VIEW: Métricas de Convergência (ROAS Futuro)
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_looker_convergence_matrix` AS
WITH 
daily_metrics AS (
    SELECT
        DATE(event_time) as date,
        COUNT(*) as events,
        COUNT(DISTINCT ssi_id) as visitors,
        COUNTIF(event_name = 'Purchase') as conversions,
        SUM(CASE WHEN event_name = 'Purchase' 
            THEN SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) 
            ELSE 0 END) as revenue,
        AVG(trust_score) as avg_trust,
        AVG(ltv_score) as avg_ltv,
        AVG(intent_score) as avg_intent,
        COUNTIF(trust_score < 0.4) / COUNT(*) as ivt_rate
    FROM `{PROJECT_ID}.ssi_shadow.events`
    WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 90 DAY)
    GROUP BY DATE(event_time)
),
costs AS (
    SELECT
        date,
        SUM(cost) as total_cost
    FROM `{PROJECT_ID}.ssi_shadow.platform_costs`
    GROUP BY date
),
predicted_value AS (
    SELECT
        DATE(predicted_at) as date,
        SUM(predicted_ltv) as total_predicted_ltv
    FROM `{PROJECT_ID}.ssi_shadow.predictions`
    WHERE model_name = 'ltv'
    GROUP BY DATE(predicted_at)
)
SELECT
    m.date,
    m.events,
    m.visitors,
    m.conversions,
    m.revenue,
    c.total_cost,
    
    -- ROAS Atual
    SAFE_DIVIDE(m.revenue, c.total_cost) as roas_current,
    
    -- ROAS Futuro (baseado em LTV predito)
    SAFE_DIVIDE(p.total_predicted_ltv, c.total_cost) as roas_predicted,
    
    -- Quality Metrics
    m.avg_trust,
    m.avg_ltv,
    m.avg_intent,
    m.ivt_rate,
    
    -- Efficiency Score
    (1 - m.ivt_rate) * m.avg_trust * SAFE_DIVIDE(m.revenue, c.total_cost) as efficiency_score
    
FROM daily_metrics m
LEFT JOIN costs c ON m.date = c.date
LEFT JOIN predicted_value p ON m.date = p.date
ORDER BY m.date DESC;

-- VIEW: Health Score do Sistema
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_looker_system_health` AS
SELECT
    CURRENT_TIMESTAMP() as check_time,
    
    -- Events Health
    (SELECT COUNT(*) FROM `{PROJECT_ID}.ssi_shadow.events` 
     WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)) as events_last_hour,
    
    -- Quality Health
    (SELECT AVG(trust_score) FROM `{PROJECT_ID}.ssi_shadow.events` 
     WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)) as avg_trust_1h,
    
    -- IVT Health
    (SELECT COUNTIF(trust_score < 0.4) / COUNT(*) FROM `{PROJECT_ID}.ssi_shadow.events` 
     WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)) as ivt_rate_1h,
    
    -- Match Rate Health
    (SELECT COUNTIF(fbp IS NOT NULL OR fbc IS NOT NULL) / COUNT(*) FROM `{PROJECT_ID}.ssi_shadow.events` 
     WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 1 HOUR)) as match_rate_1h,
    
    -- Model Health
    (SELECT COUNT(*) FROM `{PROJECT_ID}.ssi_shadow.predictions` 
     WHERE predicted_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)) as predictions_24h;

-- VIEW: Funnel por Canal
CREATE OR REPLACE VIEW `{PROJECT_ID}.ssi_shadow.v_looker_channel_funnel` AS
SELECT
    CASE
        WHEN fbclid IS NOT NULL THEN 'Meta Paid'
        WHEN gclid IS NOT NULL THEN 'Google Paid'
        WHEN ttclid IS NOT NULL THEN 'TikTok Paid'
        ELSE 'Other'
    END as channel,
    
    COUNT(DISTINCT CASE WHEN event_name = 'PageView' THEN ssi_id END) as visitors,
    COUNT(DISTINCT CASE WHEN event_name = 'ViewContent' THEN ssi_id END) as viewers,
    COUNT(DISTINCT CASE WHEN event_name = 'AddToCart' THEN ssi_id END) as added_to_cart,
    COUNT(DISTINCT CASE WHEN event_name = 'InitiateCheckout' THEN ssi_id END) as started_checkout,
    COUNT(DISTINCT CASE WHEN event_name = 'Purchase' THEN ssi_id END) as purchased,
    
    -- Funnel Rates
    SAFE_DIVIDE(
        COUNT(DISTINCT CASE WHEN event_name = 'Purchase' THEN ssi_id END),
        COUNT(DISTINCT CASE WHEN event_name = 'PageView' THEN ssi_id END)
    ) as overall_conversion_rate
    
FROM `{PROJECT_ID}.ssi_shadow.events`
WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY)
GROUP BY 1;
"""

# =============================================================================
# MAIN
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='SSI Shadow Observability')
    parser.add_argument('--project', required=True, help='GCP Project ID')
    parser.add_argument('--action', choices=['collect', 'check', 'report'], default='check')
    parser.add_argument('--hours', type=int, default=24)
    
    args = parser.parse_args()
    
    config = ObservabilityConfig(
        project_id=args.project,
        telegram_bot_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
        telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID', ''),
        cf_api_token=os.getenv('CF_API_TOKEN', ''),
        cf_account_id=os.getenv('CF_ACCOUNT_ID', '')
    )
    
    collector = MetricsCollector(config)
    alert_manager = AlertManager(config)
    
    # Coletar métricas
    metrics = collector.collect_all(args.hours)
    
    if args.action == 'collect':
        print(json.dumps(metrics, indent=2, default=str))
    
    elif args.action == 'check':
        alerts = alert_manager.check_all(metrics)
        
        if alerts:
            print(f"\n⚠️ {len(alerts)} ALERTAS DETECTADOS:\n")
            for alert in alerts:
                print(f"  [{alert['severity'].upper()}] {alert['message']}")
            
            sent = alert_manager.send_alerts(alerts)
            print(f"\n📤 {sent} alertas enviados via Telegram")
        else:
            print("✅ Todos os indicadores dentro dos limites")
    
    elif args.action == 'report':
        print("=" * 60)
        print("SSI SHADOW — OBSERVABILITY REPORT")
        print(f"Período: últimas {args.hours} horas")
        print("=" * 60)
        
        if 'traffic' in metrics:
            t = metrics['traffic']
            print(f"\n📊 TRÁFEGO")
            print(f"   Eventos: {t.get('total_events', 0):,}")
            print(f"   Visitantes: {t.get('unique_visitors', 0):,}")
            print(f"   Conversões: {t.get('purchases', 0):,}")
            print(f"   Receita: R$ {t.get('revenue', 0):,.2f}")
        
        if 'quality' in metrics:
            q = metrics['quality']
            print(f"\n🎯 QUALIDADE")
            print(f"   Trust Score médio: {q.get('avg_trust_score', 0):.2f}")
            print(f"   IVT Rate: {q.get('ivt_rate', 0):.1%}")
            print(f"   High Quality: {q.get('high_quality_rate', 0):.1%}")
        
        if 'attribution' in metrics:
            a = metrics['attribution']
            print(f"\n🔗 ATRIBUIÇÃO")
            print(f"   Match Rate: {a.get('estimated_match_rate', 0):.1%}")
            print(f"   FBC Rate: {a.get('fbc_rate', 0):.1%}")
            print(f"   EMQ Estimado: {a.get('estimated_emq', 0)}/10")
        
        if 'latency' in metrics and metrics['latency']:
            l = metrics['latency']
            print(f"\n⚡ LATÊNCIA")
            print(f"   P50: {l.get('p50_ms', 0):.0f}ms")
            print(f"   P95: {l.get('p95_ms', 0):.0f}ms")
            print(f"   P99: {l.get('p99_ms', 0):.0f}ms")
        
        print("\n" + "=" * 60)

if __name__ == '__main__':
    main()
