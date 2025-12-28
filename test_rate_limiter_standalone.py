#!/usr/bin/env python3
"""
Standalone Test script for Redis Rate Limiter
Run: python test_rate_limiter_standalone.py
"""

import asyncio
import os
import sys
import time
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, Any, Tuple, List
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

# Check for redis
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False


# =============================================================================
# ENUMS & DATA CLASSES (copied from rate_limit.py for standalone test)
# =============================================================================

class RateLimitAlgorithm(Enum):
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"
    TOKEN_BUCKET = "token_bucket"


class RateLimitTier(Enum):
    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"
    PREMIUM = "premium"
    UNLIMITED = "unlimited"


DEFAULT_TIER_LIMITS = {
    RateLimitTier.ANONYMOUS: 60,
    RateLimitTier.AUTHENTICATED: 200,
    RateLimitTier.PREMIUM: 1000,
    RateLimitTier.UNLIMITED: float('inf'),
}


@dataclass
class RateLimitConfig:
    requests_per_minute: int = 100
    burst_size: int = 20
    window_size_seconds: int = 60
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.FIXED_WINDOW


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_at: int
    retry_after: int
    current_usage: int
    tier: str = "anonymous"
    
    def to_headers(self) -> Dict[str, str]:
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_at),
            "X-RateLimit-Used": str(self.current_usage),
        }


# =============================================================================
# BACKENDS
# =============================================================================

class RateLimitBackend(ABC):
    @abstractmethod
    async def increment(self, key: str, window: int, limit: int) -> Tuple[int, int]:
        pass
    
    @abstractmethod
    async def get_count(self, key: str) -> int:
        pass
    
    @abstractmethod
    async def reset(self, key: str) -> bool:
        pass


class MemoryBackend(RateLimitBackend):
    def __init__(self):
        self._counters: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._lock = asyncio.Lock()
    
    async def increment(self, key: str, window: int, limit: int) -> Tuple[int, int]:
        now = time.time()
        window_start = int(now / window) * window
        full_key = f"{key}:{window_start}"
        
        async with self._lock:
            if full_key not in self._counters:
                self._counters[full_key] = {
                    'count': 0,
                    'expires_at': window_start + window * 2
                }
            
            self._counters[full_key]['count'] += 1
            current = self._counters[full_key]['count']
        
        ttl = window - (now - window_start)
        return current, int(ttl)
    
    async def get_count(self, key: str) -> int:
        now = time.time()
        window_start = int(now / 60) * 60
        full_key = f"{key}:{window_start}"
        
        async with self._lock:
            data = self._counters.get(full_key, {})
            return data.get('count', 0)
    
    async def reset(self, key: str) -> bool:
        async with self._lock:
            keys_to_delete = [k for k in self._counters if key in k]
            for k in keys_to_delete:
                del self._counters[k]
            return len(keys_to_delete) > 0


class RedisBackend(RateLimitBackend):
    def __init__(self, redis_client):
        self.redis = redis_client
    
    async def increment(self, key: str, window: int, limit: int) -> Tuple[int, int]:
        now = time.time()
        window_start = int(now / window) * window
        redis_key = f"ratelimit:{key}:{window_start}"
        
        pipe = self.redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window * 2)
        results = await pipe.execute()
        
        current = results[0]
        ttl = window - (now - window_start)
        
        return current, int(ttl)
    
    async def get_count(self, key: str) -> int:
        now = time.time()
        window_start = int(now / 60) * 60
        redis_key = f"ratelimit:{key}:{window_start}"
        
        count = await self.redis.get(redis_key)
        return int(count) if count else 0
    
    async def reset(self, key: str) -> bool:
        pattern = f"ratelimit:*{key}*"
        cursor = 0
        deleted = 0
        
        while True:
            cursor, keys = await self.redis.scan(cursor, match=pattern, count=100)
            if keys:
                deleted += await self.redis.delete(*keys)
            if cursor == 0:
                break
        
        return deleted > 0


# =============================================================================
# RATE LIMITER
# =============================================================================

class RateLimiter:
    def __init__(
        self,
        redis_client=None,
        redis_url: str = None,
        default_config: RateLimitConfig = None,
        tier_limits: Dict[RateLimitTier, int] = None,
        algorithm: RateLimitAlgorithm = RateLimitAlgorithm.FIXED_WINDOW,
        key_prefix: str = "ssi",
    ):
        self.config = default_config or RateLimitConfig()
        self.tier_limits = tier_limits or DEFAULT_TIER_LIMITS.copy()
        self.algorithm = algorithm
        self.key_prefix = key_prefix
        
        self._redis_client = redis_client
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._backend: Optional[RateLimitBackend] = None
        self._initialized = False
        self._memory_backend = MemoryBackend()
        
        self._metrics = {
            "total_requests": 0,
            "allowed_requests": 0,
            "blocked_requests": 0,
            "redis_errors": 0,
        }
    
    async def initialize(self):
        if self._initialized:
            return
        
        if self._redis_client:
            self._backend = RedisBackend(self._redis_client)
            print("   ✅ Rate limiter initialized with Redis client")
        elif self._redis_url and REDIS_AVAILABLE:
            try:
                self._redis_client = await aioredis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                await self._redis_client.ping()
                self._backend = RedisBackend(self._redis_client)
                print(f"   ✅ Rate limiter connected to Redis: {self._redis_url}")
            except Exception as e:
                print(f"   ⚠️  Redis connection failed: {e}. Using memory backend.")
                self._backend = self._memory_backend
        else:
            print("   ⚠️  Redis not available. Using memory backend.")
            self._backend = self._memory_backend
        
        self._initialized = True
    
    def _get_key(self, identifier: str, scope: str = "default") -> str:
        return f"{self.key_prefix}:rl:{scope}:{identifier}"
    
    async def check(
        self,
        identifier: str,
        tier: RateLimitTier = RateLimitTier.ANONYMOUS,
        limit: int = None,
        cost: int = 1,
    ) -> RateLimitResult:
        await self.initialize()
        
        effective_limit = limit if limit is not None else self.tier_limits.get(
            tier, self.config.requests_per_minute
        )
        
        if effective_limit == float('inf'):
            return RateLimitResult(
                allowed=True,
                limit=999999,
                remaining=999999,
                reset_at=int(time.time()) + 60,
                retry_after=0,
                current_usage=0,
                tier=tier.value
            )
        
        effective_limit = int(effective_limit)
        key = self._get_key(identifier)
        window = self.config.window_size_seconds
        
        try:
            current, ttl = await self._backend.increment(key, window, effective_limit)
            
            allowed = current <= effective_limit
            remaining = max(0, effective_limit - current)
            
            # Allow burst
            if not allowed and current <= effective_limit + self.config.burst_size:
                allowed = True
            
            self._metrics["total_requests"] += 1
            if allowed:
                self._metrics["allowed_requests"] += 1
            else:
                self._metrics["blocked_requests"] += 1
            
            reset_at = int(time.time()) + ttl
            retry_after = 0 if allowed else ttl
            
            return RateLimitResult(
                allowed=allowed,
                limit=effective_limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
                current_usage=current,
                tier=tier.value
            )
            
        except Exception as e:
            print(f"   ❌ Rate limit error: {e}")
            self._metrics["redis_errors"] += 1
            
            return RateLimitResult(
                allowed=True,
                limit=effective_limit,
                remaining=effective_limit,
                reset_at=int(time.time()) + 60,
                retry_after=0,
                current_usage=0,
                tier=tier.value
            )
    
    async def reset_limit(self, identifier: str) -> bool:
        await self.initialize()
        key = self._get_key(identifier)
        return await self._backend.reset(key)
    
    def get_metrics(self) -> Dict[str, Any]:
        return {
            **self._metrics,
            "algorithm": self.algorithm.value,
            "backend": "redis" if isinstance(self._backend, RedisBackend) else "memory",
        }
    
    async def close(self):
        if self._redis_client and hasattr(self._redis_client, 'close'):
            await self._redis_client.close()


# =============================================================================
# MOCK REDIS FOR TESTING
# =============================================================================

class MockRedis:
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
    
    async def close(self):
        pass


class MockPipeline:
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


# =============================================================================
# TESTS
# =============================================================================

async def test_memory_backend():
    """Test memory backend."""
    print("\n" + "=" * 60)
    print("🧪 Testing Memory Backend")
    print("=" * 60)
    
    limiter = RateLimiter(
        default_config=RateLimitConfig(requests_per_minute=5, burst_size=2)
    )
    await limiter.initialize()
    
    print(f"\n📋 Config: 5 req/min, burst=2")
    
    results = []
    for i in range(10):
        # Pass explicit limit to override tier default
        result = await limiter.check("test_user", limit=5)
        results.append(result)
        status = "✅ Allowed" if result.allowed else "❌ Blocked"
        print(f"   Request {i+1}: {status} (remaining={result.remaining})")
    
    allowed_count = sum(1 for r in results if r.allowed)
    print(f"\n📊 Results: {allowed_count}/10 allowed (limit=5, burst=2, expected=7)")
    
    assert allowed_count == 7, f"Expected 7, got {allowed_count}"
    
    await limiter.close()
    print("\n✅ Memory backend test passed!")


async def test_redis_backend():
    """Test Redis backend with mock."""
    print("\n" + "=" * 60)
    print("🧪 Testing Redis Backend (Mock)")
    print("=" * 60)
    
    mock_redis = MockRedis()
    limiter = RateLimiter(
        redis_client=mock_redis,
        default_config=RateLimitConfig(requests_per_minute=5, burst_size=0)
    )
    await limiter.initialize()
    
    print(f"\n📋 Config: 5 req/min, no burst")
    
    results = []
    for i in range(8):
        result = await limiter.check("redis_user", limit=5)
        results.append(result)
        status = "✅" if result.allowed else "❌"
        print(f"   Request {i+1}: {status} remaining={result.remaining}")
    
    allowed_count = sum(1 for r in results if r.allowed)
    print(f"\n📊 Results: {allowed_count}/8 allowed (expected=5)")
    
    assert allowed_count == 5, f"Expected 5, got {allowed_count}"
    
    await limiter.close()
    print("\n✅ Redis backend test passed!")


async def test_tier_limits():
    """Test different tier limits."""
    print("\n" + "=" * 60)
    print("🧪 Testing Tier Limits")
    print("=" * 60)
    
    limiter = RateLimiter()
    await limiter.initialize()
    
    print(f"\n📋 Tier Limits:")
    for tier, limit in DEFAULT_TIER_LIMITS.items():
        limit_str = str(limit) if limit != float('inf') else "∞"
        print(f"   {tier.value}: {limit_str} req/min")
    
    # Test each tier
    result_anon = await limiter.check("user1", tier=RateLimitTier.ANONYMOUS)
    result_auth = await limiter.check("user2", tier=RateLimitTier.AUTHENTICATED)
    result_premium = await limiter.check("user3", tier=RateLimitTier.PREMIUM)
    result_unlimited = await limiter.check("user4", tier=RateLimitTier.UNLIMITED)
    
    print(f"\n📊 Limits applied:")
    print(f"   Anonymous: {result_anon.limit}")
    print(f"   Authenticated: {result_auth.limit}")
    print(f"   Premium: {result_premium.limit}")
    print(f"   Unlimited: {result_unlimited.limit}")
    
    assert result_anon.limit == 60
    assert result_auth.limit == 200
    assert result_premium.limit == 1000
    assert result_unlimited.limit == 999999
    
    await limiter.close()
    print("\n✅ Tier limits test passed!")


async def test_rate_limit_headers():
    """Test rate limit headers."""
    print("\n" + "=" * 60)
    print("🧪 Testing Rate Limit Headers")
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
    
    print(f"\n📋 Headers:")
    for key, value in headers.items():
        print(f"   {key}: {value}")
    
    assert headers["X-RateLimit-Limit"] == "100"
    assert headers["X-RateLimit-Remaining"] == "95"
    assert headers["X-RateLimit-Used"] == "5"
    
    print("\n✅ Headers test passed!")


async def test_reset_limit():
    """Test resetting rate limits."""
    print("\n" + "=" * 60)
    print("🧪 Testing Reset Limit")
    print("=" * 60)
    
    limiter = RateLimiter(
        default_config=RateLimitConfig(requests_per_minute=3, burst_size=0)
    )
    await limiter.initialize()
    
    # Use up the limit
    print(f"\n📋 Using up limit (3 requests)...")
    for i in range(3):
        await limiter.check("reset_user", limit=3)
    
    result_before = await limiter.check("reset_user", limit=3)
    print(f"   Before reset: allowed={result_before.allowed}")
    
    # Reset
    await limiter.reset_limit("reset_user")
    print(f"   Reset performed")
    
    result_after = await limiter.check("reset_user", limit=3)
    print(f"   After reset: allowed={result_after.allowed}")
    
    assert result_before.allowed == False
    assert result_after.allowed == True
    
    await limiter.close()
    print("\n✅ Reset limit test passed!")


async def test_metrics():
    """Test metrics collection."""
    print("\n" + "=" * 60)
    print("🧪 Testing Metrics")
    print("=" * 60)
    
    limiter = RateLimiter(
        default_config=RateLimitConfig(requests_per_minute=3, burst_size=0)
    )
    await limiter.initialize()
    
    # Make requests
    for _ in range(5):
        await limiter.check("metrics_user", limit=3)
    
    metrics = limiter.get_metrics()
    
    print(f"\n📊 Metrics:")
    for key, value in metrics.items():
        print(f"   {key}: {value}")
    
    assert metrics["total_requests"] == 5
    assert metrics["allowed_requests"] == 3
    assert metrics["blocked_requests"] == 2
    
    await limiter.close()
    print("\n✅ Metrics test passed!")


async def test_concurrent_requests():
    """Test concurrent requests."""
    print("\n" + "=" * 60)
    print("🧪 Testing Concurrent Requests")
    print("=" * 60)
    
    limiter = RateLimiter(
        default_config=RateLimitConfig(requests_per_minute=10, burst_size=0)
    )
    await limiter.initialize()
    
    # Make concurrent requests
    print(f"\n📋 Making 15 concurrent requests (limit=10)...")
    
    async def make_request(i):
        result = await limiter.check(f"concurrent_user", limit=10)
        return result.allowed
    
    tasks = [make_request(i) for i in range(15)]
    results = await asyncio.gather(*tasks)
    
    allowed_count = sum(1 for r in results if r)
    blocked_count = sum(1 for r in results if not r)
    
    print(f"\n📊 Results:")
    print(f"   Allowed: {allowed_count}")
    print(f"   Blocked: {blocked_count}")
    
    assert allowed_count == 10, f"Expected 10 allowed, got {allowed_count}"
    
    await limiter.close()
    print("\n✅ Concurrent requests test passed!")


async def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 REDIS RATE LIMITER - STANDALONE TEST SUITE")
    print("=" * 60)
    print(f"📦 Redis library available: {REDIS_AVAILABLE}")
    
    try:
        await test_memory_backend()
        await test_redis_backend()
        await test_tier_limits()
        await test_rate_limit_headers()
        await test_reset_limit()
        await test_metrics()
        await test_concurrent_requests()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        
        print("\n📖 USAGE IN FASTAPI:")
        print("-" * 40)
        print("""
from fastapi import FastAPI, Depends, HTTPException
import redis.asyncio as redis
from api.middleware.rate_limit import (
    RateLimiter,
    RateLimitMiddleware,
    RateLimitTier
)

app = FastAPI()

# Initialize rate limiter with Redis
redis_client = redis.from_url("redis://localhost:6379")
rate_limiter = RateLimiter(redis_client=redis_client)

@app.on_event("startup")
async def startup():
    await rate_limiter.initialize()

# Add as middleware (applies to all routes)
app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)

# Or use as dependency for specific routes
@app.get("/api/data")
async def get_data(
    rate_info = Depends(rate_limiter.dependency())
):
    return {
        "data": "...",
        "rate_limit_remaining": rate_info.remaining
    }

# Custom limits per route
@app.post("/api/expensive")
async def expensive_operation(
    rate_info = Depends(rate_limiter.dependency(cost=10))
):
    return {"result": "..."}
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
