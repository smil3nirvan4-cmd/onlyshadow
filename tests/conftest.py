"""
S.S.I. SHADOW - Pytest Configuration
Global fixtures and configuration for tests.
"""

import pytest
import asyncio
from typing import Generator, AsyncGenerator, Dict, Any
from unittest.mock import MagicMock, AsyncMock
from datetime import datetime, date


# =============================================================================
# ASYNC CONFIGURATION
# =============================================================================

@pytest.fixture(scope="session")
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


# =============================================================================
# MOCK FIXTURES
# =============================================================================

@pytest.fixture
def mock_bigquery_client():
    """Mock BigQuery client."""
    client = MagicMock()
    client.query = MagicMock(return_value=MagicMock(result=MagicMock(return_value=[])))
    return client


@pytest.fixture
def mock_redis_client():
    """Mock Redis client."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=None)
    client.set = AsyncMock(return_value=True)
    client.delete = AsyncMock(return_value=1)
    return client


@pytest.fixture
def mock_meta_ads_client():
    """Mock Meta Ads client."""
    client = AsyncMock()
    client.create_campaign = AsyncMock(return_value="camp_123")
    client.update_campaign = AsyncMock(return_value=True)
    client.get_campaigns = AsyncMock(return_value=[])
    return client


@pytest.fixture
def mock_google_ads_client():
    """Mock Google Ads client."""
    client = AsyncMock()
    client.create_campaign = AsyncMock(return_value="123456789")
    client.update_campaign_budget = AsyncMock(return_value=True)
    client.get_campaigns = AsyncMock(return_value=[])
    client.get_campaign_performance = AsyncMock(return_value=[])
    client.get_search_terms_report = AsyncMock(return_value=[])
    return client


# =============================================================================
# SAMPLE DATA FIXTURES
# =============================================================================

@pytest.fixture
def sample_event() -> Dict[str, Any]:
    """Sample tracking event."""
    return {
        "event_name": "purchase",
        "event_id": "evt_123456",
        "user_id": "user_789",
        "timestamp": datetime.utcnow().isoformat(),
        "properties": {
            "value": 99.99,
            "currency": "USD",
            "product_ids": ["prod_123", "prod_456"],
            "order_id": "order_001"
        },
        "context": {
            "ip": "192.168.1.1",
            "user_agent": "Mozilla/5.0",
            "page_url": "https://example.com/checkout"
        }
    }


@pytest.fixture
def sample_campaign() -> Dict[str, Any]:
    """Sample campaign data."""
    return {
        "id": "123456789",
        "name": "Test Campaign",
        "status": "ENABLED",
        "type": "SEARCH",
        "daily_budget": 100.0,
        "bidding_strategy": "MAXIMIZE_CONVERSIONS"
    }


@pytest.fixture
def sample_user() -> Dict[str, Any]:
    """Sample user data."""
    return {
        "id": "user_123",
        "email": "test@example.com",
        "name": "Test User",
        "role": "admin",
        "organization_id": "org_456"
    }


@pytest.fixture
def sample_performance() -> Dict[str, Any]:
    """Sample campaign performance data."""
    return {
        "campaign_id": "123456789",
        "date": date.today().isoformat(),
        "impressions": 10000,
        "clicks": 500,
        "cost": 250.0,
        "conversions": 25,
        "conversion_value": 2500.0,
        "ctr": 0.05,
        "cpc": 0.50,
        "cpa": 10.0,
        "roas": 10.0
    }


# =============================================================================
# TEST ENVIRONMENT FIXTURES
# =============================================================================

@pytest.fixture
def test_env(monkeypatch):
    """Set up test environment variables."""
    env_vars = {
        "ENVIRONMENT": "test",
        "REDIS_URL": "redis://localhost:6379",
        "GCP_PROJECT_ID": "test-project",
        "BQ_DATASET": "test_dataset",
        "META_ACCESS_TOKEN": "test_token",
        "GOOGLE_ADS_DEVELOPER_TOKEN": "test_token",
    }
    for key, value in env_vars.items():
        monkeypatch.setenv(key, value)
    return env_vars


# =============================================================================
# HELPER FIXTURES
# =============================================================================

@pytest.fixture
def assert_within():
    """Helper to assert value is within range."""
    def _assert_within(value, expected, tolerance=0.01):
        assert abs(value - expected) <= tolerance, f"{value} not within {tolerance} of {expected}"
    return _assert_within
