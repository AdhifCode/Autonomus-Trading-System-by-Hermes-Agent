"""Execution Service package.

Manages trade execution, idempotency, state transitions, exchange interactions,
and reconciliation.
"""

from core.execution.idempotency import IdempotencyManager
from core.execution.reconciliation import (
    Discrepancy,
    ReconciliationEngine,
    ReconciliationReport,
)
from core.execution.service import ExecutionResult, ExecutionService
from core.execution.state_machine import VALID_TRANSITIONS, ExecutionStateMachine

__all__ = [
    "VALID_TRANSITIONS",
    "Discrepancy",
    "ExecutionResult",
    "ExecutionService",
    "ExecutionStateMachine",
    "IdempotencyManager",
    "ReconciliationEngine",
    "ReconciliationReport",
]
