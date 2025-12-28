"""Auth Middleware - RBAC and Permissions"""
from .permissions import (
    require_permission,
    require_role,
    require_api_key_permission,
    get_current_user_with_org,
    get_optional_user,
    CurrentUser,
    TenantContext,
    get_tenant_context,
    OrgRateLimiter,
    check_org_rate_limit,
)

# Import Permission from entities since it's defined there
from auth.models.entities import Permission

__all__ = [
    "require_permission",
    "require_role",
    "require_api_key_permission",
    "get_current_user_with_org",
    "get_optional_user",
    "CurrentUser",
    "TenantContext",
    "get_tenant_context",
    "OrgRateLimiter",
    "check_org_rate_limit",
    "Permission",
]
