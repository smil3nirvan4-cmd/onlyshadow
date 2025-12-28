"""
SSI Shadow - Multi-tenant Authentication
"""
from .models.entities import (
    Organization, User, Team, APIKey, Invitation,
    UserRole, PlanTier, Permission,
    OrganizationCreate, UserCreate, TeamCreate, APIKeyCreate,
    SSOConfig
)
from .services.organization_service import OrganizationService, get_org_service, init_org_service
from .services.user_service import UserService, get_user_service, init_user_service
from .services.team_api_key_service import TeamService, APIKeyService
from .services.sso_service import SSOService
from .middleware.permissions import require_permission, require_role

__all__ = [
    "Organization", "User", "Team", "APIKey", "Invitation",
    "UserRole", "PlanTier", "Permission",
    "OrganizationCreate", "UserCreate", "TeamCreate", "APIKeyCreate",
    "SSOConfig",
    "OrganizationService", "get_org_service", "init_org_service",
    "UserService", "get_user_service", "init_user_service",
    "TeamService", "APIKeyService", "SSOService",
    "require_permission", "require_role",
]
__version__ = "2.0.0"
