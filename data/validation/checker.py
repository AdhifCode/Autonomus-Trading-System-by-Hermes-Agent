"""Market Data Validation Module.

Performs data quality, anomaly, gap, and integrity checks on market data:
- Monotonic timestamp ordering
- Missing/duplicate timestamp detection
- Price hierarchy integrity (High >= Open/Close/Low, Low <= Open/Close/High, Open > 0, Low > 0)
- Volume non-negativity
- Max gap / staleness detection

See implementation_spec.md §5.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from core.errors import DataValidationError
from core.logging import get_logger

logger = get_logger(__name__)


class Candle(BaseModel):
    """OHLCV market bar data point."""

    timestamp: datetime
    symbol: str
    open: float = Field(gt=0.0)
    high: float = Field(gt=0.0)
    low: float = Field(gt=0.0)
    close: float = Field(gt=0.0)
    volume: float = Field(ge=0.0)


class ValidationIssue(BaseModel):
    """Details of a data quality issue found during validation."""

    issue_type: str
    message: str
    index: int | None = None
    timestamp: datetime | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class DataValidationResult(BaseModel):
    """Summary result of market data validation."""

    is_valid: bool
    total_candles: int
    issues: list[ValidationIssue] = Field(default_factory=list)
    has_critical_error: bool = False


class DataValidator:
    """Validates market data arrays/candles for temporal integrity and pricing logic."""

    def __init__(self, max_allowed_gap_seconds: float = 300.0) -> None:
        self.max_allowed_gap_seconds = max_allowed_gap_seconds

    def validate_candles(self, candles: list[Candle]) -> DataValidationResult:
        """Run comprehensive validation on an ordered list of OHLCV candles."""
        issues: list[ValidationIssue] = []
        has_critical = False

        if not candles:
            return DataValidationResult(
                is_valid=False,
                total_candles=0,
                issues=[ValidationIssue(issue_type="EMPTY_DATA", message="Candle list is empty")],
                has_critical_error=True,
            )

        seen_timestamps: set[datetime] = set()
        prev_ts: datetime | None = None

        for i, candle in enumerate(candles):
            # 1. Duplicate timestamp check
            if candle.timestamp in seen_timestamps:
                issues.append(
                    ValidationIssue(
                        issue_type="DUPLICATE_TIMESTAMP",
                        message=f"Duplicate timestamp detected at index {i}",
                        index=i,
                        timestamp=candle.timestamp,
                    )
                )
                has_critical = True
            seen_timestamps.add(candle.timestamp)

            # 2. Monotonic timestamp check & gap detection
            if prev_ts is not None:
                if candle.timestamp <= prev_ts:
                    issues.append(
                        ValidationIssue(
                            issue_type="OUT_OF_ORDER_TIMESTAMP",
                            message=(
                                f"Timestamp {candle.timestamp} is not greater than "
                                f"previous {prev_ts}"
                            ),
                            index=i,
                            timestamp=candle.timestamp,
                        )
                    )
                    has_critical = True
                else:
                    gap = (candle.timestamp - prev_ts).total_seconds()
                    if gap > self.max_allowed_gap_seconds:
                        issues.append(
                            ValidationIssue(
                                issue_type="TIME_GAP",
                                message=(
                                    f"Time gap of {gap}s exceeds threshold "
                                    f"({self.max_allowed_gap_seconds}s)"
                                ),
                                index=i,
                                timestamp=candle.timestamp,
                                details={"gap_seconds": gap},
                            )
                        )

            prev_ts = candle.timestamp

            # 3. OHLC Price hierarchy integrity check
            if candle.high < candle.open or candle.high < candle.close or candle.high < candle.low:
                issues.append(
                    ValidationIssue(
                        issue_type="INVALID_HIGH_PRICE",
                        message=(
                            f"High price {candle.high} is less than Open/Close/Low at index {i}"
                        ),
                        index=i,
                        timestamp=candle.timestamp,
                    )
                )
                has_critical = True

            if candle.low > candle.open or candle.low > candle.close or candle.low > candle.high:
                issues.append(
                    ValidationIssue(
                        issue_type="INVALID_LOW_PRICE",
                        message=(
                            f"Low price {candle.low} is greater than Open/Close/High at index {i}"
                        ),
                        index=i,
                        timestamp=candle.timestamp,
                    )
                )
                has_critical = True

        is_valid = not has_critical and len(issues) == 0

        return DataValidationResult(
            is_valid=is_valid,
            total_candles=len(candles),
            issues=issues,
            has_critical_error=has_critical,
        )

    def assert_valid(self, candles: list[Candle]) -> None:
        """Raise DataValidationError if candles fail validation checks."""
        res = self.validate_candles(candles)
        if not res.is_valid:
            first_msg = res.issues[0].message if res.issues else "Validation failed"
            raise DataValidationError(f"Market data validation failed: {first_msg}")


__all__ = [
    "Candle",
    "DataValidationResult",
    "DataValidator",
    "ValidationIssue",
]
