"""
S.S.I. SHADOW - Main FastAPI Application
Server-Side Intelligence Shadow API.
"""

import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

# Import routes
from api.routes import health, groas, budget

# Application metadata
APP_TITLE = "S.S.I. SHADOW API"
APP_DESCRIPTION = """
## Server-Side Intelligence Shadow

Complete platform for server-side tracking, multi-touch attribution,
and automated marketing optimization.

### Features

* **Event Tracking** - Server-side event collection with CAPI integrations
* **Attribution** - Multi-touch attribution with multiple models
* **gROAS** - Granular ROAS optimization using search intent analysis
* **Budget Optimization** - Bayesian optimization for budget allocation
* **Weather Bidding** - Weather-based bid adjustments
* **Competitor Intelligence** - Price monitoring and analysis

### Authentication

All endpoints require JWT Bearer token authentication.
"""

APP_VERSION = os.getenv("APP_VERSION", "1.0.0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan events."""
    # Startup
    print(f"Starting {APP_TITLE} v{APP_VERSION}")
    
    # Initialize connections, load models, etc.
    yield
    
    # Shutdown
    print("Shutting down...")


# Create FastAPI app
app = FastAPI(
    title=APP_TITLE,
    description=APP_DESCRIPTION,
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router)
app.include_router(groas.router, prefix="/api")
app.include_router(budget.router, prefix="/api")


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": APP_TITLE,
        "version": APP_VERSION,
        "docs": "/docs",
        "health": "/health"
    }


# Error handlers would be added via middleware
# from api.middleware.error_handler import setup_error_handling
# setup_error_handling(app)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api.main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        reload=os.getenv("ENVIRONMENT") == "development"
    )
