"""Strategy Versioning & Immutability Management Module.

Enforces semantic versioning rules and immutability of strategy configurations:
- Semantic version parsing and validation (vMAJOR.MINOR.PATCH)
- Automatic version incrementing (patch, minor, major)
- Immutable strategy configuration history
- Prevents mutation of production versions

See implementation_spec.md §15.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from core.domain.strategy import StrategyVersion
from core.errors import StrategyImmutabilityError

_SEMVER_REGEX = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


class SemanticVersion(BaseModel):
    """Parsed semantic version representation (MAJOR.MINOR.PATCH)."""

    major: int = Field(ge=0)
    minor: int = Field(ge=0)
    patch: int = Field(ge=0)

    @classmethod
    def parse(cls, version_str: str) -> SemanticVersion:
        """Parse a version string into a SemanticVersion."""
        match = _SEMVER_REGEX.match(version_str.strip())
        if not match:
            raise ValueError(f"Invalid semantic version string: {version_str}")
        return cls(
            major=int(match.group(1)),
            minor=int(match.group(2)),
            patch=int(match.group(3)),
        )

    def to_string(self, prefix_v: bool = True) -> str:
        """Convert version to string format (e.g. 'v1.0.0' or '1.0.0')."""
        prefix = "v" if prefix_v else ""
        return f"{prefix}{self.major}.{self.minor}.{self.patch}"

    def increment_patch(self) -> SemanticVersion:
        """Increment patch version (e.g., 1.0.0 -> 1.0.1)."""
        return SemanticVersion(major=self.major, minor=self.minor, patch=self.patch + 1)

    def increment_minor(self) -> SemanticVersion:
        """Increment minor version (e.g., 1.0.0 -> 1.1.0)."""
        return SemanticVersion(major=self.major, minor=self.minor + 1, patch=0)

    def increment_major(self) -> SemanticVersion:
        """Increment major version (e.g., 1.0.0 -> 2.0.0)."""
        return SemanticVersion(major=self.major + 1, minor=0, patch=0)

    def __lt__(self, other: SemanticVersion) -> bool:
        return (self.major, self.minor, self.patch) < (other.major, other.minor, other.patch)

    def __le__(self, other: SemanticVersion) -> bool:
        return (self.major, self.minor, self.patch) <= (other.major, other.minor, other.patch)


class StrategyVersionHistory(BaseModel):
    """Tracks version progression history for a strategy ID."""

    strategy_id: str
    versions: list[StrategyVersion] = Field(default_factory=list)

    def get_latest(self) -> StrategyVersion | None:
        """Get the latest version in history."""
        if not self.versions:
            return None
        return self.versions[-1]

    def get_production_version(self) -> StrategyVersion | None:
        """Get the currently active PRODUCTION version, if any."""
        for v in reversed(self.versions):
            if v.is_production:
                return v
        return None

    def add_version(self, version: StrategyVersion) -> None:
        """Add a new version to history after validating immutability."""
        if version.strategy_id != self.strategy_id:
            raise ValueError(
                f"Strategy ID mismatch: expected {self.strategy_id}, got {version.strategy_id}"
            )
        # Check for existing identical version
        for v in self.versions:
            if v.version == version.version:
                if v.is_production:
                    raise StrategyImmutabilityError(
                        f"Cannot overwrite production strategy version {v.qualified_name}"
                    )
        self.versions.append(version)


__all__ = [
    "SemanticVersion",
    "StrategyVersionHistory",
]
