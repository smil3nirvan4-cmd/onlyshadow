"""
S.S.I. SHADOW — CONVERSION MODELING
ML-BASED CONVERSION ESTIMATION FOR iOS 14.5+

Com iOS 14.5+ e ATT, ~70% dos usuários optam-out do tracking.
Conversion Modeling usa ML para estimar conversões não observadas.

Métodos:
1. Probabilistic Matching - Match sem IDFA
2. SKAdNetwork Mapping - Decode conversion values
3. Aggregated Event Modeling - Estimar de dados agregados
4. Regression Modeling - Predizer conversões de sinais

Similar ao Meta Aggregated Event Measurement (AEM).
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from scipy import stats
import hashlib

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_conversion_modeling')

# =============================================================================
# TYPES
# =============================================================================

class ConversionType(Enum):
    OBSERVED = "observed"  # Tracking permitido
    MODELED = "modeled"  # Estimado por ML
    SKAN = "skan"  # Via SKAdNetwork
    AGGREGATED = "aggregated"  # De dados agregados


class Platform(Enum):
    IOS = "ios"
    ANDROID = "android"
    WEB = "web"
    UNKNOWN = "unknown"


@dataclass
class ConversionEvent:
    """Evento de conversão (observado ou modelado)"""
    event_id: str
    event_name: str
    event_time: datetime
    
    # Attribution
    campaign_id: Optional[str] = None
    ad_set_id: Optional[str] = None
    ad_id: Optional[str] = None
    
    # Value
    value: float = 0
    currency: str = "BRL"
    
    # Source
    conversion_type: ConversionType = ConversionType.OBSERVED
    platform: Platform = Platform.UNKNOWN
    
    # Confidence
    confidence: float = 1.0
    
    # SKAN specific
    skan_conversion_value: Optional[int] = None
    skan_redownload: bool = False


@dataclass
class SKANPostback:
    """Postback do SKAdNetwork"""
    version: str
    transaction_id: str
    app_id: str
    
    # Attribution
    campaign_id: int
    conversion_value: int  # 0-63
    
    # Timing
    postback_time: datetime
    
    # Crowd anonymity
    did_win: bool = True
    source_app_id: Optional[str] = None


@dataclass
class ModeledConversionResult:
    """Resultado do conversion modeling"""
    campaign_id: str
    
    # Observed
    observed_conversions: int
    observed_revenue: float
    
    # Modeled
    modeled_conversions: float
    modeled_revenue: float
    
    # Total (observed + modeled)
    total_conversions: float
    total_revenue: float
    
    # Confidence
    confidence_interval: Tuple[float, float]
    model_confidence: float
    
    # Breakdown
    platform_breakdown: Dict[Platform, float]
    
    # Metadata
    modeling_date: datetime
    model_version: str


# =============================================================================
# SKAN DECODER
# =============================================================================

class SKANDecoder:
    """
    Decodifica conversion values do SKAdNetwork.
    
    SKAdNetwork retorna apenas um número 0-63 (6 bits).
    Precisamos mapear para eventos/valores reais.
    """
    
    def __init__(self):
        # Mapeamento padrão (customizável por cliente)
        self.value_mapping = self._create_default_mapping()
    
    def _create_default_mapping(self) -> Dict[int, Dict[str, Any]]:
        """
        Cria mapeamento padrão de conversion values.
        
        Estratégia: bits para eventos e ranges de valor.
        - Bits 0-2: Tipo de evento
        - Bits 3-5: Range de valor
        """
        mapping = {}
        
        event_types = [
            'install_only',
            'registration',
            'add_to_cart',
            'initiate_checkout',
            'purchase_low',  # < R$50
            'purchase_medium',  # R$50-200
            'purchase_high',  # R$200-500
            'purchase_whale'  # > R$500
        ]
        
        value_ranges = [
            (0, 0),
            (1, 10),
            (10, 25),
            (25, 50),
            (50, 100),
            (100, 200),
            (200, 500),
            (500, 2000)
        ]
        
        for cv in range(64):
            event_idx = cv % 8
            value_idx = cv // 8
            
            event_type = event_types[event_idx]
            value_min, value_max = value_ranges[value_idx]
            
            mapping[cv] = {
                'event_type': event_type,
                'is_purchase': 'purchase' in event_type,
                'value_min': value_min,
                'value_max': value_max,
                'estimated_value': (value_min + value_max) / 2
            }
        
        return mapping
    
    def decode(self, conversion_value: int) -> Dict[str, Any]:
        """Decodifica conversion value"""
        if conversion_value < 0 or conversion_value > 63:
            return {'error': 'Invalid conversion value'}
        
        return self.value_mapping.get(conversion_value, {'error': 'Unknown mapping'})
    
    def estimate_revenue(self, postbacks: List[SKANPostback]) -> Dict[str, float]:
        """
        Estima receita a partir de postbacks SKAN.
        """
        revenue_by_campaign = {}
        
        for postback in postbacks:
            decoded = self.decode(postback.conversion_value)
            
            if decoded.get('is_purchase'):
                campaign_key = str(postback.campaign_id)
                estimated_value = decoded.get('estimated_value', 0)
                
                if campaign_key not in revenue_by_campaign:
                    revenue_by_campaign[campaign_key] = 0
                
                revenue_by_campaign[campaign_key] += estimated_value
        
        return revenue_by_campaign
    
    def update_mapping(self, custom_mapping: Dict[int, Dict[str, Any]]):
        """Atualiza mapeamento com configuração custom"""
        self.value_mapping.update(custom_mapping)


# =============================================================================
# PROBABILISTIC MATCHER
# =============================================================================

class ProbabilisticMatcher:
    """
    Match probabilístico sem IDFA.
    Usa sinais contextuais para estimar probabilidade de match.
    """
    
    def __init__(self):
        self.feature_weights = {
            'ip_match': 0.4,
            'timestamp_proximity': 0.2,
            'device_model': 0.15,
            'os_version': 0.1,
            'carrier': 0.1,
            'geo': 0.05
        }
    
    def _calculate_time_score(
        self,
        click_time: datetime,
        install_time: datetime,
        max_window_hours: int = 24
    ) -> float:
        """Calcula score baseado em proximidade temporal"""
        delta = abs((install_time - click_time).total_seconds() / 3600)
        
        if delta > max_window_hours:
            return 0
        
        # Decay exponencial
        return np.exp(-delta / 6)  # 6 horas de half-life
    
    def calculate_match_probability(
        self,
        click_signals: Dict[str, Any],
        install_signals: Dict[str, Any]
    ) -> Tuple[float, Dict[str, float]]:
        """
        Calcula probabilidade de match entre click e install.
        """
        scores = {}
        
        # IP match
        if click_signals.get('ip') == install_signals.get('ip'):
            scores['ip_match'] = 1.0
        else:
            # Partial match (same /24 subnet)
            click_ip = click_signals.get('ip', '').rsplit('.', 1)[0]
            install_ip = install_signals.get('ip', '').rsplit('.', 1)[0]
            scores['ip_match'] = 0.5 if click_ip == install_ip else 0
        
        # Timestamp proximity
        click_time = click_signals.get('timestamp')
        install_time = install_signals.get('timestamp')
        
        if click_time and install_time:
            scores['timestamp_proximity'] = self._calculate_time_score(
                click_time, install_time
            )
        else:
            scores['timestamp_proximity'] = 0
        
        # Device model
        if click_signals.get('device_model') == install_signals.get('device_model'):
            scores['device_model'] = 1.0
        else:
            scores['device_model'] = 0
        
        # OS version
        if click_signals.get('os_version') == install_signals.get('os_version'):
            scores['os_version'] = 1.0
        else:
            scores['os_version'] = 0
        
        # Carrier
        if click_signals.get('carrier') == install_signals.get('carrier'):
            scores['carrier'] = 1.0
        else:
            scores['carrier'] = 0
        
        # Geo
        if click_signals.get('country') == install_signals.get('country'):
            scores['geo'] = 1.0
        else:
            scores['geo'] = 0
        
        # Weighted sum
        total_score = sum(
            scores.get(feature, 0) * weight
            for feature, weight in self.feature_weights.items()
        )
        
        # Convert to probability (sigmoid)
        probability = 1 / (1 + np.exp(-5 * (total_score - 0.5)))
        
        return probability, scores


# =============================================================================
# CONVERSION MODELER
# =============================================================================

class ConversionModeler:
    """
    Modela conversões não observadas usando ML.
    """
    
    def __init__(self):
        self.skan_decoder = SKANDecoder()
        self.probabilistic_matcher = ProbabilisticMatcher()
        
        # Model parameters (learned from data)
        self.ios_opt_in_rate = 0.30  # ~30% opt-in no Brasil
        self.modeling_multiplier = 1.0 / self.ios_opt_in_rate
    
    def estimate_modeled_conversions(
        self,
        observed_conversions: int,
        platform: Platform,
        campaign_signals: Dict[str, Any] = None
    ) -> Tuple[float, float]:
        """
        Estima conversões não observadas.
        
        Returns: (modeled_conversions, confidence)
        """
        if platform == Platform.IOS:
            # iOS: muitos não observados
            modeled = observed_conversions * (self.modeling_multiplier - 1)
            
            # Ajustar baseado em sinais da campanha
            if campaign_signals:
                # Campanhas de remarketing têm maior opt-in
                if campaign_signals.get('is_remarketing'):
                    modeled *= 0.7  # Menos modelado
                
                # App campaigns vs web
                if campaign_signals.get('destination') == 'app':
                    modeled *= 1.2  # Mais modelado
            
            confidence = 0.7
            
        elif platform == Platform.ANDROID:
            # Android: menos restrições, menos modelado
            modeled = observed_conversions * 0.1
            confidence = 0.85
            
        else:
            # Web: mínimo modelado
            modeled = observed_conversions * 0.05
            confidence = 0.9
        
        return modeled, confidence
    
    def model_campaign_conversions(
        self,
        campaign_id: str,
        observed_data: Dict[str, Any],
        skan_postbacks: List[SKANPostback] = None
    ) -> ModeledConversionResult:
        """
        Modela conversões completas de uma campanha.
        """
        # Observed conversions by platform
        observed_ios = observed_data.get('ios_conversions', 0)
        observed_android = observed_data.get('android_conversions', 0)
        observed_web = observed_data.get('web_conversions', 0)
        
        observed_total = observed_ios + observed_android + observed_web
        observed_revenue = observed_data.get('total_revenue', 0)
        
        # Model iOS
        modeled_ios, conf_ios = self.estimate_modeled_conversions(
            observed_ios, Platform.IOS
        )
        
        # Model Android
        modeled_android, conf_android = self.estimate_modeled_conversions(
            observed_android, Platform.ANDROID
        )
        
        # Model Web
        modeled_web, conf_web = self.estimate_modeled_conversions(
            observed_web, Platform.WEB
        )
        
        modeled_total = modeled_ios + modeled_android + modeled_web
        
        # Add SKAN conversions
        skan_conversions = 0
        skan_revenue = 0
        
        if skan_postbacks:
            skan_revenue_map = self.skan_decoder.estimate_revenue(skan_postbacks)
            skan_revenue = skan_revenue_map.get(campaign_id, 0)
            skan_conversions = len([
                p for p in skan_postbacks 
                if str(p.campaign_id) == campaign_id
            ])
        
        # Total
        total_conversions = observed_total + modeled_total + skan_conversions
        
        # Revenue estimation
        if observed_total > 0:
            avg_value = observed_revenue / observed_total
            modeled_revenue = modeled_total * avg_value
        else:
            modeled_revenue = 0
        
        total_revenue = observed_revenue + modeled_revenue + skan_revenue
        
        # Confidence interval (simplified)
        std_error = np.sqrt(modeled_total)  # Poisson approximation
        ci_lower = total_conversions - 1.96 * std_error
        ci_upper = total_conversions + 1.96 * std_error
        
        # Overall confidence (weighted by volume)
        total_weight = observed_ios + observed_android + observed_web + 1
        model_confidence = (
            observed_ios * conf_ios +
            observed_android * conf_android +
            observed_web * conf_web +
            1  # Prior
        ) / total_weight
        
        return ModeledConversionResult(
            campaign_id=campaign_id,
            observed_conversions=observed_total,
            observed_revenue=observed_revenue,
            modeled_conversions=modeled_total,
            modeled_revenue=modeled_revenue,
            total_conversions=total_conversions,
            total_revenue=total_revenue,
            confidence_interval=(ci_lower, ci_upper),
            model_confidence=model_confidence,
            platform_breakdown={
                Platform.IOS: observed_ios + modeled_ios,
                Platform.ANDROID: observed_android + modeled_android,
                Platform.WEB: observed_web + modeled_web
            },
            modeling_date=datetime.now(),
            model_version='1.0.0'
        )
    
    def calibrate_model(
        self,
        historical_data: List[Dict[str, Any]]
    ):
        """
        Calibra modelo com dados históricos.
        Ajusta multipliers baseado em observações passadas.
        """
        if not historical_data:
            return
        
        # Calcular opt-in rate real
        total_ios = sum(d.get('ios_conversions', 0) for d in historical_data)
        total_skan = sum(d.get('skan_conversions', 0) for d in historical_data)
        
        if total_skan > 0:
            # SKAN captura todos, observed captura só opt-in
            estimated_opt_in = total_ios / total_skan
            
            if 0.1 < estimated_opt_in < 0.9:
                self.ios_opt_in_rate = estimated_opt_in
                self.modeling_multiplier = 1.0 / self.ios_opt_in_rate
                
                logger.info(f"Calibrated opt-in rate: {self.ios_opt_in_rate:.2%}")


# =============================================================================
# AGGREGATED EVENT MODELER
# =============================================================================

class AggregatedEventModeler:
    """
    Modela eventos a partir de dados agregados (para AEM/CAPI).
    Distribui conversões agregadas para campanhas/ad sets.
    """
    
    def __init__(self):
        pass
    
    def distribute_conversions(
        self,
        total_conversions: int,
        campaign_weights: Dict[str, float]
    ) -> Dict[str, float]:
        """
        Distribui conversões agregadas para campanhas baseado em pesos.
        
        campaign_weights: Dict de campaign_id -> peso (baseado em clicks, spend, etc.)
        """
        total_weight = sum(campaign_weights.values())
        
        if total_weight == 0:
            return {}
        
        distribution = {}
        
        for campaign_id, weight in campaign_weights.items():
            share = weight / total_weight
            distribution[campaign_id] = total_conversions * share
        
        return distribution
    
    def estimate_from_aggregates(
        self,
        aggregated_events: Dict[str, int],  # event_name -> count
        campaign_clicks: Dict[str, int],
        campaign_spend: Dict[str, float]
    ) -> Dict[str, Dict[str, float]]:
        """
        Estima conversões por campanha a partir de dados agregados.
        """
        results = {}
        
        # Calculate weights (combinação de clicks e spend)
        weights = {}
        
        for campaign_id in set(campaign_clicks.keys()) | set(campaign_spend.keys()):
            clicks = campaign_clicks.get(campaign_id, 0)
            spend = campaign_spend.get(campaign_id, 0)
            
            # Peso = sqrt(clicks) * spend^0.5
            weights[campaign_id] = np.sqrt(clicks) * np.sqrt(spend + 1)
        
        # Distribute each event type
        for event_name, count in aggregated_events.items():
            distribution = self.distribute_conversions(count, weights)
            
            for campaign_id, estimated_count in distribution.items():
                if campaign_id not in results:
                    results[campaign_id] = {}
                
                results[campaign_id][event_name] = estimated_count
        
        return results


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'ConversionType',
    'Platform',
    'ConversionEvent',
    'SKANPostback',
    'ModeledConversionResult',
    'SKANDecoder',
    'ProbabilisticMatcher',
    'ConversionModeler',
    'AggregatedEventModeler'
]
