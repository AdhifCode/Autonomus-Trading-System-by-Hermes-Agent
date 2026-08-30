"""Tests for core.errors — exception hierarchy and error codes."""

from __future__ import annotations

from core.errors import (
    ConfigError,
    DatabaseError,
    DuplicateOrderError,
    ErrorCode,
    ExchangeDisconnectedError,
    ExchangeTimeoutError,
    ExecutionError,
    HermesBlockedOperationError,
    HermesInvalidProposalError,
    HermesUnauthorizedError,
    InvalidStateTransitionError,
    MigrationError,
    RiskError,
    TradingSystemError,
)


class TestErrorCodes:
    """Verify error code completeness and format."""

    def test_risk_codes_count(self):
        """All 20 risk validators have error codes."""
        risk_codes = [c for c in ErrorCode if c.value.startswith("RISK_")]
        assert len(risk_codes) == 20

    def test_exec_codes_count(self):
        exec_codes = [c for c in ErrorCode if c.value.startswith("EXEC_")]
        assert len(exec_codes) == 5

    def test_sys_codes_count(self):
        sys_codes = [c for c in ErrorCode if c.value.startswith("SYS_")]
        assert len(sys_codes) == 7

    def test_hermes_codes_count(self):
        hermes_codes = [c for c in ErrorCode if c.value.startswith("HERMES_")]
        assert len(hermes_codes) == 3

    def test_all_codes_are_unique(self):
        values = [c.value for c in ErrorCode]
        assert len(values) == len(set(values))

    def test_code_format(self):
        """All codes follow PREFIX_NNN format."""
        for code in ErrorCode:
            parts = code.value.split("_")
            assert len(parts) == 2
            assert parts[1].isdigit()
            assert len(parts[1]) == 3


class TestExceptionHierarchy:
    """Verify exception inheritance chain."""

    def test_base_exception(self):
        err = TradingSystemError("test", code=ErrorCode.SYS_CONFIG_ERROR)
        assert str(err) == "test"
        assert err.code == ErrorCode.SYS_CONFIG_ERROR
        assert err.details == {}

    def test_base_exception_with_details(self):
        err = TradingSystemError("test", details={"key": "value"})
        assert err.details == {"key": "value"}

    def test_config_error_inherits(self):
        err = ConfigError("bad config")
        assert isinstance(err, TradingSystemError)
        assert err.code == ErrorCode.SYS_CONFIG_ERROR

    def test_database_error_inherits(self):
        err = DatabaseError("db failed")
        assert isinstance(err, TradingSystemError)
        assert err.code == ErrorCode.SYS_DATABASE_ERROR

    def test_migration_error_inherits(self):
        err = MigrationError("migration failed")
        assert isinstance(err, DatabaseError)
        assert isinstance(err, TradingSystemError)

    def test_risk_error_inherits(self):
        err = RiskError("risk violation")
        assert isinstance(err, TradingSystemError)

    def test_execution_error_inherits(self):
        err = ExecutionError("exec failed")
        assert isinstance(err, TradingSystemError)

    def test_duplicate_order_error(self):
        err = DuplicateOrderError("TRD-20260828-000001")
        assert isinstance(err, ExecutionError)
        assert err.code == ErrorCode.EXEC_DUPLICATE_ORDER
        assert err.details["order_id"] == "TRD-20260828-000001"
        assert "TRD-20260828-000001" in str(err)

    def test_invalid_state_transition_error(self):
        err = InvalidStateTransitionError("APPROVED", "RECONCILED")
        assert err.code == ErrorCode.EXEC_INVALID_TRANSITION
        assert "APPROVED" in str(err)
        assert "RECONCILED" in str(err)

    def test_exchange_disconnected_error(self):
        err = ExchangeDisconnectedError()
        assert err.code == ErrorCode.SYS_EXCHANGE_DISCONNECTED

    def test_exchange_timeout_error(self):
        err = ExchangeTimeoutError()
        assert err.code == ErrorCode.EXEC_EXCHANGE_TIMEOUT

    def test_hermes_unauthorized_error(self):
        err = HermesUnauthorizedError("submit_order")
        assert err.code == ErrorCode.HERMES_UNAUTHORIZED
        assert err.details["operation"] == "submit_order"

    def test_hermes_blocked_operation_error(self):
        err = HermesBlockedOperationError("modify_risk_policy")
        assert err.code == ErrorCode.HERMES_BLOCKED_OPERATION
        assert "modify_risk_policy" in str(err)

    def test_hermes_invalid_proposal_error(self):
        err = HermesInvalidProposalError("missing field symbol")
        assert err.code == ErrorCode.HERMES_INVALID_PROPOSAL
        assert "missing field symbol" in str(err)
