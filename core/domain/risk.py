"""Risk decision domain models.

RiskPolicy is file-based and immutable at runtime.
RiskDecision is the output of the Risk Engine evaluating a TradeProposal.

See implementation_spec.md §3, §4.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.domain.enums import RiskDecisionType


class RiskViolation(BaseModel):
    """A single risk rule violation.

    Used to explain why a proposal was rejected or to log
    risk warnings on approved proposals.
    """

    validator: str = Field(min_length=1, description="Validator name (e.g. position_size)")
    rule: str = Field(min_length=1, description="Human-readable rule description")
    current_value: float | str = Field(description="Actual value that triggered violation")
    limit_value: float | str = Field(description="Policy limit that was exceeded")
    message: str = Field(min_length=1)


class RiskDecision(BaseModel):
    """Output of the Risk Engine after evaluating a TradeProposal.

    INVARIANT: If decision is REJECTED or FREEZE, violations list must
    not be empty. If APPROVED, violations list should be empty.
    """

    decision_id: str = Field(min_length=1)
    proposal_id: str = Field(
        pattern=r"^PRP-\d{8}-\d{6}$",
        description="Must reference a valid proposal",
    )
    decision: RiskDecisionType
    violations: list[RiskViolation] = Field(default_factory=list)
    policy_version: str = Field(min_length=1)
    timestamp: datetime
    computation_ms: float = Field(ge=0)

    @property
    def is_approved(self) -> bool:
        """Return True if the proposal was approved."""
        return self.decision == RiskDecisionType.APPROVED

    @property
    def is_rejected(self) -> bool:
        """Return True if the proposal was rejected."""
        return self.decision == RiskDecisionType.REJECTED

    @property
    def is_freeze(self) -> bool:
        """Return True if the decision triggered a freeze."""
        return self.decision == RiskDecisionType.FREEZE


class RiskPolicy(BaseModel):
    """Risk policy configuration.

    Loaded from configs/risk.yaml. Immutable at runtime.
    kill_switch and trading_mode are read from SystemState, not here
    (architecture §6, AI_ENGINEERING_RULES §4).
    """

    # Position limits (as fraction of portfolio)
    max_position_size_pct: float = Field(default=0.05, gt=0, le=1.0)
    max_portfolio_exposure_pct: float = Field(default=0.50, gt=0, le=1.0)
    max_symbol_exposure_pct: float = Field(default=0.20, gt=0, le=1.0)
    max_strategy_exposure_pct: float = Field(default=0.30, gt=0, le=1.0)
    max_correlated_exposure_pct: float = Field(default=0.40, gt=0, le=1.0)

    # Loss limits (as fraction of portfolio)
    max_daily_loss_pct: float = Field(default=0.03, gt=0, le=1.0)
    max_weekly_loss_pct: float = Field(default=0.07, gt=0, le=1.0)
    max_drawdown_pct: float = Field(default=0.15, gt=0, le=1.0)

    # Order limits
    max_order_notional: float = Field(default=10000.0, gt=0)
    max_concurrent_positions: int = Field(default=5, gt=0)
    max_concurrent_orders: int = Field(default=10, gt=0)
    max_leverage: float = Field(default=3.0, gt=0)

    # Market quality thresholds
    max_spread_pct: float = Field(default=0.005, gt=0, le=1.0)
    max_slippage_pct: float = Field(default=0.01, gt=0, le=1.0)
    min_liquidity_usd: float = Field(default=50000.0, gt=0)

    # Data health
    stale_data_timeout_seconds: int = Field(default=60, gt=0)
    max_price_deviation_pct: float = Field(default=0.10, gt=0, le=1.0)

    # Restrictions
    macro_event_restriction: bool = False

    # Version tracking (architecture §21)
    policy_version: str = Field(min_length=1)
