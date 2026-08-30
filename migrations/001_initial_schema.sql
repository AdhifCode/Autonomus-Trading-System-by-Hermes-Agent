-- 001_initial_schema.sql
-- SQLite operational schema definition (implementation_spec.md §6 & architecture.md §14)

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- 1. Trades
CREATE TABLE IF NOT EXISTS trades (
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

-- 2. Orders
CREATE TABLE IF NOT EXISTS orders (
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

-- 3. Fills
CREATE TABLE IF NOT EXISTS fills (
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

-- 4. Positions
CREATE TABLE IF NOT EXISTS positions (
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

-- 5. Balances
CREATE TABLE IF NOT EXISTS balances (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    currency TEXT NOT NULL,
    total REAL NOT NULL,
    available REAL NOT NULL,
    locked REAL DEFAULT 0,
    source TEXT NOT NULL,  -- 'local' or 'exchange'
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 6. Risk Decisions
CREATE TABLE IF NOT EXISTS risk_decisions (
    decision_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    decision TEXT NOT NULL,
    violations TEXT,  -- JSON array
    policy_version TEXT NOT NULL,
    computation_ms REAL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 7. Authorizations
CREATE TABLE IF NOT EXISTS authorizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposal_id TEXT NOT NULL,
    decision_id TEXT NOT NULL,
    authorized_by TEXT NOT NULL,  -- 'risk_engine', 'human'
    action TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 8. State Transitions
CREATE TABLE IF NOT EXISTS state_transitions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,  -- 'trade', 'order', 'position'
    entity_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    to_state TEXT NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 9. System Events
CREATE TABLE IF NOT EXISTS system_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type TEXT NOT NULL,
    severity TEXT NOT NULL,  -- INFO, WARNING, ERROR, CRITICAL
    source TEXT NOT NULL,
    message TEXT NOT NULL,
    metadata TEXT,  -- JSON
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 10. Strategy Versions
CREATE TABLE IF NOT EXISTS strategy_versions (
    strategy_id TEXT NOT NULL,
    version TEXT NOT NULL,
    config TEXT NOT NULL,  -- JSON
    lifecycle TEXT NOT NULL DEFAULT 'IDEA',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (strategy_id, version)
);

-- Indexes for performance & quick queries
CREATE INDEX IF NOT EXISTS idx_trades_proposal ON trades(proposal_id);
CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);
CREATE INDEX IF NOT EXISTS idx_orders_proposal ON orders(proposal_id);
CREATE INDEX IF NOT EXISTS idx_orders_trade ON orders(trade_id);
CREATE INDEX IF NOT EXISTS idx_orders_status ON orders(status);
CREATE INDEX IF NOT EXISTS idx_fills_order ON fills(order_id);
CREATE INDEX IF NOT EXISTS idx_positions_symbol ON positions(symbol);
CREATE INDEX IF NOT EXISTS idx_risk_decisions_proposal ON risk_decisions(proposal_id);
CREATE INDEX IF NOT EXISTS idx_authorizations_proposal ON authorizations(proposal_id);
CREATE INDEX IF NOT EXISTS idx_state_transitions_entity ON state_transitions(entity_type, entity_id);
CREATE INDEX IF NOT EXISTS idx_system_events_type_sev ON system_events(event_type, severity);
