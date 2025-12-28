# S.S.I. SHADOW - API Reference

## Overview

Base URL: `https://api.ssi-shadow.io/v1`

All requests require authentication via Bearer token.

## Authentication

```bash
curl -H "Authorization: Bearer YOUR_TOKEN" https://api.ssi-shadow.io/v1/health
```

---

## Health Endpoints

### GET /health
Basic health check.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "environment": "production"
}
```

### GET /health/detailed
Detailed health with all dependencies.

**Response:**
```json
{
  "status": "healthy",
  "timestamp": "2024-01-15T10:30:00Z",
  "version": "1.0.0",
  "environment": "production",
  "checks": {
    "redis": {"status": "healthy", "latency_ms": 2},
    "bigquery": {"status": "healthy"},
    "meta_api": {"status": "healthy"},
    "google_ads_api": {"status": "healthy"}
  }
}
```

---

## gROAS Automation

### POST /api/groas/start
Start a gROAS optimization cycle.

**Request:**
```json
{
  "campaign_ids": ["123456789"],
  "auto_apply": false,
  "dry_run": true
}
```

**Response:**
```json
{
  "cycle_id": "abc123",
  "status": "completed",
  "started_at": "2024-01-15T10:30:00Z",
  "completed_at": "2024-01-15T10:31:00Z",
  "campaigns_analyzed": 1,
  "recommendations_count": 15,
  "recommendations_applied": 0,
  "recommendations": [
    {
      "action": "add_keyword",
      "campaign_id": "123456789",
      "ad_group_id": "456",
      "keyword_text": "buy running shoes",
      "reason": "High intent score (0.85)",
      "confidence": 0.85
    }
  ]
}
```

### GET /api/groas/status
Get current automation status.

### GET /api/groas/recommendations
Get recommendations without applying.

---

## Budget Optimization

### POST /api/budget/optimize
Run budget optimization.

**Request:**
```json
{
  "total_budget": 10000.0,
  "campaign_ids": null,
  "auto_apply": false,
  "dry_run": true
}
```

**Response:**
```json
{
  "status": "completed",
  "total_budget": 10000.0,
  "allocations": [
    {
      "campaign_id": "123456789",
      "platform": "google",
      "current_budget": 100.0,
      "new_budget": 120.0,
      "change_pct": 0.20,
      "applied": false
    }
  ],
  "applied": false
}
```

---

## Events API

### POST /api/events
Track an event.

**Request:**
```json
{
  "event_name": "purchase",
  "user_id": "user_123",
  "properties": {
    "value": 99.99,
    "currency": "USD",
    "order_id": "order_456",
    "products": ["prod_789"]
  },
  "context": {
    "page_url": "https://example.com/checkout",
    "user_agent": "Mozilla/5.0..."
  }
}
```

**Response:**
```json
{
  "event_id": "evt_abc123",
  "status": "accepted",
  "platforms_sent": ["meta", "google", "tiktok"]
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "error": {
    "code": "VAL_001",
    "message": "Validation failed",
    "timestamp": "2024-01-15T10:30:00Z",
    "request_id": "req_xyz",
    "details": {
      "field": "campaign_id",
      "reason": "Campaign not found"
    }
  }
}
```

### Error Codes

| Code | HTTP Status | Description |
|------|-------------|-------------|
| VAL_001 | 400 | Validation error |
| AUTH_001 | 401 | Authentication failed |
| AUTHZ_001 | 403 | Authorization denied |
| RATE_001 | 429 | Rate limit exceeded |
| API_001 | 502 | External API error |
| DB_001 | 503 | Database error |

---

## Rate Limits

| Plan | Requests/min | Events/day |
|------|--------------|------------|
| Free | 60 | 10,000 |
| Starter | 300 | 100,000 |
| Pro | 1,000 | 1,000,000 |
| Enterprise | 10,000 | Unlimited |

Rate limit headers:
```
X-RateLimit-Limit: 1000
X-RateLimit-Remaining: 999
X-RateLimit-Reset: 1705312200
```
