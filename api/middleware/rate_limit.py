"""
S.S.I. SHADOW - Rate Limiting Middleware (Redis-Backed)
=======================================================
Production-grade rate limiting with Redis for horizontal scaling.

Features:
- Multiple algorithms: Fixed Window, Sliding Window Log, Token Bucket
- Per-IP, per-user, per-API-key rate limiting
- Tiered limits (anonymous, authenticated, premium)
- Per-endpoint custom limits
- Distributed rate limiting with Redis
- Graceful fallback to local memory
- Standard headers (X-RateLimit-*)
- Request cost weighting

Usage:
    from api.middleware.rate_limit import RateLimitMiddleware, RateLimiter

    # Initialize with Redis
    rate_limiter = RateLimiter(redis_client=redis_client)
    
    # Add middleware to FastAPI
    app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)
    
    # Or use as dependency
    @app.get("/api/data")
    async def get_data(rate_info: dict = Depends(rate_limiter.dependency())):
        ...

Author: SSI Shadow Team
Version: 2.0.0
"""

import os
import time
import asyncio
import logging
import hashlib
from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Callable, List, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
from collections import defaultdict

from fastapi import Request, Response, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

# Try to import redis
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

logger = logging.getLogger(__name__)


# =============================================================================
# ENUMS & CONSTANTS
# =============================================================================

class RateLimitAlgorithm(Enum):
    """Available rate limiting algorithms."""
    FIXED_WINDOW = "fixed_window"
    SLIDING_WINDOW_LOG = "sliding_window_log"
    SLIDING_WINDOW_COUNTER = "sliding_window_counter"
    TOKEN_BUCKET = "token_bucket"


class RateLimitTier(Enum):
    """Rate limit tiers for different user types."""
    ANONYMOUS = "anonymous"
    AUTHENTICATED = "authenticated"
    PREMIUM = "premium"
    UNLIMITED = "unlimited"


# Default rate limits per tier (requests per minute)
DEFAULT_TIER_LIMITS = {
    RateLimitTier.ANONYMOUS: 60,
    RateLimitTier.AUTHENTICATED: 200,
    RateLimitTier.PREMIUM: 1000,
    RateLimitTier.UNLIMITED: float('inf'),
}

# Burst allowance (percentage above limit for short bursts)
DEFAULT_BURST_MULTIPLIER = 1.2


# =============================================================================
# DATA CLASSES
# =============================================================================

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting."""
    requests_per_minute: int = 100
    requests_per_hour: int = 0  # 0 = unlimited
    requests_per_day: int = 0  # 0 = unlimited
    burst_size: int = 20
    window_size_seconds: int = 60
    algorithm: RateLimitAlgorithm = RateLimitAlgorithm.FIXED_WINDOW
    
    # Token bucket specific
    refill_rate: float = 1.67  # Tokens per second (100/min)
    bucket_size: int = 100


@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    limit: int
    remaining: int
    reset_at: int  # Unix timestamp
    retry_after: int  # Seconds until next allowed request
    current_usage: int
    tier: str = "anonymous"
    
    def to_headers(self) -> Dict[str, str]:
        """Convert to HTTP headers."""
        return {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(self.reset_at),
            "X-RateLimit-Used": str(self.current_usage),
        }


@dataclass 
class RateLimitRule:
    """Custom rate limit rule for specific paths."""
    path_pattern: str  # Regex or exact path
    requests_per_minute: int
    methods: List[str] = field(default_factory=lambda: ["GET", "POST", "PUT", "DELETE"])
    description: str = ""
    cost: int = 1  # Request cost (some endpoints cost more)


# =============================================================================
# RATE LIMIT BACKENDS
# =============================================================================

class RateLimitBackend(ABC):
    """Abstract base class for rate limit backends."""
    
    @abstractmethod
    async def increment(self, key: str, window: int, limit: int) -> Tuple[int, int]:
        """
        Increment counter for a key.
        
        Returns:
            Tuple of (current_count, ttl_seconds)
        """
        pass
    
    @abstractmethod
    async def get_count(self, key: str) -> int:
        """Get current count for a key."""
        pass
    
    @abstractmethod
    async def reset(self, key: str) -> bool:
        """Reset counter for a key."""
        pass


class RedisBackend(RateLimitBackend):
    """Redis-backed rate limit storage."""
    
    def __init__(self, redis_client: "aioredis.Redis"):
        self.redis = redis_client
        self._scripts_loaded = False
        self._sliding_window_script = None
        self._token_bucket_script = None
    
    async def _load_scripts(self):
        """Load Lua scripts for atomic operations."""
        if self._scripts_loaded:
            return
        
        # Sliding window counter script (more accurate than fixed window)
        sliding_window_lua = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local window = tonumber(ARGV[2])
        local limit = tonumber(ARGV[3])
        local cost = tonumber(ARGV[4]) or 1
        
        -- Current window key
        local current_window = math.floor(now / window) * window
        local current_key = key .. ":" .. current_window
        local previous_key = key .. ":" .. (current_window - window)
        
        -- Get counts
        local current_count = tonumber(redis.call('GET', current_key) or 0)
        local previous_count = tonumber(redis.call('GET', previous_key) or 0)
        
        -- Calculate weighted count (sliding window approximation)
        local elapsed = now - current_window
        local weight = (window - elapsed) / window
        local weighted_count = current_count + (previous_count * weight)
        
        -- Check if allowed
        if weighted_count + cost > limit then
            return {0, math.ceil(weighted_count), window - elapsed}
        end
        
        -- Increment current window
        redis.call('INCRBY', current_key, cost)
        redis.call('EXPIRE', current_key, window * 2)
        
        return {1, math.ceil(weighted_count + cost), window - elapsed}
        """
        
        # Token bucket script
        token_bucket_lua = """
        local key = KEYS[1]
        local now = tonumber(ARGV[1])
        local rate = tonumber(ARGV[2])
        local capacity = tonumber(ARGV[3])
        local cost = tonumber(ARGV[4]) or 1
        
        -- Get current bucket state
        local bucket = redis.call('HMGET', key, 'tokens', 'last_update')
        local tokens = tonumber(bucket[1]) or capacity
        local last_update = tonumber(bucket[2]) or now
        
        -- Refill tokens
        local elapsed = now - last_update
        local refill = elapsed * rate
        tokens = math.min(capacity, tokens + refill)
        
        -- Check if we have enough tokens
        if tokens < cost then
            local wait_time = (cost - tokens) / rate
            return {0, math.floor(tokens), math.ceil(wait_time)}
        end
        
        -- Consume tokens
        tokens = tokens - cost
        redis.call('HMSET', key, 'tokens', tokens, 'last_update', now)
        redis.call('EXPIRE', key, 3600)
        
        return {1, math.floor(tokens), 0}
        """
        
        self._sliding_window_script = self.redis.register_script(sliding_window_lua)
        self._token_bucket_script = self.redis.register_script(token_bucket_lua)
        self._scripts_loaded = True
    
    async def increment(self, key: str, window: int, limit: int) -> Tuple[int, int]:
        """Increment counter using fixed window."""
        now = time.time()
        window_start = int(now / window) * window
        redis_key = f"ratelimit:{key}:{window_start}"
        
        pipe = self.redis.pipeline()
        pipe.incr(redis_key)
        pipe.expire(redis_key, window * 2)  # Keep for 2 windows
        results = await pipe.execute()
        
        current = results[0]
        ttl = window - (now - window_start)
        
        return current, int(ttl)
    
    async def increment_sliding_window(
        self, 
        key: str, 
        window: int, 
        limit: int,
        cost: int = 1
    ) -> Tuple[bool, int, int]:
        """
        Increment counter using sliding window algorithm.
        
        Returns:
            Tuple of (allowed, count, reset_in_seconds)
        """
        await self._load_scripts()
        
        result = await self._sliding_window_script(
            keys=[f"ratelimit:sw:{key}"],
            args=[time.time(), window, limit, cost]
        )
        
        return bool(result[0]), result[1], result[2]
    
    async def check_token_bucket(
        self,
        key: str,
        rate: float,
        capacity: int,
        cost: int = 1
    ) -> Tuple[bool, int, int]:
        """
        Check token bucket rate limit.
        
        Returns:
            Tuple of (allowed, remaining_tokens, wait_seconds)
        """
        await self._load_scripts()
        
        result = await self._token_bucket_script(
            keys=[f"ratelimit:tb:{key}"],
            args=[time.time(), rate, capacity, cost]
        )
        
        return bool(result[0]), result[1], result[2]
    
    async def get_count(self, key: str) -> int:
        """Get current count for a key."""
        now = time.time()
        window_start = int(now / 60) * 60
        redis_key = f"ratelimit:{key}:{window_start}"
        
        count = await self.redis.get(redis_key)
        return int(count) if count else 0
    
    async def reset(self, key: str) -> bool:
        """Reset all rate limit keys for an identifier."""
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


class MemoryBackend(RateLimitBackend):
    """In-memory rate limit storage (for single-instance or fallback)."""
    
    def __init__(self):
        self._counters: Dict[str, Dict[str, Any]] = defaultdict(dict)
        self._lock = asyncio.Lock()
        self._cleanup_task: Optional[asyncio.Task] = None
    
    async def start_cleanup(self):
        """Start background cleanup task."""
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())
    
    async def _cleanup_loop(self):
        """Periodically clean up expired entries."""
        while True:
            await asyncio.sleep(60)
            await self._cleanup()
    
    async def _cleanup(self):
        """Remove expired entries."""
        now = time.time()
        async with self._lock:
            expired_keys = []
            for key, data in self._counters.items():
                if data.get('expires_at', 0) < now:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._counters[key]
            
            if expired_keys:
                logger.debug(f"Cleaned up {len(expired_keys)} expired rate limit entries")
    
    async def increment(self, key: str, window: int, limit: int) -> Tuple[int, int]:
        """Increment counter using fixed window."""
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
        """Get current count for a key."""
        now = time.time()
        window_start = int(now / 60) * 60
        full_key = f"{key}:{window_start}"
        
        async with self._lock:
            data = self._counters.get(full_key, {})
            return data.get('count', 0)
    
    async def reset(self, key: str) -> bool:
        """Reset all counters for a key."""
        async with self._lock:
            keys_to_delete = [k for k in self._counters if key in k]
            for k in keys_to_delete:
                del self._counters[k]
            return len(keys_to_delete) > 0


# =============================================================================
# MAIN RATE LIMITER CLASS
# =============================================================================

class RateLimiter:
    """
    Production-grade rate limiter with Redis support.
    
    Usage:
        # Initialize with Redis client
        redis_client = redis.from_url("redis://localhost:6379")
        limiter = RateLimiter(redis_client=redis_client)
        
        # Check rate limit
        result = await limiter.check("user:123", tier=RateLimitTier.AUTHENTICATED)
        
        if not result.allowed:
            raise HTTPException(status_code=429, headers=result.to_headers())
    """
    
    def __init__(
        self,
        redis_client: Optional["aioredis.Redis"] = None,
        redis_url: str = None,
        default_config: RateLimitConfig = None,
        tier_limits: Dict[RateLimitTier, int] = None,
        custom_rules: List[RateLimitRule] = None,
        algorithm: RateLimitAlgorithm = RateLimitAlgorithm.SLIDING_WINDOW_COUNTER,
        key_prefix: str = "ssi",
        enable_logging: bool = True,
    ):
        """
        Initialize the rate limiter.
        
        Args:
            redis_client: Existing Redis client
            redis_url: Redis URL (if no client provided)
            default_config: Default rate limit configuration
            tier_limits: Per-tier rate limits (requests per minute)
            custom_rules: Custom rules for specific endpoints
            algorithm: Rate limiting algorithm to use
            key_prefix: Prefix for Redis keys
            enable_logging: Enable rate limit logging
        """
        self.config = default_config or RateLimitConfig()
        self.tier_limits = tier_limits or DEFAULT_TIER_LIMITS.copy()
        self.custom_rules = custom_rules or []
        self.algorithm = algorithm
        self.key_prefix = key_prefix
        self.enable_logging = enable_logging
        
        # Initialize backend
        self._redis_client = redis_client
        self._redis_url = redis_url or os.getenv("REDIS_URL")
        self._backend: Optional[RateLimitBackend] = None
        self._initialized = False
        
        # Fallback memory backend
        self._memory_backend = MemoryBackend()
        
        # Metrics
        self._metrics = {
            "total_requests": 0,
            "allowed_requests": 0,
            "blocked_requests": 0,
            "redis_errors": 0,
        }
    
    async def initialize(self):
        """Initialize the rate limiter (connect to Redis)."""
        if self._initialized:
            return
        
        if self._redis_client:
            self._backend = RedisBackend(self._redis_client)
            logger.info("Rate limiter initialized with provided Redis client")
        elif self._redis_url and REDIS_AVAILABLE:
            try:
                self._redis_client = await aioredis.from_url(
                    self._redis_url,
                    encoding="utf-8",
                    decode_responses=True
                )
                await self._redis_client.ping()
                self._backend = RedisBackend(self._redis_client)
                logger.info(f"Rate limiter connected to Redis: {self._redis_url}")
            except Exception as e:
                logger.warning(f"Failed to connect to Redis: {e}. Using memory backend.")
                self._backend = self._memory_backend
        else:
            logger.warning("Redis not available. Using memory backend (not suitable for multi-instance).")
            self._backend = self._memory_backend
        
        # Start memory cleanup if using memory backend
        if isinstance(self._backend, MemoryBackend):
            await self._memory_backend.start_cleanup()
        
        self._initialized = True
    
    def _get_key(self, identifier: str, scope: str = "default") -> str:
        """Generate a rate limit key."""
        return f"{self.key_prefix}:rl:{scope}:{identifier}"
    
    def _get_client_identifier(self, request: Request) -> str:
        """Extract client identifier from request."""
        # Try to get user ID from auth
        user_id = getattr(getattr(request, 'state', None), 'user_id', None)
        if user_id:
            return f"user:{user_id}"
        
        # Try to get API key
        api_key = request.headers.get("X-API-Key")
        if api_key:
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()[:16]
            return f"apikey:{key_hash}"
        
        # Fall back to IP
        client_ip = self._get_client_ip(request)
        return f"ip:{client_ip}"
    
    def _get_client_ip(self, request: Request) -> str:
        """Get client IP, handling proxies."""
        # Check forwarded headers
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        
        # Direct connection
        if request.client:
            return request.client.host
        
        return "unknown"
    
    def _get_tier(self, request: Request) -> RateLimitTier:
        """Determine the rate limit tier for a request."""
        # Check for premium/unlimited API keys
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # In production, check API key tier in database
            if api_key.startswith("ssi_premium_"):
                return RateLimitTier.PREMIUM
            return RateLimitTier.AUTHENTICATED
        
        # Check for authenticated user
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            return RateLimitTier.AUTHENTICATED
        
        return RateLimitTier.ANONYMOUS
    
    def _get_limit_for_path(self, path: str, method: str, tier: RateLimitTier) -> Tuple[int, int]:
        """
        Get rate limit for a specific path.
        
        Returns:
            Tuple of (limit, cost)
        """
        import re
        
        # Check custom rules first
        for rule in self.custom_rules:
            if re.match(rule.path_pattern, path) and method in rule.methods:
                return rule.requests_per_minute, rule.cost
        
        # Return tier limit
        limit = self.tier_limits.get(tier, self.config.requests_per_minute)
        return int(limit) if limit != float('inf') else 999999, 1
    
    async def check(
        self,
        identifier: str,
        tier: RateLimitTier = RateLimitTier.ANONYMOUS,
        limit: int = None,
        cost: int = 1,
        path: str = None,
    ) -> RateLimitResult:
        """
        Check if a request is allowed under rate limit.
        
        Args:
            identifier: Unique identifier (user_id, IP, API key)
            tier: Rate limit tier
            limit: Override limit (uses tier default if not set)
            cost: Request cost (some endpoints cost more)
            path: Request path (for per-endpoint limits)
        
        Returns:
            RateLimitResult with allowed status and metadata
        """
        await self.initialize()
        
        # Get limit
        effective_limit = limit if limit is not None else self.tier_limits.get(
            tier, self.config.requests_per_minute
        )
        
        # Handle unlimited tier
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
            # Use appropriate algorithm
            if self.algorithm == RateLimitAlgorithm.FIXED_WINDOW:
                current, ttl = await self._backend.increment(key, window, effective_limit)
                allowed = current <= effective_limit
                remaining = max(0, effective_limit - current)
                
            elif self.algorithm == RateLimitAlgorithm.SLIDING_WINDOW_COUNTER:
                if isinstance(self._backend, RedisBackend):
                    allowed, current, ttl = await self._backend.increment_sliding_window(
                        key, window, effective_limit, cost
                    )
                    remaining = max(0, effective_limit - current)
                else:
                    # Fallback to fixed window for memory backend
                    current, ttl = await self._backend.increment(key, window, effective_limit)
                    allowed = current <= effective_limit
                    remaining = max(0, effective_limit - current)
                    
            elif self.algorithm == RateLimitAlgorithm.TOKEN_BUCKET:
                if isinstance(self._backend, RedisBackend):
                    rate = effective_limit / 60  # Tokens per second
                    allowed, remaining, wait = await self._backend.check_token_bucket(
                        key, rate, effective_limit, cost
                    )
                    current = effective_limit - remaining
                    ttl = wait if not allowed else 0
                else:
                    # Fallback to fixed window
                    current, ttl = await self._backend.increment(key, window, effective_limit)
                    allowed = current <= effective_limit
                    remaining = max(0, effective_limit - current)
            else:
                # Default to fixed window
                current, ttl = await self._backend.increment(key, window, effective_limit)
                allowed = current <= effective_limit
                remaining = max(0, effective_limit - current)
            
            # Allow burst
            if not allowed and hasattr(self.config, 'burst_size'):
                burst_limit = effective_limit + self.config.burst_size
                allowed = current <= burst_limit
            
            # Update metrics
            self._metrics["total_requests"] += 1
            if allowed:
                self._metrics["allowed_requests"] += 1
            else:
                self._metrics["blocked_requests"] += 1
            
            reset_at = int(time.time()) + ttl
            retry_after = 0 if allowed else ttl
            
            result = RateLimitResult(
                allowed=allowed,
                limit=effective_limit,
                remaining=remaining,
                reset_at=reset_at,
                retry_after=retry_after,
                current_usage=current,
                tier=tier.value
            )
            
            if self.enable_logging and not allowed:
                logger.warning(
                    f"Rate limit exceeded: {identifier} "
                    f"(tier={tier.value}, limit={effective_limit}, current={current})"
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Rate limit check failed: {e}")
            self._metrics["redis_errors"] += 1
            
            # On error, allow the request (fail open)
            return RateLimitResult(
                allowed=True,
                limit=effective_limit,
                remaining=effective_limit,
                reset_at=int(time.time()) + 60,
                retry_after=0,
                current_usage=0,
                tier=tier.value
            )
    
    async def check_request(self, request: Request, cost: int = 1) -> RateLimitResult:
        """
        Check rate limit for a FastAPI request.
        
        Args:
            request: FastAPI request object
            cost: Request cost
        
        Returns:
            RateLimitResult
        """
        identifier = self._get_client_identifier(request)
        tier = self._get_tier(request)
        path = request.url.path
        method = request.method
        
        # Get path-specific limit
        limit, path_cost = self._get_limit_for_path(path, method, tier)
        effective_cost = max(cost, path_cost)
        
        return await self.check(
            identifier=identifier,
            tier=tier,
            limit=limit,
            cost=effective_cost,
            path=path
        )
    
    async def reset_limit(self, identifier: str) -> bool:
        """Reset rate limit for an identifier."""
        await self.initialize()
        key = self._get_key(identifier)
        return await self._backend.reset(key)
    
    def dependency(self, cost: int = 1):
        """
        Create a FastAPI dependency for rate limiting.
        
        Usage:
            @app.get("/api/data")
            async def get_data(rate_info: RateLimitResult = Depends(rate_limiter.dependency())):
                ...
        """
        async def rate_limit_dependency(request: Request) -> RateLimitResult:
            result = await self.check_request(request, cost)
            
            # Store in request state for middleware to add headers
            request.state.rate_limit_result = result
            
            if not result.allowed:
                raise HTTPException(
                    status_code=429,
                    detail={
                        "error": "rate_limit_exceeded",
                        "message": "Too many requests. Please try again later.",
                        "retry_after": result.retry_after,
                    },
                    headers={
                        **result.to_headers(),
                        "Retry-After": str(result.retry_after),
                    }
                )
            
            return result
        
        return rate_limit_dependency
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get rate limiter metrics."""
        return {
            **self._metrics,
            "algorithm": self.algorithm.value,
            "backend": "redis" if isinstance(self._backend, RedisBackend) else "memory",
        }
    
    async def close(self):
        """Close connections."""
        if self._redis_client and hasattr(self._redis_client, 'close'):
            await self._redis_client.close()


# =============================================================================
# FASTAPI MIDDLEWARE
# =============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    FastAPI middleware for rate limiting.
    
    Usage:
        rate_limiter = RateLimiter(redis_client=redis_client)
        app.add_middleware(RateLimitMiddleware, rate_limiter=rate_limiter)
    """
    
    def __init__(
        self,
        app: ASGIApp,
        rate_limiter: RateLimiter,
        exclude_paths: List[str] = None,
        include_paths: List[str] = None,
    ):
        """
        Initialize the middleware.
        
        Args:
            app: FastAPI application
            rate_limiter: RateLimiter instance
            exclude_paths: Paths to exclude from rate limiting
            include_paths: If set, only these paths are rate limited
        """
        super().__init__(app)
        self.rate_limiter = rate_limiter
        self.exclude_paths = set(exclude_paths or [
            "/health",
            "/healthz", 
            "/ready",
            "/metrics",
            "/docs",
            "/redoc",
            "/openapi.json",
        ])
        self.include_paths = set(include_paths) if include_paths else None
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process the request through rate limiting."""
        path = request.url.path
        
        # Check exclusions
        if path in self.exclude_paths:
            return await call_next(request)
        
        # Check inclusions
        if self.include_paths and path not in self.include_paths:
            return await call_next(request)
        
        # Skip OPTIONS requests (CORS preflight)
        if request.method == "OPTIONS":
            return await call_next(request)
        
        # Check rate limit
        result = await self.rate_limiter.check_request(request)
        
        # Store result in request state
        request.state.rate_limit_result = result
        
        if not result.allowed:
            # Return 429 Too Many Requests
            return Response(
                content='{"error":"rate_limit_exceeded","message":"Too many requests"}',
                status_code=429,
                media_type="application/json",
                headers={
                    **result.to_headers(),
                    "Retry-After": str(result.retry_after),
                }
            )
        
        # Process request
        response = await call_next(request)
        
        # Add rate limit headers to response
        for header, value in result.to_headers().items():
            response.headers[header] = value
        
        return response


# =============================================================================
# DECORATOR FOR ROUTE-LEVEL RATE LIMITING
# =============================================================================

def rate_limit(
    requests_per_minute: int = None,
    requests_per_hour: int = None,
    cost: int = 1,
    key_func: Callable[[Request], str] = None,
):
    """
    Decorator for route-level rate limiting.
    
    Usage:
        @app.get("/api/expensive")
        @rate_limit(requests_per_minute=10, cost=5)
        async def expensive_endpoint():
            ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, request: Request = None, **kwargs):
            # Get rate limiter from app state
            limiter = getattr(request.app.state, 'rate_limiter', None)
            if not limiter:
                return await func(*args, request=request, **kwargs)
            
            # Get identifier
            if key_func:
                identifier = key_func(request)
            else:
                identifier = limiter._get_client_identifier(request)
            
            # Get tier
            tier = limiter._get_tier(request)
            
            # Use custom limit or tier default
            limit = requests_per_minute or limiter.tier_limits.get(
                tier, limiter.config.requests_per_minute
            )
            
            # Check rate limit
            result = await limiter.check(
                identifier=identifier,
                tier=tier,
                limit=limit,
                cost=cost,
            )
            
            if not result.allowed:
                raise HTTPException(
                    status_code=429,
                    detail="Rate limit exceeded",
                    headers={
                        **result.to_headers(),
                        "Retry-After": str(result.retry_after),
                    }
                )
            
            return await func(*args, request=request, **kwargs)
        
        return wrapper
    return decorator


# =============================================================================
# FACTORY FUNCTIONS
# =============================================================================

_rate_limiter: Optional[RateLimiter] = None


async def init_rate_limiter(
    redis_client: "aioredis.Redis" = None,
    redis_url: str = None,
    **kwargs
) -> RateLimiter:
    """Initialize the global rate limiter."""
    global _rate_limiter
    
    _rate_limiter = RateLimiter(
        redis_client=redis_client,
        redis_url=redis_url,
        **kwargs
    )
    await _rate_limiter.initialize()
    
    return _rate_limiter


def get_rate_limiter() -> Optional[RateLimiter]:
    """Get the global rate limiter."""
    return _rate_limiter


async def close_rate_limiter():
    """Close the global rate limiter."""
    global _rate_limiter
    if _rate_limiter:
        await _rate_limiter.close()
        _rate_limiter = None


# =============================================================================
# PREDEFINED RULES FOR COMMON ENDPOINTS
# =============================================================================

DEFAULT_RATE_LIMIT_RULES = [
    # Auth endpoints - stricter limits
    RateLimitRule(
        path_pattern=r"^/api/auth/login$",
        requests_per_minute=10,
        methods=["POST"],
        description="Login endpoint",
        cost=5
    ),
    RateLimitRule(
        path_pattern=r"^/api/auth/register$",
        requests_per_minute=5,
        methods=["POST"],
        description="Registration endpoint",
        cost=10
    ),
    RateLimitRule(
        path_pattern=r"^/api/auth/forgot-password$",
        requests_per_minute=3,
        methods=["POST"],
        description="Password reset",
        cost=10
    ),
    
    # Expensive endpoints
    RateLimitRule(
        path_pattern=r"^/api/reports/generate$",
        requests_per_minute=5,
        methods=["POST"],
        description="Report generation",
        cost=20
    ),
    RateLimitRule(
        path_pattern=r"^/api/export.*$",
        requests_per_minute=10,
        methods=["GET", "POST"],
        description="Data export",
        cost=10
    ),
    
    # Webhook endpoints - higher limits
    RateLimitRule(
        path_pattern=r"^/api/webhooks/.*$",
        requests_per_minute=1000,
        methods=["POST"],
        description="Webhook receivers",
        cost=1
    ),
]


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "RateLimiter",
    "RateLimitMiddleware",
    "RateLimitConfig",
    "RateLimitResult",
    "RateLimitRule",
    "RateLimitAlgorithm",
    "RateLimitTier",
    "RateLimitBackend",
    "RedisBackend",
    "MemoryBackend",
    "rate_limit",
    "init_rate_limiter",
    "get_rate_limiter",
    "close_rate_limiter",
    "DEFAULT_RATE_LIMIT_RULES",
    "DEFAULT_TIER_LIMITS",
]
