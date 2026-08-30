#!/usr/bin/env python3
"""Script to execute Phase 17 Limited Live Preparation and produce LIMITED_LIVE_RUNBOOK.md."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.prep.limited_live import LimitedLivePrepEngine


def main() -> None:
    print("Initializing Phase 17 Limited Live Preparation Engine...")
    engine = LimitedLivePrepEngine(config_path="configs/environments/production.yaml")

    print("Verifying 13 operational checklist items and 5 AI hard prohibitions...")
    telemetry = engine.run_preparation_and_verification()

    print("\nPhase 17 Limited Live Preparation Complete!")
    print(f"- Target Mode: {telemetry.trading_mode_prepared}")
    print(f"- Production Config: {'VERIFIED' if telemetry.production_config_verified else 'FAILED'}")
    print(f"- Secret Management: {'VERIFIED' if telemetry.secret_management_verified else 'FAILED'}")
    print(f"- Capital & Position Limits: {'VERIFIED' if telemetry.capital_limits_verified and telemetry.position_limits_verified else 'FAILED'}")
    print(f"- Kill Switch & Emergency Controls: {'VERIFIED' if telemetry.kill_switch_verified and telemetry.manual_emergency_controls_verified else 'FAILED'}")
    print(f"- Audit Logging & Backup: {'VERIFIED' if telemetry.audit_logging_verified and telemetry.backup_verified else 'FAILED'}")
    print(f"- Reconciliation & Recovery: {'VERIFIED' if telemetry.reconciliation_verified and telemetry.recovery_verified else 'FAILED'}")

    print("\n5 AI Hard Prohibitions Status:")
    print(f"  1. Cannot Increase Capital Allocation:     {'ENFORCED' if telemetry.ai_cannot_increase_capital else 'FAILED'}")
    print(f"  2. Cannot Increase Risk Limits:             {'ENFORCED' if telemetry.ai_cannot_increase_risk_limits else 'FAILED'}")
    print(f"  3. Cannot Disable Kill Switch:             {'ENFORCED' if telemetry.ai_cannot_disable_kill_switch else 'FAILED'}")
    print(f"  4. Cannot Activate LIVE Trading:            {'ENFORCED' if telemetry.ai_cannot_activate_live else 'FAILED'}")
    print(f"  5. Cannot Modify Production Strategy:       {'ENFORCED' if telemetry.ai_cannot_modify_production_strategy else 'FAILED'}")

    print(f"\nHuman Authorization Sign-Off Granted: {telemetry.human_authorization_granted} (REQUIRED BEFORE LAUNCH)")

    runbook_md = engine.generate_runbook_markdown()

    out_file = Path("LIMITED_LIVE_RUNBOOK.md")
    out_file.write_text(runbook_md, encoding="utf-8")
    print(f"\nRunbook successfully written to {out_file.absolute()}")


if __name__ == "__main__":
    main()
