"""
S.S.I. SHADOW - Organization Service
====================================
Service for managing organizations (tenants).
"""

import os
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any
import hashlib
import secrets

import redis.asyncio as redis
from cryptography.fernet import Fernet

from auth.models.entities import (
    Organization,
    OrganizationCreate,
    OrganizationUpdate,
    PlanTier,
    AuditLog,
    AuditAction,
)

logger = logging.getLogger(__name__)


# Plan limits
PLAN_LIMITS = {
    PlanTier.FREE: {
        "events_limit": 10000,
        "users_limit": 3,
        "api_keys_limit": 2,
        "features": {
            "trust_score": True,
            "ml_predictions": False,
            "bid_optimization": False,
            "real_time": True,
            "exports": True,
            "api_access": False,
            "custom_domains": False,
            "white_label": False,
        }
    },
    PlanTier.STARTER: {
        "events_limit": 100000,
        "users_limit": 10,
        "api_keys_limit": 5,
        "features": {
            "trust_score": True,
            "ml_predictions": True,
            "bid_optimization": False,
            "real_time": True,
            "exports": True,
            "api_access": True,
            "custom_domains": False,
            "white_label": False,
        }
    },
    PlanTier.PROFESSIONAL: {
        "events_limit": 1000000,
        "users_limit": 50,
        "api_keys_limit": 20,
        "features": {
            "trust_score": True,
            "ml_predictions": True,
            "bid_optimization": True,
            "real_time": True,
            "exports": True,
            "api_access": True,
            "custom_domains": True,
            "white_label": False,
        }
    },
    PlanTier.ENTERPRISE: {
        "events_limit": -1,  # Unlimited
        "users_limit": -1,
        "api_keys_limit": -1,
        "features": {
            "trust_score": True,
            "ml_predictions": True,
            "bid_optimization": True,
            "real_time": True,
            "exports": True,
            "api_access": True,
            "custom_domains": True,
            "white_label": True,
        }
    },
}


class OrganizationService:
    """
    Service for managing organizations.
    """
    
    def __init__(self, redis_url: str = None, encryption_key: str = None):
        self.redis_url = redis_url or os.getenv("REDIS_URL")
        
        # Encryption for sensitive data
        key = encryption_key or os.getenv("ENCRYPTION_KEY")
        if key:
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        else:
            # Generate a key for development (should be set in production)
            self.fernet = Fernet(Fernet.generate_key())
            logger.warning("Using generated encryption key - set ENCRYPTION_KEY in production")
        
        self._redis: Optional[redis.Redis] = None
        
        # In-memory store (replace with database in production)
        self.organizations: Dict[str, Organization] = {}
        self.organizations_by_slug: Dict[str, str] = {}
        self.audit_logs: List[AuditLog] = []
    
    async def _get_redis(self) -> Optional[redis.Redis]:
        """Get Redis connection."""
        if not self.redis_url:
            return None
        
        if self._redis is None:
            self._redis = redis.from_url(self.redis_url)
        
        return self._redis
    
    def _encrypt(self, data: str) -> str:
        """Encrypt sensitive data."""
        return self.fernet.encrypt(data.encode()).decode()
    
    def _decrypt(self, data: str) -> str:
        """Decrypt sensitive data."""
        return self.fernet.decrypt(data.encode()).decode()
    
    # =========================================================================
    # ORGANIZATION CRUD
    # =========================================================================
    
    async def create_organization(
        self,
        data: OrganizationCreate,
        created_by: str
    ) -> Organization:
        """Create a new organization."""
        # Check slug uniqueness
        if data.slug in self.organizations_by_slug:
            raise ValueError(f"Organization slug '{data.slug}' already exists")
        
        # Get plan limits
        limits = PLAN_LIMITS[data.plan]
        
        org = Organization(
            name=data.name,
            slug=data.slug,
            plan=data.plan,
            events_limit=limits["events_limit"],
            users_limit=limits["users_limit"],
            api_keys_limit=limits["api_keys_limit"],
            features=limits["features"],
            created_by=created_by
        )
        
        self.organizations[org.id] = org
        self.organizations_by_slug[org.slug] = org.id
        
        # Audit log
        await self._audit_log(
            org.id,
            created_by,
            AuditAction.ORG_CREATED,
            "organization",
            org.id,
            f"Organization '{org.name}' created"
        )
        
        logger.info(f"Organization created: {org.id} ({org.slug})")
        return org
    
    async def get_organization(self, org_id: str) -> Optional[Organization]:
        """Get an organization by ID."""
        return self.organizations.get(org_id)
    
    async def get_organization_by_slug(self, slug: str) -> Optional[Organization]:
        """Get an organization by slug."""
        org_id = self.organizations_by_slug.get(slug)
        if org_id:
            return self.organizations.get(org_id)
        return None
    
    async def update_organization(
        self,
        org_id: str,
        data: OrganizationUpdate,
        updated_by: str
    ) -> Optional[Organization]:
        """Update an organization."""
        org = self.organizations.get(org_id)
        if not org:
            return None
        
        changes = {}
        
        if data.name is not None and data.name != org.name:
            changes["name"] = {"old": org.name, "new": data.name}
            org.name = data.name
        
        if data.settings is not None:
            changes["settings"] = {"old": org.settings, "new": data.settings}
            org.settings = data.settings
        
        if data.features is not None:
            changes["features"] = {"old": org.features, "new": data.features}
            org.features.update(data.features)
        
        org.updated_at = datetime.utcnow()
        
        # Audit log
        if changes:
            await self._audit_log(
                org_id,
                updated_by,
                AuditAction.ORG_UPDATED,
                "organization",
                org_id,
                "Organization updated",
                changes
            )
        
        return org
    
    async def delete_organization(
        self,
        org_id: str,
        deleted_by: str
    ) -> bool:
        """Delete an organization (soft delete)."""
        org = self.organizations.get(org_id)
        if not org:
            return False
        
        org.is_active = False
        org.suspended_at = datetime.utcnow()
        org.suspended_reason = "deleted"
        org.updated_at = datetime.utcnow()
        
        # Remove from slug index
        if org.slug in self.organizations_by_slug:
            del self.organizations_by_slug[org.slug]
        
        # Audit log
        await self._audit_log(
            org_id,
            deleted_by,
            AuditAction.ORG_DELETED,
            "organization",
            org_id,
            f"Organization '{org.name}' deleted"
        )
        
        logger.info(f"Organization deleted: {org_id}")
        return True
    
    # =========================================================================
    # PLAN MANAGEMENT
    # =========================================================================
    
    async def upgrade_plan(
        self,
        org_id: str,
        new_plan: PlanTier,
        updated_by: str
    ) -> Optional[Organization]:
        """Upgrade an organization's plan."""
        org = self.organizations.get(org_id)
        if not org:
            return None
        
        old_plan = org.plan
        limits = PLAN_LIMITS[new_plan]
        
        org.plan = new_plan
        org.events_limit = limits["events_limit"]
        org.users_limit = limits["users_limit"]
        org.api_keys_limit = limits["api_keys_limit"]
        org.features.update(limits["features"])
        org.updated_at = datetime.utcnow()
        
        # Audit log
        await self._audit_log(
            org_id,
            updated_by,
            AuditAction.ORG_UPDATED,
            "organization",
            org_id,
            f"Plan upgraded from {old_plan} to {new_plan}",
            {"plan": {"old": old_plan, "new": new_plan}}
        )
        
        return org
    
    # =========================================================================
    # CREDENTIALS MANAGEMENT
    # =========================================================================
    
    async def update_platform_credentials(
        self,
        org_id: str,
        platform: str,
        credentials: Dict[str, str],
        updated_by: str
    ) -> bool:
        """Update platform credentials (encrypted)."""
        org = self.organizations.get(org_id)
        if not org:
            return False
        
        if platform == "meta":
            if "pixel_id" in credentials:
                org.meta_pixel_id = credentials["pixel_id"]
            if "access_token" in credentials:
                org.meta_access_token_encrypted = self._encrypt(credentials["access_token"])
        
        elif platform == "tiktok":
            if "pixel_id" in credentials:
                org.tiktok_pixel_id = credentials["pixel_id"]
            if "access_token" in credentials:
                org.tiktok_access_token_encrypted = self._encrypt(credentials["access_token"])
        
        elif platform == "google":
            if "measurement_id" in credentials:
                org.ga4_measurement_id = credentials["measurement_id"]
            if "api_secret" in credentials:
                org.ga4_api_secret_encrypted = self._encrypt(credentials["api_secret"])
        
        else:
            return False
        
        org.updated_at = datetime.utcnow()
        
        # Audit log (don't log actual credentials)
        await self._audit_log(
            org_id,
            updated_by,
            AuditAction.CREDENTIALS_UPDATED,
            "credentials",
            platform,
            f"{platform.title()} credentials updated"
        )
        
        return True
    
    async def get_platform_credentials(
        self,
        org_id: str,
        platform: str
    ) -> Optional[Dict[str, str]]:
        """Get decrypted platform credentials."""
        org = self.organizations.get(org_id)
        if not org:
            return None
        
        if platform == "meta":
            return {
                "pixel_id": org.meta_pixel_id,
                "access_token": self._decrypt(org.meta_access_token_encrypted) if org.meta_access_token_encrypted else None
            }
        
        elif platform == "tiktok":
            return {
                "pixel_id": org.tiktok_pixel_id,
                "access_token": self._decrypt(org.tiktok_access_token_encrypted) if org.tiktok_access_token_encrypted else None
            }
        
        elif platform == "google":
            return {
                "measurement_id": org.ga4_measurement_id,
                "api_secret": self._decrypt(org.ga4_api_secret_encrypted) if org.ga4_api_secret_encrypted else None
            }
        
        return None
    
    # =========================================================================
    # USAGE TRACKING
    # =========================================================================
    
    async def get_usage(self, org_id: str) -> Dict[str, Any]:
        """Get organization usage metrics."""
        org = self.organizations.get(org_id)
        if not org:
            return {}
        
        # In production, these would come from BigQuery
        # For now, return mock data
        return {
            "events": {
                "current": 5432,
                "limit": org.events_limit,
                "percentage": 54.32 if org.events_limit > 0 else 0
            },
            "users": {
                "current": 3,
                "limit": org.users_limit,
                "percentage": 100.0 if org.users_limit > 0 else 0
            },
            "api_keys": {
                "current": 1,
                "limit": org.api_keys_limit,
                "percentage": 50.0 if org.api_keys_limit > 0 else 0
            },
            "period_start": datetime.utcnow().replace(day=1).isoformat(),
            "period_end": (datetime.utcnow().replace(day=1) + timedelta(days=32)).replace(day=1).isoformat()
        }
    
    async def check_limit(self, org_id: str, resource: str, count: int = 1) -> bool:
        """Check if an organization is within its limits."""
        org = self.organizations.get(org_id)
        if not org:
            return False
        
        usage = await self.get_usage(org_id)
        
        if resource == "events":
            limit = org.events_limit
            current = usage["events"]["current"]
        elif resource == "users":
            limit = org.users_limit
            current = usage["users"]["current"]
        elif resource == "api_keys":
            limit = org.api_keys_limit
            current = usage["api_keys"]["current"]
        else:
            return True
        
        # -1 means unlimited
        if limit < 0:
            return True
        
        return (current + count) <= limit
    
    # =========================================================================
    # AUDIT LOGGING
    # =========================================================================
    
    async def _audit_log(
        self,
        org_id: str,
        actor_id: str,
        action: AuditAction,
        resource_type: str,
        resource_id: Optional[str],
        description: str,
        changes: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None
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
        
        # In production, also write to BigQuery
        logger.debug(f"Audit: {action} by {actor_id} on {resource_type}/{resource_id}")
    
    async def get_audit_logs(
        self,
        org_id: str,
        limit: int = 100,
        offset: int = 0,
        action: Optional[AuditAction] = None,
        actor_id: Optional[str] = None,
        resource_type: Optional[str] = None
    ) -> List[AuditLog]:
        """Get audit logs for an organization."""
        logs = [
            log for log in self.audit_logs
            if log.organization_id == org_id
            and (action is None or log.action == action)
            and (actor_id is None or log.actor_id == actor_id)
            and (resource_type is None or log.resource_type == resource_type)
        ]
        
        # Sort by timestamp descending
        logs.sort(key=lambda x: x.created_at, reverse=True)
        
        return logs[offset:offset + limit]
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def close(self):
        """Close connections."""
        if self._redis:
            await self._redis.close()


# =============================================================================
# SINGLETON
# =============================================================================

_org_service: Optional[OrganizationService] = None


def get_org_service() -> OrganizationService:
    """Get or create the organization service."""
    global _org_service
    if _org_service is None:
        _org_service = OrganizationService()
    return _org_service


async def init_org_service(
    redis_url: str = None,
    encryption_key: str = None
) -> OrganizationService:
    """Initialize the organization service."""
    global _org_service
    _org_service = OrganizationService(
        redis_url=redis_url,
        encryption_key=encryption_key
    )
    return _org_service
