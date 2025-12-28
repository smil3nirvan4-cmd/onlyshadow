"""
S.S.I. SHADOW — Predictive Intelligence Engine
Versão: 1.0.0

Módulos:
- Trends Collector: PyTrends, Semrush
- Blue Ocean Scorer: Cálculo de oportunidades
- Prophet Forecaster: Previsão de demanda
- Alert System: Notificações Telegram
- Main Engine: Orquestração
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
import argparse

# External dependencies
try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False
    print("⚠️ pytrends não instalado. Execute: pip install pytrends")

try:
    from prophet import Prophet
    PROPHET_AVAILABLE = True
except ImportError:
    PROPHET_AVAILABLE = False
    print("⚠️ prophet não instalado. Execute: pip install prophet")

try:
    import pandas as pd
    import numpy as np
    PANDAS_AVAILABLE = True
except ImportError:
    PANDAS_AVAILABLE = False
    print("⚠️ pandas/numpy não instalados. Execute: pip install pandas numpy")

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

try:
    from google.cloud import bigquery
    BIGQUERY_AVAILABLE = True
except ImportError:
    BIGQUERY_AVAILABLE = False
    print("⚠️ google-cloud-bigquery não instalado.")

# Logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('ssi_shadow')

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class TrendData:
    """Dados de uma keyword/trend"""
    keyword: str
    search_volume: int
    trend_score: float  # -100 a +100 (variação)
    rising_queries: List[str]
    top_queries: List[str]
    regional_interest: Dict[str, int]
    timestamp: datetime

@dataclass
class CompetitionData:
    """Dados de competição de uma keyword"""
    keyword: str
    cpc_estimate: float
    competition_score: float  # 0 a 1
    ad_density: float  # 0 a 1
    organic_results: int
    paid_results: int
    source: str

@dataclass
class BlueOceanScore:
    """Blue Ocean Score calculado"""
    keyword: str
    bos: float  # 0 a 1
    demand_score: float
    intent_score: float
    supply_score: float
    competition_score: float
    components: Dict[str, float]
    interpretation: str
    urgency: str

@dataclass
class Forecast:
    """Previsão de demanda"""
    keyword: str
    horizon_days: int
    predictions: List[Dict[str, Any]]
    mape: float
    confidence: float
    trend_direction: str

@dataclass
class Opportunity:
    """Oportunidade identificada"""
    keyword: str
    bos: float
    forecast: Optional[Forecast]
    action: str
    reasoning: str
    urgency: str
    timestamp: datetime

# =============================================================================
# TRENDS COLLECTOR
# =============================================================================

class TrendsCollector:
    """Coleta dados de Google Trends via PyTrends"""
    
    def __init__(self, geo: str = 'BR', language: str = 'pt-BR'):
        self.geo = geo
        self.language = language
        self.pytrends = None
        
        if PYTRENDS_AVAILABLE:
            self.pytrends = TrendReq(hl=language, tz=-180)  # UTC-3
    
    def get_interest_over_time(
        self, 
        keywords: List[str], 
        timeframe: str = 'today 3-m'
    ) -> Optional[pd.DataFrame]:
        """
        Obtém interesse ao longo do tempo.
        
        timeframe options:
        - 'now 1-H': última hora
        - 'now 4-H': últimas 4 horas
        - 'now 1-d': últimas 24 horas
        - 'now 7-d': últimos 7 dias
        - 'today 1-m': últimos 30 dias
        - 'today 3-m': últimos 90 dias
        - 'today 12-m': último ano
        """
        if not self.pytrends:
            logger.warning("PyTrends não disponível")
            return None
        
        try:
            self.pytrends.build_payload(
                kw_list=keywords[:5],  # Máximo 5 keywords por request
                cat=0,
                timeframe=timeframe,
                geo=self.geo,
                gprop=''
            )
            
            df = self.pytrends.interest_over_time()
            
            if df.empty:
                logger.warning(f"Nenhum dado retornado para: {keywords}")
                return None
            
            return df
            
        except Exception as e:
            logger.error(f"Erro ao obter trends: {e}")
            return None
    
    def get_related_queries(self, keyword: str) -> Dict[str, List[str]]:
        """Obtém queries relacionadas (rising e top)"""
        if not self.pytrends:
            return {'rising': [], 'top': []}
        
        try:
            self.pytrends.build_payload(
                kw_list=[keyword],
                cat=0,
                timeframe='today 3-m',
                geo=self.geo
            )
            
            related = self.pytrends.related_queries()
            
            result = {'rising': [], 'top': []}
            
            if keyword in related:
                if related[keyword]['rising'] is not None:
                    result['rising'] = related[keyword]['rising']['query'].tolist()[:10]
                if related[keyword]['top'] is not None:
                    result['top'] = related[keyword]['top']['query'].tolist()[:10]
            
            return result
            
        except Exception as e:
            logger.error(f"Erro ao obter related queries: {e}")
            return {'rising': [], 'top': []}
    
    def get_regional_interest(self, keyword: str) -> Dict[str, int]:
        """Obtém interesse por região"""
        if not self.pytrends:
            return {}
        
        try:
            self.pytrends.build_payload(
                kw_list=[keyword],
                cat=0,
                timeframe='today 3-m',
                geo=self.geo
            )
            
            by_region = self.pytrends.interest_by_region(
                resolution='REGION',
                inc_low_vol=True,
                inc_geo_code=False
            )
            
            return by_region[keyword].to_dict()
            
        except Exception as e:
            logger.error(f"Erro ao obter regional interest: {e}")
            return {}
    
    def collect(self, keywords: List[str]) -> List[TrendData]:
        """Coleta dados completos para lista de keywords"""
        results = []
        
        # Interesse ao longo do tempo
        df = self.get_interest_over_time(keywords)
        
        for kw in keywords:
            try:
                # Calcular trend score (variação percentual)
                trend_score = 0.0
                search_volume = 0
                
                if df is not None and kw in df.columns:
                    values = df[kw].values
                    if len(values) >= 2:
                        recent = np.mean(values[-7:])  # Última semana
                        previous = np.mean(values[-30:-7])  # 3 semanas anteriores
                        if previous > 0:
                            trend_score = ((recent - previous) / previous) * 100
                        search_volume = int(np.mean(values[-7:]))
                
                # Related queries
                related = self.get_related_queries(kw)
                
                # Regional
                regional = self.get_regional_interest(kw)
                
                results.append(TrendData(
                    keyword=kw,
                    search_volume=search_volume,
                    trend_score=round(trend_score, 2),
                    rising_queries=related['rising'],
                    top_queries=related['top'],
                    regional_interest=regional,
                    timestamp=datetime.now()
                ))
                
            except Exception as e:
                logger.error(f"Erro ao processar keyword '{kw}': {e}")
        
        return results

# =============================================================================
# COMPETITION ANALYZER
# =============================================================================

class CompetitionAnalyzer:
    """Analisa competição (placeholder para Semrush API)"""
    
    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or os.getenv('SEMRUSH_API_KEY')
    
    def estimate_competition(self, keyword: str, trend_data: Optional[TrendData] = None) -> CompetitionData:
        """
        Estima dados de competição.
        
        Sem API do Semrush, usa heurísticas baseadas nos dados de trends.
        """
        
        # Heurísticas básicas (substituir por Semrush API quando disponível)
        base_cpc = 0.50  # R$ base
        
        # Ajustar CPC baseado em trend score
        if trend_data:
            if trend_data.trend_score > 50:
                cpc_multiplier = 1.5  # Trending = mais caro
            elif trend_data.trend_score > 20:
                cpc_multiplier = 1.2
            elif trend_data.trend_score < -20:
                cpc_multiplier = 0.7  # Declining = mais barato
            else:
                cpc_multiplier = 1.0
        else:
            cpc_multiplier = 1.0
        
        # Estimar competição baseado em keywords relacionadas
        competition_score = 0.5  # Default médio
        if trend_data and trend_data.top_queries:
            # Mais queries top = mais competição
            competition_score = min(0.9, 0.3 + len(trend_data.top_queries) * 0.06)
        
        return CompetitionData(
            keyword=keyword,
            cpc_estimate=round(base_cpc * cpc_multiplier, 2),
            competition_score=round(competition_score, 2),
            ad_density=round(competition_score * 0.8, 2),  # Proxy
            organic_results=100,  # Placeholder
            paid_results=int(competition_score * 10),  # Placeholder
            source='heuristic'
        )
    
    def analyze_batch(
        self, 
        keywords: List[str], 
        trends: List[TrendData]
    ) -> List[CompetitionData]:
        """Analisa competição para múltiplas keywords"""
        trends_map = {t.keyword: t for t in trends}
        
        results = []
        for kw in keywords:
            trend_data = trends_map.get(kw)
            results.append(self.estimate_competition(kw, trend_data))
        
        return results

# =============================================================================
# BLUE OCEAN SCORER
# =============================================================================

class BlueOceanScorer:
    """Calcula Blue Ocean Score para identificar oportunidades"""
    
    def calculate_demand(self, trend: TrendData) -> float:
        """Calcula score de demanda (0-1)"""
        # Normalizar search volume (assumindo max ~100 do Google Trends)
        volume_score = min(1.0, trend.search_volume / 100)
        
        # Boost para trends crescentes
        if trend.trend_score > 30:
            volume_score = min(1.0, volume_score * 1.3)
        
        return round(volume_score, 3)
    
    def calculate_intent(self, trend: TrendData) -> float:
        """Estima intent de compra baseado em queries relacionadas"""
        intent_keywords = [
            'comprar', 'preço', 'onde', 'melhor', 'barato',
            'promoção', 'desconto', 'frete', 'entrega', 'loja',
            'buy', 'price', 'cheap', 'deal', 'shop'
        ]
        
        all_queries = trend.rising_queries + trend.top_queries
        if not all_queries:
            return 0.5  # Default médio
        
        intent_count = sum(
            1 for q in all_queries 
            if any(ik in q.lower() for ik in intent_keywords)
        )
        
        intent_score = min(1.0, 0.3 + (intent_count / len(all_queries)) * 0.7)
        return round(intent_score, 3)
    
    def calculate_supply(self, competition: CompetitionData) -> float:
        """Calcula score de oferta (0-1, menor = menos saturado)"""
        # Inverter competition score
        return round(1 - competition.competition_score, 3)
    
    def calculate_bos(
        self, 
        trend: TrendData, 
        competition: CompetitionData
    ) -> BlueOceanScore:
        """
        Calcula Blue Ocean Score.
        
        BOS = (Demanda × Intent) / (Oferta × Competição)
        
        BOS alto = oportunidade
        """
        demand = self.calculate_demand(trend)
        intent = self.calculate_intent(trend)
        supply = self.calculate_supply(competition)
        comp = competition.competition_score
        
        # Evitar divisão por zero
        denominator = max(0.1, (1 - supply) * max(0.1, comp))
        bos = (demand * intent) / denominator
        
        # Normalizar para 0-1
        bos = min(1.0, bos)
        
        # Interpretação
        if bos >= 0.8:
            interpretation = "Oportunidade excepcional - agir imediatamente"
            urgency = "critical"
        elif bos >= 0.6:
            interpretation = "Boa oportunidade - planejar entrada"
            urgency = "high"
        elif bos >= 0.4:
            interpretation = "Oportunidade moderada - avaliar ROI"
            urgency = "medium"
        else:
            interpretation = "Mercado saturado - evitar ou diferenciar"
            urgency = "low"
        
        return BlueOceanScore(
            keyword=trend.keyword,
            bos=round(bos, 3),
            demand_score=demand,
            intent_score=intent,
            supply_score=supply,
            competition_score=comp,
            components={
                'demand': demand,
                'intent': intent,
                'supply': supply,
                'competition': comp
            },
            interpretation=interpretation,
            urgency=urgency
        )

# =============================================================================
# PROPHET FORECASTER
# =============================================================================

class ProphetForecaster:
    """Previsão de demanda com Prophet"""
    
    def __init__(self):
        self.model = None
    
    def prepare_data(self, trend: TrendData, historical_df: pd.DataFrame) -> pd.DataFrame:
        """Prepara dados no formato do Prophet"""
        if historical_df is None or historical_df.empty:
            return pd.DataFrame()
        
        if trend.keyword not in historical_df.columns:
            return pd.DataFrame()
        
        df = pd.DataFrame({
            'ds': historical_df.index,
            'y': historical_df[trend.keyword].values
        })
        
        df = df.dropna()
        return df
    
    def forecast(
        self, 
        trend: TrendData, 
        historical_df: pd.DataFrame,
        horizon_days: int = 30
    ) -> Optional[Forecast]:
        """Gera forecast para uma keyword"""
        if not PROPHET_AVAILABLE:
            logger.warning("Prophet não disponível")
            return None
        
        df = self.prepare_data(trend, historical_df)
        
        if len(df) < 30:  # Mínimo de dados
            logger.warning(f"Dados insuficientes para forecast de '{trend.keyword}'")
            return None
        
        try:
            # Configurar modelo
            model = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True,
                yearly_seasonality=len(df) >= 365,
                changepoint_prior_scale=0.05,  # Conservador
                interval_width=0.8
            )
            
            # Treinar
            model.fit(df)
            
            # Prever
            future = model.make_future_dataframe(periods=horizon_days)
            forecast = model.predict(future)
            
            # Extrair predições futuras
            future_forecast = forecast.tail(horizon_days)
            predictions = [
                {
                    'date': row['ds'].strftime('%Y-%m-%d'),
                    'predicted': round(row['yhat'], 2),
                    'lower': round(row['yhat_lower'], 2),
                    'upper': round(row['yhat_upper'], 2)
                }
                for _, row in future_forecast.iterrows()
            ]
            
            # Calcular MAPE (usando cross-validation simplificado)
            # Em produção, usar prophet.diagnostics.cross_validation
            mape = self._estimate_mape(df, model)
            
            # Determinar direção do trend
            first_pred = predictions[0]['predicted']
            last_pred = predictions[-1]['predicted']
            if last_pred > first_pred * 1.1:
                trend_direction = "crescente"
            elif last_pred < first_pred * 0.9:
                trend_direction = "decrescente"
            else:
                trend_direction = "estável"
            
            return Forecast(
                keyword=trend.keyword,
                horizon_days=horizon_days,
                predictions=predictions,
                mape=mape,
                confidence=max(0, 1 - mape),
                trend_direction=trend_direction
            )
            
        except Exception as e:
            logger.error(f"Erro no forecast de '{trend.keyword}': {e}")
            return None
    
    def _estimate_mape(self, df: pd.DataFrame, model: Prophet) -> float:
        """Estima MAPE de forma simplificada"""
        try:
            # Usar últimos 20% dos dados como validação
            split = int(len(df) * 0.8)
            train = df.iloc[:split]
            test = df.iloc[split:]
            
            if len(test) < 5:
                return 0.15  # Default
            
            # Retreinar com dados de treino
            m = Prophet(
                daily_seasonality=False,
                weekly_seasonality=True
            )
            m.fit(train)
            
            # Prever período de teste
            future = m.make_future_dataframe(periods=len(test))
            forecast = m.predict(future)
            
            # Calcular MAPE
            y_true = test['y'].values
            y_pred = forecast.tail(len(test))['yhat'].values
            
            mape = np.mean(np.abs((y_true - y_pred) / y_true))
            return round(min(1, mape), 3)
            
        except:
            return 0.15  # Default em caso de erro

# =============================================================================
# ALERT SYSTEM
# =============================================================================

class AlertSystem:
    """Sistema de alertas via Telegram"""
    
    def __init__(
        self, 
        bot_token: Optional[str] = None,
        chat_id: Optional[str] = None
    ):
        self.bot_token = bot_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.chat_id = chat_id or os.getenv('TELEGRAM_CHAT_ID')
        self.enabled = bool(self.bot_token and self.chat_id)
    
    def send_alert(self, message: str, parse_mode: str = 'HTML') -> bool:
        """Envia alerta via Telegram"""
        if not self.enabled or not REQUESTS_AVAILABLE:
            logger.info(f"Telegram desabilitado. Mensagem: {message}")
            return False
        
        try:
            url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
            payload = {
                'chat_id': self.chat_id,
                'text': message,
                'parse_mode': parse_mode
            }
            
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
            
        except Exception as e:
            logger.error(f"Erro ao enviar alerta Telegram: {e}")
            return False
    
    def send_opportunity_alert(self, opportunity: Opportunity) -> bool:
        """Envia alerta formatado de oportunidade"""
        urgency_emoji = {
            'critical': '🔴',
            'high': '🟠',
            'medium': '🟡',
            'low': '🟢'
        }
        
        emoji = urgency_emoji.get(opportunity.urgency, '⚪')
        
        message = f"""
{emoji} <b>OPORTUNIDADE DETECTADA</b>

<b>Keyword:</b> {opportunity.keyword}
<b>BOS Score:</b> {opportunity.bos:.2f}
<b>Urgência:</b> {opportunity.urgency.upper()}

<b>Ação Sugerida:</b>
{opportunity.action}

<b>Raciocínio:</b>
{opportunity.reasoning}

<i>Timestamp: {opportunity.timestamp.strftime('%Y-%m-%d %H:%M')}</i>
"""
        return self.send_alert(message.strip())

# =============================================================================
# BIGQUERY CONNECTOR
# =============================================================================

class BigQueryConnector:
    """Conector para BigQuery"""
    
    def __init__(self, project_id: Optional[str] = None, dataset_id: str = 'ssi_shadow'):
        self.project_id = project_id or os.getenv('BQ_PROJECT_ID')
        self.dataset_id = dataset_id
        self.client = None
        
        if BIGQUERY_AVAILABLE and self.project_id:
            try:
                self.client = bigquery.Client(project=self.project_id)
            except Exception as e:
                logger.error(f"Erro ao conectar BigQuery: {e}")
    
    def save_trends(self, trends: List[TrendData], bos_scores: List[BlueOceanScore]):
        """Salva trends no BigQuery"""
        if not self.client:
            logger.warning("BigQuery não configurado")
            return
        
        table_id = f"{self.project_id}.{self.dataset_id}.trends"
        
        rows = []
        bos_map = {b.keyword: b for b in bos_scores}
        
        for trend in trends:
            bos = bos_map.get(trend.keyword)
            
            rows.append({
                'trend_id': hashlib.md5(f"{trend.keyword}:{trend.timestamp}".encode()).hexdigest()[:16],
                'keyword': trend.keyword,
                'search_volume': trend.search_volume,
                'trend_score': trend.trend_score,
                'bos_score': bos.bos if bos else None,
                'bos_components': json.dumps(bos.components) if bos else None,
                'urgency': bos.urgency if bos else None,
                'is_opportunity': bos.bos >= 0.6 if bos else False,
                'collected_at': trend.timestamp.isoformat()
            })
        
        try:
            errors = self.client.insert_rows_json(table_id, rows)
            if errors:
                logger.error(f"Erros ao inserir no BigQuery: {errors}")
            else:
                logger.info(f"Salvos {len(rows)} trends no BigQuery")
        except Exception as e:
            logger.error(f"Erro ao salvar no BigQuery: {e}")

# =============================================================================
# SHADOW ENGINE
# =============================================================================

class ShadowEngine:
    """Engine principal do Oráculo"""
    
    def __init__(
        self,
        geo: str = 'BR',
        telegram_token: Optional[str] = None,
        telegram_chat: Optional[str] = None,
        bq_project: Optional[str] = None
    ):
        self.trends_collector = TrendsCollector(geo=geo)
        self.competition_analyzer = CompetitionAnalyzer()
        self.bos_scorer = BlueOceanScorer()
        self.forecaster = ProphetForecaster()
        self.alert_system = AlertSystem(telegram_token, telegram_chat)
        self.bq_connector = BigQueryConnector(bq_project)
    
    def analyze_keywords(
        self,
        keywords: List[str],
        forecast_days: int = 30,
        alert_threshold: float = 0.6
    ) -> List[Opportunity]:
        """
        Análise completa de keywords.
        
        Returns:
            Lista de oportunidades identificadas
        """
        logger.info(f"Analisando {len(keywords)} keywords...")
        
        # 1. Coletar trends
        logger.info("Coletando trends...")
        trends = self.trends_collector.collect(keywords)
        
        if not trends:
            logger.warning("Nenhum trend coletado")
            return []
        
        # 2. Analisar competição
        logger.info("Analisando competição...")
        competitions = self.competition_analyzer.analyze_batch(keywords, trends)
        comp_map = {c.keyword: c for c in competitions}
        
        # 3. Calcular BOS
        logger.info("Calculando Blue Ocean Scores...")
        bos_scores = []
        for trend in trends:
            comp = comp_map.get(trend.keyword)
            if comp:
                bos = self.bos_scorer.calculate_bos(trend, comp)
                bos_scores.append(bos)
        
        # 4. Forecast para oportunidades
        logger.info("Gerando forecasts...")
        historical_df = self.trends_collector.get_interest_over_time(
            keywords,
            timeframe='today 12-m'
        )
        
        opportunities = []
        for bos in bos_scores:
            trend = next((t for t in trends if t.keyword == bos.keyword), None)
            
            # Forecast apenas para keywords promissoras
            forecast = None
            if bos.bos >= 0.4 and trend:
                forecast = self.forecaster.forecast(trend, historical_df, forecast_days)
            
            # Determinar ação
            if bos.bos >= 0.8:
                action = "CRIAR CAMPANHA IMEDIATA - Oportunidade excepcional com baixa competição"
            elif bos.bos >= 0.6:
                action = "PLANEJAR ENTRADA - Boa oportunidade, preparar conteúdo e anúncios"
            elif bos.bos >= 0.4:
                action = "MONITORAR - Avaliar ROI antes de investir"
            else:
                action = "EVITAR - Mercado saturado, buscar diferenciação"
            
            # Reasoning
            reasoning_parts = [
                f"Demanda: {bos.demand_score:.0%}",
                f"Intent: {bos.intent_score:.0%}",
                f"Competição: {bos.competition_score:.0%}"
            ]
            
            if forecast:
                reasoning_parts.append(f"Trend: {forecast.trend_direction}")
                reasoning_parts.append(f"Confiança forecast: {forecast.confidence:.0%}")
            
            if trend:
                if trend.rising_queries:
                    reasoning_parts.append(f"Rising: {', '.join(trend.rising_queries[:3])}")
            
            opp = Opportunity(
                keyword=bos.keyword,
                bos=bos.bos,
                forecast=forecast,
                action=action,
                reasoning=" | ".join(reasoning_parts),
                urgency=bos.urgency,
                timestamp=datetime.now()
            )
            opportunities.append(opp)
            
            # Enviar alerta se acima do threshold
            if bos.bos >= alert_threshold:
                self.alert_system.send_opportunity_alert(opp)
        
        # 5. Salvar no BigQuery
        self.bq_connector.save_trends(trends, bos_scores)
        
        # Ordenar por BOS
        opportunities.sort(key=lambda x: x.bos, reverse=True)
        
        return opportunities
    
    def generate_report(self, opportunities: List[Opportunity]) -> str:
        """Gera relatório em texto"""
        lines = [
            "=" * 60,
            "S.S.I. SHADOW — RELATÓRIO DE OPORTUNIDADES",
            f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "=" * 60,
            ""
        ]
        
        for i, opp in enumerate(opportunities, 1):
            urgency_marker = {
                'critical': '🔴',
                'high': '🟠',
                'medium': '🟡',
                'low': '🟢'
            }.get(opp.urgency, '⚪')
            
            lines.extend([
                f"{urgency_marker} #{i} - {opp.keyword}",
                f"   BOS: {opp.bos:.3f} | Urgência: {opp.urgency.upper()}",
                f"   Ação: {opp.action}",
                f"   {opp.reasoning}",
                ""
            ])
        
        lines.append("=" * 60)
        
        return "\n".join(lines)

# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description='S.S.I. Shadow - Predictive Intelligence')
    parser.add_argument(
        '--keywords', '-k',
        nargs='+',
        required=True,
        help='Keywords para analisar'
    )
    parser.add_argument(
        '--forecast-days', '-f',
        type=int,
        default=30,
        help='Dias de forecast (default: 30)'
    )
    parser.add_argument(
        '--threshold', '-t',
        type=float,
        default=0.6,
        help='Threshold para alertas (default: 0.6)'
    )
    parser.add_argument(
        '--output', '-o',
        help='Arquivo de saída JSON'
    )
    parser.add_argument(
        '--geo', '-g',
        default='BR',
        help='Geo para trends (default: BR)'
    )
    
    args = parser.parse_args()
    
    # Inicializar engine
    engine = ShadowEngine(geo=args.geo)
    
    # Analisar
    opportunities = engine.analyze_keywords(
        keywords=args.keywords,
        forecast_days=args.forecast_days,
        alert_threshold=args.threshold
    )
    
    # Relatório
    report = engine.generate_report(opportunities)
    print(report)
    
    # Salvar JSON se solicitado
    if args.output:
        output_data = {
            'timestamp': datetime.now().isoformat(),
            'keywords': args.keywords,
            'opportunities': [
                {
                    'keyword': o.keyword,
                    'bos': o.bos,
                    'urgency': o.urgency,
                    'action': o.action,
                    'reasoning': o.reasoning,
                    'forecast': asdict(o.forecast) if o.forecast else None
                }
                for o in opportunities
            ]
        }
        
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(output_data, f, ensure_ascii=False, indent=2)
        
        print(f"\nRelatório salvo em: {args.output}")

if __name__ == '__main__':
    main()
