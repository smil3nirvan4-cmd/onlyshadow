"""
S.S.I. SHADOW - API Middleware
==============================
Authentication, rate limiting, and request validation middleware.
"""

import os
import logging
import time
from datetime import datetime
from typing import Optional, Callable, List
from functools import wraps

from fastapi import Request, Response, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.base import BaseHTTPMiddleware
import redis.asyncio as redis

from api.services.auth_service import get_auth_service, TokenPayload

logger = logging.getLogger(__name__)


# =============================================================================
# SECURITY SCHEME
# =============================================================================

security = HTTPBearer(auto_error=False)


# =============================================================================
# AUTH DEPENDENCY
# =============================================================================

class AuthenticatedUser:
    """Authenticated user context."""
    
    def __init__(self, payload: TokenPayload):
        self.user_id = payload.sub
        self.organization_id = payload.org
        self.role = payload.role
        self.token_id = payload.jti


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> AuthenticatedUser:
    """
    FastAPI dependency to get the current authenticated user.
    
    Raises:
        HTTPException: If not authenticated
    """
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    auth_service = get_auth_service()
    payload = await auth_service.verify_token(credentials.credentials)
    
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    return AuthenticatedUser(payload)


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[AuthenticatedUser]:
    """
    FastAPI dependency to optionally get the current user.
    Returns None if not authenticated.
    """
    if not credentials:
        return None
    
    auth_service = get_auth_service()
    payload = await auth_service.verify_token(credentials.credentials)
    
    if not payload:
        return None
    
    return AuthenticatedUser(payload)


def require_role(*roles: str):
    """
    Dependency factory to require specific roles.
    
    Usage:
        @router.get("/admin-only")
        async def admin_endpoint(user: AuthenticatedUser = Depends(require_role("admin"))):
            ...
    """
    async def role_checker(
        user: AuthenticatedUser = Depends(get_current_user)
    ) -> AuthenticatedUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.role}' not authorized. Required: {roles}"
            )
        return user
    
    return role_checker


# =============================================================================
# RATE LIMITING
# =============================================================================

class RateLimiter:
    """
    Token bucket rate limiter using Redis.
    """
    
    def __init__(
        self,
        redis_url: str = None,
        requests_per_minute: int = 100,
        burst_size: int = 20
    ):
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self.requests_per_minute = requests_per_minute
        self.burst_size = burst_size
        self._redis: Optional[redis.Redis] = None
    
    async def _get_redis(self) -> Optional[redis.Redis]:
        """Get Redis connection."""
        if not self.redis_url:
            return None
        
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url)
        
        return self._redis
    
    async def is_allowed(self, key: str) -> tuple[bool, dict]:
        """
        Check if a request is allowed under rate limit.
        
        Args:
            key: Unique identifier (e.g., user_id, IP)
        
        Returns:
            Tuple of (is_allowed, rate_limit_info)
        """
        r = await self._get_redis()
        
        if not r:
            # No Redis, allow all
            return True, {
                "limit": self.requests_per_minute,
                "remaining": self.requests_per_minute,
                "reset": 60
            }
        
        now = time.time()
        window_start = int(now / 60) * 60  # Start of current minute
        redis_key = f"rate_limit:{key}:{window_start}"
        
        try:
            # Increment counter
            current = await r.incr(redis_key)
            
            # Set expiry on first request
            if current == 1:
                await r.expire(redis_key, 120)  # 2 minute TTL
            
            remaining = max(0, self.requests_per_minute - current)
            reset = window_start + 60 - now
            
            is_allowed = current <= self.requests_per_minute
            
            # Allow burst
            if not is_allowed and current <= self.requests_per_minute + self.burst_size:
                is_allowed = True
            
            return is_allowed, {
                "limit": self.requests_per_minute,
                "remaining": remaining,
                "reset": int(reset)
            }
            
        except Exception as e:
            logger.warning(f"Rate limit check failed: {e}")
            return True, {"limit": self.requests_per_minute, "remaining": -1, "reset": 60}
    
    async def close(self):
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()


# Global rate limiter instance
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    """Get or create rate limiter."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


async def check_rate_limit(
    request: Request,
    user: Optional[AuthenticatedUser] = Depends(get_optional_user)
):
    """
    Dependency to check rate limit.
    
    Uses user_id if authenticated, otherwise uses IP.
    """
    rate_limiter = get_rate_limiter()
    
    # Use user_id or IP as key
    if user:
        key = f"user:{user.user_id}"
        limit = 200  # Higher limit for authenticated users
    else:
        key = f"ip:{request.client.host}"
        limit = 60  # Lower limit for anonymous
    
    rate_limiter.requests_per_minute = limit
    is_allowed, info = await rate_limiter.is_allowed(key)
    
    # Add rate limit headers
    request.state.rate_limit_info = info
    
    if not is_allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={
                "X-RateLimit-Limit": str(info["limit"]),
                "X-RateLimit-Remaining": str(info["remaining"]),
                "X-RateLimit-Reset": str(info["reset"]),
                "Retry-After": str(info["reset"])
            }
        )


# =============================================================================
# RATE LIMIT MIDDLEWARE
# =============================================================================

class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add rate limit headers to all responses.
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        
        # Add rate limit headers if available
        if hasattr(request.state, "rate_limit_info"):
            info = request.state.rate_limit_info
            response.headers["X-RateLimit-Limit"] = str(info["limit"])
            response.headers["X-RateLimit-Remaining"] = str(info["remaining"])
            response.headers["X-RateLimit-Reset"] = str(info["reset"])
        
        return response


# =============================================================================
# CORS MIDDLEWARE
# =============================================================================

CORS_ORIGINS = [
    "http://localhost:3000",
    "http://localhost:5173",
    "https://dashboard.ssi-shadow.io",
    "https://app.ssi-shadow.io",
]


def get_cors_origins() -> List[str]:
    """Get allowed CORS origins from environment."""
    extra = os.getenv("CORS_ORIGINS", "")
    if extra:
        return CORS_ORIGINS + extra.split(",")
    return CORS_ORIGINS


# =============================================================================
# REQUEST ID MIDDLEWARE
# =============================================================================

class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to add request ID to all requests.
    """
    
    async def dispatch(self, request: Request, call_next) -> Response:
        import uuid
        
        # Get or generate request ID
        request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))
        
        # Store in request state
        request.state.request_id = request_id
        
        # Process request
        response = await call_next(request)
        
        # Add to response
        response.headers["X-Request-ID"] = request_id
        
        return response


# =============================================================================
# ORGANIZATION CONTEXT
# =============================================================================

class OrganizationContext:
    """Context for organization-scoped operations."""
    
    def __init__(self, organization_id: str, user: AuthenticatedUser):
        self.organization_id = organization_id
        self.user = user


async def get_organization_context(
    user: AuthenticatedUser = Depends(get_current_user)
) -> OrganizationContext:
    """
    Get organization context for the current user.
    """
    return OrganizationContext(
        organization_id=user.organization_id,
        user=user
    )


# =============================================================================
# ERROR HANDLERS
# =============================================================================

async def validation_exception_handler(request: Request, exc):
    """Handle validation errors."""
    from fastapi.exceptions import RequestValidationError
    
    errors = []
    for error in exc.errors():
        errors.append({
            "field": ".".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type": error["type"]
        })
    
    return {
        "error": "validation_error",
        "message": "Request validation failed",
        "errors": errors,
        "request_id": getattr(request.state, "request_id", None)
    }


async def http_exception_handler(request: Request, exc: HTTPException):
    """Handle HTTP exceptions."""
    return {
        "error": exc.detail if isinstance(exc.detail, str) else "error",
        "message": str(exc.detail),
        "request_id": getattr(request.state, "request_id", None)
    }


# =============================================================================
# API KEY AUTHENTICATION (for machine-to-machine)
# =============================================================================

class APIKeyAuth:
    """
    API key authentication for server-to-server communication.
    """
    
    def __init__(self, redis_url: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self._redis: Optional[redis.Redis] = None
        
        # In-memory API key store (replace with database in production)
        self.api_keys: dict = {}
    
    async def _get_redis(self) -> Optional[redis.Redis]:
        """Get Redis connection."""
        if not self.redis_url:
            return None
        
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url)
        
        return self._redis
    
    def generate_api_key(self) -> str:
        """Generate a new API key."""
        import secrets
        return f"ssi_{secrets.token_urlsafe(32)}"
    
    async def create_api_key(
        self,
        organization_id: str,
        name: str,
        permissions: List[str] = None
    ) -> dict:
        """
        Create a new API key.
        
        Returns:
            Dict with key details (key is only shown once)
        """
        import secrets
        
        key = self.generate_api_key()
        key_id = secrets.token_urlsafe(8)
        
        key_data = {
            "id": key_id,
            "organization_id": organization_id,
            "name": name,
            "permissions": permissions or ["read"],
            "created_at": datetime.utcnow().isoformat(),
            "last_used": None
        }
        
        # Store hashed key
        key_hash = self._hash_key(key)
        self.api_keys[key_hash] = key_data
        
        # Also store in Redis for distributed access
        r = await self._get_redis()
        if r:
            import json
            await r.hset("api_keys", key_hash, json.dumps(key_data))
        
        return {
            "id": key_id,
            "key": key,  # Only returned on creation
            "name": name,
            "permissions": permissions or ["read"],
            "created_at": key_data["created_at"]
        }
    
    def _hash_key(self, key: str) -> str:
        """Hash an API key."""
        import hashlib
        return hashlib.sha256(key.encode()).hexdigest()
    
    async def validate_api_key(self, key: str) -> Optional[dict]:
        """
        Validate an API key.
        
        Returns:
            Key data if valid, None otherwise
        """
        key_hash = self._hash_key(key)
        
        # Check memory cache
        if key_hash in self.api_keys:
            return self.api_keys[key_hash]
        
        # Check Redis
        r = await self._get_redis()
        if r:
            import json
            data = await r.hget("api_keys", key_hash)
            if data:
                key_data = json.loads(data)
                self.api_keys[key_hash] = key_data
                return key_data
        
        return None


# API key dependency
async def get_api_key_auth(request: Request) -> Optional[dict]:
    """
    Dependency to validate API key authentication.
    
    Expects header: X-API-Key: ssi_xxx
    """
    api_key = request.headers.get("X-API-Key")
    
    if not api_key:
        return None
    
    auth = APIKeyAuth()
    key_data = await auth.validate_api_key(api_key)
    
    if not key_data:
        raise HTTPException(
            status_code=401,
            detail="Invalid API key"
        )
    
    return key_data


async def require_api_key(
    key_data: Optional[dict] = Depends(get_api_key_auth)
) -> dict:
    """
    Dependency to require API key authentication.
    """
    if not key_data:
        raise HTTPException(
            status_code=401,
            detail="API key required",
            headers={"WWW-Authenticate": "X-API-Key"}
        )
    
    return key_data
