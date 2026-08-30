"""Risk policy model and loader.

RiskPolicy is loaded from configuration (e.g. configs/risk.yaml) and is immutable at runtime.
kill_switch and trading_mode are read from SystemState, not stored in RiskPolicy.

See architecture.md §7, implementation_spec.md §3.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from core.domain.risk import RiskPolicy
from core.errors import ConfigError


def load_risk_policy(config_path: str | Path = "configs/risk.yaml") -> RiskPolicy:
    """Load RiskPolicy from YAML configuration file.

    Args:
        config_path: Path to risk.yaml file.

    Returns:
        Validated RiskPolicy model.

    Raises:
        ConfigError: If file not found or YAML invalid.
    """
    path = Path(config_path)
    if not path.exists():
        raise ConfigError(f"Risk policy config file not found: {path}")

    try:
        content = path.read_text(encoding="utf-8")
        data: dict[str, Any] = yaml.safe_load(content)
        if not isinstance(data, dict):
            raise ConfigError(f"Invalid risk policy YAML structure in {path}")
        return RiskPolicy(**data)
    except Exception as e:
        if isinstance(e, ConfigError):
            raise
        raise ConfigError(f"Failed to load risk policy from {path}: {e}") from e


__all__ = ["RiskPolicy", "load_risk_policy"]
