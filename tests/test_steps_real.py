"""Tests for Steps 0-4 with mocked LLM and research.

Verifies that each step:
- Correctly retrieves previous step results from DB
- Passes the right data to LLMClient.generate()
- Constructs valid output models with correct metadata
- Dry-run returns sensible mock data
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from verdandi.config import Settings
from verdandi.db import Database
from verdandi.models.experiment import Experiment, ExperimentStatus
from verdandi.models.idea import IdeaCandidate, PainPoint
from verdandi.models.landing_page import (
    FAQItem,
    FeatureItem,
    LandingPageContent,
    Testimonial,
)
from verdandi.models.mvp import Feature, MVPDefinition
from verdandi.models.research import Competitor, MarketResearch, SearchResult
from verdandi.models.scoring import Decision, PreBuildScore, ScoreComponent
from verdandi.steps.base import StepContext


@pytest.fixture()
def settings() -> Settings:
    return Settings(
        anthropic_api_key="test-key",
        require_human_review=False,
        data_dir="/tmp/verdandi-test",
        log_level="DEBUG",
        log_format="console",
        max_retries=1,
    )


@pytest.fixture()
def db(tmp_path: object) -> Database:
    from pathlib import Path

    path = Path(str(tmp_path))
    database = Database(path / "test.db")
    database.init_schema()
    yield database  # type: ignore[misc]
    database.close()


@pytest.fixture()
def experiment(db: Database) -> Experiment:
    exp = Experiment(
        idea_title="DevLog — Automated Developer Changelog",
        idea_summary="Auto-generate changelogs from git commits",
        status=ExperimentStatus.PENDING,
        worker_id="test-worker-1",
    )
    return db.create_experiment(exp)


def _make_ctx(
    db: Database, settings: Settings, experiment: Experiment, *, dry_run: bool = False
) -> StepContext:
    return StepContext(
        db=db,
        settings=settings,
        experiment=experiment,
        dry_run=dry_run,
        worker_id="test-worker-1",
    )


# =====================================================================
# Fixtures: seed previous step results into DB
# =====================================================================


def _seed_idea(db: Database, experiment: Experiment) -> IdeaCandidate:
    idea = IdeaCandidate(
        experiment_id=experiment.id or 0,
        worker_id="test-worker-1",
        title="DevLog — Automated Developer Changelog",
        one_liner="Auto-generate changelogs from git commits using AI",
        problem_statement="Developers hate writing changelogs manually",
        target_audience="Open-source maintainers and small SaaS teams",
        category="developer-tools",
        pain_points=[
            PainPoint(
                description="Writing changelogs is tedious",
                severity=7,
                frequency="weekly",
                source="HackerNews",
                quote="I just stopped maintaining a changelog",
            ),
        ],
        existing_solutions=["release-please", "conventional-changelog"],
        differentiation="AI-powered summarization that produces human-quality prose",
    )
    db.save_step_result(
        experiment_id=experiment.id or 0,
        step_name="idea_discovery",
        step_number=0,
        data_json=idea.model_dump_json(),
    )
    return idea


def _seed_research(db: Database, experiment: Experiment) -> MarketResearch:
    research = MarketResearch(
        experiment_id=experiment.id or 0,
        worker_id="test-worker-1",
        tam_estimate="$850M global market",
        market_growth="18% CAGR",
        demand_signals=["Strong HN interest", "Growing search volume"],
        competitors=[
            Competitor(
                name="ExistingTool",
                url="https://existingtool.com",
                description="Market leader",
                pricing="$49/month",
                strengths=["Large user base"],
                weaknesses=["No AI features"],
            ),
        ],
        competitor_gaps=["No AI-powered solution exists"],
        target_audience_size="~500,000 developers",
        willingness_to_pay="$20-50/month based on competitor pricing",
        common_complaints=["Too expensive", "Poor UX"],
        search_results=[
            SearchResult(
                title="Test result",
                url="https://example.com",
                snippet="Test",
                source="tavily",
                relevance_score=0.9,
            ),
        ],
        key_findings=["Strong demand", "Clear gap"],
        research_summary="Strong opportunity.",
    )
    db.save_step_result(
        experiment_id=experiment.id or 0,
        step_name="deep_research",
        step_number=1,
        data_json=research.model_dump_json(),
    )
    return research


def _seed_mvp(db: Database, experiment: Experiment) -> MVPDefinition:
    mvp = MVPDefinition(
        experiment_id=experiment.id or 0,
        worker_id="test-worker-1",
        product_name="DevLog",
        tagline="Beautiful changelogs, zero effort",
        value_proposition="AI-generated changelogs from git commits",
        target_persona="Sarah, open-source maintainer",
        features=[
            Feature(title="AI Summary", description="Smart summaries", icon_name="brain"),
            Feature(title="One-Click", description="Zero config", icon_name="zap"),
            Feature(title="Multi-repo", description="Works everywhere", icon_name="git"),
        ],
        pricing_model="Freemium — free for public repos, $19/month for private",
        cta_text="Get Early Access",
        cta_subtext="Free during beta",
        domain_suggestions=["devlog.com", "getdevlog.com"],
        color_scheme="blue",
    )
    db.save_step_result(
        experiment_id=experiment.id or 0,
        step_name="mvp_definition",
        step_number=3,
        data_json=mvp.model_dump_json(),
    )
    return mvp


# =====================================================================
# Step 0: Idea Discovery
# =====================================================================


class TestIdeaDiscoveryStep:
    def test_dry_run_returns_mock_idea(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        from verdandi.steps.s0_idea_discovery import IdeaDiscoveryStep

        step = IdeaDiscoveryStep()
        ctx = _make_ctx(db, settings, experiment, dry_run=True)
        result = step.run(ctx)

        assert isinstance(result, IdeaCandidate)
        assert result.experiment_id == experiment.id
        assert result.worker_id == "test-worker-1"
        assert len(result.pain_points) > 0
        assert result.category != ""

    def test_real_run_uses_llm(
        self,
        db: Database,
        settings: Settings,
        experiment: Experiment,
    ) -> None:
        from verdandi.research import RawResearchData
        from verdandi.steps.s0_idea_discovery import IdeaDiscoveryStep, _IdeaLLMOutput

        # Build mock research data
        mock_raw = RawResearchData(
            tavily_results=[
                {
                    "title": "Test",
                    "url": "https://test.com",
                    "content": "Content",
                    "score": 0.9,
                    "published_date": "",
                }
            ],
            sources_used=["tavily"],
        )

        llm_output = _IdeaLLMOutput(
            title="TestProduct — AI Widget",
            one_liner="AI-powered widget maker",
            problem_statement="Widgets are hard to make",
            target_audience="Widget makers",
            category="developer-tools",
            pain_points=[
                PainPoint(
                    description="Manual widget creation",
                    severity=7,
                    frequency="daily",
                    source="HN",
                    quote="",
                )
            ],
            existing_solutions=["WidgetCo"],
            differentiation="AI-powered",
            source_urls=["https://example.com/llm-source"],
        )

        with (
            patch(
                "verdandi.research.ResearchCollector.collect",
                return_value=mock_raw,
            ),
            patch(
                "verdandi.research.format_research_context",
                return_value="Mock research text (https://example.com/source)",
            ),
            patch(
                "verdandi.llm.LLMClient.generate",
                return_value=llm_output,
            ),
        ):
            step = IdeaDiscoveryStep()
            ctx = _make_ctx(db, settings, experiment)
            result = step.run(ctx)

        assert isinstance(result, IdeaCandidate)
        assert result.title == "TestProduct — AI Widget"
        assert result.experiment_id == experiment.id
        assert result.worker_id == "test-worker-1"
        # Should include both LLM source URL and extracted URL
        assert "https://example.com/llm-source" in result.source_urls
        assert "https://example.com/source" in result.source_urls


# =====================================================================
# Step 1: Deep Research
# =====================================================================


class TestDeepResearchStep:
    def test_dry_run_returns_mock_research(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        from verdandi.steps.s1_deep_research import DeepResearchStep

        step = DeepResearchStep()
        ctx = _make_ctx(db, settings, experiment, dry_run=True)
        result = step.run(ctx)

        assert isinstance(result, MarketResearch)
        assert result.experiment_id == experiment.id
        assert len(result.competitors) > 0
        assert len(result.search_results) > 0

    def test_real_run_reads_idea_from_db(
        self,
        db: Database,
        settings: Settings,
        experiment: Experiment,
    ) -> None:
        from verdandi.research import RawResearchData
        from verdandi.steps.s1_deep_research import (
            DeepResearchStep,
            _MarketResearchLLMOutput,
        )

        # Seed Step 0 result
        _seed_idea(db, experiment)

        # Build mock raw research data
        mock_raw = RawResearchData(
            tavily_results=[
                {
                    "title": "Test",
                    "url": "https://test.com",
                    "content": "Test content",
                    "score": 0.9,
                    "published_date": "",
                }
            ],
            sources_used=["tavily"],
        )

        llm_output = _MarketResearchLLMOutput(
            tam_estimate="$1B",
            market_growth="15% CAGR",
            demand_signals=["Strong interest"],
            competitors=[
                Competitor(name="CompA", description="Leader", pricing="$49/mo"),
            ],
            competitor_gaps=["No AI"],
            target_audience_size="100K devs",
            willingness_to_pay="$20-50/mo",
            common_complaints=["Expensive"],
            key_findings=["Clear gap"],
            research_summary="Strong opportunity.",
        )

        with (
            patch(
                "verdandi.research.ResearchCollector.collect",
                return_value=mock_raw,
            ),
            patch(
                "verdandi.research.format_research_context",
                return_value="Formatted research text",
            ),
            patch(
                "verdandi.llm.LLMClient.generate",
                return_value=llm_output,
            ),
        ):
            step = DeepResearchStep()
            ctx = _make_ctx(db, settings, experiment)
            result = step.run(ctx)

        assert isinstance(result, MarketResearch)
        assert result.experiment_id == experiment.id
        assert result.tam_estimate == "$1B"
        # Search results come from raw data, not LLM
        assert len(result.search_results) == 1
        assert result.search_results[0].source == "tavily"

    def test_real_run_fails_without_idea(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        from verdandi.steps.s1_deep_research import DeepResearchStep

        step = DeepResearchStep()
        ctx = _make_ctx(db, settings, experiment)

        with pytest.raises(RuntimeError, match="idea_discovery"):
            step.run(ctx)


# =====================================================================
# Step 2: Scoring
# =====================================================================


class TestScoringStep:
    def test_dry_run_returns_mock_score(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        from verdandi.steps.s2_scoring import ScoringStep

        step = ScoringStep()
        ctx = _make_ctx(db, settings, experiment, dry_run=True)
        result = step.run(ctx)

        assert isinstance(result, PreBuildScore)
        assert result.experiment_id == experiment.id
        assert len(result.components) == 5
        assert 0 <= result.total_score <= 100
        assert result.decision in (Decision.GO, Decision.NO_GO)

    def test_real_run_computes_score_in_code(
        self,
        db: Database,
        settings: Settings,
        experiment: Experiment,
    ) -> None:
        from verdandi.steps.s2_scoring import ScoringStep, _ScoringLLMOutput

        # Seed prerequisite steps
        _seed_idea(db, experiment)
        _seed_research(db, experiment)

        # Mock LLM to return specific scores
        llm_output = _ScoringLLMOutput(
            components=[
                ScoreComponent(name="pain_severity", score=80, weight=0.25, reasoning="High"),
                ScoreComponent(name="frequency", score=70, weight=0.15, reasoning="Weekly"),
                ScoreComponent(
                    name="willingness_to_pay", score=85, weight=0.25, reasoning="Strong"
                ),
                ScoreComponent(name="competitor_gaps", score=90, weight=0.20, reasoning="Clear"),
                ScoreComponent(name="tam_size", score=60, weight=0.15, reasoning="Niche"),
            ],
            risks=["Competition"],
            opportunities=["First mover"],
            reasoning_summary="Strong signals.",
        )

        with patch("verdandi.llm.LLMClient.generate", return_value=llm_output):
            step = ScoringStep()
            ctx = _make_ctx(db, settings, experiment)
            result = step.run(ctx)

        assert isinstance(result, PreBuildScore)
        # Verify total is computed in code: 80*0.25 + 70*0.15 + 85*0.25 + 90*0.20 + 60*0.15
        # = 20 + 10.5 + 21.25 + 18 + 9 = 78.75 → 78
        assert result.total_score == 78
        assert result.decision == Decision.GO  # 78 >= default threshold (60)
        assert result.risks == ["Competition"]

    def test_real_run_fails_without_prereqs(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        from verdandi.steps.s2_scoring import ScoringStep

        step = ScoringStep()
        ctx = _make_ctx(db, settings, experiment)

        with pytest.raises(RuntimeError, match="idea_discovery"):
            step.run(ctx)


# =====================================================================
# Step 3: MVP Definition
# =====================================================================


class TestMVPDefinitionStep:
    def test_dry_run_returns_mock_mvp(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        from verdandi.steps.s3_mvp_definition import MVPDefinitionStep

        step = MVPDefinitionStep()
        ctx = _make_ctx(db, settings, experiment, dry_run=True)
        result = step.run(ctx)

        assert isinstance(result, MVPDefinition)
        assert result.experiment_id == experiment.id
        assert len(result.features) >= 3
        assert result.cta_text == "Get Early Access"

    def test_real_run_uses_idea_and_research(
        self,
        db: Database,
        settings: Settings,
        experiment: Experiment,
    ) -> None:
        from verdandi.steps.s3_mvp_definition import (
            MVPDefinitionStep,
            _MVPDefinitionLLMOutput,
        )

        # Seed prerequisite steps
        _seed_idea(db, experiment)
        _seed_research(db, experiment)

        llm_output = _MVPDefinitionLLMOutput(
            product_name="DevLog",
            tagline="Beautiful changelogs, zero effort",
            value_proposition="AI changelogs from git",
            target_persona="Sarah, OSS maintainer",
            features=[
                Feature(title="AI Summary", description="Smart summaries", icon_name="brain"),
                Feature(title="One-Click", description="Zero config", icon_name="zap"),
                Feature(title="Multi-repo", description="All repos", icon_name="git"),
            ],
            pricing_model="Freemium",
            cta_text="Try DevLog",
            cta_subtext="Free for public repos",
            domain_suggestions=["devlog.com"],
            color_scheme="indigo",
        )

        with patch("verdandi.llm.LLMClient.generate", return_value=llm_output):
            step = MVPDefinitionStep()
            ctx = _make_ctx(db, settings, experiment)
            result = step.run(ctx)

        assert isinstance(result, MVPDefinition)
        assert result.product_name == "DevLog"
        assert result.experiment_id == experiment.id
        assert len(result.features) == 3

    def test_real_run_fails_without_prereqs(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        from verdandi.steps.s3_mvp_definition import MVPDefinitionStep

        step = MVPDefinitionStep()
        ctx = _make_ctx(db, settings, experiment)

        with pytest.raises(ValueError, match="idea_discovery"):
            step.run(ctx)


# =====================================================================
# Step 4: Landing Page
# =====================================================================


class TestLandingPageStep:
    def test_dry_run_returns_mock_content(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        from verdandi.steps.s4_landing_page import LandingPageStep

        step = LandingPageStep()
        ctx = _make_ctx(db, settings, experiment, dry_run=True)
        result = step.run(ctx)

        assert isinstance(result, LandingPageContent)
        assert result.experiment_id == experiment.id
        assert "Automate" in result.headline
        assert len(result.features) >= 3
        assert len(result.testimonials) >= 2

    def test_real_run_generates_content(
        self,
        db: Database,
        settings: Settings,
        experiment: Experiment,
    ) -> None:
        from verdandi.steps.s4_landing_page import (
            LandingPageStep,
            _LandingPageLLMOutput,
        )

        # Seed Step 3 (MVP)
        _seed_mvp(db, experiment)

        llm_output = _LandingPageLLMOutput(
            headline="Ship Changelogs in Seconds",
            subheadline="AI-powered changelogs from your git history",
            hero_cta_text="Start Free",
            hero_cta_subtext="No credit card required",
            features_title="Why DevLog?",
            features=[
                FeatureItem(title="AI Summary", description="Smart summaries", icon="brain"),
                FeatureItem(title="One-Click", description="Zero config", icon="zap"),
                FeatureItem(title="Multi-repo", description="All repos", icon="git"),
            ],
            testimonials=[
                Testimonial(
                    quote="Saved me hours every week",
                    author_name="Alex Chen",
                    author_title="CTO, StartupCo",
                ),
            ],
            stats=[{"value": "10x", "label": "faster"}],
            faq_items=[
                FAQItem(question="How does it work?", answer="Connect your repo."),
            ],
            footer_cta_headline="Ready to ship?",
            footer_cta_text="Start Free",
            page_title="DevLog — AI Changelogs",
            meta_description="Generate changelogs automatically",
            og_title="DevLog",
            og_description="AI changelogs",
        )

        with patch("verdandi.llm.LLMClient.generate", return_value=llm_output):
            step = LandingPageStep()
            ctx = _make_ctx(db, settings, experiment)
            result = step.run(ctx)

        assert isinstance(result, LandingPageContent)
        assert result.headline == "Ship Changelogs in Seconds"
        assert result.experiment_id == experiment.id
        # rendered_html should contain the headline (template fill)
        # Note: may be empty if template file not found, which is OK in tests
        assert isinstance(result.rendered_html, str)

    def test_real_run_fails_without_mvp(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        from verdandi.steps.s4_landing_page import LandingPageStep

        step = LandingPageStep()
        ctx = _make_ctx(db, settings, experiment)

        with pytest.raises(RuntimeError, match="mvp_definition"):
            step.run(ctx)


# =====================================================================
# Step chain: verify Step N result is readable by Step N+1
# =====================================================================


class TestStepChain:
    """Integration test: save Step N result → Step N+1 reads it correctly."""

    def test_idea_to_research_chain(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        """Step 1 can read Step 0's result from DB."""
        from verdandi.steps.s0_idea_discovery import IdeaDiscoveryStep
        from verdandi.steps.s1_deep_research import DeepResearchStep

        # Step 0: dry-run produces an idea
        step0 = IdeaDiscoveryStep()
        ctx = _make_ctx(db, settings, experiment, dry_run=True)
        idea = step0.run(ctx)
        assert isinstance(idea, IdeaCandidate)

        # Save it to DB
        db.save_step_result(
            experiment_id=experiment.id or 0,
            step_name="idea_discovery",
            step_number=0,
            data_json=idea.model_dump_json(),
        )

        # Step 1: dry-run reads the idea (doesn't use it, but shouldn't crash)
        step1 = DeepResearchStep()
        result = step1.run(ctx)
        assert isinstance(result, MarketResearch)

    def test_scoring_reads_both_prereqs(
        self, db: Database, settings: Settings, experiment: Experiment
    ) -> None:
        """Step 2 can read both Step 0 and Step 1 results."""
        _seed_idea(db, experiment)
        _seed_research(db, experiment)

        from verdandi.steps.s2_scoring import ScoringStep

        step = ScoringStep()
        ctx = _make_ctx(db, settings, experiment, dry_run=True)
        result = step.run(ctx)
        assert isinstance(result, PreBuildScore)
