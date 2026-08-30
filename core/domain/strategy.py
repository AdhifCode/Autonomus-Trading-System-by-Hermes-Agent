"""Strategy version domain model.

Strategies are immutable and versioned (architecture §39, principle 11).
AI-generated lessons are hypotheses, not facts (principle 10).
Strategy changes require statistical validation + human approval.

See implementation_spec.md §15.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from core.domain.enums import MarketRegime, StrategyLifecycle


class StrategyVersion(BaseModel):
    """An immutable, versioned strategy configuration.

    INVARIANT: Once created, a version must never be mutated in place.
    New versions must be created with an incremented version string.
    """

    model_config = ConfigDict(frozen=True)

    strategy_id: str = Field(min_length=1)
    version: str = Field(min_length=1)
    lifecycle: StrategyLifecycle = StrategyLifecycle.IDEA
    parameters: dict[str, object] = Field(default_factory=dict)
    risk_overrides: dict[str, float] = Field(default_factory=dict)
    applicable_regimes: list[MarketRegime] = Field(default_factory=list)
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: datetime
    created_by: str = Field(min_length=1, description="'human' or agent identifier")

    @property
    def is_production(self) -> bool:
        """Return True if this strategy is in production."""
        return self.lifecycle == StrategyLifecycle.PRODUCTION

    @property
    def is_deprecated(self) -> bool:
        """Return True if this strategy is deprecated."""
        return self.lifecycle == StrategyLifecycle.DEPRECATED

    @property
    def qualified_name(self) -> str:
        """Return 'strategy_id:version' identifier."""
        return f"{self.strategy_id}:{self.version}"
