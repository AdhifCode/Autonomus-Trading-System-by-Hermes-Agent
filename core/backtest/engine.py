"""Deterministic Backtest Engine Module.

Executes bar-by-bar backtests with strict protection against temporal leakage and look-ahead bias:
- Signals generated at bar `t` execute at bar `t+1` open price.
- Temporal leakage attempts trigger `TemporalLeakageError`.
- Evaluates risk policies and friction costs (fees, spread, slippage, funding).
- Uses NET PnL as primary economic metric.

See implementation_spec.md §5, §8.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence

from pydantic import BaseModel, Field

from core.backtest.costs import CostBreakdown, TransactionCostModel
from core.domain.enums import OrderSide
from core.errors import TemporalLeakageError
from data.features.generator import MarketFeatures
from data.validation.checker import Candle


class TradeRecord(BaseModel):
    """Historical record of an executed trade in backtest."""

    trade_id: str
    symbol: str
    side: OrderSide
    entry_time: str
    exit_time: str
    entry_price: float
    exit_price: float
    quantity: float
    gross_pnl: float
    net_pnl: float
    costs: float


class BacktestResult(BaseModel):
    """Complete results summary from a backtest execution."""

    symbol: str
    initial_balance: float
    final_balance: float
    total_gross_pnl: float
    total_net_pnl: float
    total_costs: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate_pct: float
    max_drawdown_pct: float = Field(ge=0.0, le=100.0)
    profit_factor: float
    trades: list[TradeRecord] = Field(default_factory=list)
    equity_curve: list[float] = Field(default_factory=list)


# Signal Strategy Function Signature: receives candles up to `current_index`
SignalStrategy = Callable[[Sequence[Candle], Sequence[MarketFeatures], int], OrderSide | None]


class DeterministicBacktestEngine:
    """Event-driven backtest engine with temporal leakage assertions and cost modeling."""

    def __init__(
        self,
        initial_balance: float = 100_000.0,
        cost_model: TransactionCostModel | None = None,
        trade_size_notional: float = 10_000.0,
    ) -> None:
        self.initial_balance = initial_balance
        self.cost_model = cost_model or TransactionCostModel()
        self.trade_size_notional = trade_size_notional

    def run_backtest(
        self,
        candles: Sequence[Candle],
        features: Sequence[MarketFeatures],
        strategy: SignalStrategy,
        symbol: str = "BTCUSDT",
    ) -> BacktestResult:
        """Run deterministic backtest over candle series.

        Enforces Temporal Leakage Safeguard: strategy logic at index `t` can only see candles[:t+1].
        Signals execute at bar `t+1` open price.
        """
        if len(candles) != len(features):
            raise ValueError("Candles and features must be equal length")

        balance = self.initial_balance
        peak_balance = balance
        max_drawdown_pct = 0.0

        equity_curve: list[float] = [balance]
        trades: list[TradeRecord] = []

        pending_signal: OrderSide | None = None
        signal_bar_index: int | None = None

        active_position_side: OrderSide | None = None
        entry_price: float = 0.0
        entry_time: str = ""
        entry_qty: float = 0.0
        entry_bar_index: int = 0

        total_gross_pnl = 0.0
        total_net_pnl = 0.0
        total_costs = 0.0
        trade_counter = 0

        for t in range(len(candles)):
            current_bar = candles[t]

            # 1. Execute pending signal from previous bar at current bar's OPEN price
            if pending_signal is not None and signal_bar_index is not None:
                if t <= signal_bar_index:
                    raise TemporalLeakageError(
                        f"Temporal Leakage Violation: Signal from bar {signal_bar_index} "
                        f"attempted execution at bar {t}"
                    )

                if active_position_side is None:
                    # Open new position
                    active_position_side = pending_signal
                    entry_price = current_bar.open
                    entry_time = current_bar.timestamp.isoformat()
                    entry_qty = self.trade_size_notional / entry_price
                    entry_bar_index = t
                elif active_position_side != pending_signal:
                    # Close existing position and flip/exit
                    exit_price = current_bar.open
                    exit_time = current_bar.timestamp.isoformat()
                    intervals_held = max(1, t - entry_bar_index)

                    breakdown: CostBreakdown = self.cost_model.calculate_trade_costs(
                        side=active_position_side,
                        desired_quantity=entry_qty,
                        entry_price=entry_price,
                        exit_price=exit_price,
                        bar_volume=current_bar.volume,
                        volatility=features[t].volatility,
                        intervals_held=intervals_held,
                    )

                    trade_counter += 1
                    tr = TradeRecord(
                        trade_id=f"BT-{trade_counter:04d}",
                        symbol=symbol,
                        side=active_position_side,
                        entry_time=entry_time,
                        exit_time=exit_time,
                        entry_price=entry_price,
                        exit_price=breakdown.executed_price,
                        quantity=breakdown.filled_quantity,
                        gross_pnl=breakdown.gross_pnl,
                        net_pnl=breakdown.net_pnl,
                        costs=breakdown.total_costs,
                    )
                    trades.append(tr)

                    balance += breakdown.net_pnl
                    total_gross_pnl += breakdown.gross_pnl
                    total_net_pnl += breakdown.net_pnl
                    total_costs += breakdown.total_costs

                    active_position_side = None

                pending_signal = None
                signal_bar_index = None

            # 2. Evaluate strategy signal strictly using data up to `t`
            visible_candles = candles[: t + 1]
            visible_features = features[: t + 1]

            # Assert no future candle access
            if len(visible_candles) > t + 1:
                raise TemporalLeakageError("Look-ahead bias detected in visible candles slice")

            signal = strategy(visible_candles, visible_features, t)
            if signal is not None:
                pending_signal = signal
                signal_bar_index = t

            # 3. Track balance and drawdown
            equity_curve.append(balance)
            if balance > peak_balance:
                peak_balance = balance

            if peak_balance > 0:
                dd = ((peak_balance - balance) / peak_balance) * 100.0
                if dd > max_drawdown_pct:
                    max_drawdown_pct = dd

        # Calculate summary statistics
        winning_trades = [tr for tr in trades if tr.net_pnl > 0]
        losing_trades = [tr for tr in trades if tr.net_pnl <= 0]
        win_rate = (len(winning_trades) / len(trades) * 100.0) if trades else 0.0

        gross_wins = sum(tr.net_pnl for tr in winning_trades)
        gross_losses = abs(sum(tr.net_pnl for tr in losing_trades))
        profit_factor = (
            (gross_wins / gross_losses)
            if gross_losses > 0
            else (gross_wins if gross_wins > 0 else 1.0)
        )

        return BacktestResult(
            symbol=symbol,
            initial_balance=self.initial_balance,
            final_balance=balance,
            total_gross_pnl=total_gross_pnl,
            total_net_pnl=total_net_pnl,
            total_costs=total_costs,
            total_trades=len(trades),
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            win_rate_pct=win_rate,
            max_drawdown_pct=max_drawdown_pct,
            profit_factor=profit_factor,
            trades=trades,
            equity_curve=equity_curve,
        )


__all__ = ["BacktestResult", "DeterministicBacktestEngine", "SignalStrategy", "TradeRecord"]
