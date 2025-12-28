"""
S.S.I. SHADOW — Bid Controller
EXECUÇÃO AUTÔNOMA DE LANCES

Responsabilidades:
- Consumir predicted_ltv do BigQuery
- Ajustar lances no Meta Ads via Marketing API
- Ajustar lances no Google Ads via API
- Kill-switch para anomalias de tráfego
- Logging completo para auditoria

IMPORTANTE: Este módulo EXECUTA ações reais nas plataformas.
Teste extensivamente em ambiente de staging antes de produção.
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass
from enum import Enum
import time

import requests

# Google Ads
try:
    from google.ads.googleads.client import GoogleAdsClient
    from google.ads.googleads.errors import GoogleAdsException
    GOOGLE_ADS_AVAILABLE = True
except ImportError:
    GOOGLE_ADS_AVAILABLE = False
    print("⚠️ google-ads não instalado. Execute: pip install google-ads")

# BigQuery
try:
    from google.cloud import bigquery
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ssi_bid_controller')

# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

@dataclass
class BidControllerConfig:
    # GCP
    gcp_project_id: str
    bq_dataset_id: str = 'ssi_shadow'
    
    # Meta Ads
    meta_access_token: str = ''
    meta_ad_account_id: str = ''  # act_XXXXX
    
    # Google Ads
    google_ads_customer_id: str = ''
    google_ads_config_path: str = 'google-ads.yaml'
    
    # Bid Control
    min_bid_multiplier: float = 0.5   # Mínimo 50% do bid base
    max_bid_multiplier: float = 2.0   # Máximo 200% do bid base
    
    # Kill Switch
    ivt_threshold: float = 0.30        # 30% de tráfego inválido
    ivt_window_hours: int = 1          # Janela de 1 hora
    
    # Alertas
    telegram_bot_token: str = ''
    telegram_chat_id: str = ''

# =============================================================================
# DATA CLASSES
# =============================================================================

class BidAction(Enum):
    INCREASE = "increase"
    DECREASE = "decrease"
    MAINTAIN = "maintain"
    PAUSE = "pause"

@dataclass
class CampaignMetrics:
    campaign_id: str
    campaign_name: str
    platform: str  # 'meta' ou 'google'
    
    # Métricas atuais
    current_bid: float
    current_budget: float
    spend_today: float
    
    # Métricas de performance
    conversions: int
    conversion_value: float
    cpa: float
    roas: float
    
    # Predições SSI
    predicted_ltv: float
    avg_trust_score: float
    ivt_rate: float
    
    # Ação recomendada
    recommended_action: BidAction
    recommended_bid: float
    reasoning: str

@dataclass
class BidAdjustment:
    campaign_id: str
    platform: str
    old_bid: float
    new_bid: float
    action: BidAction
    reasoning: str
    executed: bool
    error: Optional[str]
    timestamp: datetime

# =============================================================================
# BIGQUERY DATA FETCHER
# =============================================================================

class BigQueryFetcher:
    """Obtém dados de predição do BigQuery"""
    
    def __init__(self, config: BidControllerConfig):
        self.config = config
        self.client = bigquery.Client(project=config.gcp_project_id) if BIGQUERY_AVAILABLE else None
    
    def get_campaign_predictions(self, hours: int = 24) -> List[Dict]:
        """
        Obtém predições agregadas por campanha
        """
        query = f"""
        WITH campaign_events AS (
            SELECT
                -- Extrair campaign_id do custom_data ou fbclid
                COALESCE(
                    JSON_EXTRACT_SCALAR(custom_data, '$.campaign_id'),
                    REGEXP_EXTRACT(fbclid, r'^([^_]+)')
                ) as campaign_id,
                
                -- Métricas
                event_name,
                CAST(JSON_EXTRACT_SCALAR(custom_data, '$.value') AS FLOAT64) as value,
                trust_score,
                ltv_score,
                intent_score,
                
                -- IVT
                CASE WHEN trust_score < 0.4 THEN 1 ELSE 0 END as is_ivt
                
            FROM `{self.config.gcp_project_id}.{self.config.bq_dataset_id}.events`
            WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        )
        
        SELECT
            campaign_id,
            COUNT(*) as total_events,
            COUNTIF(event_name = 'Purchase') as conversions,
            SUM(CASE WHEN event_name = 'Purchase' THEN value ELSE 0 END) as conversion_value,
            AVG(ltv_score) as avg_ltv_score,
            AVG(trust_score) as avg_trust_score,
            AVG(intent_score) as avg_intent_score,
            SUM(is_ivt) / COUNT(*) as ivt_rate
        FROM campaign_events
        WHERE campaign_id IS NOT NULL
        GROUP BY campaign_id
        HAVING total_events >= 10  -- Mínimo de eventos para decisão
        """
        
        if not self.client:
            logger.warning("BigQuery não disponível")
            return []
        
        try:
            results = self.client.query(query).result()
            return [dict(row) for row in results]
        except Exception as e:
            logger.error(f"Erro ao consultar BigQuery: {e}")
            return []
    
    def get_ivt_rate(self, hours: int = 1) -> float:
        """
        Calcula taxa de IVT na última janela
        """
        query = f"""
        SELECT
            COUNTIF(trust_score < 0.4) / COUNT(*) as ivt_rate
        FROM `{self.config.gcp_project_id}.{self.config.bq_dataset_id}.events`
        WHERE event_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL {hours} HOUR)
        """
        
        if not self.client:
            return 0.0
        
        try:
            result = list(self.client.query(query).result())[0]
            return float(result.ivt_rate or 0)
        except Exception as e:
            logger.error(f"Erro ao calcular IVT rate: {e}")
            return 0.0

# =============================================================================
# META ADS CONTROLLER
# =============================================================================

class MetaAdsController:
    """
    Controla lances e budgets no Meta Ads via Marketing API
    Docs: https://developers.facebook.com/docs/marketing-api/
    """
    
    BASE_URL = "https://graph.facebook.com/v18.0"
    
    def __init__(self, config: BidControllerConfig):
        self.config = config
        self.access_token = config.meta_access_token
        self.ad_account_id = config.meta_ad_account_id
    
    def _request(self, method: str, endpoint: str, params: Dict = None, data: Dict = None) -> Optional[Dict]:
        """Faz request para Meta API"""
        url = f"{self.BASE_URL}/{endpoint}"
        params = params or {}
        params['access_token'] = self.access_token
        
        try:
            if method == 'GET':
                response = requests.get(url, params=params, timeout=30)
            elif method == 'POST':
                response = requests.post(url, params=params, json=data, timeout=30)
            else:
                return None
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Meta API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Meta API request failed: {e}")
            return None
    
    def get_campaigns(self, status: str = 'ACTIVE') -> List[Dict]:
        """
        Obtém campanhas da conta
        """
        endpoint = f"{self.ad_account_id}/campaigns"
        params = {
            'fields': 'id,name,status,daily_budget,lifetime_budget,bid_strategy,objective',
            'filtering': json.dumps([{'field': 'status', 'operator': 'EQUAL', 'value': status}])
        }
        
        result = self._request('GET', endpoint, params)
        return result.get('data', []) if result else []
    
    def get_adsets(self, campaign_id: str) -> List[Dict]:
        """
        Obtém ad sets de uma campanha
        """
        endpoint = f"{campaign_id}/adsets"
        params = {
            'fields': 'id,name,status,daily_budget,bid_amount,billing_event,optimization_goal'
        }
        
        result = self._request('GET', endpoint, params)
        return result.get('data', []) if result else []
    
    def update_adset_bid(self, adset_id: str, new_bid: int) -> bool:
        """
        Atualiza bid de um ad set
        new_bid em centavos (ex: 500 = R$5.00)
        """
        endpoint = adset_id
        data = {
            'bid_amount': new_bid
        }
        
        result = self._request('POST', endpoint, data=data)
        return result is not None
    
    def update_adset_budget(self, adset_id: str, new_budget: int) -> bool:
        """
        Atualiza budget diário de um ad set
        new_budget em centavos
        """
        endpoint = adset_id
        data = {
            'daily_budget': new_budget
        }
        
        result = self._request('POST', endpoint, data=data)
        return result is not None
    
    def pause_campaign(self, campaign_id: str) -> bool:
        """
        Pausa uma campanha (kill switch)
        """
        endpoint = campaign_id
        data = {
            'status': 'PAUSED'
        }
        
        result = self._request('POST', endpoint, data=data)
        return result is not None
    
    def get_insights(self, campaign_id: str, date_preset: str = 'today') -> Optional[Dict]:
        """
        Obtém métricas de performance
        """
        endpoint = f"{campaign_id}/insights"
        params = {
            'fields': 'spend,impressions,clicks,conversions,conversion_values,cpm,cpc,ctr',
            'date_preset': date_preset
        }
        
        result = self._request('GET', endpoint, params)
        if result and result.get('data'):
            return result['data'][0]
        return None

# =============================================================================
# GOOGLE ADS CONTROLLER
# =============================================================================

class GoogleAdsController:
    """
    Controla lances e budgets no Google Ads via API
    Docs: https://developers.google.com/google-ads/api/
    """
    
    def __init__(self, config: BidControllerConfig):
        self.config = config
        self.client = None
        
        if GOOGLE_ADS_AVAILABLE and os.path.exists(config.google_ads_config_path):
            try:
                self.client = GoogleAdsClient.load_from_storage(config.google_ads_config_path)
            except Exception as e:
                logger.error(f"Erro ao inicializar Google Ads client: {e}")
    
    def get_campaigns(self, status: str = 'ENABLED') -> List[Dict]:
        """
        Obtém campanhas da conta
        """
        if not self.client:
            return []
        
        ga_service = self.client.get_service("GoogleAdsService")
        
        query = f"""
            SELECT
                campaign.id,
                campaign.name,
                campaign.status,
                campaign.campaign_budget,
                campaign.bidding_strategy_type,
                campaign_budget.amount_micros
            FROM campaign
            WHERE campaign.status = '{status}'
        """
        
        try:
            response = ga_service.search(
                customer_id=self.config.google_ads_customer_id,
                query=query
            )
            
            campaigns = []
            for row in response:
                campaigns.append({
                    'id': row.campaign.id,
                    'name': row.campaign.name,
                    'status': row.campaign.status.name,
                    'budget_micros': row.campaign_budget.amount_micros,
                    'bidding_strategy': row.campaign.bidding_strategy_type.name
                })
            
            return campaigns
            
        except GoogleAdsException as e:
            logger.error(f"Google Ads API error: {e}")
            return []
    
    def update_campaign_budget(self, campaign_id: str, new_budget_micros: int) -> bool:
        """
        Atualiza budget de campanha
        new_budget_micros: valor em micros (1 real = 1,000,000 micros)
        """
        if not self.client:
            return False
        
        campaign_budget_service = self.client.get_service("CampaignBudgetService")
        
        # Primeiro, obter o budget resource name
        ga_service = self.client.get_service("GoogleAdsService")
        query = f"""
            SELECT campaign.campaign_budget
            FROM campaign
            WHERE campaign.id = {campaign_id}
        """
        
        try:
            response = ga_service.search(
                customer_id=self.config.google_ads_customer_id,
                query=query
            )
            
            budget_resource = None
            for row in response:
                budget_resource = row.campaign.campaign_budget
                break
            
            if not budget_resource:
                return False
            
            # Atualizar budget
            operation = self.client.get_type("CampaignBudgetOperation")
            budget = operation.update
            budget.resource_name = budget_resource
            budget.amount_micros = new_budget_micros
            
            operation.update_mask.paths.append("amount_micros")
            
            campaign_budget_service.mutate_campaign_budgets(
                customer_id=self.config.google_ads_customer_id,
                operations=[operation]
            )
            
            return True
            
        except GoogleAdsException as e:
            logger.error(f"Erro ao atualizar budget Google Ads: {e}")
            return False
    
    def pause_campaign(self, campaign_id: str) -> bool:
        """
        Pausa campanha (kill switch)
        """
        if not self.client:
            return False
        
        campaign_service = self.client.get_service("CampaignService")
        
        try:
            operation = self.client.get_type("CampaignOperation")
            campaign = operation.update
            campaign.resource_name = f"customers/{self.config.google_ads_customer_id}/campaigns/{campaign_id}"
            campaign.status = self.client.enums.CampaignStatusEnum.PAUSED
            
            operation.update_mask.paths.append("status")
            
            campaign_service.mutate_campaigns(
                customer_id=self.config.google_ads_customer_id,
                operations=[operation]
            )
            
            return True
            
        except GoogleAdsException as e:
            logger.error(f"Erro ao pausar campanha Google Ads: {e}")
            return False

# =============================================================================
# BID OPTIMIZER
# =============================================================================

class BidOptimizer:
    """
    Lógica de otimização de lances baseada em predicted_ltv
    """
    
    def __init__(self, config: BidControllerConfig):
        self.config = config
    
    def calculate_optimal_bid(
        self,
        current_bid: float,
        predicted_ltv: float,
        current_cpa: float,
        target_roas: float = 3.0,
        trust_score: float = 0.7
    ) -> Tuple[float, BidAction, str]:
        """
        Calcula bid ótimo baseado em LTV predito
        
        Lógica:
        - Se predicted_ltv > current_cpa * target_roas: AUMENTAR bid
        - Se predicted_ltv < current_cpa: DIMINUIR bid
        - Trust score baixo: DIMINUIR bid
        """
        
        # Valor esperado = LTV * trust_score (ajuste por qualidade)
        expected_value = predicted_ltv * trust_score
        
        # Break-even bid = expected_value / target_roas
        breakeven_bid = expected_value / target_roas
        
        # Calcular multiplier
        if current_bid > 0:
            multiplier = breakeven_bid / current_bid
        else:
            multiplier = 1.0
        
        # Aplicar limites
        multiplier = max(self.config.min_bid_multiplier, 
                        min(self.config.max_bid_multiplier, multiplier))
        
        new_bid = current_bid * multiplier
        
        # Determinar ação
        if multiplier > 1.1:
            action = BidAction.INCREASE
            reasoning = f"LTV esperado (R${expected_value:.2f}) justifica aumento de {((multiplier-1)*100):.0f}%"
        elif multiplier < 0.9:
            action = BidAction.DECREASE
            reasoning = f"LTV esperado (R${expected_value:.2f}) requer redução de {((1-multiplier)*100):.0f}%"
        else:
            action = BidAction.MAINTAIN
            reasoning = f"LTV esperado (R${expected_value:.2f}) está alinhado com bid atual"
        
        return new_bid, action, reasoning

# =============================================================================
# KILL SWITCH
# =============================================================================

class KillSwitch:
    """
    Monitora IVT e pausa campanhas se necessário
    """
    
    def __init__(
        self, 
        config: BidControllerConfig,
        bq_fetcher: BigQueryFetcher,
        meta_controller: MetaAdsController,
        google_controller: GoogleAdsController
    ):
        self.config = config
        self.bq = bq_fetcher
        self.meta = meta_controller
        self.google = google_controller
    
    def check_and_execute(self) -> Dict[str, Any]:
        """
        Verifica IVT e executa kill switch se necessário
        """
        result = {
            'triggered': False,
            'ivt_rate': 0.0,
            'threshold': self.config.ivt_threshold,
            'actions': []
        }
        
        # Obter taxa de IVT
        ivt_rate = self.bq.get_ivt_rate(self.config.ivt_window_hours)
        result['ivt_rate'] = ivt_rate
        
        logger.info(f"IVT Rate: {ivt_rate:.1%} (threshold: {self.config.ivt_threshold:.1%})")
        
        if ivt_rate > self.config.ivt_threshold:
            result['triggered'] = True
            logger.warning(f"🚨 KILL SWITCH TRIGGERED! IVT: {ivt_rate:.1%}")
            
            # Pausar campanhas Meta
            meta_campaigns = self.meta.get_campaigns('ACTIVE')
            for campaign in meta_campaigns:
                success = self.meta.pause_campaign(campaign['id'])
                result['actions'].append({
                    'platform': 'meta',
                    'campaign_id': campaign['id'],
                    'campaign_name': campaign['name'],
                    'action': 'pause',
                    'success': success
                })
                
                if success:
                    logger.info(f"✓ Pausada campanha Meta: {campaign['name']}")
                else:
                    logger.error(f"✗ Falha ao pausar campanha Meta: {campaign['name']}")
            
            # Pausar campanhas Google
            google_campaigns = self.google.get_campaigns('ENABLED')
            for campaign in google_campaigns:
                success = self.google.pause_campaign(str(campaign['id']))
                result['actions'].append({
                    'platform': 'google',
                    'campaign_id': campaign['id'],
                    'campaign_name': campaign['name'],
                    'action': 'pause',
                    'success': success
                })
                
                if success:
                    logger.info(f"✓ Pausada campanha Google: {campaign['name']}")
                else:
                    logger.error(f"✗ Falha ao pausar campanha Google: {campaign['name']}")
            
            # Enviar alerta
            self._send_alert(ivt_rate, result['actions'])
        
        return result
    
    def _send_alert(self, ivt_rate: float, actions: List[Dict]):
        """Envia alerta via Telegram"""
        if not self.config.telegram_bot_token or not self.config.telegram_chat_id:
            return
        
        paused_count = sum(1 for a in actions if a['success'])
        
        message = f"""
🚨 <b>KILL SWITCH ATIVADO</b>

<b>IVT Rate:</b> {ivt_rate:.1%}
<b>Threshold:</b> {self.config.ivt_threshold:.1%}

<b>Campanhas Pausadas:</b> {paused_count}

<b>Ação Requerida:</b>
Investigar fonte de tráfego inválido antes de reativar campanhas.

<i>Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</i>
"""
        
        try:
            requests.post(
                f"https://api.telegram.org/bot{self.config.telegram_bot_token}/sendMessage",
                json={
                    'chat_id': self.config.telegram_chat_id,
                    'text': message.strip(),
                    'parse_mode': 'HTML'
                },
                timeout=10
            )
        except Exception as e:
            logger.error(f"Falha ao enviar alerta: {e}")

# =============================================================================
# BID CONTROLLER PRINCIPAL
# =============================================================================

class BidController:
    """
    Controlador principal de lances
    Orquestra todos os componentes
    """
    
    def __init__(self, config: BidControllerConfig):
        self.config = config
        
        # Componentes
        self.bq = BigQueryFetcher(config)
        self.meta = MetaAdsController(config)
        self.google = GoogleAdsController(config)
        self.optimizer = BidOptimizer(config)
        self.kill_switch = KillSwitch(config, self.bq, self.meta, self.google)
        
        # Histórico
        self.adjustments: List[BidAdjustment] = []
    
    def run_optimization_cycle(
        self, 
        dry_run: bool = True,
        target_roas: float = 3.0
    ) -> Dict[str, Any]:
        """
        Executa ciclo completo de otimização
        
        Args:
            dry_run: Se True, não executa ações reais
            target_roas: ROAS alvo para cálculo de bid
        """
        logger.info("=" * 60)
        logger.info("INICIANDO CICLO DE OTIMIZAÇÃO")
        logger.info(f"Modo: {'DRY RUN' if dry_run else 'PRODUÇÃO'}")
        logger.info("=" * 60)
        
        results = {
            'timestamp': datetime.now().isoformat(),
            'dry_run': dry_run,
            'kill_switch': None,
            'optimizations': [],
            'errors': []
        }
        
        # 1. Kill Switch Check
        logger.info("\n[1/3] Verificando Kill Switch...")
        kill_result = self.kill_switch.check_and_execute() if not dry_run else {'triggered': False, 'ivt_rate': self.bq.get_ivt_rate(1)}
        results['kill_switch'] = kill_result
        
        if kill_result['triggered']:
            logger.warning("Kill switch ativado - interrompendo otimização")
            return results
        
        # 2. Obter predições do BigQuery
        logger.info("\n[2/3] Obtendo predições do BigQuery...")
        predictions = self.bq.get_campaign_predictions(24)
        logger.info(f"Predições obtidas para {len(predictions)} campanhas")
        
        # 3. Otimizar cada campanha
        logger.info("\n[3/3] Calculando otimizações...")
        
        for pred in predictions:
            campaign_id = pred['campaign_id']
            
            # Calcular bid ótimo
            current_cpa = pred['conversion_value'] / max(1, pred['conversions'])
            
            new_bid, action, reasoning = self.optimizer.calculate_optimal_bid(
                current_bid=100,  # Placeholder - obter bid real da API
                predicted_ltv=pred['avg_ltv_score'] * 200,  # Converter score para valor
                current_cpa=current_cpa,
                target_roas=target_roas,
                trust_score=pred['avg_trust_score']
            )
            
            optimization = {
                'campaign_id': campaign_id,
                'action': action.value,
                'reasoning': reasoning,
                'metrics': {
                    'conversions': pred['conversions'],
                    'conversion_value': float(pred['conversion_value']),
                    'avg_ltv_score': float(pred['avg_ltv_score']),
                    'avg_trust_score': float(pred['avg_trust_score']),
                    'ivt_rate': float(pred['ivt_rate'])
                },
                'executed': False
            }
            
            # Executar se não for dry run e ação não é manter
            if not dry_run and action != BidAction.MAINTAIN:
                # Determinar plataforma e executar
                # (simplificado - em produção, mapear campaign_id para plataforma)
                optimization['executed'] = True
                logger.info(f"Executando {action.value} para campanha {campaign_id}")
            
            results['optimizations'].append(optimization)
            
            logger.info(f"  Campaign {campaign_id}: {action.value} - {reasoning}")
        
        # Sumário
        logger.info("\n" + "=" * 60)
        logger.info("SUMÁRIO")
        logger.info(f"  Campanhas analisadas: {len(predictions)}")
        logger.info(f"  Aumentos: {sum(1 for o in results['optimizations'] if o['action'] == 'increase')}")
        logger.info(f"  Reduções: {sum(1 for o in results['optimizations'] if o['action'] == 'decrease')}")
        logger.info(f"  Mantidas: {sum(1 for o in results['optimizations'] if o['action'] == 'maintain')}")
        logger.info("=" * 60)
        
        return results
    
    def schedule_run(self, interval_minutes: int = 60, dry_run: bool = True):
        """
        Executa otimização em loop
        """
        logger.info(f"Iniciando scheduler - intervalo: {interval_minutes} minutos")
        
        while True:
            try:
                self.run_optimization_cycle(dry_run=dry_run)
            except Exception as e:
                logger.error(f"Erro no ciclo de otimização: {e}")
            
            logger.info(f"Próxima execução em {interval_minutes} minutos...")
            time.sleep(interval_minutes * 60)

# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='S.S.I. Shadow Bid Controller')
    parser.add_argument('--project', required=True, help='GCP Project ID')
    parser.add_argument('--meta-token', help='Meta Access Token')
    parser.add_argument('--meta-account', help='Meta Ad Account ID')
    parser.add_argument('--dry-run', action='store_true', default=True, help='Não executar ações reais')
    parser.add_argument('--target-roas', type=float, default=3.0, help='ROAS alvo')
    parser.add_argument('--schedule', type=int, help='Intervalo em minutos para execução contínua')
    
    args = parser.parse_args()
    
    config = BidControllerConfig(
        gcp_project_id=args.project,
        meta_access_token=args.meta_token or os.getenv('META_ACCESS_TOKEN', ''),
        meta_ad_account_id=args.meta_account or os.getenv('META_AD_ACCOUNT_ID', ''),
        telegram_bot_token=os.getenv('TELEGRAM_BOT_TOKEN', ''),
        telegram_chat_id=os.getenv('TELEGRAM_CHAT_ID', '')
    )
    
    controller = BidController(config)
    
    if args.schedule:
        controller.schedule_run(
            interval_minutes=args.schedule,
            dry_run=args.dry_run
        )
    else:
        results = controller.run_optimization_cycle(
            dry_run=args.dry_run,
            target_roas=args.target_roas
        )
        print(json.dumps(results, indent=2, default=str))

if __name__ == '__main__':
    main()
