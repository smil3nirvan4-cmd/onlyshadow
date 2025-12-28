"""
S.S.I. SHADOW - Multi-Tenancy Support
Provides tenant isolation and management.
"""

import os
import logging
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from enum import Enum

logger = logging.getLogger(__name__)

# Context variable for current tenant
_current_tenant: ContextVar[Optional[str]] = ContextVar('current_tenant', default=None)


def get_current_tenant() -> Optional[str]:
    """Get current tenant ID from context."""
    return _current_tenant.get()


def set_current_tenant(tenant_id: str):
    """Set current tenant ID in context."""
    _current_tenant.set(tenant_id)


class TenantContext:
    """Context manager for tenant operations."""
    
    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id
        self.token = None
    
    def __enter__(self):
        self.token = _current_tenant.set(self.tenant_id)
        return self
    
    def __exit__(self, *args):
        _current_tenant.reset(self.token)
    
    async def __aenter__(self):
        return self.__enter__()
    
    async def __aexit__(self, *args):
        self.__exit__(*args)


class TenantPlan(Enum):
    FREE = "free"
    STARTER = "starter"
    PRO = "pro"
    ENTERPRISE = "enterprise"


@dataclass
class TenantLimits:
    """Usage limits for a tenant plan."""
    events_per_day: int
    api_calls_per_minute: int
    campaigns: int
    users: int
    data_retention_days: int
    
    @classmethod
    def for_plan(cls, plan: TenantPlan) -> 'TenantLimits':
        limits = {
            TenantPlan.FREE: cls(10_000, 60, 5, 2, 30),
            TenantPlan.STARTER: cls(100_000, 300, 20, 5, 90),
            TenantPlan.PRO: cls(1_000_000, 1000, 100, 20, 365),
            TenantPlan.ENTERPRISE: cls(999_999_999, 10000, 999999, 999999, 730),
        }
        return limits.get(plan, limits[TenantPlan.FREE])


@dataclass
class Tenant:
    """Tenant data model."""
    id: str
    name: str
    plan: TenantPlan
    status: str = "active"
    created_at: datetime = field(default_factory=datetime.utcnow)
    settings: Dict[str, Any] = field(default_factory=dict)
    
    # Usage tracking
    events_today: int = 0
    api_calls_minute: int = 0
    
    @property
    def limits(self) -> TenantLimits:
        return TenantLimits.for_plan(self.plan)


class TenantRepository:
    """Repository for tenant data."""
    
    def __init__(self):
        self._tenants: Dict[str, Tenant] = {}
    
    async def get(self, tenant_id: str) -> Optional[Tenant]:
        return self._tenants.get(tenant_id)
    
    async def create(self, tenant: Tenant) -> Tenant:
        self._tenants[tenant.id] = tenant
        return tenant
    
    async def update(self, tenant: Tenant) -> Tenant:
        self._tenants[tenant.id] = tenant
        return tenant
    
    async def delete(self, tenant_id: str) -> bool:
        if tenant_id in self._tenants:
            del self._tenants[tenant_id]
            return True
        return False
    
    async def list_all(self) -> List[Tenant]:
        return list(self._tenants.values())


class TenantLimitChecker:
    """Checks and enforces tenant limits."""
    
    def __init__(self, repository: TenantRepository):
        self.repo = repository
    
    async def check_limit(self, limit_type: str) -> bool:
        """
        Check if current tenant is within limits.
        
        Args:
            limit_type: Type of limit to check
        
        Returns:
            True if within limits, False if exceeded
        """
        tenant_id = get_current_tenant()
        if not tenant_id:
            return False
        
        tenant = await self.repo.get(tenant_id)
        if not tenant:
            return False
        
        limits = tenant.limits
        
        if limit_type == "events_per_day":
            return tenant.events_today < limits.events_per_day
        elif limit_type == "api_calls_per_minute":
            return tenant.api_calls_minute < limits.api_calls_per_minute
        elif limit_type == "campaigns":
            # Would need to check actual campaign count
            return True
        
        return True
    
    async def increment_usage(self, limit_type: str, amount: int = 1):
        """Increment usage counter."""
        tenant_id = get_current_tenant()
        if not tenant_id:
            return
        
        tenant = await self.repo.get(tenant_id)
        if not tenant:
            return
        
        if limit_type == "events_per_day":
            tenant.events_today += amount
        elif limit_type == "api_calls_per_minute":
            tenant.api_calls_minute += amount
        
        await self.repo.update(tenant)


class TenantProvisioner:
    """Provisions resources for new tenants."""
    
    def __init__(self, repository: TenantRepository):
        self.repo = repository
    
    async def provision(
        self,
        tenant_id: str,
        name: str,
        plan: TenantPlan = TenantPlan.FREE
    ) -> Tenant:
        """
        Provision a new tenant.
        
        This will:
        1. Create tenant record
        2. Create BigQuery dataset (if using separate datasets)
        3. Generate API keys
        4. Setup default configurations
        """
        tenant = Tenant(
            id=tenant_id,
            name=name,
            plan=plan
        )
        
        # Create tenant record
        await self.repo.create(tenant)
        
        # Additional provisioning would happen here
        logger.info(f"Provisioned tenant {tenant_id} with plan {plan.value}")
        
        return tenant
    
    async def deprovision(self, tenant_id: str) -> bool:
        """Remove a tenant and clean up resources."""
        tenant = await self.repo.get(tenant_id)
        if not tenant:
            return False
        
        # Would clean up:
        # - BigQuery data
        # - Redis cache
        # - API keys
        # - etc.
        
        await self.repo.delete(tenant_id)
        logger.info(f"Deprovisioned tenant {tenant_id}")
        
        return True


# FastAPI middleware for tenant extraction
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

class TenantMiddleware(BaseHTTPMiddleware):
    """Middleware to extract and set tenant context."""
    
    def __init__(self, app, repository: TenantRepository):
        super().__init__(app)
        self.repo = repository
    
    async def dispatch(self, request: Request, call_next):
        # Extract tenant from JWT or header
        tenant_id = await self._extract_tenant(request)
        
        if tenant_id:
            set_current_tenant(tenant_id)
        
        response = await call_next(request)
        return response
    
    async def _extract_tenant(self, request: Request) -> Optional[str]:
        # Try header first
        tenant_id = request.headers.get("X-Tenant-ID")
        if tenant_id:
            return tenant_id
        
        # Try JWT token
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            # Would decode JWT and extract tenant_id
            pass
        
        return None


class TenantBigQueryClient:
    """BigQuery client with tenant isolation."""
    
    def __init__(self, project_id: str, dataset_prefix: str = "tenant_"):
        self.project_id = project_id
        self.dataset_prefix = dataset_prefix
    
    def get_dataset(self) -> str:
        """Get tenant-specific dataset name."""
        tenant_id = get_current_tenant()
        if not tenant_id:
            raise ValueError("No tenant context")
        return f"{self.dataset_prefix}{tenant_id}"
    
    def get_table(self, table_name: str) -> str:
        """Get fully qualified table name for current tenant."""
        dataset = self.get_dataset()
        return f"`{self.project_id}.{dataset}.{table_name}`"
    
    def add_tenant_filter(self, query: str) -> str:
        """Add tenant filter to a query."""
        tenant_id = get_current_tenant()
        if not tenant_id:
            raise ValueError("No tenant context")
        
        # Simple approach - add WHERE clause
        if "WHERE" in query.upper():
            return query.replace("WHERE", f"WHERE organization_id = '{tenant_id}' AND")
        else:
            return f"{query} WHERE organization_id = '{tenant_id}'"


class TenantCacheClient:
    """Cache client with tenant namespace isolation."""
    
    def __init__(self, redis_client):
        self.redis = redis_client
    
    def _get_key(self, key: str) -> str:
        """Get tenant-namespaced key."""
        tenant_id = get_current_tenant()
        if not tenant_id:
            raise ValueError("No tenant context")
        return f"tenant:{tenant_id}:{key}"
    
    async def get(self, key: str):
        """Get value from tenant namespace."""
        return await self.redis.get(self._get_key(key))
    
    async def set(self, key: str, value, ttl: int = 300):
        """Set value in tenant namespace."""
        return await self.redis.set(self._get_key(key), value, ex=ttl)
    
    async def delete(self, key: str):
        """Delete value from tenant namespace."""
        return await self.redis.delete(self._get_key(key))
