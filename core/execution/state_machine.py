"""Execution State Machine.

Enforces valid execution state transitions and emergency recovery paths per architecture §12
and implementation_spec §5.

Critical invariant: RISK_REJECTED and EXCHANGE_REJECTED are separate, distinct states.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from core.domain.enums import ExecutionState
from core.errors import InvalidStateTransitionError
from core.logging import get_logger

if TYPE_CHECKING:
    from adapters.repositories.sqlite_repos import StateTransitionRepository

logger = get_logger(__name__)


# Canonical valid state transition map
VALID_TRANSITIONS: dict[ExecutionState, Sequence[ExecutionState]] = {
    ExecutionState.PROPOSAL_CREATED: (ExecutionState.RISK_PENDING,),
    ExecutionState.RISK_PENDING: (ExecutionState.APPROVED, ExecutionState.RISK_REJECTED),
    ExecutionState.APPROVED: (ExecutionState.EXECUTION_PENDING,),
    ExecutionState.EXECUTION_PENDING: (ExecutionState.ORDER_SUBMITTED,),
    ExecutionState.ORDER_SUBMITTED: (
        ExecutionState.PARTIAL,
        ExecutionState.FILLED,
        ExecutionState.EXCHANGE_REJECTED,
    ),
    ExecutionState.PARTIAL: (ExecutionState.FILLED,),
    ExecutionState.FILLED: (ExecutionState.POSITION_ACTIVE,),
    ExecutionState.POSITION_ACTIVE: (ExecutionState.EXIT_PENDING,),
    ExecutionState.EXIT_PENDING: (ExecutionState.POSITION_CLOSED,),
    ExecutionState.POSITION_CLOSED: (ExecutionState.RECONCILED, ExecutionState.RECONCILING),
    # Emergency & Recovery Path
    ExecutionState.UNKNOWN: (ExecutionState.FREEZE,),
    ExecutionState.FREEZE: (ExecutionState.RECONCILING,),
    ExecutionState.RECONCILING: (ExecutionState.RESOLVED,),
    ExecutionState.RISK_REJECTED: (),
    ExecutionState.EXCHANGE_REJECTED: (),
    ExecutionState.RESOLVED: (),
}


class ExecutionStateMachine:
    """State machine managing trade and order execution lifecycle transitions."""

    def __init__(
        self,
        entity_id: str,
        entity_type: str = "order",
        initial_state: ExecutionState = ExecutionState.PROPOSAL_CREATED,
        repo: StateTransitionRepository | None = None,
    ) -> None:
        self.entity_id = entity_id
        self.entity_type = entity_type
        self.current_state = initial_state
        self._repo = repo

    def can_transition_to(self, target_state: ExecutionState) -> bool:
        """Check if transition from current state to target state is valid.

        ANY state can transition to UNKNOWN (emergency path).
        """
        if target_state == ExecutionState.UNKNOWN:
            return True

        allowed = VALID_TRANSITIONS.get(self.current_state, ())
        return target_state in allowed

    def transition_to(
        self,
        target_state: ExecutionState,
        reason: str | None = None,
    ) -> ExecutionState:
        """Transition state machine to target_state.

        Raises:
            InvalidStateTransitionError: If transition is forbidden.
        """
        if not self.can_transition_to(target_state):
            logger.error(
                f"Forbidden state transition attempted for {self.entity_id}: "
                f"{self.current_state.value} → {target_state.value}"
            )
            raise InvalidStateTransitionError(
                from_state=self.current_state.value,
                to_state=target_state.value,
            )

        from_state = self.current_state
        self.current_state = target_state

        logger.info(
            f"Execution transition [{self.entity_type} {self.entity_id}]: "
            f"{from_state.value} → {target_state.value} (reason: {reason or 'N/A'})"
        )

        if self._repo is not None:
            self._repo.record_transition(
                entity_type=self.entity_type,
                entity_id=self.entity_id,
                from_state=from_state.value,
                to_state=target_state.value,
                reason=reason,
            )

        return self.current_state


__all__ = ["VALID_TRANSITIONS", "ExecutionStateMachine"]
