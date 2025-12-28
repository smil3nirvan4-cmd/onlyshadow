"""
S.S.I. SHADOW - SSO Service
===========================
Service for Single Sign-On (SAML and OAuth) authentication.
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, List, Any
from urllib.parse import urlencode
import secrets
import hashlib
import base64

import httpx
from cryptography.fernet import Fernet

from auth.models.entities import (
    User,
    UserRole,
    SSOConfig,
    SSOConfigCreate,
    AuditLog,
    AuditAction,
)
from auth.services.user_service import get_user_service

logger = logging.getLogger(__name__)


class SSOService:
    """
    Service for SSO authentication.
    
    Supports:
    - Google OAuth
    - Microsoft Azure AD OAuth
    - SAML 2.0 (generic)
    - Okta
    """
    
    def __init__(self, encryption_key: str = None):
        # Encryption for secrets
        key = encryption_key or os.getenv("ENCRYPTION_KEY")
        if key:
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        else:
            self.fernet = Fernet(Fernet.generate_key())
        
        # HTTP client
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
        # In-memory store (replace with database in production)
        self.sso_configs: Dict[str, SSOConfig] = {}
        self.sso_configs_by_org: Dict[str, str] = {}  # org_id -> config_id
        
        # OAuth state store (should be Redis in production)
        self.oauth_states: Dict[str, Dict] = {}  # state -> {org_id, redirect_uri, ...}
        
        # OAuth providers configuration
        self.oauth_providers = {
            "google": {
                "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
                "token_endpoint": "https://oauth2.googleapis.com/token",
                "userinfo_endpoint": "https://www.googleapis.com/oauth2/v3/userinfo",
                "scopes": ["openid", "email", "profile"],
            },
            "microsoft": {
                "authorization_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
                "token_endpoint": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
                "userinfo_endpoint": "https://graph.microsoft.com/v1.0/me",
                "scopes": ["openid", "email", "profile", "User.Read"],
            },
            "okta": {
                # Okta requires domain-specific URLs
                "authorization_endpoint_template": "https://{domain}/oauth2/v1/authorize",
                "token_endpoint_template": "https://{domain}/oauth2/v1/token",
                "userinfo_endpoint_template": "https://{domain}/oauth2/v1/userinfo",
                "scopes": ["openid", "email", "profile"],
            },
        }
        
        # Base URL for callbacks
        self.base_url = os.getenv("BASE_URL", "http://localhost:8000")
    
    def _encrypt(self, data: str) -> str:
        """Encrypt sensitive data."""
        return self.fernet.encrypt(data.encode()).decode()
    
    def _decrypt(self, data: str) -> str:
        """Decrypt sensitive data."""
        return self.fernet.decrypt(data.encode()).decode()
    
    # =========================================================================
    # SSO CONFIG MANAGEMENT
    # =========================================================================
    
    async def create_sso_config(
        self,
        org_id: str,
        data: SSOConfigCreate,
        created_by: str
    ) -> SSOConfig:
        """Create SSO configuration for an organization."""
        # Check if config already exists
        if org_id in self.sso_configs_by_org:
            existing_id = self.sso_configs_by_org[org_id]
            existing = self.sso_configs.get(existing_id)
            if existing and existing.is_active:
                raise ValueError("SSO configuration already exists for this organization")
        
        # Encrypt client secret
        client_secret_encrypted = None
        if data.client_secret:
            client_secret_encrypted = self._encrypt(data.client_secret)
        
        config = SSOConfig(
            organization_id=org_id,
            provider=data.provider,
            entity_id=data.entity_id,
            sso_url=data.sso_url,
            certificate=data.certificate,
            client_id=data.client_id,
            client_secret_encrypted=client_secret_encrypted,
            enforce_sso=data.enforce_sso,
            auto_provision=data.auto_provision,
            default_role=data.default_role,
            allowed_domains=data.allowed_domains,
        )
        
        self.sso_configs[config.id] = config
        self.sso_configs_by_org[org_id] = config.id
        
        logger.info(f"SSO config created: {config.id} for org {org_id}")
        return config
    
    async def get_sso_config(self, org_id: str) -> Optional[SSOConfig]:
        """Get SSO configuration for an organization."""
        config_id = self.sso_configs_by_org.get(org_id)
        if config_id:
            config = self.sso_configs.get(config_id)
            if config and config.is_active:
                return config
        return None
    
    async def update_sso_config(
        self,
        org_id: str,
        data: SSOConfigCreate,
        updated_by: str
    ) -> Optional[SSOConfig]:
        """Update SSO configuration."""
        config = await self.get_sso_config(org_id)
        if not config:
            return None
        
        config.provider = data.provider
        config.entity_id = data.entity_id
        config.sso_url = data.sso_url
        config.certificate = data.certificate
        config.client_id = data.client_id
        
        if data.client_secret:
            config.client_secret_encrypted = self._encrypt(data.client_secret)
        
        config.enforce_sso = data.enforce_sso
        config.auto_provision = data.auto_provision
        config.default_role = data.default_role
        config.allowed_domains = data.allowed_domains
        config.updated_at = datetime.utcnow()
        
        return config
    
    async def delete_sso_config(self, org_id: str, deleted_by: str) -> bool:
        """Delete SSO configuration."""
        config = await self.get_sso_config(org_id)
        if not config:
            return False
        
        config.is_active = False
        del self.sso_configs_by_org[org_id]
        
        return True
    
    # =========================================================================
    # OAUTH FLOW
    # =========================================================================
    
    async def get_oauth_authorization_url(
        self,
        org_id: str,
        redirect_uri: str = None
    ) -> str:
        """Generate OAuth authorization URL."""
        config = await self.get_sso_config(org_id)
        if not config:
            raise ValueError("SSO not configured for this organization")
        
        provider = self.oauth_providers.get(config.provider)
        if not provider:
            raise ValueError(f"Unsupported OAuth provider: {config.provider}")
        
        # Generate state
        state = secrets.token_urlsafe(32)
        
        # Store state
        self.oauth_states[state] = {
            "org_id": org_id,
            "redirect_uri": redirect_uri or f"{self.base_url}/api/auth/sso/callback",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        # Build authorization URL
        auth_endpoint = provider.get("authorization_endpoint")
        if not auth_endpoint and "authorization_endpoint_template" in provider:
            # For Okta, extract domain from entity_id
            domain = config.entity_id or "example.okta.com"
            auth_endpoint = provider["authorization_endpoint_template"].format(domain=domain)
        
        params = {
            "client_id": config.client_id,
            "response_type": "code",
            "redirect_uri": self.oauth_states[state]["redirect_uri"],
            "scope": " ".join(provider["scopes"]),
            "state": state,
        }
        
        # Add provider-specific params
        if config.provider == "google":
            params["access_type"] = "offline"
            params["prompt"] = "consent"
        elif config.provider == "microsoft":
            params["response_mode"] = "query"
        
        return f"{auth_endpoint}?{urlencode(params)}"
    
    async def handle_oauth_callback(
        self,
        code: str,
        state: str
    ) -> Dict[str, Any]:
        """Handle OAuth callback and authenticate user."""
        # Validate state
        state_data = self.oauth_states.pop(state, None)
        if not state_data:
            raise ValueError("Invalid or expired OAuth state")
        
        org_id = state_data["org_id"]
        redirect_uri = state_data["redirect_uri"]
        
        config = await self.get_sso_config(org_id)
        if not config:
            raise ValueError("SSO not configured")
        
        # Exchange code for tokens
        tokens = await self._exchange_oauth_code(config, code, redirect_uri)
        
        # Get user info
        user_info = await self._get_oauth_user_info(config, tokens["access_token"])
        
        # Validate domain if restricted
        email = user_info.get("email", "").lower()
        if config.allowed_domains:
            domain = email.split("@")[-1]
            if domain not in config.allowed_domains:
                raise ValueError(f"Email domain '{domain}' not allowed")
        
        # Find or create user
        user_service = get_user_service()
        user = await user_service.get_user_by_email(email)
        
        if not user:
            if config.auto_provision:
                # Create new user
                from auth.models.entities import UserCreate
                user = await user_service.create_user(
                    org_id,
                    UserCreate(
                        email=email,
                        name=user_info.get("name", email.split("@")[0]),
                        role=config.default_role
                    ),
                    created_by="sso"
                )
                user.auth_provider = config.provider
                user.auth_provider_id = user_info.get("sub") or user_info.get("id")
                user.is_verified = True
            else:
                raise ValueError("User not found and auto-provisioning disabled")
        elif user.organization_id != org_id:
            raise ValueError("User belongs to a different organization")
        
        # Generate tokens
        access_token, _ = user_service.create_access_token(user)
        refresh_token, _ = user_service.create_refresh_token(user)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "user": {
                "id": user.id,
                "email": user.email,
                "name": user.name,
                "role": user.role,
                "organization_id": user.organization_id,
            }
        }
    
    async def _exchange_oauth_code(
        self,
        config: SSOConfig,
        code: str,
        redirect_uri: str
    ) -> Dict:
        """Exchange authorization code for tokens."""
        provider = self.oauth_providers.get(config.provider)
        
        token_endpoint = provider.get("token_endpoint")
        if not token_endpoint and "token_endpoint_template" in provider:
            domain = config.entity_id or "example.okta.com"
            token_endpoint = provider["token_endpoint_template"].format(domain=domain)
        
        # Decrypt client secret
        client_secret = self._decrypt(config.client_secret_encrypted)
        
        response = await self.http_client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": config.client_id,
                "client_secret": client_secret,
            }
        )
        
        if response.status_code != 200:
            logger.error(f"OAuth token exchange failed: {response.text}")
            raise ValueError("Failed to exchange authorization code")
        
        return response.json()
    
    async def _get_oauth_user_info(
        self,
        config: SSOConfig,
        access_token: str
    ) -> Dict:
        """Get user info from OAuth provider."""
        provider = self.oauth_providers.get(config.provider)
        
        userinfo_endpoint = provider.get("userinfo_endpoint")
        if not userinfo_endpoint and "userinfo_endpoint_template" in provider:
            domain = config.entity_id or "example.okta.com"
            userinfo_endpoint = provider["userinfo_endpoint_template"].format(domain=domain)
        
        response = await self.http_client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"}
        )
        
        if response.status_code != 200:
            logger.error(f"OAuth userinfo failed: {response.text}")
            raise ValueError("Failed to get user info")
        
        return response.json()
    
    # =========================================================================
    # SAML FLOW (Simplified)
    # =========================================================================
    
    async def get_saml_login_url(self, org_id: str) -> str:
        """Generate SAML login URL."""
        config = await self.get_sso_config(org_id)
        if not config or config.provider != "saml":
            raise ValueError("SAML not configured for this organization")
        
        if not config.sso_url:
            raise ValueError("SAML SSO URL not configured")
        
        # Generate SAML AuthnRequest
        # In production, use a proper SAML library like python3-saml
        relay_state = secrets.token_urlsafe(32)
        
        # Store relay state
        self.oauth_states[relay_state] = {
            "org_id": org_id,
            "type": "saml",
            "created_at": datetime.utcnow().isoformat(),
        }
        
        # Build redirect URL
        # This is simplified - real implementation needs proper SAML AuthnRequest
        params = {
            "SAMLRequest": "",  # Would be base64-encoded AuthnRequest XML
            "RelayState": relay_state,
        }
        
        return f"{config.sso_url}?{urlencode(params)}"
    
    async def handle_saml_response(
        self,
        saml_response: str,
        relay_state: str
    ) -> Dict[str, Any]:
        """Handle SAML response (ACS endpoint)."""
        # Validate relay state
        state_data = self.oauth_states.pop(relay_state, None)
        if not state_data or state_data.get("type") != "saml":
            raise ValueError("Invalid SAML relay state")
        
        org_id = state_data["org_id"]
        
        config = await self.get_sso_config(org_id)
        if not config:
            raise ValueError("SAML not configured")
        
        # Parse and validate SAML response
        # In production, use python3-saml for proper validation
        # This is a simplified placeholder
        
        # For now, return an error
        raise NotImplementedError("SAML response handling requires python3-saml library")
    
    # =========================================================================
    # CLEANUP
    # =========================================================================
    
    async def close(self):
        """Close HTTP client."""
        await self.http_client.aclose()


# =============================================================================
# SINGLETON
# =============================================================================

_sso_service: Optional[SSOService] = None


def get_sso_service() -> SSOService:
    """Get or create the SSO service."""
    global _sso_service
    if _sso_service is None:
        _sso_service = SSOService()
    return _sso_service


async def init_sso_service(encryption_key: str = None) -> SSOService:
    """Initialize the SSO service."""
    global _sso_service
    _sso_service = SSOService(encryption_key=encryption_key)
    return _sso_service
