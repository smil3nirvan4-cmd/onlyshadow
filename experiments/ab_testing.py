"""
S.S.I. SHADOW — A/B Testing Framework
TEST BID STRATEGIES & CONFIGURATIONS

Features:
- Random assignment to variants
- Statistical significance calculation
- Automatic winner detection
- Rollout percentage control

Usage:
    experiment = ABExperiment(
        name="bid_multiplier_test",
        variants=[
            {"name": "control", "bid_multiplier": 1.0},
            {"name": "aggressive", "bid_multiplier": 1.5},
            {"name": "conservative", "bid_multiplier": 0.7}
        ]
    )
    
    variant = experiment.assign(user_id="ssi_123")
    bid = base_bid * variant["bid_multiplier"]
"""

import os
import json
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, asdict
from enum import Enum
import math
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_ab_testing')

# =============================================================================
# TYPES
# =============================================================================

class ExperimentStatus(Enum):
    DRAFT = "draft"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    WINNER_FOUND = "winner_found"


@dataclass
class Variant:
    name: str
    weight: float = 1.0  # Relative weight for assignment
    config: Dict[str, Any] = None  # Configuration for this variant
    
    # Metrics (updated during experiment)
    visitors: int = 0
    conversions: int = 0
    revenue: float = 0.0
    
    def __post_init__(self):
        if self.config is None:
            self.config = {}
    
    @property
    def conversion_rate(self) -> float:
        if self.visitors == 0:
            return 0.0
        return self.conversions / self.visitors
    
    @property
    def revenue_per_visitor(self) -> float:
        if self.visitors == 0:
            return 0.0
        return self.revenue / self.visitors


@dataclass
class ExperimentConfig:
    # Basic
    name: str
    description: str = ""
    
    # Targeting
    traffic_percentage: float = 100.0  # % of traffic in experiment
    targeting_rules: Dict[str, Any] = None  # Optional targeting
    
    # Duration
    start_date: datetime = None
    end_date: datetime = None
    min_sample_size: int = 1000
    
    # Significance
    confidence_level: float = 0.95
    min_effect_size: float = 0.05  # Minimum detectable effect
    
    # Auto-stop
    auto_stop_enabled: bool = True
    max_loss_threshold: float = 0.10  # Stop if variant loses by more than 10%
    
    def __post_init__(self):
        if self.start_date is None:
            self.start_date = datetime.now()
        if self.targeting_rules is None:
            self.targeting_rules = {}


@dataclass
class ExperimentResult:
    experiment_name: str
    status: ExperimentStatus
    variants: List[Dict]
    winner: Optional[str]
    confidence: float
    lift: float  # % improvement over control
    sample_size: int
    duration_days: int
    recommendation: str


# =============================================================================
# STATISTICAL FUNCTIONS
# =============================================================================

def calculate_z_score(p1: float, p2: float, n1: int, n2: int) -> float:
    """
    Calculate Z-score for two proportions test.
    """
    if n1 == 0 or n2 == 0:
        return 0.0
    
    # Pooled proportion
    p_pool = (p1 * n1 + p2 * n2) / (n1 + n2)
    
    if p_pool == 0 or p_pool == 1:
        return 0.0
    
    # Standard error
    se = math.sqrt(p_pool * (1 - p_pool) * (1/n1 + 1/n2))
    
    if se == 0:
        return 0.0
    
    # Z-score
    z = (p1 - p2) / se
    
    return z


def z_to_confidence(z: float) -> float:
    """
    Convert Z-score to confidence level using normal distribution approximation.
    """
    # Approximation of normal CDF
    if z < 0:
        return 1 - z_to_confidence(-z)
    
    # Abramowitz and Stegun approximation
    b0 = 0.2316419
    b1 = 0.319381530
    b2 = -0.356563782
    b3 = 1.781477937
    b4 = -1.821255978
    b5 = 1.330274429
    
    t = 1 / (1 + b0 * z)
    
    pdf = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
    
    cdf = 1 - pdf * (b1*t + b2*t**2 + b3*t**3 + b4*t**4 + b5*t**5)
    
    return cdf


def calculate_sample_size(
    baseline_rate: float,
    min_effect: float,
    confidence: float = 0.95,
    power: float = 0.80
) -> int:
    """
    Calculate minimum sample size per variant.
    """
    # Z-scores for confidence and power
    z_alpha = 1.96 if confidence >= 0.95 else 1.645
    z_beta = 0.84 if power >= 0.80 else 0.52
    
    p1 = baseline_rate
    p2 = baseline_rate * (1 + min_effect)
    
    p_avg = (p1 + p2) / 2
    
    n = 2 * ((z_alpha + z_beta) ** 2) * p_avg * (1 - p_avg) / ((p2 - p1) ** 2)
    
    return int(math.ceil(n))


def is_winner(
    variant: Variant,
    control: Variant,
    confidence_threshold: float = 0.95
) -> Tuple[bool, float, float]:
    """
    Determine if variant is a winner over control.
    Returns: (is_winner, confidence, lift)
    """
    if variant.visitors < 100 or control.visitors < 100:
        return False, 0.0, 0.0
    
    # Conversion rate comparison
    z = calculate_z_score(
        variant.conversion_rate,
        control.conversion_rate,
        variant.visitors,
        control.visitors
    )
    
    confidence = z_to_confidence(abs(z))
    
    # Lift calculation
    if control.conversion_rate > 0:
        lift = (variant.conversion_rate - control.conversion_rate) / control.conversion_rate
    else:
        lift = 0.0
    
    is_winner = confidence >= confidence_threshold and lift > 0
    
    return is_winner, confidence, lift


# =============================================================================
# EXPERIMENT CLASS
# =============================================================================

class ABExperiment:
    """
    A/B Testing Experiment Manager
    """
    
    def __init__(
        self,
        name: str,
        variants: List[Dict[str, Any]],
        config: ExperimentConfig = None
    ):
        self.name = name
        self.config = config or ExperimentConfig(name=name)
        self.status = ExperimentStatus.DRAFT
        
        # Parse variants
        self.variants: Dict[str, Variant] = {}
        total_weight = sum(v.get('weight', 1.0) for v in variants)
        
        for v in variants:
            variant = Variant(
                name=v['name'],
                weight=v.get('weight', 1.0) / total_weight,
                config=v.get('config', v)
            )
            self.variants[v['name']] = variant
        
        # Set control (first variant by default)
        self.control_name = variants[0]['name']
        
        # Assignment cache
        self._assignments: Dict[str, str] = {}
    
    def start(self):
        """Start the experiment"""
        self.status = ExperimentStatus.RUNNING
        self.config.start_date = datetime.now()
        logger.info(f"Experiment '{self.name}' started")
    
    def pause(self):
        """Pause the experiment"""
        self.status = ExperimentStatus.PAUSED
        logger.info(f"Experiment '{self.name}' paused")
    
    def stop(self, winner: str = None):
        """Stop the experiment"""
        if winner:
            self.status = ExperimentStatus.WINNER_FOUND
        else:
            self.status = ExperimentStatus.COMPLETED
        self.config.end_date = datetime.now()
        logger.info(f"Experiment '{self.name}' stopped. Winner: {winner}")
    
    def _hash_assignment(self, user_id: str) -> float:
        """
        Deterministic hash for consistent assignment.
        Returns value between 0 and 1.
        """
        hash_input = f"{self.name}:{user_id}"
        hash_value = hashlib.md5(hash_input.encode()).hexdigest()
        return int(hash_value[:8], 16) / 0xFFFFFFFF
    
    def assign(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        Assign user to a variant.
        Returns variant config or None if not in experiment.
        """
        if self.status != ExperimentStatus.RUNNING:
            return None
        
        # Check if already assigned
        if user_id in self._assignments:
            variant_name = self._assignments[user_id]
            return self.variants[variant_name].config
        
        # Check traffic percentage
        traffic_hash = self._hash_assignment(f"traffic:{user_id}")
        if traffic_hash > self.config.traffic_percentage / 100:
            return None  # Not in experiment
        
        # Assign to variant based on weights
        variant_hash = self._hash_assignment(user_id)
        
        cumulative_weight = 0.0
        assigned_variant = None
        
        for name, variant in self.variants.items():
            cumulative_weight += variant.weight
            if variant_hash <= cumulative_weight:
                assigned_variant = name
                break
        
        if assigned_variant is None:
            assigned_variant = list(self.variants.keys())[-1]
        
        # Cache assignment
        self._assignments[user_id] = assigned_variant
        
        # Increment visitor count
        self.variants[assigned_variant].visitors += 1
        
        return self.variants[assigned_variant].config
    
    def record_conversion(self, user_id: str, value: float = 1.0):
        """
        Record a conversion for a user.
        """
        if user_id not in self._assignments:
            return
        
        variant_name = self._assignments[user_id]
        self.variants[variant_name].conversions += 1
        self.variants[variant_name].revenue += value
    
    def get_results(self) -> ExperimentResult:
        """
        Get current experiment results with statistical analysis.
        """
        control = self.variants[self.control_name]
        
        variant_results = []
        winner = None
        best_lift = 0.0
        best_confidence = 0.0
        
        for name, variant in self.variants.items():
            is_control = name == self.control_name
            
            if is_control:
                is_win, conf, lift = False, 0.0, 0.0
            else:
                is_win, conf, lift = is_winner(
                    variant, 
                    control,
                    self.config.confidence_level
                )
            
            variant_results.append({
                'name': name,
                'is_control': is_control,
                'visitors': variant.visitors,
                'conversions': variant.conversions,
                'conversion_rate': variant.conversion_rate,
                'revenue': variant.revenue,
                'revenue_per_visitor': variant.revenue_per_visitor,
                'is_winner': is_win,
                'confidence': conf,
                'lift': lift
            })
            
            if is_win and lift > best_lift:
                winner = name
                best_lift = lift
                best_confidence = conf
        
        # Calculate duration
        duration = (datetime.now() - self.config.start_date).days if self.config.start_date else 0
        
        # Generate recommendation
        total_sample = sum(v.visitors for v in self.variants.values())
        
        if total_sample < self.config.min_sample_size:
            recommendation = f"Need more data. Current: {total_sample}, Required: {self.config.min_sample_size}"
        elif winner:
            recommendation = f"Implement '{winner}' - {best_lift:.1%} lift with {best_confidence:.1%} confidence"
        else:
            recommendation = "No clear winner yet. Continue test or evaluate if effect size is too small."
        
        return ExperimentResult(
            experiment_name=self.name,
            status=self.status,
            variants=variant_results,
            winner=winner,
            confidence=best_confidence,
            lift=best_lift,
            sample_size=total_sample,
            duration_days=duration,
            recommendation=recommendation
        )
    
    def check_auto_stop(self) -> Tuple[bool, str]:
        """
        Check if experiment should auto-stop.
        Returns: (should_stop, reason)
        """
        if not self.config.auto_stop_enabled:
            return False, ""
        
        results = self.get_results()
        
        # Check for clear winner
        if results.winner and results.confidence >= 0.99:
            return True, f"Clear winner found: {results.winner} with 99%+ confidence"
        
        # Check for losing variants
        control = self.variants[self.control_name]
        
        for name, variant in self.variants.items():
            if name == self.control_name:
                continue
            
            if variant.visitors < 100:
                continue
            
            _, conf, lift = is_winner(variant, control, 0.95)
            
            # If variant is significantly worse
            if conf >= 0.95 and lift < -self.config.max_loss_threshold:
                return True, f"Variant '{name}' is significantly worse ({lift:.1%})"
        
        # Check if reached end date
        if self.config.end_date and datetime.now() >= self.config.end_date:
            return True, "End date reached"
        
        return False, ""
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize experiment to dict"""
        return {
            'name': self.name,
            'status': self.status.value,
            'config': {
                'description': self.config.description,
                'traffic_percentage': self.config.traffic_percentage,
                'start_date': self.config.start_date.isoformat() if self.config.start_date else None,
                'end_date': self.config.end_date.isoformat() if self.config.end_date else None,
                'min_sample_size': self.config.min_sample_size,
                'confidence_level': self.config.confidence_level
            },
            'variants': {
                name: {
                    'weight': v.weight,
                    'config': v.config,
                    'visitors': v.visitors,
                    'conversions': v.conversions,
                    'revenue': v.revenue
                }
                for name, v in self.variants.items()
            },
            'control_name': self.control_name
        }


# =============================================================================
# EXPERIMENT MANAGER
# =============================================================================

class ExperimentManager:
    """
    Manages multiple experiments
    """
    
    def __init__(self, storage_path: str = None):
        self.experiments: Dict[str, ABExperiment] = {}
        self.storage_path = storage_path
    
    def create_experiment(
        self,
        name: str,
        variants: List[Dict],
        config: ExperimentConfig = None
    ) -> ABExperiment:
        """Create a new experiment"""
        experiment = ABExperiment(name, variants, config)
        self.experiments[name] = experiment
        return experiment
    
    def get_experiment(self, name: str) -> Optional[ABExperiment]:
        """Get experiment by name"""
        return self.experiments.get(name)
    
    def get_all_active(self) -> List[ABExperiment]:
        """Get all running experiments"""
        return [
            exp for exp in self.experiments.values()
            if exp.status == ExperimentStatus.RUNNING
        ]
    
    def assign_all(self, user_id: str) -> Dict[str, Dict]:
        """
        Assign user to all active experiments.
        Returns dict of experiment_name -> variant_config
        """
        assignments = {}
        
        for exp in self.get_all_active():
            variant = exp.assign(user_id)
            if variant:
                assignments[exp.name] = variant
        
        return assignments
    
    def save(self):
        """Save experiments to storage"""
        if not self.storage_path:
            return
        
        data = {
            name: exp.to_dict()
            for name, exp in self.experiments.items()
        }
        
        with open(self.storage_path, 'w') as f:
            json.dump(data, f, indent=2, default=str)
    
    def load(self):
        """Load experiments from storage"""
        if not self.storage_path or not os.path.exists(self.storage_path):
            return
        
        with open(self.storage_path, 'r') as f:
            data = json.load(f)
        
        # Reconstruct experiments
        for name, exp_data in data.items():
            variants = [
                {
                    'name': v_name,
                    'weight': v_data['weight'],
                    'config': v_data['config']
                }
                for v_name, v_data in exp_data['variants'].items()
            ]
            
            config = ExperimentConfig(
                name=name,
                description=exp_data['config'].get('description', ''),
                traffic_percentage=exp_data['config'].get('traffic_percentage', 100)
            )
            
            exp = ABExperiment(name, variants, config)
            exp.status = ExperimentStatus(exp_data['status'])
            
            # Restore metrics
            for v_name, v_data in exp_data['variants'].items():
                exp.variants[v_name].visitors = v_data['visitors']
                exp.variants[v_name].conversions = v_data['conversions']
                exp.variants[v_name].revenue = v_data['revenue']
            
            self.experiments[name] = exp


# =============================================================================
# PREDEFINED EXPERIMENTS
# =============================================================================

def create_bid_multiplier_experiment(manager: ExperimentManager) -> ABExperiment:
    """Create bid multiplier A/B test"""
    return manager.create_experiment(
        name="bid_multiplier_test",
        variants=[
            {"name": "control", "bid_multiplier": 1.0, "weight": 1.0},
            {"name": "aggressive_10", "bid_multiplier": 1.1, "weight": 1.0},
            {"name": "aggressive_20", "bid_multiplier": 1.2, "weight": 1.0},
            {"name": "conservative_10", "bid_multiplier": 0.9, "weight": 0.5}
        ],
        config=ExperimentConfig(
            name="bid_multiplier_test",
            description="Test different bid multipliers based on LTV score",
            traffic_percentage=50,  # Only 50% of traffic
            min_sample_size=5000,
            confidence_level=0.95
        )
    )


def create_trust_threshold_experiment(manager: ExperimentManager) -> ABExperiment:
    """Create trust score threshold A/B test"""
    return manager.create_experiment(
        name="trust_threshold_test",
        variants=[
            {"name": "control", "trust_threshold": 0.4, "weight": 1.0},
            {"name": "strict", "trust_threshold": 0.5, "weight": 1.0},
            {"name": "relaxed", "trust_threshold": 0.3, "weight": 1.0}
        ],
        config=ExperimentConfig(
            name="trust_threshold_test",
            description="Test different trust score thresholds for CAPI",
            traffic_percentage=100,
            min_sample_size=10000
        )
    )


# =============================================================================
# CLI
# =============================================================================

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='SSI Shadow A/B Testing')
    parser.add_argument('--action', required=True, 
                       choices=['create', 'start', 'stop', 'results', 'simulate'])
    parser.add_argument('--experiment', help='Experiment name')
    parser.add_argument('--users', type=int, default=1000, help='Users for simulation')
    
    args = parser.parse_args()
    
    manager = ExperimentManager()
    
    if args.action == 'create':
        exp = create_bid_multiplier_experiment(manager)
        print(f"Created experiment: {exp.name}")
        print(json.dumps(exp.to_dict(), indent=2, default=str))
    
    elif args.action == 'simulate':
        # Simulate an experiment
        exp = create_bid_multiplier_experiment(manager)
        exp.start()
        
        # Simulate users with different conversion rates per variant
        conversion_rates = {
            'control': 0.03,
            'aggressive_10': 0.035,
            'aggressive_20': 0.032,
            'conservative_10': 0.028
        }
        
        for i in range(args.users):
            user_id = f"user_{i}"
            variant = exp.assign(user_id)
            
            if variant:
                variant_name = None
                for name, v in exp.variants.items():
                    if v.config == variant:
                        variant_name = name
                        break
                
                if variant_name and random.random() < conversion_rates.get(variant_name, 0.03):
                    value = random.uniform(50, 200)
                    exp.record_conversion(user_id, value)
        
        results = exp.get_results()
        print(f"\nExperiment: {results.experiment_name}")
        print(f"Status: {results.status.value}")
        print(f"Sample Size: {results.sample_size}")
        print(f"Duration: {results.duration_days} days")
        print(f"\nVariants:")
        
        for v in results.variants:
            print(f"  {v['name']}:")
            print(f"    Visitors: {v['visitors']}")
            print(f"    Conversions: {v['conversions']}")
            print(f"    Conv Rate: {v['conversion_rate']:.2%}")
            print(f"    Revenue: R$ {v['revenue']:.2f}")
            if not v['is_control']:
                print(f"    Lift: {v['lift']:.1%}")
                print(f"    Confidence: {v['confidence']:.1%}")
                print(f"    Winner: {'✓' if v['is_winner'] else '✗'}")
        
        print(f"\nRecommendation: {results.recommendation}")

if __name__ == '__main__':
    main()
