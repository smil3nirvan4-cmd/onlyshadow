/**
 * S.S.I. SHADOW - Load Tests (k6)
 * Performance and load testing for the Worker Gateway
 * 
 * Run with: k6 run tests/load/worker-load.js
 * 
 * Targets:
 * - 1000 req/s sustained
 * - Latency p99 < 300ms
 * - Error rate < 0.1%
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { randomString, randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.4.0/index.js';

// =============================================================================
// CUSTOM METRICS
// =============================================================================

const errorRate = new Rate('errors');
const successRate = new Rate('success');
const eventsProcessed = new Counter('events_processed');
const trustScoreLatency = new Trend('trust_score_latency');
const platformDispatchLatency = new Trend('platform_dispatch_latency');

// =============================================================================
// CONFIGURATION
// =============================================================================

export const options = {
  // Test stages
  stages: [
    // Ramp up
    { duration: '30s', target: 100 },   // Ramp up to 100 VUs
    { duration: '1m', target: 500 },    // Ramp up to 500 VUs
    { duration: '2m', target: 1000 },   // Ramp up to 1000 VUs (target)
    
    // Sustained load
    { duration: '5m', target: 1000 },   // Hold at 1000 VUs for 5 minutes
    
    // Spike test
    { duration: '30s', target: 2000 },  // Spike to 2000 VUs
    { duration: '1m', target: 2000 },   // Hold spike
    { duration: '30s', target: 1000 },  // Back to normal
    
    // Ramp down
    { duration: '1m', target: 0 },      // Ramp down
  ],
  
  // Thresholds
  thresholds: {
    // HTTP errors should be less than 0.1%
    'http_req_failed': ['rate<0.001'],
    
    // Response time should be < 300ms for 99th percentile
    'http_req_duration': ['p(99)<300'],
    
    // Custom error rate
    'errors': ['rate<0.001'],
    
    // Trust score calculation should be fast
    'trust_score_latency': ['p(95)<50'],
    
    // Platform dispatch should complete within SLA
    'platform_dispatch_latency': ['p(95)<200'],
  },
  
  // Tags
  tags: {
    test_type: 'load',
    environment: __ENV.ENVIRONMENT || 'staging',
  },
};

// =============================================================================
// TEST DATA GENERATORS
// =============================================================================

const BASE_URL = __ENV.BASE_URL || 'https://ssi-shadow.example.workers.dev';

function generatePageViewEvent() {
  return {
    event_name: 'PageView',
    event_id: `evt_${randomString(16)}`,
    ssi_id: `ssi_${randomString(16)}`,
    timestamp: Date.now(),
    url: `https://example.com/product/${randomIntBetween(1, 1000)}`,
    referrer: 'https://google.com',
    user_agent: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0',
    scroll_depth: randomIntBetween(0, 100),
    time_on_page: randomIntBetween(1000, 60000),
  };
}

function generatePurchaseEvent() {
  return {
    event_name: 'Purchase',
    event_id: `evt_${randomString(16)}`,
    ssi_id: `ssi_${randomString(16)}`,
    timestamp: Date.now(),
    url: 'https://example.com/checkout/success',
    email: `user${randomIntBetween(1, 10000)}@example.com`,
    phone: `+55119${randomIntBetween(10000000, 99999999)}`,
    value: randomIntBetween(50, 5000) + randomIntBetween(0, 99) / 100,
    currency: 'BRL',
    content_ids: [`SKU-${randomIntBetween(1, 100)}`],
    order_id: `ORD-${randomString(10)}`,
    num_items: randomIntBetween(1, 5),
  };
}

function generateLeadEvent() {
  return {
    event_name: 'Lead',
    event_id: `evt_${randomString(16)}`,
    ssi_id: `ssi_${randomString(16)}`,
    timestamp: Date.now(),
    url: 'https://example.com/landing-page',
    email: `lead${randomIntBetween(1, 10000)}@example.com`,
    phone: `+55118${randomIntBetween(10000000, 99999999)}`,
    first_name: 'Test',
    last_name: 'User',
  };
}

function generateRandomEvent() {
  const rand = Math.random();
  if (rand < 0.7) {
    return generatePageViewEvent();  // 70% PageView
  } else if (rand < 0.9) {
    return generateLeadEvent();       // 20% Lead
  } else {
    return generatePurchaseEvent();   // 10% Purchase
  }
}

// =============================================================================
// REQUEST HELPERS
// =============================================================================

const headers = {
  'Content-Type': 'application/json',
  'User-Agent': 'k6-load-test',
};

function sendEvent(event) {
  const startTime = Date.now();
  
  const response = http.post(
    `${BASE_URL}/api/collect`,
    JSON.stringify(event),
    { headers, tags: { event_type: event.event_name } }
  );
  
  const duration = Date.now() - startTime;
  
  // Track metrics
  const success = response.status === 200 || response.status === 202;
  successRate.add(success);
  errorRate.add(!success);
  
  if (success) {
    eventsProcessed.add(1);
  }
  
  // Parse response for detailed metrics
  try {
    const body = JSON.parse(response.body);
    if (body.trust_score_ms) {
      trustScoreLatency.add(body.trust_score_ms);
    }
    if (body.dispatch_ms) {
      platformDispatchLatency.add(body.dispatch_ms);
    }
  } catch (e) {
    // Ignore parse errors
  }
  
  return { response, duration, success };
}

// =============================================================================
// TEST SCENARIOS
// =============================================================================

export default function () {
  group('Event Collection', function () {
    // Send random event
    const event = generateRandomEvent();
    const { response, success } = sendEvent(event);
    
    check(response, {
      'status is 200 or 202': (r) => r.status === 200 || r.status === 202,
      'response time < 300ms': (r) => r.timings.duration < 300,
      'has event_id in response': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.event_id !== undefined;
        } catch {
          return false;
        }
      },
    });
    
    // Small sleep to avoid overwhelming
    sleep(0.01); // 10ms between requests per VU
  });
}

// =============================================================================
// ADDITIONAL SCENARIOS
// =============================================================================

export function pageViewScenario() {
  group('PageView Events', function () {
    const event = generatePageViewEvent();
    const { response } = sendEvent(event);
    
    check(response, {
      'PageView accepted': (r) => r.status === 200,
      'response time < 200ms': (r) => r.timings.duration < 200,
    });
  });
}

export function purchaseScenario() {
  group('Purchase Events', function () {
    const event = generatePurchaseEvent();
    const { response } = sendEvent(event);
    
    check(response, {
      'Purchase accepted': (r) => r.status === 200,
      'response time < 300ms': (r) => r.timings.duration < 300,
    });
  });
}

export function batchScenario() {
  group('Batch Events', function () {
    // Send 10 events in batch
    const events = Array.from({ length: 10 }, () => generateRandomEvent());
    
    const response = http.post(
      `${BASE_URL}/api/collect/batch`,
      JSON.stringify({ events }),
      { headers }
    );
    
    check(response, {
      'batch accepted': (r) => r.status === 200,
      'all events processed': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.processed === events.length;
        } catch {
          return false;
        }
      },
    });
  });
}

// =============================================================================
// SPIKE TEST
// =============================================================================

export const spikeOptions = {
  stages: [
    { duration: '10s', target: 100 },
    { duration: '1m', target: 100 },
    { duration: '10s', target: 5000 },  // Sudden spike
    { duration: '3m', target: 5000 },   // Hold spike
    { duration: '10s', target: 100 },   // Quick recovery
    { duration: '1m', target: 100 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    'http_req_failed': ['rate<0.01'],  // Allow 1% errors during spike
    'http_req_duration': ['p(95)<500'], // Relaxed during spike
  },
};

export function spikeTest() {
  const event = generateRandomEvent();
  const { response } = sendEvent(event);
  
  check(response, {
    'survives spike': (r) => r.status === 200 || r.status === 202 || r.status === 429,
  });
  
  sleep(0.001);
}

// =============================================================================
// SOAK TEST
// =============================================================================

export const soakOptions = {
  stages: [
    { duration: '2m', target: 200 },
    { duration: '4h', target: 200 },  // 4 hour soak
    { duration: '2m', target: 0 },
  ],
  thresholds: {
    'http_req_failed': ['rate<0.001'],
    'http_req_duration': ['p(99)<300'],
  },
};

export function soakTest() {
  const event = generateRandomEvent();
  const { response } = sendEvent(event);
  
  check(response, {
    'status ok': (r) => r.status === 200,
    'consistent latency': (r) => r.timings.duration < 300,
  });
  
  sleep(0.05);
}

// =============================================================================
// STRESS TEST
// =============================================================================

export const stressOptions = {
  stages: [
    { duration: '2m', target: 100 },
    { duration: '5m', target: 500 },
    { duration: '5m', target: 1000 },
    { duration: '5m', target: 2000 },
    { duration: '5m', target: 3000 },
    { duration: '5m', target: 4000 },
    { duration: '5m', target: 5000 },  // Find breaking point
    { duration: '5m', target: 0 },
  ],
  thresholds: {
    'http_req_failed': ['rate<0.05'],  // 5% allowed at stress
  },
};

export function stressTest() {
  const event = generateRandomEvent();
  const { response } = sendEvent(event);
  
  check(response, {
    'handles stress': (r) => r.status < 500,
  });
  
  sleep(0.001);
}

// =============================================================================
// SETUP AND TEARDOWN
// =============================================================================

export function setup() {
  console.log(`Load test starting against ${BASE_URL}`);
  console.log(`Environment: ${__ENV.ENVIRONMENT || 'staging'}`);
  
  // Verify endpoint is reachable
  const healthCheck = http.get(`${BASE_URL}/health`);
  if (healthCheck.status !== 200) {
    throw new Error(`Health check failed: ${healthCheck.status}`);
  }
  
  return { startTime: Date.now() };
}

export function teardown(data) {
  const duration = (Date.now() - data.startTime) / 1000;
  console.log(`Load test completed in ${duration}s`);
}

// =============================================================================
// CUSTOM SUMMARY
// =============================================================================

export function handleSummary(data) {
  const summary = {
    timestamp: new Date().toISOString(),
    duration_seconds: data.state.testRunDurationMs / 1000,
    vus_max: data.metrics.vus_max ? data.metrics.vus_max.values.max : 0,
    
    // Request metrics
    requests_total: data.metrics.http_reqs ? data.metrics.http_reqs.values.count : 0,
    requests_per_second: data.metrics.http_reqs ? data.metrics.http_reqs.values.rate : 0,
    
    // Latency
    latency_p50: data.metrics.http_req_duration ? data.metrics.http_req_duration.values['p(50)'] : 0,
    latency_p95: data.metrics.http_req_duration ? data.metrics.http_req_duration.values['p(95)'] : 0,
    latency_p99: data.metrics.http_req_duration ? data.metrics.http_req_duration.values['p(99)'] : 0,
    latency_avg: data.metrics.http_req_duration ? data.metrics.http_req_duration.values.avg : 0,
    
    // Errors
    error_rate: data.metrics.http_req_failed ? data.metrics.http_req_failed.values.rate : 0,
    
    // Custom metrics
    events_processed: data.metrics.events_processed ? data.metrics.events_processed.values.count : 0,
    
    // Thresholds
    thresholds_passed: Object.values(data.root_group.checks || {}).every(c => c.passes > 0),
  };
  
  return {
    'test-results/load-test-summary.json': JSON.stringify(summary, null, 2),
    stdout: textSummary(data, { indent: ' ', enableColors: true }),
  };
}

function textSummary(data, options) {
  // Simple text summary
  return `
===== S.S.I. SHADOW LOAD TEST RESULTS =====

Duration: ${(data.state.testRunDurationMs / 1000).toFixed(2)}s
VUs Max: ${data.metrics.vus_max?.values.max || 0}

REQUESTS:
  Total: ${data.metrics.http_reqs?.values.count || 0}
  Rate: ${(data.metrics.http_reqs?.values.rate || 0).toFixed(2)} req/s
  Failed: ${((data.metrics.http_req_failed?.values.rate || 0) * 100).toFixed(3)}%

LATENCY:
  Avg: ${(data.metrics.http_req_duration?.values.avg || 0).toFixed(2)}ms
  P50: ${(data.metrics.http_req_duration?.values['p(50)'] || 0).toFixed(2)}ms
  P95: ${(data.metrics.http_req_duration?.values['p(95)'] || 0).toFixed(2)}ms
  P99: ${(data.metrics.http_req_duration?.values['p(99)'] || 0).toFixed(2)}ms

TARGETS:
  ✓ 1000 req/s: ${data.metrics.http_reqs?.values.rate >= 1000 ? 'PASS' : 'FAIL'}
  ✓ P99 < 300ms: ${(data.metrics.http_req_duration?.values['p(99)'] || 0) < 300 ? 'PASS' : 'FAIL'}
  ✓ Error < 0.1%: ${(data.metrics.http_req_failed?.values.rate || 0) < 0.001 ? 'PASS' : 'FAIL'}

==========================================
`;
}
