"""
S.S.I. SHADOW — Intelligence Module v2
API-DRIVEN EDITION

Integração com APIs oficiais:
- Semrush API ($120-500/mês)
- SimilarWeb API
- Google Trends (PyTrends)
- AdSpy API (opcional)

Benefícios vs Scraping:
- Zero risco de banimento
- Dados estruturados e confiáveis
- Rate limits conhecidos
- Suporte oficial
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Tuple
from dataclasses import dataclass, asdict
from abc import ABC, abstractmethod
import hashlib

import requests

# Opcional: PyTrends para Google Trends gratuito
try:
    from pytrends.request import TrendReq
    PYTRENDS_AVAILABLE = True
except ImportError:
    PYTRENDS_AVAILABLE = False

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_shadow_v2')

# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class KeywordData:
    """Dados consolidados de uma keyword"""
    keyword: str
    
    # Volume e tendência
    search_volume: int
    trend_percent: float  # -100 a +100
    
    # Competição
    cpc: float
    competition: float  # 0 a 1
    
    # SERP
    organic_results: int
    paid_results: int
    featured_snippets: bool
    
    # Scores calculados
    difficulty: float  # 0 a 100
    opportunity_score: float  # BOS
    
    # Metadata
    source: str
    collected_at: datetime

@dataclass
class CompetitorData:
    """Dados de competidor"""
    domain: str
    
    # Tráfego
    monthly_visits: int
    traffic_sources: Dict[str, float]  # organic, paid, social, etc
    
    # Keywords
    organic_keywords: int
    paid_keywords: int
    top_keywords: List[str]
    
    # Metadata
    source: str
    collected_at: datetime

@dataclass
class MarketOpportunity:
    """Oportunidade de mercado identificada"""
    keyword: str
    opportunity_score: float
    
    # Métricas
    volume: int
    cpc: float
    competition: float
    trend: float
    
    # Ação recomendada
    action: str
    urgency: str
    reasoning: str
    
    # Forecast
    forecast_7d: Optional[float]
    forecast_30d: Optional[float]
    
    timestamp: datetime

# =============================================================================
# API CLIENTS
# =============================================================================

class BaseAPIClient(ABC):
    """Base class para clientes de API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.session = requests.Session()
    
    @abstractmethod
    def get_keyword_data(self, keyword: str) -> Optional[KeywordData]:
        pass
    
    @abstractmethod
    def get_competitor_data(self, domain: str) -> Optional[CompetitorData]:
        pass


class SemrushClient(BaseAPIClient):
    """
    Cliente para Semrush API
    Docs: https://developer.semrush.com/api/
    
    Planos:
    - Pro: $129/mês - 3,000 reports/dia
    - Guru: $249/mês - 5,000 reports/dia
    - Business: $499/mês - 10,000 reports/dia
    """
    
    BASE_URL = "https://api.semrush.com/"
    
    def __init__(self, api_key: str, database: str = "br"):
        super().__init__(api_key)
        self.database = database
    
    def _request(self, endpoint: str, params: Dict) -> Optional[str]:
        """Faz request para API Semrush"""
        params['key'] = self.api_key
        
        try:
            response = self.session.get(
                f"{self.BASE_URL}{endpoint}",
                params=params,
                timeout=30
            )
            
            if response.status_code == 200:
                return response.text
            else:
                logger.error(f"Semrush API error: {response.status_code} - {response.text}")
                return None
                
        except Exception as e:
            logger.error(f"Semrush request failed: {e}")
            return None
    
    def get_keyword_data(self, keyword: str) -> Optional[KeywordData]:
        """
        Obtém dados de keyword via Keyword Overview API
        Custo: 10 unidades por keyword
        """
        params = {
            'type': 'phrase_this',
            'phrase': keyword,
            'database': self.database,
            'export_columns': 'Ph,Nq,Cp,Co,Nr'
            # Ph = Phrase, Nq = Volume, Cp = CPC, Co = Competition, Nr = Results
        }
        
        result = self._request('', params)
        if not result:
            return None
        
        try:
            # Parse CSV response
            lines = result.strip().split('\n')
            if len(lines) < 2:
                return None
            
            header = lines[0].split(';')
            values = lines[1].split(';')
            data = dict(zip(header, values))
            
            return KeywordData(
                keyword=keyword,
                search_volume=int(data.get('Search Volume', 0) or 0),
                trend_percent=0,  # Semrush não retorna trend nesse endpoint
                cpc=float(data.get('CPC', 0) or 0),
                competition=float(data.get('Competition', 0) or 0),
                organic_results=int(data.get('Number of Results', 0) or 0),
                paid_results=0,
                featured_snippets=False,
                difficulty=float(data.get('Competition', 0) or 0) * 100,
                opportunity_score=0,  # Calculado depois
                source='semrush',
                collected_at=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to parse Semrush response: {e}")
            return None
    
    def get_keyword_trends(self, keyword: str, months: int = 12) -> List[Dict]:
        """
        Obtém histórico de volume (trend)
        """
        params = {
            'type': 'phrase_history',
            'phrase': keyword,
            'database': self.database,
            'display_limit': months
        }
        
        result = self._request('', params)
        if not result:
            return []
        
        try:
            trends = []
            lines = result.strip().split('\n')
            
            for line in lines[1:]:  # Skip header
                parts = line.split(';')
                if len(parts) >= 2:
                    trends.append({
                        'date': parts[0],
                        'volume': int(parts[1] or 0)
                    })
            
            return trends
            
        except Exception as e:
            logger.error(f"Failed to parse Semrush trends: {e}")
            return []
    
    def get_competitor_data(self, domain: str) -> Optional[CompetitorData]:
        """
        Obtém dados de domínio competidor
        """
        params = {
            'type': 'domain_ranks',
            'domain': domain,
            'database': self.database,
            'export_columns': 'Dn,Rk,Or,Ot,Oc,Ad,At,Ac'
        }
        
        result = self._request('', params)
        if not result:
            return None
        
        try:
            lines = result.strip().split('\n')
            if len(lines) < 2:
                return None
            
            header = lines[0].split(';')
            values = lines[1].split(';')
            data = dict(zip(header, values))
            
            return CompetitorData(
                domain=domain,
                monthly_visits=0,  # Não disponível nesse endpoint
                traffic_sources={
                    'organic': float(data.get('Organic Traffic', 0) or 0),
                    'paid': float(data.get('Adwords Traffic', 0) or 0)
                },
                organic_keywords=int(data.get('Organic Keywords', 0) or 0),
                paid_keywords=int(data.get('Adwords Keywords', 0) or 0),
                top_keywords=[],
                source='semrush',
                collected_at=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to parse Semrush competitor data: {e}")
            return None
    
    def get_related_keywords(self, keyword: str, limit: int = 20) -> List[KeywordData]:
        """
        Obtém keywords relacionadas
        """
        params = {
            'type': 'phrase_related',
            'phrase': keyword,
            'database': self.database,
            'display_limit': limit,
            'export_columns': 'Ph,Nq,Cp,Co,Nr'
        }
        
        result = self._request('', params)
        if not result:
            return []
        
        try:
            keywords = []
            lines = result.strip().split('\n')
            
            for line in lines[1:]:  # Skip header
                parts = line.split(';')
                if len(parts) >= 5:
                    keywords.append(KeywordData(
                        keyword=parts[0],
                        search_volume=int(parts[1] or 0),
                        trend_percent=0,
                        cpc=float(parts[2] or 0),
                        competition=float(parts[3] or 0),
                        organic_results=int(parts[4] or 0),
                        paid_results=0,
                        featured_snippets=False,
                        difficulty=float(parts[3] or 0) * 100,
                        opportunity_score=0,
                        source='semrush',
                        collected_at=datetime.now()
                    ))
            
            return keywords
            
        except Exception as e:
            logger.error(f"Failed to parse Semrush related keywords: {e}")
            return []


class SimilarWebClient(BaseAPIClient):
    """
    Cliente para SimilarWeb API
    Docs: https://developers.similarweb.com/
    
    Planos variam - contatar para pricing
    """
    
    BASE_URL = "https://api.similarweb.com/v1/"
    
    def __init__(self, api_key: str):
        super().__init__(api_key)
        self.session.headers['api-key'] = api_key
    
    def _request(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Faz request para API SimilarWeb"""
        try:
            response = self.session.get(
                f"{self.BASE_URL}{endpoint}",
                params=params or {},
                timeout=30
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"SimilarWeb API error: {response.status_code}")
                return None
                
        except Exception as e:
            logger.error(f"SimilarWeb request failed: {e}")
            return None
    
    def get_keyword_data(self, keyword: str) -> Optional[KeywordData]:
        """SimilarWeb foca em tráfego de sites, não keywords individuais"""
        return None
    
    def get_competitor_data(self, domain: str) -> Optional[CompetitorData]:
        """
        Obtém dados de tráfego do domínio
        """
        # Total traffic
        traffic = self._request(f"website/{domain}/total-traffic-and-engagement/visits")
        
        # Traffic sources
        sources = self._request(f"website/{domain}/traffic-sources/overview")
        
        if not traffic:
            return None
        
        try:
            visits = traffic.get('visits', 0)
            
            traffic_sources = {}
            if sources:
                for source in sources.get('overview', []):
                    traffic_sources[source.get('source_type', 'unknown')] = source.get('share', 0)
            
            return CompetitorData(
                domain=domain,
                monthly_visits=int(visits),
                traffic_sources=traffic_sources,
                organic_keywords=0,
                paid_keywords=0,
                top_keywords=[],
                source='similarweb',
                collected_at=datetime.now()
            )
            
        except Exception as e:
            logger.error(f"Failed to parse SimilarWeb data: {e}")
            return None


class GoogleTrendsClient:
    """
    Cliente para Google Trends via PyTrends (gratuito)
    Rate limits: ~10-20 requests por minuto
    """
    
    def __init__(self, geo: str = 'BR', hl: str = 'pt-BR'):
        self.geo = geo
        self.hl = hl
        self.pytrends = None
        
        if PYTRENDS_AVAILABLE:
            self.pytrends = TrendReq(hl=hl, tz=-180)
    
    def get_interest_over_time(
        self, 
        keywords: List[str], 
        timeframe: str = 'today 3-m'
    ) -> Optional[Dict[str, List[Dict]]]:
        """
        Obtém interesse ao longo do tempo
        """
        if not self.pytrends:
            return None
        
        try:
            self.pytrends.build_payload(
                kw_list=keywords[:5],
                cat=0,
                timeframe=timeframe,
                geo=self.geo
            )
            
            df = self.pytrends.interest_over_time()
            
            if df.empty:
                return None
            
            result = {}
            for kw in keywords[:5]:
                if kw in df.columns:
                    result[kw] = [
                        {'date': str(idx.date()), 'interest': int(val)}
                        for idx, val in df[kw].items()
                    ]
            
            return result
            
        except Exception as e:
            logger.error(f"PyTrends error: {e}")
            return None
    
    def get_related_queries(self, keyword: str) -> Dict[str, List[str]]:
        """
        Obtém queries relacionadas
        """
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
            logger.error(f"PyTrends related queries error: {e}")
            return {'rising': [], 'top': []}

# =============================================================================
# OPPORTUNITY CALCULATOR
# =============================================================================

class OpportunityCalculator:
    """
    Calcula Blue Ocean Score e identifica oportunidades
    
    BOS = (Demand × Intent) / (Supply × Competition)
    """
    
    def calculate_bos(self, keyword_data: KeywordData) -> float:
        """
        Calcula Blue Ocean Score
        """
        # Normalizar volume (0-1) - assumindo max 100k
        demand = min(1.0, keyword_data.search_volume / 100000)
        
        # Intent estimado baseado em CPC (maior CPC = maior intent)
        intent = min(1.0, keyword_data.cpc / 10)  # Assumindo max CPC R$10
        
        # Supply (inverso dos resultados orgânicos)
        supply = 1 - min(1.0, keyword_data.organic_results / 10000000)  # Menos resultados = melhor
        
        # Competition (já 0-1 no Semrush)
        competition = keyword_data.competition
        
        # Evitar divisão por zero
        denominator = max(0.1, (1 - supply) * max(0.1, competition))
        bos = (demand * intent) / denominator
        
        return min(1.0, bos)
    
    def calculate_trend_score(
        self, 
        trend_data: List[Dict],
        window_recent: int = 7,
        window_previous: int = 21
    ) -> float:
        """
        Calcula score de tendência (-100 a +100)
        """
        if not trend_data or len(trend_data) < window_recent + window_previous:
            return 0.0
        
        # Últimos N dias
        recent = sum(t.get('interest', 0) or t.get('volume', 0) 
                    for t in trend_data[-window_recent:]) / window_recent
        
        # Período anterior
        previous = sum(t.get('interest', 0) or t.get('volume', 0) 
                      for t in trend_data[-(window_recent + window_previous):-window_recent]) / window_previous
        
        if previous == 0:
            return 0.0
        
        return ((recent - previous) / previous) * 100
    
    def identify_opportunities(
        self,
        keywords_data: List[KeywordData],
        trends_data: Dict[str, List[Dict]],
        min_bos: float = 0.4,
        min_volume: int = 100
    ) -> List[MarketOpportunity]:
        """
        Identifica oportunidades de mercado
        """
        opportunities = []
        
        for kw_data in keywords_data:
            # Filtro mínimo
            if kw_data.search_volume < min_volume:
                continue
            
            # Calcular BOS
            bos = self.calculate_bos(kw_data)
            
            if bos < min_bos:
                continue
            
            # Calcular trend
            trend_score = 0
            kw_trends = trends_data.get(kw_data.keyword, [])
            if kw_trends:
                trend_score = self.calculate_trend_score(kw_trends)
            
            # Determinar ação e urgência
            if bos >= 0.8:
                action = "CRIAR CAMPANHA IMEDIATA"
                urgency = "critical"
            elif bos >= 0.6:
                action = "PLANEJAR ENTRADA"
                urgency = "high"
            elif bos >= 0.4:
                action = "MONITORAR"
                urgency = "medium"
            else:
                action = "BAIXA PRIORIDADE"
                urgency = "low"
            
            # Reasoning
            reasoning_parts = [
                f"Volume: {kw_data.search_volume}",
                f"CPC: R${kw_data.cpc:.2f}",
                f"Competição: {kw_data.competition:.0%}",
                f"Trend: {trend_score:+.1f}%"
            ]
            
            opportunities.append(MarketOpportunity(
                keyword=kw_data.keyword,
                opportunity_score=round(bos, 3),
                volume=kw_data.search_volume,
                cpc=kw_data.cpc,
                competition=kw_data.competition,
                trend=trend_score,
                action=action,
                urgency=urgency,
                reasoning=" | ".join(reasoning_parts),
                forecast_7d=None,
                forecast_30d=None,
                timestamp=datetime.now()
            ))
        
        # Ordenar por BOS
        opportunities.sort(key=lambda x: x.opportunity_score, reverse=True)
        
        return opportunities

# =============================================================================
# SHADOW ENGINE v2
# =============================================================================

class ShadowEngineV2:
    """
    Engine principal do Oráculo v2
    Usa APIs oficiais em vez de scraping
    """
    
    def __init__(
        self,
        semrush_key: Optional[str] = None,
        similarweb_key: Optional[str] = None,
        geo: str = 'BR',
        telegram_token: Optional[str] = None,
        telegram_chat: Optional[str] = None
    ):
        # API Clients
        self.semrush = SemrushClient(semrush_key, geo.lower()) if semrush_key else None
        self.similarweb = SimilarWebClient(similarweb_key) if similarweb_key else None
        self.gtrends = GoogleTrendsClient(geo=geo)
        
        # Calculator
        self.calculator = OpportunityCalculator()
        
        # Telegram
        self.telegram_token = telegram_token or os.getenv('TELEGRAM_BOT_TOKEN')
        self.telegram_chat = telegram_chat or os.getenv('TELEGRAM_CHAT_ID')
    
    def analyze_keywords(
        self,
        keywords: List[str],
        include_related: bool = True,
        alert_threshold: float = 0.6
    ) -> Dict[str, Any]:
        """
        Análise completa de keywords usando APIs oficiais
        """
        logger.info(f"Analyzing {len(keywords)} keywords...")
        
        results = {
            'keywords_analyzed': len(keywords),
            'opportunities': [],
            'keyword_data': [],
            'sources_used': [],
            'timestamp': datetime.now().isoformat()
        }
        
        all_keywords = list(keywords)
        keywords_data = []
        
        # 1. Obter dados do Semrush (se disponível)
        if self.semrush:
            results['sources_used'].append('semrush')
            
            for kw in keywords:
                data = self.semrush.get_keyword_data(kw)
                if data:
                    keywords_data.append(data)
                
                # Obter relacionadas
                if include_related:
                    related = self.semrush.get_related_keywords(kw, limit=10)
                    keywords_data.extend(related)
                    all_keywords.extend([r.keyword for r in related])
        
        # 2. Obter trends do Google (gratuito)
        trends_data = {}
        if self.gtrends:
            results['sources_used'].append('google_trends')
            
            # Processar em lotes de 5 (limite PyTrends)
            for i in range(0, len(all_keywords[:25]), 5):
                batch = all_keywords[i:i+5]
                batch_trends = self.gtrends.get_interest_over_time(batch)
                if batch_trends:
                    trends_data.update(batch_trends)
        
        # 3. Calcular oportunidades
        opportunities = self.calculator.identify_opportunities(
            keywords_data,
            trends_data,
            min_bos=0.3
        )
        
        results['opportunities'] = [asdict(o) for o in opportunities]
        results['keyword_data'] = [asdict(k) for k in keywords_data]
        
        # 4. Enviar alertas
        high_priority = [o for o in opportunities if o.opportunity_score >= alert_threshold]
        for opp in high_priority[:5]:  # Max 5 alertas
            self._send_alert(opp)
        
        return results
    
    def analyze_competitors(self, domains: List[str]) -> Dict[str, Any]:
        """
        Análise de competidores
        """
        logger.info(f"Analyzing {len(domains)} competitors...")
        
        results = {
            'competitors_analyzed': len(domains),
            'data': [],
            'sources_used': [],
            'timestamp': datetime.now().isoformat()
        }
        
        for domain in domains:
            # SimilarWeb para tráfego
            if self.similarweb:
                results['sources_used'].append('similarweb')
                data = self.similarweb.get_competitor_data(domain)
                if data:
                    results['data'].append(asdict(data))
            
            # Semrush para keywords
            if self.semrush:
                results['sources_used'].append('semrush')
                data = self.semrush.get_competitor_data(domain)
                if data:
                    # Merge com dados existentes ou adicionar
                    existing = next(
                        (d for d in results['data'] if d.get('domain') == domain),
                        None
                    )
                    if existing:
                        existing.update({
                            'organic_keywords': data.organic_keywords,
                            'paid_keywords': data.paid_keywords
                        })
                    else:
                        results['data'].append(asdict(data))
        
        return results
    
    def _send_alert(self, opportunity: MarketOpportunity) -> bool:
        """
        Envia alerta via Telegram
        """
        if not self.telegram_token or not self.telegram_chat:
            return False
        
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
<b>BOS Score:</b> {opportunity.opportunity_score:.2f}
<b>Urgência:</b> {opportunity.urgency.upper()}

<b>Métricas:</b>
• Volume: {opportunity.volume:,}
• CPC: R${opportunity.cpc:.2f}
• Trend: {opportunity.trend:+.1f}%

<b>Ação:</b> {opportunity.action}

<i>{opportunity.reasoning}</i>
"""
        
        try:
            response = requests.post(
                f"https://api.telegram.org/bot{self.telegram_token}/sendMessage",
                json={
                    'chat_id': self.telegram_chat,
                    'text': message.strip(),
                    'parse_mode': 'HTML'
                },
                timeout=10
            )
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Telegram alert failed: {e}")
            return False
    
    def generate_report(self, analysis_results: Dict) -> str:
        """
        Gera relatório em texto
        """
        lines = [
            "=" * 60,
            "S.S.I. SHADOW v2 — RELATÓRIO DE OPORTUNIDADES",
            f"Gerado em: {analysis_results.get('timestamp', 'N/A')}",
            f"Fontes: {', '.join(analysis_results.get('sources_used', []))}",
            "=" * 60,
            ""
        ]
        
        opportunities = analysis_results.get('opportunities', [])
        
        if not opportunities:
            lines.append("Nenhuma oportunidade identificada com os critérios atuais.")
        else:
            for i, opp in enumerate(opportunities[:20], 1):
                urgency_marker = {
                    'critical': '🔴',
                    'high': '🟠',
                    'medium': '🟡',
                    'low': '🟢'
                }.get(opp.get('urgency', ''), '⚪')
                
                lines.extend([
                    f"{urgency_marker} #{i} - {opp.get('keyword', 'N/A')}",
                    f"   BOS: {opp.get('opportunity_score', 0):.3f} | Urgência: {opp.get('urgency', 'N/A').upper()}",
                    f"   Volume: {opp.get('volume', 0):,} | CPC: R${opp.get('cpc', 0):.2f} | Trend: {opp.get('trend', 0):+.1f}%",
                    f"   Ação: {opp.get('action', 'N/A')}",
                    ""
                ])
        
        lines.append("=" * 60)
        
        return "\n".join(lines)

# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='S.S.I. Shadow v2 - API-Driven Intelligence')
    parser.add_argument('--keywords', '-k', nargs='+', help='Keywords para analisar')
    parser.add_argument('--competitors', '-c', nargs='+', help='Domínios competidores')
    parser.add_argument('--semrush-key', help='Semrush API Key')
    parser.add_argument('--output', '-o', help='Arquivo de saída JSON')
    parser.add_argument('--geo', default='BR', help='Geo (default: BR)')
    
    args = parser.parse_args()
    
    # Inicializar engine
    engine = ShadowEngineV2(
        semrush_key=args.semrush_key or os.getenv('SEMRUSH_API_KEY'),
        geo=args.geo
    )
    
    results = {}
    
    # Analisar keywords
    if args.keywords:
        results['keywords'] = engine.analyze_keywords(args.keywords)
        print(engine.generate_report(results['keywords']))
    
    # Analisar competidores
    if args.competitors:
        results['competitors'] = engine.analyze_competitors(args.competitors)
        print(json.dumps(results['competitors'], indent=2, default=str))
    
    # Salvar JSON
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2, default=str)
        print(f"\nResultados salvos em: {args.output}")

if __name__ == '__main__':
    main()
