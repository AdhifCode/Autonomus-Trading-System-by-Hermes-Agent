# Implementation Specification

> Derived from `architecture.md` V2/V2.1. Source of truth: `architecture.md`.

---

## 1. Enums

```python
class TradingMode(str, Enum):
    DEVELOPMENT = "DEVELOPMENT"
    BACKTEST = "BACKTEST"
    SHADOW = "SHADOW"
    PAPER = "PAPER"
    TESTNET = "TESTNET"
    LIMITED_LIVE = "LIMITED_LIVE"
    LIVE = "LIVE"


class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"


class OrderType(str, Enum):
    MARKET = "MARKET"
    LIMIT = "LIMIT"
    STOP_MARKET = "STOP_MARKET"
    STOP_LIMIT = "STOP_LIMIT"


class OrderStatus(str, Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class PositionSide(str, Enum):
    LONG = "LONG"
    SHORT = "SHORT"


class MarketRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"


class RiskDecisionType(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    FREEZE = "FREEZE"


class ExecutionState(str, Enum):
    PROPOSAL_CREATED = "PROPOSAL_CREATED"
    RISK_PENDING = "RISK_PENDING"
    RISK_REJECTED = "RISK_REJECTED"  # rejected by Risk Engine
    APPROVED = "APPROVED"
    EXECUTION_PENDING = "EXECUTION_PENDING"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    EXCHANGE_REJECTED = "EXCHANGE_REJECTED"  # rejected by exchange
    PARTIAL = "PARTIAL"
    FILLED = "FILLED"
    POSITION_ACTIVE = "POSITION_ACTIVE"
    EXIT_PENDING = "EXIT_PENDING"
    POSITION_CLOSED = "POSITION_CLOSED"
    RECONCILED = "RECONCILED"
    UNKNOWN = "UNKNOWN"
    FREEZE = "FREEZE"
    RECONCILING = "RECONCILING"
    RESOLVED = "RESOLVED"


class StrategyLifecycle(str, Enum):
    IDEA = "IDEA"
    RESEARCH = "RESEARCH"
    CANDIDATE = "CANDIDATE"
    BACKTEST = "BACKTEST"
    VALIDATED = "VALIDATED"
    PAPER = "PAPER"
    APPROVED = "APPROVED"
    PRODUCTION = "PRODUCTION"
    DEPRECATED = "DEPRECATED"


class KillSwitchState(str, Enum):
    ACTIVE = "ACTIVE"
    SOFT_KILL = "SOFT_KILL"
    HARD_KILL = "HARD_KILL"
```

---

## 2. Pydantic Domain Models

### TradeProposal

```python
class EntrySpec(BaseModel):
    price: float = Field(gt=0)
    order_type: OrderType


class StopLossSpec(BaseModel):
    price: float = Field(gt=0)


class TakeProfitSpec(BaseModel):
    price: float = Field(gt=0)


class PositionSizeSpec(BaseModel):
    requested_pct: float = Field(gt=0, le=1.0)


class TradeProposal(BaseModel):
    proposal_id: str = Field(pattern=r"^PRP-\d{8}-\d{6}$")
    symbol: str = Field(min_length=1)
    side: OrderSide
    strategy_id: str
    strategy_version: str
    model_version: str  # LLM model version (architecture §21)
    thesis: str = Field(min_length=10)
    entry: EntrySpec
    stop_loss: StopLossSpec
    take_profit: TakeProfitSpec
    position_size: PositionSizeSpec
    market_regime: MarketRegime
    invalidation_conditions: list[str] = Field(min_length=1)
    evidence: list[str] = Field(min_length=1)
    uncertainty: list[str]
    llm_confidence: float = Field(ge=0.0, le=1.0)
    created_at: datetime
```

### Order

```python
class OrderRequest(BaseModel):
    client_order_id: str = Field(pattern=r"^TRD-\d{8}-\d{6}$")
    proposal_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float = Field(gt=0)
    price: float | None = Field(default=None, gt=0)
    stop_price: float | None = Field(default=None, gt=0)


class Order(BaseModel):
    client_order_id: str
    exchange_order_id: str | None = None
    proposal_id: str
    symbol: str
    side: OrderSide
    order_type: OrderType
    quantity: float
    filled_quantity: float = 0.0
    price: float | None = None
    average_fill_price: float | None = None
    status: OrderStatus = OrderStatus.PENDING
    created_at: datetime
    updated_at: datetime
```

### Fill

```python
class Fill(BaseModel):
    fill_id: str
    order_id: str
    symbol: str
    side: OrderSide
    quantity: float = Field(gt=0)
    price: float = Field(gt=0)
    fee: float = Field(ge=0)
    fee_currency: str
    timestamp: datetime
```

### Position

```python
class Position(BaseModel):
    position_id: str
    symbol: str
    side: PositionSide
    quantity: float = Field(gt=0)
    entry_price: float = Field(gt=0)
    current_price: float = Field(gt=0)
    unrealized_pnl: float = 0.0
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    total_funding: float = 0.0
    total_slippage: float = 0.0
    strategy_id: str
    strategy_version: str
    opened_at: datetime
    updated_at: datetime
```

### PortfolioState

```python
class PortfolioState(BaseModel):
    balance: float
    equity: float
    available_margin: float
    positions: list[Position]
    exposure: float
    realized_pnl: float
    unrealized_pnl: float
    daily_pnl: float
    drawdown: float
    open_orders: list[Order]
    timestamp: datetime
```

### MarketState

```python
class OHLCV(BaseModel):
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderBookEntry(BaseModel):
    price: float
    quantity: float


class OrderBook(BaseModel):
    bids: list[OrderBookEntry]
    asks: list[OrderBookEntry]
    timestamp: datetime


class MarketState(BaseModel):
    symbol: str
    price: float
    bid: float
    ask: float
    spread: float
    volume_24h: float
    ohlcv: list[OHLCV]
    order_book: OrderBook | None = None
    timestamp: datetime
    data_age_seconds: float
```

### SystemState

```python
class AccountInfo(BaseModel):
    """Exchange account information returned by ExchangeAdapter.get_account()"""

    balance: float
    equity: float
    available_margin: float
    unrealized_pnl: float
    timestamp: datetime


class SystemState(BaseModel):
    trading_mode: TradingMode
    kill_switch: KillSwitchState
    exchange_connected: bool
    data_healthy: bool
    last_heartbeat: datetime
    active_errors: list[str]
```

---

## 3. RiskPolicy

```python
class RiskPolicy(BaseModel):
    # Position limits
    max_position_size_pct: float = 0.05
    max_portfolio_exposure_pct: float = 0.50
    max_symbol_exposure_pct: float = 0.20
    max_strategy_exposure_pct: float = 0.30
    max_correlated_exposure_pct: float = 0.40

    # Loss limits
    max_daily_loss_pct: float = 0.03
    max_weekly_loss_pct: float = 0.07
    max_drawdown_pct: float = 0.15

    # Order limits
    max_order_notional: float = 10000.0
    max_concurrent_positions: int = 5
    max_concurrent_orders: int = 10
    max_leverage: float = 3.0

    # Market quality
    max_spread_pct: float = 0.005
    max_slippage_pct: float = 0.01
    min_liquidity_usd: float = 50000.0

    # Data health
    stale_data_timeout_seconds: int = 60
    max_price_deviation_pct: float = 0.10

    # Restrictions
    macro_event_restriction: bool = False

    # NOTE: kill_switch and trading_mode are read from SystemState,
    # NOT stored in RiskPolicy. The Risk Engine receives both
    # RiskPolicy and SystemState as separate inputs (architecture §6).
    # RiskPolicy is file-based and immutable at runtime.

    policy_version: str
```

## 4. RiskDecision

```python
class RiskViolation(BaseModel):
    validator: str
    rule: str
    current_value: float | str
    limit_value: float | str
    message: str


class RiskDecision(BaseModel):
    decision_id: str
    proposal_id: str
    decision: RiskDecisionType
    violations: list[RiskViolation]
    policy_version: str
    timestamp: datetime
    computation_ms: float
```

---

## 5. Execution State Machine

### Valid Transitions

```python
VALID_TRANSITIONS: dict[ExecutionState, list[ExecutionState]] = {
    PROPOSAL_CREATED: [RISK_PENDING],
    RISK_PENDING: [APPROVED, RISK_REJECTED],
    APPROVED: [EXECUTION_PENDING],
    EXECUTION_PENDING: [ORDER_SUBMITTED],
    ORDER_SUBMITTED: [PARTIAL, FILLED, EXCHANGE_REJECTED],
    PARTIAL: [FILLED],
    FILLED: [POSITION_ACTIVE],
    POSITION_ACTIVE: [EXIT_PENDING],
    EXIT_PENDING: [POSITION_CLOSED],
    POSITION_CLOSED: [RECONCILED],
    # Emergency: any state → UNKNOWN
    UNKNOWN: [FREEZE],
    FREEZE: [RECONCILING],
    RECONCILING: [RESOLVED],
}
```

### Emergency Path

Any state may transition to `UNKNOWN`. From there: `UNKNOWN → FREEZE → RECONCILING → RESOLVED`.

---

## 6. SQLite Schema

```sql
-- 001_initial_schema.sql

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE trades (
    trade_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    model_version TEXT,               -- LLM model version (architecture §21)
    risk_policy_version TEXT NOT NULL, -- risk policy version (architecture §21)
    entry_price REAL,
    exit_price REAL,
    quantity REAL,
    gross_pnl REAL,
    fees REAL DEFAULT 0,
    slippage_cost REAL DEFAULT 0,
    funding_cost REAL DEFAULT 0,
    net_pnl REAL,
    net_return REAL,
    market_regime TEXT,
    llm_confidence REAL,
    risk_decision TEXT NOT NULL,
    entry_at TEXT,
    exit_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE orders (
    client_order_id TEXT PRIMARY KEY,
    exchange_order_id TEXT,
    proposal_id TEXT NOT NULL,
    trade_id TEXT REFERENCES trades(trade_id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    order_type TEXT NOT NULL,
    quantity REAL NOT NULL,
    filled_quantity REAL DEFAULT 0,
    price REAL,
    stop_price REAL,
    average_fill_price REAL,
    status TEXT NOT NULL DEFAULT 'PENDING',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE fills (
    fill_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL REFERENCES orders(client_order_id),
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    fee REAL NOT NULL DEFAULT 0,
    fee_currency TEXT NOT NULL,
    timestamp TEXT NOT NULL
);

CREATE TABLE positions (
    position_id TEXT PRIMARY KEY,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    entry_price REAL NOT NULL,
    current_price REAL NOT NULL,
    unrealized_pnl REAL DEFAULT 0,
    realized_pnl REAL DEFAULT 0,
    total_fees REAL DEFAULT 0,
    total_funding REAL DEFAULT 0,
    total_slippage REAL DEFAULT 0,
    strategy_id TEXT NOT NULL,
    strategy_version TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    currency TEXT NOT NULL,
    total REAL NOT NULL,
    available REAL NOT NULL,
    locked REAL DEFAULT 0,
    source TEXT NOT NULL,  -- 'local' or 'exchange'
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE risk_decisions (
    decision_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    violations TEXT,  -- JSON array
    policy_version TEXT NOT NULL,
    computation_ms REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE state_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,  -- 'trade', 'order', 'position'
    entity_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,  -- INFO, WARNING, ERROR, CRITICAL
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata TEXT,  -- JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE strategy_versions (
    strategy_id TEXT NOT NULL,
    version TEXT NOT NULL,
    config TEXT NOT NULL,  -- JSON
    lifecycle TEXT NOT NULL DEFAULT 'IDEA',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (strategy_id, version)
);

CREATE TABLE authorizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    authorized_by TEXT NOT NULL,  -- 'risk_engine', 'human'
    action TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Migration tracking
CREATE TABLE schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## 7. ExchangeAdapter Interface

```python
class ExchangeAdapter(ABC):
    @abstractmethod
    async def get_account(self) -> AccountInfo: ...

    @abstractmethod
    async def get_positions(self) -> list[Position]: ...

    @abstractmethod
    async def get_open_orders(self) -> list[Order]: ...

    @abstractmethod
    async def get_order(self, order_id: str) -> Order: ...

    @abstractmethod
    async def submit_order(self, request: OrderRequest) -> Order: ...

    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool: ...

    @abstractmethod
    async def get_market_data(self, symbol: str) -> MarketState: ...

    @abstractmethod
    async def get_ohlcv(self, symbol: str, interval: str, limit: int) -> list[OHLCV]: ...
```

### MockExchange

Must simulate: order fills (full/partial), rejections, latency, account state tracking, balance updates on fills.

---

## 8. Idempotency Contract

- Format: `TRD-YYYYMMDD-NNNNNN` (e.g., `TRD-20260828-000123`)
- Sequence number resets daily, persisted in SQLite
- Before submitting: check local DB for existing order with same client_order_id
- On timeout: query exchange, reconcile, determine actual state — never re-submit blindly

---

## 9. Reconciliation Algorithm

```
1. Fetch exchange positions, orders, balances
2. Fetch local positions, orders, balances from SQLite
3. Compare:
   a. Orders: match by client_order_id, compare status/fills
   b. Positions: match by symbol, compare quantity/side
   c. Balances: compare totals within tolerance
4. For each mismatch:
   a. Log discrepancy as CRITICAL system_event
   b. If order status differs: update local to exchange truth
   c. If position differs: FREEZE + manual review
   d. If balance differs beyond threshold: FREEZE + manual review
5. Mark reconciliation timestamp
```

---

## 10. Event Schema

```python
class EventType(str, Enum):
    TRADE_PROPOSED = "TRADE_PROPOSED"
    RISK_EVALUATED = "RISK_EVALUATED"
    ORDER_SUBMITTED = "ORDER_SUBMITTED"
    ORDER_FILLED = "ORDER_FILLED"
    ORDER_REJECTED = "ORDER_REJECTED"
    POSITION_OPENED = "POSITION_OPENED"
    POSITION_CLOSED = "POSITION_CLOSED"
    KILL_SWITCH_ACTIVATED = "KILL_SWITCH_ACTIVATED"
    RECONCILIATION_STARTED = "RECONCILIATION_STARTED"
    RECONCILIATION_COMPLETED = "RECONCILIATION_COMPLETED"
    STATE_TRANSITION = "STATE_TRANSITION"
    SYSTEM_ERROR = "SYSTEM_ERROR"
    DATA_STALE = "DATA_STALE"
    EXCHANGE_DISCONNECTED = "EXCHANGE_DISCONNECTED"


class AuditEvent(BaseModel):
    event_id: str
    event_type: EventType
    severity: str  # INFO, WARNING, ERROR, CRITICAL
    source: str
    entity_type: str | None = None
    entity_id: str | None = None
    message: str
    metadata: dict | None = None
    timestamp: datetime
```

---

## 11. Portfolio Accounting

- **Net PnL** = Gross PnL - fees - slippage - funding
- Long PnL = (exit_price - entry_price) × quantity
- Short PnL = (entry_price - exit_price) × quantity
- Drawdown = (peak_equity - current_equity) / peak_equity
- Daily PnL resets at UTC midnight
- All percentages stored as decimals (0.0165, not "1.65%")

---

## 12. Transaction Cost Model

```python
class TransactionCosts(BaseModel):
    fee_rate: float = 0.001  # 0.1% taker
    maker_fee_rate: float = 0.0005  # 0.05% maker
    estimated_slippage_pct: float = 0.001
    funding_rate: float = 0.0001  # per 8h
    latency_ms: float = 100.0
    partial_fill_probability: float = 0.1
```

---

## 13. Market Regime Interface

```python
class RegimeFeatures(BaseModel):
    trend_direction: float  # -1 to +1
    trend_strength: float  # 0 to 1 (ADX normalized)
    volatility: float  # realized vol
    liquidity: float  # volume / avg volume
    momentum: float  # rate of change
    market_structure: str  # higher-highs, lower-lows, range


class RegimeClassifier(ABC):
    @abstractmethod
    def classify(self, features: RegimeFeatures) -> MarketRegime: ...
```

ADX measures trend strength only, not direction (per architecture §22).

---

## 14. Backtesting API

```python
class BacktestConfig(BaseModel):
    strategy_id: str
    strategy_version: str
    symbol: str
    start_date: date
    end_date: date
    initial_capital: float
    cost_model: TransactionCosts
    risk_policy: RiskPolicy


class BacktestResult(BaseModel):
    config: BacktestConfig
    total_trades: int
    winning_trades: int
    losing_trades: int
    gross_pnl: float
    net_pnl: float
    total_fees: float
    total_slippage: float
    max_drawdown: float
    sharpe_ratio: float
    sortino_ratio: float
    win_rate: float
    expectancy: float
    trades: list[dict]
```

Data split baseline: TRAIN 2016-2022, VALIDATION 2023-2024, TEST 2025-present. Chronological separation enforced — no future data leakage.

---

## 15. Strategy Configuration

```yaml
# configs/strategies/breakout_v2_1.yaml
strategy_id: breakout
version: "2.1"
lifecycle: PRODUCTION
parameters:
  lookback_period: 20
  breakout_threshold: 1.5
  volume_confirmation: true
  atr_multiplier: 2.0
risk_overrides:
  max_position_size_pct: 0.03
applicable_regimes:
  - BULL
  - SIDEWAYS
metadata:
  created_at: "2026-08-01"
  created_by: "human"
  backtest_sharpe: 1.45
```

---

## 16. Hermes Integration Contract

### Permitted Tools

| Tool | Domain | Access |
|------|--------|--------|
| get_market_state | Market | READ |
| get_ohlcv | Market | READ |
| get_orderbook | Market | READ |
| get_regime | Research | READ |
| get_portfolio | Portfolio | READ |
| get_positions | Portfolio | READ |
| get_pnl | Portfolio | READ |
| search_knowledge | Knowledge | READ |
| get_note | Knowledge | READ |
| get_strategy | Knowledge | READ |
| submit_proposal | Trading | WRITE (via Risk Engine) |
| post_reflection | Knowledge | WRITE |

### Blocked Operations

Direct order submission, credential access, risk policy modification, kill switch control, LIVE activation, strategy deployment.

### Tool Schema (JSON Schema)

Each tool has a strict JSON Schema for input and output. The gateway validates all requests before routing.

---

## 17. Knowledge/RAG Interface

```python
class KnowledgeQuery(BaseModel):
    query: str
    filters: KnowledgeFilters | None = None
    max_results: int = 10


class KnowledgeFilters(BaseModel):
    tags: list[str] | None = None
    symbols: list[str] | None = None
    strategies: list[str] | None = None
    regimes: list[MarketRegime] | None = None
    date_from: date | None = None
    date_to: date | None = None
    categories: list[str] | None = None


class KnowledgeResult(BaseModel):
    note_id: str
    title: str
    path: str
    excerpt: str
    tags: list[str]
    relevance_score: float
    created_at: datetime
    available_at: datetime  # temporal provenance (architecture §26)
    updated_at: datetime
```

Temporal provenance: every knowledge object tracks `created_at`, `available_at`, `effective_at`. For decision at time T, retrieval excludes `available_at > T`.

---

## 18. Error Codes

```python
class ErrorCode(str, Enum):
    # Risk — one per validator from architecture §7
    RISK_POSITION_SIZE = "RISK_001"
    RISK_PORTFOLIO_EXPOSURE = "RISK_002"
    RISK_DAILY_LOSS = "RISK_003"
    RISK_WEEKLY_LOSS = "RISK_004"
    RISK_DRAWDOWN = "RISK_005"
    RISK_KILL_SWITCH = "RISK_006"
    RISK_TRADING_MODE = "RISK_007"
    RISK_STALE_DATA = "RISK_008"
    RISK_SPREAD = "RISK_009"
    RISK_LIQUIDITY = "RISK_010"
    RISK_SYMBOL_EXPOSURE = "RISK_011"
    RISK_STRATEGY_EXPOSURE = "RISK_012"
    RISK_CORRELATED_EXPOSURE = "RISK_013"
    RISK_ORDER_NOTIONAL = "RISK_014"
    RISK_CONCURRENT_POSITIONS = "RISK_015"
    RISK_CONCURRENT_ORDERS = "RISK_016"
    RISK_LEVERAGE = "RISK_017"
    RISK_SLIPPAGE = "RISK_018"
    RISK_PRICE_DEVIATION = "RISK_019"
    RISK_MACRO_EVENT = "RISK_020"

    # Execution
    EXEC_DUPLICATE_ORDER = "EXEC_001"
    EXEC_INVALID_TRANSITION = "EXEC_002"
    EXEC_EXCHANGE_TIMEOUT = "EXEC_003"
    EXEC_EXCHANGE_REJECTED = "EXEC_004"
    EXEC_RECONCILIATION_MISMATCH = "EXEC_005"

    # System
    SYS_EXCHANGE_DISCONNECTED = "SYS_001"
    SYS_DATABASE_ERROR = "SYS_002"
    SYS_CONFIG_ERROR = "SYS_003"

    # Hermes
    HERMES_UNAUTHORIZED = "HERMES_001"
    HERMES_INVALID_PROPOSAL = "HERMES_002"
    HERMES_BLOCKED_OPERATION = "HERMES_003"
```

---

## 19. Logging & Audit

- Structured JSON logging (timestamp, level, source, message, metadata)
- All state transitions logged as AuditEvents
- All risk decisions persisted to `risk_decisions` table
- All orders persisted with full lifecycle in `orders` + `state_transitions`
- Audit log is append-only, never deleted
- Log levels: DEBUG, INFO, WARNING, ERROR, CRITICAL

---

## 20. Environment Configuration

```yaml
# configs/environments/development.yaml
trading_mode: DEVELOPMENT
database:
  path: data/trading_dev.db
exchange:
  adapter: mock
  simulated_latency_ms: 100
risk:
  policy_file: configs/risk.yaml
logging:
  level: DEBUG
  file: logs/trading.log
obsidian:
  vault_path: ~/obsidian-vault
  enabled: false
```

---

## 21. Security Boundaries

- Exchange API keys: loaded from environment variables, never logged, never exposed to Hermes
- Hermes gateway validates all requests against permission whitelist
- Risk policy: file-based, requires restart to change (no runtime modification by AI)
- Kill switch: accessible via local mechanism, web UI, and programmatic API
- LIVE mode: requires explicit human approval flag in environment config

---

## 22. Test Strategy

| Component | Unit | Integration | Failure | Recovery | E2E |
|-----------|------|-------------|---------|----------|-----|
| Domain Models | ✓ | — | — | — | — |
| Risk Engine | ✓ | ✓ | ✓ | — | ✓ |
| Execution Service | ✓ | ✓ | ✓ | ✓ | ✓ |
| Exchange Adapter | ✓ | ✓ | ✓ | — | — |
| Portfolio Accounting | ✓ | ✓ | — | — | ✓ |
| Hermes Gateway | ✓ | ✓ | ✓ | — | — |
| Kill Switch | ✓ | ✓ | ✓ | ✓ | ✓ |
| Reconciliation | ✓ | ✓ | ✓ | ✓ | ✓ |
| Backtesting | ✓ | ✓ | — | — | — |
| Knowledge Layer | ✓ | ✓ | ✓ | — | — |

---

## 23. Identified Ambiguities

| # | Severity | Ambiguity | Resolution |
|---|----------|-----------|------------|
| 1 | **CRITICAL** | Architecture §32 lists `apps/hermes/` but user directive says do not create it | **Do not create `apps/hermes/`**. Only `integration/hermes/` for boundary. Hermes is external. |
| 2 | **HIGH** | §29 defines Telegram commands but §41/V2.1 says Telegram removed | **Follow V2.1**: web + local kill switch, no Telegram. |
| 3 | **MEDIUM** | Exact correlation calculation for `MAX_CORRELATED_EXPOSURE` not specified | Use rolling Pearson correlation with configurable window and threshold. |
| 4 | **HIGH** | WebSocket vs REST authority for fills not fully specified | REST is authoritative for financial state. WebSocket triggers REST verification. |
| 5 | **MEDIUM** | `MAX_LEVERAGE` interaction with futures vs spot not specified | Apply to futures positions only. Spot leverage = 1x always. |
| 6 | **LOW** | Obsidian vault location not specified | Configurable via environment config. Default: `~/obsidian-vault`. |
| 7 | **LOW** | DuckDB schema not specified in detail | Define during Phase 12 based on actual analytical queries needed. |
| 8 | **HIGH** | Architecture §32 lists `tools/` directory but repo uses `integration/hermes/tools/` | **Use `integration/hermes/tools/`**. Tools are part of the Hermes boundary, not standalone. Architecture §27 confirms tools are Hermes-facing. |
| 9 | **CRITICAL** | Architecture §12 uses single `REJECTED` state for both risk rejection and exchange rejection | **Split into `RISK_REJECTED` and `EXCHANGE_REJECTED`** for unambiguous state tracking. |
| 10 | **HIGH** | Architecture §21 requires `model_version` on every trade but original spec omitted it | **Added `model_version`** to TradeProposal model and trades table. |
| 11 | **MEDIUM** | `RiskPolicy` originally included `kill_switch` and `trading_mode` fields, but these are runtime system state, not static policy | **Removed from RiskPolicy**. Risk Engine reads these from SystemState input. Policy is file-based and immutable at runtime. |
| 12 | **MEDIUM** | `AccountInfo` type referenced in ExchangeAdapter but never defined | **Defined `AccountInfo`** Pydantic model with balance, equity, available_margin, unrealized_pnl, timestamp. |
| 13 | **MEDIUM** | Architecture §26 requires `available_at` for temporal provenance but KnowledgeResult lacked it | **Added `available_at`** to KnowledgeResult model. |
| 14 | **LOW** | Architecture §35 lists "Prompt injection isolation" but spec has no corresponding design | Defer to Phase 7 (Hermes Integration). Gateway validates input schemas; no free-form passthrough to exchange operations. |
