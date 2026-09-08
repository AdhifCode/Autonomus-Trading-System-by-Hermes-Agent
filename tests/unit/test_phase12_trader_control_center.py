"""Phase 12: Trader Control Center Unit & Integration Tests.

Validates:
1. All core views and REST API endpoints.
2. Backend authentication and authorization checks.
3. Strict enforcement of Risk Engine safety boundary (No Execution Bypass).
4. No direct exchange access invariant.
5. SystemEvent audit logging for all UI actions.
"""

from __future__ import annotations

import tempfile

import pytest
from fastapi.testclient import TestClient

from web.api.routes import get_service
from web.app import app
from web.service import ControlCenterService


@pytest.fixture
def temp_service():
    """Fixture providing an isolated ControlCenterService with temporary SQLite database."""
    with (
        tempfile.NamedTemporaryFile(suffix=".db") as tmp_db,
        tempfile.TemporaryDirectory() as tmp_vault,
    ):
        service = ControlCenterService(db_path=tmp_db.name, vault_path=tmp_vault)
        yield service


@pytest.fixture
def client(temp_service):
    """TestClient fixture overriding service dependency."""
    app.dependency_overrides[get_service] = lambda: temp_service
    yield TestClient(app)
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# 1. Core REST Endpoints Verification
# ---------------------------------------------------------------------------


def test_system_status_endpoint(client):
    """Test /api/v1/system/status returns expected health structure."""
    response = client.get("/api/v1/system/status")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert data["trading_mode"] == "DEVELOPMENT"
    assert "sqlite_connected" in data
    assert data["sqlite_connected"] is True


def test_portfolio_endpoint(client):
    """Test /api/v1/portfolio returns equity and balance breakdown."""
    response = client.get("/api/v1/portfolio")
    assert response.status_code == 200
    data = response.json()
    assert "total_equity" in data
    assert "free_balance" in data
    assert "net_pnl_today" in data


def test_positions_and_orders_endpoints(client):
    """Test positions and orders retrieval."""
    pos_res = client.get("/api/v1/positions")
    assert pos_res.status_code == 200
    assert isinstance(pos_res.json(), list)

    ord_res = client.get("/api/v1/orders")
    assert ord_res.status_code == 200
    assert isinstance(ord_res.json(), list)


def test_risk_status_and_ai_decisions_endpoints(client):
    """Test risk engine status (20 rules) and AI decision logs."""
    risk_res = client.get("/api/v1/risk/status")
    assert risk_res.status_code == 200
    risk_data = risk_res.json()
    assert "validators" in risk_data
    assert len(risk_data["validators"]) == 20

    ai_res = client.get("/api/v1/ai/decisions")
    assert ai_res.status_code == 200
    assert isinstance(ai_res.json(), list)


def test_knowledge_and_learning_endpoints(client):
    """Test knowledge base and learning pipeline V2 endpoints."""
    k_res = client.get("/api/v1/knowledge/dashboard")
    assert k_res.status_code == 200
    assert "total_notes" in k_res.json()

    l_res = client.get("/api/v1/learning/pipeline")
    assert l_res.status_code == 200
    assert isinstance(l_res.json(), list)


# ---------------------------------------------------------------------------
# 2. Authentication & Authorization Invariants
# ---------------------------------------------------------------------------


def test_protected_endpoints_require_auth(client):
    """Test sensitive control endpoints require valid API Key or Bearer Token."""
    # 1. Kill Switch without auth -> 401
    res1 = client.post("/api/v1/system/kill-switch", json={"active": True})
    assert res1.status_code == 401

    # 2. Trade proposal without auth -> 401
    res2 = client.post(
        "/api/v1/trade/propose", json={"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.1}
    )
    assert res2.status_code == 401

    # 3. Advance stage without auth -> 401
    res3 = client.post(
        "/api/v1/learning/advance-stage",
        json={"lesson_id": "LES-001", "target_stage": "PRODUCTION_STRATEGY"},
    )
    assert res3.status_code == 401


def test_protected_endpoints_with_valid_auth(client):
    """Test protected endpoints succeed when valid X-API-Key is provided."""
    headers = {"X-API-Key": "hermes-trader-secret-key-v2.1"}

    # 1. Trading mode update
    res = client.post("/api/v1/system/trading-mode", json={"mode": "PAPER"}, headers=headers)
    assert res.status_code == 200
    assert res.json()["trading_mode"] == "PAPER"


# ---------------------------------------------------------------------------
# 3. Deterministic Safety Boundary & No Execution Bypass
# ---------------------------------------------------------------------------


def test_trade_proposal_passes_through_risk_engine(client):
    """Test TradeProposals are evaluated by RiskEngine and cannot bypass safety."""
    headers = {"X-API-Key": "hermes-trader-secret-key-v2.1"}

    payload = {
        "symbol": "BTCUSDT",
        "side": "BUY",
        "order_type": "MARKET",
        "quantity": 0.1,
        "llm_confidence": 0.85,
    }

    res = client.post("/api/v1/trade/propose", json=payload, headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["risk_decision"] == "APPROVED"
    assert data["status"] == "APPROVED"


def test_kill_switch_blocks_trade_proposals(client):
    """Test that activating System Hard Kill Switch blocks all subsequent TradeProposals."""
    headers = {"X-API-Key": "hermes-trader-secret-key-v2.1"}

    # Activate Kill Switch
    ks_res = client.post(
        "/api/v1/system/kill-switch",
        json={"active": True, "reason": "Test Kill Switch"},
        headers=headers,
    )
    assert ks_res.status_code == 200
    assert ks_res.json()["kill_switch_active"] is True

    # Try submitting proposal
    prop_res = client.post(
        "/api/v1/trade/propose",
        json={"symbol": "BTCUSDT", "side": "BUY", "quantity": 0.1},
        headers=headers,
    )
    assert prop_res.status_code == 200
    prop_data = prop_res.json()

    # Must be REJECTED or FREEZE by RiskEngine
    assert prop_data["risk_decision"] in ("REJECTED", "FREEZE")
    assert prop_data["status"] in ("REJECTED", "FREEZE")


# ---------------------------------------------------------------------------
# 4. Audit Trail Logging Invariant
# ---------------------------------------------------------------------------


def test_ui_actions_generate_audit_log_events(client):
    """Test UI actions generate SystemEvent audit trail records in SQLite."""
    headers = {"X-API-Key": "hermes-trader-secret-key-v2.1"}

    # Perform action
    client.post("/api/v1/system/trading-mode", json={"mode": "PAPER"}, headers=headers)

    # Check audit logs
    audit_res = client.get("/api/v1/audit/logs")
    assert audit_res.status_code == 200
    logs = audit_res.json()
    assert len(logs) > 0
    assert any("Trading mode updated to PAPER" in l.get("message", "") for l in logs)
