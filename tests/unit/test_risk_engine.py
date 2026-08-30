"""Comprehensive unit & integration tests for Phase 4: Deterministic Risk Engine.

Validates all 20 risk rules, determinism, kill-switch / FREEZE priority, LLM confidence
isolation, and critical risk invariants per architecture.md §6, §7 and implementation_spec.md §3.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.domain.enums import (
    KillSwitchState,
    MarketRegime,
    OrderSide,
    OrderType,
    PositionSide,
    RiskDecisionType,
    TradingMode,
)
from core.domain.market_state import MarketState
from core.domain.order import Order
from core.domain.portfolio import PortfolioState
from core.domain.position import Position
from core.domain.risk import RiskPolicy
from core.domain.system_state import SystemState
from core.domain.trade_proposal import (
    EntrySpec,
    PositionSizeSpec,
    StopLossSpec,
    TakeProfitSpec,
    TradeProposal,
)
from core.risk import RiskEngine, load_risk_policy, validators

_NOW = datetime(2026, 8, 29, 14, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Fixture Builders
# ---------------------------------------------------------------------------


def make_valid_proposal(
    symbol: str = "BTCUSDT",
    requested_pct: float = 0.02,
    llm_confidence: float = 0.85,
    entry_price: float = 50000.0,
    strategy_id: str = "strat_momentum_1",
) -> TradeProposal:
    return TradeProposal(
        proposal_id="PRP-20260829-000001",
        symbol=symbol,
        side=OrderSide.BUY,
        strategy_id=strategy_id,
        strategy_version="1.0.0",
        model_version="hermes-3.5-v1",
        thesis="Breakout above resistance with strong volume",
        entry=EntrySpec(price=entry_price, order_type=OrderType.LIMIT),
        stop_loss=StopLossSpec(price=entry_price * 0.95),
        take_profit=TakeProfitSpec(price=entry_price * 1.10),
        position_size=PositionSizeSpec(requested_pct=requested_pct),
        market_regime=MarketRegime.BULL,
        invalidation_conditions=["Close below 48000"],
        evidence=["RSI bullish divergence"],
        uncertainty=["Upcoming CPI report"],
        llm_confidence=llm_confidence,
        created_at=_NOW,
    )


def make_valid_market(
    symbol: str = "BTCUSDT",
    price: float = 50000.0,
    data_age_seconds: float = 5.0,
    spread: float = 10.0,
    volume_24h: float = 1_000_000.0,
) -> MarketState:
    return MarketState(
        symbol=symbol,
        price=price,
        bid=price - spread / 2,
        ask=price + spread / 2,
        spread=spread,
        volume_24h=volume_24h,
        timestamp=_NOW,
        data_age_seconds=data_age_seconds,
    )


def make_valid_portfolio(
    equity: float = 100_000.0,
    exposure: float = 10_000.0,
    daily_pnl: float = 100.0,
    drawdown: float = 0.02,
    positions: list[Position] | None = None,
    open_orders: list[Order] | None = None,
) -> PortfolioState:
    return PortfolioState(
        balance=equity,
        equity=equity,
        available_margin=equity - exposure,
        exposure=exposure,
        realized_pnl=500.0,
        unrealized_pnl=200.0,
        daily_pnl=daily_pnl,
        drawdown=drawdown,
        positions=positions or [],
        open_orders=open_orders or [],
        timestamp=_NOW,
    )


def make_valid_system(
    trading_mode: TradingMode = TradingMode.PAPER,
    kill_switch: KillSwitchState = KillSwitchState.ACTIVE,
    exchange_connected: bool = True,
    data_healthy: bool = True,
) -> SystemState:
    return SystemState(
        trading_mode=trading_mode,
        kill_switch=kill_switch,
        exchange_connected=exchange_connected,
        data_healthy=data_healthy,
        last_heartbeat=_NOW,
        active_errors=[],
    )


def make_default_policy() -> RiskPolicy:
    return RiskPolicy(
        max_position_size_pct=0.05,
        max_portfolio_exposure_pct=0.50,
        max_symbol_exposure_pct=0.20,
        max_strategy_exposure_pct=0.30,
        max_correlated_exposure_pct=0.40,
        max_daily_loss_pct=0.03,
        max_weekly_loss_pct=0.07,
        max_drawdown_pct=0.15,
        max_order_notional=10000.0,
        max_concurrent_positions=5,
        max_concurrent_orders=10,
        max_leverage=3.0,
        max_spread_pct=0.005,
        max_slippage_pct=0.01,
        min_liquidity_usd=50000.0,
        stale_data_timeout_seconds=60,
        max_price_deviation_pct=0.10,
        macro_event_restriction=False,
        policy_version="1.0",
    )


# ---------------------------------------------------------------------------
# Unit Tests for Individual 20 Validators
# ---------------------------------------------------------------------------


class TestIndividualValidators:
    def test_v1_kill_switch_pass(self):
        v = validators.validate_kill_switch(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(kill_switch=KillSwitchState.ACTIVE),
        )
        assert v is None

    def test_v1_kill_switch_fail(self):
        v = validators.validate_kill_switch(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(kill_switch=KillSwitchState.SOFT_KILL),
        )
        assert v is not None
        assert v.validator == "kill_switch"

    def test_v2_trading_mode_pass(self):
        v = validators.validate_trading_mode(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(trading_mode=TradingMode.PAPER),
        )
        assert v is None

    def test_v2_trading_mode_fail(self):
        v = validators.validate_trading_mode(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(trading_mode=TradingMode.DEVELOPMENT),
        )
        assert v is not None
        assert v.validator == "trading_mode"

    def test_v3_stale_data_pass(self):
        v = validators.validate_stale_data(
            make_valid_proposal(),
            make_valid_market(data_age_seconds=10),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v3_stale_data_fail_timeout(self):
        v = validators.validate_stale_data(
            make_valid_proposal(),
            make_valid_market(data_age_seconds=120),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "stale_data"

    def test_v3_stale_data_fail_unhealthy(self):
        v = validators.validate_stale_data(
            make_valid_proposal(),
            make_valid_market(data_age_seconds=5),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(data_healthy=False),
        )
        assert v is not None
        assert v.validator == "stale_data"

    def test_v4_position_size_pass(self):
        v = validators.validate_position_size(
            make_valid_proposal(requested_pct=0.04),
            make_valid_market(),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v4_position_size_fail(self):
        v = validators.validate_position_size(
            make_valid_proposal(requested_pct=0.08),
            make_valid_market(),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "position_size"

    def test_v5_portfolio_exposure_pass(self):
        v = validators.validate_portfolio_exposure(
            make_valid_proposal(requested_pct=0.04),
            make_valid_market(),
            make_valid_portfolio(exposure=30_000),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v5_portfolio_exposure_fail(self):
        v = validators.validate_portfolio_exposure(
            make_valid_proposal(requested_pct=0.10),
            make_valid_market(),
            make_valid_portfolio(exposure=45_000),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "portfolio_exposure"

    def test_v6_symbol_exposure_pass(self):
        v = validators.validate_symbol_exposure(
            make_valid_proposal(requested_pct=0.04),
            make_valid_market(),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v6_symbol_exposure_fail(self):
        existing_pos = Position(
            position_id="POS-1",
            symbol="BTCUSDT",
            side=PositionSide.LONG,
            quantity=0.3,
            entry_price=50000.0,
            current_price=50000.0,
            strategy_id="strat1",
            strategy_version="1.0",
            opened_at=_NOW,
            updated_at=_NOW,
        )
        v = validators.validate_symbol_exposure(
            make_valid_proposal(symbol="BTCUSDT", requested_pct=0.08),
            make_valid_market(),
            make_valid_portfolio(equity=100_000.0, positions=[existing_pos]),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "symbol_exposure"

    def test_v7_strategy_exposure_pass(self):
        v = validators.validate_strategy_exposure(
            make_valid_proposal(requested_pct=0.04),
            make_valid_market(),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v7_strategy_exposure_fail(self):
        existing_pos = Position(
            position_id="POS-1",
            symbol="ETHUSDT",
            side=PositionSide.LONG,
            quantity=10.0,
            entry_price=2500.0,
            current_price=2500.0,
            strategy_id="strat_momentum_1",
            strategy_version="1.0",
            opened_at=_NOW,
            updated_at=_NOW,
        )
        v = validators.validate_strategy_exposure(
            make_valid_proposal(strategy_id="strat_momentum_1", requested_pct=0.08),
            make_valid_market(),
            make_valid_portfolio(equity=100_000.0, positions=[existing_pos]),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "strategy_exposure"

    def test_v8_correlated_exposure_fail(self):
        existing_pos = Position(
            position_id="POS-1",
            symbol="BTCBUSD",
            side=PositionSide.LONG,
            quantity=0.7,
            entry_price=50000.0,
            current_price=50000.0,
            strategy_id="strat2",
            strategy_version="1.0",
            opened_at=_NOW,
            updated_at=_NOW,
        )
        v = validators.validate_correlated_exposure(
            make_valid_proposal(symbol="BTCUSDT", requested_pct=0.08),
            make_valid_market(),
            make_valid_portfolio(equity=100_000.0, positions=[existing_pos]),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "correlated_exposure"

    def test_v9_daily_loss_pass(self):
        v = validators.validate_daily_loss(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(daily_pnl=-1000.0, equity=100_000.0),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v9_daily_loss_fail(self):
        v = validators.validate_daily_loss(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(daily_pnl=-3500.0, equity=100_000.0),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "daily_loss"

    def test_v10_weekly_loss_pass(self):
        portfolio = make_valid_portfolio()
        portfolio.realized_pnl = -2000.0
        v = validators.validate_weekly_loss(
            make_valid_proposal(),
            make_valid_market(),
            portfolio,
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v10_weekly_loss_fail(self):
        portfolio = make_valid_portfolio()
        portfolio.realized_pnl = -8000.0
        v = validators.validate_weekly_loss(
            make_valid_proposal(),
            make_valid_market(),
            portfolio,
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "weekly_loss"

    def test_v11_drawdown_pass(self):
        v = validators.validate_drawdown(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(drawdown=0.05),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v11_drawdown_fail(self):
        v = validators.validate_drawdown(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(drawdown=0.18),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "drawdown"

    def test_v12_order_notional_pass(self):
        v = validators.validate_order_notional(
            make_valid_proposal(requested_pct=0.02),
            make_valid_market(),
            make_valid_portfolio(equity=100_000.0),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v12_order_notional_fail(self):
        policy = make_default_policy()
        policy.max_order_notional = 1000.0
        v = validators.validate_order_notional(
            make_valid_proposal(requested_pct=0.02),
            make_valid_market(),
            make_valid_portfolio(equity=100_000.0),
            policy,
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "order_notional"

    def test_v13_concurrent_positions_pass(self):
        v = validators.validate_concurrent_positions(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(positions=[]),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v13_concurrent_positions_fail(self):
        positions = [
            Position(
                position_id=f"POS-{i}",
                symbol=f"SYM{i}",
                side=PositionSide.LONG,
                quantity=1.0,
                entry_price=10.0,
                current_price=10.0,
                strategy_id="s1",
                strategy_version="1.0",
                opened_at=_NOW,
                updated_at=_NOW,
            )
            for i in range(5)
        ]
        v = validators.validate_concurrent_positions(
            make_valid_proposal(symbol="NEWSYM"),
            make_valid_market(),
            make_valid_portfolio(positions=positions),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "concurrent_positions"

    def test_v14_concurrent_orders_pass(self):
        v = validators.validate_concurrent_orders(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(open_orders=[]),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v14_concurrent_orders_fail(self):
        orders = [
            Order(
                client_order_id=f"ORD-{i}",
                proposal_id="PRP-20260829-000001",
                symbol="BTCUSDT",
                side=OrderSide.BUY,
                order_type=OrderType.LIMIT,
                quantity=1.0,
                created_at=_NOW,
                updated_at=_NOW,
            )
            for i in range(10)
        ]
        v = validators.validate_concurrent_orders(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(open_orders=orders),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "concurrent_orders"

    def test_v15_leverage_pass(self):
        v = validators.validate_leverage(
            make_valid_proposal(requested_pct=0.04),
            make_valid_market(),
            make_valid_portfolio(exposure=50_000),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v15_leverage_fail(self):
        v = validators.validate_leverage(
            make_valid_proposal(requested_pct=0.04),
            make_valid_market(),
            make_valid_portfolio(exposure=300_000),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "leverage"

    def test_v16_spread_pass(self):
        v = validators.validate_spread(
            make_valid_proposal(),
            make_valid_market(price=50000.0, spread=50.0),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v16_spread_fail(self):
        v = validators.validate_spread(
            make_valid_proposal(),
            make_valid_market(price=50000.0, spread=500.0),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "spread"

    def test_v17_slippage_pass(self):
        v = validators.validate_slippage(
            make_valid_proposal(entry_price=50100.0),
            make_valid_market(price=50000.0),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v17_slippage_fail(self):
        v = validators.validate_slippage(
            make_valid_proposal(entry_price=51000.0),
            make_valid_market(price=50000.0),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "slippage"

    def test_v18_liquidity_pass(self):
        v = validators.validate_liquidity(
            make_valid_proposal(),
            make_valid_market(volume_24h=1_000_000.0),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v18_liquidity_fail(self):
        v = validators.validate_liquidity(
            make_valid_proposal(),
            make_valid_market(volume_24h=10_000.0),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "liquidity"

    def test_v19_price_deviation_pass(self):
        v = validators.validate_price_deviation(
            make_valid_proposal(entry_price=52000.0),
            make_valid_market(price=50000.0),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is None

    def test_v19_price_deviation_fail(self):
        v = validators.validate_price_deviation(
            make_valid_proposal(entry_price=60000.0),
            make_valid_market(price=50000.0),
            make_valid_portfolio(),
            make_default_policy(),
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "price_deviation"

    def test_v20_macro_event_pass(self):
        policy = make_default_policy()
        policy.macro_event_restriction = False
        v = validators.validate_macro_event(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(),
            policy,
            make_valid_system(),
        )
        assert v is None

    def test_v20_macro_event_fail(self):
        policy = make_default_policy()
        policy.macro_event_restriction = True
        v = validators.validate_macro_event(
            make_valid_proposal(),
            make_valid_market(),
            make_valid_portfolio(),
            policy,
            make_valid_system(),
        )
        assert v is not None
        assert v.validator == "macro_event"


# ---------------------------------------------------------------------------
# Test Determinism and LLM Isolation
# ---------------------------------------------------------------------------


class TestRiskEngineDeterminism:
    def test_identical_inputs_produce_identical_decisions(self):
        policy = make_default_policy()
        engine = RiskEngine(policy)

        proposal = make_valid_proposal()
        market = make_valid_market()
        portfolio = make_valid_portfolio()
        system = make_valid_system()

        d1 = engine.evaluate(proposal, market, portfolio, system, timestamp=_NOW)
        d2 = engine.evaluate(proposal, market, portfolio, system, timestamp=_NOW)

        assert d1.decision == d2.decision
        assert d1.decision == RiskDecisionType.APPROVED
        assert len(d1.violations) == len(d2.violations)
        assert d1.policy_version == d2.policy_version

    def test_llm_confidence_cannot_override_rejection(self):
        """Invariant: LLM confidence=1.0 MUST NOT override risk violations."""
        policy = make_default_policy()
        engine = RiskEngine(policy)

        # Proposal with high confidence but exceeding position size limit
        proposal = make_valid_proposal(requested_pct=0.10, llm_confidence=1.0)
        market = make_valid_market()
        portfolio = make_valid_portfolio()
        system = make_valid_system()

        decision = engine.evaluate(proposal, market, portfolio, system)
        assert decision.decision == RiskDecisionType.REJECTED
        assert any(v.validator == "position_size" for v in decision.violations)

    def test_llm_confidence_cannot_override_freeze(self):
        """Invariant: LLM confidence=1.0 MUST NOT override Kill Switch / FREEZE."""
        policy = make_default_policy()
        engine = RiskEngine(policy)

        proposal = make_valid_proposal(llm_confidence=1.0)
        market = make_valid_market()
        portfolio = make_valid_portfolio()
        system = make_valid_system(kill_switch=KillSwitchState.HARD_KILL)

        decision = engine.evaluate(proposal, market, portfolio, system)
        assert decision.decision == RiskDecisionType.FREEZE


# ---------------------------------------------------------------------------
# Test Critical Architecture Invariants
# ---------------------------------------------------------------------------


class TestCriticalInvariants:
    def test_invariant_1_risk_rejection_cannot_be_overridden(self):
        policy = make_default_policy()
        engine = RiskEngine(policy)

        proposal = make_valid_proposal(requested_pct=0.20)
        market = make_valid_market()
        portfolio = make_valid_portfolio()
        system = make_valid_system()

        decision = engine.evaluate(proposal, market, portfolio, system)
        assert decision.is_rejected
        assert not decision.is_approved

    def test_invariant_2_kill_switch_cannot_be_bypassed(self):
        policy = make_default_policy()
        engine = RiskEngine(policy)

        proposal = make_valid_proposal()
        market = make_valid_market()
        portfolio = make_valid_portfolio()
        system = make_valid_system(kill_switch=KillSwitchState.HARD_KILL)

        decision = engine.evaluate(proposal, market, portfolio, system)
        assert decision.is_freeze

    def test_invariant_3_invalid_market_state_cannot_authorize(self):
        policy = make_default_policy()
        engine = RiskEngine(policy)

        proposal = make_valid_proposal()
        market = make_valid_market(volume_24h=1.0)  # Liquidity failure
        portfolio = make_valid_portfolio()
        system = make_valid_system()

        decision = engine.evaluate(proposal, market, portfolio, system)
        assert decision.is_rejected

    def test_invariant_4_stale_data_cannot_authorize(self):
        policy = make_default_policy()
        engine = RiskEngine(policy)

        proposal = make_valid_proposal()
        market = make_valid_market(data_age_seconds=500.0)
        portfolio = make_valid_portfolio()
        system = make_valid_system()

        decision = engine.evaluate(proposal, market, portfolio, system)
        assert decision.is_rejected
        assert any(v.validator == "stale_data" for v in decision.violations)

    def test_invariant_5_excess_exposure_cannot_authorize(self):
        policy = make_default_policy()
        engine = RiskEngine(policy)

        proposal = make_valid_proposal(requested_pct=0.04)
        market = make_valid_market()
        portfolio = make_valid_portfolio(equity=100_000.0, exposure=48_000.0)
        system = make_valid_system()

        decision = engine.evaluate(proposal, market, portfolio, system)
        assert decision.is_rejected
        assert any(v.validator == "portfolio_exposure" for v in decision.violations)


# ---------------------------------------------------------------------------
# Test Edge Cases and Config Loader
# ---------------------------------------------------------------------------


class TestRiskEngineEdgeCases:
    def test_multiple_simultaneous_violations(self):
        policy = make_default_policy()
        engine = RiskEngine(policy)

        # Exceeds position size AND market data is stale AND spread is huge
        proposal = make_valid_proposal(requested_pct=0.15)
        market = make_valid_market(data_age_seconds=200.0, spread=2000.0)
        portfolio = make_valid_portfolio()
        system = make_valid_system()

        decision = engine.evaluate(proposal, market, portfolio, system)
        assert decision.is_rejected
        assert len(decision.violations) >= 3
        validators_triggered = {v.validator for v in decision.violations}
        assert "position_size" in validators_triggered
        assert "stale_data" in validators_triggered
        assert "spread" in validators_triggered

    def test_load_risk_policy_file(self):
        rp = load_risk_policy("configs/risk.yaml")
        assert rp.policy_version == "1.0"
        assert rp.max_position_size_pct == 0.05
