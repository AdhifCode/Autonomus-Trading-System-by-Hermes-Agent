"""Strategy Lifecycle & Immutability Engine Module.

Enforces the canonical strategy lifecycle state machine:
IDEA -> RESEARCH -> CANDIDATE -> BACKTEST -> VALIDATED -> PAPER ->
APPROVED -> PRODUCTION -> DEPRECATED

Key Rules:
1. State transitions must follow valid forward/backward lifecycle pathways.
2. From PRODUCTION, a version can ONLY transition to DEPRECATED.
3. PRODUCTION versions are strictly immutable. Mutation attempts trigger StrategyImmutabilityError.
4. Parameter modifications require creating a NEW version (e.g., v1.0.0 -> v1.0.1).

See architecture.md §18 and implementation_spec.md §15.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from adapters.repositories.sqlite_repos import StateTransitionRepository, StrategyVersionRepository
from core.domain.enums import MarketRegime, StrategyLifecycle
from core.domain.strategy import StrategyVersion
from core.errors import StrategyImmutabilityError, StrategyLifecycleError
from core.logging import get_logger
from core.strategy.versioning import SemanticVersion

logger = get_logger(__name__)

# Canonical map of allowed target states from each source state
_ALLOWED_TRANSITIONS: dict[StrategyLifecycle, set[StrategyLifecycle]] = {
    StrategyLifecycle.IDEA: {StrategyLifecycle.RESEARCH, StrategyLifecycle.DEPRECATED},
    StrategyLifecycle.RESEARCH: {
        StrategyLifecycle.CANDIDATE,
        StrategyLifecycle.IDEA,
        StrategyLifecycle.DEPRECATED,
    },
    StrategyLifecycle.CANDIDATE: {
        StrategyLifecycle.BACKTEST,
        StrategyLifecycle.RESEARCH,
        StrategyLifecycle.DEPRECATED,
    },
    StrategyLifecycle.BACKTEST: {
        StrategyLifecycle.VALIDATED,
        StrategyLifecycle.CANDIDATE,
        StrategyLifecycle.RESEARCH,
        StrategyLifecycle.DEPRECATED,
    },
    StrategyLifecycle.VALIDATED: {
        StrategyLifecycle.PAPER,
        StrategyLifecycle.BACKTEST,
        StrategyLifecycle.DEPRECATED,
    },
    StrategyLifecycle.PAPER: {
        StrategyLifecycle.APPROVED,
        StrategyLifecycle.VALIDATED,
        StrategyLifecycle.DEPRECATED,
    },
    StrategyLifecycle.APPROVED: {
        StrategyLifecycle.PRODUCTION,
        StrategyLifecycle.PAPER,
        StrategyLifecycle.DEPRECATED,
    },
    StrategyLifecycle.PRODUCTION: {StrategyLifecycle.DEPRECATED},
    StrategyLifecycle.DEPRECATED: set(),  # Terminal state
}


class StrategyLifecycleManager:
    """Manages strategy lifecycle transitions, immutability, and version progression."""

    def __init__(
        self,
        repo: StrategyVersionRepository | None = None,
        transition_repo: StateTransitionRepository | None = None,
    ) -> None:
        self.repo = repo
        self.transition_repo = transition_repo

    @staticmethod
    def validate_transition(
        current_state: StrategyLifecycle, target_state: StrategyLifecycle
    ) -> None:
        """Validate if a lifecycle state transition is legally allowed.

        Raises StrategyLifecycleError if the transition is prohibited.
        """
        if current_state == target_state:
            return  # No-op

        allowed = _ALLOWED_TRANSITIONS.get(current_state, set())
        if target_state not in allowed:
            raise StrategyLifecycleError(
                f"Invalid strategy lifecycle transition: "
                f"{current_state.value} -> {target_state.value}"
            )

    def transition_state(
        self,
        strategy: StrategyVersion,
        target_state: StrategyLifecycle,
        reason: str = "",
        user: str = "system",
    ) -> StrategyVersion:
        """Transition strategy version to a new lifecycle state.

        Enforces transition rules and immutability invariants.
        """
        # If in PRODUCTION, config cannot be changed; only state transition to DEPRECATED allowed
        if strategy.is_production and target_state != StrategyLifecycle.DEPRECATED:
            raise StrategyImmutabilityError(
                f"Production strategy version {strategy.qualified_name} "
                f"is immutable and can only be DEPRECATED"
            )

        self.validate_transition(strategy.lifecycle, target_state)

        new_version = StrategyVersion(
            strategy_id=strategy.strategy_id,
            version=strategy.version,
            lifecycle=target_state,
            parameters=strategy.parameters,
            risk_overrides=strategy.risk_overrides,
            applicable_regimes=strategy.applicable_regimes,
            metadata=strategy.metadata,
            created_at=datetime.now(UTC),
            created_by=user,
        )

        if self.repo is not None:
            self.repo.save(new_version)

        if self.transition_repo is not None:
            self.transition_repo.save(
                entity_type="STRATEGY",
                entity_id=strategy.qualified_name,
                from_state=strategy.lifecycle.value,
                to_state=target_state.value,
                reason=reason or f"Transitioned to {target_state.value} by {user}",
            )

        logger.info(
            f"Strategy {strategy.qualified_name} transitioned: "
            f"{strategy.lifecycle.value} -> {target_state.value}"
        )
        return new_version

    def update_configuration(
        self,
        strategy: StrategyVersion,
        new_parameters: dict[str, Any] | None = None,
        new_risk_overrides: dict[str, float] | None = None,
        new_regimes: list[MarketRegime] | None = None,
    ) -> StrategyVersion:
        """Update strategy configuration parameters.

        Raises StrategyImmutabilityError if strategy is in PRODUCTION.
        """
        if strategy.is_production:
            raise StrategyImmutabilityError(
                f"Cannot mutate configuration of production strategy version "
                f"{strategy.qualified_name}. Create a new version."
            )

        updated_params = new_parameters if new_parameters is not None else strategy.parameters
        updated_risk = (
            new_risk_overrides if new_risk_overrides is not None else strategy.risk_overrides
        )
        updated_regimes = new_regimes if new_regimes is not None else strategy.applicable_regimes

        updated_version = StrategyVersion(
            strategy_id=strategy.strategy_id,
            version=strategy.version,
            lifecycle=strategy.lifecycle,
            parameters=updated_params,
            risk_overrides=updated_risk,
            applicable_regimes=updated_regimes,
            metadata=strategy.metadata,
            created_at=datetime.now(UTC),
            created_by=strategy.created_by,
        )

        if self.repo is not None:
            self.repo.save(updated_version)

        return updated_version

    def create_new_version(
        self,
        base_strategy: StrategyVersion,
        increment_type: str = "patch",
        new_parameters: dict[str, Any] | None = None,
        new_risk_overrides: dict[str, float] | None = None,
        user: str = "system",
    ) -> StrategyVersion:
        """Create a new version derived from an existing strategy version.

        Resets lifecycle to IDEA/RESEARCH while creating an incremented version string.
        """
        semver = SemanticVersion.parse(base_strategy.version)
        if increment_type == "major":
            next_semver = semver.increment_major()
        elif increment_type == "minor":
            next_semver = semver.increment_minor()
        else:
            next_semver = semver.increment_patch()

        new_version_str = next_semver.to_string(prefix_v=True)

        new_strategy = StrategyVersion(
            strategy_id=base_strategy.strategy_id,
            version=new_version_str,
            lifecycle=StrategyLifecycle.IDEA,
            parameters=new_parameters
            if new_parameters is not None
            else dict(base_strategy.parameters),
            risk_overrides=new_risk_overrides
            if new_risk_overrides is not None
            else dict(base_strategy.risk_overrides),
            applicable_regimes=list(base_strategy.applicable_regimes),
            metadata={"parent_version": base_strategy.version},
            created_at=datetime.now(UTC),
            created_by=user,
        )

        if self.repo is not None:
            self.repo.save(new_strategy)

        logger.info(f"Created new strategy version: {new_strategy.qualified_name}")
        return new_strategy


__all__ = ["StrategyLifecycleManager"]
