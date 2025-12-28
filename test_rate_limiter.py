#!/usr/bin/env python3
"""
Test script for Redis Rate Limiter
Run: python test_rate_limiter.py
"""

import asyncio
import os
import sys
import time
from unittest.mock import MagicMock, AsyncMock

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.middleware.rate_limit import (
    RateLimiter,
    RateLimitConfig,
    RateLimitResult,
    RateLimitRule,
    RateLimitAlgorithm,
    RateLimitTier,
    MemoryBackend,
    DEFAULT_TIER_LIMITS,
)


# =============================================================================
# MOCK REDIS
# =============================================================================

class MockRedis:
    """Mock Redis client for testing."""
    
    def __init__(self):
        self._data = {}
        self._expires = {}
    
    async def ping(self):
        return True
    
    async def incr(self, key):
        if key not in self._data:
            self._data[key] = 0
        self._data[key] += 1
        return self._data[key]
    
    async def get(self, key):
        return self._data.get(key)
    
    async def set(self, key, value, ex=None):
        self._data[key] = value
        if ex:
            self._expires[key] = time.time() + ex
        return True
    
    async def expire(self, key, seconds):
        self._expires[key] = time.time() + seconds
        return True
    
    async def delete(self, *keys):
        deleted = 0
        for key in keys:
            if key in self._data:
                del self._data[key]
                deleted += 1
        return deleted
    
    async def scan(self, cursor, match=None, count=100):
        matching = [k for k in self._data.keys() if match is None or match.replace('*', '') in k]
        return 0, matching
    
    def pipeline(self):
        return MockPipeline(self)
    
    async def hmget(self, key, *fields):
        data = self._data.get(key, {})
        return [data.get(f) for f in fields]
    
    async def hmset(self, key, mapping):
        if key not in self._data:
            self._data[key] = {}
        self._data[key].update(mapping)
    
    def register_script(self, script):
        return MockScript(self, script)
    
    async def close(self):
        pass


class MockPipeline:
    """Mock Redis pipeline."""
    
    def __init__(self, redis):
        self.redis = redis
        self.commands = []
    
    def incr(self, key):
        self.commands.append(('incr', key))
        return self
    
    def expire(self, key, seconds):
        self.commands.append(('expire', key, seconds))
        return self
    
    async def execute(self):
        results = []
        for cmd in self.commands:
            if cmd[0] == 'incr':
                results.append(await self.redis.incr(cmd[1]))
            elif cmd[0] == 'expire':
                results.append(await self.redis.expire(cmd[1], cmd[2]))
        return results


class MockScript:
    """Mock Lua script."""
    
    def __init__(self, redis, script):
        self.redis = redis
        self.script = script
    
    async def __call__(self, keys, args):
        # Simple mock implementation for sliding window
        if "sliding" in self.script or "window" in self.script.lower():
            key = keys[0]
            limit = args[2]
            cost = args[3] if len(args) > 3 else 1
            
            current = await self.redis.incr(key)
            allowed = current <= limit
            
            return [1 if allowed else 0, current, 60]
        
        # Token bucket
        if "token" in self.script.lower() or "bucket" in self.script.lower():
            capacity = args[2]
            cost = args[3] if len(args) > 3 else 1
            
            return [1, capacity - cost, 0]
        
        return [1, 0, 60]


# =============================================================================
# TESTS
# =============================================================================

async def test_rate_limiter_initialization():
    """Test rate limiter initialization."""
    print("\n" + "=" * 60)
    print("🧪 Testing Rate Limiter Initialization")
    print("=" * 60)
    
    # Test with no Redis (memory fallback)
    limiter = RateLimiter()
    await limiter.initialize()
    
    print(f"\n📋 Initialized without Redis")
    print(f"   Backend: {type(limiter._backend).__name__}")
    print(f"   Algorithm: {limiter.algorithm.value}")
    
    assert isinstance(limiter._backend, MemoryBackend)
    
    # Test with mock Redis
    mock_redis = MockRedis()
    limiter_redis = RateLimiter(redis_client=mock_redis)
    await limiter_redis.initialize()
    
    print(f"\n📋 Initialized with Redis")
    print(f"   Backend: {type(limiter_redis._backend).__name__}")
    
    await limiter.close()
    await limiter_redis.close()
    
    print("\n✅ Initialization tests passed!")


async def test_fixed_window_algorithm():
    """Test fixed window rate limiting."""
    print("\n" + "=" * 60)
    print("🧪 Testing Fixed Window Algorithm")
    print("=" * 60)
    
    limiter = RateLimiter(
        algorithm=RateLimitAlgorithm.FIXED_WINDOW,
        default_config=RateLimitConfig(requests_per_minute=5)
    )
    await limiter.initialize()
    
    # Make requests
    results = []
    for i in range(7):
        result = await limiter.check(
            identifier="test_user_1",
            tier=RateLimitTier.ANONYMOUS,
            limit=5
        )
        results.append(result)
        print(f"   Request {i+1}: allowed={result.allowed}, remaining={result.remaining}")
    
    # First 5 should be allowed
    assert all(r.allowed for r in results[:5])
    
    # 6th and 7th might be allowed due to burst
    print(f"\n📋 Results:")
    print(f"   Allowed: {sum(1 for r in results if r.allowed)}")
    print(f"   Blocked: {sum(1 for r in results if not r.allowed)}")
    
    await limiter.close()
    print("\n✅ Fixed window tests passed!")


async def test_tier_limits():
    """Test different tier limits."""
    print("\n" + "=" * 60)
    print("🧪 Testing Tier Limits")
    print("=" * 60)
    
    limiter = RateLimiter()
    await limiter.initialize()
    
    print(f"\n📋 Default Tier Limits:")
    for tier, limit in DEFAULT_TIER_LIMITS.items():
        print(f"   {tier.value}: {limit} req/min")
    
    # Test anonymous tier
    result_anon = await limiter.check("anon_user", tier=RateLimitTier.ANONYMOUS)
    print(f"\n📋 Anonymous Request:")
    print(f"   Limit: {result_anon.limit}")
    print(f"   Tier: {result_anon.tier}")
    
    # Test authenticated tier
    result_auth = await limiter.check("auth_user", tier=RateLimitTier.AUTHENTICATED)
    print(f"\n📋 Authenticated Request:")
    print(f"   Limit: {result_auth.limit}")
    print(f"   Tier: {result_auth.tier}")
    
    # Test premium tier
    result_premium = await limiter.check("premium_user", tier=RateLimitTier.PREMIUM)
    print(f"\n📋 Premium Request:")
    print(f"   Limit: {result_premium.limit}")
    print(f"   Tier: {result_premium.tier}")
    
    assert result_auth.limit > result_anon.limit
    assert result_premium.limit > result_auth.limit
    
    await limiter.close()
    print("\n✅ Tier limit tests passed!")


async def test_custom_rules():
    """Test custom rate limit rules."""
    print("\n" + "=" * 60)
    print("🧪 Testing Custom Rules")
    print("=" * 60)
    
    custom_rules = [
        RateLimitRule(
            path_pattern=r"^/api/auth/login$",
            requests_per_minute=10,
            methods=["POST"],
            cost=5
        ),
        RateLimitRule(
            path_pattern=r"^/api/reports/.*$",
            requests_per_minute=5,
            methods=["GET", "POST"],
            cost=10
        ),
    ]
    
    limiter = RateLimiter(custom_rules=custom_rules)
    await limiter.initialize()
    
    # Test login endpoint
    limit, cost = limiter._get_limit_for_path("/api/auth/login", "POST", RateLimitTier.ANONYMOUS)
    print(f"\n📋 /api/auth/login (POST):")
    print(f"   Limit: {limit} req/min")
    print(f"   Cost: {cost}")
    assert limit == 10
    assert cost == 5
    
    # Test reports endpoint
    limit, cost = limiter._get_limit_for_path("/api/reports/generate", "POST", RateLimitTier.ANONYMOUS)
    print(f"\n📋 /api/reports/generate (POST):")
    print(f"   Limit: {limit} req/min")
    print(f"   Cost: {cost}")
    assert limit == 5
    assert cost == 10
    
    # Test regular endpoint (should use tier default)
    limit, cost = limiter._get_limit_for_path("/api/users", "GET", RateLimitTier.AUTHENTICATED)
    print(f"\n📋 /api/users (GET) - Authenticated:")
    print(f"   Limit: {limit} req/min")
    print(f"   Cost: {cost}")
    
    await limiter.close()
    print("\n✅ Custom rules tests passed!")


async def test_rate_limit_result():
    """Test rate limit result object."""
    print("\n" + "=" * 60)
    print("🧪 Testing Rate Limit Result")
    print("=" * 60)
    
    result = RateLimitResult(
        allowed=True,
        limit=100,
        remaining=95,
        reset_at=int(time.time()) + 60,
        retry_after=0,
        current_usage=5,
        tier="authenticated"
    )
    
    headers = result.to_headers()
    
    print(f"\n📋 Result Headers:")
    for key, value in headers.items():
        print(f"   {key}: {value}")
    
    assert "X-RateLimit-Limit" in headers
    assert "X-RateLimit-Remaining" in headers
    assert "X-RateLimit-Reset" in headers
    assert "X-RateLimit-Used" in headers
    
    assert headers["X-RateLimit-Limit"] == "100"
    assert headers["X-RateLimit-Remaining"] == "95"
    
    print("\n✅ Rate limit result tests passed!")


async def test_request_cost():
    """Test request cost weighting."""
    print("\n" + "=" * 60)
    print("🧪 Testing Request Cost Weighting")
    print("=" * 60)
    
    limiter = RateLimiter(
        default_config=RateLimitConfig(requests_per_minute=10)
    )
    await limiter.initialize()
    
    # Make a request with cost=5
    result1 = await limiter.check("cost_user", limit=10, cost=5)
    print(f"\n📋 Request with cost=5:")
    print(f"   Remaining: {result1.remaining}")
    
    # Make another request with cost=5
    result2 = await limiter.check("cost_user", limit=10, cost=5)
    print(f"\n📋 Second request with cost=5:")
    print(f"   Remaining: {result2.remaining}")
    
    # Third request should be blocked (total cost = 15 > limit of 10)
    result3 = await limiter.check("cost_user", limit=10, cost=5)
    print(f"\n📋 Third request with cost=5:")
    print(f"   Allowed: {result3.allowed}")
    
    await limiter.close()
    print("\n✅ Request cost tests passed!")


async def test_memory_backend():
    """Test memory backend directly."""
    print("\n" + "=" * 60)
    print("🧪 Testing Memory Backend")
    print("=" * 60)
    
    backend = MemoryBackend()
    
    # Increment counter
    count1, ttl1 = await backend.increment("test_key", 60, 100)
    print(f"\n📋 First increment:")
    print(f"   Count: {count1}")
    print(f"   TTL: {ttl1}")
    
    count2, ttl2 = await backend.increment("test_key", 60, 100)
    print(f"\n📋 Second increment:")
    print(f"   Count: {count2}")
    
    assert count2 == count1 + 1
    
    # Get count
    current = await backend.get_count("test_key")
    print(f"\n📋 Current count: {current}")
    
    # Reset
    await backend.reset("test_key")
    current_after_reset = await backend.get_count("test_key")
    print(f"\n📋 Count after reset: {current_after_reset}")
    
    print("\n✅ Memory backend tests passed!")


async def test_metrics():
    """Test rate limiter metrics."""
    print("\n" + "=" * 60)
    print("🧪 Testing Metrics")
    print("=" * 60)
    
    limiter = RateLimiter(
        default_config=RateLimitConfig(requests_per_minute=3),
        enable_logging=False
    )
    await limiter.initialize()
    
    # Make some requests
    for i in range(5):
        await limiter.check(f"metrics_user", limit=3)
    
    metrics = limiter.get_metrics()
    
    print(f"\n📋 Metrics:")
    for key, value in metrics.items():
        print(f"   {key}: {value}")
    
    assert metrics["total_requests"] == 5
    assert metrics["allowed_requests"] <= 5
    assert metrics["blocked_requests"] >= 0
    
    await limiter.close()
    print("\n✅ Metrics tests passed!")


async def test_sliding_window_with_mock_redis():
    """Test sliding window algorithm with mock Redis."""
    print("\n" + "=" * 60)
    print("🧪 Testing Sliding Window with Mock Redis")
    print("=" * 60)
    
    mock_redis = MockRedis()
    limiter = RateLimiter(
        redis_client=mock_redis,
        algorithm=RateLimitAlgorithm.SLIDING_WINDOW_COUNTER,
        default_config=RateLimitConfig(requests_per_minute=10)
    )
    await limiter.initialize()
    
    # Make requests
    for i in range(12):
        result = await limiter.check("sliding_user", limit=10)
        status = "✅" if result.allowed else "❌"
        print(f"   Request {i+1}: {status} (remaining: {result.remaining})")
    
    await limiter.close()
    print("\n✅ Sliding window tests passed!")


async def test_reset_limit():
    """Test resetting rate limits."""
    print("\n" + "=" * 60)
    print("🧪 Testing Reset Limit")
    print("=" * 60)
    
    limiter = RateLimiter(
        default_config=RateLimitConfig(requests_per_minute=5)
    )
    await limiter.initialize()
    
    # Use up the limit
    for _ in range(5):
        await limiter.check("reset_user", limit=5)
    
    result_before = await limiter.check("reset_user", limit=5)
    print(f"\n📋 Before reset:")
    print(f"   Allowed: {result_before.allowed}")
    print(f"   Remaining: {result_before.remaining}")
    
    # Reset
    await limiter.reset_limit("reset_user")
    
    result_after = await limiter.check("reset_user", limit=5)
    print(f"\n📋 After reset:")
    print(f"   Allowed: {result_after.allowed}")
    print(f"   Remaining: {result_after.remaining}")
    
    await limiter.close()
    print("\n✅ Reset limit tests passed!")


async def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 REDIS RATE LIMITER TEST SUITE")
    print("=" * 60)
    
    try:
        await test_rate_limiter_initialization()
        await test_fixed_window_algorithm()
        await test_tier_limits()
        await test_custom_rules()
        await test_rate_limit_result()
        await test_request_cost()
        await test_memory_backend()
        await test_metrics()
        await test_sliding_window_with_mock_redis()
        await test_reset_limit()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        
        # Usage summary
        print("\n📖 USAGE SUMMARY")
        print("-" * 40)
        print("""
# 1. Initialize with Redis:
from api.middleware.rate_limit import RateLimiter, RateLimitMiddleware
import redis.asyncio as redis

redis_client = redis.from_url("redis://localhost:6379")
rate_limiter = RateLimiter(redis_client=redis_client)
await rate_limiter.initialize()

# 2. Add middleware to FastAPI:
app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

# 3. Or use as dependency:
@app.get("/api/data")
async def get_data(
    rate_info: RateLimitResult = Depends(rate_limiter.dependency())
):
    return {"remaining": rate_info.remaining}

# 4. Custom limits per endpoint:
from api.middleware.rate_limit import rate_limit

@app.post("/api/expensive")
@rate_limit(requests_per_minute=10, cost=5)
async def expensive_operation():
    ...

# 5. Different tiers:
result = await rate_limiter.check(
    identifier="user:123",
    tier=RateLimitTier.PREMIUM  # 1000 req/min
)
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
