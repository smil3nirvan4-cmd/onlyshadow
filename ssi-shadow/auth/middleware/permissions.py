"""
S.S.I. SHADOW - Permission Middleware
=====================================
FastAPI dependencies for permission checking.
"""

import logging
from typing import Optional, List
from dataclasses import dataclass

from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from auth.models.entities import (
    UserRole,
    Permission,
    has_permission,
)
from auth.services.user_service import get_user_service
from auth.services.team_api_key_service import get_api_key_service

logger = logging.getLogger(__name__)

security = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    """Current authenticated user context."""
    user_id: str
    organization_id: str
    role: UserRole
    email: str
    name: str
    permissions: List[Permission]


async def get_current_user_with_org(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    request: Request = None
) -> CurrentUser:
    """
    Get the current authenticated user with organization context.
    
    Supports both JWT tokens and API keys.
    """
    user_service = get_user_service()
    
    # Check for API key first
    api_key = None
    if request:
        api_key = request.headers.get("X-API-Key")
    
    if api_key:
        # Validate API key
        api_key_service = get_api_key_service()
        key_data = await api_key_service.validate_api_key(api_key)
        
        if not key_data:
            raise HTTPException(
                status_code=401,
                detail="Invalid API key"
            )
        
        # Return API key context (limited permissions)
        return CurrentUser(
            user_id=f"api_key:{key_data.id}",
            organization_id=key_data.organization_id,
            role=UserRole.VIEWER,  # API keys have limited role
            email="",
            name=key_data.name,
            permissions=[
                Permission(p) for p in key_data.permissions
                if p in [e.value for e in Permission]
            ]
        )
    
    # Check for JWT token
    if not credentials:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Verify JWT
    payload = user_service.verify_token(credentials.credentials)
    
    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"}
        )
    
    # Get user
    user = await user_service.get_user(payload["sub"])
    
    if not user or not user.is_active:
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive"
        )
    
    # Get permissions for role
    from auth.models.entities import get_permissions
    permissions = get_permissions(user.role)
    
    return CurrentUser(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role,
        email=user.email,
        name=user.name,
        permissions=permissions
    )


def require_permission(*permissions: Permission):
    """
    Dependency factory to require specific permissions.
    
    Usage:
        @router.get("/settings")
        async def get_settings(
            user: CurrentUser = Depends(require_permission(Permission.SETTINGS_VIEW))
        ):
            ...
    """
    async def permission_checker(
        user: CurrentUser = Depends(get_current_user_with_org)
    ) -> CurrentUser:
        # Check if user has any of the required permissions
        has_any = any(p in user.permissions for p in permissions)
        
        if not has_any:
            raise HTTPException(
                status_code=403,
                detail=f"Permission denied. Required: {[p.value for p in permissions]}"
            )
        
        return user
    
    return permission_checker


def require_role(*roles: UserRole):
    """
    Dependency factory to require specific roles.
    
    Usage:
        @router.delete("/org")
        async def delete_org(
            user: CurrentUser = Depends(require_role(UserRole.OWNER))
        ):
            ...
    """
    async def role_checker(
        user: CurrentUser = Depends(get_current_user_with_org)
    ) -> CurrentUser:
        if user.role not in roles:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{user.role}' not authorized. Required: {[r.value for r in roles]}"
            )
        
        return user
    
    return role_checker


def require_api_key_permission(*permissions: str):
    """
    Dependency factory for API key permission checking.
    
    Usage:
        @router.post("/events")
        async def create_event(
            user: CurrentUser = Depends(require_api_key_permission("write"))
        ):
            ...
    """
    async def api_key_checker(
        request: Request,
        user: CurrentUser = Depends(get_current_user_with_org)
    ) -> CurrentUser:
        # Only check for API key requests
        if not user.user_id.startswith("api_key:"):
            return user
        
        # Check permissions
        user_perms = [p.value for p in user.permissions]
        has_any = any(p in user_perms for p in permissions)
        
        if not has_any:
            raise HTTPException(
                status_code=403,
                detail=f"API key missing permission. Required: {permissions}"
            )
        
        return user
    
    return api_key_checker


async def get_optional_user(
    credentials: HTTPAuthorizationCredentials = Depends(security)
) -> Optional[CurrentUser]:
    """
    Get the current user if authenticated, otherwise return None.
    """
    if not credentials:
        return None
    
    user_service = get_user_service()
    payload = user_service.verify_token(credentials.credentials)
    
    if not payload:
        return None
    
    user = await user_service.get_user(payload["sub"])
    
    if not user or not user.is_active:
        return None
    
    from auth.models.entities import get_permissions
    permissions = get_permissions(user.role)
    
    return CurrentUser(
        user_id=user.id,
        organization_id=user.organization_id,
        role=user.role,
        email=user.email,
        name=user.name,
        permissions=permissions
    )


class TenantContext:
    """
    Context manager for tenant-scoped operations.
    
    Ensures all database queries are scoped to the current organization.
    """
    
    def __init__(self, organization_id: str):
        self.organization_id = organization_id
    
    def scope_query(self, query: dict) -> dict:
        """Add organization_id to a query."""
        return {**query, "organization_id": self.organization_id}


async def get_tenant_context(
    user: CurrentUser = Depends(get_current_user_with_org)
) -> TenantContext:
    """Get tenant context for the current user."""
    return TenantContext(user.organization_id)


# =============================================================================
# RATE LIMITING PER ORGANIZATION
# =============================================================================

class OrgRateLimiter:
    """
    Rate limiter that respects organization-level limits.
    """
    
    def __init__(self):
        # In-memory tracking (use Redis in production)
        self.request_counts: dict = {}
    
    async def check_limit(
        self,
        organization_id: str,
        limit: int,
        window_seconds: int = 60
    ) -> bool:
        """Check if organization is within rate limit."""
        import time
        
        key = f"{organization_id}:{int(time.time() / window_seconds)}"
        
        count = self.request_counts.get(key, 0)
        
        if count >= limit:
            return False
        
        self.request_counts[key] = count + 1
        return True


_org_rate_limiter = OrgRateLimiter()


async def check_org_rate_limit(
    user: CurrentUser = Depends(get_current_user_with_org)
):
    """Check organization-level rate limit."""
    # Get organization limit (from plan)
    from auth.services.organization_service import get_org_service
    org_service = get_org_service()
    org = await org_service.get_organization(user.organization_id)
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    # Default limit based on plan
    limits = {
        "free": 100,
        "starter": 500,
        "professional": 2000,
        "enterprise": 10000,
    }
    
    limit = limits.get(org.plan, 100)
    
    if not await _org_rate_limiter.check_limit(user.organization_id, limit):
        raise HTTPException(
            status_code=429,
            detail="Organization rate limit exceeded"
        )
