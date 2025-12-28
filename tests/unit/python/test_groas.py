"""
S.S.I. SHADOW - gROAS Tests
Tests for gROAS orchestrator and automation.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from ads_engine.groas_orchestrator import (
    GROASOrchestrator,
    GROASConfig,
    SearchIntentAnalyzer,
    OptimizationAction,
    OptimizationRecommendation
)


class TestSearchIntentAnalyzer:
    """Tests for SearchIntentAnalyzer."""
    
    def test_high_purchase_intent(self):
        analyzer = SearchIntentAnalyzer()
        result = analyzer.analyze("buy running shoes online")
        
        assert result['intent_score'] >= 0.7
        assert result['is_high_intent'] is True
        assert result['suggested_action'] == 'add_as_keyword'
    
    def test_low_purchase_intent(self):
        analyzer = SearchIntentAnalyzer()
        result = analyzer.analyze("how to make running shoes diy")
        
        assert result['intent_score'] <= 0.4
        assert result['is_low_intent'] is True
        assert result['suggested_action'] == 'add_as_negative'
    
    def test_medium_intent(self):
        analyzer = SearchIntentAnalyzer()
        result = analyzer.analyze("best running shoes 2024")
        
        assert 0.3 < result['intent_score'] < 0.7
        assert result['suggested_action'] == 'monitor'
    
    def test_multiple_signals(self):
        analyzer = SearchIntentAnalyzer()
        
        # Multiple high signals
        result = analyzer.analyze("buy cheap running shoes coupon discount")
        assert result['intent_score'] >= 0.8


class TestGROASOrchestrator:
    """Tests for GROASOrchestrator."""
    
    @pytest.fixture
    def mock_google_client(self):
        client = AsyncMock()
        client.get_campaigns = AsyncMock(return_value=[
            MagicMock(id="123", name="Test Campaign")
        ])
        client.get_search_terms_report = AsyncMock(return_value=[
            MagicMock(
                search_term="buy running shoes",
                campaign_id="123",
                ad_group_id="456",
                impressions=100,
                clicks=10,
                cost_micros=5_000_000,
                conversions=2.0
            )
        ])
        client.add_keywords = AsyncMock(return_value=["kw_1"])
        client.add_negative_keywords = AsyncMock(return_value=["neg_1"])
        return client
    
    @pytest.fixture
    def orchestrator(self, mock_google_client):
        return GROASOrchestrator(
            google_ads_client=mock_google_client,
            config=GROASConfig()
        )
    
    @pytest.mark.asyncio
    async def test_run_optimization_cycle(self, orchestrator, mock_google_client):
        result = await orchestrator.run_optimization_cycle(
            auto_apply=False,
            dry_run=True
        )
        
        assert result.campaigns_analyzed == 1
        assert result.completed_at is not None
        mock_google_client.get_campaigns.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_get_recommendations(self, orchestrator):
        recommendations = await orchestrator.get_recommendations()
        
        # Should return list of recommendations
        assert isinstance(recommendations, list)
    
    @pytest.mark.asyncio
    async def test_status(self, orchestrator):
        status = orchestrator.get_status()
        
        assert "running" in status
        assert status["running"] is False


class TestOptimizationRecommendation:
    """Tests for OptimizationRecommendation."""
    
    def test_create_recommendation(self):
        rec = OptimizationRecommendation(
            action=OptimizationAction.ADD_KEYWORD,
            campaign_id="123",
            ad_group_id="456",
            keyword_text="buy shoes",
            reason="High intent",
            confidence=0.85
        )
        
        assert rec.action == OptimizationAction.ADD_KEYWORD
        assert rec.confidence == 0.85
        assert rec.applied is False
