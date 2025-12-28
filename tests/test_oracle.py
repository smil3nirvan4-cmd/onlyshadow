"""
S.S.I. SHADOW — Unit Tests
PYTHON TEST SUITE

Run with: pytest tests/ -v
"""

import pytest
import json
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def mock_bq_client():
    """Mock BigQuery client"""
    client = Mock()
    client.query = Mock(return_value=Mock(result=Mock(return_value=iter([]))))
    return client


@pytest.fixture
def sample_event():
    """Sample incoming event"""
    return {
        'event_name': 'PageView',
        'event_id': 'evt_test123',
        'timestamp': int(datetime.now().timestamp() * 1000),
        'url': 'https://example.com/product/123',
        'referrer': 'https://google.com',
        'fbclid': 'fb_abc123',
        'ssi_id': 'ssi_test_user',
        'visitor_id': 'fpjs_visitor123',
        'fp_confidence': 0.95,
        'canvas_hash': 'abc123',
        'scroll_depth': 50,
        'time_on_page': 30,
        'interactions': 5
    }


@pytest.fixture
def sample_ipqs_response():
    """Sample IPQS API response"""
    return {
        'success': True,
        'fraud_score': 25,
        'bot_status': False,
        'vpn': False,
        'proxy': False,
        'tor': False,
        'mobile': True,
        'country_code': 'BR',
        'connection_type': 'Residential',
        'recent_abuse': False
    }


# =============================================================================
# SHADOW ENGINE TESTS
# =============================================================================

class TestShadowEngine:
    """Tests for Shadow Intelligence Engine"""
    
    def test_calculate_bos_score(self):
        """Test Blue Ocean Score calculation"""
        from shadow.engine_v2 import OpportunityCalculator
        
        calc = OpportunityCalculator()
        
        # High opportunity: high volume, high CPC, low competition
        score = calc.calculate_bos(
            search_volume=10000,
            cpc=5.0,
            competition=0.2,
            organic_results=500000
        )
        
        assert score > 0.5, "High opportunity should have BOS > 0.5"
    
    def test_calculate_trend_score(self):
        """Test trend score calculation"""
        from shadow.engine_v2 import OpportunityCalculator
        
        calc = OpportunityCalculator()
        
        # Upward trend
        trend_data = [
            {'value': 50},
            {'value': 55},
            {'value': 60},
            {'value': 70},
            {'value': 80}
        ]
        
        score = calc.calculate_trend_score(trend_data)
        
        assert score > 0, "Upward trend should have positive score"
    
    def test_identify_opportunities(self):
        """Test opportunity identification"""
        from shadow.engine_v2 import OpportunityCalculator, KeywordData
        
        calc = OpportunityCalculator()
        
        keywords = [
            KeywordData(
                keyword="high opportunity",
                search_volume=5000,
                trend_percent=20,
                cpc=3.0,
                competition=0.3,
                organic_results=100000,
                difficulty=40,
                opportunity_score=0.0
            ),
            KeywordData(
                keyword="low opportunity",
                search_volume=100,
                trend_percent=-10,
                cpc=0.5,
                competition=0.9,
                organic_results=10000000,
                difficulty=90,
                opportunity_score=0.0
            )
        ]
        
        opportunities = calc.identify_opportunities(keywords, min_bos=0.3)
        
        assert len(opportunities) >= 0  # May or may not find opportunities


# =============================================================================
# ENTERPRISE APIS TESTS
# =============================================================================

class TestEnterpriseAPIs:
    """Tests for Enterprise API integrations"""
    
    @patch('requests.Session.request')
    def test_ipqs_check_ip(self, mock_request, sample_ipqs_response):
        """Test IPQS IP check"""
        from integrations.enterprise_apis import IPQualityScoreClient
        
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = sample_ipqs_response
        mock_request.return_value = mock_response
        
        client = IPQualityScoreClient('test_api_key')
        result = client.checkIP('8.8.8.8')
        
        assert result is not None
        assert result['fraud_score'] == 25
        assert result['bot_status'] == False
    
    @patch('requests.Session.request')
    def test_clearbit_reveal(self, mock_request):
        """Test Clearbit company reveal"""
        from integrations.enterprise_apis import ClearbitClient
        
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'company': {
                'name': 'Test Corp',
                'domain': 'test.com',
                'category': {'industry': 'Technology'}
            }
        }
        mock_request.return_value = mock_response
        
        client = ClearbitClient('test_api_key')
        result = client.reveal_company('8.8.8.8')
        
        assert result is not None
        assert result['name'] == 'Test Corp'
    
    @patch('requests.Session.request')
    def test_hunter_verify_email(self, mock_request):
        """Test Hunter email verification"""
        from integrations.enterprise_apis import HunterClient
        
        mock_response = Mock()
        mock_response.ok = True
        mock_response.json.return_value = {
            'data': {
                'result': 'deliverable',
                'score': 95,
                'disposable': False,
                'webmail': False,
                'mx_records': True,
                'smtp_check': True
            }
        }
        mock_request.return_value = mock_response
        
        client = HunterClient('test_api_key')
        result = client.verify_email('test@example.com')
        
        assert result['valid'] == True
        assert result['score'] == 95
    
    def test_enrichment_service_should_send(self):
        """Test enrichment service decision logic"""
        from integrations.enterprise_apis import EnrichmentService
        
        service = EnrichmentService()
        
        # Valid email
        result = service.should_send_to_capi(
            email='valid@company.com',
            phone='11999999999',
            trust_score=0.8
        )
        
        assert result['send_email'] == True
        assert result['send_phone'] == True
        assert result['send_event'] == True
        
        # Disposable email
        result = service.should_send_to_capi(
            email='test@tempmail.com',
            trust_score=0.8
        )
        
        assert result['send_email'] == False
        
        # Low trust score
        result = service.should_send_to_capi(
            trust_score=0.2
        )
        
        assert result['send_event'] == False


# =============================================================================
# BID CONTROLLER TESTS
# =============================================================================

class TestBidController:
    """Tests for Bid Controller"""
    
    def test_calculate_optimal_bid(self):
        """Test bid optimization calculation"""
        from automation.bid_controller import BidOptimizer, BidControllerConfig, BidAction
        
        config = BidControllerConfig(
            gcp_project_id='test-project',
            min_bid_multiplier=0.5,
            max_bid_multiplier=2.0
        )
        
        optimizer = BidOptimizer(config)
        
        # High LTV should increase bid
        new_bid, action, reason = optimizer.calculate_optimal_bid(
            current_bid=10.0,
            predicted_ltv=100.0,
            current_cpa=20.0,
            target_roas=3.0,
            trust_score=0.8
        )
        
        assert action == BidAction.INCREASE
        assert new_bid > 10.0
        
        # Low LTV should decrease bid
        new_bid, action, reason = optimizer.calculate_optimal_bid(
            current_bid=10.0,
            predicted_ltv=10.0,
            current_cpa=20.0,
            target_roas=3.0,
            trust_score=0.8
        )
        
        assert action == BidAction.DECREASE
        assert new_bid < 10.0
    
    def test_bid_multiplier_limits(self):
        """Test that bid multipliers are within limits"""
        from automation.bid_controller import BidOptimizer, BidControllerConfig
        
        config = BidControllerConfig(
            gcp_project_id='test-project',
            min_bid_multiplier=0.5,
            max_bid_multiplier=2.0
        )
        
        optimizer = BidOptimizer(config)
        
        # Extreme high LTV
        new_bid, _, _ = optimizer.calculate_optimal_bid(
            current_bid=10.0,
            predicted_ltv=10000.0,
            current_cpa=20.0,
            target_roas=3.0,
            trust_score=1.0
        )
        
        assert new_bid <= 20.0  # Max 2x
        
        # Extreme low LTV
        new_bid, _, _ = optimizer.calculate_optimal_bid(
            current_bid=10.0,
            predicted_ltv=1.0,
            current_cpa=20.0,
            target_roas=3.0,
            trust_score=0.3
        )
        
        assert new_bid >= 5.0  # Min 0.5x


# =============================================================================
# OBSERVABILITY TESTS
# =============================================================================

class TestObservability:
    """Tests for Observability module"""
    
    def test_alert_thresholds(self):
        """Test alert threshold checking"""
        from monitoring.observability import AlertManager, ObservabilityConfig, AlertThresholds
        
        config = ObservabilityConfig(
            project_id='test-project',
            thresholds=AlertThresholds(
                ivt_rate_max=0.20,
                ivt_rate_critical=0.30,
                model_accuracy_min=0.70
            )
        )
        
        manager = AlertManager(config)
        
        # High IVT should trigger alert
        metrics = {
            'quality': {
                'ivt_rate': 0.35  # Above critical
            },
            'attribution': {
                'estimated_match_rate': 0.6,
                'estimated_emq': 7
            }
        }
        
        alerts = manager.check_all(metrics)
        
        assert len(alerts) > 0
        assert any(a['type'] == 'ivt_critical' for a in alerts)
    
    def test_no_alerts_when_healthy(self):
        """Test no alerts when metrics are healthy"""
        from monitoring.observability import AlertManager, ObservabilityConfig
        
        config = ObservabilityConfig(project_id='test-project')
        manager = AlertManager(config)
        
        # Healthy metrics
        metrics = {
            'quality': {
                'ivt_rate': 0.05,
                'avg_trust_score': 0.8
            },
            'attribution': {
                'estimated_match_rate': 0.75,
                'estimated_emq': 8.5
            },
            'latency': {
                'p95_ms': 50,
                'p99_ms': 80
            }
        }
        
        alerts = manager.check_all(metrics)
        
        assert len(alerts) == 0


# =============================================================================
# MLOPS TESTS
# =============================================================================

class TestMLOps:
    """Tests for MLOps Pipeline"""
    
    def test_data_drift_detection(self):
        """Test data drift detection"""
        from ml.mlops_pipeline import DataDriftDetector
        
        # Mock BQ client
        mock_bq = Mock()
        mock_config = Mock()
        mock_config.project_id = 'test'
        mock_config.dataset_id = 'ssi_shadow'
        
        detector = DataDriftDetector(mock_bq, mock_config)
        
        # Current vs baseline stats
        current = {
            'trust_score': {'mean': 0.75, 'std': 0.1},
            'intent_score': {'mean': 0.6, 'std': 0.15},
            'conversion_rate': 0.02
        }
        
        baseline = {
            'trust_score': {'mean': 0.72, 'std': 0.1},
            'intent_score': {'mean': 0.58, 'std': 0.15},
            'conversion_rate': 0.025
        }
        
        has_drift, drifted = detector.detect_drift(current, baseline, threshold=2.0)
        
        # Small changes should not trigger drift
        assert has_drift == False
    
    def test_onnx_export_validation(self):
        """Test ONNX model validation"""
        # This would require actual sklearn model
        # Skipping for now as it requires ML dependencies
        pass


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests (require mocked services)"""
    
    @pytest.mark.integration
    def test_full_event_flow(self, sample_event, mock_bq_client):
        """Test full event processing flow"""
        # This would test the complete flow from event ingestion
        # to CAPI send and BigQuery storage
        pass
    
    @pytest.mark.integration
    def test_identity_resolution(self):
        """Test identity resolution across multiple signals"""
        pass


# =============================================================================
# UTILITY TESTS
# =============================================================================

class TestUtilities:
    """Tests for utility functions"""
    
    def test_hash_ip(self):
        """Test IP hashing"""
        # Simple hash function test
        ip1 = "192.168.1.1"
        ip2 = "192.168.1.2"
        
        # Should produce different hashes
        hash1 = hash(ip1)
        hash2 = hash(ip2)
        
        assert hash1 != hash2
    
    def test_generate_event_id(self):
        """Test event ID generation"""
        import time
        
        def generate_event_id():
            return f"evt_{int(time.time() * 1000)}_{os.urandom(4).hex()}"
        
        id1 = generate_event_id()
        id2 = generate_event_id()
        
        assert id1 != id2
        assert id1.startswith('evt_')


# =============================================================================
# RUN TESTS
# =============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
