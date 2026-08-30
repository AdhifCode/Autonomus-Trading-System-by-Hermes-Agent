"""Domain models for the Knowledge System (Obsidian & Learning Pipeline).

See architecture.md §16-§19 and implementation_spec.md §17.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class NoteCategory(StrEnum):
    """Obsidian vault directory / note categories."""

    TRADING_LOGS = "Trading Logs"
    METHODOLOGY = "Methodology"
    MARKET_REGIMES = "Market Regimes"
    LESSONS_LEARNED = "Lessons Learned"
    PERFORMANCE = "Performance"
    RESEARCH = "Research"
    EXPERIMENTS = "Experiments"
    REFERENCES = "References"


class LearningStage(StrEnum):
    """Learning Loop V2 progression stages (architecture.md §19)."""

    RAW_TRADE_EVENT = "RAW_TRADE_EVENT"
    STATISTICAL_ANALYSIS = "STATISTICAL_ANALYSIS"
    LLM_REFLECTION = "LLM_REFLECTION"
    CANDIDATE_LESSON = "CANDIDATE_LESSON"
    EVIDENCE_CHECK = "EVIDENCE_CHECK"
    CANDIDATE_HYPOTHESIS = "CANDIDATE_HYPOTHESIS"
    BACKTEST = "BACKTEST"
    WALK_FORWARD = "WALK_FORWARD"
    PAPER_TRADING = "PAPER_TRADING"
    HUMAN_APPROVAL = "HUMAN_APPROVAL"
    PRODUCTION_STRATEGY = "PRODUCTION_STRATEGY"


class KnowledgeNote(BaseModel):
    """Parsed Markdown knowledge note with metadata and temporal provenance."""

    note_id: str = Field(min_length=1, description="Unique identifier or relative vault path")
    path: str = Field(min_length=1, description="Relative path within the Obsidian vault")
    title: str = Field(min_length=1)
    category: NoteCategory = NoteCategory.REFERENCES
    content: str = Field(default="")
    yaml_frontmatter: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)
    internal_links: list[str] = Field(
        default_factory=list, description="Target note paths/titles from [[links]]"
    )
    backlinks: list[str] = Field(default_factory=list, description="Notes that link to this note")

    # Provenance fields (architecture §26, spec §17)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    available_at: datetime = Field(
        default_factory=lambda: datetime.now(UTC), description="Strict temporal boundary timestamp"
    )
    author: str = Field(default="System")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source_trade_id: str | None = Field(default=None)
    source_event_id: str | None = Field(default=None)


class TradeJournalEntry(BaseModel):
    """Structured trade journal schema matching architecture.md §18."""

    trade_id: str = Field(pattern=r"^TRD-\d{8}-\d{6}$|^TRD-[A-Za-z0-9_-]+$")
    timestamp_entry: datetime
    timestamp_exit: datetime | None = None

    symbol: str = Field(min_length=1)
    direction: str = Field(pattern=r"^(LONG|SHORT)$")

    strategy_id: str = Field(min_length=1)
    strategy_version: str = Field(min_length=1)

    entry_price: float = Field(gt=0)
    exit_price: float | None = Field(default=None, gt=0)
    quantity: float = Field(gt=0)

    gross_pnl: float = Field(default=0.0)
    fees: float = Field(default=0.0, ge=0)
    slippage_cost: float = Field(default=0.0, ge=0)
    funding_cost: float = Field(default=0.0)

    net_pnl: float = Field(default=0.0)
    net_return: float = Field(default=0.0)

    market_regime: str = Field(default="UNKNOWN")
    llm_confidence: float = Field(default=0.0, ge=0.0, le=1.0)

    risk_decision: str = Field(default="APPROVED")
    risk_policy_version: str = Field(default="1.0.0")

    tags: list[str] = Field(default_factory=list)
    notes: str = Field(default="")


class CandidateLesson(BaseModel):
    """Candidate lesson lifecycle model (architecture.md §19).

    INVARIANT: AI-generated lessons are hypotheses, not statistical proof.
    Direct promotion from CANDIDATE_LESSON to PRODUCTION_STRATEGY is strictly prohibited.
    """

    lesson_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    description: str
    stage: LearningStage = LearningStage.CANDIDATE_LESSON
    is_hypothesis: bool = Field(default=True, description="Always True for AI-generated lessons")
    evidence_trade_ids: list[str] = Field(default_factory=list)
    evidence_count: int = Field(default=0, ge=0)
    author: str = Field(default="Hermes")
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    human_approved: bool = Field(default=False)
    target_strategy_id: str | None = Field(default=None)
    notes_path: str | None = Field(default=None)
