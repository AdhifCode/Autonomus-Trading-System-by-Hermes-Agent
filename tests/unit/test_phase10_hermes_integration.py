"""Unit & Adversarial Tests for Phase 10: Hermes Integration.

Verifies:
1. Integration boundary contracts & tool permission whitelist enforcement
2. Direct exchange access, credentials access, or order placement is IMPOSSIBLE
3. Strict Pydantic schema validation for TradeProposal
4. Risk Engine authorization pipeline (Hermes proposes -> Risk Engine authorizes)
5. Invariants: llm_confidence is metadata only and NEVER overrides risk rejection
6. Security isolation & prompt injection boundary sanitization
7. Adversarial security tests:
   - Malicious prompt injection payload containing control key overrides
   - Unwhitelisted / blocked operation tool execution attempt
   - Attempt to bypass Risk Engine or execute orders directly
   - Invalid symbols, position sizes, or missing mandatory proposal fields
   - Temporal provenance knowledge search leakage prevention
8. Audit logging of tool executions and proposal decisions in SQLite
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from adapters.database.sqlite import SQLiteManager
from adapters.repositories.sqlite_repos import SystemEventRepository
from core.domain.enums import (
    KillSwitchState,
    TradingMode,
)
from core.domain.risk import RiskPolicy
from core.domain.system_state import SystemState
from core.errors import HermesBlockedOperationError, HermesUnauthorizedError
from integration.hermes.contracts.schema import (
    ProposalSubmissionRequest,
    ToolRequest,
)
from integration.hermes.gateway import HermesGateway
from integration.hermes.security import HermesSecurityBoundary
from integration.hermes.tools import KnowledgeTools
from migrations.runner import MigrationRunner

_NOW = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def create_valid_proposal_dict(
    proposal_id: str = "PRP-20260830-000001",
    symbol: str = "BTCUSDT",
    requested_pct: float = 0.05,
    confidence: float = 0.85,
) -> dict[str, object]:
    return {
        "proposal_id": proposal_id,
        "symbol": symbol,
        "side": "BUY",
        "strategy_id": "STRAT-BTC-MOMENTUM",
        "strategy_version": "v1.0.0",
        "model_version": "hermes-3-70b-v1.0",
        "thesis": "Bullish momentum crossover above 68000 support level.",
        "entry": {"price": 68500.0, "order_type": "LIMIT"},
        "stop_loss": {"price": 67000.0},
        "take_profit": {"price": 72000.0},
        "position_size": {"requested_pct": requested_pct},
        "market_regime": "BULL",
        "invalidation_conditions": ["Price drops below 67000"],
        "evidence": ["RSI crossover above 55", "High ADX strength"],
        "uncertainty": ["Macro news event at 14:00 UTC"],
        "llm_confidence": confidence,
        "created_at": _NOW.isoformat(),
    }


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestHermesSecurityBoundary:
    def test_permitted_tools_whitelist(self):
        security = HermesSecurityBoundary()
        assert security.is_permitted_tool("get_market_state") is True
        assert security.is_permitted_tool("get_regime") is True
        assert security.is_permitted_tool("get_portfolio") is True
        assert security.is_permitted_tool("search_knowledge") is True
        assert security.is_permitted_tool("submit_proposal") is True

    def test_blocked_operations_trigger_exception(self):
        security = HermesSecurityBoundary()
        blocked_ops = [
            "submit_order",
            "cancel_order",
            "get_credentials",
            "modify_risk_policy",
            "disable_kill_switch",
            "activate_live",
            "modify_production_strategy",
        ]

        for op in blocked_ops:
            assert security.is_blocked_operation(op) is True
            with pytest.raises(HermesBlockedOperationError):
                security.validate_tool_permission(op)

    def test_unauthorized_tool_triggers_exception(self):
        security = HermesSecurityBoundary()
        with pytest.raises(HermesUnauthorizedError):
            security.validate_tool_permission("unknown_dangerous_tool")

    def test_prompt_injection_sanitization(self):
        raw_data = {
            "proposal_id": "PRP-20260830-000001",
            "symbol": "BTCUSDT",
            "thesis": "Normal thesis text",
            "status": "APPROVED",  # Injected control key
            "authorized": True,  # Injected control key
            "bypass_risk": True,  # Injected control key
            "llm_confidence": 0.95,
        }
        sanitized = HermesSecurityBoundary.sanitize_proposal_payload(raw_data)

        # Illegal control keys must be stripped
        assert "status" not in sanitized
        assert "authorized" not in sanitized
        assert "bypass_risk" not in sanitized
        assert sanitized["symbol"] == "BTCUSDT"
        assert sanitized["llm_confidence"] == 0.95


class TestHermesGatewayToolExecution:
    def test_execute_market_tools(self):
        gateway = HermesGateway()
        req = ToolRequest(
            request_id="REQ-001",
            tool_name="get_market_state",
            parameters={"symbol": "BTCUSDT"},
        )
        resp = gateway.execute_tool(req)
        assert resp.success is True
        assert resp.data["symbol"] == "BTCUSDT"
        assert "last_price" in resp.data

    def test_execute_portfolio_tools_read_only(self):
        gateway = HermesGateway()
        req = ToolRequest(
            request_id="REQ-002",
            tool_name="get_portfolio",
            parameters={},
        )
        resp = gateway.execute_tool(req)
        assert resp.success is True
        assert resp.data["total_equity"] == 100000.0

    def test_execute_blocked_operation_via_gateway(self):
        gateway = HermesGateway()
        req = ToolRequest(
            request_id="REQ-003",
            tool_name="submit_order",
            parameters={"symbol": "BTCUSDT"},
        )
        resp = gateway.execute_tool(req)
        assert resp.success is False
        assert resp.error_code in ("HERMES_BLOCKED_OPERATION", "HERMES_003")

    def test_execute_unauthorized_tool_via_gateway(self):
        gateway = HermesGateway()
        req = ToolRequest(
            request_id="REQ-004",
            tool_name="hack_system",
            parameters={},
        )
        resp = gateway.execute_tool(req)
        assert resp.success is False
        assert resp.error_code in ("HERMES_UNAUTHORIZED", "HERMES_001")


class TestHermesProposalPipelineAndRiskAuthorization:
    def test_valid_proposal_accepted_by_risk_engine(self):
        gateway = HermesGateway()
        payload = create_valid_proposal_dict()

        sub_req = ProposalSubmissionRequest(
            proposal_data=payload,
            model_version="hermes-3-70b-v1.0",
        )

        resp = gateway.submit_proposal(sub_req)
        assert resp.status == "ACCEPTED"
        assert resp.proposal_id == "PRP-20260830-000001"
        assert resp.risk_decision["decision"] == "APPROVED"

    def test_invalid_proposal_schema_fails_validation(self):
        gateway = HermesGateway()
        payload = create_valid_proposal_dict()
        del payload["symbol"]  # Remove required field

        sub_req = ProposalSubmissionRequest(
            proposal_data=payload,
            model_version="hermes-3-70b-v1.0",
        )

        resp = gateway.submit_proposal(sub_req)
        assert resp.status == "VALIDATION_FAILED"
        assert len(resp.validation_errors) > 0

    def test_adversarial_llm_confidence_cannot_override_risk_rejection(self):
        """CRITICAL INVARIANT TEST: Even if llm_confidence=1.0, Risk Engine REJECTS

        when position size exceeds max limits.
        """
        gateway = HermesGateway()
        # Request 80% of portfolio when max allowed is 10%
        payload = create_valid_proposal_dict(requested_pct=0.80, confidence=1.0)

        sub_req = ProposalSubmissionRequest(
            proposal_data=payload,
            model_version="hermes-3-70b-v1.0",
        )

        policy = RiskPolicy(max_position_size_pct=0.10, policy_version="v1.0.0")
        resp = gateway.submit_proposal(sub_req, risk_policy=policy)

        assert resp.status == "REJECTED"
        assert resp.risk_decision["decision"] == "REJECTED"

    def test_adversarial_kill_switch_active_blocks_hermes_proposal(self):
        """CRITICAL INVARIANT TEST: Hermes cannot trade if Kill Switch is active."""
        gateway = HermesGateway()
        payload = create_valid_proposal_dict()

        sub_req = ProposalSubmissionRequest(
            proposal_data=payload,
            model_version="hermes-3-70b-v1.0",
        )

        system_state = SystemState(
            trading_mode=TradingMode.PAPER,
            kill_switch=KillSwitchState.HARD_KILL,  # Kill switch engaged
            exchange_connected=True,
            data_healthy=True,
            last_heartbeat=_NOW,
        )

        resp = gateway.submit_proposal(sub_req, system_state=system_state)
        assert resp.status == "REJECTED"
        assert resp.risk_decision["decision"] == "FREEZE"


class TestKnowledgeTemporalProvenance:
    def test_temporal_provenance_prevents_future_leakage(self):
        kt = KnowledgeTools()
        # Evaluation at 2026-08-30
        as_of_time = datetime(2026, 8, 30, 12, 0, 0, tzinfo=UTC)

        results = kt.search_knowledge(query="BTC", as_of=as_of_time)
        # Should include historical note (available 2026-08-20)
        # Should EXCLUDE future note (available 2099-01-01)
        note_ids = [r["note_id"] for r in results]
        assert "NOTE-20260820-001" in note_ids
        assert "NOTE-FUTURE-LEAK" not in note_ids


class TestAuditLoggingIntegration:
    def test_hermes_gateway_logs_audit_events_to_sqlite(self, tmp_db_path):
        db = SQLiteManager(tmp_db_path)
        db.connect()
        MigrationRunner(db).run()

        event_repo = SystemEventRepository(db)
        gateway = HermesGateway(system_event_repo=event_repo)

        # 1. Execute tool
        req = ToolRequest(
            request_id="REQ-AUDIT-001",
            tool_name="get_portfolio",
            parameters={},
        )
        gateway.execute_tool(req)

        # 2. Submit proposal
        payload = create_valid_proposal_dict()
        sub_req = ProposalSubmissionRequest(
            proposal_data=payload,
            model_version="hermes-3-70b-v1.0",
        )
        gateway.submit_proposal(sub_req)

        # Verify audit logs in database
        events = event_repo.get_by_component("HermesGateway")
        assert len(events) >= 3

        db.close()
