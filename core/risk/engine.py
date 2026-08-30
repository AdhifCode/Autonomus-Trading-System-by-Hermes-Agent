"""Deterministic Risk Engine.

Evaluates TradeProposal against MarketState, PortfolioState, RiskPolicy, and SystemState.
Outputs APPROVED, REJECTED, or FREEZE with structured RiskViolation details.

Architecture Invariants:
1. Risk Engine is the primary financial safety boundary (architecture §6).
2. Identical inputs produce identical decisions (deterministic).
3. LLM confidence is metadata ONLY — it never overrides risk.
4. Kill switch or freeze conditions take absolute precedence over approval or rejection.

See architecture.md §6, §7 and implementation_spec.md §3, §4.
"""

from __future__ import annotations

import time
from datetime import UTC, datetime

from core.domain.enums import RiskDecisionType
from core.domain.market_state import MarketState
from core.domain.portfolio import PortfolioState
from core.domain.risk import RiskDecision, RiskPolicy, RiskViolation
from core.domain.system_state import SystemState
from core.domain.trade_proposal import TradeProposal
from core.logging import get_logger
from core.risk.validators import ALL_VALIDATORS, validate_kill_switch

logger = get_logger(__name__)


class RiskEngine:
    """Deterministic financial safety risk engine."""

    def __init__(self, policy: RiskPolicy) -> None:
        self.policy = policy

    def evaluate(
        self,
        proposal: TradeProposal,
        market: MarketState,
        portfolio: PortfolioState,
        system: SystemState,
        timestamp: datetime | None = None,
    ) -> RiskDecision:
        """Evaluate a TradeProposal against all 20 risk rules deterministically.

        Args:
            proposal: Structured trade proposal from Hermes.
            market: Current market state snapshot.
            portfolio: Current portfolio state snapshot.
            system: Current system state snapshot.
            timestamp: Evaluation timestamp (defaults to current UTC time).

        Returns:
            RiskDecision (APPROVED, REJECTED, or FREEZE).
        """
        start_time = time.perf_counter()
        now = timestamp or datetime.now(tz=UTC)

        violations: list[RiskViolation] = []

        # Run all 20 validators in deterministic fixed order
        for validator_fn in ALL_VALIDATORS:
            violation = validator_fn(proposal, market, portfolio, self.policy, system)
            if violation is not None:
                violations.append(violation)

        # Check for kill switch / FREEZE condition
        kill_switch_violation = validate_kill_switch(
            proposal, market, portfolio, self.policy, system
        )
        if kill_switch_violation is not None:
            decision_type = RiskDecisionType.FREEZE
        elif violations:
            decision_type = RiskDecisionType.REJECTED
        else:
            decision_type = RiskDecisionType.APPROVED

        computation_ms = (time.perf_counter() - start_time) * 1000.0

        # Construct deterministic decision ID
        # Format: RD-YYYYMMDD-HHMMSS-symbol
        date_str = now.strftime("%Y%m%d-%H%M%S")
        decision_id = f"RD-{date_str}-{proposal.proposal_id[-6:]}"

        decision = RiskDecision(
            decision_id=decision_id,
            proposal_id=proposal.proposal_id,
            decision=decision_type,
            violations=violations,
            policy_version=self.policy.policy_version,
            timestamp=now,
            computation_ms=round(computation_ms, 3),
        )

        logger.info(
            f"Risk evaluation complete for {proposal.proposal_id}: {decision_type.value}",
            extra={
                "metadata": {
                    "proposal_id": proposal.proposal_id,
                    "decision": decision_type.value,
                    "violations_count": len(violations),
                    "computation_ms": decision.computation_ms,
                }
            },
        )

        return decision


__all__ = ["RiskEngine"]
