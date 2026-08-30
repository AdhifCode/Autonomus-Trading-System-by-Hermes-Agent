"""Trader Control Center Master FastAPI Application.

Mounts REST API routes, WebSocket endpoint, CORS middleware, and serves frontend static assets.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from web.api.routes import router as api_router
from web.api.websocket import router as ws_router

app = FastAPI(
    title="Hermes Trader Control Center V2.1",
    description="Deterministic AI-Assisted Crypto Automated Trading System Control Interface",
    version="2.1.0",
)

# CORS Configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include Routers
app.include_router(api_router)
app.include_router(ws_router)

# Mount Static Files
FRONTEND_DIR = Path(__file__).parent / "frontend"
os.makedirs(FRONTEND_DIR, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def serve_index() -> FileResponse:
    """Serve single-page Trader Control Center frontend dashboard."""
    index_path = FRONTEND_DIR / "index.html"
    if not index_path.exists():
        # Fallback response if index.html is being generated
        return FileResponse(str(FRONTEND_DIR / "index.html"))
    return FileResponse(str(index_path))
