"""Transaction Cost Model.

Models full friction costs for backtesting:
- Taker / Maker trading fees
- Bid-ask spread cost (half-spread deduction)
- Slippage cost (volatility-adjusted or fixed percentage)
- Funding rate cost (perpetual futures funding per 8h/interval)
- Simulated execution latency (delayed bar fills)
- Partial fill simulation (volume cap participation)

Rule: Net PnL = Gross PnL - fees - spread - slippage - funding.
See implementation_spec.md §8.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from core.domain.enums import OrderSide


class CostBreakdown(BaseModel):
    """Breakdown of transaction costs for an executed trade."""

    gross_pnl: float
    trading_fee: float = Field(default=0.0, ge=0.0)
    spread_cost: float = Field(default=0.0, ge=0.0)
    slippage_cost: float = Field(default=0.0, ge=0.0)
    funding_cost: float = Field(default=0.0)
    total_costs: float = Field(ge=0.0)
    net_pnl: float
    executed_price: float = Field(gt=0.0)
    filled_quantity: float = Field(gt=0.0)


class TransactionCostModel:
    """Calculates realistic execution prices and cost deductions for backtesting."""

    def __init__(
        self,
        fee_rate: float = 0.0005,  # 0.05% taker fee
        half_spread_pct: float = 0.0002,  # 0.02% half-spread
        slippage_pct: float = 0.0003,  # 0.03% base slippage
        funding_rate_per_interval: float = 0.0001,  # 0.01% funding rate
        latency_bars: int = 1,  # Execution latency delay in bars
        max_volume_participation: float = 0.10,  # Max 10% of bar volume
    ) -> None:
        self.fee_rate = fee_rate
        self.half_spread_pct = half_spread_pct
        self.slippage_pct = slippage_pct
        self.funding_rate_per_interval = funding_rate_per_interval
        self.latency_bars = latency_bars
        self.max_volume_participation = max_volume_participation

    def calculate_execution_price(
        self, side: OrderSide, base_price: float, volatility: float | None = None
    ) -> tuple[float, float, float]:
        """Calculate effective executed price after incorporating spread and slippage.

        Returns: (executed_price, spread_cost, slippage_cost)
        """
        eff_slippage = self.slippage_pct
        if volatility is not None and volatility > 0:
            eff_slippage += volatility * 0.5  # Increase slippage during high vol

        total_friction_pct = self.half_spread_pct + eff_slippage

        if side == OrderSide.BUY:
            # Slippage & spread increase buy price
            executed_price = base_price * (1.0 + total_friction_pct)
        else:
            # Slippage & spread decrease sell price
            executed_price = base_price * (1.0 - total_friction_pct)

        spread_cost = base_price * self.half_spread_pct
        slippage_cost = base_price * eff_slippage

        return executed_price, spread_cost, slippage_cost

    def calculate_fill_quantity(self, desired_quantity: float, bar_volume: float) -> float:
        """Simulate partial fills based on maximum market volume participation."""
        if bar_volume <= 0:
            return desired_quantity
        max_fillable = bar_volume * self.max_volume_participation
        return min(desired_quantity, max_fillable) if max_fillable > 0 else desired_quantity

    def calculate_trade_costs(
        self,
        side: OrderSide,
        desired_quantity: float,
        entry_price: float,
        exit_price: float,
        bar_volume: float = 1_000_000.0,
        volatility: float | None = None,
        intervals_held: int = 1,
    ) -> CostBreakdown:
        """Compute full PnL and cost breakdown for a trade entry -> exit cycle.

        Formula: Net PnL = Gross PnL - trading_fee - spread_cost - slippage_cost - funding_cost
        """
        filled_qty = self.calculate_fill_quantity(desired_quantity, bar_volume)
        eff_exit, spread_per_unit, slip_per_unit = self.calculate_execution_price(
            side, exit_price, volatility
        )

        if side == OrderSide.BUY:
            # Long position PnL
            gross_pnl = (eff_exit - entry_price) * filled_qty
        else:
            # Short position PnL
            gross_pnl = (entry_price - eff_exit) * filled_qty

        notional = eff_exit * filled_qty
        trading_fee = notional * self.fee_rate * 2.0  # Entry + Exit fee
        spread_cost = spread_per_unit * filled_qty * 2.0
        slippage_cost = slip_per_unit * filled_qty * 2.0
        funding_cost = notional * self.funding_rate_per_interval * intervals_held

        total_costs = trading_fee + spread_cost + slippage_cost + abs(funding_cost)
        net_pnl = gross_pnl - total_costs

        return CostBreakdown(
            gross_pnl=gross_pnl,
            trading_fee=trading_fee,
            spread_cost=spread_cost,
            slippage_cost=slippage_cost,
            funding_cost=funding_cost,
            total_costs=total_costs,
            net_pnl=net_pnl,
            executed_price=eff_exit,
            filled_quantity=filled_qty,
        )


__all__ = ["CostBreakdown", "TransactionCostModel"]
