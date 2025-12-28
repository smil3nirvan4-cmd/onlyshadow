"""
S.S.I. SHADOW - Locust Load Testing Suite (C10)
==============================================

Testes de carga simulando Black Friday com Locust.
Valida que o sistema aguenta o pico de tráfego esperado.

Features:
- Simulação de tráfego realista
- Rampa de usuários configurável
- Múltiplos cenários (normal, pico, Black Friday)
- Métricas detalhadas
- Relatórios HTML

Uso:
    # Modo web UI
    locust -f tests/load/locustfile.py --host=http://localhost:8787
    
    # Modo headless
    locust -f tests/load/locustfile.py --host=http://localhost:8787 \
           --users 1000 --spawn-rate 50 --run-time 10m --headless
    
    # Black Friday simulation
    python -m tests.load.locustfile --scenario=black_friday

Cenários:
    - normal: 100 users, 10/s spawn
    - high: 500 users, 50/s spawn
    - black_friday: 2000 users, 100/s spawn, burst patterns

Targets:
    - P95 latency < 200ms
    - Error rate < 0.1%
    - Throughput > 1000 req/s

Author: SSI Shadow Team
Version: 1.0.0
"""

import os
import sys
import json
import random
import time
import uuid
import hashlib
from datetime import datetime
from typing import Dict, Any, List, Optional

# Locust
try:
    from locust import HttpUser, task, between, events, tag
    from locust.runners import MasterRunner, WorkerRunner
    from locust.env import Environment
    LOCUST_AVAILABLE = True
except ImportError:
    LOCUST_AVAILABLE = False
    # Stub classes for import
    class HttpUser:
        pass
    def task(weight=1):
        def decorator(func):
            return func
        return decorator
    def between(min_wait, max_wait):
        return lambda: random.uniform(min_wait, max_wait)
    def tag(*tags):
        def decorator(func):
            return func
        return decorator


# =============================================================================
# CONFIGURATION
# =============================================================================

class LoadTestConfig:
    """Load test configuration."""
    
    # Target host
    HOST = os.getenv('LOAD_TEST_HOST', 'http://localhost:8787')
    
    # API endpoints
    ENDPOINTS = {
        'track': '/api/track',
        'health': '/health',
        'pixel': '/api/pixel.js',
        'conversion': '/api/conversion',
        'webhook_meta': '/api/webhooks/meta',
        'webhook_google': '/api/webhooks/google',
        'webhook_tiktok': '/api/webhooks/tiktok',
    }
    
    # Scenarios
    SCENARIOS = {
        'normal': {
            'users': 100,
            'spawn_rate': 10,
            'run_time': '5m',
        },
        'high': {
            'users': 500,
            'spawn_rate': 50,
            'run_time': '10m',
        },
        'black_friday': {
            'users': 2000,
            'spawn_rate': 100,
            'run_time': '30m',
        },
        'spike': {
            'users': 5000,
            'spawn_rate': 500,
            'run_time': '5m',
        },
    }
    
    # SLA targets
    SLA = {
        'p95_latency_ms': 200,
        'p99_latency_ms': 500,
        'error_rate_pct': 0.1,
        'min_throughput_rps': 1000,
    }


config = LoadTestConfig()


# =============================================================================
# TEST DATA GENERATORS
# =============================================================================

class TestDataGenerator:
    """Generates realistic test data."""
    
    # Product catalog
    PRODUCTS = [
        {'id': 'SKU001', 'name': 'Tênis Runner Pro', 'price': 299.90, 'category': 'shoes'},
        {'id': 'SKU002', 'name': 'Camiseta Dry Fit', 'price': 89.90, 'category': 'apparel'},
        {'id': 'SKU003', 'name': 'Shorts Running', 'price': 129.90, 'category': 'apparel'},
        {'id': 'SKU004', 'name': 'Meias Performance', 'price': 39.90, 'category': 'accessories'},
        {'id': 'SKU005', 'name': 'Relógio GPS', 'price': 899.90, 'category': 'electronics'},
    ]
    
    # Event types with weights
    EVENT_TYPES = [
        ('PageView', 50),
        ('ViewContent', 20),
        ('AddToCart', 15),
        ('InitiateCheckout', 8),
        ('AddPaymentInfo', 4),
        ('Purchase', 3),
    ]
    
    # User agent strings
    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0',
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15',
        'Mozilla/5.0 (Linux; Android 14) AppleWebKit/537.36 Chrome/120.0.0.0',
    ]
    
    # UTM sources
    UTM_SOURCES = ['facebook', 'google', 'tiktok', 'instagram', 'email', 'organic']
    UTM_MEDIUMS = ['cpc', 'cpm', 'social', 'email', 'organic']
    
    @classmethod
    def generate_event_name(cls) -> str:
        """Generate weighted random event name."""
        total = sum(w for _, w in cls.EVENT_TYPES)
        r = random.randint(1, total)
        
        cumulative = 0
        for event, weight in cls.EVENT_TYPES:
            cumulative += weight
            if r <= cumulative:
                return event
        
        return 'PageView'
    
    @classmethod
    def generate_user_id(cls) -> str:
        """Generate a user ID (some returning, some new)."""
        # 30% returning users (from pool)
        if random.random() < 0.3:
            return f"user_{random.randint(1, 10000)}"
        # 70% new users
        return f"user_{uuid.uuid4().hex[:12]}"
    
    @classmethod
    def generate_session_id(cls) -> str:
        """Generate session ID."""
        return f"sess_{uuid.uuid4().hex[:16]}"
    
    @classmethod
    def generate_fbclid(cls) -> str:
        """Generate fake Facebook click ID."""
        return f"IwAR{uuid.uuid4().hex[:32]}"
    
    @classmethod
    def generate_gclid(cls) -> str:
        """Generate fake Google click ID."""
        return f"Cj0KCQiA{uuid.uuid4().hex[:24]}"
    
    @classmethod
    def generate_product(cls) -> Dict[str, Any]:
        """Get random product."""
        return random.choice(cls.PRODUCTS)
    
    @classmethod
    def generate_track_event(cls) -> Dict[str, Any]:
        """Generate a complete tracking event."""
        event_name = cls.generate_event_name()
        product = cls.generate_product()
        
        event = {
            'event_name': event_name,
            'event_id': str(uuid.uuid4()),
            'event_time': int(time.time()),
            'user_id': cls.generate_user_id(),
            'session_id': cls.generate_session_id(),
            'page_url': f"https://example.com/product/{product['id']}",
            'page_title': product['name'],
            'user_agent': random.choice(cls.USER_AGENTS),
            'ip_address': f"{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}.{random.randint(1,255)}",
            'utm_source': random.choice(cls.UTM_SOURCES),
            'utm_medium': random.choice(cls.UTM_MEDIUMS),
            'utm_campaign': f"campaign_{random.randint(1, 100)}",
        }
        
        # Add product data for relevant events
        if event_name in ['ViewContent', 'AddToCart', 'InitiateCheckout', 'Purchase']:
            event['content_type'] = 'product'
            event['content_ids'] = [product['id']]
            event['content_name'] = product['name']
            event['content_category'] = product['category']
            event['value'] = product['price']
            event['currency'] = 'BRL'
        
        # Add fbclid/gclid randomly
        if random.random() < 0.4:
            event['fbclid'] = cls.generate_fbclid()
        elif random.random() < 0.3:
            event['gclid'] = cls.generate_gclid()
        
        # Purchase specific data
        if event_name == 'Purchase':
            event['num_items'] = random.randint(1, 5)
            event['value'] = product['price'] * event['num_items']
            event['order_id'] = f"ORDER-{uuid.uuid4().hex[:8].upper()}"
        
        return event
    
    @classmethod
    def generate_meta_webhook(cls) -> Dict[str, Any]:
        """Generate Meta webhook payload."""
        event = cls.generate_track_event()
        
        return {
            'object': 'page',
            'entry': [{
                'id': '123456789',
                'time': int(time.time() * 1000),
                'messaging': [{
                    'sender': {'id': event['user_id']},
                    'recipient': {'id': '987654321'},
                    'timestamp': int(time.time() * 1000),
                    'message': {
                        'mid': f"m_{uuid.uuid4().hex}",
                        'text': 'Test message'
                    }
                }]
            }]
        }
    
    @classmethod
    def generate_google_webhook(cls) -> Dict[str, Any]:
        """Generate Google webhook payload."""
        event = cls.generate_track_event()
        
        return {
            'client_id': event['user_id'],
            'events': [{
                'name': event['event_name'].lower(),
                'params': {
                    'session_id': event['session_id'],
                    'engagement_time_msec': random.randint(1000, 60000),
                }
            }]
        }


# =============================================================================
# LOCUST USER CLASSES
# =============================================================================

if LOCUST_AVAILABLE:
    
    class SSIShadowUser(HttpUser):
        """
        Base user class for SSI Shadow load testing.
        
        Simulates realistic user behavior with weighted event distribution.
        """
        
        # Wait time between requests (simulates real user behavior)
        wait_time = between(0.5, 2.0)
        
        # Host (overridden by command line)
        host = config.HOST
        
        def on_start(self):
            """Initialize user session."""
            self.user_id = TestDataGenerator.generate_user_id()
            self.session_id = TestDataGenerator.generate_session_id()
            self.events_sent = 0
        
        @task(50)
        @tag('tracking', 'pageview')
        def track_pageview(self):
            """Track PageView event (most common)."""
            event = TestDataGenerator.generate_track_event()
            event['event_name'] = 'PageView'
            event['user_id'] = self.user_id
            event['session_id'] = self.session_id
            
            with self.client.post(
                config.ENDPOINTS['track'],
                json=event,
                catch_response=True
            ) as response:
                if response.status_code == 200:
                    response.success()
                    self.events_sent += 1
                else:
                    response.failure(f"Status {response.status_code}")
        
        @task(20)
        @tag('tracking', 'view_content')
        def track_view_content(self):
            """Track ViewContent event."""
            event = TestDataGenerator.generate_track_event()
            event['event_name'] = 'ViewContent'
            event['user_id'] = self.user_id
            event['session_id'] = self.session_id
            
            self.client.post(
                config.ENDPOINTS['track'],
                json=event,
                name='/api/track [ViewContent]'
            )
            self.events_sent += 1
        
        @task(15)
        @tag('tracking', 'add_to_cart')
        def track_add_to_cart(self):
            """Track AddToCart event."""
            event = TestDataGenerator.generate_track_event()
            event['event_name'] = 'AddToCart'
            event['user_id'] = self.user_id
            event['session_id'] = self.session_id
            
            self.client.post(
                config.ENDPOINTS['track'],
                json=event,
                name='/api/track [AddToCart]'
            )
            self.events_sent += 1
        
        @task(8)
        @tag('tracking', 'checkout')
        def track_checkout(self):
            """Track InitiateCheckout event."""
            event = TestDataGenerator.generate_track_event()
            event['event_name'] = 'InitiateCheckout'
            event['user_id'] = self.user_id
            event['session_id'] = self.session_id
            
            self.client.post(
                config.ENDPOINTS['track'],
                json=event,
                name='/api/track [InitiateCheckout]'
            )
            self.events_sent += 1
        
        @task(3)
        @tag('tracking', 'purchase')
        def track_purchase(self):
            """Track Purchase event (conversion)."""
            event = TestDataGenerator.generate_track_event()
            event['event_name'] = 'Purchase'
            event['user_id'] = self.user_id
            event['session_id'] = self.session_id
            event['order_id'] = f"ORDER-{uuid.uuid4().hex[:8].upper()}"
            
            self.client.post(
                config.ENDPOINTS['track'],
                json=event,
                name='/api/track [Purchase]'
            )
            self.events_sent += 1
        
        @task(5)
        @tag('sdk', 'pixel')
        def load_pixel_js(self):
            """Load pixel.js SDK."""
            self.client.get(
                config.ENDPOINTS['pixel'],
                name='/api/pixel.js'
            )
        
        @task(2)
        @tag('health')
        def check_health(self):
            """Check health endpoint."""
            self.client.get(config.ENDPOINTS['health'])
    
    
    class WebhookUser(HttpUser):
        """
        Simulates webhook traffic from ad platforms.
        """
        
        wait_time = between(0.1, 0.5)  # Higher frequency
        host = config.HOST
        
        @task(40)
        @tag('webhook', 'meta')
        def meta_webhook(self):
            """Simulate Meta webhook."""
            payload = TestDataGenerator.generate_meta_webhook()
            
            self.client.post(
                config.ENDPOINTS['webhook_meta'],
                json=payload,
                headers={'X-Hub-Signature-256': 'sha256=test'},
                name='/api/webhooks/meta'
            )
        
        @task(30)
        @tag('webhook', 'google')
        def google_webhook(self):
            """Simulate Google webhook."""
            payload = TestDataGenerator.generate_google_webhook()
            
            self.client.post(
                config.ENDPOINTS['webhook_google'],
                json=payload,
                name='/api/webhooks/google'
            )
        
        @task(30)
        @tag('webhook', 'tiktok')
        def tiktok_webhook(self):
            """Simulate TikTok webhook."""
            event = TestDataGenerator.generate_track_event()
            
            self.client.post(
                config.ENDPOINTS['webhook_tiktok'],
                json={'event': event},
                name='/api/webhooks/tiktok'
            )
    
    
    class BlackFridayUser(HttpUser):
        """
        Aggressive user simulating Black Friday traffic patterns.
        
        - Faster requests
        - More purchases
        - Burst behavior
        """
        
        wait_time = between(0.1, 0.5)  # Much faster
        host = config.HOST
        
        @task(30)
        @tag('tracking', 'black_friday')
        def rapid_pageviews(self):
            """Rapid-fire pageviews."""
            for _ in range(random.randint(1, 5)):
                event = TestDataGenerator.generate_track_event()
                event['event_name'] = 'PageView'
                
                self.client.post(
                    config.ENDPOINTS['track'],
                    json=event,
                    name='/api/track [BF-PageView]'
                )
        
        @task(15)
        @tag('tracking', 'black_friday')
        def add_multiple_to_cart(self):
            """Add multiple items to cart."""
            for _ in range(random.randint(1, 3)):
                event = TestDataGenerator.generate_track_event()
                event['event_name'] = 'AddToCart'
                
                self.client.post(
                    config.ENDPOINTS['track'],
                    json=event,
                    name='/api/track [BF-AddToCart]'
                )
        
        @task(10)
        @tag('tracking', 'black_friday', 'purchase')
        def black_friday_purchase(self):
            """Black Friday purchase (higher conversion)."""
            event = TestDataGenerator.generate_track_event()
            event['event_name'] = 'Purchase'
            event['num_items'] = random.randint(2, 10)
            event['value'] = random.uniform(100, 2000)
            
            self.client.post(
                config.ENDPOINTS['track'],
                json=event,
                name='/api/track [BF-Purchase]'
            )


# =============================================================================
# EVENT HOOKS
# =============================================================================

if LOCUST_AVAILABLE:
    
    @events.test_start.add_listener
    def on_test_start(environment, **kwargs):
        """Called when test starts."""
        print("\n" + "=" * 60)
        print("🚀 SSI Shadow Load Test Started")
        print(f"   Host: {environment.host}")
        print(f"   Users: {environment.runner.target_user_count if environment.runner else 'N/A'}")
        print("=" * 60 + "\n")
    
    @events.test_stop.add_listener
    def on_test_stop(environment, **kwargs):
        """Called when test stops."""
        print("\n" + "=" * 60)
        print("✅ SSI Shadow Load Test Completed")
        
        if environment.stats:
            total = environment.stats.total
            print(f"\n📊 Results Summary:")
            print(f"   Total Requests: {total.num_requests}")
            print(f"   Failed Requests: {total.num_failures}")
            print(f"   Error Rate: {total.fail_ratio * 100:.2f}%")
            print(f"   Avg Response Time: {total.avg_response_time:.2f}ms")
            print(f"   P95 Response Time: {total.get_response_time_percentile(0.95):.2f}ms")
            print(f"   P99 Response Time: {total.get_response_time_percentile(0.99):.2f}ms")
            print(f"   Requests/sec: {total.current_rps:.2f}")
            
            # SLA check
            print(f"\n🎯 SLA Check:")
            p95 = total.get_response_time_percentile(0.95)
            p99 = total.get_response_time_percentile(0.99)
            error_rate = total.fail_ratio * 100
            
            sla_passed = True
            
            if p95 > config.SLA['p95_latency_ms']:
                print(f"   ❌ P95 Latency: {p95:.0f}ms > {config.SLA['p95_latency_ms']}ms")
                sla_passed = False
            else:
                print(f"   ✅ P95 Latency: {p95:.0f}ms < {config.SLA['p95_latency_ms']}ms")
            
            if p99 > config.SLA['p99_latency_ms']:
                print(f"   ❌ P99 Latency: {p99:.0f}ms > {config.SLA['p99_latency_ms']}ms")
                sla_passed = False
            else:
                print(f"   ✅ P99 Latency: {p99:.0f}ms < {config.SLA['p99_latency_ms']}ms")
            
            if error_rate > config.SLA['error_rate_pct']:
                print(f"   ❌ Error Rate: {error_rate:.2f}% > {config.SLA['error_rate_pct']}%")
                sla_passed = False
            else:
                print(f"   ✅ Error Rate: {error_rate:.2f}% < {config.SLA['error_rate_pct']}%")
            
            print(f"\n{'🎉 ALL SLAs PASSED!' if sla_passed else '⚠️ SOME SLAs FAILED!'}")
        
        print("=" * 60 + "\n")
    
    @events.request.add_listener
    def on_request(request_type, name, response_time, response_length, response, context, exception, **kwargs):
        """Called on each request."""
        # Log slow requests
        if response_time > 1000:
            print(f"⚠️ Slow request: {name} - {response_time:.0f}ms")


# =============================================================================
# CLI RUNNER
# =============================================================================

def run_scenario(scenario: str, host: str = None):
    """
    Run a predefined scenario programmatically.
    
    Args:
        scenario: Scenario name (normal, high, black_friday, spike)
        host: Target host URL
    """
    if not LOCUST_AVAILABLE:
        print("❌ Locust not installed. Run: pip install locust")
        return
    
    if scenario not in config.SCENARIOS:
        print(f"❌ Unknown scenario: {scenario}")
        print(f"   Available: {list(config.SCENARIOS.keys())}")
        return
    
    sc = config.SCENARIOS[scenario]
    host = host or config.HOST
    
    print(f"\n🏃 Running scenario: {scenario}")
    print(f"   Users: {sc['users']}")
    print(f"   Spawn Rate: {sc['spawn_rate']}/s")
    print(f"   Duration: {sc['run_time']}")
    print(f"   Host: {host}\n")
    
    # Build command
    import subprocess
    
    cmd = [
        'locust',
        '-f', __file__,
        '--host', host,
        '--users', str(sc['users']),
        '--spawn-rate', str(sc['spawn_rate']),
        '--run-time', sc['run_time'],
        '--headless',
        '--html', f'report_{scenario}_{datetime.now().strftime("%Y%m%d_%H%M%S")}.html',
    ]
    
    # Add Black Friday user class for that scenario
    if scenario == 'black_friday':
        cmd.extend(['--class-picker'])
    
    subprocess.run(cmd)


def main():
    """CLI entry point."""
    import argparse
    
    parser = argparse.ArgumentParser(description='SSI Shadow Load Testing')
    parser.add_argument('--scenario', '-s', default='normal',
                       help='Scenario to run (normal, high, black_friday, spike)')
    parser.add_argument('--host', '-H', default=config.HOST,
                       help='Target host URL')
    parser.add_argument('--list', '-l', action='store_true',
                       help='List available scenarios')
    
    args = parser.parse_args()
    
    if args.list:
        print("\n📋 Available Scenarios:")
        for name, params in config.SCENARIOS.items():
            print(f"\n   {name}:")
            for key, value in params.items():
                print(f"      {key}: {value}")
        return
    
    run_scenario(args.scenario, args.host)


if __name__ == '__main__':
    main()
