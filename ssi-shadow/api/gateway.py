"""
S.S.I. SHADOW — REST API Gateway
EXTERNAL API FOR QUERIES & INTEGRATIONS

Endpoints:
- GET /api/v1/visitors/{ssi_id} - Dados do visitante
- GET /api/v1/visitors/{ssi_id}/predictions - Predições
- GET /api/v1/campaigns/{id}/metrics - Métricas de campanha
- GET /api/v1/reports/daily - Relatório diário
- POST /api/v1/webhooks/meta - Webhook Meta
- POST /api/v1/webhooks/google - Webhook Google

Deploy:
    uvicorn api.gateway:app --host 0.0.0.0 --port 8000
"""

import os
import time
import hashlib
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from functools import wraps

from fastapi import FastAPI, HTTPException, Depends, Header, Request, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import uvicorn

# Rate limiting
from collections import defaultdict
import asyncio

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger('ssi_api')

# =============================================================================
# CONFIG
# =============================================================================

API_VERSION = "1.0.0"
API_KEY_HEADER = "X-API-Key"
RATE_LIMIT_REQUESTS = int(os.environ.get('RATE_LIMIT_REQUESTS', '100'))
RATE_LIMIT_WINDOW = int(os.environ.get('RATE_LIMIT_WINDOW', '60'))

# API Keys (em produção, usar secrets manager)
VALID_API_KEYS = set(os.environ.get('API_KEYS', 'test-key-123').split(','))

# =============================================================================
# RATE LIMITER
# =============================================================================

class RateLimiter:
    def __init__(self, requests: int = 100, window: int = 60):
        self.requests = requests
        self.window = window
        self.clients: Dict[str, List[float]] = defaultdict(list)
        self._lock = asyncio.Lock()
    
    async def is_allowed(self, client_id: str) -> bool:
        async with self._lock:
            now = time.time()
            # Limpar requests antigos
            self.clients[client_id] = [
                t for t in self.clients[client_id] 
                if now - t < self.window
            ]
            
            if len(self.clients[client_id]) >= self.requests:
                return False
            
            self.clients[client_id].append(now)
            return True
    
    def remaining(self, client_id: str) -> int:
        now = time.time()
        valid_requests = [
            t for t in self.clients[client_id] 
            if now - t < self.window
        ]
        return max(0, self.requests - len(valid_requests))

rate_limiter = RateLimiter(RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW)

# =============================================================================
# MODELS
# =============================================================================

class VisitorResponse(BaseModel):
    ssi_id: str
    visitor_ids: List[str] = []
    first_seen: Optional[str]
    last_seen: Optional[str]
    event_count: int = 0
    total_value: float = 0
    ltv_segment: Optional[str]
    intent_segment: Optional[str]

class PredictionResponse(BaseModel):
    ssi_id: str
    ltv_score: float
    ltv_segment: str
    intent_score: float
    intent_segment: str
    churn_probability: Optional[float]
    predicted_at: str

class CampaignMetrics(BaseModel):
    campaign_id: str
    date_range: str
    events: int
    visitors: int
    conversions: int
    revenue: float
    avg_trust_score: float
    ivt_rate: float
    estimated_match_rate: float

class DailyReport(BaseModel):
    date: str
    total_events: int
    unique_visitors: int
    purchases: int
    revenue: float
    avg_trust_score: float
    ivt_rate: float
    conversion_rate: float
    estimated_emq: float

class WebhookPayload(BaseModel):
    event_type: str
    data: Dict[str, Any]
    timestamp: Optional[str]

class AuditLog(BaseModel):
    timestamp: str
    method: str
    path: str
    client_id: str
    status_code: int
    response_time_ms: float
    ip: Optional[str]

# =============================================================================
# APP
# =============================================================================

app = FastAPI(
    title="S.S.I. SHADOW API",
    description="Enterprise API for SSI Shadow tracking system",
    version=API_VERSION,
    docs_url="/api/docs",
    redoc_url="/api/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# DEPENDENCIES
# =============================================================================

async def verify_api_key(x_api_key: str = Header(...)):
    """Verifica API key"""
    if x_api_key not in VALID_API_KEYS:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return x_api_key

async def check_rate_limit(request: Request, api_key: str = Depends(verify_api_key)):
    """Verifica rate limit"""
    if not await rate_limiter.is_allowed(api_key):
        raise HTTPException(
            status_code=429, 
            detail="Rate limit exceeded",
            headers={"Retry-After": str(RATE_LIMIT_WINDOW)}
        )
    return api_key

# =============================================================================
# AUDIT LOGGING
# =============================================================================

audit_logs: List[AuditLog] = []

@app.middleware("http")
async def audit_middleware(request: Request, call_next):
    """Middleware para audit logging"""
    start_time = time.time()
    
    response = await call_next(request)
    
    # Log apenas para /api/
    if request.url.path.startswith("/api/"):
        duration = (time.time() - start_time) * 1000
        
        log = AuditLog(
            timestamp=datetime.now().isoformat(),
            method=request.method,
            path=request.url.path,
            client_id=request.headers.get(API_KEY_HEADER, 'anonymous')[:8] + '***',
            status_code=response.status_code,
            response_time_ms=round(duration, 2),
            ip=request.client.host if request.client else None
        )
        
        audit_logs.append(log)
        
        # Manter apenas últimos 1000 logs
        if len(audit_logs) > 1000:
            audit_logs.pop(0)
    
    return response

# =============================================================================
# HEALTH
# =============================================================================

@app.get("/health")
async def health():
    """Health check"""
    return {
        "status": "healthy",
        "version": API_VERSION,
        "timestamp": datetime.now().isoformat()
    }

@app.get("/api/v1/health")
async def api_health(api_key: str = Depends(check_rate_limit)):
    """API health com rate limit info"""
    return {
        "status": "healthy",
        "version": API_VERSION,
        "rate_limit": {
            "remaining": rate_limiter.remaining(api_key),
            "window_seconds": RATE_LIMIT_WINDOW,
            "limit": RATE_LIMIT_REQUESTS
        },
        "timestamp": datetime.now().isoformat()
    }

# =============================================================================
# VISITORS
# =============================================================================

@app.get("/api/v1/visitors/{ssi_id}", response_model=VisitorResponse)
async def get_visitor(ssi_id: str, api_key: str = Depends(check_rate_limit)):
    """
    Obtém dados de um visitante pelo SSI ID.
    """
    # Em produção, consultar BigQuery
    # Mock response
    return VisitorResponse(
        ssi_id=ssi_id,
        visitor_ids=["fpjs_abc123"],
        first_seen="2024-01-01T00:00:00Z",
        last_seen=datetime.now().isoformat(),
        event_count=42,
        total_value=350.00,
        ltv_segment="medium",
        intent_segment="warm"
    )

@app.get("/api/v1/visitors/{ssi_id}/predictions", response_model=PredictionResponse)
async def get_visitor_predictions(ssi_id: str, api_key: str = Depends(check_rate_limit)):
    """
    Obtém predições ML para um visitante.
    """
    return PredictionResponse(
        ssi_id=ssi_id,
        ltv_score=0.72,
        ltv_segment="high",
        intent_score=0.85,
        intent_segment="hot",
        churn_probability=0.15,
        predicted_at=datetime.now().isoformat()
    )

@app.get("/api/v1/visitors/{ssi_id}/events")
async def get_visitor_events(
    ssi_id: str, 
    limit: int = 50,
    api_key: str = Depends(check_rate_limit)
):
    """
    Lista eventos de um visitante.
    """
    # Mock
    return {
        "ssi_id": ssi_id,
        "events": [
            {
                "event_id": "evt_abc123",
                "event_name": "PageView",
                "event_time": datetime.now().isoformat(),
                "url": "https://example.com/product/123"
            }
        ],
        "total": 1,
        "limit": limit
    }

# =============================================================================
# CAMPAIGNS
# =============================================================================

@app.get("/api/v1/campaigns/{campaign_id}/metrics", response_model=CampaignMetrics)
async def get_campaign_metrics(
    campaign_id: str,
    days: int = 7,
    api_key: str = Depends(check_rate_limit)
):
    """
    Obtém métricas de uma campanha.
    """
    return CampaignMetrics(
        campaign_id=campaign_id,
        date_range=f"last_{days}_days",
        events=10000,
        visitors=5000,
        conversions=150,
        revenue=15000.00,
        avg_trust_score=0.72,
        ivt_rate=0.08,
        estimated_match_rate=0.75
    )

@app.get("/api/v1/campaigns")
async def list_campaigns(
    days: int = 7,
    limit: int = 50,
    api_key: str = Depends(check_rate_limit)
):
    """
    Lista campanhas com métricas básicas.
    """
    return {
        "campaigns": [
            {
                "campaign_id": "123456",
                "name": "Campaign A",
                "conversions": 50,
                "revenue": 5000.00,
                "avg_trust_score": 0.75
            }
        ],
        "total": 1,
        "date_range": f"last_{days}_days"
    }

# =============================================================================
# REPORTS
# =============================================================================

@app.get("/api/v1/reports/daily", response_model=DailyReport)
async def get_daily_report(
    date: Optional[str] = None,
    api_key: str = Depends(check_rate_limit)
):
    """
    Obtém relatório diário.
    """
    report_date = date or (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
    
    return DailyReport(
        date=report_date,
        total_events=50000,
        unique_visitors=15000,
        purchases=300,
        revenue=30000.00,
        avg_trust_score=0.73,
        ivt_rate=0.07,
        conversion_rate=0.02,
        estimated_emq=8.2
    )

@app.get("/api/v1/reports/weekly")
async def get_weekly_report(api_key: str = Depends(check_rate_limit)):
    """
    Obtém relatório semanal agregado.
    """
    return {
        "period": "last_7_days",
        "total_events": 350000,
        "unique_visitors": 80000,
        "purchases": 2100,
        "revenue": 210000.00,
        "avg_trust_score": 0.74,
        "ivt_rate": 0.065,
        "top_campaigns": []
    }

# =============================================================================
# WEBHOOKS
# =============================================================================

@app.post("/api/v1/webhooks/meta")
async def webhook_meta(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(check_rate_limit)
):
    """
    Webhook para eventos do Meta (Conversion API callback, etc).
    """
    logger.info(f"Meta webhook received: {payload.event_type}")
    
    # Processar em background
    background_tasks.add_task(process_meta_webhook, payload.dict())
    
    return {"status": "accepted", "event_type": payload.event_type}

@app.post("/api/v1/webhooks/google")
async def webhook_google(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(check_rate_limit)
):
    """
    Webhook para eventos do Google Ads.
    """
    logger.info(f"Google webhook received: {payload.event_type}")
    
    background_tasks.add_task(process_google_webhook, payload.dict())
    
    return {"status": "accepted", "event_type": payload.event_type}

@app.post("/api/v1/webhooks/revealbot")
async def webhook_revealbot(
    payload: WebhookPayload,
    background_tasks: BackgroundTasks,
    api_key: str = Depends(check_rate_limit)
):
    """
    Webhook para callbacks do Revealbot.
    """
    logger.info(f"Revealbot webhook received: {payload.event_type}")
    
    return {"status": "accepted", "event_type": payload.event_type}

async def process_meta_webhook(payload: Dict):
    """Processa webhook do Meta em background"""
    logger.info(f"Processing Meta webhook: {payload}")

async def process_google_webhook(payload: Dict):
    """Processa webhook do Google em background"""
    logger.info(f"Processing Google webhook: {payload}")

# =============================================================================
# ADMIN
# =============================================================================

@app.get("/api/v1/admin/audit-logs")
async def get_audit_logs(
    limit: int = 100,
    api_key: str = Depends(check_rate_limit)
):
    """
    Obtém logs de auditoria recentes.
    """
    return {
        "logs": [log.dict() for log in audit_logs[-limit:]],
        "total": len(audit_logs)
    }

@app.get("/api/v1/admin/rate-limits")
async def get_rate_limits(api_key: str = Depends(check_rate_limit)):
    """
    Obtém status de rate limits.
    """
    return {
        "your_remaining": rate_limiter.remaining(api_key),
        "window_seconds": RATE_LIMIT_WINDOW,
        "limit_per_window": RATE_LIMIT_REQUESTS
    }

# =============================================================================
# ERROR HANDLERS
# =============================================================================

@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.detail,
            "status_code": exc.status_code,
            "timestamp": datetime.now().isoformat()
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled error: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "status_code": 500,
            "timestamp": datetime.now().isoformat()
        }
    )

# =============================================================================
# MAIN
# =============================================================================

if __name__ == "__main__":
    uvicorn.run(
        "gateway:app",
        host="0.0.0.0",
        port=int(os.environ.get("PORT", "8000")),
        reload=os.environ.get("DEBUG", "false").lower() == "true"
    )
