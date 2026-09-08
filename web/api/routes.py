"""FastAPI Router for Trader Control Center REST API.

Provides endpoints for Dashboard, Trading, Positions, Orders, Risk, AI Decisions,
Market Regimes, Strategies, Backtesting, Knowledge Base, Learning Loop V2, and System Controls.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from web.api.auth import verify_api_key
from web.service import ControlCenterService

router = APIRouter(prefix="/api/v1", tags=["Trader Control Center"])

# Global service instance (injected via app state or singleton pattern)
_service_instance: ControlCenterService | None = None


def get_service() -> ControlCenterService:
    global _service_instance
    if _service_instance is None:
        _service_instance = ControlCenterService()
    return _service_instance


# ---------------------------------------------------------------------------
# Request Schemas
# ---------------------------------------------------------------------------


class KillSwitchRequest(BaseModel):
    active: bool
    reason: str = "User initiated via Trader Control Center UI"


class TradingModeRequest(BaseModel):
    mode: str


class TradeProposalRequest(BaseModel):
    symbol: str = Field(default="BTCUSDT")
    side: str = Field(default="BUY")
    order_type: str = Field(default="MARKET")
    quantity: float = Field(gt=0.0)
    price: float | None = None
    strategy_id: str = "manual_ui"
    strategy_version: str = "1.0"
    model_version: str = "v1.0"
    llm_confidence: float = Field(default=0.8, ge=0.0, le=1.0)


class ClosePositionRequest(BaseModel):
    symbol: str
    side: str
    size: float


class CancelOrderRequest(BaseModel):
    order_id: str


class AdvanceStageRequest(BaseModel):
    lesson_id: str
    target_stage: str
    human_approved: bool = False


# ---------------------------------------------------------------------------
# System Status & Controls
# ---------------------------------------------------------------------------


@router.get("/health")
@router.get("/system/status")
def get_system_status(service: ControlCenterService = Depends(get_service)) -> dict[str, Any]:
    """Get system health and operational status."""
    return service.get_system_status()


@router.post("/system/kill-switch")
def toggle_kill_switch(
    req: KillSwitchRequest,
    service: ControlCenterService = Depends(get_service),
    token: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Emergency System Hard Kill Switch trigger (Requires Auth)."""
    return service.set_kill_switch(active=req.active, reason=req.reason)


@router.post("/system/trading-mode")
def set_trading_mode(
    req: TradingModeRequest,
    service: ControlCenterService = Depends(get_service),
    token: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Update trading mode (Requires Auth)."""
    return service.set_trading_mode(req.mode)


# ---------------------------------------------------------------------------
# Portfolio, Positions, Orders & Execution
# ---------------------------------------------------------------------------


@router.get("/portfolio")
def get_portfolio(service: ControlCenterService = Depends(get_service)) -> dict[str, Any]:
    """Get portfolio equity and balance breakdown."""
    return service.get_portfolio()


@router.get("/positions")
def get_positions(service: ControlCenterService = Depends(get_service)) -> Any:
    """Get active open positions."""
    return service.get_positions()


@router.post("/positions/close")
async def close_position(
    req: ClosePositionRequest,
    service: ControlCenterService = Depends(get_service),
    token: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Close position safely through Risk Engine authorization and Execution Service."""
    return await service.close_position(symbol=req.symbol, side=req.side, size=req.size)


@router.get("/orders")
def get_orders(service: ControlCenterService = Depends(get_service)) -> Any:
    """Get canonical SQLite orders."""
    return service.get_orders()


@router.post("/orders/cancel")
async def cancel_order(
    req: CancelOrderRequest,
    service: ControlCenterService = Depends(get_service),
    token: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Cancel order via Execution Service (Requires Auth)."""
    return await service.cancel_order(req.order_id)


@router.get("/trades")
def get_trades(service: ControlCenterService = Depends(get_service)) -> Any:
    """Get canonical SQLite active and historical trades."""
    return service.get_trades()


@router.post("/trade/propose")
async def submit_trade_proposal(
    req: TradeProposalRequest,
    service: ControlCenterService = Depends(get_service),
    token: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Submit trade proposal through Risk Engine evaluation & Execution Service (Requires Auth)."""
    return await service.submit_trade_proposal(req.model_dump())


# ---------------------------------------------------------------------------
# Risk, AI Decisions & Intelligence
# ---------------------------------------------------------------------------


@router.get("/risk/status")
def get_risk_status(service: ControlCenterService = Depends(get_service)) -> dict[str, Any]:
    """Get deterministic risk engine policy and 20 validator statuses."""
    return service.get_risk_status()


@router.get("/ai/decisions")
def get_ai_decisions(service: ControlCenterService = Depends(get_service)) -> Any:
    """Get Hermes AI trade proposals and confidence evaluation logs."""
    return service.get_ai_decisions()


@router.get("/market/regimes")
def get_market_regimes(service: ControlCenterService = Depends(get_service)) -> dict[str, Any]:
    """Get market regime engine output."""
    return service.get_market_intelligence()


@router.get("/strategies")
def get_strategies(service: ControlCenterService = Depends(get_service)) -> Any:
    """Get active strategy versions and immutability status."""
    return service.get_strategies()


@router.get("/backtesting/summary")
def get_backtesting_summary(service: ControlCenterService = Depends(get_service)) -> dict[str, Any]:
    """Get DuckDB performance metrics and walk-forward backtest summary."""
    return service.get_backtesting_summary()


@router.get("/experiments")
def get_experiments(service: ControlCenterService = Depends(get_service)) -> Any:
    """Get candidate strategy experiments."""
    return service.get_experiments()


# ---------------------------------------------------------------------------
# Knowledge Base & Learning Loop V2
# ---------------------------------------------------------------------------


@router.get("/knowledge/dashboard")
def get_knowledge_dashboard(service: ControlCenterService = Depends(get_service)) -> dict[str, Any]:
    """Get Obsidian vault knowledge base metrics."""
    return service.get_knowledge_dashboard()


@router.get("/knowledge/notes")
def get_knowledge_notes(
    category: str | None = Query(default=None),
    service: ControlCenterService = Depends(get_service),
) -> Any:
    """Get Obsidian knowledge notes."""
    return service.get_knowledge_notes(category=category)


@router.get("/knowledge/graph")
def get_knowledge_graph(service: ControlCenterService = Depends(get_service)) -> dict[str, Any]:
    """Get Knowledge Graph nodes and links."""
    return service.get_knowledge_graph()


@router.get("/learning/pipeline")
def get_learning_pipeline(service: ControlCenterService = Depends(get_service)) -> Any:
    """Get candidate lessons across 11 stages of Learning Loop V2."""
    return service.get_learning_pipeline()


@router.post("/learning/advance-stage")
def advance_lesson_stage(
    req: AdvanceStageRequest,
    service: ControlCenterService = Depends(get_service),
    token: str = Depends(verify_api_key),
) -> dict[str, Any]:
    """Advance candidate lesson stage (Requires Auth for Human Approval)."""
    return service.advance_lesson_stage(
        lesson_id=req.lesson_id,
        target_stage=req.target_stage,
        human_approved=req.human_approved,
    )


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------


@router.get("/audit/logs")
def get_audit_logs(
    limit: int = Query(default=50, ge=1, le=500),
    service: ControlCenterService = Depends(get_service),
) -> Any:
    """Get SystemEvent audit logs."""
    return service.get_audit_logs(limit=limit)
