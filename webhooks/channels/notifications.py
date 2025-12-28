"""
S.S.I. SHADOW - Notification Channels v2
=========================================
Implementations for Slack, Telegram, Email (SendGrid + AWS SES), and SMS notifications.

Version: 2.0.0
Author: SSI Shadow Team

CHANGELOG v2:
- AWS SES implementation real (boto3)
- SMTP support added
- Better error handling
- Async boto3 via run_in_executor
"""

import os
import logging
import asyncio
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, Dict, List, Any
from concurrent.futures import ThreadPoolExecutor
import json

import httpx

# Import boto3 for AWS SES - fail gracefully
try:
    import boto3
    from botocore.exceptions import (
        ClientError, 
        NoCredentialsError, 
        PartialCredentialsError,
        EndpointConnectionError
    )
    BOTO3_AVAILABLE = True
except ImportError:
    BOTO3_AVAILABLE = False
    boto3 = None

# Import smtplib for SMTP
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from webhooks.models.entities import (
    WebhookEvent,
    AlertSeverity,
    SlackConfig,
    TelegramConfig,
    EmailConfig,
    SMSConfig,
)

logger = logging.getLogger(__name__)

# Thread pool for blocking boto3 calls
_executor = ThreadPoolExecutor(max_workers=4)


# =============================================================================
# BASE CHANNEL
# =============================================================================

class NotificationChannel(ABC):
    """Abstract base class for notification channels."""
    
    @abstractmethod
    async def send(
        self,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> bool:
        """Send a notification."""
        pass
    
    @abstractmethod
    async def test(self) -> Dict[str, Any]:
        """Test the channel configuration."""
        pass
    
    async def close(self):
        """Close any resources. Override if needed."""
        pass


# =============================================================================
# SLACK CHANNEL
# =============================================================================

class SlackChannel(NotificationChannel):
    """Slack notification channel using webhooks."""
    
    def __init__(self, config: SlackConfig):
        self.config = config
        self.http_client = httpx.AsyncClient(timeout=10.0)
    
    async def send(
        self,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> bool:
        """Send a Slack notification."""
        if not self.config.is_active:
            return False
        
        # Build Slack blocks
        blocks = self._build_blocks(title, message, data, severity)
        
        payload = {
            "username": self.config.username,
            "icon_emoji": self.config.icon_emoji,
            "blocks": blocks
        }
        
        if self.config.channel:
            payload["channel"] = self.config.channel
        
        try:
            response = await self.http_client.post(
                str(self.config.webhook_url),
                json=payload
            )
            
            if response.status_code == 200:
                logger.info(f"Slack notification sent: {title}")
                return True
            else:
                logger.error(f"Slack error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Slack send error: {e}")
            return False
    
    def _build_blocks(
        self,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> List[Dict]:
        """Build Slack blocks."""
        # Severity emoji
        emoji_map = {
            AlertSeverity.INFO: ":information_source:",
            AlertSeverity.WARNING: ":warning:",
            AlertSeverity.ERROR: ":x:",
            AlertSeverity.CRITICAL: ":rotating_light:"
        }
        
        emoji = emoji_map.get(severity, ":bell:")
        
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {title}",
                    "emoji": True
                }
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": message
                }
            }
        ]
        
        # Add data fields
        if data:
            fields = []
            for key, value in list(data.items())[:10]:  # Max 10 fields
                fields.append({
                    "type": "mrkdwn",
                    "text": f"*{key}:*\n{value}"
                })
            
            if fields:
                # Slack limits 10 fields per section
                for i in range(0, len(fields), 2):
                    blocks.append({
                        "type": "section",
                        "fields": fields[i:i+2]
                    })
        
        # Add timestamp
        blocks.append({
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"SSI Shadow • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                }
            ]
        })
        
        return blocks
    
    async def test(self) -> Dict[str, Any]:
        """Test Slack configuration."""
        success = await self.send(
            title="Test Notification",
            message="This is a test message from SSI Shadow.",
            data={"test": "true"},
            severity=AlertSeverity.INFO
        )
        return {"success": success, "channel": "slack"}
    
    async def close(self):
        await self.http_client.aclose()


# =============================================================================
# TELEGRAM CHANNEL
# =============================================================================

class TelegramChannel(NotificationChannel):
    """Telegram notification channel using Bot API."""
    
    def __init__(self, config: TelegramConfig):
        self.config = config
        self.api_url = f"https://api.telegram.org/bot{config.bot_token}"
        self.http_client = httpx.AsyncClient(timeout=10.0)
    
    async def send(
        self,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> bool:
        """Send a Telegram notification."""
        if not self.config.is_active:
            return False
        
        # Build message
        text = self._build_message(title, message, data, severity)
        
        payload = {
            "chat_id": self.config.chat_id,
            "text": text,
            "parse_mode": self.config.parse_mode,
            "disable_web_page_preview": True
        }
        
        try:
            response = await self.http_client.post(
                f"{self.api_url}/sendMessage",
                json=payload
            )
            
            result = response.json()
            
            if result.get("ok"):
                logger.info(f"Telegram notification sent: {title}")
                return True
            else:
                logger.error(f"Telegram error: {result.get('description')}")
                return False
                
        except Exception as e:
            logger.error(f"Telegram send error: {e}")
            return False
    
    def _build_message(
        self,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> str:
        """Build Telegram message with HTML formatting."""
        # Severity emoji
        emoji_map = {
            AlertSeverity.INFO: "ℹ️",
            AlertSeverity.WARNING: "⚠️",
            AlertSeverity.ERROR: "❌",
            AlertSeverity.CRITICAL: "🚨"
        }
        
        emoji = emoji_map.get(severity, "🔔")
        
        text = f"{emoji} <b>{title}</b>\n\n{message}"
        
        if data:
            text += "\n\n<b>Details:</b>"
            for key, value in list(data.items())[:10]:
                text += f"\n• <b>{key}:</b> {value}"
        
        text += f"\n\n<i>SSI Shadow • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</i>"
        
        return text
    
    async def test(self) -> Dict[str, Any]:
        """Test Telegram configuration."""
        success = await self.send(
            title="Test Notification",
            message="This is a test message from SSI Shadow.",
            data={"test": "true"},
            severity=AlertSeverity.INFO
        )
        return {"success": success, "channel": "telegram"}
    
    async def close(self):
        await self.http_client.aclose()


# =============================================================================
# EMAIL CHANNEL
# =============================================================================

class EmailChannel(NotificationChannel):
    """
    Email notification channel supporting multiple providers:
    - SendGrid (API)
    - AWS SES (boto3)
    - SMTP (standard)
    """
    
    def __init__(self, config: EmailConfig):
        self.config = config
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self._ses_client = None
    
    def _get_ses_client(self):
        """Get or create AWS SES client."""
        if not BOTO3_AVAILABLE:
            raise RuntimeError("boto3 is not installed. Run: pip install boto3")
        
        if self._ses_client is None:
            # Get credentials from environment or config
            region = os.getenv('AWS_REGION', os.getenv('AWS_DEFAULT_REGION', 'us-east-1'))
            access_key = os.getenv('AWS_ACCESS_KEY_ID')
            secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
            
            if access_key and secret_key:
                # Use explicit credentials
                self._ses_client = boto3.client(
                    'ses',
                    region_name=region,
                    aws_access_key_id=access_key,
                    aws_secret_access_key=secret_key
                )
            else:
                # Use default credentials (IAM role, ~/.aws/credentials, etc.)
                self._ses_client = boto3.client('ses', region_name=region)
        
        return self._ses_client
    
    async def send(
        self,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> bool:
        """Send an email notification."""
        if not self.config.is_active:
            return False
        
        if not self.config.recipients:
            logger.warning("No email recipients configured")
            return False
        
        # Build email content
        html_content = self._build_html(title, message, data, severity)
        text_content = self._build_text(title, message, data, severity)
        
        # Route to appropriate provider
        if self.config.provider == "sendgrid":
            return await self._send_sendgrid(title, html_content, text_content)
        elif self.config.provider == "ses":
            return await self._send_ses(title, html_content, text_content)
        elif self.config.provider == "smtp":
            return await self._send_smtp(title, html_content, text_content)
        else:
            logger.error(f"Unsupported email provider: {self.config.provider}")
            return False
    
    async def _send_sendgrid(
        self,
        subject: str,
        html_content: str,
        text_content: str
    ) -> bool:
        """Send via SendGrid API."""
        if not self.config.api_key:
            logger.error("SendGrid API key not configured")
            return False
        
        payload = {
            "personalizations": [
                {"to": [{"email": r} for r in self.config.recipients]}
            ],
            "from": {
                "email": self.config.sender_email,
                "name": self.config.sender_name
            },
            "subject": subject,
            "content": [
                {"type": "text/plain", "value": text_content},
                {"type": "text/html", "value": html_content}
            ]
        }
        
        try:
            response = await self.http_client.post(
                "https://api.sendgrid.com/v3/mail/send",
                json=payload,
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json"
                }
            )
            
            if response.status_code in [200, 202]:
                logger.info(f"Email sent via SendGrid: {subject}")
                return True
            else:
                logger.error(f"SendGrid error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"SendGrid error: {e}")
            return False
    
    async def _send_ses(
        self,
        subject: str,
        html_content: str,
        text_content: str
    ) -> bool:
        """
        Send via AWS SES.
        
        Required environment variables:
        - AWS_REGION or AWS_DEFAULT_REGION (default: us-east-1)
        - AWS_ACCESS_KEY_ID (optional if using IAM role)
        - AWS_SECRET_ACCESS_KEY (optional if using IAM role)
        
        The sender email must be verified in SES.
        """
        if not BOTO3_AVAILABLE:
            logger.error("AWS SES requires boto3. Install with: pip install boto3")
            return False
        
        try:
            # Get client (may raise if credentials missing)
            ses_client = self._get_ses_client()
            
            # Build email message
            message = {
                'Subject': {
                    'Data': subject,
                    'Charset': 'UTF-8'
                },
                'Body': {
                    'Text': {
                        'Data': text_content,
                        'Charset': 'UTF-8'
                    },
                    'Html': {
                        'Data': html_content,
                        'Charset': 'UTF-8'
                    }
                }
            }
            
            # Run boto3 call in thread pool (it's blocking)
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                _executor,
                lambda: ses_client.send_email(
                    Source=f"{self.config.sender_name} <{self.config.sender_email}>",
                    Destination={
                        'ToAddresses': self.config.recipients
                    },
                    Message=message,
                    # Optional: Add reply-to
                    # ReplyToAddresses=[self.config.sender_email],
                )
            )
            
            message_id = response.get('MessageId', 'unknown')
            logger.info(f"Email sent via AWS SES: {subject} (MessageId: {message_id})")
            return True
            
        except NoCredentialsError:
            logger.error("AWS SES Error: No credentials found. Set AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY")
            return False
        
        except PartialCredentialsError as e:
            logger.error(f"AWS SES Error: Incomplete credentials - {e}")
            return False
        
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            error_message = e.response.get('Error', {}).get('Message', str(e))
            
            if error_code == 'MessageRejected':
                logger.error(f"AWS SES: Email rejected - {error_message}")
            elif error_code == 'MailFromDomainNotVerified':
                logger.error(f"AWS SES: Sender domain not verified - {self.config.sender_email}")
            elif error_code == 'ConfigurationSetDoesNotExist':
                logger.error(f"AWS SES: Configuration set error - {error_message}")
            elif error_code == 'AccountSendingPaused':
                logger.error("AWS SES: Account sending is paused. Check your SES account status.")
            else:
                logger.error(f"AWS SES Error ({error_code}): {error_message}")
            
            return False
        
        except EndpointConnectionError as e:
            logger.error(f"AWS SES: Could not connect to endpoint. Check AWS_REGION. Error: {e}")
            return False
        
        except Exception as e:
            logger.error(f"AWS SES unexpected error: {type(e).__name__}: {e}")
            return False
    
    async def _send_smtp(
        self,
        subject: str,
        html_content: str,
        text_content: str
    ) -> bool:
        """Send via SMTP."""
        if not all([self.config.smtp_host, self.config.smtp_username, self.config.smtp_password]):
            logger.error("SMTP configuration incomplete (host, username, password required)")
            return False
        
        try:
            # Build message
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = f"{self.config.sender_name} <{self.config.sender_email}>"
            msg['To'] = ', '.join(self.config.recipients)
            
            # Attach text and HTML versions
            part1 = MIMEText(text_content, 'plain', 'utf-8')
            part2 = MIMEText(html_content, 'html', 'utf-8')
            msg.attach(part1)
            msg.attach(part2)
            
            # Send via SMTP in thread pool (blocking operation)
            loop = asyncio.get_event_loop()
            
            def send_smtp_sync():
                if self.config.smtp_port == 465:
                    # SSL
                    with smtplib.SMTP_SSL(self.config.smtp_host, self.config.smtp_port) as server:
                        server.login(self.config.smtp_username, self.config.smtp_password)
                        server.sendmail(
                            self.config.sender_email,
                            self.config.recipients,
                            msg.as_string()
                        )
                else:
                    # TLS (port 587 typically)
                    with smtplib.SMTP(self.config.smtp_host, self.config.smtp_port) as server:
                        server.starttls()
                        server.login(self.config.smtp_username, self.config.smtp_password)
                        server.sendmail(
                            self.config.sender_email,
                            self.config.recipients,
                            msg.as_string()
                        )
            
            await loop.run_in_executor(_executor, send_smtp_sync)
            
            logger.info(f"Email sent via SMTP: {subject}")
            return True
            
        except smtplib.SMTPAuthenticationError:
            logger.error("SMTP authentication failed. Check username/password.")
            return False
        
        except smtplib.SMTPRecipientsRefused as e:
            logger.error(f"SMTP recipients refused: {e}")
            return False
        
        except smtplib.SMTPException as e:
            logger.error(f"SMTP error: {e}")
            return False
        
        except Exception as e:
            logger.error(f"SMTP unexpected error: {type(e).__name__}: {e}")
            return False
    
    def _build_html(
        self,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> str:
        """Build HTML email content."""
        # Severity color
        color_map = {
            AlertSeverity.INFO: "#2196F3",
            AlertSeverity.WARNING: "#FF9800",
            AlertSeverity.ERROR: "#F44336",
            AlertSeverity.CRITICAL: "#9C27B0"
        }
        color = color_map.get(severity, "#607D8B")
        
        data_rows = ""
        if data:
            for key, value in data.items():
                data_rows += f"""
                <tr>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;"><strong>{key}</strong></td>
                    <td style="padding: 8px; border-bottom: 1px solid #eee;">{value}</td>
                </tr>
                """
        
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1.0">
        </head>
        <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333; max-width: 600px; margin: 0 auto; padding: 20px;">
            <div style="background: {color}; padding: 20px; border-radius: 8px 8px 0 0;">
                <h1 style="color: white; margin: 0; font-size: 24px;">{title}</h1>
            </div>
            <div style="background: #f9f9f9; padding: 20px; border: 1px solid #ddd; border-top: none;">
                <p style="margin: 0 0 20px 0;">{message}</p>
                
                {f'''
                <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                    <tbody>
                        {data_rows}
                    </tbody>
                </table>
                ''' if data else ''}
            </div>
            <div style="background: #f0f0f0; padding: 15px; text-align: center; font-size: 12px; color: #666; border-radius: 0 0 8px 8px;">
                <p style="margin: 0;">SSI Shadow • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC</p>
            </div>
        </body>
        </html>
        """
    
    def _build_text(
        self,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> str:
        """Build plain text email content."""
        text = f"{title}\n{'=' * len(title)}\n\n{message}\n"
        
        if data:
            text += "\nDetails:\n"
            for key, value in data.items():
                text += f"  • {key}: {value}\n"
        
        text += f"\n---\nSSI Shadow • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
        
        return text
    
    async def test(self) -> Dict[str, Any]:
        """Test email configuration."""
        success = await self.send(
            title="Test Notification",
            message="This is a test email from SSI Shadow.",
            data={"test": "true", "provider": self.config.provider},
            severity=AlertSeverity.INFO
        )
        return {"success": success, "channel": "email", "provider": self.config.provider}
    
    async def close(self):
        await self.http_client.aclose()
        self._ses_client = None


# =============================================================================
# SMS CHANNEL
# =============================================================================

class SMSChannel(NotificationChannel):
    """SMS notification channel using Twilio."""
    
    def __init__(self, config: SMSConfig):
        self.config = config
        self.http_client = httpx.AsyncClient(timeout=10.0)
    
    async def send(
        self,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> bool:
        """Send an SMS notification."""
        if not self.config.is_active:
            return False
        
        if not self.config.phone_numbers:
            logger.warning("No SMS recipients configured")
            return False
        
        # Build SMS (max 160 chars for single segment)
        text = f"[SSI Shadow] {title}: {message}"
        if len(text) > 160:
            text = text[:157] + "..."
        
        success = True
        for phone in self.config.phone_numbers:
            if not await self._send_to_phone(phone, text):
                success = False
        
        return success
    
    async def _send_to_phone(self, phone: str, text: str) -> bool:
        """Send SMS to a single phone number via Twilio."""
        if self.config.provider != "twilio":
            logger.error(f"Unsupported SMS provider: {self.config.provider}")
            return False
        
        if not all([self.config.account_sid, self.config.auth_token, self.config.from_number]):
            logger.error("Twilio configuration incomplete")
            return False
        
        try:
            response = await self.http_client.post(
                f"https://api.twilio.com/2010-04-01/Accounts/{self.config.account_sid}/Messages.json",
                data={
                    "To": phone,
                    "From": self.config.from_number,
                    "Body": text
                },
                auth=(self.config.account_sid, self.config.auth_token)
            )
            
            if response.status_code == 201:
                logger.info(f"SMS sent to {phone}")
                return True
            else:
                logger.error(f"Twilio error: {response.status_code} - {response.text}")
                return False
                
        except Exception as e:
            logger.error(f"Twilio error: {e}")
            return False
    
    async def test(self) -> Dict[str, Any]:
        """Test SMS configuration."""
        # Only test if critical - SMS is expensive
        return {
            "success": True,
            "channel": "sms",
            "message": "SMS test skipped to avoid charges. Use send() to test."
        }
    
    async def close(self):
        await self.http_client.aclose()


# =============================================================================
# NOTIFICATION SERVICE (Aggregate)
# =============================================================================

class NotificationService:
    """
    Service for sending notifications across multiple channels.
    """
    
    def __init__(self):
        self.channels: Dict[str, NotificationChannel] = {}
    
    def configure_slack(self, config: SlackConfig):
        """Configure Slack channel."""
        self.channels["slack"] = SlackChannel(config)
    
    def configure_telegram(self, config: TelegramConfig):
        """Configure Telegram channel."""
        self.channels["telegram"] = TelegramChannel(config)
    
    def configure_email(self, config: EmailConfig):
        """Configure Email channel."""
        self.channels["email"] = EmailChannel(config)
    
    def configure_sms(self, config: SMSConfig):
        """Configure SMS channel."""
        self.channels["sms"] = SMSChannel(config)
    
    async def send(
        self,
        channels: List[str],
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> Dict[str, bool]:
        """Send notification to multiple channels."""
        results = {}
        
        for channel_name in channels:
            channel = self.channels.get(channel_name)
            if channel:
                try:
                    results[channel_name] = await channel.send(
                        title, message, data, severity
                    )
                except Exception as e:
                    logger.error(f"Error sending to {channel_name}: {e}")
                    results[channel_name] = False
            else:
                results[channel_name] = False
                logger.warning(f"Channel not configured: {channel_name}")
        
        return results
    
    async def send_all(
        self,
        title: str,
        message: str,
        data: Dict[str, Any] = None,
        severity: AlertSeverity = AlertSeverity.INFO
    ) -> Dict[str, bool]:
        """Send notification to all configured channels."""
        return await self.send(
            list(self.channels.keys()),
            title, message, data, severity
        )
    
    async def test_all(self) -> Dict[str, Dict]:
        """Test all configured channels."""
        results = {}
        for name, channel in self.channels.items():
            try:
                results[name] = await channel.test()
            except Exception as e:
                results[name] = {"success": False, "error": str(e)}
        return results
    
    async def close(self):
        """Close all channels."""
        for channel in self.channels.values():
            try:
                await channel.close()
            except Exception as e:
                logger.warning(f"Error closing channel: {e}")


# =============================================================================
# SINGLETON
# =============================================================================

_notification_service: Optional[NotificationService] = None


def get_notification_service() -> NotificationService:
    """Get or create the notification service."""
    global _notification_service
    if _notification_service is None:
        _notification_service = NotificationService()
    return _notification_service


async def init_notification_service(
    slack_config: SlackConfig = None,
    telegram_config: TelegramConfig = None,
    email_config: EmailConfig = None,
    sms_config: SMSConfig = None
) -> NotificationService:
    """Initialize the notification service with configurations."""
    global _notification_service
    
    _notification_service = NotificationService()
    
    if slack_config:
        _notification_service.configure_slack(slack_config)
    if telegram_config:
        _notification_service.configure_telegram(telegram_config)
    if email_config:
        _notification_service.configure_email(email_config)
    if sms_config:
        _notification_service.configure_sms(sms_config)
    
    return _notification_service


# =============================================================================
# CONVENIENCE FUNCTIONS
# =============================================================================

async def send_alert(
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.INFO,
    data: Dict[str, Any] = None,
    channels: List[str] = None
) -> Dict[str, bool]:
    """
    Convenience function to send an alert.
    Uses all configured channels if none specified.
    """
    service = get_notification_service()
    
    if channels:
        return await service.send(channels, title, message, data, severity)
    else:
        return await service.send_all(title, message, data, severity)
