# Changelog

All notable changes to the **Trader Control Center V2.1** project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [2.1.1] - 2026-09-02

### Added
- **Authoritative System Verification Engine (`scripts/verify_system.py`)**: Standalone, deterministic verification tool covering 46 subsystem gates across Python, dependencies, packages, configs, database, migrations, domain models, risk rules, execution flow, reconciliation, backtesting, strategy lifecycle, knowledge layer, web health, and test suite.
- **Pre-Hermes Repository Audit (`PRE_HERMES_AUDIT.md`)**: Complete repository component inventory and dependency mapping.
- **Development Plan Reality Audit (`DEVELOPMENT_PLAN_REALITY.md`)**: Reconciliation of all 17 implementation phases against source code and runtime evidence.
- **Pre-Hermes Acceptance Report (`PRE_HERMES_ACCEPTANCE_REPORT.md`)**: Authoritative formal acceptance report verifying all 21 pre-Hermes criteria with decision **`PRE-HERMES READY`**.

### Fixed
- Fixed DuckDB timestamp parsing in `test_phase8_backtesting.py` by adding `pytz>=2024.1` to `analytics` dependencies in `pyproject.toml`.
- Replaced dynamic `nest_asyncio` calls in `core/paper/runner.py` and `core/testnet/runner.py` with standard `ThreadPoolExecutor` workers.
- Resolved all strict static typing issues in `web/service.py` for mypy strict compliance across 168 source files (0 errors).
- Resolved all ruff formatting and linting violations (0 errors).
- Unified test suite to 587 tests passing with 100% pass rate in 17.82s and 93.11% code coverage.
- Synchronized all documentation (`OPERATIONS_GUIDE.md`, `DEVELOPMENT_PLAN.md`, `SYSTEM_TRACEABILITY.md`, `README.md`) to canonical reality.

---

## [2.1.0] - 2026-08-30

### Added
- **Phase 17 (Limited Live Preparation)**: `LimitedLivePrepEngine` in `core/prep/limited_live.py` enforcing 13 operational verification checklist items and 5 AI Hard Prohibitions.
- **Phase 16 (Production Readiness Review)**: 5-dimension audit engine in `core/audit/production_readiness.py` verifying Trading Correctness, Execution, Risk, AI Security, and Operations.
- **Phase 15 (Binance Testnet Validation)**: 15-module verification engine in `core/testnet/runner.py` for Binance Futures Testnet REST/WS connectivity.
- **Phase 14 (Paper Trading Engine)**: Automated paper trading simulation engine in `core/paper/runner.py`.
- **Phase 13 (Full Integration & Failure Suite)**: End-to-end integration and failure injection test suite in `tests/integration/test_phase13_full_flow.py`.
- **Phase 12 (Trader Control Center Web UI)**: Single-page FastAPI dashboard (`web/app.py`, `web/service.py`, `web/frontend/`) with 18 section tabs and real-time WebSocket state broadcasting.
- **Phase 11 (Knowledge System & Learning Loop V2)**: Asynchronous Obsidian vault sync, Markdown parser, search engine, and trade reflection pipeline in `knowledge/`.
- **Phase 10 (Hermes Integration Boundary)**: `HermesGateway` and `HermesSecurityBoundary` in `integration/hermes/` enforcing strict tool permission whitelists and hard-blocked operations.
- **Phase 9 (Strategy Versioning & Market Regime)**: Strategy lifecycle engine and ADX/ATR market regime classifier in `core/strategy/`.
- **Phase 8 (Market Data & DuckDB/Parquet)**: Market data ingestion engine and tick analytical engine in `core/backtest/`.
- **Phase 7 (REST Reconciliation)**: State reconciliation engine in `core/execution/reconciliation.py` enforcing `UNKNOWN -> FREEZE -> RECONCILE -> RESOLVE`.
- **Phase 6 (Exchange Adapters)**: REST & WebSocket clients for Binance Futures API (`adapters/exchange/binance/`) and `MockExchange` (`adapters/exchange/mock/`).
- **Phase 5 (Execution Engine)**: `ExecutionStateMachine` and `ExecutionService` in `core/execution/` with dual-layer idempotency protection.
- **Phase 4 (Risk Engine)**: Deterministic `RiskEngine` in `core/risk/` enforcing 20 risk rule validators (`V01`–`V20`).
- **Phase 3 (SQLite Database & Repositories)**: `SQLiteManager` with WAL mode, `MigrationRunner`, and 10 strongly-typed repositories in `adapters/database/` and `adapters/repositories/`.
- **Phase 2 (Core Domain Models)**: Pydantic V2 domain models for `TradeProposal`, `Order`, `Position`, `Fill`, `PortfolioState`, `MarketState`, `SystemState`, `RiskPolicy`, `RiskDecision` in `core/domain/`.
- **Operational Documentation**: `OPERATIONS_GUIDE.md`, `SYSTEM_TRACEABILITY.md`, `SYSTEM_ACCEPTANCE_REPORT.md`, `LIMITED_LIVE_RUNBOOK.md`.

### Security
- Hardcoded plaintext secrets prohibited across all configuration files and codebase.
- API keys injected strictly via environment variables (`BINANCE_API_KEY`, `BINANCE_API_SECRET`).
- `HermesSecurityBoundary` hard-blocks direct order submission, risk policy modification, kill switch disabling, and LIVE mode activation.
