#!/usr/bin/env python3
"""
Test script for TikTok Ads Client
Run: python test_tiktok_ads_client.py
"""

import asyncio
import os
import sys

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ads_engine.tiktok_ads_client import (
    TikTokAdsClient,
    MockTikTokAdsClient,
    get_tiktok_ads_client,
    CampaignObjective,
    CampaignStatus,
    OptimizationGoal,
    BidStrategy,
    HTTPX_AVAILABLE,
    Campaign,
    AdGroup,
    Ad,
    InsightsData,
)


async def test_mock_client():
    """Test mock client functionality."""
    print("\n" + "=" * 60)
    print("🧪 Testing MockTikTokAdsClient")
    print("=" * 60)
    
    client = MockTikTokAdsClient()
    
    # Test get_campaigns
    print("\n📊 Testing get_campaigns()...")
    campaigns = await client.get_campaigns()
    assert len(campaigns) == 2
    assert all(isinstance(c, Campaign) for c in campaigns)
    print(f"   ✅ Got {len(campaigns)} campaigns")
    for c in campaigns:
        print(f"      - {c.campaign_name}: {c.status} (${c.budget}/day)")
    
    # Test get_all_campaigns
    print("\n📊 Testing get_all_campaigns()...")
    all_campaigns = await client.get_all_campaigns()
    assert len(all_campaigns) >= 2
    print(f"   ✅ Got {len(all_campaigns)} total campaigns")
    
    # Test get_adgroups
    print("\n📋 Testing get_adgroups()...")
    adgroups = await client.get_adgroups()
    assert len(adgroups) == 2
    assert all(isinstance(a, AdGroup) for a in adgroups)
    print(f"   ✅ Got {len(adgroups)} ad groups")
    
    # Test get_ads
    print("\n📢 Testing get_ads()...")
    ads = await client.get_ads()
    assert len(ads) == 2
    assert all(isinstance(a, Ad) for a in ads)
    print(f"   ✅ Got {len(ads)} ads")
    
    # Test create_campaign
    print("\n➕ Testing create_campaign()...")
    campaign_id = await client.create_campaign(
        name="Test TikTok Campaign",
        objective=CampaignObjective.WEBSITE_CONVERSIONS
    )
    assert campaign_id is not None
    assert len(campaign_id) == 19  # TikTok IDs are 19 digits
    print(f"   ✅ Created campaign: {campaign_id}")
    
    # Test create_adgroup
    print("\n➕ Testing create_adgroup()...")
    adgroup_id = await client.create_adgroup(
        campaign_id=campaign_id,
        name="Test Ad Group"
    )
    assert adgroup_id is not None
    print(f"   ✅ Created ad group: {adgroup_id}")
    
    # Test create_ad
    print("\n➕ Testing create_ad()...")
    ad_id = await client.create_ad(
        adgroup_id=adgroup_id,
        name="Test Ad"
    )
    assert ad_id is not None
    print(f"   ✅ Created ad: {ad_id}")
    
    # Test update_status
    print("\n🔄 Testing update_status()...")
    result = await client.update_status(campaign_id, "DISABLE", "campaign")
    assert result == True
    print(f"   ✅ Updated status")
    
    # Test pause/enable
    print("\n⏸️ Testing pause_campaign()...")
    result = await client.pause_campaign(campaign_id)
    assert result == True
    print(f"   ✅ Paused campaign")
    
    print("\n▶️ Testing enable_campaign()...")
    result = await client.enable_campaign(campaign_id)
    assert result == True
    print(f"   ✅ Enabled campaign")
    
    # Test update_budget
    print("\n💰 Testing update_budget()...")
    result = await client.update_budget(campaign_id, 750.00)
    assert result == True
    print(f"   ✅ Updated budget")
    
    # Test update_bid
    print("\n💵 Testing update_bid()...")
    result = await client.update_bid(adgroup_id, 1.50)
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
        name="TikTok Lookalike"
    )
    assert lookalike_id is not None
    print(f"   ✅ Created lookalike: {lookalike_id}")
    
    # Test create_audience
    print("\n👥 Testing create_audience()...")
    audience_id = await client.create_audience({
        "name": "Website Visitors",
        "type": "CUSTOM_AUDIENCE"
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
        print(f"      - Spend: ${i.spend:.2f}, CTR: {i.ctr:.1f}%, Conv: {i.conversions}")
        print(f"        Video Views: {i.video_views:,}, 6s Views: {i.video_watched_6s:,}")
    
    # Test test_connection
    print("\n🔌 Testing test_connection()...")
    conn = await client.test_connection()
    assert conn["success"] == True
    print(f"   ✅ Connection OK: {conn['message']}")
    
    # Test close
    await client.close()
    
    print("\n" + "=" * 60)
    print("🎉 ALL MOCK CLIENT TESTS PASSED!")
    print("=" * 60)


async def test_factory_function():
    """Test the factory function."""
    print("\n" + "=" * 60)
    print("🧪 Testing get_tiktok_ads_client() Factory")
    print("=" * 60)
    
    # Test with force mock
    print("\n🎭 Testing with use_mock=True...")
    client = get_tiktok_ads_client(use_mock=True)
    assert isinstance(client, MockTikTokAdsClient)
    print(f"   ✅ Got MockTikTokAdsClient")
    await client.close()
    
    # Test auto-detect (should use mock since no credentials)
    print("\n🔍 Testing auto-detect (no credentials)...")
    client = get_tiktok_ads_client()
    assert isinstance(client, MockTikTokAdsClient)
    print(f"   ✅ Auto-detected: Using MockTikTokAdsClient")
    await client.close()
    
    print("\n✅ Factory function tests passed!")


async def test_real_client_structure():
    """Test that real client has same interface as mock."""
    print("\n" + "=" * 60)
    print("🧪 Testing TikTokAdsClient Structure")
    print("=" * 60)
    
    print(f"\n📦 httpx available: {HTTPX_AVAILABLE}")
    
    if HTTPX_AVAILABLE:
        # Check that both clients have the same methods
        mock_methods = set(m for m in dir(MockTikTokAdsClient) if not m.startswith('_'))
        real_methods = set(m for m in dir(TikTokAdsClient) if not m.startswith('_'))
        
        print("\n📋 Checking method compatibility...")
        
        # Check key methods exist in real client
        key_methods = [
            "get_campaigns", "get_all_campaigns", "get_campaign",
            "get_adgroups", "get_ads",
            "create_campaign", "create_adgroup", "create_ad",
            "update_status", "pause_campaign", "enable_campaign",
            "update_campaign", "update_adgroup",
            "update_budget", "update_bid",
            "duplicate", "create_lookalike", "create_audience",
            "get_insights", "test_connection", "close"
        ]
        
        for method in key_methods:
            assert method in real_methods, f"Missing method: {method}"
            print(f"   ✅ {method}")
        
        print("\n✅ Real client has all required methods!")
    else:
        print("   ⚠️ httpx not installed - skipping real client structure test")


async def test_campaign_workflow():
    """Test a typical campaign workflow."""
    print("\n" + "=" * 60)
    print("🧪 Testing Campaign Workflow")
    print("=" * 60)
    
    client = MockTikTokAdsClient()
    
    print("\n1️⃣ Creating campaign...")
    campaign_id = await client.create_campaign(
        name="Q4 Holiday Sale",
        objective=CampaignObjective.PRODUCT_SALES
    )
    print(f"   Campaign ID: {campaign_id}")
    
    print("\n2️⃣ Creating ad group...")
    adgroup_id = await client.create_adgroup(
        campaign_id=campaign_id,
        name="Interests - Fashion"
    )
    print(f"   Ad Group ID: {adgroup_id}")
    
    print("\n3️⃣ Creating ad...")
    ad_id = await client.create_ad(
        adgroup_id=adgroup_id,
        name="Video Ad - 15s"
    )
    print(f"   Ad ID: {ad_id}")
    
    print("\n4️⃣ Updating budget...")
    await client.update_budget(campaign_id, 1000.00)
    print(f"   Budget set to $1000/day")
    
    print("\n5️⃣ Enabling campaign...")
    await client.enable_campaign(campaign_id)
    print(f"   Campaign enabled")
    
    print("\n6️⃣ Getting insights...")
    insights = await client.get_insights(
        start_date="2024-12-01",
        end_date="2024-12-07"
    )
    print(f"   Got {len(insights)} insight records")
    
    print("\n7️⃣ Pausing campaign...")
    await client.pause_campaign(campaign_id)
    print(f"   Campaign paused")
    
    await client.close()
    print("\n✅ Workflow completed successfully!")


async def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 TIKTOK ADS CLIENT TEST SUITE")
    print("=" * 60)
    print(f"📦 httpx: {'✅ Available' if HTTPX_AVAILABLE else '❌ Not installed'}")
    
    try:
        await test_mock_client()
        await test_factory_function()
        await test_real_client_structure()
        await test_campaign_workflow()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        
        # Usage summary
        print("\n📖 USAGE SUMMARY")
        print("-" * 40)
        print("""
# 1. Install dependencies:
pip install httpx

# 2. Set environment variables:
export TIKTOK_ACCESS_TOKEN=your_access_token
export TIKTOK_ADVERTISER_ID=7123456789012345678

# 3. Use in code:
from ads_engine.tiktok_ads_client import get_tiktok_ads_client

# Auto-detect (uses real if credentials available, mock otherwise)
client = get_tiktok_ads_client()

# Force mock for testing
client = get_tiktok_ads_client(use_mock=True)

# Get campaigns
campaigns = await client.get_campaigns()

# Create campaign
campaign_id = await client.create_campaign(
    name="My Campaign",
    objective=CampaignObjective.WEBSITE_CONVERSIONS,
    budget=500.0
)

# Get insights
insights = await client.get_insights(
    start_date="2024-01-01",
    end_date="2024-01-07"
)

# Update status
await client.pause_campaign(campaign_id)

# Don't forget to close!
await client.close()
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
