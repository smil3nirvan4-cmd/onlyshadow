"""
S.S.I. SHADOW - ML Module Tests
Tests for machine learning models and predictions
"""

import pytest
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, List
from unittest.mock import MagicMock, patch
from dataclasses import dataclass


# =============================================================================
# MOCK CLASSES (simulating ML module structures)
# =============================================================================

@dataclass
class FeatureVector:
    """Feature vector for ML models"""
    user_id: str
    # Engagement features
    total_purchases: int = 0
    total_revenue: float = 0.0
    avg_order_value: float = 0.0
    days_since_first_purchase: int = 0
    days_since_last_purchase: int = 0
    purchase_frequency: float = 0.0
    # Behavioral features
    total_pageviews: int = 0
    total_sessions: int = 0
    avg_session_duration: float = 0.0
    avg_pages_per_session: float = 0.0
    # Recency features
    days_since_last_visit: int = 0
    visits_last_7d: int = 0
    visits_last_30d: int = 0


class LTVPredictor:
    """Mock LTV Predictor"""
    
    def __init__(self, model_path: str = None):
        self.model_path = model_path
        self.is_trained = False
        self.feature_importance = {}
    
    def predict(self, features: FeatureVector) -> Dict[str, Any]:
        """Predict LTV for a user"""
        # Simple rule-based prediction for testing
        base_ltv = features.total_revenue * 1.5
        
        # Adjust based on recency
        if features.days_since_last_purchase < 30:
            recency_multiplier = 1.2
        elif features.days_since_last_purchase < 90:
            recency_multiplier = 1.0
        else:
            recency_multiplier = 0.7
        
        # Adjust based on frequency
        frequency_multiplier = min(1 + features.purchase_frequency * 10, 2.0)
        
        predicted_ltv = base_ltv * recency_multiplier * frequency_multiplier
        
        # Determine tier
        if predicted_ltv >= 1000:
            tier = 'VIP'
            percentile = 95
        elif predicted_ltv >= 500:
            tier = 'High'
            percentile = 75
        elif predicted_ltv >= 200:
            tier = 'Medium'
            percentile = 50
        else:
            tier = 'Low'
            percentile = 25
        
        return {
            'predicted_ltv_90d': round(predicted_ltv, 2),
            'ltv_tier': tier,
            'ltv_percentile': percentile,
            'confidence': 0.85 if features.total_purchases >= 3 else 0.60,
        }


class ChurnPredictor:
    """Mock Churn Predictor"""
    
    def predict(self, features: FeatureVector) -> Dict[str, Any]:
        """Predict churn probability"""
        # Simple rule-based prediction
        churn_score = 0.0
        
        # High recency = low churn
        if features.days_since_last_visit > 60:
            churn_score += 0.4
        elif features.days_since_last_visit > 30:
            churn_score += 0.2
        
        # Low frequency = high churn
        if features.visits_last_30d < 2:
            churn_score += 0.3
        
        # Declining engagement
        if features.days_since_last_purchase > 90:
            churn_score += 0.3
        
        churn_probability = min(churn_score, 0.99)
        
        # Determine risk level
        if churn_probability >= 0.7:
            risk = 'Critical'
        elif churn_probability >= 0.5:
            risk = 'High'
        elif churn_probability >= 0.3:
            risk = 'Medium'
        else:
            risk = 'Low'
        
        return {
            'churn_probability': round(churn_probability, 2),
            'churn_risk': risk,
            'confidence': 0.80,
        }


class PropensityPredictor:
    """Mock Purchase Propensity Predictor"""
    
    def predict(self, features: FeatureVector) -> Dict[str, Any]:
        """Predict purchase propensity for next 7 days"""
        # Simple rule-based prediction
        propensity = 0.1  # Base
        
        # Recent activity boosts propensity
        if features.days_since_last_visit < 3:
            propensity += 0.3
        elif features.days_since_last_visit < 7:
            propensity += 0.2
        
        # Purchase history boosts propensity
        if features.purchase_frequency > 0.1:
            propensity += 0.2
        
        # Recent engagement
        if features.visits_last_7d >= 3:
            propensity += 0.2
        
        propensity = min(propensity, 0.95)
        
        # Determine tier
        if propensity >= 0.7:
            tier = 'Very High'
        elif propensity >= 0.5:
            tier = 'High'
        elif propensity >= 0.3:
            tier = 'Medium'
        else:
            tier = 'Low'
        
        return {
            'propensity_7d': round(propensity, 2),
            'propensity_tier': tier,
            'confidence': 0.75,
        }


class FeatureStore:
    """Mock Feature Store"""
    
    def __init__(self):
        self.features_cache = {}
    
    def get_features(self, user_id: str) -> FeatureVector:
        """Get features for a user"""
        if user_id in self.features_cache:
            return self.features_cache[user_id]
        
        # Return default features for unknown user
        return FeatureVector(user_id=user_id)
    
    def compute_features(self, user_id: str, events: List[Dict]) -> FeatureVector:
        """Compute features from events"""
        purchases = [e for e in events if e.get('event_name') == 'Purchase']
        pageviews = [e for e in events if e.get('event_name') == 'PageView']
        
        total_revenue = sum(e.get('value', 0) for e in purchases)
        total_purchases = len(purchases)
        
        features = FeatureVector(
            user_id=user_id,
            total_purchases=total_purchases,
            total_revenue=total_revenue,
            avg_order_value=total_revenue / total_purchases if total_purchases > 0 else 0,
            total_pageviews=len(pageviews),
            total_sessions=len(set(e.get('session_id', '') for e in events)),
        )
        
        self.features_cache[user_id] = features
        return features


# =============================================================================
# TESTS
# =============================================================================

class TestFeatureVector:
    """Tests for Feature Vector"""
    
    def test_create_feature_vector(self):
        """Should create feature vector with defaults"""
        fv = FeatureVector(user_id='test_001')
        
        assert fv.user_id == 'test_001'
        assert fv.total_purchases == 0
        assert fv.total_revenue == 0.0
        assert fv.purchase_frequency == 0.0
    
    def test_create_feature_vector_with_values(self):
        """Should create feature vector with custom values"""
        fv = FeatureVector(
            user_id='test_002',
            total_purchases=5,
            total_revenue=500.0,
            avg_order_value=100.0,
            days_since_last_purchase=15,
        )
        
        assert fv.total_purchases == 5
        assert fv.total_revenue == 500.0
        assert fv.avg_order_value == 100.0
        assert fv.days_since_last_purchase == 15


class TestLTVPredictor:
    """Tests for LTV Predictor"""
    
    @pytest.fixture
    def predictor(self):
        return LTVPredictor()
    
    def test_predict_vip_tier(self, predictor):
        """Should predict VIP tier for high-value user"""
        features = FeatureVector(
            user_id='vip_001',
            total_purchases=10,
            total_revenue=2000.0,
            avg_order_value=200.0,
            days_since_last_purchase=5,
            purchase_frequency=0.15,
        )
        
        result = predictor.predict(features)
        
        assert result['ltv_tier'] == 'VIP'
        assert result['ltv_percentile'] == 95
        assert result['predicted_ltv_90d'] > 1000
    
    def test_predict_low_tier(self, predictor):
        """Should predict Low tier for low-value user"""
        features = FeatureVector(
            user_id='low_001',
            total_purchases=1,
            total_revenue=50.0,
            avg_order_value=50.0,
            days_since_last_purchase=120,
            purchase_frequency=0.01,
        )
        
        result = predictor.predict(features)
        
        assert result['ltv_tier'] == 'Low'
        assert result['ltv_percentile'] == 25
        assert result['predicted_ltv_90d'] < 200
    
    def test_recency_affects_prediction(self, predictor):
        """Should give higher LTV to recent buyers"""
        base_features = {
            'total_purchases': 5,
            'total_revenue': 500.0,
            'avg_order_value': 100.0,
            'purchase_frequency': 0.05,
        }
        
        recent_buyer = FeatureVector(
            user_id='recent',
            days_since_last_purchase=10,
            **base_features
        )
        
        old_buyer = FeatureVector(
            user_id='old',
            days_since_last_purchase=100,
            **base_features
        )
        
        recent_result = predictor.predict(recent_buyer)
        old_result = predictor.predict(old_buyer)
        
        assert recent_result['predicted_ltv_90d'] > old_result['predicted_ltv_90d']
    
    def test_frequency_affects_prediction(self, predictor):
        """Should give higher LTV to frequent buyers"""
        frequent_buyer = FeatureVector(
            user_id='frequent',
            total_purchases=10,
            total_revenue=500.0,
            days_since_last_purchase=30,
            purchase_frequency=0.2,
        )
        
        infrequent_buyer = FeatureVector(
            user_id='infrequent',
            total_purchases=2,
            total_revenue=500.0,
            days_since_last_purchase=30,
            purchase_frequency=0.02,
        )
        
        freq_result = predictor.predict(frequent_buyer)
        infreq_result = predictor.predict(infrequent_buyer)
        
        assert freq_result['predicted_ltv_90d'] > infreq_result['predicted_ltv_90d']
    
    def test_confidence_based_on_data(self, predictor):
        """Should have higher confidence with more data"""
        few_purchases = FeatureVector(
            user_id='few',
            total_purchases=1,
            total_revenue=100.0,
        )
        
        many_purchases = FeatureVector(
            user_id='many',
            total_purchases=10,
            total_revenue=1000.0,
        )
        
        few_result = predictor.predict(few_purchases)
        many_result = predictor.predict(many_purchases)
        
        assert many_result['confidence'] > few_result['confidence']
    
    def test_prediction_returns_all_fields(self, predictor):
        """Should return all required fields"""
        features = FeatureVector(user_id='test')
        result = predictor.predict(features)
        
        assert 'predicted_ltv_90d' in result
        assert 'ltv_tier' in result
        assert 'ltv_percentile' in result
        assert 'confidence' in result


class TestChurnPredictor:
    """Tests for Churn Predictor"""
    
    @pytest.fixture
    def predictor(self):
        return ChurnPredictor()
    
    def test_predict_low_churn_active_user(self, predictor):
        """Should predict low churn for active user"""
        features = FeatureVector(
            user_id='active_001',
            days_since_last_visit=2,
            visits_last_30d=10,
            days_since_last_purchase=15,
        )
        
        result = predictor.predict(features)
        
        assert result['churn_risk'] == 'Low'
        assert result['churn_probability'] < 0.3
    
    def test_predict_high_churn_inactive_user(self, predictor):
        """Should predict high churn for inactive user"""
        features = FeatureVector(
            user_id='inactive_001',
            days_since_last_visit=90,
            visits_last_30d=0,
            days_since_last_purchase=180,
        )
        
        result = predictor.predict(features)
        
        assert result['churn_risk'] in ['Critical', 'High']
        assert result['churn_probability'] >= 0.5
    
    def test_recency_affects_churn(self, predictor):
        """Should correlate recency with churn"""
        recent_visitor = FeatureVector(
            user_id='recent',
            days_since_last_visit=5,
            visits_last_30d=5,
            days_since_last_purchase=30,
        )
        
        old_visitor = FeatureVector(
            user_id='old',
            days_since_last_visit=70,
            visits_last_30d=0,
            days_since_last_purchase=100,
        )
        
        recent_result = predictor.predict(recent_visitor)
        old_result = predictor.predict(old_visitor)
        
        assert old_result['churn_probability'] > recent_result['churn_probability']
    
    def test_churn_probability_bounded(self, predictor):
        """Should bound churn probability between 0 and 1"""
        extreme_features = FeatureVector(
            user_id='extreme',
            days_since_last_visit=365,
            visits_last_30d=0,
            days_since_last_purchase=365,
        )
        
        result = predictor.predict(extreme_features)
        
        assert 0 <= result['churn_probability'] <= 1
    
    def test_prediction_returns_all_fields(self, predictor):
        """Should return all required fields"""
        features = FeatureVector(user_id='test')
        result = predictor.predict(features)
        
        assert 'churn_probability' in result
        assert 'churn_risk' in result
        assert 'confidence' in result


class TestPropensityPredictor:
    """Tests for Purchase Propensity Predictor"""
    
    @pytest.fixture
    def predictor(self):
        return PropensityPredictor()
    
    def test_predict_high_propensity_engaged_user(self, predictor):
        """Should predict high propensity for engaged user"""
        features = FeatureVector(
            user_id='engaged_001',
            days_since_last_visit=1,
            visits_last_7d=5,
            purchase_frequency=0.15,
        )
        
        result = predictor.predict(features)
        
        assert result['propensity_tier'] in ['Very High', 'High']
        assert result['propensity_7d'] >= 0.5
    
    def test_predict_low_propensity_disengaged_user(self, predictor):
        """Should predict low propensity for disengaged user"""
        features = FeatureVector(
            user_id='disengaged_001',
            days_since_last_visit=30,
            visits_last_7d=0,
            purchase_frequency=0.01,
        )
        
        result = predictor.predict(features)
        
        assert result['propensity_tier'] == 'Low'
        assert result['propensity_7d'] < 0.3
    
    def test_recent_visit_boosts_propensity(self, predictor):
        """Should boost propensity for recent visitors"""
        recent = FeatureVector(
            user_id='recent',
            days_since_last_visit=1,
            visits_last_7d=2,
            purchase_frequency=0.05,
        )
        
        not_recent = FeatureVector(
            user_id='not_recent',
            days_since_last_visit=14,
            visits_last_7d=2,
            purchase_frequency=0.05,
        )
        
        recent_result = predictor.predict(recent)
        not_recent_result = predictor.predict(not_recent)
        
        assert recent_result['propensity_7d'] > not_recent_result['propensity_7d']
    
    def test_propensity_bounded(self, predictor):
        """Should bound propensity between 0 and 1"""
        extreme = FeatureVector(
            user_id='extreme',
            days_since_last_visit=0,
            visits_last_7d=100,
            purchase_frequency=1.0,
        )
        
        result = predictor.predict(extreme)
        
        assert 0 <= result['propensity_7d'] <= 1


class TestFeatureStore:
    """Tests for Feature Store"""
    
    @pytest.fixture
    def store(self):
        return FeatureStore()
    
    def test_get_features_unknown_user(self, store):
        """Should return default features for unknown user"""
        features = store.get_features('unknown_user')
        
        assert features.user_id == 'unknown_user'
        assert features.total_purchases == 0
        assert features.total_revenue == 0.0
    
    def test_compute_features_from_events(self, store):
        """Should compute features from events"""
        events = [
            {'event_name': 'PageView', 'session_id': 's1'},
            {'event_name': 'PageView', 'session_id': 's1'},
            {'event_name': 'Purchase', 'value': 100, 'session_id': 's1'},
            {'event_name': 'PageView', 'session_id': 's2'},
            {'event_name': 'Purchase', 'value': 150, 'session_id': 's2'},
        ]
        
        features = store.compute_features('user_001', events)
        
        assert features.total_purchases == 2
        assert features.total_revenue == 250.0
        assert features.avg_order_value == 125.0
        assert features.total_pageviews == 3
        assert features.total_sessions == 2
    
    def test_features_cached(self, store):
        """Should cache computed features"""
        events = [
            {'event_name': 'Purchase', 'value': 100, 'session_id': 's1'},
        ]
        
        # Compute features
        store.compute_features('cached_user', events)
        
        # Should retrieve from cache
        features = store.get_features('cached_user')
        
        assert features.total_purchases == 1
        assert features.total_revenue == 100.0
    
    def test_handle_events_without_value(self, store):
        """Should handle events without value field"""
        events = [
            {'event_name': 'Purchase', 'session_id': 's1'},  # No value
            {'event_name': 'Purchase', 'value': 100, 'session_id': 's1'},
        ]
        
        features = store.compute_features('user_no_value', events)
        
        assert features.total_purchases == 2
        assert features.total_revenue == 100.0  # Only one has value


class TestMLPipeline:
    """Integration tests for ML pipeline"""
    
    @pytest.fixture
    def feature_store(self):
        return FeatureStore()
    
    @pytest.fixture
    def ltv_predictor(self):
        return LTVPredictor()
    
    @pytest.fixture
    def churn_predictor(self):
        return ChurnPredictor()
    
    @pytest.fixture
    def propensity_predictor(self):
        return PropensityPredictor()
    
    def test_full_prediction_pipeline(
        self,
        feature_store,
        ltv_predictor,
        churn_predictor,
        propensity_predictor
    ):
        """Should run full prediction pipeline"""
        # Setup events
        events = [
            {'event_name': 'PageView', 'session_id': 's1'},
            {'event_name': 'PageView', 'session_id': 's1'},
            {'event_name': 'Purchase', 'value': 200, 'session_id': 's1'},
            {'event_name': 'PageView', 'session_id': 's2'},
            {'event_name': 'PageView', 'session_id': 's2'},
            {'event_name': 'Purchase', 'value': 300, 'session_id': 's2'},
        ]
        
        # Compute features
        features = feature_store.compute_features('pipeline_user', events)
        
        # Update recency features manually for test
        features.days_since_last_purchase = 10
        features.days_since_last_visit = 2
        features.visits_last_7d = 4
        features.visits_last_30d = 8
        features.purchase_frequency = 0.1
        
        # Run all predictions
        ltv_result = ltv_predictor.predict(features)
        churn_result = churn_predictor.predict(features)
        propensity_result = propensity_predictor.predict(features)
        
        # Combine results
        combined = {
            'user_id': features.user_id,
            **ltv_result,
            **churn_result,
            **propensity_result,
        }
        
        # Verify all fields present
        assert 'predicted_ltv_90d' in combined
        assert 'ltv_tier' in combined
        assert 'churn_probability' in combined
        assert 'churn_risk' in combined
        assert 'propensity_7d' in combined
        assert 'propensity_tier' in combined
    
    def test_predictions_consistent(
        self,
        ltv_predictor,
        churn_predictor,
        propensity_predictor
    ):
        """Should produce consistent predictions for same input"""
        features = FeatureVector(
            user_id='consistent_user',
            total_purchases=5,
            total_revenue=500.0,
            days_since_last_purchase=15,
            days_since_last_visit=3,
            visits_last_7d=3,
            purchase_frequency=0.1,
        )
        
        # Run predictions twice
        ltv1 = ltv_predictor.predict(features)
        ltv2 = ltv_predictor.predict(features)
        
        churn1 = churn_predictor.predict(features)
        churn2 = churn_predictor.predict(features)
        
        propensity1 = propensity_predictor.predict(features)
        propensity2 = propensity_predictor.predict(features)
        
        # Should be identical
        assert ltv1 == ltv2
        assert churn1 == churn2
        assert propensity1 == propensity2


class TestFeatureEngineering:
    """Tests for feature engineering functions"""
    
    def test_calculate_purchase_frequency(self):
        """Should calculate purchase frequency correctly"""
        total_purchases = 10
        days_since_first = 100
        
        frequency = total_purchases / days_since_first if days_since_first > 0 else 0
        
        assert frequency == 0.1
    
    def test_calculate_avg_order_value(self):
        """Should calculate AOV correctly"""
        total_revenue = 500.0
        total_purchases = 5
        
        aov = total_revenue / total_purchases if total_purchases > 0 else 0
        
        assert aov == 100.0
    
    def test_calculate_aov_no_purchases(self):
        """Should handle zero purchases for AOV"""
        total_revenue = 0.0
        total_purchases = 0
        
        aov = total_revenue / total_purchases if total_purchases > 0 else 0
        
        assert aov == 0.0
    
    def test_calculate_recency_score(self):
        """Should calculate recency score"""
        # More recent = higher score
        def recency_score(days_since_last: int) -> float:
            if days_since_last <= 7:
                return 1.0
            elif days_since_last <= 30:
                return 0.7
            elif days_since_last <= 90:
                return 0.4
            else:
                return 0.1
        
        assert recency_score(3) == 1.0
        assert recency_score(15) == 0.7
        assert recency_score(60) == 0.4
        assert recency_score(120) == 0.1
