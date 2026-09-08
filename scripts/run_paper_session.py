#!/usr/bin/env python3
"""Script to execute Phase 14 Paper Trading Session and generate PAPER_TRADING_REPORT.md."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.paper.runner import PaperTradingEngine


def main() -> None:
    print("Initializing Phase 14 Paper Trading Engine...")
    engine = PaperTradingEngine(
        db_path="data/trading_paper.db",
        vault_path="knowledge/vault",
        simulated_latency_ms=200.0,
    )

    print("Executing 60-cycle PAPER mode simulation across multi-regime time series...")
    telemetry = engine.run_paper_session(num_cycles=60, random_seed=42)

    print("Session finished successfully!")
    print(f"- Total Signals Ingested: {telemetry.total_signals_ingested}")
    print(f"- Proposals Generated: {telemetry.total_proposals_generated}")
    print(f"- Proposals Approved: {telemetry.proposals_approved}")
    print(f"- Proposals Rejected: {telemetry.proposals_rejected}")
    print(f"- Total Orders Submitted: {telemetry.total_orders_submitted}")
    print(f"- Total Orders Filled: {telemetry.total_orders_filled}")
    print(f"- Gross PnL: ${telemetry.gross_pnl:+,.2f} USD")
    print(f"- Fees Paid: ${telemetry.fees_paid:,.2f} USD")
    print(f"- Slippage Cost: ${telemetry.slippage_cost:,.2f} USD")
    print(f"- Net PnL: ${telemetry.net_pnl:+,.2f} USD")
    print(f"- Max Drawdown: {telemetry.max_drawdown_pct:.2f}%")
    print(f"- Avg Latency: {telemetry.avg_latency_ms():.2f} ms")
    print(
        f"- Reconciliations: {telemetry.reconciliations_count} ({telemetry.reconciliation_clean_count} clean)"
    )

    report_md = engine.generate_report_markdown()

    out_file = Path("PAPER_TRADING_REPORT.md")
    out_file.write_text(report_md, encoding="utf-8")
    print(f"Report written to {out_file.absolute()}")


if __name__ == "__main__":
    main()
