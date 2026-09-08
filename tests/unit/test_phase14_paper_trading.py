"""Unit and Integration Tests for Phase 14: Paper Trading Engine."""

from __future__ import annotations

import os
import tempfile

import pytest

from core.paper.runner import PaperTelemetry, PaperTradingEngine


@pytest.fixture
def paper_engine():
    """Setup temporary paper trading engine with isolated database and vault."""
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    db_path = tmp_db.name

    tmp_vault = tempfile.TemporaryDirectory()
    vault_path = tmp_vault.name

    engine = PaperTradingEngine(
        db_path=db_path,
        vault_path=vault_path,
        simulated_latency_ms=50.0,
    )

    yield engine

    if os.path.exists(db_path):
        os.unlink(db_path)
    tmp_vault.cleanup()


def test_paper_trading_engine_full_run(paper_engine: PaperTradingEngine):
    """Test full multi-cycle paper trading execution session."""
    telemetry: PaperTelemetry = paper_engine.run_paper_session(num_cycles=25, random_seed=42)

    assert telemetry.total_signals_ingested == 25
    assert telemetry.total_proposals_generated == 25
    assert telemetry.proposals_approved > 0
    assert (
        telemetry.proposals_rejected > 0
    )  # Position size injection test (requested_pct=0.50 at cycle 15)
    assert telemetry.total_orders_submitted > 0
    assert telemetry.total_orders_filled > 0
    assert telemetry.fees_paid >= 0.0
    assert telemetry.slippage_cost >= 0.0
    assert telemetry.latencies_ms
    assert telemetry.avg_latency_ms() > 0.0
    assert telemetry.reconciliations_count >= 2
    assert telemetry.reconciliation_mismatches_count == 0


def test_paper_trading_safety_invariants(paper_engine: PaperTradingEngine):
    """Test strict enforcement of PAPER mode safety invariants."""
    telemetry = paper_engine.run_paper_session(num_cycles=10, random_seed=123)

    # 1. Trading mode invariant
    assert telemetry.trading_mode == "PAPER"
    from adapters.exchange.mock.adapter import MockExchange

    assert isinstance(paper_engine.execution_service.exchange, MockExchange)

    # 2. Capital safety: initial balance = 50k
    assert telemetry.initial_balance == 50000.0

    # 3. Non-promotion invariant: Risk policy file policy_version remains unchanged
    assert paper_engine.risk_engine.policy.policy_version == "v1.4"


def test_paper_trading_report_generation(paper_engine: PaperTradingEngine):
    """Test PAPER_TRADING_REPORT.md generation."""
    paper_engine.run_paper_session(num_cycles=15, random_seed=99)
    report_md = paper_engine.generate_report_markdown()

    assert "# Trader Control Center — Phase 14: Paper Trading Telemetry & Audit Report" in report_md
    assert "`PAPER`" in report_md
    assert "$0.00" in report_md
    assert "NET Portfolio PnL" in report_md
    assert "Non-Promotion Safeguard" in report_md
