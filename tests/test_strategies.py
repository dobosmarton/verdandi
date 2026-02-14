"""Tests for the dual discovery agent strategy system."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from verdandi.models.idea import (
    ComplaintEvidence,
    DiscoveryType,
    IdeaCandidate,
    OpportunityReport,
    PainPoint,
    ProblemReport,
    TrendSignal,
)
from verdandi.strategies import (
    ALL_STRATEGIES,
    DISRUPTION_STRATEGY,
    MOONSHOT_STRATEGY,
)

if TYPE_CHECKING:
    from verdandi.config import Settings
    from verdandi.db import Database
    from verdandi.orchestrator import PipelineRunner


# ---------------------------------------------------------------------------
# Strategy definition tests
# ---------------------------------------------------------------------------


class TestStrategyDefinitions:
    """Verify both strategy constants have all required fields."""

    def test_disruption_strategy_fields(self) -> None:
        assert DISRUPTION_STRATEGY.discovery_type == DiscoveryType.DISRUPTION
        assert DISRUPTION_STRATEGY.name == "Disruption Agent"
        assert len(DISRUPTION_STRATEGY.discovery_queries) >= 3
        assert DISRUPTION_STRATEGY.discovery_perplexity_question
        assert DISRUPTION_STRATEGY.discovery_system_prompt
        assert DISRUPTION_STRATEGY.synthesis_system_prompt
        assert DISRUPTION_STRATEGY.discovery_output_model == "ProblemReport"

    def test_moonshot_strategy_fields(self) -> None:
        assert MOONSHOT_STRATEGY.discovery_type == DiscoveryType.MOONSHOT
        assert MOONSHOT_STRATEGY.name == "Moonshot Agent"
        assert len(MOONSHOT_STRATEGY.discovery_queries) >= 3
        assert MOONSHOT_STRATEGY.discovery_perplexity_question
        assert MOONSHOT_STRATEGY.discovery_system_prompt
        assert MOONSHOT_STRATEGY.synthesis_system_prompt
        assert MOONSHOT_STRATEGY.discovery_output_model == "OpportunityReport"

    def test_strategies_have_distinct_queries(self) -> None:
        assert set(DISRUPTION_STRATEGY.discovery_queries) != set(
            MOONSHOT_STRATEGY.discovery_queries
        )

    def test_strategies_have_distinct_system_prompts(self) -> None:
        assert (
            DISRUPTION_STRATEGY.discovery_system_prompt != MOONSHOT_STRATEGY.discovery_system_prompt
        )
        assert (
            DISRUPTION_STRATEGY.synthesis_system_prompt != MOONSHOT_STRATEGY.synthesis_system_prompt
        )

    def test_strategy_is_frozen(self) -> None:
        with pytest.raises(Exception):  # noqa: B017
            DISRUPTION_STRATEGY.name = "Modified"  # type: ignore[misc]

    def test_all_strategies_list(self) -> None:
        assert len(ALL_STRATEGIES) == 2
        types = {s.discovery_type for s in ALL_STRATEGIES}
        assert types == {DiscoveryType.DISRUPTION, DiscoveryType.MOONSHOT}

    def test_disruption_prioritizes_reddit(self) -> None:
        assert DISRUPTION_STRATEGY.prioritize_reddit is True

    def test_moonshot_deprioritizes_reddit(self) -> None:
        assert MOONSHOT_STRATEGY.prioritize_reddit is False

    def test_both_prioritize_hn(self) -> None:
        assert DISRUPTION_STRATEGY.prioritize_hn is True
        assert MOONSHOT_STRATEGY.prioritize_hn is True


# ---------------------------------------------------------------------------
# Model tests — new discovery models
# ---------------------------------------------------------------------------


class TestDiscoveryModels:
    """Test the new Phase 1 output models."""

    def test_problem_report_creation(self) -> None:
        report = ProblemReport(
            problem_area="Invoice reconciliation for freelance accountants",
            user_group="Freelance accountants with 10-50 clients",
            workflow_description="Manual matching of bank transactions to invoices",
            pain_severity=8,
            pain_frequency="weekly",
            complaint_count=15,
            evidence=[
                ComplaintEvidence(
                    source="Reddit r/accounting",
                    quote="I spend 3 hours every Friday matching invoices",
                    url="https://reddit.com/r/accounting/abc",
                    upvotes=42,
                ),
            ],
            existing_tools=["QuickBooks", "FreshBooks"],
            why_existing_tools_fail="Auto-matching accuracy below 60%",
        )
        assert report.discovery_type == DiscoveryType.DISRUPTION
        assert report.pain_severity == 8
        assert len(report.evidence) == 1
        assert report.evidence[0].upvotes == 42

    def test_problem_report_is_frozen(self) -> None:
        report = ProblemReport(
            problem_area="Test",
            user_group="Test users",
            workflow_description="Test workflow",
            pain_severity=5,
            pain_frequency="daily",
            complaint_count=1,
        )
        with pytest.raises(Exception):  # noqa: B017
            report.problem_area = "Modified"  # type: ignore[misc]

    def test_opportunity_report_creation(self) -> None:
        report = OpportunityReport(
            capability_or_trend="Real-time video understanding via multimodal AI",
            future_scenario="In 2-3 years, every creator will have AI editing",
            target_user_group="YouTube creators with 10K-100K subscribers",
            why_now="GPT-4o and Claude 4 can process video in real-time",
            signals=[
                TrendSignal(
                    description="Multimodal AI models can now process video",
                    source="OpenAI blog",
                    url="https://openai.com/blog",
                    recency="3 months",
                ),
            ],
            existing_attempts=["Descript", "CapCut AI"],
            moat_potential="First-mover in real-time editing feedback",
        )
        assert report.discovery_type == DiscoveryType.MOONSHOT
        assert len(report.signals) == 1

    def test_idea_candidate_with_discovery_type(self) -> None:
        idea = IdeaCandidate(
            experiment_id=1,
            title="TestProduct",
            one_liner="A test product",
            problem_statement="Testing is hard",
            target_audience="Testers",
            category="testing",
            discovery_type=DiscoveryType.MOONSHOT,
        )
        assert idea.discovery_type == DiscoveryType.MOONSHOT

    def test_idea_candidate_default_discovery_type(self) -> None:
        idea = IdeaCandidate(
            experiment_id=1,
            title="TestProduct",
            one_liner="A test product",
            problem_statement="Testing is hard",
            target_audience="Testers",
            category="testing",
        )
        assert idea.discovery_type == DiscoveryType.DISRUPTION

    def test_idea_candidate_discovery_report_json(self) -> None:
        report = ProblemReport(
            problem_area="Test",
            user_group="Test users",
            workflow_description="Test workflow",
            pain_severity=5,
            pain_frequency="daily",
            complaint_count=1,
        )
        idea = IdeaCandidate(
            experiment_id=1,
            title="TestProduct",
            one_liner="A test product",
            problem_statement="Testing is hard",
            target_audience="Testers",
            category="testing",
            discovery_report_json=report.model_dump_json(),
        )
        assert idea.discovery_report_json
        assert "Test users" in idea.discovery_report_json

    def test_pain_point_unchanged(self) -> None:
        """PainPoint model should still work as before."""
        pp = PainPoint(
            description="Test pain",
            severity=7,
            frequency="daily",
            source="HN",
        )
        assert pp.severity == 7
        assert pp.quote == ""  # default


# ---------------------------------------------------------------------------
# Strategy scheduling tests (via orchestrator)
# ---------------------------------------------------------------------------


class TestStrategyScheduling:
    """Test portfolio-aware strategy selection in the orchestrator."""

    @pytest.fixture()
    def runner(self, db: Database, settings: Settings) -> PipelineRunner:
        from verdandi.orchestrator import PipelineRunner

        return PipelineRunner(db=db, settings=settings, dry_run=True)

    def test_schedule_default_ratio(self, runner: PipelineRunner) -> None:
        """With no existing experiments, greedy ratio converges toward 70/30."""
        schedule = runner._build_strategy_schedule(3)
        types = [s.discovery_type for s in schedule]
        # Greedy: d(0/0→d), m(1/1→m), d(1/2→d) = [d, m, d]
        assert types[0] == DiscoveryType.DISRUPTION
        assert types[1] == DiscoveryType.MOONSHOT
        assert types[2] == DiscoveryType.DISRUPTION

    def test_schedule_with_10_slots(self, runner: PipelineRunner) -> None:
        """10-slot schedule should approximate 70/30."""
        schedule = runner._build_strategy_schedule(10)
        disruption_count = sum(1 for s in schedule if s.discovery_type == DiscoveryType.DISRUPTION)
        moonshot_count = sum(1 for s in schedule if s.discovery_type == DiscoveryType.MOONSHOT)
        assert disruption_count == 7
        assert moonshot_count == 3

    def test_schedule_single_idea(self, runner: PipelineRunner) -> None:
        """Single idea should be disruption (starts with disruption)."""
        schedule = runner._build_strategy_schedule(1)
        assert schedule[0].discovery_type == DiscoveryType.DISRUPTION

    def test_count_ideas_by_type_empty(self, runner: PipelineRunner) -> None:
        """No experiments → count is 0."""
        assert runner._count_ideas_by_type("disruption") == 0
        assert runner._count_ideas_by_type("moonshot") == 0

    def test_discovery_batch_assigns_discovery_type(
        self, runner: PipelineRunner, db: Database
    ) -> None:
        """Ideas from discovery batch should have discovery_type set."""
        ids = runner.run_discovery_batch(max_ideas=2)
        assert len(ids) >= 1
        for eid in ids:
            result = db.get_step_result(eid, "idea_discovery")
            assert result is not None
            data = result["data"]
            assert isinstance(data, dict)
            assert data.get("discovery_type") in ("disruption", "moonshot")

    def test_forced_disruption_strategy(self, runner: PipelineRunner, db: Database) -> None:
        """All ideas should be disruption when strategy is forced."""
        ids = runner.run_discovery_batch(max_ideas=2, strategy_override=DISRUPTION_STRATEGY)
        for eid in ids:
            result = db.get_step_result(eid, "idea_discovery")
            assert result is not None
            data = result["data"]
            assert isinstance(data, dict)
            assert data.get("discovery_type") == "disruption"

    def test_forced_moonshot_strategy(self, runner: PipelineRunner, db: Database) -> None:
        """All ideas should be moonshot when strategy is forced."""
        ids = runner.run_discovery_batch(max_ideas=2, strategy_override=MOONSHOT_STRATEGY)
        for eid in ids:
            result = db.get_step_result(eid, "idea_discovery")
            assert result is not None
            data = result["data"]
            assert isinstance(data, dict)
            assert data.get("discovery_type") == "moonshot"

    def test_count_updates_after_discovery(self, runner: PipelineRunner, db: Database) -> None:
        """_count_ideas_by_type should reflect newly created experiments."""
        runner.run_discovery_batch(max_ideas=2, strategy_override=DISRUPTION_STRATEGY)
        assert runner._count_ideas_by_type("disruption") == 2
        assert runner._count_ideas_by_type("moonshot") == 0


# ---------------------------------------------------------------------------
# Scoring context tests
# ---------------------------------------------------------------------------


class TestScoringContext:
    """Test that scoring step adds discovery-type-aware context."""

    def test_disruption_scoring_context(self) -> None:
        from verdandi.agents.scoring import _scoring_context_for_discovery_type

        ctx = _scoring_context_for_discovery_type(DiscoveryType.DISRUPTION)
        assert "DISRUPTION" in ctx
        assert "pain_severity" in ctx
        assert "willingness_to_pay" in ctx

    def test_moonshot_scoring_context(self) -> None:
        from verdandi.agents.scoring import _scoring_context_for_discovery_type

        ctx = _scoring_context_for_discovery_type(DiscoveryType.MOONSHOT)
        assert "MOONSHOT" in ctx
        assert "tam_size" in ctx
        assert "growth" in ctx.lower()
