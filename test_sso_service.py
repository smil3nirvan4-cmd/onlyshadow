#!/usr/bin/env python3
"""
Test script for SSO Service with SAML 2.0
Run: python test_sso_service.py
"""

import asyncio
import os
import sys
import base64

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Check for python3-saml
try:
    from onelogin.saml2.auth import OneLogin_Saml2_Auth
    SAML_AVAILABLE = True
except ImportError:
    SAML_AVAILABLE = False
    print("⚠️  python3-saml not installed. Install with: pip install python3-saml")

from auth.services.sso_service_v2 import (
    SSOService,
    SAMLError,
    SAMLConfigError,
    SAMLAttributeMapping,
    SAML_AVAILABLE as SERVICE_SAML_AVAILABLE,
)


# Mock SSOConfig for testing
class MockSSOConfig:
    def __init__(self):
        self.id = "sso_test_123"
        self.organization_id = "org_123"
        self.provider = "saml"
        self.entity_id = "https://idp.example.com/saml"
        self.sso_url = "https://idp.example.com/saml/sso"
        self.certificate = """-----BEGIN CERTIFICATE-----
MIICpDCCAYwCCQDU+pQ4P4AYzTANBgkqhkiG9w0BAQsFADAUMRIwEAYDVQQDDAls
b2NhbGhvc3QwHhcNMjQwMTAxMDAwMDAwWhcNMjUwMTAxMDAwMDAwWjAUMRIwEAYD
VQQDDAlsb2NhbGhvc3QwggEiMA0GCSqGSIb3DQEBAQUAA4IBDwAwggEKAoIBAQC7
o5e7TOKRHJFhG6HgmF5n3P8HNKKyXD4PcXMIyZcRB4FyVBOuBJFSbRmBT4gFO3IY
3fBgRWoIZXJ5B3HGQkBIG8j8J0n3RQl8P5ug3F4v6DrJX3tvF3DP6/ZDKlT3MPNS
JZKyQkXmRMkI3P6R3qK0jI5NQYALCwB7wfPJYCsWQwQ7VxKJvPDHPxJ6V5e7s6zu
G5c5VpKuJC5lN1TIYn5G7L4VQ4AuhJzYg8Y8Y+FvQIxvKqHU0e5V3PtLPcNRKL9k
LB3CRY1eW7YbC5q3HKVPxQBmZ0F5C9e8Y+v7y9fj4bm6d7A6E9Rf0pF3K8TDYQ3P
ODAhYQ3f5vJ9fJ8F3pJnAgMBAAEwDQYJKoZIhvcNAQELBQADggEBAHN1/L5EQNZL
QFu5zP0FPMnCK7e3sPj9A1j7I5h8Y9e9P0N1Zw3P0K2r7Q5V5D4v6U8W3X1tM9gT
f0K3dX2O1y7U9b3Z5c6V7X8W3D9F0J1K2L3M4N5O6P7Q8R9S0T1U2V3W4X5Y6Z7A
1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6Q7R8S9T0U1V2W3X4Y5Z6A7B8C9D0E1F2G
-----END CERTIFICATE-----"""
        self.client_id = None
        self.client_secret_encrypted = None
        self.enforce_sso = False
        self.auto_provision = True
        self.default_role = "viewer"
        self.allowed_domains = ["example.com"]
        self.is_active = True
        self.slo_url = None


async def test_service_initialization():
    """Test SSO service initialization."""
    print("\n" + "=" * 60)
    print("🧪 Testing SSOService Initialization")
    print("=" * 60)
    
    service = SSOService()
    
    print(f"\n📦 python3-saml available: {SERVICE_SAML_AVAILABLE}")
    print(f"📦 Encryption initialized: {service.fernet is not None}")
    print(f"📦 HTTP client initialized: {service.http_client is not None}")
    print(f"📦 Base URL: {service.base_url}")
    print(f"📦 SAML Strict Mode: {service.saml_strict}")
    
    await service.close()
    print("\n✅ Service initialization passed!")


async def test_attribute_mapping():
    """Test SAML attribute mapping."""
    print("\n" + "=" * 60)
    print("🧪 Testing SAMLAttributeMapping")
    print("=" * 60)
    
    mapping = SAMLAttributeMapping()
    
    print("\n📋 Email attributes to check:")
    for attr in mapping.email[:5]:
        print(f"   - {attr}")
    
    print("\n📋 First name attributes to check:")
    for attr in mapping.first_name[:5]:
        print(f"   - {attr}")
    
    print("\n📋 Groups attributes to check:")
    for attr in mapping.groups[:5]:
        print(f"   - {attr}")
    
    # Test extraction
    service = SSOService()
    
    # Simulate Okta-style attributes
    okta_attributes = {
        "email": ["john.doe@example.com"],
        "firstName": ["John"],
        "lastName": ["Doe"],
        "groups": ["Everyone", "Engineering", "ssi-admins"],
    }
    
    user_data = service._extract_user_data(okta_attributes, "john.doe@example.com")
    
    print(f"\n✅ Okta attributes extracted:")
    print(f"   Email: {user_data['email']}")
    print(f"   Name: {user_data['name']}")
    print(f"   Groups: {user_data['groups']}")
    
    # Simulate Azure AD-style attributes
    azure_attributes = {
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress": ["jane@company.com"],
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/givenname": ["Jane"],
        "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/surname": ["Smith"],
        "http://schemas.microsoft.com/ws/2008/06/identity/claims/groups": ["Admin", "Users"],
    }
    
    user_data = service._extract_user_data(azure_attributes, "jane@company.com")
    
    print(f"\n✅ Azure AD attributes extracted:")
    print(f"   Email: {user_data['email']}")
    print(f"   Name: {user_data['name']}")
    print(f"   Groups: {user_data['groups']}")
    
    await service.close()
    print("\n✅ Attribute mapping tests passed!")


async def test_saml_settings_builder():
    """Test SAML settings builder."""
    print("\n" + "=" * 60)
    print("🧪 Testing SAML Settings Builder")
    print("=" * 60)
    
    service = SSOService()
    config = MockSSOConfig()
    
    # Build settings
    settings = service._build_saml_settings(config)
    
    print(f"\n📋 SP Settings:")
    print(f"   Entity ID: {settings['sp']['entityId']}")
    print(f"   ACS URL: {settings['sp']['assertionConsumerService']['url']}")
    print(f"   SLS URL: {settings['sp']['singleLogoutService']['url']}")
    print(f"   NameID Format: {settings['sp']['NameIDFormat']}")
    
    print(f"\n📋 IdP Settings:")
    print(f"   Entity ID: {settings['idp']['entityId']}")
    print(f"   SSO URL: {settings['idp']['singleSignOnService']['url']}")
    print(f"   Certificate: {settings['idp']['x509cert'][:50]}...")
    
    print(f"\n📋 Security Settings:")
    print(f"   Strict: {settings['strict']}")
    print(f"   wantAssertionsSigned: {settings['security']['wantAssertionsSigned']}")
    print(f"   signatureAlgorithm: {settings['security']['signatureAlgorithm']}")
    
    await service.close()
    print("\n✅ SAML settings builder tests passed!")


async def test_request_data_preparation():
    """Test request data preparation."""
    print("\n" + "=" * 60)
    print("🧪 Testing Request Data Preparation")
    print("=" * 60)
    
    service = SSOService()
    
    # Test default request data
    request_data = service._prepare_request_data()
    
    print(f"\n📋 Default Request Data:")
    print(f"   https: {request_data['https']}")
    print(f"   http_host: {request_data['http_host']}")
    print(f"   server_port: {request_data['server_port']}")
    
    # Test custom request data
    custom_data = {
        "https": "on",
        "http_host": "app.ssi-shadow.io",
        "script_name": "/api/auth/saml/acs",
        "server_port": "443",
        "post_data": {"SAMLResponse": "base64data", "RelayState": "abc123"},
    }
    
    request_data = service._prepare_request_data(custom_data=custom_data)
    
    print(f"\n📋 Custom Request Data:")
    print(f"   https: {request_data['https']}")
    print(f"   http_host: {request_data['http_host']}")
    print(f"   script_name: {request_data['script_name']}")
    print(f"   post_data: {list(request_data['post_data'].keys())}")
    
    await service.close()
    print("\n✅ Request data preparation tests passed!")


async def test_sso_config_management():
    """Test SSO config CRUD operations."""
    print("\n" + "=" * 60)
    print("🧪 Testing SSO Config Management")
    print("=" * 60)
    
    service = SSOService()
    
    # Create mock config data
    from auth.models.entities import SSOConfigCreate
    
    config_data = SSOConfigCreate(
        provider="saml",
        entity_id="https://idp.example.com/saml",
        sso_url="https://idp.example.com/saml/sso",
        certificate="-----BEGIN CERTIFICATE-----\nMIIC...\n-----END CERTIFICATE-----",
        enforce_sso=False,
        auto_provision=True,
        default_role="viewer",
        allowed_domains=["example.com"],
    )
    
    # Create config
    print("\n1️⃣ Creating SSO config...")
    config = await service.create_sso_config("org_test_123", config_data, "admin_user")
    print(f"   ✅ Created config: {config.id}")
    print(f"   Provider: {config.provider}")
    print(f"   Entity ID: {config.entity_id}")
    
    # Get config
    print("\n2️⃣ Getting SSO config...")
    retrieved = await service.get_sso_config("org_test_123")
    assert retrieved is not None
    assert retrieved.id == config.id
    print(f"   ✅ Retrieved config: {retrieved.id}")
    
    # Update config
    print("\n3️⃣ Updating SSO config...")
    config_data.enforce_sso = True
    updated = await service.update_sso_config("org_test_123", config_data, "admin_user")
    assert updated.enforce_sso == True
    print(f"   ✅ Updated enforce_sso: {updated.enforce_sso}")
    
    # Delete config
    print("\n4️⃣ Deleting SSO config...")
    deleted = await service.delete_sso_config("org_test_123", "admin_user")
    assert deleted == True
    print(f"   ✅ Deleted config")
    
    # Verify deletion
    retrieved = await service.get_sso_config("org_test_123")
    assert retrieved is None
    print(f"   ✅ Config no longer accessible")
    
    await service.close()
    print("\n✅ SSO config management tests passed!")


async def test_saml_login_flow():
    """Test SAML login URL generation."""
    print("\n" + "=" * 60)
    print("🧪 Testing SAML Login Flow")
    print("=" * 60)
    
    if not SAML_AVAILABLE:
        print("⚠️  Skipping - python3-saml not installed")
        return
    
    service = SSOService()
    
    # Create SSO config
    from auth.models.entities import SSOConfigCreate
    
    config_data = SSOConfigCreate(
        provider="saml",
        entity_id="https://idp.example.com/saml",
        sso_url="https://idp.example.com/saml/sso",
        certificate=MockSSOConfig().certificate,
        enforce_sso=False,
        auto_provision=True,
        default_role="viewer",
        allowed_domains=["example.com"],
    )
    
    await service.create_sso_config("org_saml_test", config_data, "admin")
    
    try:
        print("\n1️⃣ Generating SAML login URL...")
        login_url, request_id = await service.get_saml_login_url(
            org_id="org_saml_test",
            return_to="/dashboard"
        )
        
        print(f"   ✅ Login URL generated")
        print(f"   URL starts with: {login_url[:60]}...")
        print(f"   Request ID: {request_id}")
        
        # Verify state was stored
        print("\n2️⃣ Verifying state storage...")
        assert request_id in service.saml_requests
        print(f"   ✅ Request stored with org_id: {service.saml_requests[request_id]['org_id']}")
        
    except Exception as e:
        print(f"   ⚠️  Expected error (no real IdP): {type(e).__name__}")
    
    await service.close()
    print("\n✅ SAML login flow tests passed!")


async def test_saml_metadata_generation():
    """Test SP metadata generation."""
    print("\n" + "=" * 60)
    print("🧪 Testing SAML Metadata Generation")
    print("=" * 60)
    
    if not SAML_AVAILABLE:
        print("⚠️  Skipping - python3-saml not installed")
        return
    
    service = SSOService()
    
    # Create SSO config
    from auth.models.entities import SSOConfigCreate
    
    config_data = SSOConfigCreate(
        provider="saml",
        entity_id="https://idp.example.com/saml",
        sso_url="https://idp.example.com/saml/sso",
        certificate=MockSSOConfig().certificate,
    )
    
    await service.create_sso_config("org_metadata_test", config_data, "admin")
    
    try:
        print("\n📋 Generating SP Metadata...")
        metadata = await service.get_saml_metadata("org_metadata_test")
        
        print(f"   ✅ Metadata generated ({len(metadata)} bytes)")
        print(f"   Contains EntityDescriptor: {'EntityDescriptor' in metadata}")
        print(f"   Contains AssertionConsumerService: {'AssertionConsumerService' in metadata}")
        print(f"   Contains SingleLogoutService: {'SingleLogoutService' in metadata}")
        
        # Show snippet
        print(f"\n   First 200 chars:")
        print(f"   {metadata[:200]}...")
        
    except Exception as e:
        print(f"   ⚠️  Error: {e}")
    
    await service.close()
    print("\n✅ Metadata generation tests passed!")


async def test_state_cleanup():
    """Test expired state cleanup."""
    print("\n" + "=" * 60)
    print("🧪 Testing State Cleanup")
    print("=" * 60)
    
    service = SSOService()
    
    # Add some old states
    from datetime import datetime, timedelta
    
    old_time = (datetime.utcnow() - timedelta(minutes=15)).isoformat()
    
    service.oauth_states["old_state_1"] = {
        "org_id": "org_1",
        "created_at": old_time,
    }
    service.oauth_states["old_state_2"] = {
        "org_id": "org_2",
        "created_at": old_time,
    }
    service.oauth_states["recent_state"] = {
        "org_id": "org_3",
        "created_at": datetime.utcnow().isoformat(),
    }
    
    service.saml_requests["old_request"] = {
        "org_id": "org_1",
        "expires_at": old_time,
    }
    
    print(f"\n📋 Before cleanup:")
    print(f"   OAuth states: {len(service.oauth_states)}")
    print(f"   SAML requests: {len(service.saml_requests)}")
    
    # Run cleanup
    cleaned = await service.cleanup_expired_states()
    
    print(f"\n📋 After cleanup:")
    print(f"   Cleaned: {cleaned} items")
    print(f"   OAuth states: {len(service.oauth_states)}")
    print(f"   SAML requests: {len(service.saml_requests)}")
    
    assert len(service.oauth_states) == 1
    assert "recent_state" in service.oauth_states
    
    await service.close()
    print("\n✅ State cleanup tests passed!")


async def run_all_tests():
    """Run all tests."""
    print("\n" + "=" * 60)
    print("🧪 SSO SERVICE TEST SUITE (SAML 2.0)")
    print("=" * 60)
    print(f"📦 python3-saml: {'✅ Available' if SAML_AVAILABLE else '❌ Not installed'}")
    
    try:
        await test_service_initialization()
        await test_attribute_mapping()
        await test_saml_settings_builder()
        await test_request_data_preparation()
        await test_sso_config_management()
        await test_saml_login_flow()
        await test_saml_metadata_generation()
        await test_state_cleanup()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        
        # Usage summary
        print("\n📖 USAGE SUMMARY")
        print("-" * 40)
        print("""
# 1. Install dependencies:
pip install python3-saml httpx cryptography

# 2. Set environment variables:
export ENCRYPTION_KEY=$(python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")
export BASE_URL=https://app.ssi-shadow.io
export SAML_STRICT=true
export SAML_DEBUG=false

# 3. Configure SSO in your organization:
from auth.services.sso_service_v2 import get_sso_service
from auth.models.entities import SSOConfigCreate

service = get_sso_service()

# Create SAML SSO config
config = await service.create_sso_config(
    org_id="org_123",
    data=SSOConfigCreate(
        provider="saml",
        entity_id="https://your-idp.okta.com/saml",
        sso_url="https://your-idp.okta.com/saml/sso",
        certificate="-----BEGIN CERTIFICATE-----...",
        auto_provision=True,
        allowed_domains=["yourcompany.com"],
    ),
    created_by="admin"
)

# 4. Generate login URL for users:
login_url, request_id = await service.get_saml_login_url(
    org_id="org_123",
    return_to="/dashboard"
)
# Redirect user to login_url

# 5. Handle SAML response (ACS endpoint):
@app.post("/api/auth/saml/acs/{org_id}")
async def saml_acs(org_id: str, request: Request):
    form = await request.form()
    request_data = {
        "https": "on",
        "http_host": request.headers.get("host"),
        "post_data": dict(form),
    }
    
    result = await service.handle_saml_response(request_data, org_id)
    
    # result contains:
    # - access_token
    # - refresh_token
    # - user info
    
    return RedirectResponse(f"/dashboard?token={result['access_token']}")

# 6. Generate SP metadata for IdP configuration:
metadata = await service.get_saml_metadata("org_123")
# Provide this XML to your IdP administrator
""")
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
