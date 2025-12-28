"""
S.S.I. SHADOW - Redis Cache Decorator (C3)
==========================================

Cache inteligente com Redis para acelerar Dashboard e APIs.

Features:
- Decorator simples para funções async
- Invalidação inteligente por tags
- TTL configurável por tipo de dado
- Fallback para memória local
- Métricas de hit/miss
- Cache warming

Uso:
    from api.middleware.cache import cache, invalidate_cache
    
    @cache(ttl=300, tags=['dashboard', 'metrics'])
    async def get_dashboard_metrics(org_id: str):
        # Query pesada do BigQuery
        return await fetch_from_bigquery()
    
    # Invalidar quando dados mudam
    await invalidate_cache(tags=['dashboard'])

Performance:
    - Sem cache: ~2s (BigQuery query)
    - Com cache: ~5ms (Redis GET)
    - Melhoria: 400x mais rápido

Author: SSI Shadow Team
Version: 1.0.0
"""

import os
import json
import time
import asyncio
import hashlib
import logging
import pickle
from datetime import datetime, timedelta
from typing import (
    Optional, Dict, Any, List, Callable, TypeVar, 
    Union, Set, Awaitable, Tuple
)
from dataclasses import dataclass, field
from functools import wraps
from enum import Enum
import inspect

# Redis
try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    aioredis = None
    REDIS_AVAILABLE = False

# Local imports
from monitoring.metrics import metrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('cache')

# Type variable for generic return types
T = TypeVar('T')


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class CacheConfig:
    """Cache configuration."""
    redis_url: str = field(default_factory=lambda: os.getenv('REDIS_URL', 'redis://localhost:6379'))
    default_ttl: int = field(default_factory=lambda: int(os.getenv('CACHE_DEFAULT_TTL', '300')))
    key_prefix: str = field(default_factory=lambda: os.getenv('CACHE_KEY_PREFIX', 'ssi:cache:'))
    max_key_length: int = 200
    max_value_size_mb: int = 10
    enable_local_fallback: bool = True
    local_max_items: int = 1000
    enable_compression: bool = True
    compression_threshold: int = 1024  # Compress if larger than 1KB
    enable_metrics: bool = True
    warm_on_startup: bool = False


# Global config
config = CacheConfig()


# =============================================================================
# TTL PRESETS
# =============================================================================

class CacheTTL(Enum):
    """Predefined TTL values for common use cases."""
    REALTIME = 10           # 10 seconds - near real-time data
    SHORT = 60              # 1 minute - frequently changing data
    MEDIUM = 300            # 5 minutes - dashboard data
    LONG = 3600             # 1 hour - stable data
    DAILY = 86400           # 24 hours - rarely changing data
    WEEKLY = 604800         # 7 days - static data
    
    # Specific use cases
    DASHBOARD_OVERVIEW = 60     # Refresh every minute
    DASHBOARD_CHARTS = 300      # Refresh every 5 minutes
    CAMPAIGN_LIST = 120         # Refresh every 2 minutes
    CAMPAIGN_DETAIL = 60        # Refresh every minute
    USER_PROFILE = 3600         # Refresh every hour
    REPORTS = 1800              # Refresh every 30 minutes
    STATIC_CONFIG = 86400       # Refresh daily


# =============================================================================
# SERIALIZATION
# =============================================================================

class CacheSerializer:
    """Handles serialization/deserialization of cached values."""
    
    @staticmethod
    def serialize(value: Any, compress: bool = False) -> bytes:
        """Serialize value to bytes."""
        try:
            # Try JSON first (more portable)
            data = json.dumps(value, default=str).encode('utf-8')
            prefix = b'json:'
        except (TypeError, ValueError):
            # Fall back to pickle for complex objects
            data = pickle.dumps(value)
            prefix = b'pickle:'
        
        if compress and len(data) > config.compression_threshold:
            import zlib
            data = zlib.compress(data)
            prefix = b'z' + prefix  # zjson: or zpickle:
        
        return prefix + data
    
    @staticmethod
    def deserialize(data: bytes) -> Any:
        """Deserialize bytes to value."""
        if data.startswith(b'zjson:'):
            import zlib
            data = zlib.decompress(data[6:])
            return json.loads(data.decode('utf-8'))
        elif data.startswith(b'zpickle:'):
            import zlib
            data = zlib.decompress(data[8:])
            return pickle.loads(data)
        elif data.startswith(b'json:'):
            return json.loads(data[5:].decode('utf-8'))
        elif data.startswith(b'pickle:'):
            return pickle.loads(data[7:])
        else:
            # Legacy format - try JSON
            return json.loads(data.decode('utf-8'))


# =============================================================================
# CACHE BACKENDS
# =============================================================================

class CacheBackend:
    """Abstract cache backend."""
    
    async def get(self, key: str) -> Optional[bytes]:
        raise NotImplementedError
    
    async def set(self, key: str, value: bytes, ttl: int) -> bool:
        raise NotImplementedError
    
    async def delete(self, key: str) -> bool:
        raise NotImplementedError
    
    async def delete_pattern(self, pattern: str) -> int:
        raise NotImplementedError
    
    async def exists(self, key: str) -> bool:
        raise NotImplementedError
    
    async def ttl(self, key: str) -> int:
        raise NotImplementedError
    
    async def keys(self, pattern: str) -> List[str]:
        raise NotImplementedError


class RedisBackend(CacheBackend):
    """Redis-backed cache storage."""
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or config.redis_url
        self._client: Optional[aioredis.Redis] = None
        self._connected = False
    
    async def connect(self) -> bool:
        """Connect to Redis."""
        if not REDIS_AVAILABLE:
            logger.warning("Redis library not available")
            return False
        
        try:
            self._client = aioredis.from_url(
                self.redis_url,
                encoding='utf-8',
                decode_responses=False
            )
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis: {self.redis_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Disconnect from Redis."""
        if self._client:
            await self._client.close()
            self._connected = False
    
    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None
    
    async def get(self, key: str) -> Optional[bytes]:
        if not self.is_connected:
            return None
        try:
            return await self._client.get(key)
        except Exception as e:
            logger.error(f"Redis GET error: {e}")
            return None
    
    async def set(self, key: str, value: bytes, ttl: int) -> bool:
        if not self.is_connected:
            return False
        try:
            await self._client.setex(key, ttl, value)
            return True
        except Exception as e:
            logger.error(f"Redis SET error: {e}")
            return False
    
    async def delete(self, key: str) -> bool:
        if not self.is_connected:
            return False
        try:
            await self._client.delete(key)
            return True
        except Exception as e:
            logger.error(f"Redis DELETE error: {e}")
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        """Delete all keys matching pattern."""
        if not self.is_connected:
            return 0
        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)
            
            if keys:
                await self._client.delete(*keys)
            return len(keys)
        except Exception as e:
            logger.error(f"Redis DELETE PATTERN error: {e}")
            return 0
    
    async def exists(self, key: str) -> bool:
        if not self.is_connected:
            return False
        try:
            return await self._client.exists(key) > 0
        except Exception:
            return False
    
    async def ttl(self, key: str) -> int:
        if not self.is_connected:
            return -1
        try:
            return await self._client.ttl(key)
        except Exception:
            return -1
    
    async def keys(self, pattern: str) -> List[str]:
        if not self.is_connected:
            return []
        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key.decode() if isinstance(key, bytes) else key)
            return keys
        except Exception:
            return []
    
    async def add_to_tag(self, tag: str, key: str, ttl: int) -> bool:
        """Add key to a tag set for invalidation."""
        if not self.is_connected:
            return False
        try:
            tag_key = f"{config.key_prefix}tag:{tag}"
            await self._client.sadd(tag_key, key)
            await self._client.expire(tag_key, ttl * 2)  # Tag lives longer than entries
            return True
        except Exception as e:
            logger.error(f"Redis SADD error: {e}")
            return False
    
    async def get_tag_keys(self, tag: str) -> Set[str]:
        """Get all keys associated with a tag."""
        if not self.is_connected:
            return set()
        try:
            tag_key = f"{config.key_prefix}tag:{tag}"
            members = await self._client.smembers(tag_key)
            return {m.decode() if isinstance(m, bytes) else m for m in members}
        except Exception:
            return set()
    
    async def invalidate_tag(self, tag: str) -> int:
        """Invalidate all keys with a tag."""
        if not self.is_connected:
            return 0
        try:
            keys = await self.get_tag_keys(tag)
            if keys:
                await self._client.delete(*keys)
            
            # Also delete the tag set
            tag_key = f"{config.key_prefix}tag:{tag}"
            await self._client.delete(tag_key)
            
            return len(keys)
        except Exception as e:
            logger.error(f"Redis invalidate tag error: {e}")
            return 0


class MemoryBackend(CacheBackend):
    """In-memory cache backend (fallback)."""
    
    def __init__(self, max_items: int = 1000):
        self.max_items = max_items
        self._cache: Dict[str, Tuple[bytes, float]] = {}  # key -> (value, expiry_time)
        self._tags: Dict[str, Set[str]] = {}  # tag -> set of keys
        self._lock = asyncio.Lock()
    
    async def _cleanup(self):
        """Remove expired entries."""
        now = time.time()
        expired = [k for k, (_, exp) in self._cache.items() if exp < now]
        for k in expired:
            del self._cache[k]
        
        # LRU eviction if too many items
        if len(self._cache) > self.max_items:
            # Remove oldest 10%
            to_remove = len(self._cache) - int(self.max_items * 0.9)
            for k in list(self._cache.keys())[:to_remove]:
                del self._cache[k]
    
    async def get(self, key: str) -> Optional[bytes]:
        async with self._lock:
            await self._cleanup()
            if key in self._cache:
                value, expiry = self._cache[key]
                if expiry > time.time():
                    return value
                else:
                    del self._cache[key]
            return None
    
    async def set(self, key: str, value: bytes, ttl: int) -> bool:
        async with self._lock:
            await self._cleanup()
            self._cache[key] = (value, time.time() + ttl)
            return True
    
    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False
    
    async def delete_pattern(self, pattern: str) -> int:
        import fnmatch
        async with self._lock:
            pattern = pattern.replace('*', '.*')
            keys = [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]
            for k in keys:
                del self._cache[k]
            return len(keys)
    
    async def exists(self, key: str) -> bool:
        return key in self._cache and self._cache[key][1] > time.time()
    
    async def ttl(self, key: str) -> int:
        if key in self._cache:
            return int(self._cache[key][1] - time.time())
        return -1
    
    async def keys(self, pattern: str) -> List[str]:
        import fnmatch
        pattern = pattern.replace('*', '.*')
        return [k for k in self._cache.keys() if fnmatch.fnmatch(k, pattern)]
    
    async def add_to_tag(self, tag: str, key: str, ttl: int) -> bool:
        async with self._lock:
            if tag not in self._tags:
                self._tags[tag] = set()
            self._tags[tag].add(key)
            return True
    
    async def get_tag_keys(self, tag: str) -> Set[str]:
        return self._tags.get(tag, set())
    
    async def invalidate_tag(self, tag: str) -> int:
        async with self._lock:
            keys = self._tags.get(tag, set())
            for k in keys:
                if k in self._cache:
                    del self._cache[k]
            if tag in self._tags:
                del self._tags[tag]
            return len(keys)


# =============================================================================
# CACHE MANAGER
# =============================================================================

class CacheManager:
    """
    Central cache manager with multi-tier storage.
    
    Hierarchy:
    1. L1: In-memory (fastest, limited size)
    2. L2: Redis (fast, shared across instances)
    """
    
    def __init__(self):
        self.redis_backend: Optional[RedisBackend] = None
        self.memory_backend = MemoryBackend(config.local_max_items)
        self._initialized = False
        self._stats = {
            'hits': 0,
            'misses': 0,
            'sets': 0,
            'deletes': 0,
            'errors': 0,
        }
    
    async def initialize(self, redis_url: str = None) -> bool:
        """Initialize cache backends."""
        if self._initialized:
            return True
        
        # Try Redis first
        self.redis_backend = RedisBackend(redis_url)
        redis_connected = await self.redis_backend.connect()
        
        if not redis_connected and config.enable_local_fallback:
            logger.warning("Redis unavailable, using memory backend only")
        
        self._initialized = True
        return True
    
    async def close(self):
        """Close all connections."""
        if self.redis_backend:
            await self.redis_backend.disconnect()
        self._initialized = False
    
    def _make_key(self, key: str) -> str:
        """Create full cache key with prefix."""
        full_key = f"{config.key_prefix}{key}"
        if len(full_key) > config.max_key_length:
            # Hash long keys
            key_hash = hashlib.sha256(key.encode()).hexdigest()[:32]
            full_key = f"{config.key_prefix}h:{key_hash}"
        return full_key
    
    async def get(self, key: str) -> Tuple[Optional[Any], bool]:
        """
        Get value from cache.
        
        Returns:
            Tuple of (value, hit) where hit is True if found in cache
        """
        full_key = self._make_key(key)
        
        # Try memory first (L1)
        data = await self.memory_backend.get(full_key)
        if data:
            self._stats['hits'] += 1
            if config.enable_metrics:
                metrics.http_requests_total.labels(
                    method='GET', endpoint='cache', status='hit_l1'
                ).inc()
            return CacheSerializer.deserialize(data), True
        
        # Try Redis (L2)
        if self.redis_backend and self.redis_backend.is_connected:
            data = await self.redis_backend.get(full_key)
            if data:
                self._stats['hits'] += 1
                
                # Promote to L1
                ttl = await self.redis_backend.ttl(full_key)
                if ttl > 0:
                    await self.memory_backend.set(full_key, data, min(ttl, 60))
                
                if config.enable_metrics:
                    metrics.http_requests_total.labels(
                        method='GET', endpoint='cache', status='hit_l2'
                    ).inc()
                return CacheSerializer.deserialize(data), True
        
        self._stats['misses'] += 1
        if config.enable_metrics:
            metrics.http_requests_total.labels(
                method='GET', endpoint='cache', status='miss'
            ).inc()
        return None, False
    
    async def set(
        self,
        key: str,
        value: Any,
        ttl: int = None,
        tags: List[str] = None
    ) -> bool:
        """
        Set value in cache.
        
        Args:
            key: Cache key
            value: Value to cache
            ttl: Time-to-live in seconds
            tags: Tags for invalidation
        """
        full_key = self._make_key(key)
        ttl = ttl or config.default_ttl
        
        try:
            # Serialize
            data = CacheSerializer.serialize(value, config.enable_compression)
            
            # Check size
            if len(data) > config.max_value_size_mb * 1024 * 1024:
                logger.warning(f"Value too large to cache: {len(data)} bytes")
                return False
            
            # Set in Redis (L2)
            if self.redis_backend and self.redis_backend.is_connected:
                await self.redis_backend.set(full_key, data, ttl)
                
                # Register tags
                if tags:
                    for tag in tags:
                        await self.redis_backend.add_to_tag(tag, full_key, ttl)
            
            # Set in memory (L1) with shorter TTL
            await self.memory_backend.set(full_key, data, min(ttl, 60))
            if tags:
                for tag in tags:
                    await self.memory_backend.add_to_tag(tag, full_key, ttl)
            
            self._stats['sets'] += 1
            return True
            
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            self._stats['errors'] += 1
            return False
    
    async def delete(self, key: str) -> bool:
        """Delete a key from cache."""
        full_key = self._make_key(key)
        
        await self.memory_backend.delete(full_key)
        if self.redis_backend and self.redis_backend.is_connected:
            await self.redis_backend.delete(full_key)
        
        self._stats['deletes'] += 1
        return True
    
    async def invalidate_tags(self, tags: List[str]) -> int:
        """Invalidate all keys with given tags."""
        total = 0
        
        for tag in tags:
            total += await self.memory_backend.invalidate_tag(tag)
            if self.redis_backend and self.redis_backend.is_connected:
                total += await self.redis_backend.invalidate_tag(tag)
        
        logger.info(f"Invalidated {total} keys for tags: {tags}")
        return total
    
    async def invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern."""
        total = 0
        
        full_pattern = f"{config.key_prefix}{pattern}"
        total += await self.memory_backend.delete_pattern(full_pattern)
        if self.redis_backend and self.redis_backend.is_connected:
            total += await self.redis_backend.delete_pattern(full_pattern)
        
        return total
    
    async def clear(self) -> int:
        """Clear all cache entries."""
        return await self.invalidate_pattern("*")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self._stats['hits'] + self._stats['misses']
        hit_rate = self._stats['hits'] / total if total > 0 else 0
        
        return {
            **self._stats,
            'hit_rate': round(hit_rate, 4),
            'total_requests': total,
            'redis_connected': self.redis_backend.is_connected if self.redis_backend else False,
        }


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_cache_manager: Optional[CacheManager] = None


async def get_cache_manager() -> CacheManager:
    """Get or create cache manager."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
        await _cache_manager.initialize()
    return _cache_manager


async def close_cache_manager():
    """Close cache manager."""
    global _cache_manager
    if _cache_manager:
        await _cache_manager.close()
        _cache_manager = None


# =============================================================================
# DECORATOR
# =============================================================================

def cache(
    ttl: Union[int, CacheTTL] = None,
    tags: List[str] = None,
    key_builder: Callable[..., str] = None,
    condition: Callable[..., bool] = None,
    unless: Callable[[Any], bool] = None,
):
    """
    Cache decorator for async functions.
    
    Args:
        ttl: Time-to-live in seconds or CacheTTL enum
        tags: Tags for invalidation
        key_builder: Custom function to build cache key
        condition: Only cache if this returns True
        unless: Don't cache if this returns True for the result
    
    Usage:
        @cache(ttl=CacheTTL.MEDIUM, tags=['dashboard'])
        async def get_dashboard_data(org_id: str):
            return await expensive_query()
    """
    _ttl = ttl.value if isinstance(ttl, CacheTTL) else (ttl or config.default_ttl)
    _tags = tags or []
    
    def decorator(func: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            # Check condition
            if condition and not condition(*args, **kwargs):
                return await func(*args, **kwargs)
            
            # Build cache key
            if key_builder:
                cache_key = key_builder(*args, **kwargs)
            else:
                cache_key = _build_key(func, args, kwargs)
            
            # Get cache manager
            manager = await get_cache_manager()
            
            # Try cache
            value, hit = await manager.get(cache_key)
            if hit:
                return value
            
            # Execute function
            result = await func(*args, **kwargs)
            
            # Check unless condition
            if unless and unless(result):
                return result
            
            # Cache result
            await manager.set(cache_key, result, _ttl, _tags)
            
            return result
        
        # Add cache control methods to wrapper
        wrapper.invalidate = lambda: _invalidate_func(func)
        wrapper.cache_key = lambda *a, **kw: _build_key(func, a, kw)
        
        return wrapper
    
    return decorator


def _build_key(func: Callable, args: tuple, kwargs: dict) -> str:
    """Build cache key from function signature."""
    # Get function name with module
    func_name = f"{func.__module__}.{func.__qualname__}"
    
    # Get argument names
    sig = inspect.signature(func)
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()
    
    # Build key from arguments
    arg_parts = []
    for name, value in bound.arguments.items():
        # Skip 'self' and 'cls'
        if name in ('self', 'cls'):
            continue
        
        # Handle different types
        if isinstance(value, (str, int, float, bool)):
            arg_parts.append(f"{name}={value}")
        elif isinstance(value, (list, tuple)):
            arg_parts.append(f"{name}={hash(tuple(value))}")
        elif isinstance(value, dict):
            arg_parts.append(f"{name}={hash(frozenset(value.items()))}")
        elif hasattr(value, 'id'):
            arg_parts.append(f"{name}={value.id}")
        else:
            arg_parts.append(f"{name}={hash(str(value))}")
    
    args_str = ":".join(arg_parts)
    return f"{func_name}:{args_str}"


async def _invalidate_func(func: Callable):
    """Invalidate all cached results for a function."""
    manager = await get_cache_manager()
    pattern = f"{func.__module__}.{func.__qualname__}:*"
    return await manager.invalidate_pattern(pattern)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

async def invalidate_cache(
    tags: List[str] = None,
    keys: List[str] = None,
    pattern: str = None
) -> int:
    """
    Invalidate cache entries.
    
    Args:
        tags: Invalidate all keys with these tags
        keys: Specific keys to invalidate
        pattern: Pattern to match keys (supports *)
    
    Returns:
        Number of keys invalidated
    """
    manager = await get_cache_manager()
    total = 0
    
    if tags:
        total += await manager.invalidate_tags(tags)
    
    if keys:
        for key in keys:
            await manager.delete(key)
            total += 1
    
    if pattern:
        total += await manager.invalidate_pattern(pattern)
    
    return total


async def cache_get(key: str) -> Tuple[Optional[Any], bool]:
    """Direct cache get."""
    manager = await get_cache_manager()
    return await manager.get(key)


async def cache_set(
    key: str,
    value: Any,
    ttl: int = None,
    tags: List[str] = None
) -> bool:
    """Direct cache set."""
    manager = await get_cache_manager()
    return await manager.set(key, value, ttl, tags)


async def cache_delete(key: str) -> bool:
    """Direct cache delete."""
    manager = await get_cache_manager()
    return await manager.delete(key)


def get_cache_stats() -> Dict[str, Any]:
    """Get cache statistics."""
    if _cache_manager:
        return _cache_manager.get_stats()
    return {}


# =============================================================================
# CACHE WARMING
# =============================================================================

class CacheWarmer:
    """
    Pre-warm cache with common queries.
    
    Usage:
        warmer = CacheWarmer()
        warmer.register(get_dashboard_data, org_ids=['org1', 'org2'])
        await warmer.warm_all()
    """
    
    def __init__(self):
        self._tasks: List[Tuple[Callable, List, Dict]] = []
    
    def register(
        self,
        func: Callable,
        args_list: List[tuple] = None,
        kwargs_list: List[dict] = None
    ):
        """Register function to warm."""
        args_list = args_list or [()]
        kwargs_list = kwargs_list or [{}]
        
        for args in args_list:
            for kwargs in kwargs_list:
                self._tasks.append((func, args if isinstance(args, tuple) else (args,), kwargs))
    
    async def warm_all(self, concurrency: int = 5):
        """Execute all warming tasks."""
        semaphore = asyncio.Semaphore(concurrency)
        
        async def run_task(func, args, kwargs):
            async with semaphore:
                try:
                    await func(*args, **kwargs)
                except Exception as e:
                    logger.error(f"Cache warming error for {func.__name__}: {e}")
        
        tasks = [run_task(f, a, k) for f, a, k in self._tasks]
        await asyncio.gather(*tasks)
        
        logger.info(f"Cache warmed with {len(self._tasks)} entries")


# =============================================================================
# FASTAPI INTEGRATION
# =============================================================================

try:
    from fastapi import APIRouter, Request
    
    cache_router = APIRouter(prefix="/api/cache", tags=["cache"])
    
    @cache_router.get("/stats")
    async def cache_stats():
        """Get cache statistics."""
        return get_cache_stats()
    
    @cache_router.post("/invalidate")
    async def invalidate(
        tags: List[str] = None,
        pattern: str = None
    ):
        """Invalidate cache entries."""
        count = await invalidate_cache(tags=tags, pattern=pattern)
        return {"invalidated": count}
    
    @cache_router.post("/clear")
    async def clear_cache():
        """Clear all cache."""
        manager = await get_cache_manager()
        count = await manager.clear()
        return {"cleared": count}

except ImportError:
    cache_router = None


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    'cache',
    'CacheTTL',
    'CacheConfig',
    'CacheManager',
    'CacheWarmer',
    'get_cache_manager',
    'close_cache_manager',
    'invalidate_cache',
    'cache_get',
    'cache_set',
    'cache_delete',
    'get_cache_stats',
    'cache_router',
]
