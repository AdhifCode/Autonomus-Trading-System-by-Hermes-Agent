"""Unit and Integration Tests for Phase 17: Limited Live Preparation."""

from __future__ import annotations

import pytest
from core.prep.limited_live import LimitedLivePrepEngine, LimitedLivePrepTelemetry


def test_limited_live_prep_engine_run():
    """Test full execution of Limited Live Preparation verification engine."""
    engine = LimitedLivePrepEngine()
    telemetry: LimitedLivePrepTelemetry = engine.run_preparation_and_verification()

    # Verify all 13 operational items
    assert telemetry.production_config_verified is True
    assert telemetry.secret_management_verified is True
    assert telemetry.exchange_credentials_verified is True
    assert telemetry.monitoring_verified is True
    assert telemetry.alerting_verified is True
    assert telemetry.backup_verified is True
    assert telemetry.kill_switch_verified is True
    assert telemetry.manual_emergency_controls_verified is True
    assert telemetry.capital_limits_verified is True
    assert telemetry.position_limits_verified is True
    assert telemetry.audit_logging_verified is True
    assert telemetry.reconciliation_verified is True
    assert telemetry.recovery_verified is True

    # Verify 5 AI Hard Prohibitions
    assert telemetry.ai_cannot_increase_capital is True
    assert telemetry.ai_cannot_increase_risk_limits is True
    assert telemetry.ai_cannot_disable_kill_switch is True
    assert telemetry.ai_cannot_activate_live is True
    assert telemetry.ai_cannot_modify_production_strategy is True

    # Human authorization MUST remain False
    assert telemetry.human_authorization_granted is False


def test_limited_live_runbook_generation():
    """Test generation of official LIMITED_LIVE_RUNBOOK.md content."""
    engine = LimitedLivePrepEngine()
    engine.run_preparation_and_verification()
    runbook_md = engine.generate_runbook_markdown()

    assert "# Trader Control Center — Phase 17: Limited Live Runbook" in runbook_md
    assert "LIMITED_LIVE" in runbook_md
    assert "13 Operational Verification Checklist" in runbook_md
    assert "5 AI Hard Prohibitions" in runbook_md
    assert "Human Authorization Sign-Off" in runbook_md
    assert "Do NOT activate LIVE trading" in runbook_md
