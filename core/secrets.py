"""
S.S.I. SHADOW - Secrets Management
Secure management of API keys, tokens, and sensitive configuration.
"""

import os
import json
import logging
import base64
import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from functools import lru_cache
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

logger = logging.getLogger(__name__)


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class SecretsConfig:
    """Configuration for secrets management."""
    
    # Provider settings
    provider: str = "env"  # env, gcp, aws, vault
    
    # GCP Secret Manager
    gcp_project_id: Optional[str] = None
    
    # AWS Secrets Manager
    aws_region: Optional[str] = None
    
    # HashiCorp Vault
    vault_url: Optional[str] = None
    vault_token: Optional[str] = None
    vault_mount_path: str = "secret"
    
    # Encryption
    encryption_key: Optional[str] = None
    
    # Caching
    cache_enabled: bool = True
    cache_ttl_seconds: int = 300
    
    @classmethod
    def from_env(cls) -> 'SecretsConfig':
        """Create config from environment variables."""
        return cls(
            provider=os.getenv("SECRETS_PROVIDER", "env"),
            gcp_project_id=os.getenv("GCP_PROJECT_ID"),
            aws_region=os.getenv("AWS_REGION", "us-east-1"),
            vault_url=os.getenv("VAULT_URL"),
            vault_token=os.getenv("VAULT_TOKEN"),
            vault_mount_path=os.getenv("VAULT_MOUNT_PATH", "secret"),
            encryption_key=os.getenv("SECRETS_ENCRYPTION_KEY"),
            cache_enabled=os.getenv("SECRETS_CACHE_ENABLED", "true").lower() == "true",
            cache_ttl_seconds=int(os.getenv("SECRETS_CACHE_TTL", "300"))
        )


# =============================================================================
# SECRET VALUE CLASS
# =============================================================================

@dataclass
class SecretValue:
    """Represents a secret value with metadata."""
    
    name: str
    value: str
    version: Optional[str] = None
    created_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_expired(self) -> bool:
        """Check if secret is expired."""
        if self.expires_at is None:
            return False
        return datetime.utcnow() > self.expires_at
    
    def __str__(self) -> str:
        """Mask the value when converting to string."""
        return f"SecretValue(name={self.name}, value=***masked***)"
    
    def __repr__(self) -> str:
        return self.__str__()


# =============================================================================
# ABSTRACT BASE CLASS
# =============================================================================

class SecretsManager(ABC):
    """Abstract base class for secrets managers."""
    
    @abstractmethod
    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[SecretValue]:
        """
        Get a secret by name.
        
        Args:
            name: Secret name
            version: Optional version (for versioned secrets)
        
        Returns:
            SecretValue or None if not found
        """
        pass
    
    @abstractmethod
    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SecretValue:
        """
        Set a secret value.
        
        Args:
            name: Secret name
            value: Secret value
            metadata: Optional metadata
        
        Returns:
            Created SecretValue
        """
        pass
    
    @abstractmethod
    async def delete_secret(self, name: str) -> bool:
        """
        Delete a secret.
        
        Args:
            name: Secret name
        
        Returns:
            True if deleted, False if not found
        """
        pass
    
    @abstractmethod
    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """
        List secret names.
        
        Args:
            prefix: Optional prefix filter
        
        Returns:
            List of secret names
        """
        pass
    
    async def get_secret_value(self, name: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get just the secret value (convenience method).
        
        Args:
            name: Secret name
            default: Default value if not found
        
        Returns:
            Secret value or default
        """
        secret = await self.get_secret(name)
        if secret is None:
            return default
        return secret.value
    
    async def get_json_secret(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Get a secret and parse as JSON.
        
        Args:
            name: Secret name
        
        Returns:
            Parsed JSON or None
        """
        value = await self.get_secret_value(name)
        if value is None:
            return None
        try:
            return json.loads(value)
        except json.JSONDecodeError:
            logger.error(f"Failed to parse secret '{name}' as JSON")
            return None


# =============================================================================
# ENVIRONMENT VARIABLE SECRETS MANAGER
# =============================================================================

class EnvSecretsManager(SecretsManager):
    """
    Secrets manager using environment variables.
    Good for local development.
    """
    
    def __init__(self, prefix: str = ""):
        """
        Initialize environment secrets manager.
        
        Args:
            prefix: Prefix for environment variable names
        """
        self.prefix = prefix
        self._cache: Dict[str, SecretValue] = {}
    
    def _get_env_name(self, name: str) -> str:
        """Get environment variable name for a secret."""
        full_name = f"{self.prefix}{name}" if self.prefix else name
        return full_name.upper().replace("-", "_").replace(".", "_")
    
    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[SecretValue]:
        """Get secret from environment variable."""
        env_name = self._get_env_name(name)
        value = os.getenv(env_name)
        
        if value is None:
            return None
        
        return SecretValue(
            name=name,
            value=value,
            version="env",
            created_at=None
        )
    
    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SecretValue:
        """Set environment variable (in-memory only, not persistent)."""
        env_name = self._get_env_name(name)
        os.environ[env_name] = value
        
        secret = SecretValue(
            name=name,
            value=value,
            version="env",
            created_at=datetime.utcnow(),
            metadata=metadata or {}
        )
        self._cache[name] = secret
        return secret
    
    async def delete_secret(self, name: str) -> bool:
        """Remove environment variable."""
        env_name = self._get_env_name(name)
        if env_name in os.environ:
            del os.environ[env_name]
            self._cache.pop(name, None)
            return True
        return False
    
    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List environment variables that look like secrets."""
        secrets = []
        env_prefix = self._get_env_name(prefix or "")
        
        for key in os.environ:
            if env_prefix and not key.startswith(env_prefix):
                continue
            # Filter to likely secret names
            if any(word in key.upper() for word in ["KEY", "SECRET", "TOKEN", "PASSWORD", "CREDENTIAL"]):
                secrets.append(key)
        
        return secrets


# =============================================================================
# GCP SECRET MANAGER
# =============================================================================

class GCPSecretManager(SecretsManager):
    """
    Secrets manager using Google Cloud Secret Manager.
    
    Requires:
        - google-cloud-secret-manager package
        - GOOGLE_APPLICATION_CREDENTIALS environment variable
    """
    
    def __init__(self, project_id: str):
        """
        Initialize GCP Secret Manager client.
        
        Args:
            project_id: GCP project ID
        """
        self.project_id = project_id
        self._client = None
    
    @property
    def client(self):
        """Lazy-load the Secret Manager client."""
        if self._client is None:
            try:
                from google.cloud import secretmanager
                self._client = secretmanager.SecretManagerServiceClient()
            except ImportError:
                raise ImportError(
                    "google-cloud-secret-manager is required for GCP Secret Manager. "
                    "Install with: pip install google-cloud-secret-manager"
                )
        return self._client
    
    def _get_secret_path(self, name: str, version: str = "latest") -> str:
        """Get the full resource path for a secret."""
        return f"projects/{self.project_id}/secrets/{name}/versions/{version}"
    
    def _get_parent_path(self) -> str:
        """Get the parent path for listing secrets."""
        return f"projects/{self.project_id}"
    
    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[SecretValue]:
        """Get secret from GCP Secret Manager."""
        try:
            from google.api_core import exceptions
            
            version = version or "latest"
            path = self._get_secret_path(name, version)
            
            response = self.client.access_secret_version(request={"name": path})
            
            return SecretValue(
                name=name,
                value=response.payload.data.decode("utf-8"),
                version=response.name.split("/")[-1],
                created_at=response.create_time.replace(tzinfo=None) if response.create_time else None
            )
        
        except exceptions.NotFound:
            logger.debug(f"Secret '{name}' not found in GCP Secret Manager")
            return None
        except Exception as e:
            logger.error(f"Error accessing secret '{name}': {e}")
            raise
    
    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SecretValue:
        """Create or update secret in GCP Secret Manager."""
        from google.api_core import exceptions
        
        parent = self._get_parent_path()
        
        try:
            # Try to create the secret first
            self.client.create_secret(
                request={
                    "parent": parent,
                    "secret_id": name,
                    "secret": {
                        "replication": {"automatic": {}},
                        "labels": metadata or {}
                    }
                }
            )
        except exceptions.AlreadyExists:
            # Secret already exists, that's fine
            pass
        
        # Add new version
        secret_path = f"{parent}/secrets/{name}"
        response = self.client.add_secret_version(
            request={
                "parent": secret_path,
                "payload": {"data": value.encode("utf-8")}
            }
        )
        
        return SecretValue(
            name=name,
            value=value,
            version=response.name.split("/")[-1],
            created_at=datetime.utcnow(),
            metadata=metadata or {}
        )
    
    async def delete_secret(self, name: str) -> bool:
        """Delete secret from GCP Secret Manager."""
        from google.api_core import exceptions
        
        try:
            secret_path = f"{self._get_parent_path()}/secrets/{name}"
            self.client.delete_secret(request={"name": secret_path})
            return True
        except exceptions.NotFound:
            return False
    
    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List secrets in GCP Secret Manager."""
        parent = self._get_parent_path()
        secrets = []
        
        for secret in self.client.list_secrets(request={"parent": parent}):
            name = secret.name.split("/")[-1]
            if prefix is None or name.startswith(prefix):
                secrets.append(name)
        
        return secrets


# =============================================================================
# AWS SECRETS MANAGER
# =============================================================================

class AWSSecretManager(SecretsManager):
    """
    Secrets manager using AWS Secrets Manager.
    
    Requires:
        - boto3 package
        - AWS credentials configured
    """
    
    def __init__(self, region: str = "us-east-1"):
        """
        Initialize AWS Secrets Manager client.
        
        Args:
            region: AWS region
        """
        self.region = region
        self._client = None
    
    @property
    def client(self):
        """Lazy-load the boto3 client."""
        if self._client is None:
            try:
                import boto3
                self._client = boto3.client("secretsmanager", region_name=self.region)
            except ImportError:
                raise ImportError(
                    "boto3 is required for AWS Secrets Manager. "
                    "Install with: pip install boto3"
                )
        return self._client
    
    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[SecretValue]:
        """Get secret from AWS Secrets Manager."""
        try:
            kwargs = {"SecretId": name}
            if version:
                kwargs["VersionId"] = version
            
            response = self.client.get_secret_value(**kwargs)
            
            value = response.get("SecretString")
            if value is None:
                # Binary secret
                value = base64.b64decode(response["SecretBinary"]).decode("utf-8")
            
            return SecretValue(
                name=name,
                value=value,
                version=response.get("VersionId"),
                created_at=response.get("CreatedDate")
            )
        
        except self.client.exceptions.ResourceNotFoundException:
            return None
        except Exception as e:
            logger.error(f"Error accessing secret '{name}': {e}")
            raise
    
    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SecretValue:
        """Create or update secret in AWS Secrets Manager."""
        try:
            # Try to create
            response = self.client.create_secret(
                Name=name,
                SecretString=value,
                Tags=[{"Key": k, "Value": str(v)} for k, v in (metadata or {}).items()]
            )
        except self.client.exceptions.ResourceExistsException:
            # Update existing
            response = self.client.put_secret_value(
                SecretId=name,
                SecretString=value
            )
        
        return SecretValue(
            name=name,
            value=value,
            version=response.get("VersionId"),
            created_at=datetime.utcnow(),
            metadata=metadata or {}
        )
    
    async def delete_secret(self, name: str) -> bool:
        """Delete secret from AWS Secrets Manager."""
        try:
            self.client.delete_secret(
                SecretId=name,
                ForceDeleteWithoutRecovery=True
            )
            return True
        except self.client.exceptions.ResourceNotFoundException:
            return False
    
    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List secrets in AWS Secrets Manager."""
        secrets = []
        paginator = self.client.get_paginator("list_secrets")
        
        filters = []
        if prefix:
            filters.append({"Key": "name", "Values": [prefix]})
        
        for page in paginator.paginate(Filters=filters):
            for secret in page.get("SecretList", []):
                secrets.append(secret["Name"])
        
        return secrets


# =============================================================================
# HASHICORP VAULT SECRETS MANAGER
# =============================================================================

class VaultSecretManager(SecretsManager):
    """
    Secrets manager using HashiCorp Vault.
    
    Requires:
        - hvac package
        - Vault server running and accessible
    """
    
    def __init__(
        self,
        url: str,
        token: str,
        mount_path: str = "secret"
    ):
        """
        Initialize Vault client.
        
        Args:
            url: Vault server URL
            token: Vault token
            mount_path: KV secrets engine mount path
        """
        self.url = url
        self.token = token
        self.mount_path = mount_path
        self._client = None
    
    @property
    def client(self):
        """Lazy-load the hvac client."""
        if self._client is None:
            try:
                import hvac
                self._client = hvac.Client(url=self.url, token=self.token)
            except ImportError:
                raise ImportError(
                    "hvac is required for HashiCorp Vault. "
                    "Install with: pip install hvac"
                )
        return self._client
    
    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[SecretValue]:
        """Get secret from Vault."""
        try:
            if version:
                response = self.client.secrets.kv.v2.read_secret_version(
                    path=name,
                    mount_point=self.mount_path,
                    version=int(version)
                )
            else:
                response = self.client.secrets.kv.v2.read_secret_version(
                    path=name,
                    mount_point=self.mount_path
                )
            
            data = response["data"]["data"]
            metadata = response["data"]["metadata"]
            
            # If single value, return it directly; otherwise JSON encode
            if len(data) == 1 and "value" in data:
                value = data["value"]
            else:
                value = json.dumps(data)
            
            return SecretValue(
                name=name,
                value=value,
                version=str(metadata.get("version")),
                created_at=datetime.fromisoformat(
                    metadata["created_time"].replace("Z", "+00:00")
                ).replace(tzinfo=None) if metadata.get("created_time") else None,
                metadata=metadata
            )
        
        except Exception as e:
            if "404" in str(e) or "not found" in str(e).lower():
                return None
            logger.error(f"Error accessing secret '{name}': {e}")
            raise
    
    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SecretValue:
        """Create or update secret in Vault."""
        # Try to parse as JSON, otherwise store as {"value": value}
        try:
            data = json.loads(value)
            if not isinstance(data, dict):
                data = {"value": value}
        except json.JSONDecodeError:
            data = {"value": value}
        
        self.client.secrets.kv.v2.create_or_update_secret(
            path=name,
            secret=data,
            mount_point=self.mount_path
        )
        
        # Read back to get version
        return await self.get_secret(name)
    
    async def delete_secret(self, name: str) -> bool:
        """Delete secret from Vault."""
        try:
            self.client.secrets.kv.v2.delete_metadata_and_all_versions(
                path=name,
                mount_point=self.mount_path
            )
            return True
        except Exception:
            return False
    
    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List secrets in Vault."""
        path = prefix or ""
        try:
            response = self.client.secrets.kv.v2.list_secrets(
                path=path,
                mount_point=self.mount_path
            )
            return response["data"]["keys"]
        except Exception:
            return []


# =============================================================================
# CACHING WRAPPER
# =============================================================================

class CachedSecretsManager(SecretsManager):
    """
    Wrapper that adds caching to any secrets manager.
    """
    
    def __init__(
        self,
        manager: SecretsManager,
        ttl_seconds: int = 300
    ):
        """
        Initialize cached secrets manager.
        
        Args:
            manager: Underlying secrets manager
            ttl_seconds: Cache TTL in seconds
        """
        self._manager = manager
        self._ttl = timedelta(seconds=ttl_seconds)
        self._cache: Dict[str, tuple[SecretValue, datetime]] = {}
    
    def _is_cached_valid(self, name: str) -> bool:
        """Check if cached value is still valid."""
        if name not in self._cache:
            return False
        _, cached_at = self._cache[name]
        return datetime.utcnow() - cached_at < self._ttl
    
    async def get_secret(self, name: str, version: Optional[str] = None) -> Optional[SecretValue]:
        """Get secret with caching."""
        cache_key = f"{name}:{version}" if version else name
        
        if self._is_cached_valid(cache_key):
            return self._cache[cache_key][0]
        
        secret = await self._manager.get_secret(name, version)
        if secret:
            self._cache[cache_key] = (secret, datetime.utcnow())
        
        return secret
    
    async def set_secret(
        self,
        name: str,
        value: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> SecretValue:
        """Set secret and update cache."""
        secret = await self._manager.set_secret(name, value, metadata)
        self._cache[name] = (secret, datetime.utcnow())
        return secret
    
    async def delete_secret(self, name: str) -> bool:
        """Delete secret and remove from cache."""
        result = await self._manager.delete_secret(name)
        self._cache.pop(name, None)
        return result
    
    async def list_secrets(self, prefix: Optional[str] = None) -> List[str]:
        """List secrets (not cached)."""
        return await self._manager.list_secrets(prefix)
    
    def clear_cache(self):
        """Clear the cache."""
        self._cache.clear()


# =============================================================================
# ENCRYPTION UTILITIES
# =============================================================================

class FieldEncryption:
    """
    Encrypt/decrypt sensitive fields for database storage.
    Uses Fernet symmetric encryption.
    """
    
    def __init__(self, key: Optional[str] = None):
        """
        Initialize field encryption.
        
        Args:
            key: Encryption key (base64 encoded) or None to generate
        """
        if key:
            self._key = key.encode() if isinstance(key, str) else key
        else:
            self._key = Fernet.generate_key()
        
        self._fernet = Fernet(self._key)
    
    @classmethod
    def from_password(cls, password: str, salt: Optional[bytes] = None) -> 'FieldEncryption':
        """
        Create encryption from a password using PBKDF2.
        
        Args:
            password: Password to derive key from
            salt: Salt for key derivation (generates random if not provided)
        
        Returns:
            FieldEncryption instance
        """
        if salt is None:
            salt = os.urandom(16)
        
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000
        )
        
        key = base64.urlsafe_b64encode(kdf.derive(password.encode()))
        return cls(key.decode())
    
    def encrypt(self, value: str) -> str:
        """
        Encrypt a string value.
        
        Args:
            value: Plain text value
        
        Returns:
            Encrypted value (base64 encoded)
        """
        return self._fernet.encrypt(value.encode()).decode()
    
    def decrypt(self, encrypted: str) -> str:
        """
        Decrypt an encrypted value.
        
        Args:
            encrypted: Encrypted value (base64 encoded)
        
        Returns:
            Decrypted plain text
        """
        return self._fernet.decrypt(encrypted.encode()).decode()
    
    def encrypt_dict(
        self,
        data: Dict[str, Any],
        fields: List[str]
    ) -> Dict[str, Any]:
        """
        Encrypt specific fields in a dictionary.
        
        Args:
            data: Dictionary with data
            fields: List of field names to encrypt
        
        Returns:
            Dictionary with encrypted fields
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                result[field] = self.encrypt(str(result[field]))
        return result
    
    def decrypt_dict(
        self,
        data: Dict[str, Any],
        fields: List[str]
    ) -> Dict[str, Any]:
        """
        Decrypt specific fields in a dictionary.
        
        Args:
            data: Dictionary with encrypted data
            fields: List of field names to decrypt
        
        Returns:
            Dictionary with decrypted fields
        """
        result = data.copy()
        for field in fields:
            if field in result and result[field]:
                result[field] = self.decrypt(result[field])
        return result


# =============================================================================
# FACTORY FUNCTION
# =============================================================================

def create_secrets_manager(config: Optional[SecretsConfig] = None) -> SecretsManager:
    """
    Create a secrets manager based on configuration.
    
    Args:
        config: Secrets configuration (uses env vars if not provided)
    
    Returns:
        Configured SecretsManager instance
    """
    if config is None:
        config = SecretsConfig.from_env()
    
    if config.provider == "gcp":
        if not config.gcp_project_id:
            raise ValueError("GCP project ID is required for GCP secrets manager")
        manager = GCPSecretManager(config.gcp_project_id)
    
    elif config.provider == "aws":
        manager = AWSSecretManager(config.aws_region or "us-east-1")
    
    elif config.provider == "vault":
        if not config.vault_url or not config.vault_token:
            raise ValueError("Vault URL and token are required for Vault secrets manager")
        manager = VaultSecretManager(
            url=config.vault_url,
            token=config.vault_token,
            mount_path=config.vault_mount_path
        )
    
    else:  # Default to env
        manager = EnvSecretsManager()
    
    # Wrap with caching if enabled
    if config.cache_enabled:
        manager = CachedSecretsManager(manager, config.cache_ttl_seconds)
    
    return manager


# =============================================================================
# GLOBAL INSTANCE
# =============================================================================

_secrets_manager: Optional[SecretsManager] = None


def get_secrets_manager() -> SecretsManager:
    """Get the global secrets manager instance."""
    global _secrets_manager
    if _secrets_manager is None:
        _secrets_manager = create_secrets_manager()
    return _secrets_manager


async def get_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Convenience function to get a secret value."""
    return await get_secrets_manager().get_secret_value(name, default)


# =============================================================================
# CREDENTIAL ROTATION
# =============================================================================

@dataclass
class RotationResult:
    """Result of a credential rotation."""
    
    secret_name: str
    old_version: Optional[str]
    new_version: str
    rotated_at: datetime
    success: bool
    error: Optional[str] = None


class CredentialRotator:
    """
    Automatic credential rotation manager.
    """
    
    def __init__(self, secrets_manager: SecretsManager):
        """
        Initialize credential rotator.
        
        Args:
            secrets_manager: Secrets manager to use
        """
        self._manager = secrets_manager
        self._rotation_handlers: Dict[str, callable] = {}
    
    def register_handler(
        self,
        secret_pattern: str,
        handler: callable
    ):
        """
        Register a rotation handler for secrets matching a pattern.
        
        Args:
            secret_pattern: Pattern to match secret names
            handler: Async function(old_value) -> new_value
        """
        self._rotation_handlers[secret_pattern] = handler
    
    async def rotate(
        self,
        secret_name: str,
        generator: Optional[callable] = None
    ) -> RotationResult:
        """
        Rotate a credential.
        
        Args:
            secret_name: Name of the secret to rotate
            generator: Optional function to generate new value
        
        Returns:
            RotationResult
        """
        try:
            # Get current secret
            current = await self._manager.get_secret(secret_name)
            old_version = current.version if current else None
            
            # Generate new value
            if generator:
                new_value = await generator(current.value if current else None)
            else:
                # Find matching handler
                handler = None
                for pattern, h in self._rotation_handlers.items():
                    if pattern in secret_name:
                        handler = h
                        break
                
                if handler:
                    new_value = await handler(current.value if current else None)
                else:
                    # Default: generate random token
                    new_value = base64.urlsafe_b64encode(os.urandom(32)).decode()
            
            # Update secret
            new_secret = await self._manager.set_secret(
                secret_name,
                new_value,
                metadata={"rotated_at": datetime.utcnow().isoformat()}
            )
            
            logger.info(f"Rotated credential: {secret_name}")
            
            return RotationResult(
                secret_name=secret_name,
                old_version=old_version,
                new_version=new_secret.version,
                rotated_at=datetime.utcnow(),
                success=True
            )
        
        except Exception as e:
            logger.error(f"Failed to rotate credential {secret_name}: {e}")
            return RotationResult(
                secret_name=secret_name,
                old_version=None,
                new_version="",
                rotated_at=datetime.utcnow(),
                success=False,
                error=str(e)
            )
