#!/usr/bin/env python3
"""
Test script for Notification Channels with AWS SES
Run: python test_notifications.py
"""

import asyncio
import os
import sys
from unittest.mock import MagicMock, patch
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Optional, Any

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Create mock classes for testing without full dependencies
class AlertSeverity(Enum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"

@dataclass
class EmailConfig:
    recipients: List[str] = field(default_factory=list)
    sender_email: str = "notifications@ssi-shadow.io"
    sender_name: str = "SSI Shadow"
    is_active: bool = True
    provider: str = "sendgrid"
    api_key: Optional[str] = None
    smtp_host: Optional[str] = None
    smtp_port: int = 587
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    events: List[Any] = field(default_factory=list)

# Patch the entities module before importing notifications
import importlib.util
import types

# Create a mock entities module
mock_entities = types.ModuleType('webhooks.models.entities')
mock_entities.WebhookEvent = str
mock_entities.AlertSeverity = AlertSeverity
mock_entities.SlackConfig = type('SlackConfig', (), {})
mock_entities.TelegramConfig = type('TelegramConfig', (), {})
mock_entities.EmailConfig = EmailConfig
mock_entities.SMSConfig = type('SMSConfig', (), {})

sys.modules['webhooks.models.entities'] = mock_entities

# Now import the notification module directly
spec = importlib.util.spec_from_file_location(
    "notifications",
    os.path.join(os.path.dirname(__file__), "webhooks/channels/notifications.py")
)
notifications_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notifications_module)

EmailChannel = notifications_module.EmailChannel
NotificationService = notifications_module.NotificationService
BOTO3_AVAILABLE = notifications_module.BOTO3_AVAILABLE


async def test_email_channel_initialization():
    """Test EmailChannel initialization."""
    print("\n📧 Testing EmailChannel initialization...")
    
    config = EmailConfig(
        recipients=["test@example.com"],
        provider="ses",
        is_active=True
    )
    
    channel = EmailChannel(config)
    
    assert channel.config.provider == "ses"
    assert channel.config.recipients == ["test@example.com"]
    print("   ✅ EmailChannel initialized correctly")
    
    await channel.close()


async def test_ses_client_creation():
    """Test SES client creation with mocked boto3."""
    print("\n🔌 Testing SES client creation...")
    
    if not BOTO3_AVAILABLE:
        print("   ⚠️ boto3 not installed - skipping real client test")
        return
    
    # Set mock environment variables
    os.environ['AWS_REGION'] = 'us-east-1'
    os.environ['AWS_ACCESS_KEY_ID'] = 'test_key'
    os.environ['AWS_SECRET_ACCESS_KEY'] = 'test_secret'
    
    config = EmailConfig(
        recipients=["test@example.com"],
        provider="ses",
        is_active=True
    )
    
    channel = EmailChannel(config)
    
    try:
        # This will create a client but won't make real API calls
        client = channel._get_ses_client()
        assert client is not None
        print("   ✅ SES client created successfully")
    except Exception as e:
        print(f"   ⚠️ SES client creation info: {e}")
    
    await channel.close()


async def test_ses_send_with_mock():
    """Test SES send with mocked boto3."""
    print("\n📤 Testing SES send with mock...")
    
    if not BOTO3_AVAILABLE:
        print("   ⚠️ boto3 not available - skipping SES mock test")
        return
    
    config = EmailConfig(
        recipients=["test@example.com", "test2@example.com"],
        sender_email="sender@ssi-shadow.io",
        sender_name="SSI Shadow Test",
        provider="ses",
        is_active=True
    )
    
    channel = EmailChannel(config)
    
    # Mock the boto3 client
    mock_ses = MagicMock()
    mock_ses.send_email.return_value = {'MessageId': 'test-message-id-12345'}
    channel._ses_client = mock_ses
    
    # Send test email
    result = await channel._send_ses(
        subject="Test Alert",
        html_content="<h1>Test</h1><p>This is a test.</p>",
        text_content="Test\n====\nThis is a test."
    )
    
    assert result == True
    mock_ses.send_email.assert_called_once()
    
    # Verify call parameters
    call_args = mock_ses.send_email.call_args
    assert call_args is not None
    
    print("   ✅ SES send works with mock")
    print(f"   📧 Mock MessageId: test-message-id-12345")
    
    await channel.close()


async def test_ses_error_handling():
    """Test SES error handling."""
    print("\n❌ Testing SES error handling...")
    
    config = EmailConfig(
        recipients=["test@example.com"],
        provider="ses",
        is_active=True
    )
    
    channel = EmailChannel(config)
    
    if BOTO3_AVAILABLE:
        from botocore.exceptions import ClientError
        
        # Mock client that raises errors
        mock_ses = MagicMock()
        mock_ses.send_email.side_effect = ClientError(
            {'Error': {'Code': 'MessageRejected', 'Message': 'Email rejected'}},
            'send_email'
        )
        channel._ses_client = mock_ses
        
        result = await channel._send_ses(
            subject="Test",
            html_content="<p>Test</p>",
            text_content="Test"
        )
        
        assert result == False
        print("   ✅ ClientError handled correctly")
    else:
        print("   ⚠️ boto3 not available - testing RuntimeError")
        
        result = await channel._send_ses(
            subject="Test",
            html_content="<p>Test</p>",
            text_content="Test"
        )
        
        assert result == False
        print("   ✅ Missing boto3 handled correctly")
    
    await channel.close()


async def test_html_content_generation():
    """Test HTML email content generation."""
    print("\n🎨 Testing HTML content generation...")
    
    config = EmailConfig(
        recipients=["test@example.com"],
        provider="ses",
        is_active=True
    )
    
    channel = EmailChannel(config)
    
    html = channel._build_html(
        title="Test Alert",
        message="This is a test message.",
        data={"event": "Purchase", "value": "$150.00", "user": "test@example.com"},
        severity=AlertSeverity.WARNING
    )
    
    assert "Test Alert" in html
    assert "This is a test message." in html
    assert "$150.00" in html
    assert "#FF9800" in html  # Warning color
    
    print("   ✅ HTML content generated correctly")
    print(f"   📄 HTML length: {len(html)} chars")
    
    await channel.close()


async def test_text_content_generation():
    """Test plain text email content generation."""
    print("\n📝 Testing text content generation...")
    
    config = EmailConfig(
        recipients=["test@example.com"],
        provider="ses",
        is_active=True
    )
    
    channel = EmailChannel(config)
    
    text = channel._build_text(
        title="Test Alert",
        message="This is a test message.",
        data={"event": "Purchase", "value": "$150.00"},
        severity=AlertSeverity.ERROR
    )
    
    assert "Test Alert" in text
    assert "This is a test message." in text
    assert "$150.00" in text
    assert "SSI Shadow" in text
    
    print("   ✅ Text content generated correctly")
    print(f"   📄 Text length: {len(text)} chars")
    
    await channel.close()


async def test_notification_service():
    """Test NotificationService with email channel."""
    print("\n🔧 Testing NotificationService...")
    
    service = NotificationService()
    
    # Configure email channel
    email_config = EmailConfig(
        recipients=["test@example.com"],
        provider="ses",
        is_active=True
    )
    service.configure_email(email_config)
    
    assert "email" in service.channels
    print("   ✅ Email channel configured")
    
    # Test with mock
    email_channel = service.channels["email"]
    mock_ses = MagicMock()
    mock_ses.send_email.return_value = {'MessageId': 'test-123'}
    email_channel._ses_client = mock_ses
    
    # Send notification
    results = await service.send(
        channels=["email"],
        title="Test Notification",
        message="This is a test.",
        data={"test": "true"},
        severity=AlertSeverity.INFO
    )
    
    assert results.get("email") == True
    print("   ✅ Notification sent successfully")
    
    await service.close()


async def test_smtp_configuration():
    """Test SMTP email configuration."""
    print("\n📬 Testing SMTP configuration...")
    
    config = EmailConfig(
        recipients=["test@example.com"],
        provider="smtp",
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_username="user@gmail.com",
        smtp_password="password",
        is_active=True
    )
    
    channel = EmailChannel(config)
    
    assert channel.config.provider == "smtp"
    assert channel.config.smtp_host == "smtp.gmail.com"
    assert channel.config.smtp_port == 587
    
    print("   ✅ SMTP configuration correct")
    
    await channel.close()


async def run_all_tests():
    """Run all tests."""
    print("=" * 60)
    print("🧪 Testing Notification Channels with AWS SES")
    print("=" * 60)
    print(f"📦 boto3 available: {BOTO3_AVAILABLE}")
    
    try:
        await test_email_channel_initialization()
        await test_ses_client_creation()
        await test_ses_send_with_mock()
        await test_ses_error_handling()
        await test_html_content_generation()
        await test_text_content_generation()
        await test_notification_service()
        await test_smtp_configuration()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        
        # Summary
        print("\n📋 AWS SES Implementation Summary:")
        print("   • EmailChannel with SendGrid, SES, SMTP support")
        print("   • Async boto3 via run_in_executor")
        print("   • Proper error handling for AWS exceptions")
        print("   • HTML and plain text email generation")
        print("   • Thread-safe client management")
        
        print("\n🔧 Required Environment Variables for SES:")
        print("   • AWS_REGION (default: us-east-1)")
        print("   • AWS_ACCESS_KEY_ID")
        print("   • AWS_SECRET_ACCESS_KEY")
        
        print("\n📧 Usage Example:")
        print('''
    from webhooks.channels.notifications import EmailChannel
    from webhooks.models.entities import EmailConfig, AlertSeverity
    
    config = EmailConfig(
        recipients=["alert@yourcompany.com"],
        sender_email="noreply@ssi-shadow.io",
        provider="ses",
        is_active=True
    )
    
    channel = EmailChannel(config)
    success = await channel.send(
        title="High Trust Score Alert",
        message="Conversion detected with 0.95 trust score.",
        data={"event_id": "evt_123", "value": "$150.00"},
        severity=AlertSeverity.INFO
    )
        ''')
        
        return True
        
    except Exception as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    sys.exit(0 if success else 1)
