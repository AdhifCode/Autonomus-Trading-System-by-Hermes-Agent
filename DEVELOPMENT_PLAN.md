# Development Plan

> Derived from `architecture.md` V2/V2.1 and `implementation_spec.md`.
> Each phase must pass all tests, type checks, and linting before proceeding.

---

## Phase Overview

| Phase | Name | Depends On | Deliverables |
|-------|------|------------|-------------|
| 0 | Specification Validation | — | Consistency audit, updated specs, ambiguity resolution |
| 1 | Foundation & Project Setup | Phase 0 | pyproject.toml, configs, DB adapter, migrations framework |
| 2 | Domain Models & Contracts | Phase 1 | Pydantic models, enums, value objects |
| 3 | SQLite Operational Database | Phase 2 | Schema, migrations, repository layer |
| 4 | Risk Engine | Phase 2, 3 | RiskPolicy, validators, engine, risk decisions |
| 5 | Execution Service | Phase 3, 4 | State machine, idempotency, order management |
| 6 | Exchange Adapter | Phase 5 | Base adapter, MockExchange, Binance adapter shell |
| 7 | Portfolio Accounting | Phase 3, 6 | Position tracking, PnL, balance reconciliation |
| 8 | Hermes Integration Boundary | Phase 2, 7 | Gateway, tool contracts, security boundary |
| 9 | Market Data & Regime Engine | Phase 1 | Ingestion, validation, regime classification |
| 10 | Strategy Framework | Phase 2, 9 | Lifecycle, versioning, configuration |
| 11 | Operations & Kill Switch | Phase 4, 5 | Kill switch, health, monitoring, audit |
| 12 | Backtesting Framework | Phase 7, 9, 10 | Engine, cost model, WFO, Monte Carlo |
| 13 | DuckDB/Parquet Analytics | Phase 9 | Parquet storage, DuckDB queries |
| 14 | Knowledge Layer | Phase 7 | Obsidian indexing, search, learning pipeline |
| 15 | Web Application | Phase 4-14 | API, frontend, dashboard |
| 16 | End-to-End Integration | Phase 1-15 | Full pipeline tests, shadow mode |

---

## Phase 0: Specification Validation

### Tasks

- [x] Read architecture.md completely
- [x] Read implementation_spec.md, DEVELOPMENT_PLAN.md, AI_ENGINEERING_RULES.md
- [x] 16-point consistency audit (architecture vs spec vs plan vs rules)
- [x] Verify Hermes boundary (external, not implemented here)
- [x] Verify Risk boundary (deterministic, independent of Hermes)
- [x] Verify Execution authority (only Execution Service submits orders)
- [x] Verify Database source of truth (SQLite operational, DuckDB analytics)
- [x] Verify State machine (no ambiguous states)
- [x] Verify Idempotency contract
- [x] Verify Reconciliation algorithm
- [x] Verify Environment modes (7 trading modes)
- [x] Verify Security boundaries
- [x] Document and classify all ambiguities by severity
- [x] Update all specification documents

### Acceptance Criteria

- [x] No critical architectural contradiction
- [x] Hermes boundary explicitly defined
- [x] Risk boundary explicitly defined
- [x] Execution authority explicitly defined
- [x] Database source of truth defined
- [x] State machine defined (with RISK_REJECTED / EXCHANGE_REJECTED split)
- [x] Idempotency defined
- [x] Reconciliation defined
- [x] Environment modes defined
- [x] Testing strategy defined

---

## Phase 1: Foundation & Project Setup

### Tasks

- [x] Create `pyproject.toml` with dependencies (pydantic, pytest, mypy, ruff, aiosqlite, httpx, duckdb, pyyaml)
- [x] Create `__init__.py` files for all packages
- [x] Create `.env.example` with documented environment variables
- [x] Create `.gitignore` for Python project
- [x] Create `configs/environments/development.yaml`
- [x] Create `configs/environments/paper.yaml`
- [x] Create `configs/environments/testnet.yaml`
- [x] Create environment configuration loader (`core/config.py`)
- [x] Create base error types and error codes (`core/errors.py`)
- [x] Create logging configuration with structured audit logging (`core/logging.py`)
- [x] Create SQLite connection manager (`adapters/database/sqlite.py`)
- [x] Create migration framework (`migrations/`)

### Tests

- [x] Config loading unit tests (25 tests)
- [x] SQLite connection unit tests (15 tests)
- [x] Migration framework unit tests (12 tests)
- [x] Error type tests (20 tests)
- [x] Logging unit tests (12 tests)

### Acceptance Criteria

- [x] `pytest` passes (84 tests, 0.35s)
- [x] `mypy` passes with strict mode (43 source files)
- [x] `ruff` passes (all checks passed)
- [x] All packages importable
- [x] SQLite database can be created and migrated

---

## Phase 2: Domain Models & Contracts

### Tasks

- [x] `core/domain/enums.py` — TradingMode, OrderSide, OrderType, OrderStatus, PositionSide, MarketRegime, RiskDecisionType, ExecutionState (with RISK_REJECTED + EXCHANGE_REJECTED), StrategyLifecycle, KillSwitchState
- [x] `core/domain/trade_proposal.py` — TradeProposal Pydantic model with strict validation (including model_version per architecture §21)
- [x] `core/domain/order.py` — Order, OrderRequest, OrderFill Pydantic models
- [x] `core/domain/fill.py` — Fill model with fee/slippage tracking
- [x] `core/domain/position.py` — Position model with PnL calculation
- [x] `core/domain/portfolio.py` — PortfolioState model
- [x] `core/domain/market_state.py` — MarketState, OHLCV, OrderBook, AccountInfo models
- [x] `core/domain/system_state.py` — SystemState model
- [x] `core/domain/events.py` — Event schema (TradeEvent, RiskEvent, SystemEvent, AuditEvent)

### Tests

- [x] Validation tests for every model (valid/invalid inputs) — 292 tests
- [x] Serialization round-trip tests
- [x] Enum completeness tests
- [x] TradeProposal constraint tests (confidence bounds, required fields)

### Acceptance Criteria

- [x] All models validate correctly
- [x] Invalid data is rejected with clear errors
- [x] Models serialize/deserialize cleanly
- [x] Type checking passes (`mypy --strict`: 12 source files, 0 errors)
- [x] Lint passes (`ruff`: all checks passed)
- [x] 376 total tests pass (292 domain + 84 foundation)

---

## Phase 3: SQLite Operational Database

### Tasks

- [x] Define SQLite schema for: trades, orders, fills, positions, balances, risk_decisions, authorizations, state_transitions, system_events, strategy_versions (`migrations/001_initial_schema.sql`)
- [x] Create numbered migration files (001_initial_schema.sql)
- [x] Implement migration runner with version tracking (`migrations/runner.py`)
- [x] Implement repository layer (`adapters/repositories/sqlite_repos.py`) with repositories for all 10 canonical operational entities
- [x] Configure WAL mode and appropriate pragmas (`PRAGMA journal_mode=WAL`, foreign_keys, busy_timeout)
- [x] Implement idempotent insert patterns (`ON CONFLICT` primary key strategies)

### Tests

- [x] Schema creation & migration tests
- [x] Migration runner idempotency & version tracking tests
- [x] CRUD tests for all 10 repositories
- [x] Transaction atomicity & rollback tests
- [x] Primary key & foreign key constraint tests
- [x] Data persistence across connection reopening tests
- [x] Verification that Obsidian is NOT used as an operational state store

### Acceptance Criteria

- [x] Schema matches architecture specification (10 entities implemented)
- [x] All repositories perform CRUD correctly & map Pydantic domain models
- [x] Concurrent reads/writes supported via WAL
- [x] Audit trail works (state_transitions, authorizations, system_events)
- [x] All tests pass (395 total tests pass in 0.98s)
- [x] Type checking (`mypy --strict`) and linting (`ruff`) clean

---

## Phase 4: Risk Engine

### Tasks

- [x] `core/risk/policy.py` — RiskPolicy model re-export and `load_risk_policy` YAML configuration loader
- [x] `core/risk/decisions.py` — Re-exports RiskDecision, RiskViolation, RiskDecisionType
- [x] `core/risk/validators.py` — 20 individual deterministic validators: position_size, portfolio_exposure, symbol_exposure, strategy_exposure, correlated_exposure, daily_loss, weekly_loss, drawdown, order_notional, concurrent_positions, concurrent_orders, leverage, spread, slippage, liquidity, stale_data, price_deviation, macro_event, kill_switch, trading_mode
- [x] `core/risk/engine.py` — Deterministic RiskEngine evaluating TradeProposal against MarketState, PortfolioState, RiskPolicy, SystemState
- [x] `configs/risk.yaml` — Default risk policy configuration file

### Tests

- [x] Unit test for every individual validator (pass/fail cases for all 20 rules)
- [x] Determinism test: identical inputs → identical decision & violations
- [x] Kill switch test: FREEZE overrides all (SOFT_KILL / HARD_KILL)
- [x] LLM confidence isolation test: LLM confidence cannot override risk rejection or FREEZE
- [x] Critical invariants test: 5 critical safety invariants proven by test suite
- [x] Integration & boundary tests: exact limits, multiple simultaneous violations, YAML policy loading

### Acceptance Criteria

- [x] All 20 risk rules implemented and tested
- [x] Deterministic evaluation (proven by test suite)
- [x] Every rule tested independently
- [x] Edge cases and multiple simultaneous violations tested
- [x] Kill switch tested (`KillSwitchState` -> FREEZE)
- [x] FREEZE decision outcome fully tested
- [x] LLM cannot override risk decisions
- [x] All 445 tests pass (1.05s execution time)
- [x] `mypy --strict` and `ruff` linting clean

---

## Phase 5: Execution Service

### Tasks

- [x] `core/execution/state_machine.py` — ExecutionStateMachine with RISK_REJECTED/EXCHANGE_REJECTED split (architecture §12, spec §5)
- [x] `core/execution/idempotency.py` — Client-side order ID generation (TRD-YYYYMMDD-NNNNNN), duplicate detection
- [x] `core/execution/service.py` — ExecutionService: accept approved proposals, manage order lifecycle
- [x] `core/execution/reconciliation.py` — Reconciliation algorithm: compare local state with exchange state

### Tests

- [x] State machine transition tests (all valid transitions)
- [x] Invalid transition rejection tests
- [x] Emergency path tests (ANY → UNKNOWN → FREEZE → RECONCILING → RESOLVED)
- [x] RISK_REJECTED vs EXCHANGE_REJECTED distinction tests
- [x] Idempotency: duplicate order prevention
- [x] Timeout + retry → reconcile (not re-submit)
- [x] Partial fill handling
- [x] Order rejection handling
- [x] Reconciliation: local vs exchange mismatch detection
- [x] Failure test: exchange disconnect during order

### Acceptance Criteria

- [x] State machine enforces all valid transitions
- [x] No duplicate orders possible
- [x] Reconciliation detects mismatches
- [x] Unknown state always leads to safe state

---

## Phase 6: Exchange Adapter

### Tasks

- [x] `adapters/exchange/base.py` — Abstract ExchangeAdapter interface (get_account, get_positions, get_open_orders, get_order, submit_order, cancel_order, get_market_data)
- [x] `adapters/exchange/mock/adapter.py` — Full MockExchange with simulated fills, latency, partial fills, rejections
- [x] `adapters/exchange/binance/adapter.py` — Binance adapter shell (REST + WebSocket)
- [x] `adapters/exchange/binance/rest.py` — Binance REST client
- [x] `adapters/exchange/binance/websocket.py` — Binance WebSocket client

### Tests

- [x] MockExchange: order lifecycle (submit → fill)
- [x] MockExchange: partial fills
- [x] MockExchange: order rejection
- [x] MockExchange: simulated latency
- [x] MockExchange: account state consistency
- [x] Interface compliance tests
- [x] Binance adapter: connection/auth tests (mocked HTTP)

### Acceptance Criteria

- [x] ExchangeAdapter interface stable
- [x] Mock adapter works with all failure injections
- [x] Testnet adapter works for REST and WebSocket
- [x] REST verification works for financial state
- [x] Reconnect and error mapping verified
- [x] Live trading protection guard enforced

- MockExchange faithfully simulates exchange behavior
- All adapter methods are testable
- Execution Service works with MockExchange end-to-end
- Binance adapter compiles and passes type checks

---

## Phase 7: Portfolio Accounting & Reconciliation

### Tasks

- [x] `core/portfolio/accounting.py` — Position tracking, realized/unrealized PnL, fee tracking, funding & slippage cost accounting
- [x] `core/portfolio/calculator.py` — Portfolio state calculation (balance, equity, margin, exposure, drawdown)
- [x] `core/execution/reconciliation.py` — State reconciliation algorithm across balances, positions, and open orders
- [x] Mismatch detection & 7-tier classification (MATCH, ORDER_STATUS_MISMATCH, MISSING_LOCAL_ORDER, MISSING_REMOTE_ORDER, POSITION_MISMATCH, BALANCE_MISMATCH, FILL_MISMATCH)
- [x] System FREEZE callback & audit event logging (`system_events`) for critical financial discrepancies
- [x] Process restart / reopen startup reconciliation protocol

### Tests

- [x] Long & short position PnL calculations
- [x] Fee deduction, funding cost, and slippage cost tracking (`Net PnL = Gross PnL - fees - slippage - funding`)
- [x] Drawdown percentage and peak equity high-water-mark tracking
- [x] 10 Mandatory Reconciliation Scenarios:
  1. Matching state (clean report)
  2. Balance mismatch (triggers FREEZE & audit logging)
  3. Position mismatch (triggers FREEZE & audit logging)
  4. Missing local order (auto-created from exchange)
  5. Missing remote order (triggers FREEZE & updates local status)
  6. Local OPEN / Remote FILLED (self-heals local order)
  7. Local FILLED / Remote OPEN (flags status mismatch & self-heals)
  8. Unknown order state handling & state machine recovery
  9. Exchange disconnect error handling during reconciliation
  10. Process restart / reopen startup recovery protocol

### Acceptance Criteria

- [x] PnL calculations are numerically correct
- [x] Net PnL = Gross PnL - fees - slippage - funding
- [x] Reconciliation engine detects & classifies 7 discrepancy types
- [x] Critical financial discrepancies safely trigger system FREEZE
- [x] Startup reconciliation protocol recovers state on process restart

---

## Phase 8: Hermes Integration Boundary

### Tasks

- [ ] `integration/hermes/gateway.py` — HermesGateway: tool registration, request routing, response formatting
- [ ] `integration/hermes/security.py` — Permission enforcement: validate Hermes requests against allowed operations
- [ ] `integration/hermes/tools/market.py` — Market tools (read market state, OHLCV, orderbook)
- [ ] `integration/hermes/tools/research.py` — Research tools (retrieve analysis, regime)
- [ ] `integration/hermes/tools/portfolio.py` — Portfolio tools (read portfolio state, positions, PnL)
- [ ] `integration/hermes/tools/knowledge.py` — Knowledge tools (search, retrieve notes)
- [ ] `integration/hermes/tools/trading.py` — Trading tools (submit TradeProposal — routed through Risk Engine)
- [ ] Define MCP-compatible tool schemas (JSON Schema for inputs/outputs)

### Tests

- [ ] Gateway routes requests correctly
- [ ] Security: block disallowed operations (direct order, credential access, risk modification)
- [ ] TradeProposal submission flows through Risk Engine
- [ ] Tool input/output validation
- [ ] Permission boundary tests (positive and negative)

### Acceptance Criteria

- Hermes can only access explicitly permitted tools
- No path from Hermes to exchange without Risk Engine
- All tool contracts are JSON Schema validated
- Gateway is independently testable

---

## Phase 9: Strategy Framework & Market Regime Engine

### Tasks

- [x] `core/strategy/lifecycle.py` — Canonical Strategy Lifecycle state machine & immutability engine
- [x] `core/strategy/versioning.py` — Semantic versioning & configuration history tracking
- [x] `data/validation/` — Data quality checks (gaps, staleness, anomalies)
- [x] `data/features/` — Feature generation (moving averages, ADX, ATR, volatility, momentum, liquidity, structure)
- [x] `core/strategy/regime.py` — Market regime classification engine (BULL, BEAR, SIDEWAYS, HIGH_VOLATILITY, LOW_VOLATILITY)

### Tests

- [x] Strategy lifecycle transitions & prohibited transition error handling
- [x] Production strategy immutability & parameter mutation safeguards
- [x] Feature calculation correctness (ADX, ATR, RSI, Volatility)
- [x] Regime classification: known market conditions → expected regime
- [x] ADX used for trend strength, NOT direction (architecture §22)

### Acceptance Criteria

- Strategy lifecycle enforced (IDEA -> ... -> PRODUCTION -> DEPRECATED)
- Production versions are strictly immutable (StrategyImmutabilityError on mutation)
- Regime classification uses multiple features (ADX for strength ONLY)
- Regime algorithm independently testable and verified
- Backtesting integration works

---

## Phase 10: Strategy Framework

### Tasks

- [ ] `core/strategy/interface.py` — Strategy interface (entry/exit signals, parameters)
- [ ] `core/strategy/lifecycle.py` — Strategy lifecycle state machine (IDEA → RESEARCH → CANDIDATE → BACKTEST → VALIDATED → PAPER → APPROVED → PRODUCTION → DEPRECATED)
- [ ] `core/strategy/versioning.py` — Immutable version management
- [ ] `configs/strategies/` — Strategy configuration format (YAML)

### Tests

- [ ] Lifecycle transition tests
- [ ] Version immutability tests
- [ ] Strategy configuration loading tests
- [ ] Version metadata recording tests

### Acceptance Criteria

- Strategy versions are immutable
- Lifecycle enforces correct progression
- Every trade records strategy_id + strategy_version

---

## Phase 11: Operations & Kill Switch

### Tasks

- [ ] `operations/kill_switch.py` — KillSwitchController: soft kill (STOP_NEW_ORDERS), hard kill (CANCEL_OPEN + STOP_NEW + OBSERVE)
- [ ] `operations/health.py` — System health checks (exchange connectivity, data freshness, DB, disk)
- [ ] `operations/monitoring.py` — Metrics collection and alerting thresholds
- [ ] `operations/audit.py` — Audit event logging (all state changes, all decisions)
- [ ] `operations/recovery.py` — Recovery procedures (FREEZE → RECONCILE → RESOLVE)

### Tests

- [ ] Soft kill: new orders blocked, existing positions managed
- [ ] Hard kill: open orders cancelled, new orders blocked
- [ ] Health check: detect exchange disconnect, stale data
- [ ] Audit: all events persisted
- [ ] Recovery: UNKNOWN → FREEZE → RECONCILE → RESOLVE

### Acceptance Criteria

- Kill switch is always available (not only via Telegram/web)
- Audit trail is complete and immutable
- Recovery procedure restores safe state

---

## Phase 12: Backtesting Framework

### Tasks

- [ ] `backtesting/engine/` — Backtest engine with event-driven simulation
- [ ] `backtesting/costs/` — Transaction cost model (fees, spread, slippage, funding, latency, partial fills)
- [ ] `backtesting/walk_forward/` — Walk-forward optimization
- [ ] `backtesting/monte_carlo/` — Monte Carlo simulation
- [ ] `backtesting/stress/` — Parameter sensitivity and stress testing
- [ ] `backtesting/metrics/` — Performance metrics (Sharpe, Sortino, max drawdown, win rate, expectancy)

### Tests

- [ ] Known trade sequence → known PnL (net, not gross)
- [ ] Walk-forward produces out-of-sample results
- [ ] Monte Carlo produces distribution of outcomes
- [ ] No look-ahead bias (data leakage protection)
- [ ] Cost model accuracy under stress

### Acceptance Criteria

- Backtests use net economics
- No future data leakage
- Walk-forward analysis works correctly
- Results match hand-calculated expected values

---

## Phase 13: DuckDB/Parquet Analytics

### Tasks

- [ ] `data/parquet/` — Parquet writer for historical market data
- [ ] `data/duckdb/` — DuckDB query interface for analytics
- [ ] Data pipeline: ingestion → validation → Parquet → DuckDB

### Tests

- [ ] Write/read roundtrip for Parquet
- [ ] DuckDB query correctness
- [ ] Large dataset handling

### Acceptance Criteria

- Historical data persisted in Parquet
- DuckDB can query time-series efficiently
- Analytics pipeline works end-to-end

---

## Phase 14: Knowledge Layer

### Tasks

- [ ] `knowledge/obsidian/` — Obsidian vault reader, Markdown parser
- [ ] `knowledge/indexing/` — File watcher, knowledge index builder
- [ ] `knowledge/search/` — Full-text and tag-based search
- [ ] `knowledge/learning/` — Learning pipeline (observation → hypothesis → candidate → validation)

### Tests

- [ ] Markdown parsing accuracy
- [ ] Search returns relevant results
- [ ] Learning pipeline state transitions
- [ ] Obsidian unavailable → trading continues

### Acceptance Criteria

- Knowledge is searchable
- Learning pipeline enforces validation steps
- Knowledge layer failure does not block trading

---

## Phase 15: Web Application

### Tasks

- [ ] `web/api/` — REST API for all trading system data
- [ ] `web/frontend/` — Trader Control Center (dashboard, trading, portfolio, risk, AI decisions, strategies, backtesting, knowledge, system health, audit log)
- [ ] `web/services/` — WebSocket service for live updates

### Tests

- [ ] API endpoint tests
- [ ] Authentication/authorization tests
- [ ] Frontend rendering tests

### Acceptance Criteria

- All system data accessible via web UI
- Kill switch accessible from web
- Knowledge center with Obsidian reader functional

---

## Phase 16: End-to-End Integration

### Tasks

- [ ] Full pipeline test: TradeProposal → Risk → Execution → MockExchange → Portfolio update
- [ ] Shadow mode: run alongside live market data without real orders
- [ ] Recovery scenario: simulate exchange disconnect mid-order
- [ ] Multi-proposal stress test

### Tests

- [ ] End-to-end happy path
- [ ] End-to-end rejection path
- [ ] End-to-end failure/recovery path
- [ ] Concurrent proposal handling
- [ ] Kill switch during active trading

### Acceptance Criteria

- Full pipeline works with MockExchange
- Recovery from any failure state
- All audit events captured
- System ready for PAPER mode

---

## Failure Conditions (Any Phase)

A phase MUST NOT be marked complete if:

- Any test fails
- Type checking (`mypy --strict`) fails
- Linting (`ruff`) fails
- Architecture constraints are violated
- Safety checks are bypassed
- Documentation is not updated
