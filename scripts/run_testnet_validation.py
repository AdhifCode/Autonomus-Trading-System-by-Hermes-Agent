#!/usr/bin/env python3
"""Script to execute Phase 15 Testnet Validation suite and generate TESTNET_VALIDATION_REPORT.md."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.testnet.runner import BinanceTestnetValidationEngine


def main() -> None:
    print("Initializing Phase 15 Binance Testnet Validation Engine...")
    engine = BinanceTestnetValidationEngine(
        db_path="data/trading_testnet.db",
        api_key="testnet_api_key_sample_12345",
        api_secret="testnet_api_secret_sample_67890",
    )

    print("Executing 15 Testnet Validation Modules & Controlled Failure Scenarios...")
    telemetry = engine.run_validation_suite()

    print("\nPhase 15 Testnet Validation Completed Successfully!")
    print(f"- Mode: {telemetry.trading_mode}")
    print(f"- Live Protection Activated: {telemetry.live_protection_activated}")
    print(f"- Auth Verified: {telemetry.auth_verified}")
    print(f"- Market Data Verified: {telemetry.market_data_verified}")
    print(f"- Order Submission Verified: {telemetry.order_submission_verified}")
    print(f"- Cancellation Verified: {telemetry.cancellation_verified}")
    print(f"- Fills & Partial Fills Verified: {telemetry.fills_verified}")
    print(f"- Balances & Positions Verified: {telemetry.balances_verified}")
    print(
        f"- WebSocket & Reconnect Verified: {telemetry.websocket_verified} / {telemetry.reconnect_verified}"
    )
    print(f"- REST Rate Limit Weight Used: {telemetry.rate_limit_weight_used}")
    print(f"- Controlled Failures Passed: {len(telemetry.controlled_failures_passed)}")

    report_md = engine.generate_report_markdown()

    out_file = Path("TESTNET_VALIDATION_REPORT.md")
    out_file.write_text(report_md, encoding="utf-8")
    print(f"\nReport successfully written to {out_file.absolute()}")


if __name__ == "__main__":
    main()
