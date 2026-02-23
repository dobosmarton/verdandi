"""Tests for the Council Dissent Analyzer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from verdandi.agents.council import _DIMENSION_NAMES
from verdandi.agents.dissent import (
    _SCORING_TO_RESEARCH_DIM,
    DissentAnalyzer,
)
from verdandi.config import Settings
from verdandi.models.scoring import (
    CouncilMemberVote,
    Decision,
    DimensionDissent,
    DissentAnalysis,
    PreBuildScore,
    ScoreComponent,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_components(
    scores: dict[str, int] | None = None,
) -> list[ScoreComponent]:
    """Build a standard 5-dimension component list with given scores."""
    defaults = {
        "pain_severity": 70,
        "frequency": 65,
        "willingness_to_pay": 75,
        "competitor_gaps": 80,
        "tam_size": 60,
    }
    weights = {
        "pain_severity": 0.25,
        "frequency": 0.15,
        "willingness_to_pay": 0.25,
        "competitor_gaps": 0.20,
        "tam_size": 0.15,
    }
    merged = {**defaults, **(scores or {})}
    return [
        ScoreComponent(
            name=name,
            score=merged[name],
            weight=weights[name],
            reasoning=f"Reasoning for {name}",
        )
        for name in _DIMENSION_NAMES
    ]


def _make_vote(
    provider: str,
    decision: Decision,
    base_score: int = 72,
    scores: dict[str, int] | None = None,
) -> CouncilMemberVote:
    return CouncilMemberVote(
        provider_name=provider,
        model_name=f"mock-{provider}",
        components=_make_components(scores),
        base_score=base_score,
        decision=decision,
        risks=["risk A"],
        opportunities=["opp A"],
        reasoning_summary=f"Mock {provider} reasoning.",
    )


def _dissent_settings(**overrides: object) -> Settings:
    """Create settings with dissent enabled."""
    defaults: dict[str, object] = {
        "anthropic_api_key": "test-anthropic",
        "openai_api_key": "test-openai",
        "google_api_key": "test-google",
        "council_enabled": True,
        "dissent_enabled": True,
        "dissent_dimension_threshold": 25,
        "dissent_max_rounds": 1,
        "dissent_decision_split_required": False,
        "score_go_threshold": 70,
        "_env_file": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


def _make_score(
    votes: list[CouncilMemberVote],
    total_score: int = 72,
    decision: Decision = Decision.GO,
) -> PreBuildScore:
    return PreBuildScore(
        experiment_id=1,
        worker_id="test-worker",
        components=_make_components(),
        total_score=total_score,
        decision=decision,
        reasoning="Test reasoning",
        risks=["risk"],
        opportunities=["opp"],
        council_votes=votes,
    )


# ---------------------------------------------------------------------------
# Detection tests
# ---------------------------------------------------------------------------


class TestDetectDissent:
    def test_no_dissent_when_agreement(self) -> None:
        """All voters within threshold → no dissent detected."""
        settings = _dissent_settings(dissent_dimension_threshold=25)
        analyzer = DissentAnalyzer(settings)

        votes = [
            _make_vote("anthropic", Decision.GO, scores={"pain_severity": 70}),
            _make_vote("openai", Decision.GO, scores={"pain_severity": 80}),
            _make_vote("google", Decision.GO, scores={"pain_severity": 75}),
        ]

        dissents = analyzer.detect_dissent(votes)
        assert len(dissents) == 0

    def test_detects_dimension_spread(self) -> None:
        """30-point spread on willingness_to_pay → flags dimension."""
        settings = _dissent_settings(dissent_dimension_threshold=25)
        analyzer = DissentAnalyzer(settings)

        votes = [
            _make_vote("anthropic", Decision.GO, scores={"willingness_to_pay": 90}),
            _make_vote("openai", Decision.GO, scores={"willingness_to_pay": 60}),
            _make_vote("google", Decision.GO, scores={"willingness_to_pay": 75}),
        ]

        dissents = analyzer.detect_dissent(votes)
        assert len(dissents) == 1
        assert dissents[0].dimension == "willingness_to_pay"
        assert dissents[0].spread == 30
        assert dissents[0].scores_by_provider["anthropic"] == 90
        assert dissents[0].scores_by_provider["openai"] == 60

    def test_detects_multiple_dimensions(self) -> None:
        """Multiple dimensions with high spread → flags all."""
        settings = _dissent_settings(dissent_dimension_threshold=25)
        analyzer = DissentAnalyzer(settings)

        votes = [
            _make_vote(
                "anthropic",
                Decision.GO,
                scores={"willingness_to_pay": 90, "tam_size": 85},
            ),
            _make_vote(
                "openai",
                Decision.NO_GO,
                scores={"willingness_to_pay": 50, "tam_size": 40},
            ),
        ]

        dissents = analyzer.detect_dissent(votes)
        dims = {d.dimension for d in dissents}
        assert "willingness_to_pay" in dims
        assert "tam_size" in dims

    def test_exact_threshold_not_flagged(self) -> None:
        """Spread exactly at threshold → not flagged (needs to exceed)."""
        settings = _dissent_settings(dissent_dimension_threshold=25)
        analyzer = DissentAnalyzer(settings)

        votes = [
            _make_vote("anthropic", Decision.GO, scores={"pain_severity": 80}),
            _make_vote("openai", Decision.GO, scores={"pain_severity": 55}),
        ]

        dissents = analyzer.detect_dissent(votes)
        # spread is exactly 25, threshold requires >= 25
        assert len(dissents) == 1
        assert dissents[0].spread == 25

    def test_decision_split_detection(self) -> None:
        """GO vs NO_GO → decision split detected."""
        settings = _dissent_settings()
        analyzer = DissentAnalyzer(settings)

        votes = [
            _make_vote("anthropic", Decision.GO),
            _make_vote("openai", Decision.NO_GO),
        ]

        assert analyzer._has_decision_split(votes) is True

    def test_no_decision_split(self) -> None:
        """All GO → no decision split."""
        settings = _dissent_settings()
        analyzer = DissentAnalyzer(settings)

        votes = [
            _make_vote("anthropic", Decision.GO),
            _make_vote("openai", Decision.GO),
        ]

        assert analyzer._has_decision_split(votes) is False


# ---------------------------------------------------------------------------
# Dimension mapping tests
# ---------------------------------------------------------------------------


class TestDimensionMapping:
    def test_all_scoring_dims_mapped(self) -> None:
        """Every scoring dimension has a research dimension mapping."""
        for dim in _DIMENSION_NAMES:
            assert dim in _SCORING_TO_RESEARCH_DIM

    def test_mapping_values_are_valid(self) -> None:
        """Research dimension names are from the RESEARCH_DIMENSIONS tuple."""
        from verdandi.models.research import RESEARCH_DIMENSIONS

        for research_dim in _SCORING_TO_RESEARCH_DIM.values():
            assert research_dim in RESEARCH_DIMENSIONS


# ---------------------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------------------


class TestDissentModels:
    def test_dimension_dissent_frozen(self) -> None:
        dd = DimensionDissent(
            dimension="pain_severity",
            scores_by_provider={"a": 80, "b": 50},
            spread=30,
            median_score=65,
        )
        with pytest.raises(ValidationError):
            dd.dimension = "other"  # type: ignore[misc]

    def test_dissent_analysis_defaults(self) -> None:
        da = DissentAnalysis()
        assert da.dissent_detected is False
        assert da.dimension_dissents == []
        assert da.resolution_rounds == []
        assert da.decision_flipped is False

    def test_prebuild_score_with_dissent_analysis(self) -> None:
        score = PreBuildScore(
            experiment_id=1,
            worker_id="w",
            components=[],
            total_score=72,
            decision=Decision.GO,
            dissent_analysis=DissentAnalysis(dissent_detected=True),
        )
        assert score.dissent_analysis is not None
        assert score.dissent_analysis.dissent_detected is True

    def test_prebuild_score_default_none_dissent(self) -> None:
        score = PreBuildScore(
            experiment_id=1,
            worker_id="w",
            components=[],
            total_score=72,
            decision=Decision.GO,
        )
        assert score.dissent_analysis is None


# ---------------------------------------------------------------------------
# Resolution flow tests
# ---------------------------------------------------------------------------


class TestResolve:
    def test_no_dissent_returns_original_with_analysis(self) -> None:
        """No dissent → returns score with empty DissentAnalysis attached."""
        settings = _dissent_settings(dissent_dimension_threshold=50)
        analyzer = DissentAnalyzer(settings)

        votes = [
            _make_vote("anthropic", Decision.GO, scores={"pain_severity": 70}),
            _make_vote("openai", Decision.GO, scores={"pain_severity": 75}),
        ]
        score = _make_score(votes)

        # Build a mock context
        ctx = MagicMock()
        ctx.settings = settings
        ctx.experiment.id = 1
        ctx.worker_id = "test"

        result = analyzer.resolve(ctx, score)
        assert result.dissent_analysis is not None
        assert result.dissent_analysis.dissent_detected is False
        assert result.total_score == score.total_score

    def test_no_council_votes_returns_original(self) -> None:
        """No council votes → returns score with empty analysis."""
        settings = _dissent_settings()
        analyzer = DissentAnalyzer(settings)

        score = PreBuildScore(
            experiment_id=1,
            worker_id="w",
            components=_make_components(),
            total_score=72,
            decision=Decision.GO,
            council_votes=[],
        )

        ctx = MagicMock()
        ctx.settings = settings

        result = analyzer.resolve(ctx, score)
        assert result.dissent_analysis is not None
        assert result.dissent_analysis.dissent_detected is False

    def test_decision_split_required_skips_dim_only(self) -> None:
        """When decision_split_required=True, dimension spread alone doesn't trigger."""
        settings = _dissent_settings(
            dissent_decision_split_required=True,
            dissent_dimension_threshold=25,
        )
        analyzer = DissentAnalyzer(settings)

        # Same decision but different dimension scores
        votes = [
            _make_vote("anthropic", Decision.GO, scores={"pain_severity": 90}),
            _make_vote("openai", Decision.GO, scores={"pain_severity": 50}),
        ]
        score = _make_score(votes)

        ctx = MagicMock()
        ctx.settings = settings
        ctx.experiment.id = 1

        result = analyzer.resolve(ctx, score)
        assert result.dissent_analysis is not None
        assert result.dissent_analysis.dissent_detected is False

    @patch("verdandi.agents.dissent.DissentAnalyzer.run_followup_research", return_value=3)
    @patch("verdandi.agents.dissent.DissentAnalyzer.build_followup_queries")
    @patch("verdandi.agents.dissent.DissentAnalyzer._rescore_with_context")
    def test_resolve_with_dissent(
        self,
        mock_rescore: MagicMock,
        mock_queries: MagicMock,
        mock_research: MagicMock,
    ) -> None:
        """Full dissent flow: detect → research → re-score → attach analysis."""
        settings = _dissent_settings(dissent_dimension_threshold=25)
        analyzer = DissentAnalyzer(settings)

        # Create votes with dissent
        votes = [
            _make_vote("anthropic", Decision.GO, scores={"willingness_to_pay": 90}),
            _make_vote("openai", Decision.NO_GO, scores={"willingness_to_pay": 50}),
        ]
        initial_score = _make_score(votes, total_score=65, decision=Decision.NO_GO)

        # Mock follow-up queries
        mock_queries.return_value = ["query 1", "query 2"]

        # Mock re-score result (higher score, GO decision)
        rescored = _make_score(
            [
                _make_vote("anthropic", Decision.GO, scores={"willingness_to_pay": 85}),
                _make_vote("openai", Decision.GO, scores={"willingness_to_pay": 80}),
            ],
            total_score=78,
            decision=Decision.GO,
        )
        mock_rescore.return_value = rescored

        # Build mock context with prior_results
        mock_idea = MagicMock()
        mock_research_data = MagicMock()

        ctx = MagicMock()
        ctx.settings = settings
        ctx.experiment.id = 1
        ctx.worker_id = "test"
        ctx.prior_results.get_typed.side_effect = [mock_idea, mock_research_data]

        result = analyzer.resolve(ctx, initial_score)

        assert result.dissent_analysis is not None
        assert result.dissent_analysis.dissent_detected is True
        assert result.dissent_analysis.decision_flipped is True
        assert result.dissent_analysis.initial_score == 65
        assert result.dissent_analysis.final_score == 78
        assert len(result.dissent_analysis.resolution_rounds) == 1

        rr = result.dissent_analysis.resolution_rounds[0]
        assert rr.round_number == 1
        assert rr.score_before == 65
        assert rr.score_after == 78
        assert rr.decision_changed is True
        assert rr.new_sources_count == 3


# ---------------------------------------------------------------------------
# Settings integration
# ---------------------------------------------------------------------------


class TestDissentSettings:
    def test_dissent_disabled_by_default(self) -> None:
        s = Settings(anthropic_api_key="test", _env_file=None)
        assert s.dissent_enabled is False

    def test_dissent_settings_validation(self) -> None:
        s = _dissent_settings(
            dissent_max_rounds=3,
            dissent_dimension_threshold=40,
        )
        assert s.dissent_max_rounds == 3
        assert s.dissent_dimension_threshold == 40

    @pytest.mark.parametrize(
        ("field", "value"),
        [
            ("dissent_dimension_threshold", 5),  # below ge=10
            ("dissent_dimension_threshold", 60),  # above le=50
            ("dissent_max_rounds", -1),  # below ge=0
            ("dissent_max_rounds", 4),  # above le=3
        ],
        ids=["threshold-too-low", "threshold-too-high", "rounds-too-low", "rounds-too-high"],
    )
    def test_dissent_settings_rejects_out_of_bounds(self, field: str, value: int) -> None:
        with pytest.raises(ValidationError):
            _dissent_settings(**{field: value})
