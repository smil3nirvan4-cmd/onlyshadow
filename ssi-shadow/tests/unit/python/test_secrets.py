"""
S.S.I. SHADOW - Secrets Tests
Tests for secrets management.
"""

import pytest
import os
from unittest.mock import AsyncMock, MagicMock, patch

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

from core.secrets import (
    EnvSecretsManager,
    SecretValue,
    SecretsConfig,
    FieldEncryption,
    CachedSecretsManager,
    create_secrets_manager
)


class TestEnvSecretsManager:
    """Tests for environment variable secrets manager."""
    
    @pytest.fixture
    def manager(self):
        return EnvSecretsManager(prefix="TEST_")
    
    @pytest.mark.asyncio
    async def test_get_secret(self, manager, monkeypatch):
        monkeypatch.setenv("TEST_API_KEY", "secret123")
        
        secret = await manager.get_secret("api_key")
        
        assert secret is not None
        assert secret.value == "secret123"
        assert secret.name == "api_key"
    
    @pytest.mark.asyncio
    async def test_get_nonexistent_secret(self, manager):
        secret = await manager.get_secret("nonexistent")
        assert secret is None
    
    @pytest.mark.asyncio
    async def test_set_secret(self, manager):
        secret = await manager.set_secret("new_key", "new_value")
        
        assert secret.value == "new_value"
        assert os.environ.get("TEST_NEW_KEY") == "new_value"
    
    @pytest.mark.asyncio
    async def test_delete_secret(self, manager, monkeypatch):
        monkeypatch.setenv("TEST_TO_DELETE", "value")
        
        result = await manager.delete_secret("to_delete")
        assert result is True
        assert "TEST_TO_DELETE" not in os.environ


class TestSecretValue:
    """Tests for SecretValue model."""
    
    def test_basic_secret(self):
        secret = SecretValue(
            name="test",
            value="secret123"
        )
        
        assert secret.name == "test"
        assert secret.value == "secret123"
        assert secret.is_expired is False
    
    def test_masked_str(self):
        secret = SecretValue(name="password", value="super_secret")
        
        str_repr = str(secret)
        assert "super_secret" not in str_repr
        assert "masked" in str_repr


class TestFieldEncryption:
    """Tests for field-level encryption."""
    
    @pytest.fixture
    def encryption(self):
        return FieldEncryption()
    
    def test_encrypt_decrypt(self, encryption):
        original = "sensitive data"
        
        encrypted = encryption.encrypt(original)
        decrypted = encryption.decrypt(encrypted)
        
        assert encrypted != original
        assert decrypted == original
    
    def test_encrypt_dict(self, encryption):
        data = {
            "username": "john",
            "password": "secret123",
            "email": "john@example.com"
        }
        
        encrypted = encryption.encrypt_dict(data, ["password"])
        
        assert encrypted["username"] == "john"  # Not encrypted
        assert encrypted["password"] != "secret123"  # Encrypted
        assert encrypted["email"] == "john@example.com"  # Not encrypted
    
    def test_decrypt_dict(self, encryption):
        data = {"password": "secret123"}
        encrypted = encryption.encrypt_dict(data, ["password"])
        decrypted = encryption.decrypt_dict(encrypted, ["password"])
        
        assert decrypted["password"] == "secret123"


class TestCachedSecretsManager:
    """Tests for cached secrets manager."""
    
    @pytest.mark.asyncio
    async def test_caching(self):
        inner = AsyncMock()
        inner.get_secret = AsyncMock(return_value=SecretValue(
            name="cached_key",
            value="cached_value"
        ))
        
        cached = CachedSecretsManager(inner, ttl_seconds=60)
        
        # First call
        secret1 = await cached.get_secret("cached_key")
        # Second call (should use cache)
        secret2 = await cached.get_secret("cached_key")
        
        assert secret1.value == secret2.value
        # Inner manager should only be called once
        assert inner.get_secret.call_count == 1
    
    def test_clear_cache(self):
        inner = AsyncMock()
        cached = CachedSecretsManager(inner, ttl_seconds=60)
        cached._cache["test"] = (SecretValue("test", "value"), None)
        
        cached.clear_cache()
        
        assert len(cached._cache) == 0


class TestSecretsConfig:
    """Tests for SecretsConfig."""
    
    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("SECRETS_PROVIDER", "gcp")
        monkeypatch.setenv("GCP_PROJECT_ID", "my-project")
        
        config = SecretsConfig.from_env()
        
        assert config.provider == "gcp"
        assert config.gcp_project_id == "my-project"
