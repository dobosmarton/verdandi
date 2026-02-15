"""Tests for the Agent Council multi-model scoring."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from verdandi.agents.council import _DIMENSION_NAMES, AgentCouncil
from verdandi.config import Settings
from verdandi.models.scoring import (
    CouncilMemberVote,
    CouncilResult,
    Decision,
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
    risks: list[str] | None = None,
    opportunities: list[str] | None = None,
) -> CouncilMemberVote:
    return CouncilMemberVote(
        provider_name=provider,
        model_name=f"mock-{provider}",
        components=_make_components(scores),
        base_score=base_score,
        decision=decision,
        risks=risks or ["risk A"],
        opportunities=opportunities or ["opp A"],
        reasoning_summary=f"Mock {provider} reasoning.",
    )


def _council_settings(**overrides: object) -> Settings:
    """Create settings with council enabled and all 3 provider keys."""
    defaults: dict[str, object] = {
        "anthropic_api_key": "test-anthropic",
        "openai_api_key": "test-openai",
        "google_api_key": "test-google",
        "council_enabled": True,
        "score_go_threshold": 70,
        "_env_file": None,
    }
    defaults.update(overrides)
    return Settings(**defaults)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# CouncilMemberVote & CouncilResult model tests
# ---------------------------------------------------------------------------

class TestCouncilModels:
    def test_vote_creation(self):
        vote = _make_vote("anthropic", Decision.GO)
        assert vote.provider_name == "anthropic"
        assert vote.decision == Decision.GO
        assert len(vote.components) == 5

    def test_vote_frozen(self):
        vote = _make_vote("openai", Decision.NO_GO)
        with pytest.raises(ValidationError):
            vote.provider_name = "changed"  # type: ignore[misc]

    def test_vote_serialization_roundtrip(self):
        vote = _make_vote("google", Decision.GO, base_score=80)
        json_str = vote.model_dump_json()
        restored = CouncilMemberVote.model_validate_json(json_str)
        assert restored.provider_name == "google"
        assert restored.base_score == 80
        assert restored.decision == Decision.GO

    def test_prebuild_score_with_council_votes(self):
        votes = [
            _make_vote("anthropic", Decision.GO),
            _make_vote("openai", Decision.GO),
            _make_vote("google", Decision.NO_GO),
        ]
        score = PreBuildScore(
            experiment_id=1,
            total_score=75,
            decision=Decision.GO,
            council_votes=votes,
        )
        assert len(score.council_votes) == 3
        assert score.council_votes[0].provider_name == "anthropic"

    def test_prebuild_score_without_council_votes(self):
        """Backwards compatibility: council_votes defaults to empty list."""
        score = PreBuildScore(
            experiment_id=1,
            total_score=60,
            decision=Decision.NO_GO,
        )
        assert score.council_votes == []

    def test_prebuild_score_roundtrip_with_votes(self):
        """JSON roundtrip preserves council votes."""
        votes = [_make_vote("anthropic", Decision.GO)]
        score = PreBuildScore(
            experiment_id=1,
            total_score=75,
            decision=Decision.GO,
            council_votes=votes,
        )
        json_str = score.model_dump_json()
        restored = PreBuildScore.model_validate_json(json_str)
        assert len(restored.council_votes) == 1
        assert restored.council_votes[0].provider_name == "anthropic"

    def test_prebuild_score_old_data_without_council_field(self):
        """Old serialized data without council_votes still deserializes."""
        old_data = {
            "experiment_id": 1,
            "step_name": "scoring",
            "total_score": 65,
            "decision": "no_go",
            "worker_id": "w1",
        }
        score = PreBuildScore.model_validate(old_data)
        assert score.council_votes == []
        assert score.total_score == 65


# ---------------------------------------------------------------------------
# Aggregation logic tests
# ---------------------------------------------------------------------------

class TestAggregation:
    def _aggregate(
        self,
        votes: list[CouncilMemberVote],
        novelty_score: float = 0.0,
        threshold: int = 70,
    ) -> CouncilResult:
        settings = _council_settings()
        council = AgentCouncil(settings)
        return council._aggregate(votes, novelty_score, threshold)

    def test_all_go_majority(self):
        votes = [
            _make_vote("anthropic", Decision.GO, base_score=75),
            _make_vote("openai", Decision.GO, base_score=80),
            _make_vote("google", Decision.GO, base_score=72),
        ]
        result = self._aggregate(votes)
        assert result.decision == Decision.GO

    def test_all_nogo_majority(self):
        votes = [
            _make_vote("anthropic", Decision.NO_GO, base_score=50),
            _make_vote("openai", Decision.NO_GO, base_score=55),
            _make_vote("google", Decision.NO_GO, base_score=45),
        ]
        result = self._aggregate(votes)
        assert result.decision == Decision.NO_GO

    def test_two_go_one_nogo_majority(self):
        votes = [
            _make_vote("anthropic", Decision.GO, base_score=75),
            _make_vote("openai", Decision.GO, base_score=72),
            _make_vote("google", Decision.NO_GO, base_score=50),
        ]
        result = self._aggregate(votes)
        assert result.decision == Decision.GO

    def test_one_go_two_nogo_majority(self):
        votes = [
            _make_vote("anthropic", Decision.GO, base_score=75),
            _make_vote("openai", Decision.NO_GO, base_score=55),
            _make_vote("google", Decision.NO_GO, base_score=50),
        ]
        result = self._aggregate(votes)
        assert result.decision == Decision.NO_GO

    def test_two_providers_both_must_agree(self):
        """With 2 providers, majority is ceil(2/2)=1 so 1 GO suffices."""
        votes = [
            _make_vote("anthropic", Decision.GO, base_score=75),
            _make_vote("openai", Decision.NO_GO, base_score=55),
        ]
        result = self._aggregate(votes)
        assert result.decision == Decision.GO

    def test_two_providers_both_nogo(self):
        votes = [
            _make_vote("anthropic", Decision.NO_GO, base_score=50),
            _make_vote("openai", Decision.NO_GO, base_score=55),
        ]
        result = self._aggregate(votes)
        assert result.decision == Decision.NO_GO

    def test_median_score_odd(self):
        """Median of 3 scores picks the middle value."""
        votes = [
            _make_vote("a", Decision.GO, scores={"pain_severity": 60}),
            _make_vote("b", Decision.GO, scores={"pain_severity": 80}),
            _make_vote("c", Decision.GO, scores={"pain_severity": 90}),
        ]
        result = self._aggregate(votes)
        pain = next(c for c in result.aggregated_components if c.name == "pain_severity")
        assert pain.score == 80  # median of [60, 80, 90]

    def test_median_score_even(self):
        """Median of 2 scores picks the upper value (integer division)."""
        votes = [
            _make_vote("a", Decision.GO, scores={"pain_severity": 60}),
            _make_vote("b", Decision.GO, scores={"pain_severity": 80}),
        ]
        result = self._aggregate(votes)
        pain = next(c for c in result.aggregated_components if c.name == "pain_severity")
        assert pain.score == 80  # sorted [60, 80], mid=1 -> 80

    def test_novelty_bonus_applied(self):
        votes = [
            _make_vote("a", Decision.GO, base_score=70, scores={"pain_severity": 70}),
        ]
        result_no_novelty = self._aggregate(votes, novelty_score=0.0)
        result_with_novelty = self._aggregate(votes, novelty_score=1.0)
        assert result_with_novelty.total_score > result_no_novelty.total_score

    def test_total_score_capped_at_100(self):
        votes = [
            _make_vote(
                "a",
                Decision.GO,
                scores={
                    "pain_severity": 100,
                    "frequency": 100,
                    "willingness_to_pay": 100,
                    "competitor_gaps": 100,
                    "tam_size": 100,
                },
            ),
        ]
        result = self._aggregate(votes, novelty_score=1.0)
        assert result.total_score <= 100

    def test_risk_deduplication(self):
        votes = [
            _make_vote("a", Decision.GO, risks=["Crowded market", "High costs"]),
            _make_vote("b", Decision.GO, risks=["crowded market", "Scalability"]),
        ]
        result = self._aggregate(votes)
        risk_lower = [r.lower().strip() for r in result.aggregated_risks]
        # "crowded market" should appear only once
        assert risk_lower.count("crowded market") == 1
        assert len(result.aggregated_risks) == 3

    def test_opportunity_deduplication(self):
        votes = [
            _make_vote("a", Decision.GO, opportunities=["First-mover"]),
            _make_vote("b", Decision.GO, opportunities=["first-mover", "New market"]),
        ]
        result = self._aggregate(votes)
        opp_lower = [o.lower().strip() for o in result.aggregated_opportunities]
        assert opp_lower.count("first-mover") == 1

    def test_reasoning_contains_all_providers(self):
        votes = [
            _make_vote("anthropic", Decision.GO, base_score=75),
            _make_vote("openai", Decision.NO_GO, base_score=55),
        ]
        result = self._aggregate(votes)
        assert "anthropic" in result.reasoning
        assert "openai" in result.reasoning

    def test_all_five_dimensions_aggregated(self):
        votes = [_make_vote("a", Decision.GO)]
        result = self._aggregate(votes)
        dim_names = {c.name for c in result.aggregated_components}
        assert dim_names == set(_DIMENSION_NAMES)


# ---------------------------------------------------------------------------
# Provider discovery tests
# ---------------------------------------------------------------------------

class TestProviderDiscovery:
    def test_all_three_providers(self):
        settings = _council_settings()
        council = AgentCouncil(settings)
        providers = council._discover_available_providers()
        names = [name for name, _ in providers]
        assert names == ["anthropic", "openai", "google"]

    def test_two_providers(self):
        settings = _council_settings(google_api_key="")
        council = AgentCouncil(settings)
        providers = council._discover_available_providers()
        names = [name for name, _ in providers]
        assert names == ["anthropic", "openai"]

    def test_one_provider(self):
        settings = _council_settings(openai_api_key="", google_api_key="")
        council = AgentCouncil(settings)
        providers = council._discover_available_providers()
        assert len(providers) == 1

    def test_no_providers(self):
        settings = _council_settings(
            anthropic_api_key="", openai_api_key="", google_api_key=""
        )
        council = AgentCouncil(settings)
        providers = council._discover_available_providers()
        assert len(providers) == 0


# ---------------------------------------------------------------------------
# Config integration tests
# ---------------------------------------------------------------------------

class TestCouncilConfig:
    def test_council_disabled_by_default(self):
        settings = Settings(anthropic_api_key="test", _env_file=None)
        assert settings.council_enabled is False

    def test_council_enabled(self):
        settings = _council_settings()
        assert settings.council_enabled is True

    def test_default_models(self):
        settings = _council_settings()
        assert settings.openai_model == "gpt-4o"
        assert settings.google_model == "gemini-2.5-flash"
