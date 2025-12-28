#!/usr/bin/env python3
"""
S.S.I. SHADOW - Deployment Validation Script
Run this after deployment to verify all systems are working.
"""

import asyncio
import sys
import os
import httpx

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


async def check_api_health(base_url: str) -> bool:
    """Check API health endpoint."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/health")
            data = response.json()
            return data.get("status") == "healthy"
    except Exception as e:
        print(f"❌ API health check failed: {e}")
        return False


async def check_detailed_health(base_url: str) -> dict:
    """Get detailed health status."""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{base_url}/health/detailed")
            return response.json()
    except Exception as e:
        print(f"❌ Detailed health check failed: {e}")
        return {"status": "error", "error": str(e)}


def check_environment_variables() -> list:
    """Check required environment variables are set."""
    required = [
        "GCP_PROJECT_ID",
        "BQ_DATASET",
        "REDIS_URL",
    ]
    
    optional = [
        "META_ACCESS_TOKEN",
        "GOOGLE_ADS_DEVELOPER_TOKEN",
        "OPENWEATHER_API_KEY",
    ]
    
    missing = []
    for var in required:
        if not os.getenv(var):
            missing.append(var)
    
    warnings = []
    for var in optional:
        if not os.getenv(var):
            warnings.append(var)
    
    return missing, warnings


async def main():
    """Run all deployment checks."""
    print("=" * 60)
    print("S.S.I. SHADOW - Deployment Validation")
    print("=" * 60)
    print()
    
    base_url = os.getenv("API_URL", "http://localhost:8000")
    
    # Check environment variables
    print("📋 Checking environment variables...")
    missing, warnings = check_environment_variables()
    
    if missing:
        print(f"❌ Missing required variables: {', '.join(missing)}")
    else:
        print("✅ All required variables set")
    
    if warnings:
        print(f"⚠️  Optional variables not set: {', '.join(warnings)}")
    
    print()
    
    # Check API health
    print(f"🔍 Checking API health at {base_url}...")
    
    if await check_api_health(base_url):
        print("✅ API is healthy")
    else:
        print("❌ API is not healthy")
    
    print()
    
    # Get detailed health
    print("📊 Detailed health status:")
    health = await check_detailed_health(base_url)
    
    if "checks" in health:
        for service, status in health["checks"].items():
            icon = "✅" if status.get("status") == "healthy" else "❌"
            print(f"   {icon} {service}: {status.get('status', 'unknown')}")
    
    print()
    print("=" * 60)
    print("Validation complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
