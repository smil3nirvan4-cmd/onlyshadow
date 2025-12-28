"""
S.S.I. SHADOW - Multi-Tenant Data Models
========================================
Database models for organizations, users, teams, and permissions.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, EmailStr, validator
import uuid


# =============================================================================
# ENUMS
# =============================================================================

class UserRole(str, Enum):
    """User roles within an organization."""
    OWNER = "owner"          # Full access, can delete org
    ADMIN = "admin"          # Full access except org deletion
    MANAGER = "manager"      # Can manage team members and settings
    ANALYST = "analyst"      # Can view all data, limited writes
    VIEWER = "viewer"        # Read-only access


class PlanTier(str, Enum):
    """Subscription plan tiers."""
    FREE = "free"
    STARTER = "starter"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class InvitationStatus(str, Enum):
    """Invitation status."""
    PENDING = "pending"
    ACCEPTED = "accepted"
    EXPIRED = "expired"
    REVOKED = "revoked"


class AuditAction(str, Enum):
    """Audit log actions."""
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    USER_ROLE_CHANGED = "user.role_changed"
    
    ORG_CREATED = "org.created"
    ORG_UPDATED = "org.updated"
    ORG_DELETED = "org.deleted"
    
    TEAM_CREATED = "team.created"
    TEAM_UPDATED = "team.updated"
    TEAM_DELETED = "team.deleted"
    TEAM_MEMBER_ADDED = "team.member_added"
    TEAM_MEMBER_REMOVED = "team.member_removed"
    
    INVITATION_SENT = "invitation.sent"
    INVITATION_ACCEPTED = "invitation.accepted"
    INVITATION_REVOKED = "invitation.revoked"
    
    API_KEY_CREATED = "api_key.created"
    API_KEY_REVOKED = "api_key.revoked"
    
    SETTINGS_UPDATED = "settings.updated"
    CREDENTIALS_UPDATED = "credentials.updated"
    
    EXPORT_REQUESTED = "export.requested"
    DATA_DELETED = "data.deleted"


# =============================================================================
# PERMISSION DEFINITIONS
# =============================================================================

class Permission(str, Enum):
    """Granular permissions."""
    # Dashboard
    DASHBOARD_VIEW = "dashboard:view"
    DASHBOARD_EXPORT = "dashboard:export"
    
    # Events
    EVENTS_VIEW = "events:view"
    EVENTS_EXPORT = "events:export"
    
    # Settings
    SETTINGS_VIEW = "settings:view"
    SETTINGS_EDIT = "settings:edit"
    CREDENTIALS_EDIT = "credentials:edit"
    
    # Users
    USERS_VIEW = "users:view"
    USERS_INVITE = "users:invite"
    USERS_EDIT = "users:edit"
    USERS_DELETE = "users:delete"
    
    # Teams
    TEAMS_VIEW = "teams:view"
    TEAMS_CREATE = "teams:create"
    TEAMS_EDIT = "teams:edit"
    TEAMS_DELETE = "teams:delete"
    
    # API Keys
    API_KEYS_VIEW = "api_keys:view"
    API_KEYS_CREATE = "api_keys:create"
    API_KEYS_REVOKE = "api_keys:revoke"
    
    # Billing
    BILLING_VIEW = "billing:view"
    BILLING_EDIT = "billing:edit"
    
    # Organization
    ORG_SETTINGS = "org:settings"
    ORG_DELETE = "org:delete"


# Role permission mappings
ROLE_PERMISSIONS: Dict[UserRole, List[Permission]] = {
    UserRole.OWNER: list(Permission),  # All permissions
    
    UserRole.ADMIN: [
        Permission.DASHBOARD_VIEW, Permission.DASHBOARD_EXPORT,
        Permission.EVENTS_VIEW, Permission.EVENTS_EXPORT,
        Permission.SETTINGS_VIEW, Permission.SETTINGS_EDIT, Permission.CREDENTIALS_EDIT,
        Permission.USERS_VIEW, Permission.USERS_INVITE, Permission.USERS_EDIT, Permission.USERS_DELETE,
        Permission.TEAMS_VIEW, Permission.TEAMS_CREATE, Permission.TEAMS_EDIT, Permission.TEAMS_DELETE,
        Permission.API_KEYS_VIEW, Permission.API_KEYS_CREATE, Permission.API_KEYS_REVOKE,
        Permission.BILLING_VIEW, Permission.BILLING_EDIT,
        Permission.ORG_SETTINGS,
    ],
    
    UserRole.MANAGER: [
        Permission.DASHBOARD_VIEW, Permission.DASHBOARD_EXPORT,
        Permission.EVENTS_VIEW, Permission.EVENTS_EXPORT,
        Permission.SETTINGS_VIEW,
        Permission.USERS_VIEW, Permission.USERS_INVITE,
        Permission.TEAMS_VIEW, Permission.TEAMS_CREATE, Permission.TEAMS_EDIT,
        Permission.API_KEYS_VIEW,
    ],
    
    UserRole.ANALYST: [
        Permission.DASHBOARD_VIEW, Permission.DASHBOARD_EXPORT,
        Permission.EVENTS_VIEW, Permission.EVENTS_EXPORT,
        Permission.SETTINGS_VIEW,
        Permission.USERS_VIEW,
        Permission.TEAMS_VIEW,
    ],
    
    UserRole.VIEWER: [
        Permission.DASHBOARD_VIEW,
        Permission.EVENTS_VIEW,
    ],
}


def has_permission(role: UserRole, permission: Permission) -> bool:
    """Check if a role has a specific permission."""
    return permission in ROLE_PERMISSIONS.get(role, [])


def get_permissions(role: UserRole) -> List[Permission]:
    """Get all permissions for a role."""
    return ROLE_PERMISSIONS.get(role, [])


# =============================================================================
# ORGANIZATION MODEL
# =============================================================================

class Organization(BaseModel):
    """Organization (tenant) model."""
    id: str = Field(default_factory=lambda: f"org_{uuid.uuid4().hex[:16]}")
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    
    # Plan & Billing
    plan: PlanTier = PlanTier.FREE
    stripe_customer_id: Optional[str] = None
    subscription_status: str = "active"
    
    # Limits (based on plan)
    events_limit: int = 10000  # Monthly events
    users_limit: int = 3
    api_keys_limit: int = 2
    
    # Settings
    settings: Dict[str, Any] = Field(default_factory=dict)
    
    # Platform credentials (encrypted)
    meta_pixel_id: Optional[str] = None
    meta_access_token_encrypted: Optional[str] = None
    tiktok_pixel_id: Optional[str] = None
    tiktok_access_token_encrypted: Optional[str] = None
    ga4_measurement_id: Optional[str] = None
    ga4_api_secret_encrypted: Optional[str] = None
    
    # Feature flags
    features: Dict[str, bool] = Field(default_factory=lambda: {
        "trust_score": True,
        "ml_predictions": False,
        "bid_optimization": False,
        "real_time": True,
        "exports": True,
        "api_access": False,
        "custom_domains": False,
        "white_label": False,
    })
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: Optional[str] = None
    
    # Status
    is_active: bool = True
    suspended_at: Optional[datetime] = None
    suspended_reason: Optional[str] = None
    
    class Config:
        use_enum_values = True


class OrganizationCreate(BaseModel):
    """Schema for creating an organization."""
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(..., min_length=2, max_length=50, pattern=r"^[a-z0-9-]+$")
    plan: PlanTier = PlanTier.FREE


class OrganizationUpdate(BaseModel):
    """Schema for updating an organization."""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    settings: Optional[Dict[str, Any]] = None
    features: Optional[Dict[str, bool]] = None


# =============================================================================
# USER MODEL
# =============================================================================

class User(BaseModel):
    """User model."""
    id: str = Field(default_factory=lambda: f"usr_{uuid.uuid4().hex[:16]}")
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)
    
    # Auth
    password_hash: Optional[str] = None  # None for SSO users
    auth_provider: str = "email"  # email, google, microsoft, saml
    auth_provider_id: Optional[str] = None
    
    # Organization
    organization_id: str
    role: UserRole = UserRole.VIEWER
    
    # Teams
    team_ids: List[str] = Field(default_factory=list)
    
    # Profile
    avatar_url: Optional[str] = None
    timezone: str = "UTC"
    locale: str = "en"
    
    # Security
    mfa_enabled: bool = False
    mfa_secret_encrypted: Optional[str] = None
    
    # Status
    is_active: bool = True
    is_verified: bool = False
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    last_login_at: Optional[datetime] = None
    last_login_ip: Optional[str] = None
    
    # Preferences
    preferences: Dict[str, Any] = Field(default_factory=lambda: {
        "email_notifications": True,
        "slack_notifications": False,
        "weekly_digest": True,
        "theme": "system",
    })
    
    class Config:
        use_enum_values = True


class UserCreate(BaseModel):
    """Schema for creating a user."""
    email: EmailStr
    name: str = Field(..., min_length=2, max_length=100)
    password: Optional[str] = Field(None, min_length=8)
    role: UserRole = UserRole.VIEWER


class UserUpdate(BaseModel):
    """Schema for updating a user."""
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    role: Optional[UserRole] = None
    avatar_url: Optional[str] = None
    timezone: Optional[str] = None
    locale: Optional[str] = None
    preferences: Optional[Dict[str, Any]] = None


class UserPublic(BaseModel):
    """Public user information."""
    id: str
    email: EmailStr
    name: str
    role: UserRole
    avatar_url: Optional[str] = None
    is_active: bool
    created_at: datetime
    last_login_at: Optional[datetime] = None


# =============================================================================
# TEAM MODEL
# =============================================================================

class Team(BaseModel):
    """Team model for organizing users within an organization."""
    id: str = Field(default_factory=lambda: f"team_{uuid.uuid4().hex[:12]}")
    organization_id: str
    name: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None
    
    # Members
    member_ids: List[str] = Field(default_factory=list)
    
    # Permissions (additional team-specific permissions)
    permissions: List[str] = Field(default_factory=list)
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: str
    
    class Config:
        use_enum_values = True


class TeamCreate(BaseModel):
    """Schema for creating a team."""
    name: str = Field(..., min_length=2, max_length=50)
    description: Optional[str] = None
    member_ids: List[str] = Field(default_factory=list)


class TeamUpdate(BaseModel):
    """Schema for updating a team."""
    name: Optional[str] = Field(None, min_length=2, max_length=50)
    description: Optional[str] = None


# =============================================================================
# INVITATION MODEL
# =============================================================================

class Invitation(BaseModel):
    """Invitation model for inviting users to an organization."""
    id: str = Field(default_factory=lambda: f"inv_{uuid.uuid4().hex[:16]}")
    organization_id: str
    
    # Invite details
    email: EmailStr
    role: UserRole = UserRole.VIEWER
    team_ids: List[str] = Field(default_factory=list)
    
    # Token
    token: str = Field(default_factory=lambda: uuid.uuid4().hex)
    
    # Status
    status: InvitationStatus = InvitationStatus.PENDING
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    invited_by: str
    accepted_at: Optional[datetime] = None
    accepted_by_user_id: Optional[str] = None
    
    class Config:
        use_enum_values = True


class InvitationCreate(BaseModel):
    """Schema for creating an invitation."""
    email: EmailStr
    role: UserRole = UserRole.VIEWER
    team_ids: List[str] = Field(default_factory=list)


# =============================================================================
# API KEY MODEL
# =============================================================================

class APIKey(BaseModel):
    """API key model for programmatic access."""
    id: str = Field(default_factory=lambda: f"key_{uuid.uuid4().hex[:12]}")
    organization_id: str
    
    # Key details
    name: str = Field(..., min_length=2, max_length=50)
    key_prefix: str  # First 8 chars for identification
    key_hash: str  # Full key hash
    
    # Permissions
    permissions: List[str] = Field(default_factory=lambda: ["read"])
    
    # Rate limiting
    rate_limit: int = 1000  # Requests per minute
    
    # Status
    is_active: bool = True
    
    # Usage
    last_used_at: Optional[datetime] = None
    usage_count: int = 0
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: Optional[datetime] = None
    created_by: str
    
    class Config:
        use_enum_values = True


class APIKeyCreate(BaseModel):
    """Schema for creating an API key."""
    name: str = Field(..., min_length=2, max_length=50)
    permissions: List[str] = Field(default_factory=lambda: ["read"])
    rate_limit: int = Field(1000, ge=10, le=10000)
    expires_in_days: Optional[int] = Field(None, ge=1, le=365)


class APIKeyResponse(BaseModel):
    """Response after creating an API key (includes the key only once)."""
    id: str
    name: str
    key: str  # Only returned on creation
    permissions: List[str]
    rate_limit: int
    created_at: datetime
    expires_at: Optional[datetime] = None


# =============================================================================
# AUDIT LOG MODEL
# =============================================================================

class AuditLog(BaseModel):
    """Audit log entry."""
    id: str = Field(default_factory=lambda: f"audit_{uuid.uuid4().hex[:16]}")
    organization_id: str
    
    # Actor
    actor_id: str
    actor_type: str = "user"  # user, api_key, system
    actor_email: Optional[str] = None
    
    # Action
    action: AuditAction
    resource_type: str  # user, team, org, settings, etc.
    resource_id: Optional[str] = None
    
    # Details
    description: str
    changes: Optional[Dict[str, Any]] = None  # Before/after for updates
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    # Request context
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    
    # Timestamp
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


# =============================================================================
# SESSION MODEL
# =============================================================================

class Session(BaseModel):
    """User session model."""
    id: str = Field(default_factory=lambda: f"sess_{uuid.uuid4().hex[:16]}")
    user_id: str
    organization_id: str
    
    # Token
    refresh_token_hash: str
    
    # Device info
    device_name: Optional[str] = None
    device_type: Optional[str] = None  # desktop, mobile, tablet
    browser: Optional[str] = None
    os: Optional[str] = None
    
    # Location
    ip_address: str
    country: Optional[str] = None
    city: Optional[str] = None
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_active_at: datetime = Field(default_factory=datetime.utcnow)
    expires_at: datetime
    
    # Status
    is_active: bool = True
    revoked_at: Optional[datetime] = None
    revoked_reason: Optional[str] = None


# =============================================================================
# SSO CONFIGURATION
# =============================================================================

class SSOConfig(BaseModel):
    """SSO configuration for an organization."""
    id: str = Field(default_factory=lambda: f"sso_{uuid.uuid4().hex[:12]}")
    organization_id: str
    
    # Provider
    provider: str  # saml, google, microsoft, okta
    
    # SAML settings
    entity_id: Optional[str] = None
    sso_url: Optional[str] = None
    certificate: Optional[str] = None
    
    # OAuth settings
    client_id: Optional[str] = None
    client_secret_encrypted: Optional[str] = None
    
    # Settings
    enforce_sso: bool = False  # Require SSO for all users
    auto_provision: bool = True  # Auto-create users on first login
    default_role: UserRole = UserRole.VIEWER
    
    # Domain restrictions
    allowed_domains: List[str] = Field(default_factory=list)
    
    # Status
    is_active: bool = True
    
    # Metadata
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    class Config:
        use_enum_values = True


class SSOConfigCreate(BaseModel):
    """Schema for creating SSO configuration."""
    provider: str
    entity_id: Optional[str] = None
    sso_url: Optional[str] = None
    certificate: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    enforce_sso: bool = False
    auto_provision: bool = True
    default_role: UserRole = UserRole.VIEWER
    allowed_domains: List[str] = Field(default_factory=list)
