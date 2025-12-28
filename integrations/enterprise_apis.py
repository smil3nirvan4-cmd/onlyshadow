"""
S.S.I. SHADOW — Enterprise Integrations
THIRD-PARTY API CONNECTORS

Integrações:
1. Revealbot - Automated bid rules
2. Clearbit - Company enrichment
3. Meta Conversion Lift API - Incrementality measurement
4. Hunter.io - Email verification
5. BigQuery ML - Native ML models

Budget: ~$500/mês para todas as integrações básicas
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from dataclasses import dataclass
import requests
from abc import ABC, abstractmethod

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_integrations')

# =============================================================================
# BASE CLIENT
# =============================================================================

class BaseAPIClient(ABC):
    """Base class para clientes de API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
    
    def _request(
        self, 
        method: str, 
        url: str, 
        headers: Dict = None,
        params: Dict = None,
        json_data: Dict = None,
        timeout: int = 30
    ) -> Optional[Dict]:
        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                params=params,
                json=json_data,
                timeout=timeout
            )
            
            if response.ok:
                return response.json() if response.text else {}
            else:
                logger.error(f"API error: {response.status_code} - {response.text[:200]}")
                return None
                
        except Exception as e:
            logger.error(f"Request failed: {e}")
            return None

# =============================================================================
# 1. REVEALBOT INTEGRATION
# =============================================================================

@dataclass
class RevealBotMetrics:
    """Métricas customizadas para Revealbot"""
    campaign_id: str
    ad_account_id: str
    
    # SSI metrics
    ssi_ltv_score: float
    ssi_trust_score: float
    ssi_intent_score: float
    ssi_predicted_value: float
    ssi_conversion_probability: float
    ssi_quality_score: float
    
    # IVT metrics
    ivt_rate: float
    bot_rate: float
    
    timestamp: datetime = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


class RevealBotClient(BaseAPIClient):
    """
    Revealbot Integration
    
    Permite enviar métricas customizadas do SSI para Revealbot,
    que então executa regras de automação baseadas nesses dados.
    
    Pricing: $99-499/mês dependendo do spend
    Docs: https://revealbot.com/docs
    """
    
    BASE_URL = "https://api.revealbot.com/v1"
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.session.headers['Authorization'] = f'Bearer {api_key}'
        self.session.headers['Content-Type'] = 'application/json'
    
    def push_custom_metrics(self, metrics: RevealBotMetrics) -> bool:
        """
        Envia métricas customizadas do SSI para Revealbot.
        
        Revealbot pode então usar essas métricas em regras como:
        - Se ssi_ltv_score > 0.8, aumentar bid 20%
        - Se ssi_trust_score < 0.4, pausar ad set
        - Se ivt_rate > 0.2, alertar
        """
        payload = {
            "campaign_id": metrics.campaign_id,
            "ad_account_id": metrics.ad_account_id,
            "custom_metrics": {
                "ssi_ltv_score": metrics.ssi_ltv_score,
                "ssi_trust_score": metrics.ssi_trust_score,
                "ssi_intent_score": metrics.ssi_intent_score,
                "ssi_predicted_value": metrics.ssi_predicted_value,
                "ssi_conversion_probability": metrics.ssi_conversion_probability,
                "ssi_quality_score": metrics.ssi_quality_score,
                "ssi_ivt_rate": metrics.ivt_rate,
                "ssi_bot_rate": metrics.bot_rate
            },
            "timestamp": metrics.timestamp.isoformat()
        }
        
        result = self._request(
            'POST',
            f"{self.BASE_URL}/custom_metrics",
            json_data=payload
        )
        
        return result is not None
    
    def get_rules(self) -> List[Dict]:
        """Obtém regras configuradas"""
        result = self._request('GET', f"{self.BASE_URL}/rules")
        return result.get('rules', []) if result else []
    
    def trigger_rule(self, rule_id: str) -> bool:
        """Dispara uma regra manualmente"""
        result = self._request(
            'POST',
            f"{self.BASE_URL}/rules/{rule_id}/trigger"
        )
        return result is not None


class RevealBotSync:
    """
    Sincroniza métricas do BigQuery para Revealbot
    """
    
    def __init__(self, revealbot_key: str, bq_client, project_id: str):
        self.client = RevealBotClient(revealbot_key)
        self.bq = bq_client
        self.project_id = project_id
    
    def sync_campaign_metrics(self, hours: int = 24) -> Dict[str, Any]:
        """
        Busca métricas do BigQuery e envia para Revealbot
        """
        query = f"""
        WITH campaign_metrics AS (
            SELECT
                COALESCE(
                    JSON_EXTRACT_SCALAR(custom_data, '$.campaign_id'),
                    REGEXP_EXTRACT(fbclid, r'^([^_]+)')
                ) as campaign_id,
                
                AVG(ltv_score) as avg_ltv_score,
                AVG(trust_score) as avg_trust_score,
                AVG(intent_score) as avg_intent_score,
                
                COUNTIF(event_name = 'Purchase') as conversions,
                SUM(CASE WHEN event_name = 'Purchase' 
                    THEN SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) 
                    ELSE 0 END) as revenue,
                
                COUNTIF(trust_score < 0.4) / COUNT(*) as ivt_rate,
                COUNTIF(trust_score < 0.3) / COUNT(*) as bot_rate,
                
                COUNT(*) as events
                
            FROM `{self.project_id}.ssi_shadow.events`
            WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
            GROUP BY campaign_id
            HAVING campaign_id IS NOT NULL AND events >= 10
        )
        SELECT * FROM campaign_metrics
        """
        
        results = {
            'synced': 0,
            'failed': 0,
            'campaigns': []
        }
        
        for row in self.bq.query(query).result():
            # Calcular scores compostos
            quality_score = (
                row.avg_trust_score * 0.4 +
                (1 - row.ivt_rate) * 0.3 +
                row.avg_intent_score * 0.3
            )
            
            conversion_prob = min(1.0, row.conversions / max(1, row.events) * 10)
            predicted_value = row.avg_ltv_score * 200  # Converter score para valor estimado
            
            metrics = RevealBotMetrics(
                campaign_id=row.campaign_id,
                ad_account_id='',  # Será preenchido pelo Revealbot
                ssi_ltv_score=float(row.avg_ltv_score or 0),
                ssi_trust_score=float(row.avg_trust_score or 0),
                ssi_intent_score=float(row.avg_intent_score or 0),
                ssi_predicted_value=predicted_value,
                ssi_conversion_probability=conversion_prob,
                ssi_quality_score=quality_score,
                ivt_rate=float(row.ivt_rate or 0),
                bot_rate=float(row.bot_rate or 0)
            )
            
            success = self.client.push_custom_metrics(metrics)
            
            if success:
                results['synced'] += 1
            else:
                results['failed'] += 1
            
            results['campaigns'].append({
                'campaign_id': row.campaign_id,
                'success': success,
                'metrics': {
                    'ltv_score': metrics.ssi_ltv_score,
                    'trust_score': metrics.ssi_trust_score,
                    'quality_score': quality_score
                }
            })
        
        logger.info(f"Revealbot sync: {results['synced']} synced, {results['failed']} failed")
        
        return results

# =============================================================================
# 2. CLEARBIT INTEGRATION
# =============================================================================

class ClearbitClient(BaseAPIClient):
    """
    Clearbit Integration
    
    Enriquece dados de visitantes com informações de empresa.
    Útil para B2B ou high-ticket e-commerce.
    
    Pricing: $99+/mês
    Docs: https://clearbit.com/docs
    """
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.session.headers['Authorization'] = f'Bearer {api_key}'
    
    def reveal_company(self, ip: str) -> Optional[Dict]:
        """
        Identifica empresa por IP (Clearbit Reveal)
        """
        result = self._request(
            'GET',
            f"https://reveal.clearbit.com/v1/companies/find",
            params={'ip': ip}
        )
        
        if result and 'company' in result:
            return {
                'name': result['company'].get('name'),
                'domain': result['company'].get('domain'),
                'industry': result['company'].get('category', {}).get('industry'),
                'employees': result['company'].get('metrics', {}).get('employees'),
                'revenue': result['company'].get('metrics', {}).get('estimatedAnnualRevenue'),
                'country': result['company'].get('geo', {}).get('country'),
                'type': result['company'].get('type')  # 'company', 'education', 'government'
            }
        
        return None
    
    def enrich_email(self, email: str) -> Optional[Dict]:
        """
        Enriquece dados a partir de email
        """
        result = self._request(
            'GET',
            f"https://person-stream.clearbit.com/v2/combined/find",
            params={'email': email}
        )
        
        if result:
            person = result.get('person', {})
            company = result.get('company', {})
            
            return {
                'person': {
                    'name': person.get('name', {}).get('fullName'),
                    'title': person.get('employment', {}).get('title'),
                    'seniority': person.get('employment', {}).get('seniority'),
                    'linkedin': person.get('linkedin', {}).get('handle')
                },
                'company': {
                    'name': company.get('name'),
                    'domain': company.get('domain'),
                    'industry': company.get('category', {}).get('industry'),
                    'employees': company.get('metrics', {}).get('employees')
                }
            }
        
        return None

# =============================================================================
# 3. META CONVERSION LIFT API
# =============================================================================

class MetaConversionLiftClient(BaseAPIClient):
    """
    Meta Conversion Lift API
    
    Mede incrementalidade real de campanhas via holdout groups.
    GRATUITO - parte da Marketing API.
    
    Docs: https://developers.facebook.com/docs/marketing-api/conversion-lift
    """
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self, access_token: str, ad_account_id: str):
        super().__init__(access_token)
        self.access_token = access_token
        self.ad_account_id = ad_account_id
    
    def create_lift_study(
        self,
        name: str,
        objective: str = 'CONVERSIONS',
        treatment_percentage: int = 90,
        start_time: datetime = None,
        end_time: datetime = None
    ) -> Optional[Dict]:
        """
        Cria um estudo de Conversion Lift.
        
        O Meta vai dividir o público:
        - treatment_percentage% vê anúncios
        - (100 - treatment_percentage)% não vê (holdout)
        
        Depois de 2-4 semanas, você pode medir incrementalidade real.
        """
        if start_time is None:
            start_time = datetime.now()
        if end_time is None:
            end_time = start_time + timedelta(days=28)
        
        payload = {
            'access_token': self.access_token,
            'name': name,
            'objective': objective,
            'cells': json.dumps([
                {'treatment_percentage': treatment_percentage},
                {'treatment_percentage': 0}  # Holdout
            ]),
            'start_time': int(start_time.timestamp()),
            'end_time': int(end_time.timestamp())
        }
        
        result = self._request(
            'POST',
            f"{self.BASE_URL}/{self.ad_account_id}/lift_studies",
            params=payload
        )
        
        return result
    
    def get_lift_study_results(self, study_id: str) -> Optional[Dict]:
        """
        Obtém resultados de um estudo de lift
        """
        result = self._request(
            'GET',
            f"{self.BASE_URL}/{study_id}",
            params={
                'access_token': self.access_token,
                'fields': 'name,status,results,incremental_conversions,incremental_revenue'
            }
        )
        
        if result:
            return {
                'name': result.get('name'),
                'status': result.get('status'),
                'incremental_conversions': result.get('incremental_conversions'),
                'incremental_revenue': result.get('incremental_revenue'),
                'lift_percentage': result.get('results', {}).get('lift_percentage'),
                'confidence': result.get('results', {}).get('confidence')
            }
        
        return None
    
    def list_lift_studies(self) -> List[Dict]:
        """Lista todos os estudos de lift"""
        result = self._request(
            'GET',
            f"{self.BASE_URL}/{self.ad_account_id}/lift_studies",
            params={'access_token': self.access_token}
        )
        
        return result.get('data', []) if result else []

# =============================================================================
# 4. HUNTER.IO INTEGRATION
# =============================================================================

class HunterClient(BaseAPIClient):
    """
    Hunter.io Integration
    
    Verifica validade de emails antes de hashear para CAPI.
    Evita enviar emails inválidos que prejudicam EMQ.
    
    Pricing: $49+/mês (1000 verifications)
    Docs: https://hunter.io/api-documentation
    """
    
    BASE_URL = "https://api.hunter.io/v2"
    
    def verify_email(self, email: str) -> Dict:
        """
        Verifica se email é válido e deliverable
        """
        result = self._request(
            'GET',
            f"{self.BASE_URL}/email-verifier",
            params={
                'email': email,
                'api_key': self.api_key
            }
        )
        
        if result and 'data' in result:
            data = result['data']
            return {
                'email': email,
                'valid': data.get('result') == 'deliverable',
                'result': data.get('result'),  # 'deliverable', 'undeliverable', 'risky', 'unknown'
                'score': data.get('score'),  # 0-100
                'disposable': data.get('disposable', False),
                'webmail': data.get('webmail', False),
                'mx_records': data.get('mx_records', False),
                'smtp_check': data.get('smtp_check', False)
            }
        
        return {
            'email': email,
            'valid': False,
            'result': 'error'
        }
    
    def should_hash_email(self, email: str) -> bool:
        """
        Decide se email deve ser hasheado e enviado para CAPI.
        
        Retorna False para emails inválidos ou de baixa qualidade,
        que prejudicariam o EMQ.
        """
        verification = self.verify_email(email)
        
        # Não enviar emails descartáveis
        if verification.get('disposable'):
            return False
        
        # Não enviar se não tem MX records
        if not verification.get('mx_records'):
            return False
        
        # Enviar se deliverable ou score alto
        if verification.get('result') == 'deliverable':
            return True
        
        if verification.get('score', 0) >= 70:
            return True
        
        return False

# =============================================================================
# 5. BIGQUERY ML NATIVE MODELS
# =============================================================================

class BigQueryMLClient:
    """
    BigQuery ML Integration
    
    Cria e usa modelos ML diretamente no BigQuery.
    Mais simples que Vertex AI para casos básicos.
    
    Pricing: $5/TB processado + training costs
    Docs: https://cloud.google.com/bigquery-ml/docs
    """
    
    def __init__(self, bq_client, project_id: str, dataset_id: str = 'ssi_shadow'):
        self.bq = bq_client
        self.project_id = project_id
        self.dataset_id = dataset_id
    
    def create_ltv_model(self, training_days: int = 90) -> str:
        """
        Cria modelo de LTV usando BOOSTED_TREE_REGRESSOR
        """
        query = f"""
        CREATE OR REPLACE MODEL `{self.project_id}.{self.dataset_id}.bqml_ltv_model`
        OPTIONS(
            model_type='BOOSTED_TREE_REGRESSOR',
            input_label_cols=['total_value'],
            max_iterations=50,
            early_stop=TRUE,
            data_split_method='AUTO_SPLIT'
        ) AS
        
        WITH user_features AS (
            SELECT
                ssi_id,
                COUNT(*) as total_events,
                COUNTIF(event_name = 'PageView') as pageviews,
                COUNTIF(event_name = 'ViewContent') as product_views,
                COUNTIF(event_name = 'AddToCart') as add_to_carts,
                COUNTIF(event_name = 'InitiateCheckout') as checkouts,
                COUNTIF(event_name = 'Purchase') as purchases,
                AVG(trust_score) as avg_trust_score,
                AVG(intent_score) as avg_intent_score,
                COUNTIF(device_type = 'mobile') / COUNT(*) as mobile_rate,
                SUM(CASE WHEN event_name = 'Purchase' 
                    THEN SAFE_CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) 
                    ELSE 0 END) as total_value
            FROM `{self.project_id}.{self.dataset_id}.events`
            WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {training_days} DAY)
            GROUP BY ssi_id
            HAVING total_events >= 3 AND total_value > 0
        )
        
        SELECT
            pageviews,
            product_views,
            add_to_carts,
            checkouts,
            purchases,
            avg_trust_score,
            avg_intent_score,
            mobile_rate,
            total_value
        FROM user_features
        """
        
        job = self.bq.query(query)
        job.result()  # Wait for completion
        
        return f"{self.project_id}.{self.dataset_id}.bqml_ltv_model"
    
    def create_intent_model(self, training_days: int = 30) -> str:
        """
        Cria modelo de Intent (classificação binária)
        """
        query = f"""
        CREATE OR REPLACE MODEL `{self.project_id}.{self.dataset_id}.bqml_intent_model`
        OPTIONS(
            model_type='BOOSTED_TREE_CLASSIFIER',
            input_label_cols=['converted'],
            max_iterations=50,
            early_stop=TRUE
        ) AS
        
        SELECT
            COUNTIF(event_name = 'PageView') as pageviews,
            COUNTIF(event_name = 'ViewContent') as product_views,
            COUNTIF(event_name = 'AddToCart') as add_to_carts,
            AVG(trust_score) as avg_trust_score,
            AVG(scroll_depth) as avg_scroll_depth,
            MAX(CASE WHEN event_name IN ('InitiateCheckout', 'Purchase') THEN 1 ELSE 0 END) as converted
        FROM `{self.project_id}.{self.dataset_id}.events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {training_days} DAY)
        GROUP BY ssi_id
        HAVING pageviews >= 1
        """
        
        job = self.bq.query(query)
        job.result()
        
        return f"{self.project_id}.{self.dataset_id}.bqml_intent_model"
    
    def predict_ltv(self, ssi_ids: List[str] = None) -> List[Dict]:
        """
        Faz predição de LTV para usuários
        """
        where_clause = ""
        if ssi_ids:
            ids_str = ", ".join([f"'{id}'" for id in ssi_ids])
            where_clause = f"WHERE ssi_id IN ({ids_str})"
        
        query = f"""
        SELECT
            ssi_id,
            predicted_total_value as predicted_ltv,
            predicted_total_value_interval.lower_bound as ltv_lower,
            predicted_total_value_interval.upper_bound as ltv_upper
        FROM ML.PREDICT(
            MODEL `{self.project_id}.{self.dataset_id}.bqml_ltv_model`,
            (
                SELECT
                    ssi_id,
                    COUNTIF(event_name = 'PageView') as pageviews,
                    COUNTIF(event_name = 'ViewContent') as product_views,
                    COUNTIF(event_name = 'AddToCart') as add_to_carts,
                    COUNTIF(event_name = 'InitiateCheckout') as checkouts,
                    COUNTIF(event_name = 'Purchase') as purchases,
                    AVG(trust_score) as avg_trust_score,
                    AVG(intent_score) as avg_intent_score,
                    COUNTIF(device_type = 'mobile') / COUNT(*) as mobile_rate
                FROM `{self.project_id}.{self.dataset_id}.events`
                WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 7 DAY)
                {where_clause}
                GROUP BY ssi_id
            )
        )
        """
        
        results = []
        for row in self.bq.query(query).result():
            results.append({
                'ssi_id': row.ssi_id,
                'predicted_ltv': float(row.predicted_ltv),
                'ltv_lower': float(row.ltv_lower) if row.ltv_lower else None,
                'ltv_upper': float(row.ltv_upper) if row.ltv_upper else None
            })
        
        return results
    
    def predict_intent(self, ssi_ids: List[str] = None) -> List[Dict]:
        """
        Faz predição de intent para usuários
        """
        where_clause = ""
        if ssi_ids:
            ids_str = ", ".join([f"'{id}'" for id in ssi_ids])
            where_clause = f"WHERE ssi_id IN ({ids_str})"
        
        query = f"""
        SELECT
            ssi_id,
            predicted_converted as will_convert,
            predicted_converted_probs[OFFSET(1)].prob as conversion_probability
        FROM ML.PREDICT(
            MODEL `{self.project_id}.{self.dataset_id}.bqml_intent_model`,
            (
                SELECT
                    ssi_id,
                    COUNTIF(event_name = 'PageView') as pageviews,
                    COUNTIF(event_name = 'ViewContent') as product_views,
                    COUNTIF(event_name = 'AddToCart') as add_to_carts,
                    AVG(trust_score) as avg_trust_score,
                    AVG(scroll_depth) as avg_scroll_depth
                FROM `{self.project_id}.{self.dataset_id}.events`
                WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
                {where_clause}
                GROUP BY ssi_id
            )
        )
        """
        
        results = []
        for row in self.bq.query(query).result():
            results.append({
                'ssi_id': row.ssi_id,
                'will_convert': row.will_convert == 1,
                'conversion_probability': float(row.conversion_probability)
            })
        
        return results
    
    def evaluate_model(self, model_name: str) -> Dict:
        """
        Avalia performance do modelo
        """
        query = f"""
        SELECT *
        FROM ML.EVALUATE(MODEL `{self.project_id}.{self.dataset_id}.{model_name}`)
        """
        
        result = list(self.bq.query(query).result())[0]
        
        return dict(result)

# =============================================================================
# UNIFIED ENRICHMENT SERVICE
# =============================================================================

class EnrichmentService:
    """
    Serviço unificado de enriquecimento de dados
    """
    
    def __init__(
        self,
        clearbit_key: str = None,
        hunter_key: str = None,
        revealbot_key: str = None
    ):
        self.clearbit = ClearbitClient(clearbit_key) if clearbit_key else None
        self.hunter = HunterClient(hunter_key) if hunter_key else None
        self.revealbot = RevealBotClient(revealbot_key) if revealbot_key else None
    
    def enrich_visitor(self, ip: str, email: str = None) -> Dict:
        """
        Enriquece dados de visitante com todas as fontes disponíveis
        """
        enrichment = {
            'ip': ip,
            'timestamp': datetime.now().isoformat()
        }
        
        # Clearbit: Company reveal
        if self.clearbit:
            company = self.clearbit.reveal_company(ip)
            if company:
                enrichment['company'] = company
        
        # Hunter: Email verification
        if self.hunter and email:
            verification = self.hunter.verify_email(email)
            enrichment['email_verification'] = verification
            enrichment['email_valid'] = verification.get('valid', False)
        
        return enrichment
    
    def should_send_to_capi(
        self, 
        email: str = None, 
        phone: str = None,
        trust_score: float = 0.5
    ) -> Dict[str, bool]:
        """
        Decide quais dados enviar para CAPI baseado em qualidade
        """
        result = {
            'send_email': False,
            'send_phone': False,
            'send_event': trust_score >= 0.4
        }
        
        # Verificar email
        if email and self.hunter:
            result['send_email'] = self.hunter.should_hash_email(email)
        elif email:
            # Sem Hunter, enviar se não for obviamente descartável
            disposable_domains = ['tempmail', 'guerrillamail', '10minutemail', 'mailinator']
            domain = email.split('@')[-1].lower() if '@' in email else ''
            result['send_email'] = not any(d in domain for d in disposable_domains)
        
        # Phone: enviar se tiver formato válido BR
        if phone:
            clean_phone = ''.join(filter(str.isdigit, phone))
            result['send_phone'] = len(clean_phone) >= 10
        
        return result

# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='SSI Shadow Enterprise Integrations')
    parser.add_argument('--action', required=True, 
                       choices=['test-clearbit', 'test-hunter', 'sync-revealbot', 'create-lift-study', 'train-bqml'])
    parser.add_argument('--ip', help='IP para Clearbit reveal')
    parser.add_argument('--email', help='Email para Hunter verification')
    parser.add_argument('--project', help='GCP Project ID')
    
    args = parser.parse_args()
    
    if args.action == 'test-clearbit':
        client = ClearbitClient(os.getenv('CLEARBIT_API_KEY', ''))
        result = client.reveal_company(args.ip or '8.8.8.8')
        print(json.dumps(result, indent=2))
    
    elif args.action == 'test-hunter':
        client = HunterClient(os.getenv('HUNTER_API_KEY', ''))
        result = client.verify_email(args.email or 'test@example.com')
        print(json.dumps(result, indent=2))
    
    elif args.action == 'train-bqml':
        from google.cloud import bigquery
        bq = bigquery.Client(project=args.project)
        client = BigQueryMLClient(bq, args.project)
        
        print("Training LTV model...")
        ltv_model = client.create_ltv_model()
        print(f"Created: {ltv_model}")
        
        print("\nTraining Intent model...")
        intent_model = client.create_intent_model()
        print(f"Created: {intent_model}")
        
        print("\nEvaluating LTV model...")
        eval_result = client.evaluate_model('bqml_ltv_model')
        print(json.dumps(eval_result, indent=2, default=str))

if __name__ == '__main__':
    main()
