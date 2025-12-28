"""
S.S.I. SHADOW - SSO Service (Complete SAML 2.0 Implementation)
==============================================================
Service for Single Sign-On authentication with SAML 2.0 and OAuth support.

Prerequisites:
    pip install python3-saml httpx cryptography

Environment Variables:
    ENCRYPTION_KEY - Fernet key for encrypting secrets
    BASE_URL - Base URL for callbacks (e.g., https://app.ssi-shadow.io)
    SAML_STRICT - Enable strict SAML validation (default: true)
    SAML_DEBUG - Enable SAML debug mode (default: false)

Author: SSI Shadow Team
Version: 2.0.0 (Full SAML Implementation)
"""

import os
import logging
import json
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Optional, Dict, List, Any, Tuple
from urllib.parse import urlencode, urlparse
import secrets
import hashlib
import base64
from dataclasses import dataclass, field

import httpx
from cryptography.fernet import Fernet

# Try to import python3-saml
try:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    from onelogin.saml2.settings import OneLogin_Saml2_Settings
    from onelogin.saml2.utils import OneLogin_Saml2_Utils
    from onelogin.saml2.errors import OneLogin_Saml2_Error
    SAML_AVAILABLE = True
except ImportError:
    SAML_AVAILABLE = False
    OneLogin_Saml2_Auth = None
    OneLogin_Saml2_Settings = None

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


# =============================================================================
# SAML ERROR CLASSES
# =============================================================================

class SAMLError(Exception):
    """Base SAML Error"""
    def __init__(self, message: str, errors: List[str] = None):
        self.message = message
        self.errors = errors or []
        super().__init__(message)


class SAMLConfigError(SAMLError):
    """SAML Configuration Error"""
    pass


class SAMLResponseError(SAMLError):
    """SAML Response Validation Error"""
    pass


class SAMLAuthError(SAMLError):
    """SAML Authentication Error"""
    pass


# =============================================================================
# SAML ATTRIBUTE MAPPING
# =============================================================================

@dataclass
class SAMLAttributeMapping:
    """
    Mapping of SAML attributes to user fields.
    Different IdPs use different attribute names.
    """
    email: List[str] = field(default_factory=lambda: [
        "email",
        "Email",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
        "urn:oid:0.9.2342.19200300.100.1.3",  # mail
        "http://schemas.xmlsoap.org/claims/EmailAddress",
        "User.Email",
        "emailAddress",
    ])
    
    first_name: List[str] = field(default_factory=lambda: [
        "firstName",
        "FirstName",
        "first_name",
        "givenName",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname",
        "urn:oid:2.5.4.42",  # givenName
        "User.FirstName",
    ])
    
    last_name: List[str] = field(default_factory=lambda: [
        "lastName",
        "LastName",
        "last_name",
        "surname",
        "sn",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname",
        "urn:oid:2.5.4.4",  # sn
        "User.LastName",
    ])
    
    display_name: List[str] = field(default_factory=lambda: [
        "displayName",
        "name",
        "Name",
        "cn",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/name",
        "urn:oid:2.5.4.3",  # cn
        "User.DisplayName",
    ])
    
    groups: List[str] = field(default_factory=lambda: [
        "groups",
        "Groups",
        "memberOf",
        "member_of",
        "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups",
        "http://schemas.xmlsoap.org/claims/Group",
        "Role",
        "role",
    ])
    
    department: List[str] = field(default_factory=lambda: [
        "department",
        "Department",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/department",
        "User.Department",
    ])
    
    employee_id: List[str] = field(default_factory=lambda: [
        "employeeId",
        "employee_id",
        "employeeNumber",
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/employeeid",
    ])


# =============================================================================
# SSO SERVICE
# =============================================================================

class SSOService:
    """
    Service for SSO authentication.
    
    Supports:
    - SAML 2.0 (Okta, Azure AD, OneLogin, Google Workspace, ADFS)
    - Google OAuth
    - Microsoft Azure AD OAuth
    - Okta OAuth
    """
    
    def __init__(self, encryption_key: str = None):
        # Encryption for secrets
        key = encryption_key or os.getenv("ENCRYPTION_KEY")
        if key:
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        else:
            self.fernet = Fernet(Fernet.generate_key())
            logger.warning("Using generated encryption key - secrets will be lost on restart")
        
        # HTTP client
        self.http_client = httpx.AsyncClient(timeout=30.0)
        
        # In-memory store (replace with database in production)
        self.sso_configs: Dict[str, SSOConfig] = {}
        self.sso_configs_by_org: Dict[str, str] = {}  # org_id -> config_id
        
        # State store (should be Redis in production)
        self.oauth_states: Dict[str, Dict] = {}  # state -> {org_id, redirect_uri, ...}
        self.saml_requests: Dict[str, Dict] = {}  # request_id -> {org_id, ...}
        
        # SAML attribute mapping
        self.attribute_mapping = SAMLAttributeMapping()
        
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
        
        # SAML settings
        self.saml_strict = os.getenv("SAML_STRICT", "true").lower() == "true"
        self.saml_debug = os.getenv("SAML_DEBUG", "false").lower() == "true"
        
        if not SAML_AVAILABLE:
            logger.warning("python3-saml not installed. SAML SSO will not work.")
        else:
            logger.info("✅ SAML 2.0 support enabled")
    
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
        
        logger.info(f"SSO config created: {config.id} for org {org_id} (provider: {data.provider})")
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
        
        logger.info(f"SSO config updated for org {org_id}")
        return config
    
    async def delete_sso_config(self, org_id: str, deleted_by: str) -> bool:
        """Delete SSO configuration."""
        config = await self.get_sso_config(org_id)
        if not config:
            return False
        
        config.is_active = False
        del self.sso_configs_by_org[org_id]
        
        logger.info(f"SSO config deleted for org {org_id} by {deleted_by}")
        return True
    
    # =========================================================================
    # SAML 2.0 SETTINGS
    # =========================================================================
    
    def _build_saml_settings(self, config: SSOConfig, request_data: Dict = None) -> Dict:
        """
        Build python3-saml settings from SSOConfig.
        
        Args:
            config: SSO configuration
            request_data: Optional request data for SP URL building
            
        Returns:
            Settings dictionary for OneLogin_Saml2_Auth
        """
        # Determine SP URLs
        base_url = request_data.get("https", "on") == "on" and "https://" or "http://"
        host = request_data.get("http_host", urlparse(self.base_url).netloc) if request_data else urlparse(self.base_url).netloc
        sp_base_url = f"{base_url}{host}"
        
        # SP Entity ID (unique identifier for our service)
        sp_entity_id = f"{self.base_url}/api/auth/saml/metadata/{config.organization_id}"
        
        # SP ACS (Assertion Consumer Service) URL
        sp_acs_url = f"{self.base_url}/api/auth/saml/acs/{config.organization_id}"
        
        # SP SLS (Single Logout Service) URL
        sp_sls_url = f"{self.base_url}/api/auth/saml/sls/{config.organization_id}"
        
        settings = {
            # Strict mode
            "strict": self.saml_strict,
            "debug": self.saml_debug,
            
            # Service Provider (SP) settings - our application
            "sp": {
                "entityId": sp_entity_id,
                "assertionConsumerService": {
                    "url": sp_acs_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST",
                },
                "singleLogoutService": {
                    "url": sp_sls_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "NameIDFormat": "urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress",
                "x509cert": "",  # SP certificate (optional)
                "privateKey": "",  # SP private key (optional)
            },
            
            # Identity Provider (IdP) settings - customer's IdP
            "idp": {
                "entityId": config.entity_id,
                "singleSignOnService": {
                    "url": config.sso_url,
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "singleLogoutService": {
                    "url": config.slo_url if hasattr(config, 'slo_url') and config.slo_url else "",
                    "binding": "urn:oasis:names:tc:SAML:2.0:bindings:HTTP-Redirect",
                },
                "x509cert": config.certificate,
            },
            
            # Security settings
            "security": {
                # Signatures
                "authnRequestsSigned": False,
                "logoutRequestSigned": False,
                "logoutResponseSigned": False,
                "signMetadata": False,
                
                # Encryption
                "wantAssertionsSigned": True,
                "wantAssertionsEncrypted": False,
                "wantNameIdEncrypted": False,
                
                # Validation
                "wantMessagesSigned": False,
                "wantNameId": True,
                
                # Algorithm
                "signatureAlgorithm": "http://www.w3.org/2001/04/xmldsig-more#rsa-sha256",
                "digestAlgorithm": "http://www.w3.org/2001/04/xmlenc#sha256",
                
                # Relaxed validation for development
                "relaxDestinationValidation": not self.saml_strict,
                "rejectUnsolicitedResponsesWithInResponseTo": False,
            },
            
            # Contact information (optional)
            "contactPerson": {
                "technical": {
                    "givenName": "SSI Shadow",
                    "emailAddress": "support@ssi-shadow.io"
                },
            },
            
            # Organization information (optional)
            "organization": {
                "en-US": {
                    "name": "SSI Shadow",
                    "displayname": "SSI Shadow Platform",
                    "url": self.base_url
                }
            },
        }
        
        return settings
    
    def _prepare_request_data(self, request: Any = None, custom_data: Dict = None) -> Dict:
        """
        Prepare request data dictionary for python3-saml.
        
        This method converts a web framework request object (FastAPI, Flask, etc.)
        into the format expected by python3-saml.
        
        Args:
            request: Web framework request object (optional)
            custom_data: Custom request data dictionary (optional)
            
        Returns:
            Request data dictionary
        """
        if custom_data:
            # Use provided custom data
            return {
                "https": custom_data.get("https", "on"),
                "http_host": custom_data.get("http_host", urlparse(self.base_url).netloc),
                "script_name": custom_data.get("script_name", ""),
                "server_port": custom_data.get("server_port", "443"),
                "get_data": custom_data.get("get_data", {}),
                "post_data": custom_data.get("post_data", {}),
                "query_string": custom_data.get("query_string", ""),
            }
        
        if request is None:
            # Default request data
            parsed = urlparse(self.base_url)
            return {
                "https": "on" if parsed.scheme == "https" else "off",
                "http_host": parsed.netloc,
                "script_name": "",
                "server_port": str(parsed.port or (443 if parsed.scheme == "https" else 80)),
                "get_data": {},
                "post_data": {},
                "query_string": "",
            }
        
        # Try to extract from request object (FastAPI/Starlette)
        try:
            url = str(request.url)
            parsed = urlparse(url)
            
            # Get POST data if available
            post_data = {}
            if hasattr(request, '_form'):
                post_data = dict(request._form)
            
            return {
                "https": "on" if parsed.scheme == "https" else "off",
                "http_host": request.headers.get("host", parsed.netloc),
                "script_name": parsed.path,
                "server_port": str(parsed.port or (443 if parsed.scheme == "https" else 80)),
                "get_data": dict(request.query_params) if hasattr(request, 'query_params') else {},
                "post_data": post_data,
                "query_string": parsed.query or "",
            }
        except Exception as e:
            logger.warning(f"Could not extract request data: {e}")
            return self._prepare_request_data(custom_data={})
    
    # =========================================================================
    # SAML 2.0 FLOW
    # =========================================================================
    
    async def get_saml_login_url(
        self,
        org_id: str,
        relay_state: str = None,
        return_to: str = None
    ) -> Tuple[str, str]:
        """
        Generate SAML AuthnRequest URL for SSO login.
        
        Args:
            org_id: Organization ID
            relay_state: Optional custom relay state
            return_to: Optional URL to redirect to after login
            
        Returns:
            Tuple of (login_url, request_id)
        """
        if not SAML_AVAILABLE:
            raise SAMLConfigError("SAML support not available. Install python3-saml.")
        
        config = await self.get_sso_config(org_id)
        if not config or config.provider != "saml":
            raise SAMLConfigError("SAML not configured for this organization")
        
        if not config.sso_url:
            raise SAMLConfigError("SAML SSO URL not configured")
        
        if not config.entity_id:
            raise SAMLConfigError("SAML IdP Entity ID not configured")
        
        if not config.certificate:
            raise SAMLConfigError("SAML IdP certificate not configured")
        
        # Build SAML settings
        request_data = self._prepare_request_data()
        saml_settings = self._build_saml_settings(config, request_data)
        
        try:
            # Create SAML Auth instance
            auth = OneLogin_Saml2_Auth(request_data, saml_settings)
            
            # Generate login URL with AuthnRequest
            # relay_state is used to maintain state after IdP redirects back
            if not relay_state:
                relay_state = secrets.token_urlsafe(32)
            
            login_url = auth.login(return_to=return_to or relay_state)
            
            # Extract request ID from the AuthnRequest
            # This is used to match the response to the request
            request_id = auth.get_last_request_id()
            
            # Store request info for validation
            self.saml_requests[request_id] = {
                "org_id": org_id,
                "relay_state": relay_state,
                "return_to": return_to,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": (datetime.utcnow() + timedelta(minutes=10)).isoformat(),
            }
            
            # Also store relay state
            self.oauth_states[relay_state] = {
                "org_id": org_id,
                "type": "saml",
                "request_id": request_id,
                "return_to": return_to,
                "created_at": datetime.utcnow().isoformat(),
            }
            
            logger.info(f"SAML AuthnRequest generated for org {org_id}, request_id: {request_id}")
            return login_url, request_id
            
        except OneLogin_Saml2_Error as e:
            logger.error(f"SAML AuthnRequest generation failed: {e}")
            raise SAMLConfigError(f"Failed to generate SAML request: {str(e)}")
    
    async def handle_saml_response(
        self,
        request_data: Dict,
        org_id: str = None
    ) -> Dict[str, Any]:
        """
        Process SAML response from IdP (ACS endpoint).
        
        Args:
            request_data: Dictionary containing POST data with SAMLResponse
                          and optionally RelayState
            org_id: Optional organization ID (can be extracted from URL)
            
        Returns:
            Dictionary with access_token, refresh_token, and user info
        """
        if not SAML_AVAILABLE:
            raise SAMLConfigError("SAML support not available. Install python3-saml.")
        
        # Extract SAML response and relay state from POST data
        post_data = request_data.get("post_data", {})
        saml_response = post_data.get("SAMLResponse")
        relay_state = post_data.get("RelayState")
        
        if not saml_response:
            raise SAMLResponseError("No SAMLResponse in POST data")
        
        # Determine org_id from relay state or parameter
        if not org_id and relay_state:
            state_data = self.oauth_states.get(relay_state)
            if state_data:
                org_id = state_data.get("org_id")
        
        if not org_id:
            raise SAMLResponseError("Cannot determine organization from SAML response")
        
        # Get SSO config
        config = await self.get_sso_config(org_id)
        if not config or config.provider != "saml":
            raise SAMLConfigError("SAML not configured for this organization")
        
        # Build SAML settings
        saml_settings = self._build_saml_settings(config, request_data)
        
        try:
            # Create SAML Auth instance with request data
            auth = OneLogin_Saml2_Auth(request_data, saml_settings)
            
            # Process the SAML response
            auth.process_response()
            
            # Check for errors
            errors = auth.get_errors()
            
            if errors:
                error_reason = auth.get_last_error_reason()
                logger.error(f"SAML Response errors: {errors}, reason: {error_reason}")
                raise SAMLResponseError(
                    f"SAML validation failed: {error_reason}",
                    errors=errors
                )
            
            # Verify authentication
            if not auth.is_authenticated():
                raise SAMLAuthError("SAML authentication failed - user not authenticated")
            
            # Extract user attributes
            attributes = auth.get_attributes()
            name_id = auth.get_nameid()
            name_id_format = auth.get_nameid_format()
            session_index = auth.get_session_index()
            
            logger.debug(f"SAML attributes received: {json.dumps(attributes, indent=2)}")
            logger.debug(f"SAML NameID: {name_id}, format: {name_id_format}")
            
            # Map attributes to user data
            user_data = self._extract_user_data(attributes, name_id)
            
            # Validate email domain if restricted
            email = user_data.get("email", "").lower()
            if not email:
                raise SAMLAuthError("No email found in SAML response")
            
            if config.allowed_domains:
                domain = email.split("@")[-1]
                if domain not in config.allowed_domains:
                    raise SAMLAuthError(f"Email domain '{domain}' not allowed")
            
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
                            name=user_data.get("name", email.split("@")[0]),
                            role=config.default_role
                        ),
                        created_by="saml_sso"
                    )
                    user.auth_provider = "saml"
                    user.auth_provider_id = name_id
                    user.is_verified = True
                    logger.info(f"User auto-provisioned via SAML: {email}")
                else:
                    raise SAMLAuthError("User not found and auto-provisioning disabled")
            elif user.organization_id != org_id:
                raise SAMLAuthError("User belongs to a different organization")
            else:
                # Update existing user's SAML info
                user.auth_provider = "saml"
                user.auth_provider_id = name_id
                user.last_login = datetime.utcnow()
            
            # Update user groups if provided
            if user_data.get("groups"):
                await self._sync_user_groups(user, user_data["groups"], config)
            
            # Generate JWT tokens
            access_token, access_exp = user_service.create_access_token(user)
            refresh_token, refresh_exp = user_service.create_refresh_token(user)
            
            # Clean up state
            if relay_state:
                state_data = self.oauth_states.pop(relay_state, None)
                if state_data and state_data.get("request_id"):
                    self.saml_requests.pop(state_data["request_id"], None)
            
            # Get return URL
            return_to = None
            if relay_state:
                state_data = self.oauth_states.get(relay_state) or {}
                return_to = state_data.get("return_to")
            
            logger.info(f"SAML authentication successful for {email}")
            
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "expires_in": int((access_exp - datetime.utcnow()).total_seconds()),
                "return_to": return_to,
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "name": user.name,
                    "role": user.role,
                    "organization_id": user.organization_id,
                },
                "saml": {
                    "name_id": name_id,
                    "session_index": session_index,
                    "attributes": user_data,
                }
            }
            
        except OneLogin_Saml2_Error as e:
            logger.error(f"SAML processing error: {e}")
            raise SAMLResponseError(f"SAML processing failed: {str(e)}")
    
    def _extract_user_data(self, attributes: Dict[str, List], name_id: str) -> Dict:
        """
        Extract user data from SAML attributes using the attribute mapping.
        
        Args:
            attributes: SAML attributes dictionary
            name_id: SAML NameID value
            
        Returns:
            Dictionary with extracted user data
        """
        def get_first_match(possible_keys: List[str], default: str = None) -> Optional[str]:
            """Get the first matching attribute value."""
            for key in possible_keys:
                if key in attributes and attributes[key]:
                    value = attributes[key]
                    if isinstance(value, list):
                        return value[0] if value else default
                    return value
            return default
        
        def get_all_matches(possible_keys: List[str]) -> List[str]:
            """Get all matching attribute values."""
            result = []
            for key in possible_keys:
                if key in attributes and attributes[key]:
                    value = attributes[key]
                    if isinstance(value, list):
                        result.extend(value)
                    else:
                        result.append(value)
            return result
        
        # Extract email
        email = get_first_match(self.attribute_mapping.email)
        if not email:
            # Fall back to NameID if it looks like an email
            if name_id and "@" in name_id:
                email = name_id
        
        # Extract name parts
        first_name = get_first_match(self.attribute_mapping.first_name, "")
        last_name = get_first_match(self.attribute_mapping.last_name, "")
        display_name = get_first_match(self.attribute_mapping.display_name, "")
        
        # Build full name
        if first_name and last_name:
            full_name = f"{first_name} {last_name}"
        elif display_name:
            full_name = display_name
        elif first_name:
            full_name = first_name
        elif email:
            full_name = email.split("@")[0]
        else:
            full_name = "Unknown User"
        
        # Extract groups
        groups = get_all_matches(self.attribute_mapping.groups)
        
        # Extract other fields
        department = get_first_match(self.attribute_mapping.department)
        employee_id = get_first_match(self.attribute_mapping.employee_id)
        
        return {
            "email": email.lower() if email else None,
            "name": full_name,
            "first_name": first_name,
            "last_name": last_name,
            "groups": groups,
            "department": department,
            "employee_id": employee_id,
            "raw_attributes": attributes,
        }
    
    async def _sync_user_groups(
        self,
        user: User,
        groups: List[str],
        config: SSOConfig
    ) -> None:
        """
        Sync user role based on IdP group membership.
        
        Args:
            user: User object
            groups: List of group names from IdP
            config: SSO configuration with group mappings
        """
        # Example group-to-role mapping (customize per organization)
        group_role_mapping = {
            "ssi-admins": UserRole.ADMIN,
            "ssi-managers": UserRole.MANAGER,
            "ssi-analysts": UserRole.ANALYST,
            "ssi-viewers": UserRole.VIEWER,
            # Azure AD style
            "Admin": UserRole.ADMIN,
            "Manager": UserRole.MANAGER,
            # Okta style
            "Everyone": UserRole.VIEWER,
        }
        
        # Determine highest role from groups
        highest_role = config.default_role
        role_priority = {
            UserRole.ADMIN: 4,
            UserRole.MANAGER: 3,
            UserRole.ANALYST: 2,
            UserRole.VIEWER: 1,
        }
        
        for group in groups:
            if group in group_role_mapping:
                mapped_role = group_role_mapping[group]
                if role_priority.get(mapped_role, 0) > role_priority.get(highest_role, 0):
                    highest_role = mapped_role
        
        if user.role != highest_role:
            logger.info(f"Updating user {user.email} role from {user.role} to {highest_role} based on groups")
            user.role = highest_role
    
    async def get_saml_metadata(self, org_id: str) -> str:
        """
        Generate SP metadata XML for SAML configuration.
        
        This metadata should be provided to the IdP administrator
        when setting up the SAML integration.
        
        Args:
            org_id: Organization ID
            
        Returns:
            SP metadata XML string
        """
        if not SAML_AVAILABLE:
            raise SAMLConfigError("SAML support not available")
        
        config = await self.get_sso_config(org_id)
        if not config:
            # Generate metadata even without full config
            config = SSOConfig(
                organization_id=org_id,
                provider="saml",
                entity_id="",
                sso_url="",
            )
        
        request_data = self._prepare_request_data()
        saml_settings = self._build_saml_settings(config, request_data)
        
        try:
            settings = OneLogin_Saml2_Settings(saml_settings)
            metadata = settings.get_sp_metadata()
            errors = settings.validate_metadata(metadata)
            
            if errors:
                logger.warning(f"SP metadata validation warnings: {errors}")
            
            return metadata
            
        except Exception as e:
            logger.error(f"Failed to generate SP metadata: {e}")
            raise SAMLConfigError(f"Failed to generate metadata: {str(e)}")
    
    async def handle_saml_logout(
        self,
        request_data: Dict,
        org_id: str
    ) -> str:
        """
        Handle SAML Single Logout (SLO) request or response.
        
        Args:
            request_data: Request data dictionary
            org_id: Organization ID
            
        Returns:
            Redirect URL after logout
        """
        if not SAML_AVAILABLE:
            raise SAMLConfigError("SAML support not available")
        
        config = await self.get_sso_config(org_id)
        if not config:
            raise SAMLConfigError("SAML not configured")
        
        saml_settings = self._build_saml_settings(config, request_data)
        
        try:
            auth = OneLogin_Saml2_Auth(request_data, saml_settings)
            
            # Process logout request or response
            url = auth.process_slo()
            
            errors = auth.get_errors()
            if errors:
                logger.error(f"SAML SLO errors: {errors}")
            
            return url or f"{self.base_url}/login"
            
        except Exception as e:
            logger.error(f"SAML logout error: {e}")
            return f"{self.base_url}/login"
    
    # =========================================================================
    # OAUTH FLOW (Existing implementation)
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
            domain = config.entity_id or "example.okta.com"
            auth_endpoint = provider["authorization_endpoint_template"].format(domain=domain)
        
        params = {
            "client_id": config.client_id,
            "redirect_uri": redirect_uri or f"{self.base_url}/api/auth/sso/callback",
            "response_type": "code",
            "scope": " ".join(provider["scopes"]),
            "state": state,
        }
        
        # Provider-specific params
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
                from auth.models.entities import UserCreate
                user = await user_service.create_user(
                    org_id,
                    UserCreate(
                        email=email,
                        name=user_info.get("name", email.split("@")[0]),
                        role=config.default_role
                    ),
                    created_by="oauth_sso"
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
    # CLEANUP
    # =========================================================================
    
    async def cleanup_expired_states(self) -> int:
        """Clean up expired OAuth states and SAML requests."""
        now = datetime.utcnow()
        cleaned = 0
        
        # Clean OAuth states older than 10 minutes
        for state, data in list(self.oauth_states.items()):
            created_at = datetime.fromisoformat(data["created_at"])
            if (now - created_at).total_seconds() > 600:
                del self.oauth_states[state]
                cleaned += 1
        
        # Clean SAML requests older than 10 minutes
        for request_id, data in list(self.saml_requests.items()):
            expires_at = datetime.fromisoformat(data["expires_at"])
            if now > expires_at:
                del self.saml_requests[request_id]
                cleaned += 1
        
        if cleaned > 0:
            logger.info(f"Cleaned up {cleaned} expired SSO states")
        
        return cleaned
    
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


# =============================================================================
# EXPORTS
# =============================================================================

__all__ = [
    "SSOService",
    "get_sso_service",
    "init_sso_service",
    "SAMLError",
    "SAMLConfigError",
    "SAMLResponseError",
    "SAMLAuthError",
    "SAMLAttributeMapping",
    "SAML_AVAILABLE",
]
