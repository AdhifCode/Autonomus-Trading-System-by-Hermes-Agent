"""Unit tests for Operations Package (monitoring, health, kill switch, recovery, audit)."""

import tempfile
from datetime import UTC, datetime, timedelta

import pytest

from adapters.database.sqlite import SQLiteManager
from adapters.repositories.sqlite_repos import OrderRepository, SystemEventRepository
from core.domain.enums import EventType, KillSwitchState, Severity
from migrations.runner import MigrationRunner
from operations.audit import AuditLogger
from operations.health import HealthChecker, HealthStatus
from operations.kill_switch import KillSwitchManager
from operations.monitoring import OperationalMonitor
from operations.recovery import RecoveryOrchestrator


@pytest.fixture
def db():
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp:
        manager = SQLiteManager(db_path=tmp.name, wal_mode=True)
        manager.connect()
        MigrationRunner(manager).run()
        yield manager
        manager.close()


def test_kill_switch_manager(db):
    event_repo = SystemEventRepository(db)
    ks = KillSwitchManager(event_repo=event_repo)

    assert ks.is_active is True
    assert ks.state == KillSwitchState.ACTIVE

    # Engage kill switch
    ks.engage(reason="Emergency manual shutdown", source="admin")
    assert ks.is_active is False
    assert ks.state == KillSwitchState.HARD_KILL

    status = ks.get_status()
    assert status["state"] == "HARD_KILL"
    assert status["is_active"] is False

    # Check event was logged
    events = event_repo.get_all()
    assert len(events) >= 1
    assert any(e["event_type"] == EventType.KILL_SWITCH_ACTIVATED.value for e in events)

    # Release kill switch
    ks.release(reason="Operational verification complete", source="admin")
    assert ks.is_active is True
    assert ks.state == KillSwitchState.ACTIVE


def test_health_checker(db):
    checker = HealthChecker(db=db)

    # Database check
    db_health = checker.check_database()
    assert db_health.name == "database"
    assert db_health.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    # Market data check
    now = datetime.now(UTC)
    fresh_health = checker.check_market_data(last_data_timestamp=now, stale_timeout_sec=5.0)
    assert fresh_health.status == HealthStatus.HEALTHY

    stale_health = checker.check_market_data(
        last_data_timestamp=now - timedelta(seconds=15), stale_timeout_sec=5.0
    )
    assert stale_health.status == HealthStatus.DEGRADED

    # Exchange check
    ex_health = checker.check_exchange(is_connected=True, last_heartbeat_age_sec=5.0)
    assert ex_health.status == HealthStatus.HEALTHY

    disc_health = checker.check_exchange(is_connected=False)
    assert disc_health.status == HealthStatus.UNHEALTHY

    # System overall
    report = checker.evaluate_system_health(last_data_ts=now, exchange_connected=True)
    assert report.is_healthy is True
    report_dict = report.to_dict()
    assert "overall_status" in report_dict
    assert len(report_dict["components"]) == 3


def test_operational_monitor():
    monitor = OperationalMonitor()

    monitor.telemetry.record_proposal("APPROVED")
    monitor.telemetry.record_proposal("APPROVED")
    monitor.telemetry.record_proposal("REJECTED")

    assert monitor.telemetry.proposals_received == 3
    assert monitor.telemetry.proposals_approved == 2
    assert monitor.telemetry.proposals_rejected == 1
    assert round(monitor.telemetry.approval_rate_pct, 1) == 66.7

    monitor.telemetry.record_order("FILLED", latency_ms=120.0)
    monitor.telemetry.record_order("FILLED", latency_ms=180.0)
    monitor.telemetry.record_order("CANCELLED", latency_ms=50.0)

    assert monitor.telemetry.orders_submitted == 3
    assert monitor.telemetry.orders_filled == 2
    assert monitor.telemetry.avg_latency_ms == pytest.approx(116.67, 0.1)

    metrics = monitor.get_metrics()
    assert metrics["orders_filled"] == 2
    assert metrics["fill_rate_pct"] == pytest.approx(66.67, 0.1)


def test_audit_logger(db):
    event_repo = SystemEventRepository(db)
    logger = AuditLogger(repo=event_repo)

    logger.record_event(
        event_type=EventType.STATE_TRANSITION,
        message="Mode set to PAPER",
        severity=Severity.INFO,
    )
    logger.record_event(
        event_type=EventType.SYSTEM_ERROR,
        message="Transient network glitch",
        severity=Severity.WARNING,
    )
    logger.record_event(
        event_type=EventType.KILL_SWITCH_ACTIVATED,
        message="Critical financial discrepancy",
        severity=Severity.CRITICAL,
    )

    recent = logger.list_recent_events(limit=10)
    assert len(recent) == 3

    warnings_and_up = logger.filter_by_severity(min_severity=Severity.WARNING)
    assert len(warnings_and_up) == 2


@pytest.mark.asyncio
async def test_recovery_orchestrator(db):
    from adapters.exchange.mock.adapter import MockExchange
    from adapters.repositories.sqlite_repos import BalanceRepository, PositionRepository
    from core.execution.reconciliation import ReconciliationEngine

    order_repo = OrderRepository(db)
    pos_repo = PositionRepository(db)
    bal_repo = BalanceRepository(db)
    evt_repo = SystemEventRepository(db)

    mock_ex = MockExchange(balance=50_000.0)
    bal_repo.save("USDT", total=50_000.0, available=50_000.0, locked=0.0, source="local")

    recon_engine = ReconciliationEngine(
        exchange=mock_ex,
        order_repo=order_repo,
        position_repo=pos_repo,
        balance_repo=bal_repo,
        system_event_repo=evt_repo,
    )

    orchestrator = RecoveryOrchestrator(
        reconciliation_engine=recon_engine,
        order_repo=order_repo,
        event_repo=evt_repo,
    )

    # Execute clean recovery
    result = await orchestrator.execute_recovery(reason="Test recovery startup")
    assert result.success is True
    assert result.reconciliation_report is not None
    assert result.reconciliation_report.is_clean is True
    assert result.orders_recovered == 0

    # Verify audit event was logged
    events = evt_repo.get_all()
    assert any("Test recovery startup" in e.get("message", "") for e in events)

