"""Trade Journal Generator and Reader.

Converts trade domain events / models into structured Markdown trade log notes
matching the schema defined in architecture.md §18.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.logging import get_logger
from knowledge.models import NoteCategory, TradeJournalEntry
from knowledge.obsidian.vault import ObsidianVaultManager

logger = get_logger(__name__)


class TradeJournalManager:
    """Manages trade log creation and retrieval in the Obsidian vault."""

    def __init__(self, vault_manager: ObsidianVaultManager | None = None) -> None:
        self.vault = vault_manager or ObsidianVaultManager()

    def format_entry_markdown(self, entry: TradeJournalEntry) -> str:
        """Format a TradeJournalEntry into YAML frontmatter + Markdown body."""
        entry_iso = entry.timestamp_entry.isoformat()
        exit_iso = entry.timestamp_exit.isoformat() if entry.timestamp_exit else ""

        tags_yaml = "\n".join([f"  - {t}" for t in entry.tags]) if entry.tags else "  - trade_log"

        markdown = f"""---
trade_id: {entry.trade_id}
timestamp:
  entry: "{entry_iso}"
  exit: "{exit_iso}"
symbol: {entry.symbol}
direction: {entry.direction}
strategy_id: {entry.strategy_id}
strategy_version: "{entry.strategy_version}"
entry_price: {entry.entry_price}
exit_price: {entry.exit_price or 0.0}
quantity: {entry.quantity}
gross_pnl: {entry.gross_pnl}
fees: {entry.fees}
slippage_cost: {entry.slippage_cost}
funding_cost: {entry.funding_cost}
net_pnl: {entry.net_pnl}
net_return: {entry.net_return}
market_regime: {entry.market_regime}
llm_confidence: {entry.llm_confidence}
risk_decision: {entry.risk_decision}
risk_policy_version: "{entry.risk_policy_version}"
created_at: "{datetime.now(UTC).isoformat()}"
available_at: "{entry_iso}"
source_trade_id: {entry.trade_id}
category: "Trading Logs"
tags:
{tags_yaml}
---

# Trade Log: {entry.trade_id} ({entry.symbol} {entry.direction})

## Trade Summary
- **Symbol**: {entry.symbol}
- **Direction**: {entry.direction}
- **Strategy**: `{entry.strategy_id}` (v{entry.strategy_version})
- **Entry Price**: ${entry.entry_price:,.2f}
- **Exit Price**: ${entry.exit_price or 0:,.2f}
- **Net PnL**: ${entry.net_pnl:,.2f} ({entry.net_return * 100:.2f}%)
- **Market Regime**: `{entry.market_regime}`

## Execution Metrics
- Gross PnL: ${entry.gross_pnl:,.2f}
- Fees: ${entry.fees:,.2f}
- Slippage: ${entry.slippage_cost:,.2f}
- Funding Cost: ${entry.funding_cost:,.2f}

## Risk & Agent Metadata
- Risk Decision: `{entry.risk_decision}` (Policy v{entry.risk_policy_version})
- LLM Signal Confidence: {entry.llm_confidence * 100:.1f}%

## Reflection Notes
{entry.notes or "_No manual reflection notes recorded._"}
"""
        return markdown

    def create_journal_note(self, entry: TradeJournalEntry) -> bool:
        """Create a trade log note in the Obsidian vault under Trading Logs/."""
        date_str = entry.timestamp_entry.strftime("%Y-%m-%d")
        filename = f"{date_str}_{entry.trade_id}_{entry.symbol}_{entry.direction}.md"
        content = self.format_entry_markdown(entry)

        return self.vault.write_note(NoteCategory.TRADING_LOGS, filename, content)
