"""
S.S.I. SHADOW - Authentication Service
======================================
JWT-based authentication with refresh tokens.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple
import hashlib
import secrets

from jose import jwt, JWTError
from passlib.context import CryptContext
from pydantic import BaseModel
import redis.asyncio as redis

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

class AuthConfig:
    """Authentication configuration."""
    
    SECRET_KEY: str = os.getenv("JWT_SECRET_KEY", secrets.token_urlsafe(32))
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60  # 1 hour
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7
    
    # Password hashing
    PASSWORD_MIN_LENGTH: int = 8
    PASSWORD_SCHEMES: list = ["bcrypt"]


config = AuthConfig()
pwd_context = CryptContext(schemes=config.PASSWORD_SCHEMES, deprecated="auto")


# =============================================================================
# MODELS
# =============================================================================

class TokenPayload(BaseModel):
    """JWT token payload."""
    sub: str  # user_id
    org: str  # organization_id
    role: str
    exp: datetime
    iat: datetime
    type: str  # "access" or "refresh"
    jti: str  # token ID for revocation


class User(BaseModel):
    """User model."""
    id: str
    email: str
    name: str
    password_hash: str
    role: str
    organization_id: str
    organization_name: str
    is_active: bool = True
    created_at: datetime
    last_login: Optional[datetime] = None


# =============================================================================
# AUTH SERVICE
# =============================================================================

class AuthService:
    """
    Authentication service with JWT tokens and Redis for token revocation.
    """
    
    def __init__(self, redis_url: str = None, user_store: Dict = None):
        """
        Initialize auth service.
        
        Args:
            redis_url: Redis URL for token blacklist
            user_store: Optional in-memory user store (for testing)
        """
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        self._redis: Optional[redis.Redis] = None
        
        # In-memory user store (replace with database in production)
        self.users: Dict[str, User] = user_store or {}
        self.users_by_email: Dict[str, str] = {}  # email -> user_id
    
    async def _get_redis(self) -> Optional[redis.Redis]:
        """Get Redis connection."""
        if not self.redis_url:
            return None
        
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url)
        
        return self._redis
    
    # =========================================================================
    # PASSWORD HASHING (using bcrypt directly for compatibility)
    # =========================================================================
    
    def hash_password(self, password: str) -> str:
        """Hash a password using bcrypt."""
        import bcrypt
        pwd_bytes = password.encode('utf-8')[:72]
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')
    
    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        """Verify a password against hash."""
        import bcrypt
        pwd_bytes = plain_password.encode('utf-8')[:72]
        hash_bytes = hashed_password.encode('utf-8')
        return bcrypt.checkpw(pwd_bytes, hash_bytes)
    
    # =========================================================================
    # TOKEN GENERATION
    # =========================================================================
    
    def create_access_token(self, user: User) -> Tuple[str, datetime]:
        """
        Create an access token.
        
        Returns:
            Tuple of (token, expiration)
        """
        now = datetime.utcnow()
        expires = now + timedelta(minutes=config.ACCESS_TOKEN_EXPIRE_MINUTES)
        jti = secrets.token_urlsafe(16)
        
        payload = {
            "sub": user.id,
            "org": user.organization_id,
            "role": user.role,
            "exp": expires,
            "iat": now,
            "type": "access",
            "jti": jti
        }
        
        token = jwt.encode(payload, config.SECRET_KEY, algorithm=config.ALGORITHM)
        return token, expires
    
    def create_refresh_token(self, user: User) -> Tuple[str, datetime]:
        """
        Create a refresh token.
        
        Returns:
            Tuple of (token, expiration)
        """
        now = datetime.utcnow()
        expires = now + timedelta(days=config.REFRESH_TOKEN_EXPIRE_DAYS)
        jti = secrets.token_urlsafe(16)
        
        payload = {
            "sub": user.id,
            "org": user.organization_id,
            "role": user.role,
            "exp": expires,
            "iat": now,
            "type": "refresh",
            "jti": jti
        }
        
        token = jwt.encode(payload, config.SECRET_KEY, algorithm=config.ALGORITHM)
        return token, expires
    
    def create_tokens(self, user: User) -> Dict[str, any]:
        """
        Create both access and refresh tokens.
        
        Returns:
            Dict with access_token, refresh_token, expires_in, token_type
        """
        access_token, access_expires = self.create_access_token(user)
        refresh_token, refresh_expires = self.create_refresh_token(user)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": config.ACCESS_TOKEN_EXPIRE_MINUTES * 60
        }
    
    # =========================================================================
    # TOKEN VERIFICATION
    # =========================================================================
    
    def decode_token(self, token: str) -> Optional[TokenPayload]:
        """
        Decode and validate a JWT token.
        
        Returns:
            TokenPayload if valid, None otherwise
        """
        try:
            payload = jwt.decode(
                token,
                config.SECRET_KEY,
                algorithms=[config.ALGORITHM]
            )
            
            return TokenPayload(
                sub=payload["sub"],
                org=payload["org"],
                role=payload["role"],
                exp=datetime.fromtimestamp(payload["exp"]),
                iat=datetime.fromtimestamp(payload["iat"]),
                type=payload["type"],
                jti=payload["jti"]
            )
        except JWTError as e:
            logger.debug(f"Token decode failed: {e}")
            return None
    
    async def verify_token(self, token: str, token_type: str = "access") -> Optional[TokenPayload]:
        """
        Verify a token is valid and not revoked.
        
        Args:
            token: JWT token
            token_type: Expected token type ("access" or "refresh")
        
        Returns:
            TokenPayload if valid, None otherwise
        """
        payload = self.decode_token(token)
        
        if not payload:
            return None
        
        # Check token type
        if payload.type != token_type:
            logger.debug(f"Token type mismatch: expected {token_type}, got {payload.type}")
            return None
        
        # Check expiration
        if payload.exp < datetime.utcnow():
            logger.debug("Token expired")
            return None
        
        # Check if revoked
        if await self.is_token_revoked(payload.jti):
            logger.debug("Token revoked")
            return None
        
        return payload
    
    async def is_token_revoked(self, jti: str) -> bool:
        """Check if a token has been revoked."""
        try:
            r = await self._get_redis()
            if r:
                return await r.exists(f"revoked_token:{jti}")
        except Exception as e:
            logger.warning(f"Failed to check token revocation: {e}")
        return False
    
    async def revoke_token(self, jti: str, expires_in: int = None):
        """
        Revoke a token by its JTI.
        
        Args:
            jti: Token ID
            expires_in: TTL in seconds (default: refresh token lifetime)
        """
        try:
            r = await self._get_redis()
            if r:
                ttl = expires_in or (config.REFRESH_TOKEN_EXPIRE_DAYS * 86400)
                await r.setex(f"revoked_token:{jti}", ttl, "1")
        except Exception as e:
            logger.warning(f"Failed to revoke token: {e}")
    
    # =========================================================================
    # USER AUTHENTICATION
    # =========================================================================
    
    async def authenticate(self, email: str, password: str) -> Optional[User]:
        """
        Authenticate a user with email and password.
        
        Returns:
            User if authenticated, None otherwise
        """
        user = await self.get_user_by_email(email)
        
        if not user:
            logger.debug(f"User not found: {email}")
            return None
        
        if not user.is_active:
            logger.debug(f"User not active: {email}")
            return None
        
        if not self.verify_password(password, user.password_hash):
            logger.debug(f"Invalid password for: {email}")
            return None
        
        # Update last login
        user.last_login = datetime.utcnow()
        
        return user
    
    async def login(self, email: str, password: str) -> Optional[Dict]:
        """
        Login a user and return tokens.
        
        Returns:
            Dict with tokens and user info, or None if auth failed
        """
        user = await self.authenticate(email, password)
        
        if not user:
            return None
        
        tokens = self.create_tokens(user)
        
        return {
            **tokens,
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "organization_id": user.organization_id,
                "organization_name": user.organization_name,
                "created_at": user.created_at.isoformat(),
                "last_login": user.last_login.isoformat() if user.last_login else None
            }
        }
    
    async def refresh_tokens(self, refresh_token: str) -> Optional[Dict]:
        """
        Refresh tokens using a refresh token.
        
        Returns:
            Dict with new tokens, or None if refresh failed
        """
        payload = await self.verify_token(refresh_token, token_type="refresh")
        
        if not payload:
            return None
        
        # Get user
        user = await self.get_user(payload.sub)
        
        if not user or not user.is_active:
            return None
        
        # Revoke old refresh token
        await self.revoke_token(payload.jti)
        
        # Create new tokens
        return self.create_tokens(user)
    
    async def logout(self, access_token: str, refresh_token: str = None):
        """
        Logout a user by revoking their tokens.
        """
        # Revoke access token
        payload = self.decode_token(access_token)
        if payload:
            await self.revoke_token(payload.jti, config.ACCESS_TOKEN_EXPIRE_MINUTES * 60)
        
        # Revoke refresh token if provided
        if refresh_token:
            payload = self.decode_token(refresh_token)
            if payload:
                await self.revoke_token(payload.jti)
    
    # =========================================================================
    # USER MANAGEMENT
    # =========================================================================
    
    async def get_user(self, user_id: str) -> Optional[User]:
        """Get a user by ID."""
        return self.users.get(user_id)
    
    async def get_user_by_email(self, email: str) -> Optional[User]:
        """Get a user by email."""
        user_id = self.users_by_email.get(email.lower())
        if user_id:
            return self.users.get(user_id)
        return None
    
    async def create_user(
        self,
        email: str,
        password: str,
        name: str,
        role: str,
        organization_id: str,
        organization_name: str
    ) -> User:
        """Create a new user."""
        user_id = secrets.token_urlsafe(16)
        
        user = User(
            id=user_id,
            email=email.lower(),
            name=name,
            password_hash=self.hash_password(password),
            role=role,
            organization_id=organization_id,
            organization_name=organization_name,
            created_at=datetime.utcnow()
        )
        
        self.users[user_id] = user
        self.users_by_email[email.lower()] = user_id
        
        return user
    
    async def update_password(
        self,
        user_id: str,
        current_password: str,
        new_password: str
    ) -> bool:
        """
        Update a user's password.
        
        Returns:
            True if successful, False otherwise
        """
        user = await self.get_user(user_id)
        
        if not user:
            return False
        
        if not self.verify_password(current_password, user.password_hash):
            return False
        
        user.password_hash = self.hash_password(new_password)
        return True
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_auth_service: Optional[AuthService] = None


def get_auth_service() -> AuthService:
    """Get or create the auth service instance."""
    global _auth_service
    if _auth_service is None:
        _auth_service = AuthService()
    return _auth_service


async def init_auth_service(redis_url: str = None) -> AuthService:
    """Initialize the auth service with configuration."""
    global _auth_service
    _auth_service = AuthService(redis_url=redis_url)
    
    # Create default admin user if not exists
    if not await _auth_service.get_user_by_email("admin@ssi-shadow.io"):
        await _auth_service.create_user(
            email="admin@ssi-shadow.io",
            password=os.getenv("ADMIN_PASSWORD", "admin123!@#"),
            name="Admin",
            role="admin",
            organization_id="org_default",
            organization_name="SSI Shadow"
        )
        logger.info("Created default admin user")
    
    return _auth_service
