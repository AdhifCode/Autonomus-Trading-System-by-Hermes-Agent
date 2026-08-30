"""System state domain model.

See implementation_spec.md §2.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from core.domain.enums import KillSwitchState, TradingMode


class SystemState(BaseModel):
    """Current system operational state.

    The Risk Engine reads kill_switch and trading_mode from here,
    NOT from RiskPolicy (architecture §6, AI_ENGINEERING_RULES §4a).
    """

    trading_mode: TradingMode
    kill_switch: KillSwitchState
    exchange_connected: bool
    data_healthy: bool
    last_heartbeat: datetime
    active_errors: list[str] = Field(default_factory=list)

    @property
    def is_healthy(self) -> bool:
        """Return True if the system is in a healthy operational state."""
        return (
            self.exchange_connected
            and self.data_healthy
            and self.kill_switch == KillSwitchState.ACTIVE
            and len(self.active_errors) == 0
        )

    @property
    def can_trade(self) -> bool:
        """Return True if the system can accept new proposals."""
        return self.is_healthy and self.trading_mode not in (
            TradingMode.DEVELOPMENT,
            TradingMode.BACKTEST,
        )
