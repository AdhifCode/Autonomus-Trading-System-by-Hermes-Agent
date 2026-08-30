# AI Engineering Rules

> Derived from `architecture.md` V2/V2.1. This document is normative.
> Any contradiction with `architecture.md` must be resolved in favour of `architecture.md`.

---

## 1. Fundamental Principle

**Probabilistic intelligence, deterministic authority.**

The AI layer (Hermes) generates proposals. Deterministic software authorizes trades.

---

## 2. Hermes Boundary

### 2.1 Hermes MAY

- Read market state via exposed tool interfaces.
- Read portfolio state via exposed tool interfaces.
- Retrieve research, historical knowledge, strategy information.
- Create structured `TradeProposal` objects.
- Perform post-trade reflection.
- Propose candidate strategy improvements (for human review).

### 2.2 Hermes MUST NOT

- Directly call exchange SDK order functions.
- Directly submit exchange orders.
- Bypass the Risk Engine.
- Override Risk Engine decisions.
- Modify `RiskPolicy`.
- Disable the kill switch.
- Activate LIVE trading.
- Increase trading limits.
- Modify production strategies automatically.
- Access exchange credentials directly.

### 2.3 Hermes Is NOT Implemented Here

This repository is the trading system that Hermes consumes.
No `apps/hermes/` application shall be created.
No Hermes runtime, agent loop, or LLM orchestration code shall exist in this repository.
The `integration/hermes/` module defines **only** the integration boundary:
- `gateway.py` — request routing and response formatting
- `security.py` — permission enforcement
- `tools/` — tool contracts that Hermes calls (market, research, portfolio, knowledge, trading)
- `contracts/` — JSON Schema definitions for tool inputs/outputs

Hermes already runs on the Ubuntu host. This repository exposes interfaces for it.

---

## 3. Financial Execution Path

The **only** valid execution path is:

```
Hermes → TradeProposal → Validation → Risk Engine → Authorization → Execution Service → Exchange Adapter → Exchange
```

No shortcut is permitted. Every link in this chain is mandatory.

---

## 4. Risk Engine Rules

- The Risk Engine is the deterministic financial safety boundary.
- Identical inputs MUST produce identical risk decisions.
- The LLM MUST NOT override a rejection.
- `llm_confidence` is metadata only — it MUST NOT determine position sizing or override risk rules.
- Risk checks must be independently testable without Hermes.
- RiskPolicy is file-based (`configs/risk.yaml`) and immutable at runtime.
- `kill_switch` and `trading_mode` are system state (read from `SystemState`), NOT part of `RiskPolicy`.
- The Risk Engine receives four inputs: `TradeProposal`, `MarketState`, `PortfolioState`, `RiskPolicy`, and `SystemState` (architecture §6).

---

## 4a. Execution State Machine Rules

- `RISK_REJECTED` and `EXCHANGE_REJECTED` are distinct states (never use ambiguous `REJECTED`).
- Every state transition must be logged in `state_transitions` table.
- Emergency path: any state → `UNKNOWN` → `FREEZE` → `RECONCILING` → `RESOLVED`.
- The emergency path is the ONLY way to recover from an unknown state.

---

## 5. Fail-Safe Principle

When financial state becomes uncertain:

```
UNKNOWN → FREEZE → RECONCILE → RESOLVE
```

- Never guess financial state.
- Prefer stopping new trading over making irreversible assumptions.
- A single WebSocket event is never final authority for critical financial state.

---

## 6. Trading Modes

Required progression:

```
DEVELOPMENT → BACKTEST → SHADOW → PAPER → TESTNET → LIMITED_LIVE → LIVE
```

- No AI agent may autonomously transition to LIVE.
- LIVE activation requires explicit human approval.
- During development, NEVER use real trading capital.

---

## 7. Strategy Rules

- Production strategy versions are immutable (`breakout_v2.1`, `breakout_v2.2`).
- Never mutate a version in place.
- AI-generated lessons are hypotheses, not facts.
- Strategy changes require statistical validation + human approval.
- Every production trade must record: `strategy_id`, `strategy_version`, `risk_policy_version`, `model_version` (architecture §21).
- `model_version` tracks which LLM model produced the TradeProposal.

---

## 8. Data Integrity Rules

- SQLite is the canonical operational source of truth.
- DuckDB/Parquet handle analytical workloads.
- Obsidian is knowledge memory, not trading state.
- Exchange reconciliation is mandatory.
- Every order must be idempotent (unique client-side ID).

### 8.1 Data Leakage Protection

For a decision at time `T`, retrieval must not include information where `available_at > T`.
Applies to: market data, research, macro events, strategy statistics, lessons, regime labels, RAG documents.

---

## 9. Architectural Simplicity

### 9.1 Priority Order

```
Correctness > Safety > Auditability > Testability > Maintainability > Performance > Architectural Sophistication
```

### 9.2 Prohibited Unless Justified

- Kubernetes
- Kafka
- Redis cluster
- PostgreSQL cluster
- Spark
- Service mesh
- Multi-agent orchestration
- Apache Arrow / zero-copy IPC

The system is local-first. Complexity must be justified by measured need.

---

## 10. Testing Rules

- Testing is part of implementation, not an afterthought.
- Never mark a phase complete if tests fail.
- Never weaken tests to make implementation pass.
- Never remove safety checks because they are inconvenient.
- Critical financial components require: unit, integration, failure, recovery, and e2e tests.
- The Risk Engine must be independently testable without Hermes.
- The Execution Service must be independently testable using MockExchange.

---

## 11. Knowledge Layer Rules

- Obsidian is outside the critical execution path.
- If Obsidian becomes unavailable: trading continues, knowledge is queued.
- If LLM becomes unavailable: no new AI proposals, existing positions continue under deterministic management.

---

## 12. Development Method

For every phase:

1. Inspect repository and architecture.
2. Inspect previous phase results.
3. Create implementation plan.
4. Implement.
5. Write tests.
6. Run tests — fix failures.
7. Run type checking.
8. Run linting.
9. Architecture review.
10. Update documentation.
11. Commit.

Do not modify unrelated code. Each phase must produce passing tests, type checks, lint, and documentation.

---

## 13. Source-of-Truth Separation

| Layer | Responsibility | Authority |
|---|---|---|
| SQLite | Operational trading state | Canonical operational truth |
| DuckDB + Parquet | Analytics and historical market data | Analytical truth |
| Obsidian | Semantic knowledge and documentation | Knowledge layer |
| Exchange | External account/order state | External authoritative state |

---

## 14. Web Application (V2.1)

- The website is the single primary human interface.
- Telegram is removed from Architecture V2.1 (kill switch and operations are via web + local mechanisms).
- AI explanations in the Knowledge panel must separate: FACTS, AI INTERPRETATION, EVIDENCE.
- AI explanation must never silently become a trading authorization.
