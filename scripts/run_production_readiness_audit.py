#!/usr/bin/env python3
"""Script to execute Phase 16 Production Readiness Review audit and produce PRODUCTION_READINESS_REPORT.md."""

from __future__ import annotations

import sys
from pathlib import Path

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.audit.production_readiness import ProductionReadinessAuditEngine


def main() -> None:
    print("Initializing Phase 16 Production Readiness Review Audit Engine...")
    engine = ProductionReadinessAuditEngine()

    print("Auditing system against architecture.md & implementation_spec.md across 5 core dimensions...")
    telemetry = engine.run_full_audit()

    print("\nPhase 16 Production Readiness Audit Complete!")
    print(f"- Verified Mode: {telemetry.trading_mode_verified}")
    print(f"- Trading Correctness: {'PASSED' if telemetry.trading_correctness_pass else 'FAILED'}")
    print(f"- Execution Determinism: {'PASSED' if telemetry.execution_pass else 'FAILED'}")
    print(f"- Risk Engine Authority: {'PASSED' if telemetry.risk_pass else 'FAILED'}")
    print(f"- AI / Hermes Boundary: {'PASSED' if telemetry.ai_boundary_pass else 'FAILED'}")
    print(f"- Operational Resilience: {'PASSED' if telemetry.operations_pass else 'FAILED'}")
    print(f"\nAudit Findings Summary:")
    print(f"  CRITICAL Issues: {telemetry.critical_count} (Mandate: ZERO)")
    print(f"  HIGH Issues:     {telemetry.high_count} (Mandate: ZERO)")
    print(f"  MEDIUM Issues:   {telemetry.medium_count}")
    print(f"  LOW Issues:      {telemetry.low_count}")

    if telemetry.critical_count == 0 and telemetry.high_count == 0:
        print("\nSUCCESS: Production readiness gate PASSED with ZERO CRITICAL and ZERO HIGH issues.")
    else:
        print("\nFAILURE: Production readiness gate FAILED due to unmitigated CRITICAL or HIGH issues.")

    report_md = engine.generate_report_markdown()

    out_file = Path("PRODUCTION_READINESS_REPORT.md")
    out_file.write_text(report_md, encoding="utf-8")
    print(f"\nReport successfully written to {out_file.absolute()}")


if __name__ == "__main__":
    main()
