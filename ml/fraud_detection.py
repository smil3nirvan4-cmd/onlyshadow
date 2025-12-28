"""
S.S.I. SHADOW — FRAUD DETECTION SYSTEM
REAL-TIME ML-BASED FRAUD SCORING

Multi-layer fraud detection:
1. Rule-based (fast, deterministic)
2. ML-based (accurate, probabilistic)
3. Behavioral analysis (pattern detection)
4. Network analysis (device graph)

Detects:
- Click fraud
- Conversion fraud
- Account takeover
- Bot traffic
- Attribution fraud
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import hashlib
import math

import numpy as np
from scipy import stats

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_fraud')

# =============================================================================
# TYPES
# =============================================================================

class FraudType(Enum):
    CLICK_FRAUD = "click_fraud"
    CONVERSION_FRAUD = "conversion_fraud"
    BOT_TRAFFIC = "bot_traffic"
    ATTRIBUTION_FRAUD = "attribution_fraud"
    ACCOUNT_TAKEOVER = "account_takeover"
    PAYMENT_FRAUD = "payment_fraud"
    AFFILIATE_FRAUD = "affiliate_fraud"


class RiskLevel(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class FraudSignal:
    """Um sinal individual de fraude"""
    name: str
    value: float  # 0-1
    weight: float  # Importância
    category: FraudType
    description: str = ""
    metadata: Dict[str, Any] = None


@dataclass
class FraudScore:
    """Resultado da análise de fraude"""
    score: float  # 0-1 (1 = fraude certa)
    risk_level: RiskLevel
    fraud_types: List[FraudType]
    signals: List[FraudSignal]
    action: str  # 'allow', 'review', 'block'
    confidence: float
    explanation: str
    metadata: Dict[str, Any] = None


@dataclass
class DeviceFingerprint:
    """Fingerprint de device para network analysis"""
    device_id: str
    canvas_hash: str
    webgl_hash: str
    user_agent: str
    screen_resolution: str
    timezone: str
    language: str
    plugins: List[str] = None
    fonts: List[str] = None


@dataclass
class UserBehaviorProfile:
    """Perfil comportamental do usuário"""
    user_id: str
    
    # Temporal patterns
    typical_hours: List[int] = None  # Horas típicas de acesso
    typical_days: List[int] = None  # Dias típicos
    avg_session_duration: float = 0
    avg_events_per_session: float = 0
    
    # Interaction patterns
    avg_scroll_depth: float = 0
    avg_time_on_page: float = 0
    click_pattern_variance: float = 0
    
    # Device patterns
    known_devices: List[str] = None
    typical_locations: List[str] = None
    
    # History
    total_sessions: int = 0
    total_purchases: int = 0
    total_value: float = 0
    first_seen: datetime = None
    last_seen: datetime = None


# =============================================================================
# RULE ENGINE
# =============================================================================

class FraudRuleEngine:
    """
    Engine de regras determinísticas para detecção rápida.
    """
    
    def __init__(self):
        self.rules: List[Dict] = []
        self._setup_default_rules()
    
    def _setup_default_rules(self):
        """Configura regras padrão"""
        
        # Click fraud rules
        self.add_rule({
            'name': 'high_click_velocity',
            'category': FraudType.CLICK_FRAUD,
            'condition': lambda e: e.get('clicks_last_minute', 0) > 10,
            'score': 0.8,
            'weight': 0.9,
            'description': 'Mais de 10 cliques por minuto'
        })
        
        self.add_rule({
            'name': 'datacenter_ip',
            'category': FraudType.BOT_TRAFFIC,
            'condition': lambda e: e.get('is_datacenter', False),
            'score': 0.7,
            'weight': 0.8,
            'description': 'IP de datacenter detectado'
        })
        
        self.add_rule({
            'name': 'missing_fingerprint',
            'category': FraudType.BOT_TRAFFIC,
            'condition': lambda e: not e.get('canvas_hash') and not e.get('webgl_hash'),
            'score': 0.6,
            'weight': 0.7,
            'description': 'Fingerprint não disponível'
        })
        
        self.add_rule({
            'name': 'instant_conversion',
            'category': FraudType.CONVERSION_FRAUD,
            'condition': lambda e: e.get('time_to_conversion', 999) < 5,
            'score': 0.9,
            'weight': 0.95,
            'description': 'Conversão em menos de 5 segundos'
        })
        
        self.add_rule({
            'name': 'no_scroll',
            'category': FraudType.BOT_TRAFFIC,
            'condition': lambda e: e.get('scroll_depth', 0) == 0 and e.get('time_on_page', 0) > 10,
            'score': 0.5,
            'weight': 0.6,
            'description': 'Tempo na página sem scroll'
        })
        
        self.add_rule({
            'name': 'vpn_detected',
            'category': FraudType.BOT_TRAFFIC,
            'condition': lambda e: e.get('is_vpn', False),
            'score': 0.3,
            'weight': 0.4,
            'description': 'VPN detectado'
        })
        
        self.add_rule({
            'name': 'tor_detected',
            'category': FraudType.BOT_TRAFFIC,
            'condition': lambda e: e.get('is_tor', False),
            'score': 0.8,
            'weight': 0.9,
            'description': 'Tor exit node detectado'
        })
        
        self.add_rule({
            'name': 'headless_browser',
            'category': FraudType.BOT_TRAFFIC,
            'condition': lambda e: 'HeadlessChrome' in e.get('user_agent', ''),
            'score': 0.95,
            'weight': 1.0,
            'description': 'Navegador headless detectado'
        })
        
        self.add_rule({
            'name': 'suspicious_referrer',
            'category': FraudType.ATTRIBUTION_FRAUD,
            'condition': lambda e: self._is_suspicious_referrer(e.get('referrer', '')),
            'score': 0.6,
            'weight': 0.7,
            'description': 'Referrer suspeito'
        })
        
        self.add_rule({
            'name': 'click_injection',
            'category': FraudType.ATTRIBUTION_FRAUD,
            'condition': lambda e: e.get('click_to_install_time', 999) < 2,
            'score': 0.85,
            'weight': 0.9,
            'description': 'Possível click injection'
        })
    
    def _is_suspicious_referrer(self, referrer: str) -> bool:
        """Verifica se referrer é suspeito"""
        suspicious_patterns = [
            'click.', 'track.', 'redirect.',
            'offer.', 'promo.', 'deal.'
        ]
        referrer_lower = referrer.lower()
        return any(p in referrer_lower for p in suspicious_patterns)
    
    def add_rule(self, rule: Dict):
        """Adiciona uma regra"""
        self.rules.append(rule)
    
    def evaluate(self, event_data: Dict[str, Any]) -> List[FraudSignal]:
        """Avalia todas as regras"""
        signals = []
        
        for rule in self.rules:
            try:
                if rule['condition'](event_data):
                    signals.append(FraudSignal(
                        name=rule['name'],
                        value=rule['score'],
                        weight=rule['weight'],
                        category=rule['category'],
                        description=rule['description']
                    ))
            except Exception as e:
                logger.warning(f"Rule {rule['name']} failed: {e}")
        
        return signals


# =============================================================================
# ML FRAUD DETECTOR
# =============================================================================

class MLFraudDetector:
    """
    Detector de fraude baseado em ML.
    Usa ensemble de modelos para detecção.
    """
    
    def __init__(self):
        self.feature_means: Dict[str, float] = {}
        self.feature_stds: Dict[str, float] = {}
        self.model_weights: Dict[str, float] = {}
        self._setup_default_model()
    
    def _setup_default_model(self):
        """Configura modelo padrão (heurístico até termos dados)"""
        # Feature statistics (baseline)
        self.feature_means = {
            'scroll_depth': 45,
            'time_on_page': 60,
            'interactions': 5,
            'pages_per_session': 3,
            'trust_score': 0.6,
            'biometric_score': 0.5
        }
        
        self.feature_stds = {
            'scroll_depth': 30,
            'time_on_page': 90,
            'interactions': 4,
            'pages_per_session': 3,
            'trust_score': 0.2,
            'biometric_score': 0.2
        }
        
        # Pesos das features para scoring
        self.model_weights = {
            'scroll_depth_anomaly': 0.15,
            'time_anomaly': 0.15,
            'interaction_anomaly': 0.20,
            'trust_score': 0.25,
            'biometric_score': 0.15,
            'velocity_anomaly': 0.10
        }
    
    def _calculate_zscore(self, value: float, feature: str) -> float:
        """Calcula z-score para uma feature"""
        mean = self.feature_means.get(feature, 0)
        std = self.feature_stds.get(feature, 1)
        
        if std == 0:
            return 0
        
        return (value - mean) / std
    
    def _zscore_to_anomaly(self, zscore: float) -> float:
        """Converte z-score em score de anomalia (0-1)"""
        # Quanto mais longe da média, maior a anomalia
        return min(1.0, abs(zscore) / 3)
    
    def extract_features(self, event_data: Dict[str, Any]) -> Dict[str, float]:
        """Extrai features para o modelo"""
        features = {}
        
        # Behavioral features
        scroll = event_data.get('scroll_depth', 0)
        features['scroll_depth_anomaly'] = self._zscore_to_anomaly(
            self._calculate_zscore(scroll, 'scroll_depth')
        )
        
        time = event_data.get('time_on_page', 0)
        features['time_anomaly'] = self._zscore_to_anomaly(
            self._calculate_zscore(time, 'time_on_page')
        )
        
        interactions = event_data.get('interactions', 0)
        features['interaction_anomaly'] = self._zscore_to_anomaly(
            self._calculate_zscore(interactions, 'interactions')
        )
        
        # Quality features
        features['trust_score'] = 1 - event_data.get('trust_score', 0.5)
        features['biometric_score'] = 1 - event_data.get('biometric_score', 0.5)
        
        # Velocity features
        events_per_minute = event_data.get('events_per_minute', 0)
        features['velocity_anomaly'] = min(1.0, events_per_minute / 20)
        
        return features
    
    def predict(self, event_data: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
        """
        Prediz probabilidade de fraude.
        Returns: (score, feature_contributions)
        """
        features = self.extract_features(event_data)
        
        # Weighted sum
        score = 0
        contributions = {}
        
        for feature, value in features.items():
            weight = self.model_weights.get(feature, 0.1)
            contribution = value * weight
            score += contribution
            contributions[feature] = contribution
        
        # Normalizar para 0-1
        score = min(1.0, max(0.0, score))
        
        return score, contributions


# =============================================================================
# BEHAVIORAL ANALYZER
# =============================================================================

class BehavioralAnalyzer:
    """
    Analisa padrões comportamentais para detectar anomalias.
    """
    
    def __init__(self):
        self.user_profiles: Dict[str, UserBehaviorProfile] = {}
    
    def update_profile(
        self,
        user_id: str,
        event_data: Dict[str, Any]
    ) -> UserBehaviorProfile:
        """Atualiza perfil do usuário com novo evento"""
        
        if user_id not in self.user_profiles:
            self.user_profiles[user_id] = UserBehaviorProfile(
                user_id=user_id,
                typical_hours=[],
                typical_days=[],
                known_devices=[],
                typical_locations=[],
                first_seen=datetime.now()
            )
        
        profile = self.user_profiles[user_id]
        
        # Atualizar padrões temporais
        event_time = event_data.get('timestamp', datetime.now())
        if isinstance(event_time, (int, float)):
            event_time = datetime.fromtimestamp(event_time / 1000)
        
        hour = event_time.hour
        if profile.typical_hours:
            profile.typical_hours.append(hour)
            profile.typical_hours = profile.typical_hours[-100:]  # Keep last 100
        else:
            profile.typical_hours = [hour]
        
        day = event_time.weekday()
        if profile.typical_days:
            profile.typical_days.append(day)
            profile.typical_days = profile.typical_days[-100:]
        else:
            profile.typical_days = [day]
        
        # Atualizar métricas
        profile.avg_scroll_depth = (
            profile.avg_scroll_depth * 0.9 + 
            event_data.get('scroll_depth', 0) * 0.1
        )
        
        profile.avg_time_on_page = (
            profile.avg_time_on_page * 0.9 + 
            event_data.get('time_on_page', 0) * 0.1
        )
        
        # Atualizar devices
        device_id = event_data.get('device_id') or event_data.get('canvas_hash')
        if device_id and profile.known_devices is not None:
            if device_id not in profile.known_devices:
                profile.known_devices.append(device_id)
                profile.known_devices = profile.known_devices[-10:]
        
        # Atualizar locations
        location = event_data.get('city') or event_data.get('country')
        if location and profile.typical_locations is not None:
            if location not in profile.typical_locations:
                profile.typical_locations.append(location)
                profile.typical_locations = profile.typical_locations[-5:]
        
        profile.last_seen = datetime.now()
        profile.total_sessions += 1
        
        if event_data.get('event_name') == 'Purchase':
            profile.total_purchases += 1
            profile.total_value += float(event_data.get('value', 0))
        
        return profile
    
    def analyze_anomaly(
        self,
        user_id: str,
        event_data: Dict[str, Any]
    ) -> List[FraudSignal]:
        """Analisa se evento é anômalo para o usuário"""
        signals = []
        
        profile = self.user_profiles.get(user_id)
        
        if not profile or profile.total_sessions < 3:
            # Novo usuário, não podemos detectar anomalias comportamentais
            return signals
        
        event_time = event_data.get('timestamp', datetime.now())
        if isinstance(event_time, (int, float)):
            event_time = datetime.fromtimestamp(event_time / 1000)
        
        # 1. Anomalia temporal
        hour = event_time.hour
        if profile.typical_hours:
            hour_mean = np.mean(profile.typical_hours)
            hour_std = np.std(profile.typical_hours) or 3
            
            if abs(hour - hour_mean) > 2 * hour_std:
                signals.append(FraudSignal(
                    name='unusual_hour',
                    value=0.5,
                    weight=0.4,
                    category=FraudType.ACCOUNT_TAKEOVER,
                    description=f'Acesso em hora incomum: {hour}h (típico: {hour_mean:.0f}h)'
                ))
        
        # 2. Novo device
        device_id = event_data.get('device_id') or event_data.get('canvas_hash')
        if device_id and profile.known_devices:
            if device_id not in profile.known_devices and len(profile.known_devices) >= 2:
                signals.append(FraudSignal(
                    name='new_device',
                    value=0.4,
                    weight=0.5,
                    category=FraudType.ACCOUNT_TAKEOVER,
                    description='Device não reconhecido'
                ))
        
        # 3. Nova localização
        location = event_data.get('city') or event_data.get('country')
        if location and profile.typical_locations:
            if location not in profile.typical_locations and len(profile.typical_locations) >= 2:
                signals.append(FraudSignal(
                    name='new_location',
                    value=0.5,
                    weight=0.6,
                    category=FraudType.ACCOUNT_TAKEOVER,
                    description=f'Acesso de nova localização: {location}'
                ))
        
        # 4. Comportamento anômalo
        scroll = event_data.get('scroll_depth', 0)
        if profile.avg_scroll_depth > 0:
            scroll_ratio = scroll / profile.avg_scroll_depth
            if scroll_ratio < 0.2 or scroll_ratio > 5:
                signals.append(FraudSignal(
                    name='abnormal_scroll',
                    value=0.3,
                    weight=0.3,
                    category=FraudType.BOT_TRAFFIC,
                    description='Padrão de scroll anormal'
                ))
        
        return signals


# =============================================================================
# NETWORK ANALYZER
# =============================================================================

class NetworkAnalyzer:
    """
    Analisa rede de devices/IPs para detectar fraude coordenada.
    """
    
    def __init__(self):
        self.device_graph: Dict[str, Set[str]] = defaultdict(set)  # device -> users
        self.ip_graph: Dict[str, Set[str]] = defaultdict(set)  # ip -> users
        self.user_devices: Dict[str, Set[str]] = defaultdict(set)  # user -> devices
    
    def add_connection(
        self,
        user_id: str,
        device_id: str = None,
        ip: str = None
    ):
        """Adiciona conexão ao grafo"""
        if device_id:
            self.device_graph[device_id].add(user_id)
            self.user_devices[user_id].add(device_id)
        
        if ip:
            self.ip_graph[ip].add(user_id)
    
    def analyze_network(
        self,
        user_id: str,
        device_id: str = None,
        ip: str = None
    ) -> List[FraudSignal]:
        """Analisa rede para sinais de fraude"""
        signals = []
        
        # 1. Device compartilhado
        if device_id:
            users_on_device = self.device_graph.get(device_id, set())
            if len(users_on_device) > 5:
                signals.append(FraudSignal(
                    name='shared_device',
                    value=min(1.0, len(users_on_device) / 20),
                    weight=0.7,
                    category=FraudType.CLICK_FRAUD,
                    description=f'Device usado por {len(users_on_device)} usuários'
                ))
        
        # 2. IP com muitos usuários
        if ip:
            users_on_ip = self.ip_graph.get(ip, set())
            if len(users_on_ip) > 10:
                signals.append(FraudSignal(
                    name='high_ip_usage',
                    value=min(1.0, len(users_on_ip) / 50),
                    weight=0.6,
                    category=FraudType.CLICK_FRAUD,
                    description=f'IP usado por {len(users_on_ip)} usuários'
                ))
        
        # 3. Usuário com muitos devices
        user_device_count = len(self.user_devices.get(user_id, set()))
        if user_device_count > 5:
            signals.append(FraudSignal(
                name='many_devices',
                value=min(1.0, user_device_count / 20),
                weight=0.5,
                category=FraudType.CLICK_FRAUD,
                description=f'Usuário com {user_device_count} devices'
            ))
        
        return signals


# =============================================================================
# UNIFIED FRAUD DETECTOR
# =============================================================================

class FraudDetector:
    """
    Detector unificado de fraude.
    Combina rule engine, ML e behavioral analysis.
    """
    
    def __init__(self):
        self.rule_engine = FraudRuleEngine()
        self.ml_detector = MLFraudDetector()
        self.behavioral_analyzer = BehavioralAnalyzer()
        self.network_analyzer = NetworkAnalyzer()
        
        # Thresholds
        self.thresholds = {
            RiskLevel.LOW: 0.25,
            RiskLevel.MEDIUM: 0.5,
            RiskLevel.HIGH: 0.75,
            RiskLevel.CRITICAL: 0.9
        }
    
    def _combine_signals(self, signals: List[FraudSignal]) -> float:
        """Combina sinais em score único"""
        if not signals:
            return 0.0
        
        total_weight = sum(s.weight for s in signals)
        if total_weight == 0:
            return 0.0
        
        weighted_sum = sum(s.value * s.weight for s in signals)
        
        return weighted_sum / total_weight
    
    def _get_risk_level(self, score: float) -> RiskLevel:
        """Determina nível de risco baseado no score"""
        if score >= self.thresholds[RiskLevel.CRITICAL]:
            return RiskLevel.CRITICAL
        elif score >= self.thresholds[RiskLevel.HIGH]:
            return RiskLevel.HIGH
        elif score >= self.thresholds[RiskLevel.MEDIUM]:
            return RiskLevel.MEDIUM
        else:
            return RiskLevel.LOW
    
    def _get_action(self, risk_level: RiskLevel) -> str:
        """Determina ação baseada no risco"""
        actions = {
            RiskLevel.LOW: 'allow',
            RiskLevel.MEDIUM: 'allow',
            RiskLevel.HIGH: 'review',
            RiskLevel.CRITICAL: 'block'
        }
        return actions[risk_level]
    
    def analyze(
        self,
        event_data: Dict[str, Any],
        user_id: str = None
    ) -> FraudScore:
        """
        Analisa evento para fraude.
        """
        all_signals = []
        fraud_types = set()
        
        # 1. Rule-based signals
        rule_signals = self.rule_engine.evaluate(event_data)
        all_signals.extend(rule_signals)
        for s in rule_signals:
            fraud_types.add(s.category)
        
        # 2. ML-based score
        ml_score, ml_contributions = self.ml_detector.predict(event_data)
        if ml_score > 0.3:
            all_signals.append(FraudSignal(
                name='ml_fraud_score',
                value=ml_score,
                weight=0.8,
                category=FraudType.BOT_TRAFFIC,
                description=f'ML score: {ml_score:.2f}',
                metadata={'contributions': ml_contributions}
            ))
        
        # 3. Behavioral analysis
        if user_id:
            self.behavioral_analyzer.update_profile(user_id, event_data)
            behavioral_signals = self.behavioral_analyzer.analyze_anomaly(user_id, event_data)
            all_signals.extend(behavioral_signals)
            for s in behavioral_signals:
                fraud_types.add(s.category)
        
        # 4. Network analysis
        device_id = event_data.get('device_id') or event_data.get('canvas_hash')
        ip = event_data.get('ip')
        
        if user_id:
            self.network_analyzer.add_connection(user_id, device_id, ip)
            network_signals = self.network_analyzer.analyze_network(user_id, device_id, ip)
            all_signals.extend(network_signals)
            for s in network_signals:
                fraud_types.add(s.category)
        
        # Combine scores
        final_score = self._combine_signals(all_signals)
        risk_level = self._get_risk_level(final_score)
        action = self._get_action(risk_level)
        
        # Generate explanation
        top_signals = sorted(all_signals, key=lambda s: s.value * s.weight, reverse=True)[:3]
        explanation_parts = [f"{s.name}: {s.description}" for s in top_signals]
        explanation = "; ".join(explanation_parts) if explanation_parts else "Nenhum sinal de fraude detectado"
        
        return FraudScore(
            score=final_score,
            risk_level=risk_level,
            fraud_types=list(fraud_types),
            signals=all_signals,
            action=action,
            confidence=min(0.95, 0.5 + len(all_signals) * 0.05),
            explanation=explanation,
            metadata={
                'ml_score': ml_score,
                'rule_signals': len(rule_signals),
                'total_signals': len(all_signals)
            }
        )


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'FraudType',
    'RiskLevel',
    'FraudSignal',
    'FraudScore',
    'FraudDetector',
    'FraudRuleEngine',
    'MLFraudDetector',
    'BehavioralAnalyzer',
    'NetworkAnalyzer'
]
