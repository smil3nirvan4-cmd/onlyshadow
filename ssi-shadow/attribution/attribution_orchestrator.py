"""
S.S.I. SHADOW — ATTRIBUTION ORCHESTRATOR
UNIFIED ATTRIBUTION ACROSS ALL METHODS

Unifica todos os métodos de atribuição:
1. Last-click (reportado pelas plataformas)
2. Multi-touch (MTA) - Shapley, Markov, etc.
3. Media Mix Modeling (MMM)
4. Incrementality (holdout tests)
5. Conversion Modeling (iOS 14.5+)

Triangula resultados para visão unificada.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum
import numpy as np
from collections import defaultdict

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_attribution_orchestrator')

# =============================================================================
# TYPES
# =============================================================================

class AttributionMethod(Enum):
    LAST_CLICK = "last_click"
    FIRST_CLICK = "first_click"
    LINEAR = "linear"
    TIME_DECAY = "time_decay"
    POSITION_BASED = "position_based"
    SHAPLEY = "shapley"
    MARKOV = "markov"
    MMM = "media_mix_model"
    INCREMENTALITY = "incrementality"
    UNIFIED = "unified"


class Channel(Enum):
    META_PAID = "meta_paid"
    GOOGLE_PAID = "google_paid"
    TIKTOK_PAID = "tiktok_paid"
    ORGANIC_SEARCH = "organic_search"
    ORGANIC_SOCIAL = "organic_social"
    DIRECT = "direct"
    EMAIL = "email"
    REFERRAL = "referral"
    AFFILIATE = "affiliate"


@dataclass
class TouchPoint:
    """Ponto de contato na jornada"""
    channel: Channel
    timestamp: datetime
    
    # Attribution IDs
    campaign_id: Optional[str] = None
    ad_set_id: Optional[str] = None
    ad_id: Optional[str] = None
    
    # Context
    device_type: str = ""
    source: str = ""
    medium: str = ""
    
    # Cost (if paid)
    cost: float = 0
    
    # Engagement
    engagement_score: float = 0


@dataclass
class Conversion:
    """Evento de conversão"""
    conversion_id: str
    user_id: str
    timestamp: datetime
    
    value: float = 0
    conversion_type: str = "purchase"
    
    # Journey
    touch_points: List[TouchPoint] = field(default_factory=list)
    
    # Platform reported
    platform_attributed_channel: Optional[Channel] = None


@dataclass
class ChannelAttribution:
    """Atribuição por canal"""
    channel: Channel
    
    # Por método
    last_click_conversions: float = 0
    first_click_conversions: float = 0
    linear_conversions: float = 0
    shapley_conversions: float = 0
    markov_conversions: float = 0
    mmm_conversions: float = 0
    incrementality_conversions: float = 0
    
    # Unified (triangulated)
    unified_conversions: float = 0
    unified_revenue: float = 0
    
    # Confidence
    confidence: float = 0
    data_quality: float = 0


@dataclass
class AttributionReport:
    """Relatório de atribuição"""
    report_id: str
    date_range: Tuple[datetime, datetime]
    
    # Totals
    total_conversions: int
    total_revenue: float
    total_spend: float
    
    # By channel
    channel_attribution: Dict[Channel, ChannelAttribution] = field(default_factory=dict)
    
    # By method
    method_comparison: Dict[AttributionMethod, Dict[Channel, float]] = field(default_factory=dict)
    
    # Insights
    insights: List[str] = field(default_factory=list)
    
    # Metadata
    generated_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# MTA CALCULATOR
# =============================================================================

class MTACalculator:
    """Calcula atribuição Multi-Touch"""
    
    def calculate_last_click(
        self,
        conversions: List[Conversion]
    ) -> Dict[Channel, float]:
        """Last-click attribution"""
        attribution = defaultdict(float)
        
        for conv in conversions:
            if conv.touch_points:
                last_touch = conv.touch_points[-1]
                attribution[last_touch.channel] += conv.value
        
        return dict(attribution)
    
    def calculate_first_click(
        self,
        conversions: List[Conversion]
    ) -> Dict[Channel, float]:
        """First-click attribution"""
        attribution = defaultdict(float)
        
        for conv in conversions:
            if conv.touch_points:
                first_touch = conv.touch_points[0]
                attribution[first_touch.channel] += conv.value
        
        return dict(attribution)
    
    def calculate_linear(
        self,
        conversions: List[Conversion]
    ) -> Dict[Channel, float]:
        """Linear attribution"""
        attribution = defaultdict(float)
        
        for conv in conversions:
            n = len(conv.touch_points)
            if n > 0:
                credit = conv.value / n
                for touch in conv.touch_points:
                    attribution[touch.channel] += credit
        
        return dict(attribution)
    
    def calculate_time_decay(
        self,
        conversions: List[Conversion],
        half_life_days: float = 7
    ) -> Dict[Channel, float]:
        """Time-decay attribution"""
        attribution = defaultdict(float)
        
        for conv in conversions:
            if not conv.touch_points:
                continue
            
            # Calculate weights based on time decay
            weights = []
            for touch in conv.touch_points:
                days_before = (conv.timestamp - touch.timestamp).days
                weight = np.exp(-days_before * np.log(2) / half_life_days)
                weights.append(weight)
            
            total_weight = sum(weights)
            
            if total_weight > 0:
                for touch, weight in zip(conv.touch_points, weights):
                    credit = conv.value * weight / total_weight
                    attribution[touch.channel] += credit
        
        return dict(attribution)
    
    def calculate_position_based(
        self,
        conversions: List[Conversion],
        first_weight: float = 0.4,
        last_weight: float = 0.4
    ) -> Dict[Channel, float]:
        """Position-based (U-shaped) attribution"""
        attribution = defaultdict(float)
        middle_weight = 1 - first_weight - last_weight
        
        for conv in conversions:
            n = len(conv.touch_points)
            
            if n == 0:
                continue
            elif n == 1:
                attribution[conv.touch_points[0].channel] += conv.value
            elif n == 2:
                attribution[conv.touch_points[0].channel] += conv.value * 0.5
                attribution[conv.touch_points[1].channel] += conv.value * 0.5
            else:
                # First touch
                attribution[conv.touch_points[0].channel] += conv.value * first_weight
                # Last touch
                attribution[conv.touch_points[-1].channel] += conv.value * last_weight
                # Middle touches
                middle_credit = conv.value * middle_weight / (n - 2)
                for touch in conv.touch_points[1:-1]:
                    attribution[touch.channel] += middle_credit
        
        return dict(attribution)
    
    def calculate_shapley(
        self,
        conversions: List[Conversion],
        max_channels: int = 6
    ) -> Dict[Channel, float]:
        """Simplified Shapley value attribution"""
        attribution = defaultdict(float)
        
        # Get unique channels
        all_channels = set()
        for conv in conversions:
            for touch in conv.touch_points:
                all_channels.add(touch.channel)
        
        channels = list(all_channels)[:max_channels]
        n = len(channels)
        
        if n == 0:
            return {}
        
        # Build coalition values (simplified)
        coalition_values = defaultdict(float)
        
        for conv in conversions:
            conv_channels = set(t.channel for t in conv.touch_points)
            conv_channels = conv_channels & set(channels)
            
            if conv_channels:
                key = tuple(sorted(c.value for c in conv_channels))
                coalition_values[key] += conv.value
        
        # Approximate Shapley values
        for channel in channels:
            marginal_contributions = []
            
            for key, value in coalition_values.items():
                if channel.value in key:
                    # Contribution = value with - value without
                    without_key = tuple(c for c in key if c != channel.value)
                    value_without = coalition_values.get(without_key, 0)
                    marginal = value - value_without
                    marginal_contributions.append(marginal)
            
            if marginal_contributions:
                attribution[channel] = np.mean(marginal_contributions)
        
        # Normalize to total revenue
        total_attr = sum(attribution.values())
        total_revenue = sum(c.value for c in conversions)
        
        if total_attr > 0:
            scale = total_revenue / total_attr
            attribution = {k: v * scale for k, v in attribution.items()}
        
        return dict(attribution)


# =============================================================================
# ATTRIBUTION ORCHESTRATOR
# =============================================================================

class AttributionOrchestrator:
    """
    Orquestra múltiplos métodos de atribuição e triangula resultados.
    """
    
    def __init__(self):
        self.mta_calculator = MTACalculator()
        
        # Weights for triangulation
        self.method_weights = {
            AttributionMethod.LAST_CLICK: 0.10,
            AttributionMethod.LINEAR: 0.10,
            AttributionMethod.TIME_DECAY: 0.15,
            AttributionMethod.SHAPLEY: 0.20,
            AttributionMethod.MARKOV: 0.15,
            AttributionMethod.MMM: 0.15,
            AttributionMethod.INCREMENTALITY: 0.15
        }
    
    def calculate_all_methods(
        self,
        conversions: List[Conversion]
    ) -> Dict[AttributionMethod, Dict[Channel, float]]:
        """Calcula atribuição por todos os métodos MTA"""
        
        results = {}
        
        results[AttributionMethod.LAST_CLICK] = self.mta_calculator.calculate_last_click(conversions)
        results[AttributionMethod.FIRST_CLICK] = self.mta_calculator.calculate_first_click(conversions)
        results[AttributionMethod.LINEAR] = self.mta_calculator.calculate_linear(conversions)
        results[AttributionMethod.TIME_DECAY] = self.mta_calculator.calculate_time_decay(conversions)
        results[AttributionMethod.POSITION_BASED] = self.mta_calculator.calculate_position_based(conversions)
        results[AttributionMethod.SHAPLEY] = self.mta_calculator.calculate_shapley(conversions)
        
        return results
    
    def triangulate(
        self,
        mta_results: Dict[AttributionMethod, Dict[Channel, float]],
        mmm_results: Optional[Dict[Channel, float]] = None,
        incrementality_results: Optional[Dict[Channel, float]] = None
    ) -> Dict[Channel, float]:
        """
        Triangula resultados de múltiplos métodos.
        Retorna atribuição unificada.
        """
        all_channels = set()
        
        for method_results in mta_results.values():
            all_channels.update(method_results.keys())
        
        if mmm_results:
            all_channels.update(mmm_results.keys())
        if incrementality_results:
            all_channels.update(incrementality_results.keys())
        
        unified = {}
        
        for channel in all_channels:
            weighted_sum = 0
            weight_sum = 0
            
            # MTA methods
            for method, results in mta_results.items():
                if channel in results:
                    weight = self.method_weights.get(method, 0.1)
                    weighted_sum += results[channel] * weight
                    weight_sum += weight
            
            # MMM
            if mmm_results and channel in mmm_results:
                weight = self.method_weights[AttributionMethod.MMM]
                weighted_sum += mmm_results[channel] * weight
                weight_sum += weight
            
            # Incrementality
            if incrementality_results and channel in incrementality_results:
                weight = self.method_weights[AttributionMethod.INCREMENTALITY]
                weighted_sum += incrementality_results[channel] * weight
                weight_sum += weight
            
            if weight_sum > 0:
                unified[channel] = weighted_sum / weight_sum
            else:
                unified[channel] = 0
        
        return unified
    
    def generate_report(
        self,
        conversions: List[Conversion],
        spend_by_channel: Dict[Channel, float],
        mmm_results: Optional[Dict[Channel, float]] = None,
        incrementality_results: Optional[Dict[Channel, float]] = None,
        date_range: Tuple[datetime, datetime] = None
    ) -> AttributionReport:
        """Gera relatório completo de atribuição"""
        
        # Calculate MTA
        mta_results = self.calculate_all_methods(conversions)
        
        # Triangulate
        unified = self.triangulate(mta_results, mmm_results, incrementality_results)
        
        # Build channel attribution
        channel_attribution = {}
        
        for channel in set(unified.keys()) | set(spend_by_channel.keys()):
            attr = ChannelAttribution(channel=channel)
            
            attr.last_click_conversions = mta_results.get(AttributionMethod.LAST_CLICK, {}).get(channel, 0)
            attr.linear_conversions = mta_results.get(AttributionMethod.LINEAR, {}).get(channel, 0)
            attr.shapley_conversions = mta_results.get(AttributionMethod.SHAPLEY, {}).get(channel, 0)
            
            if mmm_results:
                attr.mmm_conversions = mmm_results.get(channel, 0)
            if incrementality_results:
                attr.incrementality_conversions = incrementality_results.get(channel, 0)
            
            attr.unified_conversions = unified.get(channel, 0)
            
            # Calculate revenue (assume conversions = revenue for simplicity)
            attr.unified_revenue = attr.unified_conversions
            
            # Confidence based on data availability
            methods_with_data = sum([
                1 if attr.last_click_conversions > 0 else 0,
                1 if attr.linear_conversions > 0 else 0,
                1 if attr.shapley_conversions > 0 else 0,
                1 if attr.mmm_conversions > 0 else 0,
                1 if attr.incrementality_conversions > 0 else 0
            ])
            attr.confidence = min(1.0, methods_with_data / 5)
            
            channel_attribution[channel] = attr
        
        # Generate insights
        insights = self._generate_insights(channel_attribution, spend_by_channel, mta_results)
        
        # Calculate totals
        total_conversions = len(conversions)
        total_revenue = sum(c.value for c in conversions)
        total_spend = sum(spend_by_channel.values())
        
        if date_range is None:
            date_range = (datetime.now() - timedelta(days=30), datetime.now())
        
        return AttributionReport(
            report_id=f"attr_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
            date_range=date_range,
            total_conversions=total_conversions,
            total_revenue=total_revenue,
            total_spend=total_spend,
            channel_attribution=channel_attribution,
            method_comparison=mta_results,
            insights=insights
        )
    
    def _generate_insights(
        self,
        channel_attribution: Dict[Channel, ChannelAttribution],
        spend_by_channel: Dict[Channel, float],
        mta_results: Dict
    ) -> List[str]:
        """Gera insights automáticos"""
        insights = []
        
        # Find discrepancies between methods
        for channel, attr in channel_attribution.items():
            if attr.last_click_conversions > 0:
                ratio = attr.unified_conversions / attr.last_click_conversions
                
                if ratio < 0.7:
                    insights.append(
                        f"{channel.value}: Last-click superestima em {((1-ratio)*100):.0f}%. "
                        f"Considere reduzir budget."
                    )
                elif ratio > 1.3:
                    insights.append(
                        f"{channel.value}: Last-click subestima em {((ratio-1)*100):.0f}%. "
                        f"Assistência significativa no funil."
                    )
        
        # ROI analysis
        for channel, attr in channel_attribution.items():
            spend = spend_by_channel.get(channel, 0)
            if spend > 0:
                roi = attr.unified_revenue / spend
                
                if roi < 1:
                    insights.append(
                        f"{channel.value}: ROI unificado de {roi:.2f}x. "
                        f"Considere otimização ou redução."
                    )
                elif roi > 5:
                    insights.append(
                        f"{channel.value}: ROI excelente de {roi:.2f}x. "
                        f"Considere aumentar investimento."
                    )
        
        return insights


# =============================================================================
# BUDGET OPTIMIZER
# =============================================================================

class BudgetOptimizer:
    """
    Otimiza alocação de budget baseado na atribuição unificada.
    """
    
    def __init__(self, orchestrator: AttributionOrchestrator):
        self.orchestrator = orchestrator
    
    def optimize_allocation(
        self,
        current_spend: Dict[Channel, float],
        unified_attribution: Dict[Channel, float],
        total_budget: float,
        constraints: Dict[Channel, Tuple[float, float]] = None
    ) -> Dict[Channel, float]:
        """
        Sugere nova alocação de budget.
        
        constraints: Dict de channel -> (min_spend, max_spend)
        """
        # Calculate ROI by channel
        roi_by_channel = {}
        
        for channel, revenue in unified_attribution.items():
            spend = current_spend.get(channel, 1)
            roi_by_channel[channel] = revenue / max(1, spend)
        
        # Sort by ROI
        sorted_channels = sorted(
            roi_by_channel.items(),
            key=lambda x: x[1],
            reverse=True
        )
        
        # Allocate budget based on ROI
        optimal_allocation = {}
        remaining_budget = total_budget
        
        for channel, roi in sorted_channels:
            if constraints and channel in constraints:
                min_spend, max_spend = constraints[channel]
            else:
                min_spend = 0
                max_spend = total_budget * 0.5  # Max 50% in single channel
            
            # Allocate proportional to ROI
            if roi > 1:  # Only invest if ROI > 1
                ideal_spend = current_spend.get(channel, 0) * min(2, roi / 2)
                actual_spend = max(min_spend, min(max_spend, ideal_spend, remaining_budget))
            else:
                actual_spend = min_spend
            
            optimal_allocation[channel] = actual_spend
            remaining_budget -= actual_spend
        
        # Distribute remaining budget to top performers
        if remaining_budget > 0:
            top_channel = sorted_channels[0][0] if sorted_channels else None
            if top_channel:
                optimal_allocation[top_channel] += remaining_budget
        
        return optimal_allocation
    
    def calculate_expected_lift(
        self,
        current_spend: Dict[Channel, float],
        optimal_spend: Dict[Channel, float],
        unified_attribution: Dict[Channel, float]
    ) -> Dict[str, Any]:
        """
        Calcula lift esperado da nova alocação.
        """
        current_revenue = sum(unified_attribution.values())
        current_total_spend = sum(current_spend.values())
        
        # Estimate new revenue
        estimated_revenue = 0
        
        for channel, new_spend in optimal_spend.items():
            old_spend = current_spend.get(channel, 0)
            old_revenue = unified_attribution.get(channel, 0)
            
            if old_spend > 0:
                roi = old_revenue / old_spend
                # Diminishing returns
                efficiency = 1 - 0.1 * np.log1p(new_spend / old_spend - 1)
                efficiency = max(0.5, min(1.0, efficiency))
                new_revenue = new_spend * roi * efficiency
            else:
                new_revenue = 0
            
            estimated_revenue += new_revenue
        
        new_total_spend = sum(optimal_spend.values())
        
        return {
            'current_revenue': current_revenue,
            'estimated_revenue': estimated_revenue,
            'revenue_lift': estimated_revenue - current_revenue,
            'revenue_lift_pct': (estimated_revenue / current_revenue - 1) * 100 if current_revenue > 0 else 0,
            'current_roas': current_revenue / current_total_spend if current_total_spend > 0 else 0,
            'estimated_roas': estimated_revenue / new_total_spend if new_total_spend > 0 else 0,
            'budget_change': new_total_spend - current_total_spend
        }


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'AttributionMethod',
    'Channel',
    'TouchPoint',
    'Conversion',
    'ChannelAttribution',
    'AttributionReport',
    'MTACalculator',
    'AttributionOrchestrator',
    'BudgetOptimizer'
]
