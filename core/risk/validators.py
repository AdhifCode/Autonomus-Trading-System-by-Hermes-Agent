"""Deterministic risk validators.

Each validator evaluates a specific risk rule against TradeProposal, MarketState,
PortfolioState, RiskPolicy, and SystemState.

See architecture.md §7 and implementation_spec.md §3.
"""

from __future__ import annotations

from core.domain.enums import KillSwitchState
from core.domain.market_state import MarketState
from core.domain.portfolio import PortfolioState
from core.domain.risk import RiskPolicy, RiskViolation
from core.domain.system_state import SystemState
from core.domain.trade_proposal import TradeProposal


def validate_kill_switch(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 1: System Kill Switch.

    Kill switch MUST be in ACTIVE state. Any ENGAGED/TRIGGERED state causes FREEZE.
    """
    if system.kill_switch != KillSwitchState.ACTIVE:
        return RiskViolation(
            validator="kill_switch",
            rule="Kill Switch Active",
            current_value=system.kill_switch.value,
            limit_value=KillSwitchState.ACTIVE.value,
            message=f"Kill switch is in state {system.kill_switch.value} (FREEZE required)",
        )
    return None


def validate_trading_mode(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 2: Trading Mode Authorization.

    Trading is not allowed in DEVELOPMENT or BACKTEST mode, or if system cannot trade.
    """
    if not system.can_trade:
        return RiskViolation(
            validator="trading_mode",
            rule="Trading Mode Authorization",
            current_value=system.trading_mode.value,
            limit_value="LIVE/PAPER/TESTNET/SHADOW/LIMITED_LIVE",
            message=f"Trading proposals not authorized in trading mode {system.trading_mode.value}",
        )
    return None


def validate_stale_data(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 3: Data Freshness and Health.

    Data age must be <= policy.stale_data_timeout_seconds and system data must be healthy.
    """
    if not system.data_healthy:
        return RiskViolation(
            validator="stale_data",
            rule="Market Data Health",
            current_value="unhealthy",
            limit_value="healthy",
            message="System data health flag is False",
        )
    if market.data_age_seconds > policy.stale_data_timeout_seconds:
        return RiskViolation(
            validator="stale_data",
            rule="Market Data Freshness",
            current_value=market.data_age_seconds,
            limit_value=policy.stale_data_timeout_seconds,
            message=(
                f"Market data age ({market.data_age_seconds}s) exceeds "
                f"stale timeout ({policy.stale_data_timeout_seconds}s)"
            ),
        )
    return None


def validate_position_size(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 4: Maximum Single Position Size.

    Requested position size fraction must not exceed max_position_size_pct.
    """
    requested_pct = proposal.position_size.requested_pct
    if requested_pct > policy.max_position_size_pct:
        return RiskViolation(
            validator="position_size",
            rule="Maximum Position Size Limit",
            current_value=requested_pct,
            limit_value=policy.max_position_size_pct,
            message=(
                f"Requested position size ({requested_pct:.4f}) exceeds "
                f"maximum limit ({policy.max_position_size_pct:.4f})"
            ),
        )
    return None


def validate_portfolio_exposure(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 5: Maximum Total Portfolio Exposure.

    Total proposed exposure (current exposure + new requested exposure)
    must not exceed max_portfolio_exposure_pct.
    """
    if portfolio.equity <= 0:
        return RiskViolation(
            validator="portfolio_exposure",
            rule="Portfolio Equity Positive",
            current_value=portfolio.equity,
            limit_value=0.0,
            message="Portfolio equity must be greater than zero to calculate exposure",
        )

    current_exposure_pct = portfolio.exposure / portfolio.equity
    proposed_pct = proposal.position_size.requested_pct
    total_exposure_pct = current_exposure_pct + proposed_pct

    if total_exposure_pct > policy.max_portfolio_exposure_pct:
        return RiskViolation(
            validator="portfolio_exposure",
            rule="Maximum Portfolio Exposure Limit",
            current_value=round(total_exposure_pct, 4),
            limit_value=policy.max_portfolio_exposure_pct,
            message=(
                f"Total portfolio exposure after proposal ({total_exposure_pct:.4f}) exceeds "
                f"limit ({policy.max_portfolio_exposure_pct:.4f})"
            ),
        )
    return None


def validate_symbol_exposure(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 6: Maximum Single Symbol Exposure.

    Total exposure to the proposal's symbol must not exceed max_symbol_exposure_pct.
    """
    if portfolio.equity <= 0:
        return RiskViolation(
            validator="symbol_exposure",
            rule="Portfolio Equity Positive",
            current_value=portfolio.equity,
            limit_value=0.0,
            message="Portfolio equity must be greater than zero",
        )

    symbol_current_notional = sum(
        pos.notional for pos in portfolio.positions if pos.symbol == proposal.symbol
    )
    symbol_current_pct = symbol_current_notional / portfolio.equity
    total_symbol_pct = symbol_current_pct + proposal.position_size.requested_pct

    if total_symbol_pct > policy.max_symbol_exposure_pct:
        return RiskViolation(
            validator="symbol_exposure",
            rule="Maximum Symbol Exposure Limit",
            current_value=round(total_symbol_pct, 4),
            limit_value=policy.max_symbol_exposure_pct,
            message=(
                f"Symbol exposure for {proposal.symbol} after proposal ({total_symbol_pct:.4f}) "
                f"exceeds limit ({policy.max_symbol_exposure_pct:.4f})"
            ),
        )
    return None


def validate_strategy_exposure(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 7: Maximum Single Strategy Exposure.

    Total exposure to the proposal's strategy_id must not exceed max_strategy_exposure_pct.
    """
    if portfolio.equity <= 0:
        return RiskViolation(
            validator="strategy_exposure",
            rule="Portfolio Equity Positive",
            current_value=portfolio.equity,
            limit_value=0.0,
            message="Portfolio equity must be greater than zero",
        )

    strategy_current_notional = sum(
        pos.notional for pos in portfolio.positions if pos.strategy_id == proposal.strategy_id
    )
    strategy_current_pct = strategy_current_notional / portfolio.equity
    total_strategy_pct = strategy_current_pct + proposal.position_size.requested_pct

    if total_strategy_pct > policy.max_strategy_exposure_pct:
        return RiskViolation(
            validator="strategy_exposure",
            rule="Maximum Strategy Exposure Limit",
            current_value=round(total_strategy_pct, 4),
            limit_value=policy.max_strategy_exposure_pct,
            message=(
                f"Strategy exposure for {proposal.strategy_id} after proposal "
                f"({total_strategy_pct:.4f}) exceeds limit ({policy.max_strategy_exposure_pct:.4f})"
            ),
        )
    return None


def validate_correlated_exposure(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 8: Maximum Correlated Asset Exposure.

    Total exposure across correlated assets (assets sharing same base currency, e.g. BTC)
    must not exceed max_correlated_exposure_pct.
    """
    if portfolio.equity <= 0:
        return RiskViolation(
            validator="correlated_exposure",
            rule="Portfolio Equity Positive",
            current_value=portfolio.equity,
            limit_value=0.0,
            message="Portfolio equity must be greater than zero",
        )

    # Base asset prefix heuristic (e.g. BTC from BTCUSDT)
    base_asset = proposal.symbol[:3]
    correlated_notional = sum(
        pos.notional for pos in portfolio.positions if pos.symbol.startswith(base_asset)
    )
    correlated_pct = correlated_notional / portfolio.equity
    total_correlated_pct = correlated_pct + proposal.position_size.requested_pct

    if total_correlated_pct > policy.max_correlated_exposure_pct:
        return RiskViolation(
            validator="correlated_exposure",
            rule="Maximum Correlated Exposure Limit",
            current_value=round(total_correlated_pct, 4),
            limit_value=policy.max_correlated_exposure_pct,
            message=(
                f"Correlated exposure for {base_asset} assets ({total_correlated_pct:.4f}) "
                f"exceeds limit ({policy.max_correlated_exposure_pct:.4f})"
            ),
        )
    return None


def validate_daily_loss(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 9: Maximum Daily Loss Limit.

    If current daily PnL is negative, loss pct must not exceed max_daily_loss_pct.
    """
    if portfolio.daily_pnl < 0:
        if portfolio.equity <= 0:
            return RiskViolation(
                validator="daily_loss",
                rule="Daily Loss Limit",
                current_value=abs(portfolio.daily_pnl),
                limit_value=policy.max_daily_loss_pct,
                message="Portfolio equity non-positive during daily loss check",
            )
        daily_loss_pct = abs(portfolio.daily_pnl) / portfolio.equity
        if daily_loss_pct > policy.max_daily_loss_pct:
            return RiskViolation(
                validator="daily_loss",
                rule="Maximum Daily Loss Limit",
                current_value=round(daily_loss_pct, 4),
                limit_value=policy.max_daily_loss_pct,
                message=(
                    f"Current daily loss ({daily_loss_pct:.4f}) exceeds "
                    f"maximum daily loss limit ({policy.max_daily_loss_pct:.4f})"
                ),
            )
    return None


def validate_weekly_loss(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 10: Maximum Weekly Loss Limit.

    If current realized PnL is negative, loss pct must not exceed max_weekly_loss_pct.
    """
    if portfolio.realized_pnl < 0:
        if portfolio.equity <= 0:
            return RiskViolation(
                validator="weekly_loss",
                rule="Weekly Loss Limit",
                current_value=abs(portfolio.realized_pnl),
                limit_value=policy.max_weekly_loss_pct,
                message="Portfolio equity non-positive during weekly loss check",
            )
        weekly_loss_pct = abs(portfolio.realized_pnl) / portfolio.equity
        if weekly_loss_pct > policy.max_weekly_loss_pct:
            return RiskViolation(
                validator="weekly_loss",
                rule="Maximum Weekly Loss Limit",
                current_value=round(weekly_loss_pct, 4),
                limit_value=policy.max_weekly_loss_pct,
                message=(
                    f"Current weekly loss ({weekly_loss_pct:.4f}) exceeds "
                    f"maximum weekly loss limit ({policy.max_weekly_loss_pct:.4f})"
                ),
            )
    return None


def validate_drawdown(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 11: Maximum Portfolio Drawdown.

    Portfolio drawdown must not exceed max_drawdown_pct.
    """
    if portfolio.drawdown > policy.max_drawdown_pct:
        return RiskViolation(
            validator="drawdown",
            rule="Maximum Drawdown Limit",
            current_value=round(portfolio.drawdown, 4),
            limit_value=policy.max_drawdown_pct,
            message=(
                f"Current drawdown ({portfolio.drawdown:.4f}) exceeds "
                f"maximum drawdown limit ({policy.max_drawdown_pct:.4f})"
            ),
        )
    return None


def validate_order_notional(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 12: Maximum Order Notional Value.

    Proposed order notional USD value must not exceed max_order_notional.
    """
    proposed_notional = proposal.position_size.requested_pct * portfolio.equity
    if proposed_notional > policy.max_order_notional:
        return RiskViolation(
            validator="order_notional",
            rule="Maximum Order Notional Limit",
            current_value=round(proposed_notional, 2),
            limit_value=policy.max_order_notional,
            message=(
                f"Proposed order notional (${proposed_notional:.2f}) exceeds "
                f"maximum limit (${policy.max_order_notional:.2f})"
            ),
        )
    return None


def validate_concurrent_positions(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 13: Maximum Concurrent Positions.

    Number of open positions after proposal must not exceed max_concurrent_positions.
    """
    existing_symbol_position = any(pos.symbol == proposal.symbol for pos in portfolio.positions)
    new_position_count = portfolio.position_count + (0 if existing_symbol_position else 1)

    if new_position_count > policy.max_concurrent_positions:
        return RiskViolation(
            validator="concurrent_positions",
            rule="Maximum Concurrent Positions Limit",
            current_value=new_position_count,
            limit_value=policy.max_concurrent_positions,
            message=(
                f"Concurrent positions after proposal ({new_position_count}) exceeds "
                f"limit ({policy.max_concurrent_positions})"
            ),
        )
    return None


def validate_concurrent_orders(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 14: Maximum Concurrent Open Orders.

    Number of current open orders must be strictly less than max_concurrent_orders.
    """
    if portfolio.open_order_count >= policy.max_concurrent_orders:
        return RiskViolation(
            validator="concurrent_orders",
            rule="Maximum Concurrent Orders Limit",
            current_value=portfolio.open_order_count,
            limit_value=policy.max_concurrent_orders,
            message=(
                f"Open order count ({portfolio.open_order_count}) reaches "
                f"or exceeds maximum limit ({policy.max_concurrent_orders})"
            ),
        )
    return None


def validate_leverage(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 15: Maximum Portfolio Leverage.

    Effective portfolio leverage after proposal must not exceed max_leverage.
    """
    if portfolio.equity <= 0:
        return RiskViolation(
            validator="leverage",
            rule="Portfolio Equity Positive",
            current_value=portfolio.equity,
            limit_value=0.0,
            message="Portfolio equity must be greater than zero to calculate leverage",
        )

    proposed_notional = proposal.position_size.requested_pct * portfolio.equity
    total_notional = portfolio.exposure + proposed_notional
    effective_leverage = total_notional / portfolio.equity

    if effective_leverage > policy.max_leverage:
        return RiskViolation(
            validator="leverage",
            rule="Maximum Leverage Limit",
            current_value=round(effective_leverage, 4),
            limit_value=policy.max_leverage,
            message=(
                f"Effective leverage after proposal ({effective_leverage:.4f}) exceeds "
                f"limit ({policy.max_leverage:.4f})"
            ),
        )
    return None


def validate_spread(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 16: Maximum Bid-Ask Spread.

    Current market spread pct must not exceed max_spread_pct.
    """
    if market.price <= 0:
        return RiskViolation(
            validator="spread",
            rule="Market Price Positive",
            current_value=market.price,
            limit_value=0.0,
            message="Market price must be positive",
        )

    spread_pct = market.spread / market.price
    if spread_pct > policy.max_spread_pct:
        return RiskViolation(
            validator="spread",
            rule="Maximum Spread Limit",
            current_value=round(spread_pct, 6),
            limit_value=policy.max_spread_pct,
            message=(
                f"Market spread ({spread_pct:.6f}) exceeds "
                f"maximum threshold ({policy.max_spread_pct:.6f})"
            ),
        )
    return None


def validate_slippage(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 17: Maximum Expected Slippage.

    Difference between proposal entry price and market ask/bid must not exceed max_slippage_pct.
    """
    if market.price <= 0:
        return RiskViolation(
            validator="slippage",
            rule="Market Price Positive",
            current_value=market.price,
            limit_value=0.0,
            message="Market price must be positive",
        )

    estimated_slippage_pct = abs(proposal.entry.price - market.price) / market.price
    if estimated_slippage_pct > policy.max_slippage_pct:
        return RiskViolation(
            validator="slippage",
            rule="Maximum Slippage Limit",
            current_value=round(estimated_slippage_pct, 6),
            limit_value=policy.max_slippage_pct,
            message=(
                f"Estimated slippage ({estimated_slippage_pct:.6f}) exceeds "
                f"maximum limit ({policy.max_slippage_pct:.6f})"
            ),
        )
    return None


def validate_liquidity(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 18: Minimum Market Liquidity.

    Market 24-hour volume in USD must be >= min_liquidity_usd.
    """
    if market.volume_24h < policy.min_liquidity_usd:
        return RiskViolation(
            validator="liquidity",
            rule="Minimum Liquidity Requirement",
            current_value=round(market.volume_24h, 2),
            limit_value=policy.min_liquidity_usd,
            message=(
                f"24h market volume (${market.volume_24h:.2f}) is below "
                f"minimum required liquidity (${policy.min_liquidity_usd:.2f})"
            ),
        )
    return None


def validate_price_deviation(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 19: Maximum Price Deviation.

    Proposal entry price deviation from market price must not exceed max_price_deviation_pct.
    """
    if market.price <= 0:
        return RiskViolation(
            validator="price_deviation",
            rule="Market Price Positive",
            current_value=market.price,
            limit_value=0.0,
            message="Market price must be positive",
        )

    price_deviation_pct = abs(proposal.entry.price - market.price) / market.price
    if price_deviation_pct > policy.max_price_deviation_pct:
        return RiskViolation(
            validator="price_deviation",
            rule="Maximum Price Deviation Limit",
            current_value=round(price_deviation_pct, 4),
            limit_value=policy.max_price_deviation_pct,
            message=(
                f"Entry price deviation ({price_deviation_pct:.4f}) exceeds "
                f"maximum limit ({policy.max_price_deviation_pct:.4f})"
            ),
        )
    return None


def validate_macro_event(
    proposal: TradeProposal,
    market: MarketState,
    portfolio: PortfolioState,
    policy: RiskPolicy,
    system: SystemState,
) -> RiskViolation | None:
    """Validator 20: Macro Event Restrictions.

    Trading proposals must be blocked if macro_event_restriction is True in policy.
    """
    if policy.macro_event_restriction:
        return RiskViolation(
            validator="macro_event",
            rule="Macro Event Trading Restriction",
            current_value="restricted",
            limit_value="unrestricted",
            message="Trading blocked due to active macro event restriction",
        )
    return None


# Canonical ordered list of all 20 risk validators
ALL_VALIDATORS = [
    validate_kill_switch,
    validate_trading_mode,
    validate_stale_data,
    validate_position_size,
    validate_portfolio_exposure,
    validate_symbol_exposure,
    validate_strategy_exposure,
    validate_correlated_exposure,
    validate_daily_loss,
    validate_weekly_loss,
    validate_drawdown,
    validate_order_notional,
    validate_concurrent_positions,
    validate_concurrent_orders,
    validate_leverage,
    validate_spread,
    validate_slippage,
    validate_liquidity,
    validate_price_deviation,
    validate_macro_event,
]
