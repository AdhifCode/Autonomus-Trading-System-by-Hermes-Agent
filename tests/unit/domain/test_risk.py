"""Tests for core.domain.risk — RiskDecision, RiskViolation, RiskPolicy models."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from core.domain.risk import RiskDecision, RiskPolicy, RiskViolation

_NOW = datetime(2026, 8, 28, 12, 0, 0, tzinfo=UTC)


# ---- RiskViolation ----


def _violation(**kw):
    d = {
        "validator": "position_size",
        "rule": "Max position size 5%",
        "current_value": 0.08,
        "limit_value": 0.05,
        "message": "Position size 8% exceeds limit 5%",
    }
    d.update(kw)
    return d


class TestRiskViolationValid:
    def test_basic(self):
        v = RiskViolation(**_violation())
        assert v.validator == "position_size"

    def test_string_values(self):
        v = RiskViolation(
            **_violation(
                current_value="SOFT_KILL",
                limit_value="ACTIVE",
            )
        )
        assert v.current_value == "SOFT_KILL"


class TestRiskViolationInvalid:
    def test_empty_validator(self):
        with pytest.raises(ValidationError):
            RiskViolation(**_violation(validator=""))

    def test_empty_rule(self):
        with pytest.raises(ValidationError):
            RiskViolation(**_violation(rule=""))

    def test_empty_message(self):
        with pytest.raises(ValidationError):
            RiskViolation(**_violation(message=""))


# ---- RiskDecision ----


def _decision(**kw):
    d = {
        "decision_id": "RD-001",
        "proposal_id": "PRP-20260828-000001",
        "decision": "APPROVED",
        "violations": [],
        "policy_version": "1.4",
        "timestamp": _NOW.isoformat(),
        "computation_ms": 2.5,
    }
    d.update(kw)
    return d


class TestRiskDecisionValid:
    def test_approved(self):
        rd = RiskDecision(**_decision())
        assert rd.is_approved
        assert not rd.is_rejected
        assert not rd.is_freeze

    def test_rejected(self):
        rd = RiskDecision(
            **_decision(
                decision="REJECTED",
                violations=[_violation()],
            )
        )
        assert rd.is_rejected
        assert not rd.is_approved

    def test_freeze(self):
        rd = RiskDecision(
            **_decision(
                decision="FREEZE",
                violations=[_violation(validator="kill_switch")],
            )
        )
        assert rd.is_freeze


class TestRiskDecisionInvalid:
    def test_invalid_decision_type(self):
        with pytest.raises(ValidationError):
            RiskDecision(**_decision(decision="MAYBE"))

    def test_invalid_proposal_id_format(self):
        with pytest.raises(ValidationError):
            RiskDecision(**_decision(proposal_id="BAD-ID"))

    def test_empty_decision_id(self):
        with pytest.raises(ValidationError):
            RiskDecision(**_decision(decision_id=""))

    def test_empty_policy_version(self):
        with pytest.raises(ValidationError):
            RiskDecision(**_decision(policy_version=""))

    def test_negative_computation_ms(self):
        with pytest.raises(ValidationError):
            RiskDecision(**_decision(computation_ms=-1.0))


class TestRiskDecisionSerialization:
    def test_json_round_trip(self):
        original = RiskDecision(
            **_decision(
                decision="REJECTED",
                violations=[_violation()],
            )
        )
        restored = RiskDecision.model_validate_json(original.model_dump_json())
        assert restored == original


# ---- RiskPolicy ----


def _policy(**kw):
    d = {"policy_version": "1.4"}
    d.update(kw)
    return d


class TestRiskPolicyDefaults:
    def test_defaults(self):
        rp = RiskPolicy(**_policy())
        assert rp.max_position_size_pct == 0.05
        assert rp.max_portfolio_exposure_pct == 0.50
        assert rp.max_daily_loss_pct == 0.03
        assert rp.max_drawdown_pct == 0.15
        assert rp.max_order_notional == 10000.0
        assert rp.max_concurrent_positions == 5
        assert rp.max_leverage == 3.0
        assert rp.stale_data_timeout_seconds == 60
        assert rp.macro_event_restriction is False


class TestRiskPolicyBoundaries:
    def test_position_size_zero_rejected(self):
        with pytest.raises(ValidationError):
            RiskPolicy(**_policy(max_position_size_pct=0))

    def test_position_size_over_one_rejected(self):
        with pytest.raises(ValidationError):
            RiskPolicy(**_policy(max_position_size_pct=1.01))

    def test_position_size_max(self):
        rp = RiskPolicy(**_policy(max_position_size_pct=1.0))
        assert rp.max_position_size_pct == 1.0

    def test_daily_loss_boundary(self):
        rp = RiskPolicy(**_policy(max_daily_loss_pct=1.0))
        assert rp.max_daily_loss_pct == 1.0

    def test_max_concurrent_zero_rejected(self):
        with pytest.raises(ValidationError):
            RiskPolicy(**_policy(max_concurrent_positions=0))

    def test_stale_timeout_zero_rejected(self):
        with pytest.raises(ValidationError):
            RiskPolicy(**_policy(stale_data_timeout_seconds=0))


class TestRiskPolicyNoKillSwitch:
    """kill_switch and trading_mode must NOT be in RiskPolicy (architecture §6)."""

    def test_no_kill_switch_field(self):
        assert "kill_switch" not in RiskPolicy.model_fields

    def test_no_trading_mode_field(self):
        assert "trading_mode" not in RiskPolicy.model_fields


class TestRiskPolicySerialization:
    def test_json_round_trip(self):
        original = RiskPolicy(**_policy())
        restored = RiskPolicy.model_validate_json(original.model_dump_json())
        assert restored == original
