#!/usr/bin/env python3
"""
Test script for Meta Ads Client
Run: python test_meta_ads_client.py
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Force mock mode for testing
os.environ["USE_MOCK_DATA"] = "true"

from ads_engine.meta_ads_client import (
    MetaAdsClient,
    MockMetaAdsClient,
    get_meta_ads_client,
    CampaignObjective,
    CampaignStatus,
    FB_SDK_AVAILABLE,
    Campaign,
    AdSet,
    Ad,
    InsightsData,
)


async def test_mock_client():
    """Test mock client functionality."""
    print("\n" + "=" * 60)
    print("🧪 Testing MockMetaAdsClient")
    print("=" * 60)
    
    client = MockMetaAdsClient()
    
    # Test get_campaigns
    print("\n📊 Testing get_campaigns()...")
    campaigns = await client.get_campaigns()
    assert len(campaigns) == 2
    assert all(isinstance(c, Campaign) for c in campaigns)
    print(f"   ✅ Got {len(campaigns)} campaigns")
    for c in campaigns:
        print(f"      - {c.name}: {c.status} (${c.daily_budget}/day)")
    
    # Test get_adsets
    print("\n📋 Testing get_adsets()...")
    adsets = await client.get_adsets()
    assert len(adsets) == 2
    assert all(isinstance(a, AdSet) for a in adsets)
    print(f"   ✅ Got {len(adsets)} ad sets")
    
    # Test get_ads
    print("\n📢 Testing get_ads()...")
    ads = await client.get_ads()
    assert len(ads) == 2
    assert all(isinstance(a, Ad) for a in ads)
    print(f"   ✅ Got {len(ads)} ads")
    
    # Test create_campaign
    print("\n➕ Testing create_campaign()...")
    campaign_id = await client.create_campaign(
        name="Test Campaign",
        objective=CampaignObjective.OUTCOME_SALES
    )
    assert campaign_id is not None
    print(f"   ✅ Created campaign: {campaign_id}")
    
    # Test create_adset
    print("\n➕ Testing create_adset()...")
    adset_id = await client.create_adset(
        campaign_id=campaign_id,
        name="Test Ad Set"
    )
    assert adset_id is not None
    print(f"   ✅ Created ad set: {adset_id}")
    
    # Test create_ad
    print("\n➕ Testing create_ad()...")
    ad_id = await client.create_ad(
        adset_id=adset_id,
        name="Test Ad",
        creative_id="creative_123"
    )
    assert ad_id is not None
    print(f"   ✅ Created ad: {ad_id}")
    
    # Test update_status
    print("\n🔄 Testing update_status()...")
    result = await client.update_status(campaign_id, "PAUSED")
    assert result == True
    print(f"   ✅ Updated status")
    
    # Test update_budget
    print("\n💰 Testing update_budget()...")
    result = await client.update_budget(campaign_id, 150.00)
    assert result == True
    print(f"   ✅ Updated budget")
    
    # Test update_bid
    print("\n💵 Testing update_bid()...")
    result = await client.update_bid(adset_id, 2.50)
    assert result == True
    print(f"   ✅ Updated bid")
    
    # Test duplicate
    print("\n📋 Testing duplicate()...")
    new_id = await client.duplicate(campaign_id)
    assert new_id is not None
    print(f"   ✅ Duplicated: {campaign_id} -> {new_id}")
    
    # Test create_lookalike
    print("\n👥 Testing create_lookalike()...")
    lookalike_id = await client.create_lookalike(
        source_id="audience_123",
        name="1% Lookalike"
    )
    assert lookalike_id is not None
    print(f"   ✅ Created lookalike: {lookalike_id}")
    
    # Test create_audience
    print("\n👥 Testing create_audience()...")
    audience_id = await client.create_audience({
        "name": "Website Visitors",
        "subtype": "WEBSITE"
    })
    assert audience_id is not None
    print(f"   ✅ Created audience: {audience_id}")
    
    # Test get_insights
    print("\n📈 Testing get_insights()...")
    insights = await client.get_insights()
    assert len(insights) > 0
    assert all(isinstance(i, InsightsData) for i in insights)
    print(f"   ✅ Got {len(insights)} insight records")
    for i in insights:
        print(f"      - Spend: ${i.spend:.2f}, ROAS: {i.roas:.2f}x, Conv: {i.conversions}")
    
    # Test test_connection
    print("\n🔌 Testing test_connection()...")
    conn = await client.test_connection()
    assert conn["success"] == True
    print(f"   ✅ Connection OK: {conn['account_name']}")
    
    print("\n" + "=" * 60)
    print("🎉 ALL MOCK CLIENT TESTS PASSED!")
    print("=" * 60)


async def test_factory_function():
    """Test the factory function."""
    print("\n" + "=" * 60)
    print("🧪 Testing get_meta_ads_client() Factory")
    print("=" * 60)
    
    # Test with force mock
    print("\n🎭 Testing with use_mock=True...")
    client = get_meta_ads_client(use_mock=True)
    assert isinstance(client, MockMetaAdsClient)
    print(f"   ✅ Got MockMetaAdsClient")
    
    # Test auto-detect (should use mock since no credentials)
    print("\n🔍 Testing auto-detect (no credentials)...")
    client = get_meta_ads_client()
    assert isinstance(client, MockMetaAdsClient)
    print(f"   ✅ Auto-detected: Using MockMetaAdsClient")
    
    print("\n✅ Factory function tests passed!")


async def test_real_client_structure():
    """Test that real client has same interface as mock."""
    print("\n" + "=" * 60)
    print("🧪 Testing MetaAdsClient Structure")
    print("=" * 60)
    
    print(f"\n📦 facebook-business SDK available: {FB_SDK_AVAILABLE}")
    
    # Check that both clients have the same methods
    mock_methods = set(m for m in dir(MockMetaAdsClient) if not m.startswith('_'))
    
    if FB_SDK_AVAILABLE:
        real_methods = set(m for m in dir(MetaAdsClient) if not m.startswith('_'))
        
        print("\n📋 Checking method compatibility...")
        
        # Check key methods exist in real client
        key_methods = [
            "get_campaigns", "get_adsets", "get_ads",
            "create_campaign", "create_adset", "create_ad",
            "update_status", "update_budget", "update_bid",
            "duplicate", "create_lookalike", "create_audience",
            "get_insights", "test_connection"
        ]
        
        for method in key_methods:
            assert method in real_methods, f"Missing method: {method}"
            print(f"   ✅ {method}")
        
        print("\n✅ Real client has all required methods!")
    else:
        print("   ⚠️ SDK not installed - skipping real client structure test")


async def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 META ADS CLIENT TEST SUITE")
    print("=" * 60)
    print(f"📦 facebook-business SDK: {'✅ Available' if FB_SDK_AVAILABLE else '❌ Not installed'}")
    
    try:
        await test_mock_client()
        await test_factory_function()
        await test_real_client_structure()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        
        # Usage summary
        print("\n📖 USAGE SUMMARY")
        print("-" * 40)
        print("""
# 1. Install SDK (for production):
pip install facebook-business

# 2. Set environment variables:
export META_APP_ID=your_app_id
export META_APP_SECRET=your_app_secret
export META_ACCESS_TOKEN=your_access_token
export META_AD_ACCOUNT_ID=1234567890

# 3. Use in code:
from ads_engine.meta_ads_client import get_meta_ads_client

# Auto-detect (uses real if credentials available, mock otherwise)
client = get_meta_ads_client()

# Force mock for testing
client = get_meta_ads_client(use_mock=True)

# Force real (will raise error if no credentials)
client = get_meta_ads_client(use_mock=False)

# Get campaigns
campaigns = await client.get_campaigns()

# Create campaign
campaign_id = await client.create_campaign(
    name="My Campaign",
    objective=CampaignObjective.OUTCOME_SALES,
    daily_budget=100.0
)

# Update status
await client.update_status(campaign_id, "PAUSED")
""")
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
