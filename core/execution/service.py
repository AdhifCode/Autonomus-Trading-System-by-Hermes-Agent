"""Execution Service.

Manages trade authorization, order lifecycle, idempotency, state transitions,
exchange submission, and recovery on timeouts/network errors.

Pipeline: TradeProposal → Risk Engine → Authorization → Execution Service → Exchange Adapter

See architecture §12, §13 and implementation_spec §5, §8.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from adapters.exchange.base import ExchangeAdapter
from adapters.repositories.sqlite_repos import (
    AuthorizationRepository,
    FillRepository,
    OrderRepository,
    PositionRepository,
    StateTransitionRepository,
    TradeRepository,
)
from core.domain.enums import (
    ExecutionState,
    OrderSide,
    OrderStatus,
    PositionSide,
    RiskDecisionType,
)
from core.domain.fill import Fill
from core.domain.order import Order
from core.domain.position import Position
from core.domain.risk import RiskDecision
from core.domain.trade_proposal import TradeProposal
from core.errors import (
    ExchangeDisconnectedError,
    ExchangeError,
    ExchangeTimeoutError,
    ExecutionError,
    RecordNotFoundError,
)
from core.execution.idempotency import IdempotencyManager
from core.execution.state_machine import ExecutionStateMachine
from core.logging import get_logger

if TYPE_CHECKING:
    from adapters.repositories.sqlite_repos import BalanceRepository, SystemEventRepository

logger = get_logger(__name__)


class ExecutionResult:
    """Encapsulates the outcome of an execution attempt."""

    def __init__(
        self,
        success: bool,
        client_order_id: str,
        execution_state: ExecutionState,
        order: Order | None = None,
        position: Position | None = None,
        error_message: str | None = None,
    ) -> None:
        self.success = success
        self.client_order_id = client_order_id
        self.execution_state = execution_state
        self.order = order
        self.position = position
        self.error_message = error_message


class ExecutionService:
    """Orchestrates order execution, state machine transitions, and emergency recovery."""

    def __init__(
        self,
        exchange: ExchangeAdapter,
        order_repo: OrderRepository,
        trade_repo: TradeRepository,
        position_repo: PositionRepository,
        fill_repo: FillRepository,
        auth_repo: AuthorizationRepository,
        state_transition_repo: StateTransitionRepository,
        balance_repo: BalanceRepository | None = None,
        system_event_repo: SystemEventRepository | None = None,
        idempotency_manager: IdempotencyManager | None = None,
    ) -> None:
        self.exchange = exchange
        self.order_repo = order_repo
        self.trade_repo = trade_repo
        self.position_repo = position_repo
        self.fill_repo = fill_repo
        self.auth_repo = auth_repo
        self.state_transition_repo = state_transition_repo
        self.balance_repo = balance_repo
        self.system_event_repo = system_event_repo
        self.idempotency = idempotency_manager or IdempotencyManager()

    async def execute_proposal(
        self,
        proposal: TradeProposal,
        risk_decision: RiskDecision,
    ) -> ExecutionResult:
        """Execute an APPROVED TradeProposal through the safety pipeline.

        Flow:
            1. Validate risk decision is APPROVED.
            2. Record trade authorization in SQLite.
            3. Generate client_order_id and enforce idempotency.
            4. Transition state machine: PROPOSAL_CREATED → RISK_PENDING →
               APPROVED → EXECUTION_PENDING.
            5. Submit order to exchange.
            6. On timeout/network error: execute emergency query + reconcile recovery
               (never re-submit).
        """
        # Step 1: Validate Risk Decision
        if risk_decision.decision != RiskDecisionType.APPROVED:
            logger.warning(
                "Execution rejected for %s: Risk decision is %s",
                proposal.proposal_id,
                risk_decision.decision.value,
            )
            sm = ExecutionStateMachine(
                entity_id=proposal.proposal_id,
                entity_type="proposal",
                initial_state=ExecutionState.PROPOSAL_CREATED,
                repo=self.state_transition_repo,
            )
            sm.transition_to(ExecutionState.RISK_PENDING, reason="Evaluating risk decision")
            sm.transition_to(
                ExecutionState.RISK_REJECTED,
                reason=f"Risk engine decision: {risk_decision.decision.value}",
            )
            return ExecutionResult(
                success=False,
                client_order_id="",
                execution_state=ExecutionState.RISK_REJECTED,
                error_message=f"Risk engine rejected proposal: {risk_decision.decision.value}",
            )

        # Step 2: Record Authorization
        self.auth_repo.record_authorization(
            proposal_id=proposal.proposal_id,
            decision_id=risk_decision.decision_id,
            authorized_by="risk_engine",
            action="APPROVE_TRADE",
        )

        # Step 3: Generate Client Order ID & Check Idempotency
        client_order_id = self.idempotency.generate_client_order_id()
        self.idempotency.check_and_register(client_order_id, order_repo=self.order_repo)

        # Step 4: Initialize State Machine
        sm = ExecutionStateMachine(
            entity_id=client_order_id,
            entity_type="order",
            initial_state=ExecutionState.PROPOSAL_CREATED,
            repo=self.state_transition_repo,
        )
        sm.transition_to(ExecutionState.RISK_PENDING, reason="Risk evaluation completed")
        sm.transition_to(ExecutionState.APPROVED, reason="Risk decision APPROVED")
        sm.transition_to(ExecutionState.EXECUTION_PENDING, reason="Preparing exchange order")

        now = datetime.now(tz=UTC)
        # Approximate order quantity based on entry price (or 1.0 default for test unit consistency)
        price = proposal.entry.price
        qty = round(1000.0 / price, 4) if price > 0 else 1.0

        order = Order(
            client_order_id=client_order_id,
            proposal_id=proposal.proposal_id,
            symbol=proposal.symbol,
            side=proposal.side,
            order_type=proposal.entry.order_type,
            quantity=qty,
            price=proposal.entry.price,
            stop_price=proposal.stop_loss.price if proposal.stop_loss else None,
            status=OrderStatus.PENDING,
            created_at=now,
            updated_at=now,
        )

        # Save order initial PENDING state in SQLite
        self.order_repo.save_order(order)

        # Step 5: Submit Order to Exchange with Timeout Recovery Protection
        try:
            sm.transition_to(ExecutionState.ORDER_SUBMITTED, reason="Submitted to exchange")
            exchange_order = await self.exchange.submit_order(order)
            self.order_repo.save_order(exchange_order)

            return self._handle_exchange_response(exchange_order, sm)

        except (ExchangeTimeoutError, ExchangeDisconnectedError) as err:
            logger.error(
                f"Exchange submission exception for {client_order_id}: {err}. "
                "Executing recovery query protocol (NO BLIND RESUBMIT)."
            )
            return await self._handle_timeout_recovery(client_order_id, order, sm, str(err))

        except ExchangeError as err:
            logger.error(f"Exchange rejected order {client_order_id}: {err}")
            sm.transition_to(
                ExecutionState.EXCHANGE_REJECTED,
                reason=f"Exchange rejection: {err}",
            )
            self.order_repo.update_order_status(client_order_id, OrderStatus.REJECTED)
            return ExecutionResult(
                success=False,
                client_order_id=client_order_id,
                execution_state=ExecutionState.EXCHANGE_REJECTED,
                error_message=str(err),
            )

    def _handle_exchange_response(
        self,
        exchange_order: Order,
        sm: ExecutionStateMachine,
    ) -> ExecutionResult:
        """Handle successful response returned by exchange submission."""
        now = datetime.now(tz=UTC)

        if exchange_order.status == OrderStatus.FILLED:
            sm.transition_to(ExecutionState.FILLED, reason="Order fully filled")
            sm.transition_to(ExecutionState.POSITION_ACTIVE, reason="Position created")

            # Save Fill in SQLite
            fill_id = f"FIL-{exchange_order.client_order_id[-6:]}"
            fill = Fill(
                fill_id=fill_id,
                order_id=exchange_order.client_order_id,
                symbol=exchange_order.symbol,
                side=exchange_order.side,
                quantity=exchange_order.filled_quantity,
                price=exchange_order.average_fill_price or exchange_order.price or 50000.0,
                fee=1.0,
                fee_currency="USDT",
                timestamp=now,
            )
            self.fill_repo.save_fill(fill)

            # Create & Save Position in SQLite
            pos_side = (
                PositionSide.LONG if exchange_order.side == OrderSide.BUY else PositionSide.SHORT
            )
            pos_id = f"POS-{exchange_order.symbol}"
            position = Position(
                position_id=pos_id,
                symbol=exchange_order.symbol,
                side=pos_side,
                quantity=exchange_order.filled_quantity,
                entry_price=fill.price,
                current_price=fill.price,
                strategy_id="strat_active",
                strategy_version="1.0",
                opened_at=now,
                updated_at=now,
            )
            self.position_repo.save_position(position)

            return ExecutionResult(
                success=True,
                client_order_id=exchange_order.client_order_id,
                execution_state=ExecutionState.POSITION_ACTIVE,
                order=exchange_order,
                position=position,
            )

        elif exchange_order.status == OrderStatus.PARTIAL:
            sm.transition_to(ExecutionState.PARTIAL, reason="Order partially filled")

            fill_id = f"FIL-{exchange_order.client_order_id[-6:]}"
            fill = Fill(
                fill_id=fill_id,
                order_id=exchange_order.client_order_id,
                symbol=exchange_order.symbol,
                side=exchange_order.side,
                quantity=exchange_order.filled_quantity,
                price=exchange_order.average_fill_price or exchange_order.price or 50000.0,
                fee=0.5,
                fee_currency="USDT",
                timestamp=now,
            )
            self.fill_repo.save_fill(fill)

            return ExecutionResult(
                success=True,
                client_order_id=exchange_order.client_order_id,
                execution_state=ExecutionState.PARTIAL,
                order=exchange_order,
            )

        elif exchange_order.status == OrderStatus.REJECTED:
            sm.transition_to(ExecutionState.EXCHANGE_REJECTED, reason="Exchange rejected order")
            return ExecutionResult(
                success=False,
                client_order_id=exchange_order.client_order_id,
                execution_state=ExecutionState.EXCHANGE_REJECTED,
                error_message="Exchange rejected order",
            )

        return ExecutionResult(
            success=True,
            client_order_id=exchange_order.client_order_id,
            execution_state=ExecutionState.ORDER_SUBMITTED,
            order=exchange_order,
        )

    async def _handle_timeout_recovery(
        self,
        client_order_id: str,
        local_order: Order,
        sm: ExecutionStateMachine,
        error_details: str,
    ) -> ExecutionResult:
        """Required recovery pattern on timeout/network error:

        submit order → timeout → query exchange → reconcile → determine actual state.
        NEVER re-submit blindly!
        """
        # Step 1: Transition to UNKNOWN state
        sm.transition_to(ExecutionState.UNKNOWN, reason=f"Timeout/Network error: {error_details}")

        # Step 2: Query Exchange to determine actual state
        try:
            ex_order = await self.exchange.get_order(client_order_id)
            logger.info(f"Recovery query found order on exchange: status={ex_order.status.value}")

            # Reconcile local state with exchange reality
            self.order_repo.save_order(ex_order)

            sm.transition_to(ExecutionState.FREEZE, reason="Freezing during timeout recovery")
            sm.transition_to(ExecutionState.RECONCILING, reason="Reconciling exchange state")
            sm.transition_to(ExecutionState.RESOLVED, reason="State reconciled with exchange")

            if ex_order.status == OrderStatus.FILLED:
                return ExecutionResult(
                    success=True,
                    client_order_id=client_order_id,
                    execution_state=ExecutionState.RESOLVED,
                    order=ex_order,
                )
            else:
                return ExecutionResult(
                    success=False,
                    client_order_id=client_order_id,
                    execution_state=ExecutionState.RESOLVED,
                    order=ex_order,
                    error_message=f"Order state recovered as {ex_order.status.value}",
                )

        except RecordNotFoundError:
            # Order never reached exchange before timeout
            logger.info(f"Recovery query confirmed order {client_order_id} not on exchange")
            self.order_repo.update_order_status(client_order_id, OrderStatus.EXPIRED)

            sm.transition_to(ExecutionState.FREEZE, reason="Freezing after missing order query")
            sm.transition_to(ExecutionState.RECONCILING, reason="Reconciling missing order")
            sm.transition_to(ExecutionState.RESOLVED, reason="Resolved as missing/expired")

            return ExecutionResult(
                success=False,
                client_order_id=client_order_id,
                execution_state=ExecutionState.RESOLVED,
                error_message="Order timed out before reaching exchange",
            )

        except Exception as query_err:
            logger.error(f"Recovery query failed for {client_order_id}: {query_err}")
            sm.transition_to(ExecutionState.FREEZE, reason=f"Recovery query failed: {query_err}")

            return ExecutionResult(
                success=False,
                client_order_id=client_order_id,
                execution_state=ExecutionState.FREEZE,
                error_message=f"Recovery failed, system frozen: {query_err}",
            )

    async def cancel_order(self, client_order_id: str) -> bool:
        """Cancel an open order on exchange and update local SQLite state."""
        local_order = self.order_repo.get_by_id(client_order_id)
        if local_order is None:
            raise ExecutionError(f"Order {client_order_id} not found in database")

        cancelled = await self.exchange.cancel_order(client_order_id)
        if cancelled:
            self.order_repo.update_order_status(client_order_id, OrderStatus.CANCELLED)
            logger.info(f"Order {client_order_id} cancelled successfully")
            return True
        return False


__all__ = ["ExecutionResult", "ExecutionService"]
