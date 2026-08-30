"""Unit and Integration Tests for Phase 15: Testnet Validation Engine."""

from __future__ import annotations

import os
import tempfile
import pytest

from core.errors import ExchangeError
from core.testnet.runner import BinanceTestnetValidationEngine, BinanceTestnetTelemetry


@pytest.fixture
def testnet_engine():
    """Setup temporary testnet validation engine with isolated database."""
    tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    tmp_db.close()
    db_path = tmp_db.name

    engine = BinanceTestnetValidationEngine(db_path=db_path)

    yield engine

    if os.path.exists(db_path):
        os.unlink(db_path)


def test_testnet_validation_engine_full_run(testnet_engine: BinanceTestnetValidationEngine):
    """Test complete execution of 15 testnet validation modules and controlled failure suite."""
    telemetry: BinanceTestnetTelemetry = testnet_engine.run_validation_suite()

    # Verify all 15 validation modules
    assert telemetry.auth_verified is True
    assert telemetry.market_data_verified is True
    assert telemetry.order_submission_verified is True
    assert telemetry.cancellation_verified is True
    assert telemetry.partial_fills_verified is True
    assert telemetry.fills_verified is True
    assert telemetry.balances_verified is True
    assert telemetry.positions_verified is True
    assert telemetry.rest_verification_verified is True
    assert telemetry.websocket_verified is True
    assert telemetry.reconnect_verified is True
    assert telemetry.rate_limits_verified is True
    assert telemetry.timeout_behavior_verified is True
    assert telemetry.reconciliation_verified is True
    assert telemetry.restart_recovery_verified is True
    assert telemetry.live_protection_activated is True

    # Verify controlled failure scenarios
    assert "LIVE_PROTECTION_GUARD" in telemetry.controlled_failures_passed
    assert "RATE_LIMIT_OVERFLOW_429" in telemetry.controlled_failures_passed
    assert "REST_NETWORK_DISCONNECT" in telemetry.controlled_failures_passed
    assert "STATE_MISMATCH_DETECTION_AND_FREEZE" in telemetry.controlled_failures_passed


def test_testnet_report_generation(testnet_engine: BinanceTestnetValidationEngine):
    """Test generation of official TESTNET_VALIDATION_REPORT.md content."""
    testnet_engine.run_validation_suite()
    report_md = testnet_engine.generate_report_markdown()

    assert "# Trader Control Center — Phase 15: Testnet Validation Audit Report" in report_md
    assert "`TESTNET`" in report_md
    assert "Live Protection Guard" in report_md
    assert "15 Key Interface & Operational Validation Modules" in report_md
    assert "Controlled Failure Tests Summary" in report_md
    assert "Do NOT activate LIVE trading" in report_md
