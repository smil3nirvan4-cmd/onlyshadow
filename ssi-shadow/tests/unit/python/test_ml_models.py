"""
S.S.I. SHADOW - ML Models Tests
Tests for LTV prediction, churn detection, and propensity scoring
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch
from dataclasses import dataclass


# =============================================================================
# TYPES
# =============================================================================

@dataclass
class UserFeatures:
    """User features for ML models"""
    user_id: str
    total_purchases: int
    total_revenue: float
    avg_order_value: float
    days_since_first_purchase: int
    days_since_last_purchase: int
    purchase_frequency: float
    view_to_cart_rate: float
    cart_to_purchase_rate: float
    total_sessions: int
    avg_session_duration: float
    avg_scroll_depth: float
    avg_time_on_page: float
    device_type: str
    returning_user: bool


@dataclass
class LTVPrediction:
    """LTV prediction result"""
    user_id: str
    predicted_ltv_90d: float
    ltv_tier: str
    ltv_percentile: int
    confidence: float


@dataclass
class ChurnPrediction:
    """Churn prediction result"""
    user_id: str
    churn_probability: float
    churn_risk: str
    days_to_churn: int
    confidence: float


@dataclass
class PropensityPrediction:
    """Propensity prediction result"""
    user_id: str
    propensity_7d: float
    propensity_tier: str
    confidence: float


# =============================================================================
# FEATURE ENGINEERING
# =============================================================================

class FeatureEngineer:
    """Feature engineering for ML models"""
    
    @staticmethod
    def compute_recency_score(days_since_last: int) -> float:
        """Compute recency score (0-1, higher is more recent)"""
        if days_since_last <= 0:
            return 1.0
        elif days_since_last <= 7:
            return 0.9
        elif days_since_last <= 14:
            return 0.7
        elif days_since_last <= 30:
            return 0.5
        elif days_since_last <= 60:
            return 0.3
        elif days_since_last <= 90:
            return 0.1
        else:
            return 0.0
    
    @staticmethod
    def compute_frequency_score(purchase_count: int, days_active: int) -> float:
        """Compute frequency score based on purchase rate"""
        if days_active <= 0:
            return 0.0
        
        purchases_per_month = (purchase_count / days_active) * 30
        
        if purchases_per_month >= 4:
            return 1.0
        elif purchases_per_month >= 2:
            return 0.8
        elif purchases_per_month >= 1:
            return 0.6
        elif purchases_per_month >= 0.5:
            return 0.4
        elif purchases_per_month > 0:
            return 0.2
        else:
            return 0.0
    
    @staticmethod
    def compute_monetary_score(total_revenue: float, avg_revenue: float = 500.0) -> float:
        """Compute monetary score relative to average"""
        if total_revenue <= 0:
            return 0.0
        
        ratio = total_revenue / avg_revenue
        
        if ratio >= 5:
            return 1.0
        elif ratio >= 2:
            return 0.8
        elif ratio >= 1:
            return 0.6
        elif ratio >= 0.5:
            return 0.4
        elif ratio > 0:
            return 0.2
        else:
            return 0.0
    
    @staticmethod
    def compute_engagement_score(
        avg_session_duration: float,
        avg_scroll_depth: float,
        sessions_count: int
    ) -> float:
        """Compute engagement score from behavioral data"""
        # Duration score (max at 5 minutes)
        duration_score = min(avg_session_duration / 300, 1.0)
        
        # Scroll score (already 0-100)
        scroll_score = avg_scroll_depth / 100
        
        # Sessions score (max at 10 sessions)
        sessions_score = min(sessions_count / 10, 1.0)
        
        # Weighted average
        return (duration_score * 0.4 + scroll_score * 0.3 + sessions_score * 0.3)
    
    @staticmethod
    def compute_rfm_score(
        recency_score: float,
        frequency_score: float,
        monetary_score: float
    ) -> float:
        """Compute combined RFM score"""
        return (recency_score * 0.35 + frequency_score * 0.35 + monetary_score * 0.30)


# =============================================================================
# LTV MODEL
# =============================================================================

class LTVModel:
    """Simple LTV prediction model"""
    
    LTV_TIERS = {
        'VIP': (0.9, float('inf')),      # Top 10%
        'High': (0.7, 0.9),               # 70-90%
        'Medium': (0.4, 0.7),             # 40-70%
        'Low': (0.0, 0.4),                # Bottom 40%
    }
    
    def predict(self, features: UserFeatures) -> LTVPrediction:
        """Predict LTV for user"""
        # Compute component scores
        recency = FeatureEngineer.compute_recency_score(features.days_since_last_purchase)
        frequency = FeatureEngineer.compute_frequency_score(
            features.total_purchases,
            features.days_since_first_purchase
        )
        monetary = FeatureEngineer.compute_monetary_score(features.total_revenue)
        engagement = FeatureEngineer.compute_engagement_score(
            features.avg_session_duration,
            features.avg_scroll_depth,
            features.total_sessions
        )
        
        # Combine scores
        rfm_score = FeatureEngineer.compute_rfm_score(recency, frequency, monetary)
        combined_score = rfm_score * 0.7 + engagement * 0.3
        
        # Predict LTV based on score and historical revenue
        base_ltv = features.total_revenue * (90 / max(features.days_since_first_purchase, 30))
        predicted_ltv = base_ltv * (0.5 + combined_score)
        
        # Determine tier
        tier = self._get_tier(combined_score)
        percentile = int(combined_score * 100)
        
        # Confidence based on data completeness
        confidence = self._calculate_confidence(features)
        
        return LTVPrediction(
            user_id=features.user_id,
            predicted_ltv_90d=round(predicted_ltv, 2),
            ltv_tier=tier,
            ltv_percentile=percentile,
            confidence=confidence
        )
    
    def _get_tier(self, score: float) -> str:
        """Get LTV tier from score"""
        for tier, (low, high) in self.LTV_TIERS.items():
            if low <= score < high:
                return tier
        return 'Low'
    
    def _calculate_confidence(self, features: UserFeatures) -> float:
        """Calculate prediction confidence"""
        data_points = sum([
            1 if features.total_purchases > 0 else 0,
            1 if features.total_sessions > 3 else 0,
            1 if features.days_since_first_purchase > 14 else 0,
            1 if features.avg_session_duration > 0 else 0,
        ])
        return min(data_points / 4 * 0.9 + 0.1, 1.0)


# =============================================================================
# CHURN MODEL
# =============================================================================

class ChurnModel:
    """Simple churn prediction model"""
    
    CHURN_RISKS = {
        'Critical': (0.8, 1.0),
        'High': (0.6, 0.8),
        'Medium': (0.4, 0.6),
        'Low': (0.0, 0.4),
    }
    
    def predict(self, features: UserFeatures) -> ChurnPrediction:
        """Predict churn probability for user"""
        # Recency is key indicator (inverse - longer = higher churn)
        recency_score = FeatureEngineer.compute_recency_score(features.days_since_last_purchase)
        churn_from_recency = 1 - recency_score
        
        # Frequency indicator
        frequency_score = FeatureEngineer.compute_frequency_score(
            features.total_purchases,
            features.days_since_first_purchase
        )
        churn_from_frequency = 1 - frequency_score
        
        # Engagement indicator
        engagement_score = FeatureEngineer.compute_engagement_score(
            features.avg_session_duration,
            features.avg_scroll_depth,
            features.total_sessions
        )
        churn_from_engagement = 1 - engagement_score
        
        # Combined churn probability
        churn_probability = (
            churn_from_recency * 0.5 +
            churn_from_frequency * 0.3 +
            churn_from_engagement * 0.2
        )
        
        # Adjust for valuable customers (they're more at risk if showing signs)
        if features.total_revenue > 500 and churn_probability > 0.5:
            churn_probability = min(churn_probability * 1.1, 1.0)
        
        # Get risk level
        risk = self._get_risk_level(churn_probability)
        
        # Estimate days to churn
        days_to_churn = self._estimate_days_to_churn(churn_probability, features)
        
        # Confidence
        confidence = self._calculate_confidence(features)
        
        return ChurnPrediction(
            user_id=features.user_id,
            churn_probability=round(churn_probability, 3),
            churn_risk=risk,
            days_to_churn=days_to_churn,
            confidence=confidence
        )
    
    def _get_risk_level(self, probability: float) -> str:
        """Get churn risk level from probability"""
        for risk, (low, high) in self.CHURN_RISKS.items():
            if low <= probability < high:
                return risk
        return 'Low'
    
    def _estimate_days_to_churn(self, probability: float, features: UserFeatures) -> int:
        """Estimate days until likely churn"""
        if probability < 0.3:
            return 90
        elif probability < 0.5:
            return 60
        elif probability < 0.7:
            return 30
        elif probability < 0.85:
            return 14
        else:
            return 7
    
    def _calculate_confidence(self, features: UserFeatures) -> float:
        """Calculate prediction confidence"""
        data_points = sum([
            1 if features.total_purchases > 0 else 0,
            1 if features.days_since_first_purchase > 30 else 0,
            1 if features.total_sessions > 5 else 0,
        ])
        return min(data_points / 3 * 0.85 + 0.15, 1.0)


# =============================================================================
# PROPENSITY MODEL
# =============================================================================

class PropensityModel:
    """Simple purchase propensity model"""
    
    PROPENSITY_TIERS = {
        'Very High': (0.7, 1.0),
        'High': (0.5, 0.7),
        'Medium': (0.3, 0.5),
        'Low': (0.0, 0.3),
    }
    
    def predict(self, features: UserFeatures) -> PropensityPrediction:
        """Predict purchase propensity for next 7 days"""
        # Recency is strong indicator
        recency_score = FeatureEngineer.compute_recency_score(features.days_since_last_purchase)
        
        # Past conversion behavior
        conversion_score = (
            features.view_to_cart_rate * 0.4 +
            features.cart_to_purchase_rate * 0.6
        )
        
        # Engagement signals
        engagement_score = FeatureEngineer.compute_engagement_score(
            features.avg_session_duration,
            features.avg_scroll_depth,
            features.total_sessions
        )
        
        # Frequency (repeat buyers more likely)
        frequency_score = FeatureEngineer.compute_frequency_score(
            features.total_purchases,
            features.days_since_first_purchase
        )
        
        # Combined propensity
        propensity = (
            recency_score * 0.35 +
            conversion_score * 0.30 +
            engagement_score * 0.20 +
            frequency_score * 0.15
        )
        
        # Boost for returning users
        if features.returning_user and features.total_purchases > 0:
            propensity = min(propensity * 1.15, 1.0)
        
        # Get tier
        tier = self._get_tier(propensity)
        
        # Confidence
        confidence = self._calculate_confidence(features)
        
        return PropensityPrediction(
            user_id=features.user_id,
            propensity_7d=round(propensity, 3),
            propensity_tier=tier,
            confidence=confidence
        )
    
    def _get_tier(self, propensity: float) -> str:
        """Get propensity tier"""
        for tier, (low, high) in self.PROPENSITY_TIERS.items():
            if low <= propensity < high:
                return tier
        return 'Low'
    
    def _calculate_confidence(self, features: UserFeatures) -> float:
        """Calculate prediction confidence"""
        data_points = sum([
            1 if features.total_sessions > 0 else 0,
            1 if features.avg_scroll_depth > 0 else 0,
            1 if features.total_purchases > 0 else 0,
        ])
        return min(data_points / 3 * 0.8 + 0.2, 1.0)


# =============================================================================
# TESTS
# =============================================================================

class TestFeatureEngineer:
    """Tests for feature engineering functions"""
    
    # -------------------------------------------------------------------------
    # Recency Score Tests
    # -------------------------------------------------------------------------
    
    def test_recency_score_today(self):
        """Should return 1.0 for purchase today"""
        assert FeatureEngineer.compute_recency_score(0) == 1.0
    
    def test_recency_score_last_week(self):
        """Should return high score for recent purchase"""
        score = FeatureEngineer.compute_recency_score(5)
        assert score == 0.9
    
    def test_recency_score_two_weeks(self):
        """Should return medium-high score for 2 weeks"""
        score = FeatureEngineer.compute_recency_score(10)
        assert score == 0.7
    
    def test_recency_score_month(self):
        """Should return medium score for month ago"""
        score = FeatureEngineer.compute_recency_score(25)
        assert score == 0.5
    
    def test_recency_score_old(self):
        """Should return low score for old purchase"""
        score = FeatureEngineer.compute_recency_score(100)
        assert score == 0.0
    
    # -------------------------------------------------------------------------
    # Frequency Score Tests
    # -------------------------------------------------------------------------
    
    def test_frequency_score_high(self):
        """Should return high score for frequent buyer"""
        # 10 purchases in 60 days = ~5/month
        score = FeatureEngineer.compute_frequency_score(10, 60)
        assert score == 1.0
    
    def test_frequency_score_medium(self):
        """Should return medium score for occasional buyer"""
        # 2 purchases in 60 days = 1/month
        score = FeatureEngineer.compute_frequency_score(2, 60)
        assert score == 0.6
    
    def test_frequency_score_low(self):
        """Should return low score for rare buyer"""
        # 1 purchase in 90 days = 0.33/month
        score = FeatureEngineer.compute_frequency_score(1, 90)
        assert score == 0.2
    
    def test_frequency_score_zero_days(self):
        """Should handle zero days active"""
        score = FeatureEngineer.compute_frequency_score(5, 0)
        assert score == 0.0
    
    def test_frequency_score_no_purchases(self):
        """Should return 0 for no purchases"""
        score = FeatureEngineer.compute_frequency_score(0, 30)
        assert score == 0.0
    
    # -------------------------------------------------------------------------
    # Monetary Score Tests
    # -------------------------------------------------------------------------
    
    def test_monetary_score_vip(self):
        """Should return high score for VIP spender"""
        score = FeatureEngineer.compute_monetary_score(3000, 500)
        assert score == 1.0  # 6x average
    
    def test_monetary_score_above_average(self):
        """Should return good score for above average"""
        score = FeatureEngineer.compute_monetary_score(750, 500)
        assert score == 0.8  # 1.5x average
    
    def test_monetary_score_average(self):
        """Should return medium score for average"""
        score = FeatureEngineer.compute_monetary_score(500, 500)
        assert score == 0.6  # 1x average
    
    def test_monetary_score_below_average(self):
        """Should return low score for below average"""
        score = FeatureEngineer.compute_monetary_score(200, 500)
        assert score == 0.4  # 0.4x average
    
    def test_monetary_score_zero(self):
        """Should return 0 for no revenue"""
        score = FeatureEngineer.compute_monetary_score(0, 500)
        assert score == 0.0
    
    # -------------------------------------------------------------------------
    # Engagement Score Tests
    # -------------------------------------------------------------------------
    
    def test_engagement_score_high(self):
        """Should return high score for engaged user"""
        score = FeatureEngineer.compute_engagement_score(
            avg_session_duration=300,  # 5 minutes
            avg_scroll_depth=80,
            sessions_count=15
        )
        assert score > 0.8
    
    def test_engagement_score_medium(self):
        """Should return medium score for average engagement"""
        score = FeatureEngineer.compute_engagement_score(
            avg_session_duration=120,  # 2 minutes
            avg_scroll_depth=50,
            sessions_count=5
        )
        assert 0.4 < score < 0.7
    
    def test_engagement_score_low(self):
        """Should return low score for low engagement"""
        score = FeatureEngineer.compute_engagement_score(
            avg_session_duration=30,
            avg_scroll_depth=20,
            sessions_count=2
        )
        assert score < 0.4
    
    def test_engagement_score_caps_at_one(self):
        """Should not exceed 1.0"""
        score = FeatureEngineer.compute_engagement_score(
            avg_session_duration=1000,
            avg_scroll_depth=100,
            sessions_count=100
        )
        assert score <= 1.0
    
    # -------------------------------------------------------------------------
    # RFM Score Tests
    # -------------------------------------------------------------------------
    
    def test_rfm_score_perfect(self):
        """Should return high RFM for perfect scores"""
        score = FeatureEngineer.compute_rfm_score(1.0, 1.0, 1.0)
        assert score == 1.0
    
    def test_rfm_score_zero(self):
        """Should return 0 for zero scores"""
        score = FeatureEngineer.compute_rfm_score(0, 0, 0)
        assert score == 0.0
    
    def test_rfm_score_weighted(self):
        """Should apply correct weights"""
        # R=1, F=0, M=0 should give 0.35
        score = FeatureEngineer.compute_rfm_score(1.0, 0, 0)
        assert score == 0.35


class TestLTVModel:
    """Tests for LTV prediction model"""
    
    @pytest.fixture
    def model(self):
        return LTVModel()
    
    @pytest.fixture
    def vip_user(self):
        return UserFeatures(
            user_id='vip_001',
            total_purchases=15,
            total_revenue=5000.0,
            avg_order_value=333.33,
            days_since_first_purchase=180,
            days_since_last_purchase=3,
            purchase_frequency=2.5,
            view_to_cart_rate=0.25,
            cart_to_purchase_rate=0.60,
            total_sessions=50,
            avg_session_duration=240,
            avg_scroll_depth=75,
            avg_time_on_page=180,
            device_type='desktop',
            returning_user=True
        )
    
    @pytest.fixture
    def new_user(self):
        return UserFeatures(
            user_id='new_001',
            total_purchases=0,
            total_revenue=0,
            avg_order_value=0,
            days_since_first_purchase=7,
            days_since_last_purchase=7,
            purchase_frequency=0,
            view_to_cart_rate=0.10,
            cart_to_purchase_rate=0,
            total_sessions=3,
            avg_session_duration=60,
            avg_scroll_depth=40,
            avg_time_on_page=45,
            device_type='mobile',
            returning_user=False
        )
    
    def test_predict_vip_user(self, model, vip_user):
        """Should predict high LTV for VIP user"""
        prediction = model.predict(vip_user)
        
        assert prediction.ltv_tier in ['VIP', 'High']
        assert prediction.ltv_percentile >= 70
        assert prediction.confidence > 0.7
    
    def test_predict_new_user(self, model, new_user):
        """Should predict low LTV for new user with no purchases"""
        prediction = model.predict(new_user)
        
        assert prediction.ltv_tier in ['Low', 'Medium']
        assert prediction.ltv_percentile < 50
        assert prediction.confidence < 0.5  # Low confidence for new user
    
    def test_prediction_structure(self, model, vip_user):
        """Should return complete prediction structure"""
        prediction = model.predict(vip_user)
        
        assert prediction.user_id == 'vip_001'
        assert isinstance(prediction.predicted_ltv_90d, float)
        assert prediction.ltv_tier in ['VIP', 'High', 'Medium', 'Low']
        assert 0 <= prediction.ltv_percentile <= 100
        assert 0 <= prediction.confidence <= 1


class TestChurnModel:
    """Tests for churn prediction model"""
    
    @pytest.fixture
    def model(self):
        return ChurnModel()
    
    @pytest.fixture
    def loyal_user(self):
        return UserFeatures(
            user_id='loyal_001',
            total_purchases=10,
            total_revenue=2000.0,
            avg_order_value=200.0,
            days_since_first_purchase=120,
            days_since_last_purchase=5,  # Recent
            purchase_frequency=2.5,
            view_to_cart_rate=0.20,
            cart_to_purchase_rate=0.50,
            total_sessions=30,
            avg_session_duration=180,
            avg_scroll_depth=60,
            avg_time_on_page=120,
            device_type='desktop',
            returning_user=True
        )
    
    @pytest.fixture
    def churning_user(self):
        return UserFeatures(
            user_id='churning_001',
            total_purchases=3,
            total_revenue=600.0,
            avg_order_value=200.0,
            days_since_first_purchase=90,
            days_since_last_purchase=60,  # Long time ago
            purchase_frequency=1.0,
            view_to_cart_rate=0.05,
            cart_to_purchase_rate=0.20,
            total_sessions=5,
            avg_session_duration=45,
            avg_scroll_depth=25,
            avg_time_on_page=30,
            device_type='mobile',
            returning_user=True
        )
    
    def test_predict_loyal_user(self, model, loyal_user):
        """Should predict low churn for loyal user"""
        prediction = model.predict(loyal_user)
        
        assert prediction.churn_risk in ['Low', 'Medium']
        assert prediction.churn_probability < 0.5
        assert prediction.days_to_churn >= 30
    
    def test_predict_churning_user(self, model, churning_user):
        """Should predict high churn for inactive user"""
        prediction = model.predict(churning_user)
        
        assert prediction.churn_risk in ['High', 'Critical']
        assert prediction.churn_probability >= 0.5
        assert prediction.days_to_churn <= 30
    
    def test_prediction_structure(self, model, loyal_user):
        """Should return complete prediction structure"""
        prediction = model.predict(loyal_user)
        
        assert prediction.user_id == 'loyal_001'
        assert 0 <= prediction.churn_probability <= 1
        assert prediction.churn_risk in ['Critical', 'High', 'Medium', 'Low']
        assert prediction.days_to_churn > 0
        assert 0 <= prediction.confidence <= 1


class TestPropensityModel:
    """Tests for purchase propensity model"""
    
    @pytest.fixture
    def model(self):
        return PropensityModel()
    
    @pytest.fixture
    def hot_lead(self):
        return UserFeatures(
            user_id='hot_001',
            total_purchases=2,
            total_revenue=400.0,
            avg_order_value=200.0,
            days_since_first_purchase=30,
            days_since_last_purchase=2,  # Just bought
            purchase_frequency=2.0,
            view_to_cart_rate=0.30,
            cart_to_purchase_rate=0.70,
            total_sessions=15,
            avg_session_duration=200,
            avg_scroll_depth=80,
            avg_time_on_page=150,
            device_type='desktop',
            returning_user=True
        )
    
    @pytest.fixture
    def cold_lead(self):
        return UserFeatures(
            user_id='cold_001',
            total_purchases=0,
            total_revenue=0,
            avg_order_value=0,
            days_since_first_purchase=30,
            days_since_last_purchase=30,
            purchase_frequency=0,
            view_to_cart_rate=0.05,
            cart_to_purchase_rate=0,
            total_sessions=2,
            avg_session_duration=30,
            avg_scroll_depth=20,
            avg_time_on_page=20,
            device_type='mobile',
            returning_user=False
        )
    
    def test_predict_hot_lead(self, model, hot_lead):
        """Should predict high propensity for engaged buyer"""
        prediction = model.predict(hot_lead)
        
        assert prediction.propensity_tier in ['Very High', 'High']
        assert prediction.propensity_7d >= 0.5
    
    def test_predict_cold_lead(self, model, cold_lead):
        """Should predict low propensity for cold lead"""
        prediction = model.predict(cold_lead)
        
        assert prediction.propensity_tier in ['Low', 'Medium']
        assert prediction.propensity_7d < 0.5
    
    def test_returning_user_boost(self, model, hot_lead, cold_lead):
        """Returning buyers should get propensity boost"""
        hot_prediction = model.predict(hot_lead)
        
        # Hot lead is returning user with purchases
        # Propensity should be boosted
        assert hot_prediction.propensity_7d > 0.5
    
    def test_prediction_structure(self, model, hot_lead):
        """Should return complete prediction structure"""
        prediction = model.predict(hot_lead)
        
        assert prediction.user_id == 'hot_001'
        assert 0 <= prediction.propensity_7d <= 1
        assert prediction.propensity_tier in ['Very High', 'High', 'Medium', 'Low']
        assert 0 <= prediction.confidence <= 1


class TestModelIntegration:
    """Integration tests for all models together"""
    
    @pytest.fixture
    def all_models(self):
        return {
            'ltv': LTVModel(),
            'churn': ChurnModel(),
            'propensity': PropensityModel()
        }
    
    @pytest.fixture
    def sample_user(self):
        return UserFeatures(
            user_id='sample_001',
            total_purchases=5,
            total_revenue=1000.0,
            avg_order_value=200.0,
            days_since_first_purchase=60,
            days_since_last_purchase=10,
            purchase_frequency=2.5,
            view_to_cart_rate=0.15,
            cart_to_purchase_rate=0.40,
            total_sessions=20,
            avg_session_duration=120,
            avg_scroll_depth=55,
            avg_time_on_page=90,
            device_type='desktop',
            returning_user=True
        )
    
    def test_all_models_produce_predictions(self, all_models, sample_user):
        """All models should produce valid predictions"""
        ltv_pred = all_models['ltv'].predict(sample_user)
        churn_pred = all_models['churn'].predict(sample_user)
        propensity_pred = all_models['propensity'].predict(sample_user)
        
        assert ltv_pred.user_id == sample_user.user_id
        assert churn_pred.user_id == sample_user.user_id
        assert propensity_pred.user_id == sample_user.user_id
    
    def test_predictions_are_consistent(self, all_models, sample_user):
        """High LTV + Low Churn should correlate with High Propensity"""
        ltv_pred = all_models['ltv'].predict(sample_user)
        churn_pred = all_models['churn'].predict(sample_user)
        propensity_pred = all_models['propensity'].predict(sample_user)
        
        # Good user metrics should be somewhat consistent
        if ltv_pred.ltv_percentile > 60 and churn_pred.churn_probability < 0.4:
            # High value, low churn user should have decent propensity
            assert propensity_pred.propensity_7d > 0.3
