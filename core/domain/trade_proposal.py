"""TradeProposal domain model.

The TradeProposal is the primary structured contract from Hermes to the
Risk Engine. It enforces strict schema validation via Pydantic.

Architecture invariants:
    - llm_confidence is metadata ONLY — it must never authorize trading
      or override risk decisions (architecture §4, §39).
    - proposal_id format: PRP-YYYYMMDD-NNNNNN
    - model_version required per architecture §21.

See implementation_spec.md §2.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from core.domain.enums import MarketRegime, OrderSide, OrderType


class EntrySpec(BaseModel):
    """Entry price and order type specification."""

    price: float = Field(gt=0, description="Entry price (must be positive)")
    order_type: OrderType


class StopLossSpec(BaseModel):
    """Stop-loss price specification."""

    price: float = Field(gt=0, description="Stop-loss price (must be positive)")


class TakeProfitSpec(BaseModel):
    """Take-profit price specification."""

    price: float = Field(gt=0, description="Take-profit price (must be positive)")


class PositionSizeSpec(BaseModel):
    """Requested position size as fraction of portfolio."""

    requested_pct: float = Field(
        gt=0,
        le=1.0,
        description="Fraction of portfolio (0 < pct <= 1.0)",
    )


class TradeProposal(BaseModel):
    """Structured trade proposal from Hermes to Risk Engine.

    Every field is validated. The Risk Engine evaluates this against
    RiskPolicy + MarketState + PortfolioState + SystemState.

    INVARIANT: llm_confidence is metadata only. It must never:
        - Determine position sizing
        - Override risk rejection
        - Authorize trading directly
    """

    proposal_id: str = Field(
        pattern=r"^PRP-\d{8}-\d{6}$",
        description="Format: PRP-YYYYMMDD-NNNNNN",
    )
    symbol: str = Field(min_length=1, description="Trading pair (e.g. BTCUSDT)")
    side: OrderSide
    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)
    model_version: str = Field(
        min_length=1,
        description="LLM model version (architecture §21)",
    )
    thesis: str = Field(
        min_length=10,
        description="Trading thesis (minimum 10 characters)",
    )
    entry: EntrySpec
    stop_loss: StopLossSpec
    take_profit: TakeProfitSpec
    position_size: PositionSizeSpec
    market_regime: MarketRegime
    invalidation_conditions: list[str] = Field(
        min_length=1,
        description="At least one invalidation condition required",
    )
    evidence: list[str] = Field(
        min_length=1,
        description="At least one piece of evidence required",
    )
    uncertainty: list[str] = Field(default_factory=list)
    llm_confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="LLM self-assessed confidence — METADATA ONLY",
    )
    created_at: datetime

    @model_validator(mode="after")
    def validate_price_logic(self) -> TradeProposal:
        """Validate that stop-loss and take-profit are on correct sides of entry."""
        entry_price = self.entry.price
        sl_price = self.stop_loss.price
        tp_price = self.take_profit.price

        if self.side == OrderSide.BUY:
            # Long: stop-loss below entry, take-profit above entry
            if sl_price >= entry_price:
                msg = f"BUY stop-loss ({sl_price}) must be below entry ({entry_price})"
                raise ValueError(msg)
            if tp_price <= entry_price:
                msg = f"BUY take-profit ({tp_price}) must be above entry ({entry_price})"
                raise ValueError(msg)
        else:
            # Short: stop-loss above entry, take-profit below entry
            if sl_price <= entry_price:
                msg = f"SELL stop-loss ({sl_price}) must be above entry ({entry_price})"
                raise ValueError(msg)
            if tp_price >= entry_price:
                msg = f"SELL take-profit ({tp_price}) must be below entry ({entry_price})"
                raise ValueError(msg)

        return self
