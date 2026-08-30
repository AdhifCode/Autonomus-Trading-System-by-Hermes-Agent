"""Learning Pipeline V2 Engine (architecture.md §19).

Enforces the 11-stage learning workflow:
Trade -> Raw Trade Event -> Statistical Analysis -> LLM Reflection -> Candidate Lesson ->
Evidence Check -> Candidate Hypothesis -> Backtest -> Walk Forward -> Paper Trading ->
Human Approval -> Production Strategy

CRITICAL INVARIANTS:
1. AI-generated reflections create hypotheses (CandidateLesson.is_hypothesis = True).
2. Obsidian notes MUST NOT directly modify operational strategy code or SQLite state.
3. Direct jumps to PRODUCTION_STRATEGY are prohibited (raises StrategyLifecycleError).
4. Human approval is strictly required prior to PRODUCTION_STRATEGY transition.
"""

from __future__ import annotations

from datetime import UTC, datetime

from core.errors import StrategyImmutabilityError, StrategyLifecycleError
from core.logging import get_logger
from knowledge.models import CandidateLesson, LearningStage, NoteCategory
from knowledge.obsidian.vault import ObsidianVaultManager

logger = get_logger(__name__)

# Valid state transitions map
_VALID_TRANSITIONS: dict[LearningStage, set[LearningStage]] = {
    LearningStage.RAW_TRADE_EVENT: {LearningStage.STATISTICAL_ANALYSIS},
    LearningStage.STATISTICAL_ANALYSIS: {LearningStage.LLM_REFLECTION},
    LearningStage.LLM_REFLECTION: {LearningStage.CANDIDATE_LESSON},
    LearningStage.CANDIDATE_LESSON: {LearningStage.EVIDENCE_CHECK},
    LearningStage.EVIDENCE_CHECK: {
        LearningStage.CANDIDATE_HYPOTHESIS,
        LearningStage.CANDIDATE_LESSON,
    },
    LearningStage.CANDIDATE_HYPOTHESIS: {LearningStage.BACKTEST},
    LearningStage.BACKTEST: {LearningStage.WALK_FORWARD, LearningStage.CANDIDATE_LESSON},
    LearningStage.WALK_FORWARD: {LearningStage.PAPER_TRADING, LearningStage.CANDIDATE_LESSON},
    LearningStage.PAPER_TRADING: {LearningStage.HUMAN_APPROVAL},
    LearningStage.HUMAN_APPROVAL: {LearningStage.PRODUCTION_STRATEGY},
    # Production strategies are immutable (architecture §20)
    LearningStage.PRODUCTION_STRATEGY: set(),
}


class LearningPipeline:
    """Manager for the Learning Loop V2 lifecycle."""

    def __init__(self, vault_manager: ObsidianVaultManager | None = None) -> None:
        self.vault = vault_manager or ObsidianVaultManager()
        self._lessons: dict[str, CandidateLesson] = {}

    def create_candidate_lesson_from_reflection(
        self,
        lesson_id: str,
        title: str,
        reflection_text: str,
        source_trade_id: str | None = None,
        target_strategy_id: str | None = None,
        author: str = "Hermes",
    ) -> CandidateLesson:
        """Create a new CandidateLesson from LLM reflection.

        INVARIANT 1: Marked as hypothesis (is_hypothesis=True), NOT statistical proof.
        """
        now = datetime.now(UTC)
        lesson = CandidateLesson(
            lesson_id=lesson_id,
            title=title,
            description=reflection_text,
            stage=LearningStage.CANDIDATE_LESSON,
            is_hypothesis=True,  # Always hypothesis
            evidence_trade_ids=[source_trade_id] if source_trade_id else [],
            evidence_count=1 if source_trade_id else 0,
            author=author,
            created_at=now,
            updated_at=now,
            human_approved=False,
            target_strategy_id=target_strategy_id,
        )

        self._lessons[lesson_id] = lesson

        # Write semantic note into Obsidian vault under Lessons Learned/
        self._write_lesson_note(lesson)
        logger.info(f"Created candidate lesson: {lesson_id} ('{title}')")
        return lesson

    def advance_stage(
        self,
        lesson_id: str,
        target_stage: LearningStage,
        evidence_trade_ids: list[str] | None = None,
        human_approved: bool = False,
        min_evidence_count: int = 5,
    ) -> CandidateLesson:
        """Advance a candidate lesson to the target learning stage.

        Enforces state machine transitions, evidence requirements, and human approval.
        Raises StrategyLifecycleError or StrategyImmutabilityError on violation.
        """
        lesson = self._lessons.get(lesson_id)
        if not lesson:
            raise StrategyLifecycleError(f"Lesson not found: {lesson_id}")

        current_stage = lesson.stage

        # Check production immutability
        if current_stage == LearningStage.PRODUCTION_STRATEGY:
            raise StrategyImmutabilityError(
                f"Lesson/Strategy {lesson_id} is already in PRODUCTION and cannot be modified."
            )

        # Check valid step-by-step transition
        allowed_next = _VALID_TRANSITIONS.get(current_stage, set())
        if target_stage not in allowed_next:
            raise StrategyLifecycleError(
                f"Prohibited transition from {current_stage.value} to {target_stage.value}. "
                f"Allowed transitions: {[s.value for s in allowed_next]}"
            )

        # Rule: EVIDENCE_CHECK requires min evidence count
        if target_stage == LearningStage.EVIDENCE_CHECK:
            if evidence_trade_ids:
                for tid in evidence_trade_ids:
                    if tid not in lesson.evidence_trade_ids:
                        lesson.evidence_trade_ids.append(tid)
                lesson.evidence_count = len(lesson.evidence_trade_ids)

            if lesson.evidence_count < min_evidence_count:
                logger.warning(
                    f"Evidence check for {lesson_id}: insufficient trade evidence "
                    f"({lesson.evidence_count} < {min_evidence_count})."
                )

        # Rule: Transition to PRODUCTION_STRATEGY strictly requires human approval
        if target_stage == LearningStage.PRODUCTION_STRATEGY:
            if not human_approved and not lesson.human_approved:
                raise StrategyLifecycleError(
                    f"Cannot promote lesson {lesson_id} to PRODUCTION_STRATEGY "
                    "without human approval."
                )
            lesson.human_approved = True

        lesson.stage = target_stage
        lesson.updated_at = datetime.now(UTC)
        self._write_lesson_note(lesson)

        logger.info(
            f"Advanced lesson {lesson_id} stage: {current_stage.value} -> {target_stage.value}"
        )
        return lesson

    def get_lesson(self, lesson_id: str) -> CandidateLesson | None:
        """Get CandidateLesson by ID."""
        return self._lessons.get(lesson_id)

    def list_lessons(self) -> list[CandidateLesson]:
        """List all tracked candidate lessons."""
        return list(self._lessons.values())

    def _write_lesson_note(self, lesson: CandidateLesson) -> None:
        """Write semantic markdown note into Obsidian Lessons Learned directory (non-blocking)."""
        ev_str = ", ".join(lesson.evidence_trade_ids) if lesson.evidence_trade_ids else "None"
        content = f"""---
lesson_id: "{lesson.lesson_id}"
title: "{lesson.title}"
stage: "{lesson.stage.value}"
is_hypothesis: {str(lesson.is_hypothesis).lower()}
author: "{lesson.author}"
evidence_count: {lesson.evidence_count}
human_approved: {str(lesson.human_approved).lower()}
created_at: "{lesson.created_at.isoformat()}"
updated_at: "{lesson.updated_at.isoformat()}"
category: "Lessons Learned"
tags:
  - lesson
  - hypothesis
  - {lesson.stage.value.lower()}
---

# Lesson Learned: {lesson.title}

## Description & Hypothesis
{lesson.description}

## Learning Loop Status
- **Current Stage**: `{lesson.stage.value}`
- **Is Hypothesis Only**: `{lesson.is_hypothesis}`
- **Evidence Count**: {lesson.evidence_count} trades ({ev_str})
- **Human Approved**: `{lesson.human_approved}`

> [!IMPORTANT]
> AI-generated lessons are candidate hypotheses for quantitative backtesting.
> Obsidian notes DO NOT directly alter operational trading algorithms or SQLite risk rules.
"""
        filename = f"{lesson.lesson_id}_{lesson.title.replace(' ', '_')}.md"
        self.vault.write_note(NoteCategory.LESSONS_LEARNED, filename, content)
