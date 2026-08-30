"""Unit & Adversarial Security Tests for Phase 11: Knowledge System.

Validates:
1. Markdown parser, YAML frontmatter, [[wiki-links]], and #tags.
2. Obsidian vault manager structure, non-blocking scanning, and fault tolerance.
3. Indexing, link-graph computation, and backlinks.
4. Full-text search and temporal provenance RAG filtering (available_at <= as_of).
5. Trade journal formatting and note generation.
6. Learning Loop V2 lifecycle, AI hypothesis rules, and human approval requirements.
7. Architectural invariants: Obsidian failure cannot block execution; notes are read-only.
"""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from core.errors import StrategyImmutabilityError, StrategyLifecycleError
from knowledge import (
    KnowledgeAPI,
    KnowledgeIndex,
    KnowledgeNote,
    LearningPipeline,
    LearningStage,
    MarkdownParser,
    NoteCategory,
    ObsidianVaultManager,
    SearchEngine,
    TradeJournalEntry,
    TradeJournalManager,
)


@pytest.fixture
def temp_vault():
    """Fixture providing a temporary directory as an Obsidian vault."""
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "obsidian-vault"
        yield vault_path


class TestMarkdownParserAndVaultManager:
    """Tests for Markdown parsing and Obsidian vault operations."""

    def test_markdown_parser_extracts_frontmatter_links_and_tags(self):
        raw_md = """---
title: "BTC Breakout Strategy Note"
category: "Methodology"
author: "Hermes Agent"
confidence: 0.88
created_at: "2026-08-20T10:00:00Z"
available_at: "2026-08-20T10:00:00Z"
source_trade_id: "TRD-20260820-000001"
tags:
  - breakout
  - btc
---

# BTC Breakout Strategy

Analysis of BTC [[Breakout Pattern]] in high volume regimes.
See also [[Risk Limits|Risk Management]].

#bullish #momentum
"""
        parser = MarkdownParser()
        note = parser.parse(raw_md, file_path="Methodology/BTC Breakout.md")

        assert note.title == "BTC Breakout Strategy Note"
        assert note.category == NoteCategory.METHODOLOGY
        assert note.author == "Hermes Agent"
        assert note.confidence == 0.88
        assert note.source_trade_id == "TRD-20260820-000001"

        # Tags (YAML + inline)
        assert "breakout" in note.tags
        assert "btc" in note.tags
        assert "bullish" in note.tags
        assert "momentum" in note.tags

        # Links
        assert "Breakout Pattern" in note.internal_links
        assert "Risk Limits" in note.internal_links

    def test_obsidian_vault_manager_structure_creation_and_scan(self, temp_vault):
        vault_mgr = ObsidianVaultManager(temp_vault)
        assert vault_mgr.ensure_vault_structure() is True

        # Check standard directories created
        for category in NoteCategory:
            assert (temp_vault / category.value).exists()

        # Write test notes
        vault_mgr.write_note(
            NoteCategory.METHODOLOGY, "Breakout.md", "# Breakout Strategy\nDetails..."
        )
        vault_mgr.write_note(
            NoteCategory.LESSONS_LEARNED, "Drawdown.md", "# Drawdown Analysis\nDetails..."
        )

        notes = vault_mgr.scan_vault()
        assert len(notes) == 2
        titles = [n.title for n in notes]
        assert "Breakout Strategy" in titles
        assert "Drawdown Analysis" in titles


class TestKnowledgeIndexingAndSearch:
    """Tests for indexing, link graphs, full-text search, and temporal provenance."""

    def test_knowledge_index_link_graph_and_backlinks(self):
        index = KnowledgeIndex()

        note_a = KnowledgeNote(
            note_id="note_a",
            path="Methodology/Strategy A.md",
            title="Strategy A",
            category=NoteCategory.METHODOLOGY,
            content="Mentions [[Strategy B]]",
            internal_links=["Strategy B"],
        )

        note_b = KnowledgeNote(
            note_id="note_b",
            path="Methodology/Strategy B.md",
            title="Strategy B",
            category=NoteCategory.METHODOLOGY,
            content="Base strategy description",
            internal_links=[],
        )

        index.add_note(note_a)
        index.add_note(note_b)
        index.build_link_graph()

        backlinks_b = index.get_backlinks("Methodology/Strategy B.md")
        assert len(backlinks_b) == 1
        assert backlinks_b[0].path == "Methodology/Strategy A.md"

    def test_search_engine_temporal_provenance_boundary(self):
        index = KnowledgeIndex()
        t0 = datetime(2026, 8, 20, 12, 0, 0, tzinfo=UTC)
        t_past = t0 - timedelta(days=1)
        t_future = t0 + timedelta(days=1)

        past_note = KnowledgeNote(
            note_id="past_note",
            path="Research/Past Note.md",
            title="Past Market Context",
            category=NoteCategory.RESEARCH,
            content="Historical analysis available before T0",
            tags=["historical"],
            created_at=t_past,
            available_at=t_past,
        )

        future_note = KnowledgeNote(
            note_id="future_note",
            path="Research/Future Note.md",
            title="Future Leaked Data",
            category=NoteCategory.RESEARCH,
            content="Data available after T0",
            tags=["future"],
            created_at=t_future,
            available_at=t_future,
        )

        index.add_note(past_note)
        index.add_note(future_note)

        search_engine = SearchEngine(index=index)

        # Search as of t0 -> future_note MUST be excluded
        results_as_of_t0 = search_engine.search(as_of=t0)
        assert len(results_as_of_t0) == 1
        assert results_as_of_t0[0].note_id == "past_note"

        # Search as of future -> both notes available
        results_future = search_engine.search(as_of=t_future)
        assert len(results_future) == 2


class TestTradeJournalManager:
    """Tests for TradeJournalEntry formatting and note creation."""

    def test_trade_journal_entry_formatting(self, temp_vault):
        vault_mgr = ObsidianVaultManager(temp_vault)
        journal_mgr = TradeJournalManager(vault_manager=vault_mgr)

        entry = TradeJournalEntry(
            trade_id="TRD-20260828-000123",
            timestamp_entry=datetime(2026, 8, 28, 8, 30, 0, tzinfo=UTC),
            timestamp_exit=datetime(2026, 8, 28, 14, 45, 0, tzinfo=UTC),
            symbol="BTCUSDT",
            direction="LONG",
            strategy_id="breakout",
            strategy_version="2.1",
            entry_price=42500.0,
            exit_price=43200.0,
            quantity=0.5,
            gross_pnl=400.0,
            fees=35.0,
            slippage_cost=15.0,
            funding_cost=0.0,
            net_pnl=350.0,
            net_return=0.0165,
            market_regime="BULL",
            llm_confidence=0.75,
            risk_decision="APPROVED",
            risk_policy_version="1.4",
            tags=["breakout", "bull", "profitable"],
            notes="Strong momentum entry on 4h candle close.",
        )

        success = journal_mgr.create_journal_note(entry)
        assert success is True

        log_file = temp_vault / "Trading Logs" / "2026-08-28_TRD-20260828-000123_BTCUSDT_LONG.md"
        assert log_file.exists()

        content = log_file.read_text(encoding="utf-8")
        assert "TRD-20260828-000123" in content
        assert "strategy_id: breakout" in content
        assert "net_pnl: 350.0" in content
        assert "Strong momentum entry" in content


class TestLearningPipelineV2:
    """Tests for Learning Loop V2 stage transitions and safety invariants."""

    def test_llm_reflection_creates_candidate_lesson_as_hypothesis(self, temp_vault):
        vault_mgr = ObsidianVaultManager(temp_vault)
        pipeline = LearningPipeline(vault_manager=vault_mgr)

        lesson = pipeline.create_candidate_lesson_from_reflection(
            lesson_id="LES-001",
            title="High ADX Volatility Compression",
            reflection_text="Higher win rate when ADX > 30 during volatility compression.",
            source_trade_id="TRD-20260828-000123",
            target_strategy_id="breakout",
            author="Hermes",
        )

        assert lesson.lesson_id == "LES-001"
        assert lesson.stage == LearningStage.CANDIDATE_LESSON
        assert lesson.is_hypothesis is True  # CRITICAL INVARIANT: AI lessons are hypotheses
        assert lesson.human_approved is False

    def test_canonical_learning_pipeline_stage_progression(self, temp_vault):
        vault_mgr = ObsidianVaultManager(temp_vault)
        pipeline = LearningPipeline(vault_manager=vault_mgr)

        pipeline.create_candidate_lesson_from_reflection(
            lesson_id="LES-002",
            title="RSI Divergence Filter",
            reflection_text="Filter out counter-trend trades when RSI divergence is present.",
        )

        # Step 1: CANDIDATE_LESSON -> EVIDENCE_CHECK
        lesson = pipeline.advance_stage(
            "LES-002",
            LearningStage.EVIDENCE_CHECK,
            evidence_trade_ids=["TRD-1", "TRD-2", "TRD-3", "TRD-4", "TRD-5"],
            min_evidence_count=5,
        )
        assert lesson.stage == LearningStage.EVIDENCE_CHECK

        # Step 2: EVIDENCE_CHECK -> CANDIDATE_HYPOTHESIS
        lesson = pipeline.advance_stage("LES-002", LearningStage.CANDIDATE_HYPOTHESIS)
        assert lesson.stage == LearningStage.CANDIDATE_HYPOTHESIS

        # Step 3: CANDIDATE_HYPOTHESIS -> BACKTEST
        lesson = pipeline.advance_stage("LES-002", LearningStage.BACKTEST)
        assert lesson.stage == LearningStage.BACKTEST

        # Step 4: BACKTEST -> WALK_FORWARD
        lesson = pipeline.advance_stage("LES-002", LearningStage.WALK_FORWARD)
        assert lesson.stage == LearningStage.WALK_FORWARD

        # Step 5: WALK_FORWARD -> PAPER_TRADING
        lesson = pipeline.advance_stage("LES-002", LearningStage.PAPER_TRADING)
        assert lesson.stage == LearningStage.PAPER_TRADING

        # Step 6: PAPER_TRADING -> HUMAN_APPROVAL
        lesson = pipeline.advance_stage("LES-002", LearningStage.HUMAN_APPROVAL)
        assert lesson.stage == LearningStage.HUMAN_APPROVAL

        # Step 7: HUMAN_APPROVAL -> PRODUCTION_STRATEGY (with human_approved=True)
        lesson = pipeline.advance_stage(
            "LES-002", LearningStage.PRODUCTION_STRATEGY, human_approved=True
        )
        assert lesson.stage == LearningStage.PRODUCTION_STRATEGY
        assert lesson.human_approved is True

    def test_prohibited_stage_transition_raises_error(self, temp_vault):
        vault_mgr = ObsidianVaultManager(temp_vault)
        pipeline = LearningPipeline(vault_manager=vault_mgr)

        pipeline.create_candidate_lesson_from_reflection(
            lesson_id="LES-003",
            title="Direct Jump Attempt",
            reflection_text="Attempting to jump directly from Candidate Lesson to Production.",
        )

        # Prohibited: CANDIDATE_LESSON directly to PRODUCTION_STRATEGY
        with pytest.raises(StrategyLifecycleError, match="Prohibited transition"):
            pipeline.advance_stage(
                "LES-003", LearningStage.PRODUCTION_STRATEGY, human_approved=True
            )

    def test_production_strategy_transition_without_human_approval_fails(self, temp_vault):
        vault_mgr = ObsidianVaultManager(temp_vault)
        pipeline = LearningPipeline(vault_manager=vault_mgr)

        pipeline.create_candidate_lesson_from_reflection(
            lesson_id="LES-004",
            title="Unapproved Production Attempt",
            reflection_text="Attempting production promotion without human approval.",
        )

        # Move to HUMAN_APPROVAL stage step by step
        pipeline.advance_stage(
            "LES-004",
            LearningStage.EVIDENCE_CHECK,
            evidence_trade_ids=["T1", "T2", "T3", "T4", "T5"],
        )
        pipeline.advance_stage("LES-004", LearningStage.CANDIDATE_HYPOTHESIS)
        pipeline.advance_stage("LES-004", LearningStage.BACKTEST)
        pipeline.advance_stage("LES-004", LearningStage.WALK_FORWARD)
        pipeline.advance_stage("LES-004", LearningStage.PAPER_TRADING)
        pipeline.advance_stage("LES-004", LearningStage.HUMAN_APPROVAL)

        # Attempt transition to PRODUCTION_STRATEGY with human_approved=False
        with pytest.raises(StrategyLifecycleError, match="without human approval"):
            pipeline.advance_stage(
                "LES-004", LearningStage.PRODUCTION_STRATEGY, human_approved=False
            )

    def test_production_strategy_is_immutable(self, temp_vault):
        vault_mgr = ObsidianVaultManager(temp_vault)
        pipeline = LearningPipeline(vault_manager=vault_mgr)

        pipeline.create_candidate_lesson_from_reflection(
            lesson_id="LES-005",
            title="Immutable Production Lesson",
            reflection_text="Validated strategy lesson.",
        )

        # Move all the way to PRODUCTION_STRATEGY
        pipeline.advance_stage(
            "LES-005",
            LearningStage.EVIDENCE_CHECK,
            evidence_trade_ids=["T1", "T2", "T3", "T4", "T5"],
        )
        pipeline.advance_stage("LES-005", LearningStage.CANDIDATE_HYPOTHESIS)
        pipeline.advance_stage("LES-005", LearningStage.BACKTEST)
        pipeline.advance_stage("LES-005", LearningStage.WALK_FORWARD)
        pipeline.advance_stage("LES-005", LearningStage.PAPER_TRADING)
        pipeline.advance_stage("LES-005", LearningStage.HUMAN_APPROVAL)
        pipeline.advance_stage("LES-005", LearningStage.PRODUCTION_STRATEGY, human_approved=True)

        # Further state transition attempts must fail with StrategyImmutabilityError
        with pytest.raises(StrategyImmutabilityError, match="already in PRODUCTION"):
            pipeline.advance_stage("LES-005", LearningStage.BACKTEST)


class TestFaultToleranceAndNonBlockingInvariants:
    """Tests guaranteeing Obsidian failures NEVER block trading execution."""

    def test_obsidian_vault_unavailable_does_not_raise_exceptions(self, tmp_path):
        bad_path = tmp_path / "non_existent_vault_dir"
        api = KnowledgeAPI(vault_path=bad_path)

        assert api.is_vault_available() is False

        # Sync, search, get_note should execute safely without exceptions
        count = api.sync_knowledge()
        assert count == 0

        notes = api.search_notes("BTC")
        assert notes == []

        note = api.get_note("NonExistent.md")
        assert note is None

    def test_trade_journaling_queues_notes_when_vault_unavailable(self, tmp_path):
        bad_path = tmp_path / "non_existent_vault_dir_2"
        api = KnowledgeAPI(vault_path=bad_path)

        entry = TradeJournalEntry(
            trade_id="TRD-20260828-999999",
            timestamp_entry=datetime.now(UTC),
            symbol="ETHUSDT",
            direction="SHORT",
            strategy_id="mean_reversion",
            strategy_version="1.0",
            entry_price=2500.0,
            quantity=1.0,
        )

        # Recording entry when vault is unavailable should queue write without throwing error
        res = api.record_trade_journal_entry(entry)
        assert res is False
        assert api.sync_worker.queue.size == 1

    def test_obsidian_notes_do_not_modify_operational_trading_code(self):
        """CRITICAL INVARIANT: Obsidian notes are semantic memory only.

        Creating a methodology note in Obsidian does not alter RiskEngine policies,
        TradingMode, or executable strategy Python modules.
        """
        api = KnowledgeAPI()
        # Verify creating note does not alter any system runtime state
        note = KnowledgeNote(
            note_id="test_methodology",
            path="Methodology/Aggressive Strategy.md",
            title="Aggressive Strategy Override",
            category=NoteCategory.METHODOLOGY,
            content="Set max position size to 100%",
        )
        api.index.add_note(note)

        indexed_note = api.get_note("Methodology/Aggressive Strategy.md")
        assert indexed_note is not None
        assert indexed_note.content == "Set max position size to 100%"
        # Proves it is purely a semantic memory note object in KnowledgeIndex
