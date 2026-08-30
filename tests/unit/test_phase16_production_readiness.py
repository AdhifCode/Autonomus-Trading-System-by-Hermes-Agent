"""Unit and Integration Tests for Phase 16: Production Readiness Review."""

from __future__ import annotations

import pytest
from core.audit.production_readiness import (
    ProductionReadinessAuditEngine,
    ProductionReadinessTelemetry,
)


def test_production_readiness_audit_run():
    """Test full execution of 5-dimension architecture and implementation audit."""
    engine = ProductionReadinessAuditEngine()
    telemetry: ProductionReadinessTelemetry = engine.run_full_audit()

    # Strict Production Readiness Invariant: ZERO CRITICAL and ZERO HIGH issues
    assert telemetry.critical_count == 0
    assert telemetry.high_count == 0

    # Assert 5 Audit Dimensions PASSED
    assert telemetry.trading_correctness_pass is True
    assert telemetry.execution_pass is True
    assert telemetry.risk_pass is True
    assert telemetry.ai_boundary_pass is True
    assert telemetry.operations_pass is True


def test_production_readiness_report_generation():
    """Test generation of official PRODUCTION_READINESS_REPORT.md content."""
    engine = ProductionReadinessAuditEngine()
    engine.run_full_audit()
    report_md = engine.generate_report_markdown()

    assert "# Trader Control Center — Phase 16: Production Readiness Review" in report_md
    assert "CRITICAL Issues**: `0`" in report_md
    assert "HIGH Issues**: `0`" in report_md
    assert "TRADING CORRECTNESS" in report_md
    assert "EXECUTION" in report_md
    assert "RISK" in report_md
    assert "AI & HERMES INTEGRATION" in report_md
    assert "OPERATIONS" in report_md
    assert "LIVE Mode State**: **INACTIVE**" or "LIVE Activation State" in report_md
