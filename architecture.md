# Automated Trading System — Architecture V2

## 1. Executive Summary

Architecture is the baseline for an AI-assisted automated trading system.

The central principle is:

> **Probabilistic intelligence, deterministic authority.**

The LLM/Hermes layer is responsible for market interpretation, research synthesis, reasoning, trade hypotheses, structured trade proposals, and post-trade reflection.

It does **not** have direct authority over capital or the exchange.

All proposed trades must pass through a deterministic Risk Engine before the Execution Service is allowed to submit an order.

The architecture deliberately removes or postpones several components considered premature or over-engineered in the previous design:

- Multi-agent orchestration is postponed.
- Seven separate MCP servers are reduced to domain-oriented tool interfaces.
- Apache Arrow/zero-copy IPC is postponed.
- Autonomous production strategy modification is prohibited.
- Obsidian is removed from the critical execution path.
- Advanced orchestration such as Cost Ladder/UltraCode is postponed until measured requirements justify it.

---

# 2. Core Architectural Principles

## 2.1 Probabilistic Intelligence, Deterministic Authority

The AI layer may:

- Observe market conditions.
- Analyze technical and contextual information.
- Read research.
- Retrieve historical knowledge.
- Form trading hypotheses.
- Produce structured trade proposals.
- Explain uncertainty.
- Perform post-trade reflection.
- Propose candidate strategy improvements.

The AI layer may **not**:

- Submit arbitrary exchange orders.
- Bypass the Risk Engine.
- Override risk limits.
- Modify production risk policy.
- Disable the kill switch.
- Enable LIVE trading autonomously.
- Change a production strategy without validation and approval.

---

## 2.2 Source-of-Truth Separation

Each storage layer has a clearly defined responsibility.

| Layer | Responsibility | Authority |
|---|---|---|
| SQLite | Operational trading state | Canonical operational truth |
| DuckDB + Parquet | Analytics and historical market data | Analytical truth |
| Obsidian | Semantic knowledge and human/AI documentation | Knowledge layer |
| Exchange | External account/order state | External authoritative state |

Obsidian must never become the canonical source for positions, balances, orders, or fills.

---

## 2.3 Fail Safe

When system state becomes uncertain, the default behavior is:

```text
UNKNOWN
   ↓
FREEZE
   ↓
RECONCILE
   ↓
RESOLVE
```

The system must prefer temporarily stopping new trading over making an irreversible assumption about financial state.

---

# 3. High-Level Architecture

```text
                    ┌───────────────────┐
                    │      HERMES       │
                    │   AI Reasoning    │
                    └─────────┬─────────┘
                              │
                        TradeProposal
                              │
                              ▼
                ┌─────────────────────────┐
                │    DETERMINISTIC        │
                │      RISK ENGINE        │
                ├─────────────────────────┤
                │ Position limits         │
                │ Exposure                │
                │ Drawdown                │
                │ Liquidity               │
                │ Slippage                │
                │ Correlation             │
                │ Data health             │
                │ Kill switch             │
                │ Trading mode            │
                └───────────┬─────────────┘
                            │
                 APPROVE / REJECT / FREEZE
                            │
                            ▼
                ┌─────────────────────────┐
                │    EXECUTION SERVICE    │
                ├─────────────────────────┤
                │ Order Manager           │
                │ State Machine           │
                │ Idempotency             │
                │ Reconciliation          │
                │ Exchange Adapter        │
                └───────────┬─────────────┘
                            │
                            ▼
                         EXCHANGE
```

---

# 4. Hermes / AI Cognitive Layer

Hermes acts as the cognitive orchestrator.

## Responsibilities

```text
Observe
  ↓
Analyze
  ↓
Reason
  ↓
Propose
```

Primary capabilities:

- Market analysis.
- Research synthesis.
- Strategy interpretation.
- Historical context retrieval.
- Trade proposal generation.
- Post-trade analysis.
- Knowledge retrieval.

## Explicit Non-Responsibilities

Hermes is not:

- The risk authority.
- The portfolio accounting authority.
- The execution authority.
- The strategy deployment authority.

---

# 5. TradeProposal Contract

Every AI trading decision must be represented as a structured object.

Conceptual schema:

```python
class TradeProposal:
    proposal_id: str

    symbol: str
    side: str

    strategy_id: str
    strategy_version: str

    thesis: str

    entry:
        price: float
        order_type: str

    stop_loss:
        price: float

    take_profit:
        price: float

    position_size:
        requested_pct: float

    market_regime: str

    invalidation_conditions: list[str]

    evidence: list[str]

    uncertainty: list[str]

    llm_confidence: float
```

The actual implementation should use strict schema validation, preferably with Pydantic.

## LLM Confidence

`llm_confidence` is metadata only.

It must not directly determine position sizing or override deterministic risk rules.

```text
LLM confidence ≠ probability of profit
```

---

# 6. Deterministic Risk Engine

The Risk Engine is the primary financial safety boundary.

## Inputs

```text
TradeProposal
MarketState
PortfolioState
RiskPolicy
SystemState
```

## Outputs

```text
APPROVED
REJECTED
FREEZE
```

## Decision Principle

Identical inputs must produce identical risk decisions.

The LLM must not be able to override a rejection.

---

# 7. Risk Policy V2

The minimum policy should support:

```text
MAX_POSITION_SIZE
MAX_PORTFOLIO_EXPOSURE
MAX_SYMBOL_EXPOSURE
MAX_STRATEGY_EXPOSURE
MAX_CORRELATED_EXPOSURE

MAX_DAILY_LOSS
MAX_WEEKLY_LOSS
MAX_DRAWDOWN

MAX_ORDER_NOTIONAL
MAX_CONCURRENT_POSITIONS
MAX_CONCURRENT_ORDERS

MAX_LEVERAGE

MAX_SPREAD
MAX_SLIPPAGE

MIN_LIQUIDITY

STALE_DATA_TIMEOUT
MAX_PRICE_DEVIATION

MACRO_EVENT_RESTRICTION

KILL_SWITCH
TRADING_MODE
```

Risk checks must be deterministic and testable independently from the LLM.

---

# 8. Portfolio State

Portfolio state must be derived from canonical operational data and reconciled with the exchange.

Minimum state:

```text
balance
equity
available_margin
positions
exposure
realized_pnl
unrealized_pnl
daily_pnl
drawdown
open_orders
```

Hermes must never be treated as the source of truth for portfolio state.

---

# 9. Execution Service

The Execution Service is the only component authorized to submit orders to the exchange.

```text
TradeProposal
      ↓
Risk Engine
      ↓
Authorization
      ↓
Execution Service
      ↓
Exchange Adapter
      ↓
Exchange
```

Hermes must not directly call exchange SDK order functions.

---

# 10. Exchange Adapter

The exchange-specific implementation must be isolated behind a common interface.

Conceptual interface:

```python
class ExchangeAdapter:
    def get_account(self): ...

    def get_positions(self): ...

    def get_open_orders(self): ...

    def get_order(self, order_id): ...

    def submit_order(self, order_request): ...

    def cancel_order(self, order_id): ...

    def get_market_data(self): ...
```

This allows the trading core to remain independent of exchange-specific SDK behavior.

---

# 11. WebSocket and REST Responsibilities

## WebSocket

Use WebSocket primarily for:

- Realtime market data.
- Realtime exchange events.
- Low-latency updates.

## REST

Use REST for authoritative state verification:

- Order status.
- Account balance.
- Positions.
- Open orders.

A single WebSocket event must not be treated as the final authority for critical financial state.

---

# 12. Execution State Machine

```text
PROPOSAL_CREATED
       │
       ▼
RISK_PENDING
       │
   ┌───┴────┐
   ▼        ▼
REJECTED  APPROVED
              │
              ▼
       EXECUTION_PENDING
              │
              ▼
        ORDER_SUBMITTED
              │
       ┌──────┼────────┐
       ▼      ▼        ▼
    PARTIAL FILLED  REJECTED
       │
       ▼
    FILLED
       │
       ▼
 POSITION_ACTIVE
       │
       ▼
  EXIT_PENDING
       │
       ▼
 POSITION_CLOSED
       │
       ▼
 RECONCILED
```

Emergency path:

```text
ANY STATE
   ↓
UNKNOWN
   ↓
FREEZE
   ↓
RECONCILING
   ↓
RESOLVED / SAFE_STATE
```

---

# 13. Idempotency

Every order submission must have a unique client-side identifier.

Example:

```text
TRD-20260828-000123
```

The system must prevent duplicate orders caused by network timeouts or retries.

Unsafe pattern:

```text
submit order
↓
timeout
↓
submit again
```

Required pattern:

```text
submit order
↓
timeout
↓
query exchange
↓
reconcile
↓
determine actual state
```

---

# 14. SQLite Operational Database

SQLite is the canonical local operational database.

Recommended logical entities:

```text
trades
orders
fills
positions
balances
risk_decisions
authorizations
state_transitions
system_events
strategy_versions
```

SQLite should be configured appropriately for concurrent operational workloads, including WAL where applicable.

---

# 15. DuckDB + Parquet Analytics Layer

DuckDB and Parquet are retained for analytical workloads.

```text
Historical Market Data
        ↓
     Parquet
        ↓
      DuckDB
        ↓
Backtesting / Analytics
```

Use cases:

- Historical market analysis.
- Large time-series queries.
- Backtesting.
- Performance analysis.
- Strategy research.

Apache Arrow and zero-copy IPC are explicitly **not required for V2**.

They may be introduced later only after benchmarking demonstrates a real bottleneck.

---

# 16. Obsidian Knowledge Layer

Obsidian is a semantic knowledge system, not an operational trading database.

```text
SQLite
   ↓
Trade Event
   ↓
Post-Trade Worker
   ↓
LLM Reflection
   ↓
Obsidian
```

If Obsidian becomes unavailable:

```text
Trading continues
Knowledge processing is queued
```

Obsidian must therefore be outside the critical execution path.

---

# 17. Obsidian V2 Structure

```text
Obsidian Trading Vault/
│
├── Trading Logs/
│   ├── 2026-08-28_TRD-000123_BTC_LONG.md
│   └── ...
│
├── Methodology/
│   ├── Breakout Strategy.md
│   └── ...
│
├── Market Regimes/
│   ├── Bull.md
│   ├── Bear.md
│   ├── Sideways.md
│   └── High Volatility.md
│
├── Lessons Learned/
│   ├── Drawdown Analysis.md
│   ├── Failed Trades.md
│   └── Pattern Recognition.md
│
├── Performance/
│   ├── Weekly Summary.md
│   ├── Monthly Dashboard.md
│   └── Backtest Reports.md
│
└── References/
```

---

# 18. Trade Journal Schema

Each trade must have a unique `trade_id`.

Example:

```yaml
trade_id: TRD-000123

timestamp:
  entry: 2026-08-28T08:30:00Z
  exit: 2026-08-28T14:45:00Z

symbol: BTCUSDT
direction: LONG

strategy_id: breakout
strategy_version: 2.1

entry_price: 42500
exit_price: 43200

quantity: 0.5

gross_pnl: 400
fees: 35
slippage_cost: 15
funding_cost: 0

net_pnl: 350
net_return: 0.0165

market_regime: BULL

llm_confidence: 0.75

risk_decision: APPROVED
risk_policy_version: 1.4

tags:
  - breakout
  - bull
  - profitable
```

Percentages should be stored numerically, not as strings such as `1.65%`.

---

# 19. Learning Loop V2

The old model of directly changing methodology after a trade is prohibited.

## V2 Learning Pipeline

```text
Trade
  ↓
Raw Trade Event
  ↓
Statistical Analysis
  ↓
LLM Reflection
  ↓
Candidate Lesson
  ↓
Evidence Check
  ↓
Candidate Hypothesis
  ↓
Backtest
  ↓
Walk Forward
  ↓
Paper Trading
  ↓
Human Approval
  ↓
Production Strategy
```

LLM reflection is not considered statistical proof.

A lesson must not become a production rule merely because a small number of trades appear to support it.

---

# 20. Strategy Lifecycle

```text
IDEA
 ↓
RESEARCH
 ↓
CANDIDATE
 ↓
BACKTEST
 ↓
VALIDATED
 ↓
PAPER
 ↓
APPROVED
 ↓
PRODUCTION
 ↓
DEPRECATED
```

Production strategy versions must be immutable.

Example:

```text
breakout_v2.1
breakout_v2.2
```

Do not mutate `breakout_v2.1` in place.

---

# 21. Strategy Version Metadata

Every production trade should record:

```text
strategy_id
strategy_version
risk_policy_version
model_version
```

This enables retrospective analysis of exactly which configuration produced a trade.

---

# 22. Market Regime Engine

ADX must not be interpreted as market direction.

ADX measures trend strength, not bullish/bearish direction.

Regime classification should consider multiple features such as:

```text
Trend Direction
Trend Strength
Volatility
Liquidity
Momentum
Market Structure
```

The resulting regime may be:

```text
BULL
BEAR
SIDEWAYS
HIGH_VOLATILITY
LOW_VOLATILITY
```

The exact regime algorithm must be explicitly specified and independently tested.

---

# 23. Transaction Cost Model

Backtesting must use net economics rather than gross PnL.

Minimum cost components:

```text
fees
spread
slippage
funding
latency
partial fills
```

Primary performance metric:

```text
Net PnL
```

not merely:

```text
Gross PnL
```

For strategies with small profit targets, transaction costs can materially alter expectancy.

---

# 24. Backtesting Framework

```text
Historical Data
      ↓
Data Validation
      ↓
Feature Generation
      ↓
Backtest Engine
      ↓
Transaction Cost Model
      ↓
Performance Analysis
```

Required tests:

```text
Walk Forward
Parameter Sensitivity
Monte Carlo
Transaction Cost Stress
Slippage Stress
Regime Breakdown
Out-of-Sample Testing
```

A strategy should not be considered robust merely because one parameter configuration is profitable.

---

# 25. Data Split

The previous temporal split remains a baseline:

```text
TRAIN
2016–2022

VALIDATION
2023–2024

REAL / PAPER TEST
2025–Present
```

The exact dates must be adapted to the availability and quality of the actual dataset.

The important rule is chronological separation and prevention of future information leakage.

---

# 26. Data Leakage Protection

Every knowledge/data object that can influence a decision should support temporal provenance.

Minimum timestamps:

```text
created_at
available_at
effective_at
```

For a decision at time `T`, retrieval must not include information where:

```text
available_at > T
```

This rule applies to:

- Market data.
- Research.
- Macro events.
- Strategy statistics.
- Lessons.
- Regime labels.
- RAG documents.

---

# 27. MCP Architecture V2

MCP is treated as an interface layer, not as the architecture itself.

Recommended domain interfaces:

```text
Hermes
 │
 ├── Market Tools
 ├── Research Tools
 ├── Portfolio Tools
 └── Knowledge Tools
```

The critical financial path remains:

```text
TradeProposal
      ↓
Risk Engine
      ↓
Execution Service
      ↓
Exchange
```

MCP must not become a prerequisite for deterministic safety.

---

# 28. Multi-Agent Architecture

Multi-agent orchestration is **not part of the V2 critical path**.

Initial implementation:

```text
ONE HERMES AGENT
```

Possible future architecture:

```text
Hermes
 ├── Research Agent
 ├── Market Agent
 └── Analyst Agent
```

This should only be introduced if empirical benchmarks demonstrate that multi-agent architecture improves the system sufficiently to justify its additional complexity.

---

# 29. Telegram Operations Interface

Telegram provides operational supervision.

Minimum commands:

```text
/status
/positions
/orders
/pnl
/risk
/freeze
/resume
/kill
```

## Soft Kill

```text
STOP_NEW_ORDERS
```

Existing positions continue under deterministic management.

## Hard Kill

```text
CANCEL_OPEN_ORDERS
+
STOP_NEW_ORDERS
+
AGENT → OBSERVE
```

Automatic position liquidation must be a separately configured policy.

Telegram must not be the only kill mechanism.

---

# 30. Kill Switch Architecture

```text
             ┌──────────────┐
             │ Telegram     │
             └──────┬───────┘
                    │
             ┌──────▼───────┐
             │ Kill Switch  │
             │ Controller   │
             └──────┬───────┘
                    │
       ┌────────────┼────────────┐
       ▼            ▼            ▼
   Risk Engine  Execution     Hermes
       │            │            │
       ▼            ▼            ▼
     FREEZE    NO NEW ORDER   OBSERVE
```

The system should also support a local/manual emergency mechanism.

---

# 31. Failure Handling

## Exchange disconnected

```text
FREEZE
```

## Stale market data

```text
FREEZE
```

## Balance mismatch

```text
FREEZE
+
RECONCILE
```

## Position mismatch

```text
FREEZE
+
RECONCILE
```

## Unknown order

```text
FREEZE
+
QUERY EXCHANGE
+
RECONCILE
```

## Obsidian unavailable

```text
TRADING CONTINUES
KNOWLEDGE QUEUED
```

## LLM unavailable

```text
NO NEW AI PROPOSALS
EXISTING POSITIONS
CONTINUE UNDER
DETERMINISTIC MANAGEMENT
```

---

# 32. Repository Structure

```text
trading-system/
│
├── apps/
│   └── hermes/
│
├── core/
│   ├── domain/
│   │   ├── trade_proposal.py
│   │   ├── order.py
│   │   ├── position.py
│   │   └── portfolio.py
│   │
│   ├── risk/
│   │   ├── engine.py
│   │   ├── policy.py
│   │   └── validators.py
│   │
│   ├── execution/
│   │   ├── service.py
│   │   ├── state_machine.py
│   │   ├── reconciliation.py
│   │   └── idempotency.py
│   │
│   ├── portfolio/
│   │
│   └── strategy/
│
├── adapters/
│   └── exchange/
│       └── binance/
│
├── data/
│   ├── ingestion/
│   ├── parquet/
│   └── duckdb/
│
├── backtesting/
│   ├── engine/
│   ├── costs/
│   ├── walk_forward/
│   └── monte_carlo/
│
├── knowledge/
│   ├── obsidian/
│   └── learning/
│
├── tools/
│   ├── market/
│   ├── research/
│   ├── portfolio/
│   └── knowledge/
│
├── operations/
│   ├── kill_switch.py
│   ├── health.py
│   └── telegram.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── execution/
│   ├── risk/
│   └── backtest/
│
└── configs/
    ├── risk.yaml
    ├── strategies/
    └── environments/
```

---

# 33. Deployment Model

V2 is local-first.

Initial deployment does not require:

```text
Kubernetes
Kafka
Redis Cluster
PostgreSQL Cluster
Spark
Service Mesh
```

Initial environment:

```text
Linux
│
├── Trading Runtime
├── Hermes
├── SQLite
├── DuckDB
├── Parquet
└── Obsidian Vault
```

Docker may be used for reproducibility and isolation, but individual modules do not need to become separate containers unless there is a demonstrated operational reason.

---

# 34. Trading Modes

Required progression:

```text
DEVELOPMENT
     ↓
BACKTEST
     ↓
SHADOW
     ↓
PAPER
     ↓
TESTNET
     ↓
LIMITED LIVE
     ↓
LIVE
```

No AI agent may autonomously transition the system into LIVE mode.

---

# 35. Production Readiness Requirements

The system is not considered LIVE-ready merely because the AI can generate trades or because a backtest is profitable.

## Trading Correctness

```text
[ ] PnL calculation
[ ] Fees
[ ] Slippage
[ ] Funding
[ ] Position accounting
[ ] Balance reconciliation
[ ] Realized/unrealized PnL
[ ] Long/short accounting
```

## Execution

```text
[ ] Idempotency
[ ] Partial fills
[ ] Timeout handling
[ ] Order rejection handling
[ ] Reconciliation
[ ] UNKNOWN state
[ ] Duplicate order protection
```

## Risk

```text
[ ] Position limits
[ ] Portfolio exposure
[ ] Daily loss
[ ] Weekly loss
[ ] Drawdown
[ ] Correlation exposure
[ ] Liquidity
[ ] Spread
[ ] Slippage
[ ] Stale data
[ ] Price anomaly
[ ] Kill switch
```

## Research

```text
[ ] No look-ahead bias
[ ] No data leakage
[ ] Realistic transaction costs
[ ] Walk-forward analysis
[ ] Parameter sensitivity
[ ] Monte Carlo
[ ] Regime analysis
```

## AI

```text
[ ] Structured output
[ ] Schema validation
[ ] No direct exchange authority
[ ] Prompt injection isolation
[ ] Deterministic risk boundary
[ ] Decision logging
[ ] Strategy modification restrictions
```

## Operations

```text
[ ] Monitoring
[ ] Alerting
[ ] Recovery
[ ] Backup
[ ] Audit logs
[ ] Manual emergency controls
```

---

# 36. Architecture V2 Design Decisions

The following decisions are intentional.

| Previous Design | Architecture V2 |
|---|---|
| Many MCP servers | Domain-oriented tool interfaces |
| Multi-agent orchestration | Single Hermes agent initially |
| Arrow/zero-copy IPC | Postponed |
| Autonomous strategy modification | Prohibited |
| Obsidian in operational flow | Asynchronous knowledge layer |
| LLM confidence affects decisions | Metadata only |
| Simple risk limits | Expanded deterministic risk policy |
| Gross PnL focus | Net PnL |
| Basic backtesting | Cost-aware + WFO + stress testing |
| Filename-based trade identity | Unique `trade_id` |
| Methodology mutable | Immutable strategy versions |
| ADX as regime direction | Multi-feature regime classification |

---

# 37. Design Philosophy

The system should optimize for:

```text
Correctness
    >
Safety
    >
Auditability
    >
Testability
    >
Maintainability
    >
Performance Optimization
    >
Architectural Sophistication
```

Complexity must be justified by a measured requirement.

Do not introduce a component simply because it is technically possible.

---

# 38. Final Architecture

```text
                         ┌─────────────────┐
                         │     HERMES      │
                         │    LLM Brain    │
                         └────────┬────────┘
                                  │
                            TradeProposal
                                  │
                                  ▼
                     ┌────────────────────────┐
                     │   DETERMINISTIC RISK   │
                     │         ENGINE         │
                     └───────────┬────────────┘
                                 │
                     APPROVE / REJECT / FREEZE
                                 │
                                 ▼
                     ┌────────────────────────┐
                     │   EXECUTION SERVICE    │
                     │                        │
                     │ State Machine          │
                     │ Idempotency            │
                     │ Reconciliation         │
                     └───────────┬────────────┘
                                 │
                                 ▼
                         ┌─────────────┐
                         │   EXCHANGE  │
                         └──────┬──────┘
                                │
             ┌──────────────────┴──────────────────┐
             │                                     │
             ▼                                     ▼
        ┌──────────┐                        ┌─────────────┐
        │  SQLite  │                        │ Market Data │
        │  Truth   │                        └──────┬──────┘
        └────┬─────┘                               │
             │                                     ▼
             │                              Parquet/DuckDB
             │                                     │
             │                                     ▼
             │                              Backtesting /
             │                               Analytics
             │
             ▼
       Post-Trade Worker
             │
             ▼
       LLM Reflection
             │
             ▼
         Obsidian
             │
             ▼
       Candidate Lessons
             │
             ▼
        Hypothesis
             │
             ▼
      Backtest/WFO/Paper
             │
             ▼
       Human Approval
             │
             ▼
      Strategy Production
```

---

# 39. Final Principles

1. **LLM generates proposals; deterministic software authorizes trades.**
2. **No direct LLM-to-exchange execution.**
3. **Unknown state always leads to a safe state.**
4. **Exchange reconciliation is mandatory.**
5. **Every order must be idempotent.**
6. **SQLite is the operational source of truth.**
7. **DuckDB/Parquet handle analytical workloads.**
8. **Obsidian is knowledge memory, not trading state.**
9. **LLM confidence is not a risk metric.**
10. **AI-generated lessons are hypotheses, not facts.**
11. **Production strategies are immutable and versioned.**
12. **Strategy changes require statistical validation.**
13. **Backtests must include realistic trading costs.**
14. **Future information must never enter historical decisions.**
15. **Complexity must be justified by measured need.**
16. **Human approval remains required for strategy promotion and LIVE activation.**

---

## Architecture V2 Status

**This document supersedes the previous conceptual architecture as the baseline design.**

The next engineering artifact should be a detailed implementation specification derived from this architecture, including:

- Exact Pydantic contracts.
- Exact SQLite schema and migrations.
- Exact event schema.
- Exact state transition rules.
- Exact `RiskPolicy` schema.
- Exchange adapter interface.
- Idempotency contract.
- Reconciliation algorithm.
- Backtesting API.
- Strategy configuration format.
- Knowledge/RAG interface.
- Error codes.
- Logging/audit requirements.
- Test cases.
- Environment configuration.
- Phase-by-phase implementation plan.

Architecture V2 should be implemented incrementally. Components classified as postponed must not be introduced into the critical path without an explicit performance or operational justification.

---

# 40. Obsidian Reader & Knowledge Workspace

Architecture V2.1 adds a dedicated **Obsidian Reader** inside the Trader Web Application. The goal is to let the trader read, search, navigate, and understand the Obsidian knowledge base without opening the native Obsidian application.

Obsidian remains a knowledge layer, not the operational source of truth.

## 40.1 Knowledge Dashboard

The Knowledge Center should show:

- total notes
- recent notes
- recent trading journals
- important lessons
- active methodologies
- candidate hypotheses
- recently completed experiments
- searchable knowledge

Example navigation:

```text
Knowledge Center
├── Notes
├── Trading Journal
├── Methodology
├── Lessons Learned
├── Research
├── Market Regimes
├── Timeline
└── Knowledge Graph
```

## 40.2 Note Reader

Every Obsidian note should be rendered in a clean reading interface supporting:

- Markdown rendering
- headings
- tables
- lists
- code blocks
- frontmatter metadata
- tags
- internal note links
- related trades
- related notes
- search within note
- open-in-Obsidian action

Example:

```text
← Knowledge / Lessons Learned

Breakout Performance During High Volatility

Updated: 2026-08-28
Tags: #breakout #volatility #risk

## Observation
...

## Evidence
42 similar trades
Win Rate: 54.8%
Average Net Return: +0.18%

## Interpretation
...

## Related Trades
TRD-000123
TRD-000119

## Related Notes
→ Breakout Strategy v2.1
→ Volatility Regime

[Open in Obsidian]
```

## 40.3 Specialized Trading Journal View

Trade notes should have a structured view showing:

- trade ID
- symbol and direction
- strategy and version
- entry/exit
- gross PnL
- fees
- slippage
- funding
- net PnL
- risk decision
- AI rationale
- AI reflection
- lessons
- similar historical trades

The user should be able to navigate:

```text
Trade
 ↓
Strategy
 ↓
Similar Trades
 ↓
Lessons
 ↓
Experiments
```

## 40.4 Methodology Reader

Strategy notes should be presented as structured strategy pages containing:

- status
- strategy rules
- parameters
- risk rules
- performance
- regime performance
- drawdown
- trade history
- version history

The raw Markdown remains accessible, but the website should make the methodology understandable without requiring the trader to inspect Markdown syntax.

## 40.5 Lessons Explorer

Lessons should be separated by status:

```text
OBSERVATION
HYPOTHESIS
CANDIDATE
VALIDATED
REJECTED
PRODUCTION RULE
```

The interface should expose evidence behind important lessons.

Example:

```text
Breakout + High Volume
Status: VALIDATED
Evidence: 87 trades

[View Evidence]
```

This prevents an AI-generated observation from being mistaken for a statistically validated trading rule.

## 40.6 Knowledge Search

The Knowledge Center should support:

- full-text search
- semantic search where available
- tag filtering
- symbol filtering
- strategy filtering
- market-regime filtering
- date filtering
- category filtering

Example query:

```text
"breakout failures during high volatility"
```

Results may include:

```text
Lessons Learned
Trading Journal
Methodology
Research
```

## 40.7 Knowledge Graph

The website should provide an optional graph view showing relationships among:

```text
Strategy
  ↕
Trades
  ↕
Lessons
  ↕
Experiments
  ↕
Strategy Versions
```

This allows the trader to understand how methodology evolved from historical evidence.

## 40.8 Timeline

A timeline should show knowledge evolution chronologically:

```text
AUG 2026

Aug 28  ● Trade journal updated
Aug 26  ● Experiment completed
Aug 24  ● Strategy v2.1 created
Aug 20  ● Lesson validated
```

## 40.9 AI Context Panel

While reading a note, the trader may request an AI explanation such as:

> What does this mean for my current strategy?

The response must separate:

```text
FACTS
AI INTERPRETATION
EVIDENCE
```

The AI explanation must never silently become a trading authorization.

## 40.10 Knowledge Provenance

Where possible, every important insight should show:

- source notes
- source trade IDs
- number of observations
- validation date
- strategy version
- experiment ID

Example:

```text
Derived from:
14 trade records
3 methodology notes
1 experiment

Last validated:
2026-08-20
```

## 40.11 Obsidian Synchronization

Recommended flow:

```text
Obsidian Vault
      ↓
File Watcher / Sync Worker
      ↓
Markdown Parser
      ↓
Knowledge Index
      ↓
Knowledge API
      ↓
Trader Web Application
```

The initial implementation should prioritize reliable reading and indexing. Bidirectional editing may be added later after synchronization is stable.

## 40.12 Knowledge Failure Handling

If Obsidian or the indexing worker becomes unavailable:

```text
Trading → CONTINUES
Knowledge → QUEUED
Last indexed notes → READ-ONLY
```

The knowledge layer must never block deterministic risk or exchange execution.

---

# 41. Updated Web Information Architecture

The complete trader-facing application should contain:

```text
TRADER CONTROL CENTER
│
├── Dashboard
├── Trading
│   ├── Live Market
│   ├── Positions
│   ├── Orders
│   └── Execution
├── Portfolio
├── Risk Center
├── AI Decision Center
├── Market Intelligence
├── Strategies
├── Backtesting
├── Experiments
├── Knowledge
│   ├── Knowledge Dashboard
│   ├── Notes
│   ├── Trading Journal
│   ├── Methodology
│   ├── Lessons Learned
│   ├── Research
│   ├── Market Regimes
│   ├── Timeline
│   └── Knowledge Graph
├── AI Learning
├── Audit Log
├── System Health
├── Notifications
└── System Control
```

The website is now the single primary human interface. Telegram is removed from Architecture V2.1.
