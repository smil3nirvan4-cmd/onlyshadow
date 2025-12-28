"""
S.S.I. SHADOW - Team & API Key Service
======================================
Services for managing teams and API keys.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List
import secrets
import hashlib

from auth.models.entities import (
    Team,
    TeamCreate,
    TeamUpdate,
    APIKey,
    APIKeyCreate,
    APIKeyResponse,
    AuditLog,
    AuditAction,
)
from auth.services.organization_service import get_org_service

logger = logging.getLogger(__name__)


# =============================================================================
# TEAM SERVICE
# =============================================================================

class TeamService:
    """
    Service for managing teams within organizations.
    """
    
    def __init__(self):
        # In-memory store (replace with database in production)
        self.teams: Dict[str, Team] = {}
        self.audit_logs: List[AuditLog] = []
    
    async def create_team(
        self,
        org_id: str,
        data: TeamCreate,
        created_by: str
    ) -> Team:
        """Create a new team."""
        team = Team(
            organization_id=org_id,
            name=data.name,
            description=data.description,
            member_ids=data.member_ids,
            created_by=created_by
        )
        
        self.teams[team.id] = team
        
        # Audit log
        await self._audit_log(
            org_id,
            created_by,
            AuditAction.TEAM_CREATED,
            "team",
            team.id,
            f"Team '{team.name}' created"
        )
        
        logger.info(f"Team created: {team.id} ({team.name})")
        return team
    
    async def get_team(self, team_id: str) -> Optional[Team]:
        """Get a team by ID."""
        return self.teams.get(team_id)
    
    async def get_teams_by_organization(self, org_id: str) -> List[Team]:
        """Get all teams in an organization."""
        return [
            team for team in self.teams.values()
            if team.organization_id == org_id
        ]
    
    async def get_teams_for_user(self, user_id: str) -> List[Team]:
        """Get all teams a user belongs to."""
        return [
            team for team in self.teams.values()
            if user_id in team.member_ids
        ]
    
    async def update_team(
        self,
        team_id: str,
        data: TeamUpdate,
        updated_by: str
    ) -> Optional[Team]:
        """Update a team."""
        team = self.teams.get(team_id)
        if not team:
            return None
        
        changes = {}
        
        if data.name is not None and data.name != team.name:
            changes["name"] = {"old": team.name, "new": data.name}
            team.name = data.name
        
        if data.description is not None:
            team.description = data.description
        
        team.updated_at = datetime.utcnow()
        
        # Audit log
        if changes:
            await self._audit_log(
                team.organization_id,
                updated_by,
                AuditAction.TEAM_UPDATED,
                "team",
                team_id,
                "Team updated",
                changes
            )
        
        return team
    
    async def delete_team(
        self,
        team_id: str,
        deleted_by: str
    ) -> bool:
        """Delete a team."""
        team = self.teams.get(team_id)
        if not team:
            return False
        
        org_id = team.organization_id
        team_name = team.name
        
        del self.teams[team_id]
        
        # Audit log
        await self._audit_log(
            org_id,
            deleted_by,
            AuditAction.TEAM_DELETED,
            "team",
            team_id,
            f"Team '{team_name}' deleted"
        )
        
        logger.info(f"Team deleted: {team_id}")
        return True
    
    async def add_member(
        self,
        team_id: str,
        user_id: str,
        added_by: str
    ) -> bool:
        """Add a member to a team."""
        team = self.teams.get(team_id)
        if not team:
            return False
        
        if user_id in team.member_ids:
            return True  # Already a member
        
        team.member_ids.append(user_id)
        team.updated_at = datetime.utcnow()
        
        # Audit log
        await self._audit_log(
            team.organization_id,
            added_by,
            AuditAction.TEAM_MEMBER_ADDED,
            "team",
            team_id,
            f"User added to team '{team.name}'",
            metadata={"user_id": user_id}
        )
        
        return True
    
    async def remove_member(
        self,
        team_id: str,
        user_id: str,
        removed_by: str
    ) -> bool:
        """Remove a member from a team."""
        team = self.teams.get(team_id)
        if not team:
            return False
        
        if user_id not in team.member_ids:
            return True  # Not a member
        
        team.member_ids.remove(user_id)
        team.updated_at = datetime.utcnow()
        
        # Audit log
        await self._audit_log(
            team.organization_id,
            removed_by,
            AuditAction.TEAM_MEMBER_REMOVED,
            "team",
            team_id,
            f"User removed from team '{team.name}'",
            metadata={"user_id": user_id}
        )
        
        return True
    
    async def _audit_log(
        self,
        org_id: str,
        actor_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[str],
        description: str,
        changes: Dict = None,
        metadata: Dict = None
    ):
        """Create an audit log entry."""
        log = AuditLog(
            organization_id=org_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            changes=changes,
            metadata=metadata or {}
        )
        
        self.audit_logs.append(log)


# =============================================================================
# API KEY SERVICE
# =============================================================================

class APIKeyService:
    """
    Service for managing API keys.
    """
    
    def __init__(self):
        # In-memory store (replace with database in production)
        self.api_keys: Dict[str, APIKey] = {}
        self.api_keys_by_prefix: Dict[str, str] = {}  # prefix -> key_id
        self.audit_logs: List[AuditLog] = []
    
    def _generate_key(self) -> str:
        """Generate a new API key."""
        return f"ssi_{secrets.token_urlsafe(32)}"
    
    def _hash_key(self, key: str) -> str:
        """Hash an API key."""
        return hashlib.sha256(key.encode()).hexdigest()
    
    def _get_prefix(self, key: str) -> str:
        """Get the prefix of an API key for identification."""
        return key[:12]  # ssi_ + 8 chars
    
    async def create_api_key(
        self,
        org_id: str,
        data: APIKeyCreate,
        created_by: str
    ) -> APIKeyResponse:
        """Create a new API key."""
        # Check organization limit
        org_service = get_org_service()
        if not await org_service.check_limit(org_id, "api_keys"):
            raise ValueError("Organization API key limit reached")
        
        # Generate key
        key = self._generate_key()
        key_hash = self._hash_key(key)
        key_prefix = self._get_prefix(key)
        
        # Calculate expiry
        expires_at = None
        if data.expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=data.expires_in_days)
        
        # Create API key record
        api_key = APIKey(
            organization_id=org_id,
            name=data.name,
            key_prefix=key_prefix,
            key_hash=key_hash,
            permissions=data.permissions,
            rate_limit=data.rate_limit,
            expires_at=expires_at,
            created_by=created_by
        )
        
        self.api_keys[api_key.id] = api_key
        self.api_keys_by_prefix[key_prefix] = api_key.id
        
        # Audit log
        await self._audit_log(
            org_id,
            created_by,
            AuditAction.API_KEY_CREATED,
            "api_key",
            api_key.id,
            f"API key '{data.name}' created"
        )
        
        logger.info(f"API key created: {api_key.id} ({data.name})")
        
        # Return response with the actual key (only time it's shown)
        return APIKeyResponse(
            id=api_key.id,
            name=api_key.name,
            key=key,  # Only returned on creation!
            permissions=api_key.permissions,
            rate_limit=api_key.rate_limit,
            created_at=api_key.created_at,
            expires_at=api_key.expires_at
        )
    
    async def get_api_key(self, key_id: str) -> Optional[APIKey]:
        """Get an API key by ID."""
        return self.api_keys.get(key_id)
    
    async def get_api_keys_by_organization(self, org_id: str) -> List[APIKey]:
        """Get all API keys for an organization."""
        return [
            key for key in self.api_keys.values()
            if key.organization_id == org_id and key.is_active
        ]
    
    async def validate_api_key(self, key: str) -> Optional[APIKey]:
        """Validate an API key and return the key record if valid."""
        key_prefix = self._get_prefix(key)
        key_id = self.api_keys_by_prefix.get(key_prefix)
        
        if not key_id:
            return None
        
        api_key = self.api_keys.get(key_id)
        
        if not api_key:
            return None
        
        # Check if active
        if not api_key.is_active:
            return None
        
        # Check expiry
        if api_key.expires_at and api_key.expires_at < datetime.utcnow():
            return None
        
        # Verify hash
        if api_key.key_hash != self._hash_key(key):
            return None
        
        # Update usage
        api_key.last_used_at = datetime.utcnow()
        api_key.usage_count += 1
        
        return api_key
    
    async def revoke_api_key(
        self,
        key_id: str,
        revoked_by: str
    ) -> bool:
        """Revoke an API key."""
        api_key = self.api_keys.get(key_id)
        
        if not api_key:
            return False
        
        api_key.is_active = False
        
        # Audit log
        await self._audit_log(
            api_key.organization_id,
            revoked_by,
            AuditAction.API_KEY_REVOKED,
            "api_key",
            key_id,
            f"API key '{api_key.name}' revoked"
        )
        
        logger.info(f"API key revoked: {key_id}")
        return True
    
    async def rotate_api_key(
        self,
        key_id: str,
        rotated_by: str
    ) -> Optional[APIKeyResponse]:
        """Rotate an API key (revoke old, create new with same settings)."""
        old_key = self.api_keys.get(key_id)
        
        if not old_key:
            return None
        
        # Revoke old key
        await self.revoke_api_key(key_id, rotated_by)
        
        # Create new key with same settings
        return await self.create_api_key(
            old_key.organization_id,
            APIKeyCreate(
                name=old_key.name,
                permissions=old_key.permissions,
                rate_limit=old_key.rate_limit
            ),
            rotated_by
        )
    
    async def _audit_log(
        self,
        org_id: str,
        actor_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[str],
        description: str,
        changes: Dict = None,
        metadata: Dict = None
    ):
        """Create an audit log entry."""
        log = AuditLog(
            organization_id=org_id,
            actor_id=actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            description=description,
            changes=changes,
            metadata=metadata or {}
        )
        
        self.audit_logs.append(log)


# =============================================================================
# SINGLETONS
# =============================================================================

_team_service: Optional[TeamService] = None
_api_key_service: Optional[APIKeyService] = None


def get_team_service() -> TeamService:
    """Get or create the team service."""
    global _team_service
    if _team_service is None:
        _team_service = TeamService()
    return _team_service


def get_api_key_service() -> APIKeyService:
    """Get or create the API key service."""
    global _api_key_service
    if _api_key_service is None:
        _api_key_service = APIKeyService()
    return _api_key_service
