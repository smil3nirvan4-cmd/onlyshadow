"""
S.S.I. SHADOW - Tenant Tests
Tests for multi-tenancy functionality.
"""

import pytest
from unittest.mock import AsyncMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from tenant.tenant import (
    TenantContext,
    Tenant,
    TenantPlan,
    TenantLimits,
    TenantRepository,
    TenantProvisioner,
    get_current_tenant,
    set_current_tenant
)


class TestTenantContext:
    """Tests for tenant context management."""
    
    def test_set_and_get_tenant(self):
        set_current_tenant("tenant_123")
        assert get_current_tenant() == "tenant_123"
    
    def test_context_manager(self):
        with TenantContext("tenant_456"):
            assert get_current_tenant() == "tenant_456"
        
        # After context, should be None or previous value
    
    @pytest.mark.asyncio
    async def test_async_context_manager(self):
        async with TenantContext("tenant_789"):
            assert get_current_tenant() == "tenant_789"


class TestTenantLimits:
    """Tests for tenant plan limits."""
    
    def test_free_plan_limits(self):
        limits = TenantLimits.for_plan(TenantPlan.FREE)
        
        assert limits.events_per_day == 10_000
        assert limits.api_calls_per_minute == 60
        assert limits.campaigns == 5
    
    def test_pro_plan_limits(self):
        limits = TenantLimits.for_plan(TenantPlan.PRO)
        
        assert limits.events_per_day == 1_000_000
        assert limits.api_calls_per_minute == 1000
        assert limits.campaigns == 100
    
    def test_enterprise_plan_limits(self):
        limits = TenantLimits.for_plan(TenantPlan.ENTERPRISE)
        
        assert limits.events_per_day > 100_000_000  # Effectively unlimited


class TestTenantRepository:
    """Tests for TenantRepository."""
    
    @pytest.fixture
    def repo(self):
        return TenantRepository()
    
    @pytest.mark.asyncio
    async def test_create_and_get(self, repo):
        tenant = Tenant(
            id="test_tenant",
            name="Test Org",
            plan=TenantPlan.PRO
        )
        
        await repo.create(tenant)
        retrieved = await repo.get("test_tenant")
        
        assert retrieved is not None
        assert retrieved.name == "Test Org"
        assert retrieved.plan == TenantPlan.PRO
    
    @pytest.mark.asyncio
    async def test_delete(self, repo):
        tenant = Tenant(id="to_delete", name="Delete Me", plan=TenantPlan.FREE)
        await repo.create(tenant)
        
        result = await repo.delete("to_delete")
        assert result is True
        
        retrieved = await repo.get("to_delete")
        assert retrieved is None
    
    @pytest.mark.asyncio
    async def test_list_all(self, repo):
        await repo.create(Tenant(id="t1", name="Tenant 1", plan=TenantPlan.FREE))
        await repo.create(Tenant(id="t2", name="Tenant 2", plan=TenantPlan.PRO))
        
        tenants = await repo.list_all()
        assert len(tenants) == 2


class TestTenantProvisioner:
    """Tests for TenantProvisioner."""
    
    @pytest.fixture
    def provisioner(self):
        repo = TenantRepository()
        return TenantProvisioner(repo)
    
    @pytest.mark.asyncio
    async def test_provision_tenant(self, provisioner):
        tenant = await provisioner.provision(
            tenant_id="new_tenant",
            name="New Organization",
            plan=TenantPlan.STARTER
        )
        
        assert tenant.id == "new_tenant"
        assert tenant.name == "New Organization"
        assert tenant.plan == TenantPlan.STARTER
    
    @pytest.mark.asyncio
    async def test_deprovision_tenant(self, provisioner):
        await provisioner.provision("temp_tenant", "Temp", TenantPlan.FREE)
        
        result = await provisioner.deprovision("temp_tenant")
        assert result is True


class TestTenant:
    """Tests for Tenant model."""
    
    def test_tenant_limits_property(self):
        tenant = Tenant(
            id="test",
            name="Test",
            plan=TenantPlan.PRO
        )
        
        limits = tenant.limits
        assert limits.events_per_day == 1_000_000
