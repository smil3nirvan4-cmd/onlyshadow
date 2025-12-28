"""
S.S.I. SHADOW - Multi-Tenant Routes
===================================
API routes for organization, user, team, and API key management.
"""

import logging
from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, HTTPException, Query, Path, Request

from auth.models.entities import (
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
    User,
    UserCreate,
    UserUpdate,
    UserPublic,
    UserRole,
    Team,
    TeamCreate,
    TeamUpdate,
    Invitation,
    InvitationCreate,
    APIKey,
    APIKeyCreate,
    APIKeyResponse,
    Permission,
    has_permission,
    SSOConfig,
    SSOConfigCreate,
)
from auth.services.organization_service import get_org_service
from auth.services.user_service import get_user_service
from auth.services.team_api_key_service import get_team_service, get_api_key_service
from auth.services.sso_service import get_sso_service
from auth.middleware.permissions import (
    require_permission,
    require_role,
    get_current_user_with_org,
    CurrentUser,
)

logger = logging.getLogger(__name__)


# =============================================================================
# ORGANIZATION ROUTES
# =============================================================================

org_router = APIRouter(prefix="/api/organizations", tags=["Organizations"])


@org_router.get(
    "/current",
    response_model=Organization,
    summary="Get current organization",
)
async def get_current_organization(
    user: CurrentUser = Depends(get_current_user_with_org)
):
    """Get the current user's organization."""
    org_service = get_org_service()
    org = await org_service.get_organization(user.organization_id)
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    return org


@org_router.put(
    "/current",
    response_model=Organization,
    summary="Update current organization",
)
async def update_current_organization(
    data: OrganizationUpdate,
    user: CurrentUser = Depends(require_permission(Permission.ORG_SETTINGS))
):
    """Update the current organization."""
    org_service = get_org_service()
    org = await org_service.update_organization(
        user.organization_id,
        data,
        user.user_id
    )
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    return org


@org_router.get(
    "/current/usage",
    summary="Get organization usage",
)
async def get_organization_usage(
    user: CurrentUser = Depends(get_current_user_with_org)
):
    """Get the current organization's usage metrics."""
    org_service = get_org_service()
    return await org_service.get_usage(user.organization_id)


@org_router.put(
    "/current/credentials/{platform}",
    summary="Update platform credentials",
)
async def update_platform_credentials(
    platform: str = Path(..., pattern="^(meta|tiktok|google)$"),
    credentials: dict = None,
    user: CurrentUser = Depends(require_permission(Permission.CREDENTIALS_EDIT))
):
    """Update platform credentials (Meta, TikTok, Google)."""
    org_service = get_org_service()
    
    success = await org_service.update_platform_credentials(
        user.organization_id,
        platform,
        credentials,
        user.user_id
    )
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to update credentials")
    
    return {"status": "updated", "platform": platform}


# =============================================================================
# USER ROUTES
# =============================================================================

user_router = APIRouter(prefix="/api/users", tags=["Users"])


@user_router.get(
    "",
    response_model=List[UserPublic],
    summary="List organization users",
)
async def list_users(
    include_inactive: bool = Query(False),
    user: CurrentUser = Depends(require_permission(Permission.USERS_VIEW))
):
    """List all users in the organization."""
    user_service = get_user_service()
    users = await user_service.get_users_by_organization(
        user.organization_id,
        include_inactive
    )
    
    return [
        UserPublic(
            id=u.id,
            email=u.email,
            name=u.name,
            role=u.role,
            avatar_url=u.avatar_url,
            is_active=u.is_active,
            created_at=u.created_at,
            last_login_at=u.last_login_at
        )
        for u in users
    ]


@user_router.get(
    "/{user_id}",
    response_model=UserPublic,
    summary="Get user details",
)
async def get_user(
    user_id: str = Path(...),
    current_user: CurrentUser = Depends(require_permission(Permission.USERS_VIEW))
):
    """Get details of a specific user."""
    user_service = get_user_service()
    user = await user_service.get_user(user_id)
    
    if not user or user.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at
    )


@user_router.put(
    "/{user_id}",
    response_model=UserPublic,
    summary="Update user",
)
async def update_user(
    data: UserUpdate,
    user_id: str = Path(...),
    current_user: CurrentUser = Depends(require_permission(Permission.USERS_EDIT))
):
    """Update a user's details."""
    user_service = get_user_service()
    
    # Check user exists in org
    target_user = await user_service.get_user(user_id)
    if not target_user or target_user.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Check role change permissions
    if data.role is not None:
        # Only admins/owners can change roles
        if current_user.role not in [UserRole.ADMIN, UserRole.OWNER]:
            raise HTTPException(status_code=403, detail="Cannot change user roles")
        
        # Can't demote an owner unless you're also an owner
        if target_user.role == UserRole.OWNER and current_user.role != UserRole.OWNER:
            raise HTTPException(status_code=403, detail="Cannot change owner's role")
        
        # Can't promote to owner unless you're an owner
        if data.role == UserRole.OWNER and current_user.role != UserRole.OWNER:
            raise HTTPException(status_code=403, detail="Cannot promote to owner")
    
    user = await user_service.update_user(user_id, data, current_user.user_id)
    
    return UserPublic(
        id=user.id,
        email=user.email,
        name=user.name,
        role=user.role,
        avatar_url=user.avatar_url,
        is_active=user.is_active,
        created_at=user.created_at,
        last_login_at=user.last_login_at
    )


@user_router.delete(
    "/{user_id}",
    status_code=204,
    summary="Delete user",
)
async def delete_user(
    user_id: str = Path(...),
    current_user: CurrentUser = Depends(require_permission(Permission.USERS_DELETE))
):
    """Delete a user from the organization."""
    user_service = get_user_service()
    
    # Check user exists in org
    target_user = await user_service.get_user(user_id)
    if not target_user or target_user.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="User not found")
    
    try:
        await user_service.delete_user(user_id, current_user.user_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# INVITATION ROUTES
# =============================================================================

invitation_router = APIRouter(prefix="/api/invitations", tags=["Invitations"])


@invitation_router.get(
    "",
    summary="List pending invitations",
)
async def list_invitations(
    user: CurrentUser = Depends(require_permission(Permission.USERS_INVITE))
):
    """List all pending invitations."""
    user_service = get_user_service()
    invitations = await user_service.get_pending_invitations(user.organization_id)
    
    return [
        {
            "id": inv.id,
            "email": inv.email,
            "role": inv.role,
            "invited_by": inv.invited_by,
            "created_at": inv.created_at.isoformat(),
            "expires_at": inv.expires_at.isoformat(),
        }
        for inv in invitations
    ]


@invitation_router.post(
    "",
    summary="Create invitation",
)
async def create_invitation(
    data: InvitationCreate,
    user: CurrentUser = Depends(require_permission(Permission.USERS_INVITE))
):
    """Send an invitation to join the organization."""
    user_service = get_user_service()
    
    try:
        invitation = await user_service.create_invitation(
            user.organization_id,
            data,
            user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "id": invitation.id,
        "email": invitation.email,
        "role": invitation.role,
        "expires_at": invitation.expires_at.isoformat(),
        "invitation_url": f"/auth/accept-invite?token={invitation.token}"
    }


@invitation_router.delete(
    "/{invitation_id}",
    status_code=204,
    summary="Revoke invitation",
)
async def revoke_invitation(
    invitation_id: str = Path(...),
    user: CurrentUser = Depends(require_permission(Permission.USERS_INVITE))
):
    """Revoke a pending invitation."""
    user_service = get_user_service()
    
    success = await user_service.revoke_invitation(invitation_id, user.user_id)
    
    if not success:
        raise HTTPException(status_code=404, detail="Invitation not found")


@invitation_router.post(
    "/accept",
    summary="Accept invitation",
)
async def accept_invitation(
    token: str,
    name: str,
    password: str
):
    """Accept an invitation and create account."""
    user_service = get_user_service()
    
    try:
        user = await user_service.accept_invitation(token, name, password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Auto-login
    return await user_service.login(user.email, password)


# =============================================================================
# TEAM ROUTES
# =============================================================================

team_router = APIRouter(prefix="/api/teams", tags=["Teams"])


@team_router.get(
    "",
    response_model=List[Team],
    summary="List teams",
)
async def list_teams(
    user: CurrentUser = Depends(require_permission(Permission.TEAMS_VIEW))
):
    """List all teams in the organization."""
    team_service = get_team_service()
    return await team_service.get_teams_by_organization(user.organization_id)


@team_router.post(
    "",
    response_model=Team,
    summary="Create team",
)
async def create_team(
    data: TeamCreate,
    user: CurrentUser = Depends(require_permission(Permission.TEAMS_CREATE))
):
    """Create a new team."""
    team_service = get_team_service()
    
    return await team_service.create_team(
        user.organization_id,
        data,
        user.user_id
    )


@team_router.get(
    "/{team_id}",
    response_model=Team,
    summary="Get team",
)
async def get_team(
    team_id: str = Path(...),
    user: CurrentUser = Depends(require_permission(Permission.TEAMS_VIEW))
):
    """Get team details."""
    team_service = get_team_service()
    team = await team_service.get_team(team_id)
    
    if not team or team.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Team not found")
    
    return team


@team_router.put(
    "/{team_id}",
    response_model=Team,
    summary="Update team",
)
async def update_team(
    data: TeamUpdate,
    team_id: str = Path(...),
    user: CurrentUser = Depends(require_permission(Permission.TEAMS_EDIT))
):
    """Update a team."""
    team_service = get_team_service()
    
    team = await team_service.get_team(team_id)
    if not team or team.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Team not found")
    
    return await team_service.update_team(team_id, data, user.user_id)


@team_router.delete(
    "/{team_id}",
    status_code=204,
    summary="Delete team",
)
async def delete_team(
    team_id: str = Path(...),
    user: CurrentUser = Depends(require_permission(Permission.TEAMS_DELETE))
):
    """Delete a team."""
    team_service = get_team_service()
    
    team = await team_service.get_team(team_id)
    if not team or team.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="Team not found")
    
    await team_service.delete_team(team_id, user.user_id)


@team_router.post(
    "/{team_id}/members/{user_id}",
    summary="Add team member",
)
async def add_team_member(
    team_id: str = Path(...),
    user_id: str = Path(...),
    current_user: CurrentUser = Depends(require_permission(Permission.TEAMS_EDIT))
):
    """Add a user to a team."""
    team_service = get_team_service()
    user_service = get_user_service()
    
    # Verify team
    team = await team_service.get_team(team_id)
    if not team or team.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Team not found")
    
    # Verify user
    target_user = await user_service.get_user(user_id)
    if not target_user or target_user.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="User not found")
    
    await team_service.add_member(team_id, user_id, current_user.user_id)
    
    return {"status": "added"}


@team_router.delete(
    "/{team_id}/members/{user_id}",
    summary="Remove team member",
)
async def remove_team_member(
    team_id: str = Path(...),
    user_id: str = Path(...),
    current_user: CurrentUser = Depends(require_permission(Permission.TEAMS_EDIT))
):
    """Remove a user from a team."""
    team_service = get_team_service()
    
    team = await team_service.get_team(team_id)
    if not team or team.organization_id != current_user.organization_id:
        raise HTTPException(status_code=404, detail="Team not found")
    
    await team_service.remove_member(team_id, user_id, current_user.user_id)
    
    return {"status": "removed"}


# =============================================================================
# API KEY ROUTES
# =============================================================================

api_key_router = APIRouter(prefix="/api/api-keys", tags=["API Keys"])


@api_key_router.get(
    "",
    summary="List API keys",
)
async def list_api_keys(
    user: CurrentUser = Depends(require_permission(Permission.API_KEYS_VIEW))
):
    """List all API keys for the organization."""
    api_key_service = get_api_key_service()
    keys = await api_key_service.get_api_keys_by_organization(user.organization_id)
    
    return [
        {
            "id": key.id,
            "name": key.name,
            "key_prefix": key.key_prefix,
            "permissions": key.permissions,
            "rate_limit": key.rate_limit,
            "is_active": key.is_active,
            "last_used_at": key.last_used_at.isoformat() if key.last_used_at else None,
            "usage_count": key.usage_count,
            "created_at": key.created_at.isoformat(),
            "expires_at": key.expires_at.isoformat() if key.expires_at else None,
        }
        for key in keys
    ]


@api_key_router.post(
    "",
    response_model=APIKeyResponse,
    summary="Create API key",
)
async def create_api_key(
    data: APIKeyCreate,
    user: CurrentUser = Depends(require_permission(Permission.API_KEYS_CREATE))
):
    """Create a new API key. The key is only shown once!"""
    api_key_service = get_api_key_service()
    
    try:
        return await api_key_service.create_api_key(
            user.organization_id,
            data,
            user.user_id
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@api_key_router.delete(
    "/{key_id}",
    status_code=204,
    summary="Revoke API key",
)
async def revoke_api_key(
    key_id: str = Path(...),
    user: CurrentUser = Depends(require_permission(Permission.API_KEYS_REVOKE))
):
    """Revoke an API key."""
    api_key_service = get_api_key_service()
    
    key = await api_key_service.get_api_key(key_id)
    if not key or key.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="API key not found")
    
    await api_key_service.revoke_api_key(key_id, user.user_id)


@api_key_router.post(
    "/{key_id}/rotate",
    response_model=APIKeyResponse,
    summary="Rotate API key",
)
async def rotate_api_key(
    key_id: str = Path(...),
    user: CurrentUser = Depends(require_permission(Permission.API_KEYS_CREATE))
):
    """Rotate an API key (revoke old, create new)."""
    api_key_service = get_api_key_service()
    
    key = await api_key_service.get_api_key(key_id)
    if not key or key.organization_id != user.organization_id:
        raise HTTPException(status_code=404, detail="API key not found")
    
    new_key = await api_key_service.rotate_api_key(key_id, user.user_id)
    
    if not new_key:
        raise HTTPException(status_code=500, detail="Failed to rotate API key")
    
    return new_key


# =============================================================================
# SSO ROUTES
# =============================================================================

sso_router = APIRouter(prefix="/api/sso", tags=["SSO"])


@sso_router.get(
    "/config",
    summary="Get SSO configuration",
)
async def get_sso_config(
    user: CurrentUser = Depends(require_permission(Permission.ORG_SETTINGS))
):
    """Get SSO configuration for the organization."""
    sso_service = get_sso_service()
    config = await sso_service.get_sso_config(user.organization_id)
    
    if not config:
        return {"configured": False}
    
    return {
        "configured": True,
        "provider": config.provider,
        "enforce_sso": config.enforce_sso,
        "auto_provision": config.auto_provision,
        "default_role": config.default_role,
        "allowed_domains": config.allowed_domains,
    }


@sso_router.post(
    "/config",
    summary="Configure SSO",
)
async def configure_sso(
    data: SSOConfigCreate,
    user: CurrentUser = Depends(require_permission(Permission.ORG_SETTINGS))
):
    """Configure SSO for the organization."""
    sso_service = get_sso_service()
    
    try:
        # Check if config exists
        existing = await sso_service.get_sso_config(user.organization_id)
        
        if existing:
            config = await sso_service.update_sso_config(
                user.organization_id,
                data,
                user.user_id
            )
        else:
            config = await sso_service.create_sso_config(
                user.organization_id,
                data,
                user.user_id
            )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    return {
        "status": "configured",
        "provider": config.provider,
    }


@sso_router.delete(
    "/config",
    status_code=204,
    summary="Delete SSO configuration",
)
async def delete_sso_config(
    user: CurrentUser = Depends(require_permission(Permission.ORG_SETTINGS))
):
    """Delete SSO configuration."""
    sso_service = get_sso_service()
    await sso_service.delete_sso_config(user.organization_id, user.user_id)


@sso_router.get(
    "/login",
    summary="Initiate SSO login",
)
async def sso_login(
    org_slug: str = Query(...),
):
    """Initiate SSO login flow."""
    org_service = get_org_service()
    org = await org_service.get_organization_by_slug(org_slug)
    
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    
    sso_service = get_sso_service()
    config = await sso_service.get_sso_config(org.id)
    
    if not config:
        raise HTTPException(status_code=400, detail="SSO not configured")
    
    if config.provider == "saml":
        url = await sso_service.get_saml_login_url(org.id)
    else:
        url = await sso_service.get_oauth_authorization_url(org.id)
    
    return {"redirect_url": url}


@sso_router.get(
    "/callback",
    summary="SSO callback",
)
async def sso_callback(
    request: Request,
    code: str = Query(None),
    state: str = Query(None),
    error: str = Query(None),
):
    """Handle SSO callback."""
    if error:
        raise HTTPException(status_code=400, detail=f"SSO error: {error}")
    
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state")
    
    sso_service = get_sso_service()
    
    try:
        result = await sso_service.handle_oauth_callback(code, state)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# AUDIT LOG ROUTES
# =============================================================================

audit_router = APIRouter(prefix="/api/audit", tags=["Audit"])


@audit_router.get(
    "",
    summary="Get audit logs",
)
async def get_audit_logs(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    action: str = Query(None),
    resource_type: str = Query(None),
    user: CurrentUser = Depends(require_role(UserRole.ADMIN, UserRole.OWNER))
):
    """Get audit logs for the organization."""
    org_service = get_org_service()
    
    logs = await org_service.get_audit_logs(
        user.organization_id,
        limit=limit,
        offset=offset,
        action=action,
        resource_type=resource_type
    )
    
    return [
        {
            "id": log.id,
            "action": log.action,
            "actor_id": log.actor_id,
            "resource_type": log.resource_type,
            "resource_id": log.resource_id,
            "description": log.description,
            "changes": log.changes,
            "ip_address": log.ip_address,
            "created_at": log.created_at.isoformat(),
        }
        for log in logs
    ]
