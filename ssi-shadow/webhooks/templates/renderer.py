"""
S.S.I. SHADOW - Notification Templates
======================================
Templates for Slack, Telegram, and Email notifications.
"""

from datetime import datetime
from typing import Dict, Any, Optional
from jinja2 import Template


# =============================================================================
# TELEGRAM TEMPLATES
# =============================================================================

TELEGRAM_TEMPLATES = {
    "purchase": """
🎉 <b>New Purchase!</b>

<b>Order:</b> {{ order_id }}
<b>Amount:</b> {{ currency }}{{ value | round(2) }}
<b>Items:</b> {{ num_items }}

{% if customer_email %}
<b>Customer:</b> {{ customer_email }}
{% endif %}

<i>SSI Shadow • {{ timestamp }}</i>
""",

    "high_value_purchase": """
💎 <b>High Value Purchase!</b>

A high-value order has been placed!

<b>Order:</b> {{ order_id }}
<b>Amount:</b> {{ currency }}{{ value | round(2) }}
<b>Items:</b> {{ num_items }}

{% if ltv_tier %}
<b>Customer LTV Tier:</b> {{ ltv_tier }}
{% endif %}

<i>SSI Shadow • {{ timestamp }}</i>
""",

    "high_ltv_detected": """
⭐ <b>VIP Customer Detected</b>

A new high-value customer has been identified!

<b>LTV Tier:</b> {{ ltv_tier }}
<b>Predicted LTV:</b> ${{ ltv_90d | round(2) }}
{% if email_hash %}
<b>User Hash:</b> {{ email_hash[:8] }}...
{% endif %}

<i>SSI Shadow • {{ timestamp }}</i>
""",

    "churn_risk": """
⚠️ <b>Churn Risk Alert</b>

A customer has been flagged as high churn risk.

<b>Risk Level:</b> {{ churn_risk }}
<b>Probability:</b> {{ (churn_probability * 100) | round(1) }}%
<b>Last Active:</b> {{ last_active }}

<i>SSI Shadow • {{ timestamp }}</i>
""",

    "platform_error": """
🚨 <b>Platform Error</b>

An error occurred with the {{ platform }} API.

<b>Error Code:</b> {{ error_code }}
<b>Message:</b> {{ error_message }}
<b>Events Affected:</b> {{ events_affected }}

<i>SSI Shadow • {{ timestamp }}</i>
""",

    "daily_summary": """
📊 <b>Daily Summary</b>

Here's your daily performance summary:

<b>Events:</b> {{ events_total | default(0) | int | format_number }}
<b>Revenue:</b> ${{ revenue | default(0) | round(2) | format_number }}
<b>Conversion Rate:</b> {{ (conversion_rate * 100) | round(2) }}%

<b>Trust Score:</b>
• Allowed: {{ allowed_rate | round(1) }}%
• Blocked: {{ blocked_rate | round(1) }}%

<b>Platforms:</b>
• Meta: {{ meta_events }} events
• TikTok: {{ tiktok_events }} events
• Google: {{ google_events }} events

<i>SSI Shadow • {{ date }}</i>
""",

    "alert": """
{% if severity == 'critical' %}🚨{% elif severity == 'error' %}❌{% elif severity == 'warning' %}⚠️{% else %}ℹ️{% endif %} <b>{{ title }}</b>

{{ message }}

{% if details %}
<b>Details:</b>
{% for key, value in details.items() %}
• <b>{{ key }}:</b> {{ value }}
{% endfor %}
{% endif %}

<i>SSI Shadow • {{ timestamp }}</i>
"""
}


# =============================================================================
# SLACK TEMPLATES (Block Kit JSON)
# =============================================================================

def slack_purchase_blocks(data: Dict[str, Any]) -> list:
    """Generate Slack blocks for purchase notification."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "🎉 New Purchase!",
                "emoji": True
            }
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Order ID:*\n{data.get('order_id', 'N/A')}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Amount:*\n{data.get('currency', '$')}{data.get('value', 0):.2f}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Items:*\n{data.get('num_items', 1)}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Platform:*\n{data.get('platform', 'Web')}"
                }
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"SSI Shadow • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                }
            ]
        }
    ]
    
    return blocks


def slack_alert_blocks(data: Dict[str, Any]) -> list:
    """Generate Slack blocks for alert notification."""
    severity = data.get('severity', 'info')
    emoji_map = {
        'info': ':information_source:',
        'warning': ':warning:',
        'error': ':x:',
        'critical': ':rotating_light:'
    }
    
    color_map = {
        'info': '#2196F3',
        'warning': '#FF9800',
        'error': '#F44336',
        'critical': '#9C27B0'
    }
    
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"{emoji_map.get(severity, ':bell:')} {data.get('title', 'Alert')}",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": data.get('message', '')
            }
        }
    ]
    
    # Add details if present
    details = data.get('details', {})
    if details:
        fields = []
        for key, value in list(details.items())[:6]:
            fields.append({
                "type": "mrkdwn",
                "text": f"*{key}:*\n{value}"
            })
        
        blocks.append({
            "type": "section",
            "fields": fields
        })
    
    # Add actions
    blocks.append({
        "type": "actions",
        "elements": [
            {
                "type": "button",
                "text": {
                    "type": "plain_text",
                    "text": "View Dashboard"
                },
                "url": data.get('dashboard_url', 'https://dashboard.ssi-shadow.io'),
                "style": "primary"
            }
        ]
    })
    
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


def slack_daily_summary_blocks(data: Dict[str, Any]) -> list:
    """Generate Slack blocks for daily summary."""
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": "📊 Daily Summary",
                "emoji": True
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"Here's your performance summary for *{data.get('date', 'today')}*"
            }
        },
        {
            "type": "divider"
        },
        {
            "type": "section",
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"*Events*\n{data.get('events_total', 0):,}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Revenue*\n${data.get('revenue', 0):,.2f}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Conversion Rate*\n{data.get('conversion_rate', 0) * 100:.2f}%"
                },
                {
                    "type": "mrkdwn",
                    "text": f"*Avg Order Value*\n${data.get('avg_order_value', 0):.2f}"
                }
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Trust Score*"
            },
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"✅ Allowed: {data.get('allowed_rate', 0):.1f}%"
                },
                {
                    "type": "mrkdwn",
                    "text": f"🚫 Blocked: {data.get('blocked_rate', 0):.1f}%"
                }
            ]
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "*Platform Events*"
            },
            "fields": [
                {
                    "type": "mrkdwn",
                    "text": f"Meta: {data.get('meta_events', 0):,}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"TikTok: {data.get('tiktok_events', 0):,}"
                },
                {
                    "type": "mrkdwn",
                    "text": f"Google: {data.get('google_events', 0):,}"
                }
            ]
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {
                        "type": "plain_text",
                        "text": "View Full Report"
                    },
                    "url": data.get('report_url', 'https://dashboard.ssi-shadow.io'),
                    "style": "primary"
                }
            ]
        },
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": f"SSI Shadow • {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC"
                }
            ]
        }
    ]
    
    return blocks


# =============================================================================
# EMAIL TEMPLATES
# =============================================================================

EMAIL_TEMPLATES = {
    "purchase": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #4CAF50; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background: #f9f9f9; }
        .detail { margin: 10px 0; }
        .label { font-weight: bold; }
        .footer { text-align: center; padding: 20px; font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🎉 New Purchase!</h1>
        </div>
        <div class="content">
            <div class="detail">
                <span class="label">Order ID:</span> {{ order_id }}
            </div>
            <div class="detail">
                <span class="label">Amount:</span> {{ currency }}{{ value | round(2) }}
            </div>
            <div class="detail">
                <span class="label">Items:</span> {{ num_items }}
            </div>
            {% if customer_email %}
            <div class="detail">
                <span class="label">Customer:</span> {{ customer_email }}
            </div>
            {% endif %}
        </div>
        <div class="footer">
            SSI Shadow • {{ timestamp }}
        </div>
    </div>
</body>
</html>
""",

    "daily_summary": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background: #2196F3; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background: #f9f9f9; }
        .stats { display: flex; flex-wrap: wrap; }
        .stat { width: 50%; padding: 10px; box-sizing: border-box; }
        .stat-value { font-size: 24px; font-weight: bold; color: #2196F3; }
        .stat-label { font-size: 12px; color: #666; }
        .section { margin: 20px 0; }
        .section-title { font-size: 16px; font-weight: bold; border-bottom: 1px solid #ddd; padding-bottom: 5px; }
        .footer { text-align: center; padding: 20px; font-size: 12px; color: #666; }
        .btn { display: inline-block; padding: 10px 20px; background: #2196F3; color: white; text-decoration: none; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Daily Summary</h1>
            <p>{{ date }}</p>
        </div>
        <div class="content">
            <div class="stats">
                <div class="stat">
                    <div class="stat-value">{{ events_total | int | format_number }}</div>
                    <div class="stat-label">Events</div>
                </div>
                <div class="stat">
                    <div class="stat-value">${{ revenue | round(2) | format_number }}</div>
                    <div class="stat-label">Revenue</div>
                </div>
                <div class="stat">
                    <div class="stat-value">{{ (conversion_rate * 100) | round(2) }}%</div>
                    <div class="stat-label">Conversion Rate</div>
                </div>
                <div class="stat">
                    <div class="stat-value">${{ avg_order_value | round(2) }}</div>
                    <div class="stat-label">Avg Order Value</div>
                </div>
            </div>
            
            <div class="section">
                <div class="section-title">Trust Score</div>
                <p>✅ Allowed: {{ allowed_rate | round(1) }}%</p>
                <p>🚫 Blocked: {{ blocked_rate | round(1) }}%</p>
            </div>
            
            <div class="section">
                <div class="section-title">Platform Events</div>
                <p>Meta: {{ meta_events | format_number }}</p>
                <p>TikTok: {{ tiktok_events | format_number }}</p>
                <p>Google: {{ google_events | format_number }}</p>
            </div>
            
            <p style="text-align: center; margin-top: 20px;">
                <a href="{{ report_url }}" class="btn">View Full Report</a>
            </p>
        </div>
        <div class="footer">
            SSI Shadow<br>
            <a href="{{ unsubscribe_url }}">Unsubscribe</a>
        </div>
    </div>
</body>
</html>
""",

    "alert": """
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { padding: 20px; text-align: center; }
        .header.info { background: #2196F3; color: white; }
        .header.warning { background: #FF9800; color: white; }
        .header.error { background: #F44336; color: white; }
        .header.critical { background: #9C27B0; color: white; }
        .content { padding: 20px; background: #f9f9f9; }
        .detail { margin: 10px 0; padding: 10px; background: white; border-left: 4px solid #ddd; }
        .footer { text-align: center; padding: 20px; font-size: 12px; color: #666; }
        .btn { display: inline-block; padding: 10px 20px; background: #2196F3; color: white; text-decoration: none; border-radius: 4px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header {{ severity }}">
            <h1>{{ title }}</h1>
        </div>
        <div class="content">
            <p>{{ message }}</p>
            
            {% if details %}
            <div class="section">
                {% for key, value in details.items() %}
                <div class="detail">
                    <strong>{{ key }}:</strong> {{ value }}
                </div>
                {% endfor %}
            </div>
            {% endif %}
            
            <p style="text-align: center; margin-top: 20px;">
                <a href="{{ dashboard_url }}" class="btn">View Dashboard</a>
            </p>
        </div>
        <div class="footer">
            SSI Shadow • {{ timestamp }}
        </div>
    </div>
</body>
</html>
"""
}


# =============================================================================
# TEMPLATE RENDERER
# =============================================================================

class TemplateRenderer:
    """Render notification templates."""
    
    def __init__(self):
        # Add custom Jinja2 filters
        self.filters = {
            'format_number': lambda x: f"{x:,}" if isinstance(x, (int, float)) else x,
            'round': lambda x, n=2: round(x, n) if isinstance(x, (int, float)) else x
        }
    
    def render_telegram(self, template_name: str, data: Dict[str, Any]) -> str:
        """Render a Telegram template."""
        template_str = TELEGRAM_TEMPLATES.get(template_name)
        if not template_str:
            raise ValueError(f"Template not found: {template_name}")
        
        # Add timestamp if not present
        if 'timestamp' not in data:
            data['timestamp'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        
        template = Template(template_str)
        for name, func in self.filters.items():
            template.environment.filters[name] = func
        
        return template.render(**data)
    
    def render_slack_blocks(self, template_name: str, data: Dict[str, Any]) -> list:
        """Render Slack blocks."""
        if template_name == 'purchase':
            return slack_purchase_blocks(data)
        elif template_name == 'alert':
            return slack_alert_blocks(data)
        elif template_name == 'daily_summary':
            return slack_daily_summary_blocks(data)
        else:
            # Generic blocks
            return slack_alert_blocks({
                'title': data.get('title', 'Notification'),
                'message': data.get('message', ''),
                'details': data,
                'severity': 'info'
            })
    
    def render_email(self, template_name: str, data: Dict[str, Any]) -> str:
        """Render an email template."""
        template_str = EMAIL_TEMPLATES.get(template_name)
        if not template_str:
            # Fall back to alert template
            template_str = EMAIL_TEMPLATES['alert']
        
        # Add defaults
        if 'timestamp' not in data:
            data['timestamp'] = datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
        if 'dashboard_url' not in data:
            data['dashboard_url'] = 'https://dashboard.ssi-shadow.io'
        if 'unsubscribe_url' not in data:
            data['unsubscribe_url'] = '#'
        
        template = Template(template_str)
        for name, func in self.filters.items():
            template.environment.filters[name] = func
        
        return template.render(**data)


# Singleton
_renderer: Optional[TemplateRenderer] = None


def get_template_renderer() -> TemplateRenderer:
    """Get the template renderer."""
    global _renderer
    if _renderer is None:
        _renderer = TemplateRenderer()
    return _renderer
