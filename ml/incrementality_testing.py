"""
S.S.I. SHADOW — INCREMENTALITY TESTING
GEO HOLDOUTS & SYNTHETIC CONTROL

Mede incrementalidade real de campanhas publicitárias.

Métodos:
1. Geo Holdout - Divide regiões em test/control
2. Synthetic Control - Cria controle sintético de regiões similares
3. Time-based Holdout - Pausa ads em períodos específicos
4. Ghost Ads - Holdout a nível de usuário

Por que isso importa:
- Last-click attribution superestima paid media
- MMM é top-down e pode ter viés
- Holdout é o "gold standard" para causalidade
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
from scipy.optimize import minimize

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_incrementality')

# =============================================================================
# TYPES
# =============================================================================

class TestType(Enum):
    GEO_HOLDOUT = "geo_holdout"
    SYNTHETIC_CONTROL = "synthetic_control"
    TIME_HOLDOUT = "time_holdout"
    USER_HOLDOUT = "user_holdout"  # Ghost ads


class TestStatus(Enum):
    DRAFT = "draft"
    RUNNING = "running"
    COMPLETED = "completed"
    ANALYZED = "analyzed"


@dataclass
class GeoRegion:
    """Região geográfica para testes"""
    id: str
    name: str
    population: int = 0
    baseline_conversions: float = 0
    baseline_revenue: float = 0
    
    # Covariates para matching
    avg_income: float = 0
    urban_rate: float = 0
    internet_penetration: float = 0


@dataclass
class TestConfig:
    """Configuração do teste de incrementalidade"""
    name: str
    test_type: TestType
    
    # Duration
    start_date: datetime
    end_date: datetime
    pre_period_days: int = 30  # Para baseline
    
    # Split
    treatment_percentage: float = 50  # % de regiões em tratamento
    min_effect_size: float = 0.05  # Efeito mínimo detectável
    confidence_level: float = 0.95
    
    # Targeting
    channel: str = None  # 'meta', 'google', 'all'
    campaign_ids: List[str] = None


@dataclass
class IncrementalityResult:
    """Resultado do teste de incrementalidade"""
    test_name: str
    test_type: TestType
    
    # Metrics
    treatment_conversions: float
    control_conversions: float
    incremental_conversions: float
    incremental_revenue: float
    
    # Statistics
    lift_percentage: float
    confidence_interval: Tuple[float, float]
    p_value: float
    is_significant: bool
    
    # ROI
    ad_spend: float
    incremental_roas: float
    cost_per_incremental_conversion: float
    
    # Details
    treatment_regions: List[str]
    control_regions: List[str]
    analysis_date: datetime


# =============================================================================
# GEO HOLDOUT TEST
# =============================================================================

class GeoHoldoutTest:
    """
    Teste de holdout geográfico.
    
    Divide regiões em tratamento (veem ads) e controle (não veem).
    Após período de teste, compara conversões para medir incrementalidade.
    """
    
    def __init__(self, config: TestConfig, regions: List[GeoRegion]):
        self.config = config
        self.regions = {r.id: r for r in regions}
        self.treatment_regions: List[str] = []
        self.control_regions: List[str] = []
        self.status = TestStatus.DRAFT
    
    def _calculate_distance(self, r1: GeoRegion, r2: GeoRegion) -> float:
        """Calcula distância entre regiões baseado em covariates"""
        features1 = np.array([
            r1.population / 1e6,
            r1.baseline_conversions / max(1, r1.population) * 1000,
            r1.avg_income / 1000,
            r1.urban_rate,
            r1.internet_penetration
        ])
        
        features2 = np.array([
            r2.population / 1e6,
            r2.baseline_conversions / max(1, r2.population) * 1000,
            r2.avg_income / 1000,
            r2.urban_rate,
            r2.internet_penetration
        ])
        
        return np.sqrt(np.sum((features1 - features2) ** 2))
    
    def create_matched_pairs(self) -> List[Tuple[str, str]]:
        """
        Cria pares de regiões similares para matching.
        Uma vai para tratamento, outra para controle.
        """
        region_list = list(self.regions.values())
        n = len(region_list)
        
        # Calcular matriz de distâncias
        distances = np.zeros((n, n))
        for i in range(n):
            for j in range(i+1, n):
                dist = self._calculate_distance(region_list[i], region_list[j])
                distances[i, j] = dist
                distances[j, i] = dist
        
        # Greedy matching
        pairs = []
        used = set()
        
        # Ordenar pares por distância
        pair_distances = []
        for i in range(n):
            for j in range(i+1, n):
                pair_distances.append((distances[i, j], i, j))
        
        pair_distances.sort()
        
        for dist, i, j in pair_distances:
            if i not in used and j not in used:
                pairs.append((region_list[i].id, region_list[j].id))
                used.add(i)
                used.add(j)
        
        return pairs
    
    def assign_regions(self, method: str = 'matched_pairs'):
        """
        Atribui regiões a tratamento e controle.
        
        Methods:
        - 'matched_pairs': Pares similares, random assignment
        - 'stratified': Estratificação por covariates
        - 'random': Completamente aleatório
        """
        if method == 'matched_pairs':
            pairs = self.create_matched_pairs()
            
            for r1, r2 in pairs:
                if np.random.random() < 0.5:
                    self.treatment_regions.append(r1)
                    self.control_regions.append(r2)
                else:
                    self.treatment_regions.append(r2)
                    self.control_regions.append(r1)
        
        elif method == 'random':
            region_ids = list(self.regions.keys())
            np.random.shuffle(region_ids)
            
            split_idx = int(len(region_ids) * self.config.treatment_percentage / 100)
            self.treatment_regions = region_ids[:split_idx]
            self.control_regions = region_ids[split_idx:]
        
        elif method == 'stratified':
            # Estratificar por baseline conversions
            sorted_regions = sorted(
                self.regions.values(),
                key=lambda r: r.baseline_conversions
            )
            
            for i, region in enumerate(sorted_regions):
                if i % 2 == 0:
                    self.treatment_regions.append(region.id)
                else:
                    self.control_regions.append(region.id)
        
        logger.info(f"Assigned {len(self.treatment_regions)} treatment, {len(self.control_regions)} control regions")
    
    def start(self):
        """Inicia o teste"""
        if not self.treatment_regions:
            self.assign_regions()
        
        self.status = TestStatus.RUNNING
        self.config.start_date = datetime.now()
        
        logger.info(f"Geo holdout test '{self.config.name}' started")
        
        return {
            'treatment_regions': self.treatment_regions,
            'control_regions': self.control_regions,
            'start_date': self.config.start_date.isoformat()
        }
    
    def analyze(
        self,
        treatment_data: Dict[str, float],  # region_id -> conversions
        control_data: Dict[str, float],
        spend_data: Dict[str, float] = None  # region_id -> ad spend
    ) -> IncrementalityResult:
        """
        Analisa resultados do teste.
        """
        # Calcular totais
        treatment_conversions = sum(
            treatment_data.get(r, 0) for r in self.treatment_regions
        )
        control_conversions = sum(
            control_data.get(r, 0) for r in self.control_regions
        )
        
        # Normalizar por população
        treatment_pop = sum(
            self.regions[r].population for r in self.treatment_regions
        )
        control_pop = sum(
            self.regions[r].population for r in self.control_regions
        )
        
        treatment_rate = treatment_conversions / max(1, treatment_pop) * 1000
        control_rate = control_conversions / max(1, control_pop) * 1000
        
        # Lift
        if control_rate > 0:
            lift = (treatment_rate - control_rate) / control_rate
        else:
            lift = 0
        
        # Statistical test (two-proportion z-test)
        n1 = treatment_pop
        n2 = control_pop
        p1 = treatment_conversions / max(1, n1)
        p2 = control_conversions / max(1, n2)
        
        # Pooled proportion
        p_pool = (treatment_conversions + control_conversions) / (n1 + n2)
        
        # Standard error
        se = np.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
        
        if se > 0:
            z_score = (p1 - p2) / se
            p_value = 2 * (1 - stats.norm.cdf(abs(z_score)))
        else:
            z_score = 0
            p_value = 1
        
        # Confidence interval
        ci_mult = stats.norm.ppf((1 + self.config.confidence_level) / 2)
        se_lift = se / max(p2, 1e-10)
        ci_lower = lift - ci_mult * se_lift
        ci_upper = lift + ci_mult * se_lift
        
        # Incremental metrics
        # Incremental = O que teríamos perdido sem ads
        expected_control_conversions = control_rate * treatment_pop / 1000
        incremental_conversions = treatment_conversions - expected_control_conversions
        
        # Assume R$100 AOV for revenue
        aov = 100
        incremental_revenue = incremental_conversions * aov
        
        # Ad spend
        if spend_data:
            ad_spend = sum(spend_data.get(r, 0) for r in self.treatment_regions)
        else:
            ad_spend = 0
        
        # iROAS
        if ad_spend > 0:
            incremental_roas = incremental_revenue / ad_spend
            cpic = ad_spend / max(1, incremental_conversions)
        else:
            incremental_roas = 0
            cpic = 0
        
        self.status = TestStatus.ANALYZED
        
        return IncrementalityResult(
            test_name=self.config.name,
            test_type=self.config.test_type,
            treatment_conversions=treatment_conversions,
            control_conversions=control_conversions,
            incremental_conversions=incremental_conversions,
            incremental_revenue=incremental_revenue,
            lift_percentage=lift * 100,
            confidence_interval=(ci_lower * 100, ci_upper * 100),
            p_value=p_value,
            is_significant=p_value < (1 - self.config.confidence_level),
            ad_spend=ad_spend,
            incremental_roas=incremental_roas,
            cost_per_incremental_conversion=cpic,
            treatment_regions=self.treatment_regions,
            control_regions=self.control_regions,
            analysis_date=datetime.now()
        )


# =============================================================================
# SYNTHETIC CONTROL
# =============================================================================

class SyntheticControlTest:
    """
    Método de Controle Sintético.
    
    Cria uma região de controle "sintética" como combinação ponderada
    de regiões não tratadas que melhor replica a região tratada.
    
    Útil quando não podemos fazer holdout real (poucas regiões).
    """
    
    def __init__(self, config: TestConfig, regions: List[GeoRegion]):
        self.config = config
        self.regions = {r.id: r for r in regions}
        self.treatment_region: str = None
        self.donor_weights: Dict[str, float] = {}
    
    def set_treatment(self, region_id: str):
        """Define região de tratamento"""
        self.treatment_region = region_id
    
    def fit_synthetic_control(
        self,
        pre_period_data: Dict[str, List[float]]  # region_id -> time series
    ) -> Dict[str, float]:
        """
        Encontra pesos ótimos para criar controle sintético.
        
        Minimiza diferença entre tratamento e combinação ponderada
        de doadores no período pré-tratamento.
        """
        treatment_data = np.array(pre_period_data[self.treatment_region])
        
        donor_ids = [r for r in pre_period_data if r != self.treatment_region]
        donor_matrix = np.column_stack([
            pre_period_data[r] for r in donor_ids
        ])
        
        n_donors = len(donor_ids)
        
        def objective(weights):
            synthetic = donor_matrix @ weights
            return np.sum((treatment_data - synthetic) ** 2)
        
        # Constraints: weights sum to 1, all positive
        constraints = [
            {'type': 'eq', 'fun': lambda w: np.sum(w) - 1}
        ]
        bounds = [(0, 1) for _ in range(n_donors)]
        
        # Initial guess
        x0 = np.ones(n_donors) / n_donors
        
        result = minimize(
            objective,
            x0,
            method='SLSQP',
            bounds=bounds,
            constraints=constraints
        )
        
        self.donor_weights = dict(zip(donor_ids, result.x))
        
        # Filter small weights
        self.donor_weights = {
            k: v for k, v in self.donor_weights.items()
            if v > 0.01
        }
        
        # Renormalize
        total = sum(self.donor_weights.values())
        self.donor_weights = {
            k: v / total for k, v in self.donor_weights.items()
        }
        
        logger.info(f"Synthetic control weights: {self.donor_weights}")
        
        return self.donor_weights
    
    def estimate_effect(
        self,
        post_period_data: Dict[str, List[float]]
    ) -> Dict[str, Any]:
        """
        Estima efeito do tratamento.
        
        Compara tratamento real com controle sintético no período pós.
        """
        treatment_actual = np.array(post_period_data[self.treatment_region])
        
        # Synthetic control
        synthetic = np.zeros(len(treatment_actual))
        for region_id, weight in self.donor_weights.items():
            if region_id in post_period_data:
                synthetic += weight * np.array(post_period_data[region_id])
        
        # Effect = Treatment - Synthetic
        effect = treatment_actual - synthetic
        cumulative_effect = np.sum(effect)
        
        # Percentage lift
        if np.sum(synthetic) > 0:
            lift = cumulative_effect / np.sum(synthetic)
        else:
            lift = 0
        
        # Placebo tests para p-value
        # (rodar controle sintético em cada donor como se fosse tratamento)
        placebo_effects = []
        
        for placebo_region in self.donor_weights.keys():
            # Fit synthetic control for placebo
            placebo_weights = {
                k: v for k, v in self.donor_weights.items()
                if k != placebo_region
            }
            
            if not placebo_weights:
                continue
            
            # Renormalize
            total = sum(placebo_weights.values())
            placebo_weights = {k: v / total for k, v in placebo_weights.items()}
            
            placebo_synthetic = np.zeros(len(treatment_actual))
            for rid, w in placebo_weights.items():
                if rid in post_period_data:
                    placebo_synthetic += w * np.array(post_period_data[rid])
            
            placebo_actual = np.array(post_period_data.get(placebo_region, [0]))
            if len(placebo_actual) == len(placebo_synthetic):
                placebo_effect = np.sum(placebo_actual - placebo_synthetic)
                placebo_effects.append(placebo_effect)
        
        # P-value: proportion of placebo effects >= our effect
        if placebo_effects:
            p_value = np.mean([abs(pe) >= abs(cumulative_effect) for pe in placebo_effects])
        else:
            p_value = 0.5
        
        return {
            'treatment_region': self.treatment_region,
            'cumulative_effect': cumulative_effect,
            'lift_percentage': lift * 100,
            'p_value': p_value,
            'is_significant': p_value < 0.1,
            'effect_by_period': effect.tolist(),
            'synthetic_by_period': synthetic.tolist(),
            'actual_by_period': treatment_actual.tolist(),
            'donor_weights': self.donor_weights
        }


# =============================================================================
# INCREMENTALITY CALCULATOR
# =============================================================================

class IncrementalityCalculator:
    """
    Calculadora unificada de incrementalidade.
    Usa múltiplos métodos e triangula resultados.
    """
    
    def __init__(self, bq_client = None, project_id: str = None):
        self.bq = bq_client
        self.project_id = project_id
    
    def run_geo_holdout(
        self,
        config: TestConfig,
        regions: List[GeoRegion]
    ) -> GeoHoldoutTest:
        """Cria e inicia teste de geo holdout"""
        test = GeoHoldoutTest(config, regions)
        test.assign_regions(method='matched_pairs')
        return test
    
    def run_synthetic_control(
        self,
        config: TestConfig,
        regions: List[GeoRegion],
        treatment_region: str,
        pre_period_data: Dict[str, List[float]]
    ) -> SyntheticControlTest:
        """Cria e ajusta controle sintético"""
        test = SyntheticControlTest(config, regions)
        test.set_treatment(treatment_region)
        test.fit_synthetic_control(pre_period_data)
        return test
    
    def calculate_iroas(
        self,
        incremental_revenue: float,
        ad_spend: float
    ) -> float:
        """Calcula incremental ROAS"""
        if ad_spend <= 0:
            return 0
        return incremental_revenue / ad_spend
    
    def power_analysis(
        self,
        baseline_conversion_rate: float,
        expected_lift: float,
        sample_size_per_group: int,
        alpha: float = 0.05
    ) -> float:
        """
        Calcula poder estatístico do teste.
        
        Retorna probabilidade de detectar efeito real.
        """
        p1 = baseline_conversion_rate
        p2 = baseline_conversion_rate * (1 + expected_lift)
        
        # Pooled proportion
        p_pool = (p1 + p2) / 2
        
        # Standard error under null
        se_null = np.sqrt(2 * p_pool * (1 - p_pool) / sample_size_per_group)
        
        # Standard error under alternative
        se_alt = np.sqrt(
            p1 * (1 - p1) / sample_size_per_group +
            p2 * (1 - p2) / sample_size_per_group
        )
        
        # Z-score for significance level
        z_alpha = stats.norm.ppf(1 - alpha / 2)
        
        # Effect size
        effect = abs(p2 - p1)
        
        # Power
        z_power = (effect - z_alpha * se_null) / se_alt
        power = stats.norm.cdf(z_power)
        
        return power
    
    def required_sample_size(
        self,
        baseline_conversion_rate: float,
        min_detectable_effect: float,
        power: float = 0.8,
        alpha: float = 0.05
    ) -> int:
        """
        Calcula tamanho de amostra necessário.
        """
        p1 = baseline_conversion_rate
        p2 = baseline_conversion_rate * (1 + min_detectable_effect)
        
        effect = abs(p2 - p1)
        p_pool = (p1 + p2) / 2
        
        z_alpha = stats.norm.ppf(1 - alpha / 2)
        z_beta = stats.norm.ppf(power)
        
        n = (
            2 * p_pool * (1 - p_pool) * (z_alpha + z_beta) ** 2
        ) / (effect ** 2)
        
        return int(np.ceil(n))
    
    def triangulate_results(
        self,
        geo_result: IncrementalityResult = None,
        synthetic_result: Dict = None,
        mta_result: Dict = None,
        mmm_result: Dict = None
    ) -> Dict[str, Any]:
        """
        Triangula resultados de diferentes métodos.
        
        Combina evidências para estimativa mais robusta.
        """
        estimates = []
        weights = []
        
        if geo_result and geo_result.is_significant:
            estimates.append(geo_result.lift_percentage)
            weights.append(0.4)  # Peso alto para experimento
        
        if synthetic_result and synthetic_result.get('is_significant'):
            estimates.append(synthetic_result['lift_percentage'])
            weights.append(0.3)
        
        if mta_result:
            # MTA geralmente superestima
            mta_lift = mta_result.get('lift_percentage', 0)
            estimates.append(mta_lift * 0.7)  # Desconto
            weights.append(0.15)
        
        if mmm_result:
            mmm_lift = mmm_result.get('lift_percentage', 0)
            estimates.append(mmm_lift)
            weights.append(0.15)
        
        if not estimates:
            return {'error': 'No valid estimates available'}
        
        # Weighted average
        total_weight = sum(weights)
        weights = [w / total_weight for w in weights]
        
        triangulated_lift = sum(e * w for e, w in zip(estimates, weights))
        
        # Variance
        variance = sum(w * (e - triangulated_lift) ** 2 for e, w in zip(estimates, weights))
        std_error = np.sqrt(variance)
        
        return {
            'triangulated_lift': triangulated_lift,
            'confidence_interval': (
                triangulated_lift - 1.96 * std_error,
                triangulated_lift + 1.96 * std_error
            ),
            'individual_estimates': {
                'geo_holdout': geo_result.lift_percentage if geo_result else None,
                'synthetic_control': synthetic_result.get('lift_percentage') if synthetic_result else None,
                'mta': mta_result.get('lift_percentage') if mta_result else None,
                'mmm': mmm_result.get('lift_percentage') if mmm_result else None
            },
            'weights_used': dict(zip(
                ['geo', 'synthetic', 'mta', 'mmm'][:len(weights)],
                weights
            ))
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'TestType',
    'TestConfig',
    'GeoRegion',
    'IncrementalityResult',
    'GeoHoldoutTest',
    'SyntheticControlTest',
    'IncrementalityCalculator'
]
