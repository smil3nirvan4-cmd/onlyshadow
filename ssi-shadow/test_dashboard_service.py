#!/usr/bin/env python3
"""
Test script for DashboardDataService with Mock Mode
Run: python test_dashboard_service.py
"""

import asyncio
import os
import sys
import json

# Force mock mode for testing
os.environ["USE_MOCK_DATA"] = "true"

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import directly to avoid dependency issues
import importlib.util
spec = importlib.util.spec_from_file_location(
    "dashboard_service", 
    os.path.join(os.path.dirname(__file__), "api/services/dashboard_service.py")
)
dashboard_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dashboard_module)

DashboardDataService = dashboard_module.DashboardDataService
get_dashboard_service = dashboard_module.get_dashboard_service


async def test_dashboard_service():
    """Test all dashboard service methods in mock mode."""
    print("=" * 60)
    print("🧪 Testing DashboardDataService with MOCK MODE")
    print("=" * 60)
    
    # Initialize service
    service = DashboardDataService()
    
    assert service.use_mock == True, "Service should be in mock mode"
    print("✅ Service initialized in MOCK mode")
    
    org_id = "test_org_123"
    
    # Test 1: Overview
    print("\n📊 Testing get_overview()...")
    overview = await service.get_overview(org_id)
    assert "events_today" in overview
    assert "revenue" in overview
    assert overview.get("data_source") == "mock"
    print(f"   Events: {overview['events_today']['current']}")
    print(f"   Revenue: ${overview['revenue']['current']:.2f}")
    print("   ✅ Overview OK")
    
    # Test 2: Platforms
    print("\n🔌 Testing get_platforms()...")
    platforms = await service.get_platforms(org_id)
    assert "platforms" in platforms
    assert len(platforms["platforms"]) > 0
    assert platforms.get("data_source") == "mock"
    print(f"   Total platforms: {len(platforms['platforms'])}")
    print(f"   Overall status: {platforms['overall_status']}")
    print("   ✅ Platforms OK")
    
    # Test 3: Trust Score
    print("\n🛡️ Testing get_trust_score()...")
    trust = await service.get_trust_score(org_id)
    assert "distribution" in trust
    assert "avg_trust_score" in trust
    assert trust.get("data_source") == "mock"
    print(f"   Avg Trust Score: {trust['avg_trust_score']:.4f}")
    print(f"   Block Rate: {trust['block_rate'] * 100:.2f}%")
    print("   ✅ Trust Score OK")
    
    # Test 4: ML Predictions
    print("\n🤖 Testing get_ml_predictions()...")
    ml = await service.get_ml_predictions(org_id)
    assert "ltv_segments" in ml
    assert "churn_segments" in ml
    assert ml.get("data_source") == "mock"
    print(f"   Total users predicted: {ml['total_users_predicted']}")
    print(f"   High value users: {ml['high_value_users']}")
    print("   ✅ ML Predictions OK")
    
    # Test 5: Funnel
    print("\n🔄 Testing get_funnel()...")
    funnel = await service.get_funnel(org_id)
    assert "stages" in funnel
    assert len(funnel["stages"]) == 5
    assert funnel.get("data_source") == "mock"
    print(f"   Total sessions: {funnel['total_sessions']}")
    print(f"   Conversion rate: {funnel['overall_conversion_rate'] * 100:.2f}%")
    print("   ✅ Funnel OK")
    
    # Test 6: Events
    print("\n📋 Testing get_events()...")
    events = await service.get_events(org_id, limit=10)
    assert "events" in events
    assert len(events["events"]) == 10
    assert events.get("data_source") == "mock"
    print(f"   Total events: {events['total']}")
    print(f"   Returned: {len(events['events'])}")
    print("   ✅ Events OK")
    
    # Test 7: Event Detail
    print("\n🔍 Testing get_event_detail()...")
    detail = await service.get_event_detail(org_id, "evt_test_123")
    assert "event_id" in detail
    assert "trust_signals" in detail
    assert detail.get("data_source") == "mock"
    print(f"   Event: {detail['event_name']}")
    print(f"   Value: ${detail['value']:.2f}")
    print("   ✅ Event Detail OK")
    
    # Test 8: Bid Metrics
    print("\n💰 Testing get_bid_metrics()...")
    bids = await service.get_bid_metrics(org_id)
    assert "strategies" in bids
    assert "avg_multiplier" in bids
    assert bids.get("data_source") == "mock"
    print(f"   Avg multiplier: {bids['avg_multiplier']:.2f}")
    print(f"   Strategies: {list(bids['strategies'].keys())}")
    print("   ✅ Bid Metrics OK")
    
    # Cleanup
    await service.close()
    
    print("\n" + "=" * 60)
    print("🎉 ALL TESTS PASSED!")
    print("=" * 60)
    
    # Print sample JSON output
    print("\n📄 Sample Overview Response:")
    print(json.dumps(overview, indent=2, default=str))
    
    return True


async def test_singleton():
    """Test singleton pattern."""
    print("\n🔄 Testing singleton pattern...")
    
    service1 = get_dashboard_service()
    service2 = get_dashboard_service()
    
    assert service1 is service2, "Singleton should return same instance"
    print("   ✅ Singleton OK")


if __name__ == "__main__":
    try:
        asyncio.run(test_dashboard_service())
        asyncio.run(test_singleton())
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
