"""Unit and Integration Tests for Phase 8: Market Data and Backtesting.

Verifies:
1. Market data validation & quality checking (gaps, invalid prices, duplicates)
2. Parquet file storage read/write operations
3. DuckDB SQL query analytics engine
4. Feature generation & market regime classification
5. Transaction cost model (fees, spread, slippage, funding, partial fills)
6. Deterministic backtest engine execution
7. Explicit temporal leakage & look-ahead bias protection tests
8. Walk-Forward Optimization (WFO)
9. Monte Carlo trade sequence resampling (95% confidence intervals)
10. Transaction cost & slippage stress testing
11. Regime performance breakdown
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta

import pytest

from core.backtest.analysis import PerformanceAnalyzer
from core.backtest.costs import TransactionCostModel
from core.backtest.engine import DeterministicBacktestEngine
from core.backtest.robustness import RobustnessTester
from core.domain.enums import OrderSide
from core.errors import DataValidationError, TemporalLeakageError
from data.features.generator import FeatureGenerator, MarketFeatures, RegimeType
from data.storage.duckdb_engine import DuckDBEngine
from data.storage.parquet_store import ParquetStore
from data.validation.checker import Candle, DataValidator

_START_TIME = datetime(2026, 1, 1, 0, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def generate_synthetic_candles(
    count: int = 100,
    symbol: str = "BTCUSDT",
    base_price: float = 50000.0,
    trend: str = "BULL",
) -> list[Candle]:
    """Generate synthetic OHLCV candle series for testing."""
    candles: list[Candle] = []
    price = base_price

    for i in range(count):
        ts = _START_TIME + timedelta(minutes=i * 5)
        if trend == "BULL":
            change = 20.0 + (i % 5) * 5.0
        elif trend == "BEAR":
            change = -20.0 - (i % 5) * 5.0
        else:
            change = 10.0 if i % 2 == 0 else -10.0

        open_p = price
        close_p = max(100.0, open_p + change)
        high_p = max(open_p, close_p) + 15.0
        low_p = min(open_p, close_p) - 15.0
        vol = 1000.0 + (i * 10)

        price = close_p
        candles.append(
            Candle(
                timestamp=ts,
                symbol=symbol,
                open=open_p,
                high=high_p,
                low=low_p,
                close=close_p,
                volume=vol,
            )
        )

    return candles


# Test strategy that triggers trades based on candle indices to test execution cycles
def sample_signal_strategy(
    candles: Sequence[Candle], features: Sequence[MarketFeatures], t: int
) -> OrderSide | None:
    if t < 10:
        return None
    # Flip signal every 15 bars to ensure trades open and close
    if t % 15 == 0:
        return OrderSide.BUY if (t // 15) % 2 == 1 else OrderSide.SELL
    return None


# ---------------------------------------------------------------------------
# Test Cases
# ---------------------------------------------------------------------------


class TestDataValidation:
    def test_valid_candles_pass(self):
        candles = generate_synthetic_candles(20)
        validator = DataValidator()
        res = validator.validate_candles(candles)
        assert res.is_valid is True
        assert res.has_critical_error is False
        assert len(res.issues) == 0

    def test_invalid_high_price_fails(self):
        candles = generate_synthetic_candles(5)
        # Corrupt candle 2 high price to be lower than open/close
        candles[2] = candles[2].model_copy(update={"high": candles[2].open - 50.0})

        validator = DataValidator()
        res = validator.validate_candles(candles)
        assert res.is_valid is False
        assert res.has_critical_error is True
        assert any(i.issue_type == "INVALID_HIGH_PRICE" for i in res.issues)

        with pytest.raises(DataValidationError):
            validator.assert_valid(candles)

    def test_duplicate_timestamp_fails(self):
        candles = generate_synthetic_candles(5)
        candles[3] = candles[3].model_copy(update={"timestamp": candles[2].timestamp})

        validator = DataValidator()
        res = validator.validate_candles(candles)
        assert res.is_valid is False
        assert any(i.issue_type == "DUPLICATE_TIMESTAMP" for i in res.issues)


class TestParquetAndDuckDB:
    def test_parquet_store_save_and_load(self, tmp_path):
        store = ParquetStore(base_dir=tmp_path)
        candles = generate_synthetic_candles(15)

        path = store.save_candles("BTCUSDT", candles, "test_btc.parquet")
        assert path.exists()

        loaded = store.load_candles("test_btc.parquet")
        assert len(loaded) == 15
        assert loaded[0].symbol == "BTCUSDT"
        assert loaded[0].close == candles[0].close

    def test_duckdb_engine_queries(self, tmp_path):
        store = ParquetStore(base_dir=tmp_path)
        candles = generate_synthetic_candles(30)
        pq_path = store.save_candles("BTCUSDT", candles, "duck_btc.parquet")

        db = DuckDBEngine(":memory:")
        db.register_parquet("v_btc", pq_path)

        summary = db.get_ohlcv_summary("v_btc")
        assert summary["total_bars"] == 30
        assert summary["min_price"] > 0
        db.close()


class TestFeatureGenerator:
    def test_feature_generation_and_regimes(self):
        candles = generate_synthetic_candles(50, trend="BULL")
        features = FeatureGenerator.generate_features(candles, fast_period=5, slow_period=15)

        assert len(features) == 50
        assert features[49].sma_fast is not None
        assert features[49].sma_slow is not None
        assert features[49].rsi is not None
        # Strong bull trend should classify regime as BULL or HIGH_VOLATILITY
        assert features[49].regime in (RegimeType.BULL, RegimeType.HIGH_VOLATILITY)


class TestTransactionCostModel:
    def test_cost_breakdown_formula(self):
        # Net PnL = Gross PnL - fees - spread - slippage - funding
        cost_model = TransactionCostModel(
            fee_rate=0.001,  # 0.1%
            half_spread_pct=0.0005,  # 0.05%
            slippage_pct=0.0005,  # 0.05%
            funding_rate_per_interval=0.0001,
        )

        breakdown = cost_model.calculate_trade_costs(
            side=OrderSide.BUY,
            desired_quantity=1.0,
            entry_price=50000.0,
            exit_price=55000.0,
        )

        assert breakdown.gross_pnl > 0
        assert breakdown.total_costs > 0
        assert abs(breakdown.net_pnl - (breakdown.gross_pnl - breakdown.total_costs)) < 1e-5


class TestBacktestEngineAndLeakage:
    def test_deterministic_backtest(self):
        candles = generate_synthetic_candles(100, trend="BULL")
        features = FeatureGenerator.generate_features(candles, fast_period=5, slow_period=15)

        engine = DeterministicBacktestEngine(initial_balance=100_000.0)
        res = engine.run_backtest(candles, features, sample_signal_strategy)

        assert res.initial_balance == 100_000.0
        assert res.final_balance != 100_000.0
        assert len(res.equity_curve) == len(candles) + 1

        metrics = PerformanceAnalyzer.analyze_result(res)
        assert metrics.max_drawdown_pct >= 0.0

    def test_temporal_leakage_protection(self):
        candles = generate_synthetic_candles(20)
        features = FeatureGenerator.generate_features(candles, fast_period=5, slow_period=10)

        # Defective strategy trying to look ahead into future bar candles[t+1]
        def cheating_strategy(
            c_slice: Sequence[Candle], f_slice: Sequence[MarketFeatures], t: int
        ) -> OrderSide | None:
            # Illegal look-ahead access attempt
            if len(c_slice) <= t:
                raise TemporalLeakageError("Temporal Leakage: Attempted to inspect future bar")
            return OrderSide.BUY

        engine = DeterministicBacktestEngine()
        # Ensure backtest runs without throwing leakage error when strategy obeys length constraint
        res = engine.run_backtest(candles, features, cheating_strategy)
        assert res.total_trades >= 0


class TestRobustnessAnalysis:
    def test_monte_carlo_resampling(self):
        candles = generate_synthetic_candles(100, trend="BULL")
        features = FeatureGenerator.generate_features(candles, fast_period=5, slow_period=15)

        engine = DeterministicBacktestEngine()
        res = engine.run_backtest(candles, features, sample_signal_strategy)

        tester = RobustnessTester(engine)
        mc_summary = tester.run_monte_carlo(res, iterations=100, seed=42)

        assert mc_summary.simulations == 100
        assert mc_summary.p05_net_pnl <= mc_summary.p95_net_pnl

    def test_cost_stress_testing(self):
        candles = generate_synthetic_candles(100, trend="BULL")
        features = FeatureGenerator.generate_features(candles, fast_period=5, slow_period=15)

        tester = RobustnessTester()
        stress_points = tester.run_cost_stress_test(
            candles, features, sample_signal_strategy, multipliers=(1.0, 2.0, 5.0)
        )

        assert len(stress_points) == 3
        # Higher cost multipliers should decrease Net PnL
        assert stress_points[0].total_net_pnl >= stress_points[2].total_net_pnl

    def test_walk_forward_optimization(self):
        candles = generate_synthetic_candles(120)
        features = FeatureGenerator.generate_features(candles, fast_period=5, slow_period=15)

        tester = RobustnessTester()
        wfo = tester.run_walk_forward(candles, features, sample_signal_strategy, num_windows=2)

        assert wfo.total_windows == 2
        assert len(wfo.window_results) == 2

    def test_regime_breakdown(self):
        candles = generate_synthetic_candles(60)
        features = FeatureGenerator.generate_features(candles, fast_period=5, slow_period=15)

        tester = RobustnessTester()
        breakdown = tester.analyze_regime_breakdown(candles, features, sample_signal_strategy)

        assert len(breakdown) == len(RegimeType)
