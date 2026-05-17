"""
FastAPI Application — Vietnamese Legal Knowledge Graph Backend.

Connects frontend to Python pipeline:
- QA chat with SSE streaming
- Contract review with async job processing
- Conversation management
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from infra.api.middleware import error_handler_middleware
from infra.api.qa_routes import router as qa_router
from infra.api.contract_routes import router as contract_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    logger.info("Starting Vietnamese Legal Knowledge Graph API")
    yield
    logger.info("Shutting down API")


app = FastAPI(
    title="Vietnamese Legal Knowledge Graph API",
    description="Backend API for contract review and legal QA",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Error handler middleware
app.middleware("http")(error_handler_middleware)

# Routes
app.include_router(qa_router, prefix="/api/qa", tags=["qa"])
app.include_router(contract_router, prefix="/api/contracts", tags=["contracts"])


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "ok", "service": "vietnamese-legal-api"}
