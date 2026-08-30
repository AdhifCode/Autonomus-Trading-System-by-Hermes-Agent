"""Unit and Integration Tests for Phase 9: Strategy Lifecycle and Market Regime Engine.

Verifies:
1. Canonical strategy lifecycle state machine transitions (IDEA -> ... -> PRODUCTION -> DEPRECATED)
2. Prohibited state transitions raise StrategyLifecycleError
3. Production strategy immutability (modifications trigger StrategyImmutabilityError)
4. Version creation and semantic version progression (v1.0.0 -> v1.0.1)
5. Explicit Market Regime classification (BULL, BEAR, SIDEWAYS, HIGH_VOLATILITY, LOW_VOLATILITY)
6. Explicit verification that ADX is used strictly for trend STRENGTH, NOT direction
7. SQLite repository persistence of strategy versions and audit transition logs
8. Regime filtering integration with Backtest Engine
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

import pytest

from adapters.database.sqlite import SQLiteManager
from adapters.repositories.sqlite_repos import StateTransitionRepository, StrategyVersionRepository
from core.domain.enums import MarketRegime, OrderSide, StrategyLifecycle
from core.domain.strategy import StrategyVersion
from core.errors import StrategyImmutabilityError, StrategyLifecycleError
from core.strategy.interface import BaseStrategy
from core.strategy.lifecycle import StrategyLifecycleManager
from core.strategy.regime import MarketRegimeEngine, RegimeInput
from core.strategy.versioning import SemanticVersion, StrategyVersionHistory
from data.features.generator import MarketFeatures
from data.validation.checker import Candle
from migrations.runner import MigrationRunner

_NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Test Helpers
# ---------------------------------------------------------------------------


def create_test_strategy_version(
    version_str: str = "v1.0.0",
    lifecycle: StrategyLifecycle = StrategyLifecycle.IDEA,
) -> StrategyVersion:
    return StrategyVersion(
        strategy_id="STRAT-BTC-MOMENTUM",
        version=version_str,
        lifecycle=lifecycle,
        parameters={"fast_period": 10, "slow_period": 30},
        risk_overrides={"max_position_size": 10000.0},
        applicable_regimes=[MarketRegime.BULL, MarketRegime.BEAR],
        metadata={"author": "quant_team"},
        created_at=_NOW,
        created_by="human",
    )


class RegimeAwareTestStrategy(BaseStrategy):
    """Test strategy implementation supporting regime filtering."""

    def generate_signal(
        self,
        candles: Sequence[Candle],
        features: Sequence[MarketFeatures],
        t: int,
    ) -> OrderSide | None:
        feat = features[t]
        if not self.is_regime_allowed(feat.regime):
            return None  # Block trading if market regime is not permitted

        if t < 5:
            return None

        # Simple crossover logic
        if feat.sma_fast is not None and feat.sma_slow is not None:
            if feat.sma_fast > feat.sma_slow:
                return OrderSide.BUY
            elif feat.sma_fast < feat.sma_slow:
                return OrderSide.SELL
        return None


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestStrategyLifecycle:
    def test_canonical_lifecycle_progression(self):
        mgr = StrategyLifecycleManager()
        sv = create_test_strategy_version("v1.0.0", StrategyLifecycle.IDEA)

        # IDEA -> RESEARCH -> CANDIDATE -> BACKTEST -> VALIDATED -> PAPER
        # -> APPROVED -> PRODUCTION -> DEPRECATED
        sv = mgr.transition_state(sv, StrategyLifecycle.RESEARCH)
        assert sv.lifecycle == StrategyLifecycle.RESEARCH

        sv = mgr.transition_state(sv, StrategyLifecycle.CANDIDATE)
        assert sv.lifecycle == StrategyLifecycle.CANDIDATE

        sv = mgr.transition_state(sv, StrategyLifecycle.BACKTEST)
        assert sv.lifecycle == StrategyLifecycle.BACKTEST

        sv = mgr.transition_state(sv, StrategyLifecycle.VALIDATED)
        assert sv.lifecycle == StrategyLifecycle.VALIDATED

        sv = mgr.transition_state(sv, StrategyLifecycle.PAPER)
        assert sv.lifecycle == StrategyLifecycle.PAPER

        sv = mgr.transition_state(sv, StrategyLifecycle.APPROVED)
        assert sv.lifecycle == StrategyLifecycle.APPROVED

        sv = mgr.transition_state(sv, StrategyLifecycle.PRODUCTION)
        assert sv.lifecycle == StrategyLifecycle.PRODUCTION

        sv = mgr.transition_state(sv, StrategyLifecycle.DEPRECATED)
        assert sv.lifecycle == StrategyLifecycle.DEPRECATED

    def test_prohibited_transitions_raise_error(self):
        mgr = StrategyLifecycleManager()
        sv = create_test_strategy_version("v1.0.0", StrategyLifecycle.IDEA)

        # Cannot skip from IDEA directly to PRODUCTION
        with pytest.raises(StrategyLifecycleError):
            mgr.transition_state(sv, StrategyLifecycle.PRODUCTION)

        # Cannot transition out of DEPRECATED
        deprecated_sv = create_test_strategy_version("v1.0.0", StrategyLifecycle.DEPRECATED)
        with pytest.raises(StrategyLifecycleError):
            mgr.transition_state(deprecated_sv, StrategyLifecycle.PRODUCTION)

    def test_production_immutability(self):
        mgr = StrategyLifecycleManager()
        prod_sv = create_test_strategy_version("v1.0.0", StrategyLifecycle.PRODUCTION)

        # Attempting to mutate configuration parameters raises StrategyImmutabilityError
        with pytest.raises(StrategyImmutabilityError):
            mgr.update_configuration(prod_sv, new_parameters={"fast_period": 12})

        # Attempting to transition production version to non-DEPRECATED state raises error
        with pytest.raises(StrategyImmutabilityError):
            mgr.transition_state(prod_sv, StrategyLifecycle.APPROVED)

        # Transitioning to DEPRECATED is allowed
        deprecated = mgr.transition_state(prod_sv, StrategyLifecycle.DEPRECATED)
        assert deprecated.lifecycle == StrategyLifecycle.DEPRECATED

    def test_create_new_version(self):
        mgr = StrategyLifecycleManager()
        prod_sv = create_test_strategy_version("v1.0.0", StrategyLifecycle.PRODUCTION)

        new_sv = mgr.create_new_version(
            base_strategy=prod_sv,
            increment_type="patch",
            new_parameters={"fast_period": 12, "slow_period": 30},
        )

        assert new_sv.version == "v1.0.1"
        assert new_sv.lifecycle == StrategyLifecycle.IDEA
        assert new_sv.parameters["fast_period"] == 12
        assert prod_sv.version == "v1.0.0"
        assert prod_sv.parameters["fast_period"] == 10


class TestSemanticVersion:
    def test_version_parsing_and_increment(self):
        sv = SemanticVersion.parse("v1.2.3")
        assert sv.major == 1
        assert sv.minor == 2
        assert sv.patch == 3

        patch_inc = sv.increment_patch()
        assert patch_inc.to_string() == "v1.2.4"

        minor_inc = sv.increment_minor()
        assert minor_inc.to_string() == "v1.3.0"

        major_inc = sv.increment_major()
        assert major_inc.to_string() == "v2.0.0"

    def test_version_history_tracking(self):
        history = StrategyVersionHistory(strategy_id="STRAT-BTC-MOMENTUM")
        v1 = create_test_strategy_version("v1.0.0", StrategyLifecycle.APPROVED)
        v2 = create_test_strategy_version("v1.0.1", StrategyLifecycle.PRODUCTION)
        history.add_version(v1)
        history.add_version(v2)

        latest = history.get_latest()
        prod = history.get_production_version()
        assert latest is not None
        assert prod is not None
        assert latest.version == "v1.0.1"
        assert prod.version == "v1.0.1"


class TestMarketRegimeEngine:
    def test_adx_used_for_strength_not_direction(self):
        """EXPLICIT GUARD TEST: High ADX must produce BEAR if direction is negative.

        Proves ADX alone is NOT interpreted as bullish direction.
        """
        engine = MarketRegimeEngine(adx_trend_threshold=25.0)

        # High ADX (50.0) with NEGATIVE trend direction (-1.0) -> MUST be BEAR
        bear_input = RegimeInput(
            trend_direction=-1.0,
            trend_strength_adx=50.0,
            volatility=0.01,
            momentum_rsi=35.0,
            market_structure="LOWER_LOWS",
        )
        assert engine.classify(bear_input) == MarketRegime.BEAR

        # High ADX (50.0) with POSITIVE trend direction (+1.0) -> MUST be BULL
        bull_input = RegimeInput(
            trend_direction=1.0,
            trend_strength_adx=50.0,
            volatility=0.01,
            momentum_rsi=65.0,
            market_structure="HIGHER_HIGHS",
        )
        assert engine.classify(bull_input) == MarketRegime.BULL

    def test_high_and_low_volatility_classification(self):
        engine = MarketRegimeEngine(
            high_volatility_threshold=0.03,
            low_volatility_threshold=0.005,
            adx_trend_threshold=25.0,
        )

        # High Volatility
        high_vol_input = RegimeInput(volatility=0.04)
        assert engine.classify(high_vol_input) == MarketRegime.HIGH_VOLATILITY

        # Low Volatility (low stddev + low ADX)
        low_vol_input = RegimeInput(volatility=0.002, trend_strength_adx=10.0)
        assert engine.classify(low_vol_input) == MarketRegime.LOW_VOLATILITY

    def test_sideways_regime_classification(self):
        engine = MarketRegimeEngine(adx_trend_threshold=25.0)

        # Low ADX (15.0) -> SIDEWAYS despite positive slope
        sideways_input = RegimeInput(
            trend_direction=1.0,
            trend_strength_adx=15.0,
            volatility=0.01,
            momentum_rsi=51.0,
        )
        assert engine.classify(sideways_input) == MarketRegime.SIDEWAYS


class TestSQLitePersistenceAndBacktesting:
    def test_strategy_repository_persistence(self, tmp_db_path):
        db = SQLiteManager(tmp_db_path)
        db.connect()
        MigrationRunner(db).run()

        strat_repo = StrategyVersionRepository(db)
        trans_repo = StateTransitionRepository(db)
        mgr = StrategyLifecycleManager(repo=strat_repo, transition_repo=trans_repo)

        sv = create_test_strategy_version("v1.0.0", StrategyLifecycle.IDEA)
        strat_repo.save(sv)

        # Load back
        loaded = strat_repo.get_version("STRAT-BTC-MOMENTUM", "v1.0.0")
        assert loaded.strategy_id == sv.strategy_id
        assert loaded.version == "v1.0.0"
        assert loaded.lifecycle == StrategyLifecycle.IDEA

        # Transition state
        updated = mgr.transition_state(
            sv, StrategyLifecycle.RESEARCH, reason="Passed initial research"
        )
        assert updated.lifecycle == StrategyLifecycle.RESEARCH

        # Verify transition audit record in DB
        transitions = trans_repo.get_by_entity("STRATEGY", "STRAT-BTC-MOMENTUM:v1.0.0")
        assert len(transitions) == 1
        assert transitions[0]["from_state"] == "IDEA"
        assert transitions[0]["to_state"] == "RESEARCH"

        db.close()

    def test_regime_filtering_in_backtesting(self):
        # Strategy only allowed in BULL regime
        sv = StrategyVersion(
            strategy_id="BULL-ONLY",
            version="v1.0.0",
            lifecycle=StrategyLifecycle.APPROVED,
            applicable_regimes=[MarketRegime.BULL],
            created_at=_NOW,
            created_by="human",
        )

        strat = RegimeAwareTestStrategy(sv)
        assert strat.is_regime_allowed(MarketRegime.BULL) is True
        assert strat.is_regime_allowed(MarketRegime.SIDEWAYS) is False
        assert strat.is_regime_allowed(MarketRegime.BEAR) is False
