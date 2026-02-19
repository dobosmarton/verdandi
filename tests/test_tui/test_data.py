"""Tests for verdandi.tui.data — data bridge between CliBackend and TUI."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from verdandi.models.experiment import Experiment, ExperimentStatus
from verdandi.tui.data import (
    STATUS_COLORS,
    ExperimentSummary,
    fetch_detail,
    fetch_summaries,
)


def _make_backend() -> MagicMock:
    """Create a mock CliBackend."""
    return MagicMock(
        spec=[
            "get_experiment",
            "list_experiments",
            "get_step_result",
            "get_all_step_results",
            "close",
        ]
    )


def _make_experiment(
    *,
    exp_id: int = 1,
    status: ExperimentStatus = ExperimentStatus.RUNNING,
    current_step: int = 2,
    idea_title: str = "Test Idea",
) -> Experiment:
    return Experiment(id=exp_id, status=status, current_step=current_step, idea_title=idea_title)


# --- ExperimentSummary tests ---


class TestFetchSummaries:
    def test_empty_list(self) -> None:
        backend = _make_backend()
        backend.list_experiments.return_value = []
        result = fetch_summaries(backend)
        assert result == []

    def test_basic_summary_without_scoring(self) -> None:
        """Experiment at step 0 should not try to fetch scoring."""
        backend = _make_backend()
        exp = _make_experiment(current_step=0, status=ExperimentStatus.PENDING)
        backend.list_experiments.return_value = [exp]

        summaries = fetch_summaries(backend)
        assert len(summaries) == 1
        s = summaries[0]
        assert s.id == 1
        assert s.status == "pending"
        assert s.status_color == "yellow"
        assert s.idea_title == "Test Idea"
        assert s.score is None
        assert s.decision is None
        # Should NOT have called get_step_result for pre-scoring experiments
        backend.get_step_result.assert_not_called()

    def test_summary_with_scoring(self) -> None:
        """Experiment at step >= 2 should fetch scoring data."""
        backend = _make_backend()
        exp = _make_experiment(current_step=3)
        backend.list_experiments.return_value = [exp]
        backend.get_step_result.return_value = {
            "id": 1,
            "experiment_id": 1,
            "step_name": "scoring",
            "step_number": 2,
            "data": {"total_score": 78, "decision": "go"},
            "worker_id": "w1",
            "created_at": "2026-01-01T00:00:00",
        }

        summaries = fetch_summaries(backend)
        s = summaries[0]
        assert s.score == 78
        assert s.decision == "go"
        backend.get_step_result.assert_called_once_with(1, "scoring")

    def test_summary_with_missing_scoring_step(self) -> None:
        """If scoring step doesn't exist yet, score/decision should be None."""
        backend = _make_backend()
        exp = _make_experiment(current_step=2)
        backend.list_experiments.return_value = [exp]
        backend.get_step_result.return_value = None

        summaries = fetch_summaries(backend)
        s = summaries[0]
        assert s.score is None
        assert s.decision is None

    def test_status_color_mapping(self) -> None:
        """All defined statuses should have a color mapping."""
        for status in ExperimentStatus:
            assert status.value in STATUS_COLORS, f"Missing color for {status.value}"

    def test_step_label_known_step(self) -> None:
        backend = _make_backend()
        exp = _make_experiment(current_step=1)
        backend.list_experiments.return_value = [exp]
        backend.get_step_result.return_value = None

        summaries = fetch_summaries(backend)
        assert summaries[0].step_label == "research"

    def test_step_label_unknown_step(self) -> None:
        backend = _make_backend()
        exp = _make_experiment(current_step=99)
        backend.list_experiments.return_value = [exp]
        backend.get_step_result.return_value = None

        summaries = fetch_summaries(backend)
        assert summaries[0].step_label == "step 99"

    def test_multiple_experiments(self) -> None:
        backend = _make_backend()
        exps = [
            _make_experiment(exp_id=1, current_step=0, status=ExperimentStatus.PENDING),
            _make_experiment(exp_id=2, current_step=4, status=ExperimentStatus.COMPLETED),
        ]
        backend.list_experiments.return_value = exps
        backend.get_step_result.return_value = {
            "id": 2,
            "experiment_id": 2,
            "step_name": "scoring",
            "step_number": 2,
            "data": {"total_score": 45, "decision": "iterate"},
            "worker_id": "w1",
            "created_at": "2026-01-01T00:00:00",
        }

        summaries = fetch_summaries(backend)
        assert len(summaries) == 2
        assert summaries[0].id == 1
        assert summaries[1].id == 2
        assert summaries[1].score == 45
        assert summaries[1].decision == "iterate"


# --- ExperimentDetail tests ---


class TestFetchDetail:
    def test_not_found(self) -> None:
        backend = _make_backend()
        backend.get_experiment.return_value = None

        result = fetch_detail(backend, 999)
        assert result is None

    def test_experiment_no_steps(self) -> None:
        """Experiment exists but no steps completed yet."""
        backend = _make_backend()
        backend.get_experiment.return_value = _make_experiment()
        backend.get_step_result.return_value = None
        backend.get_all_step_results.return_value = []

        result = fetch_detail(backend, 1)
        assert result is not None
        assert result.experiment.id == 1
        assert result.idea is None
        assert result.research is None
        assert result.score is None
        assert result.all_steps == []

    def test_experiment_with_idea(self) -> None:
        """Idea step completed — should reconstruct IdeaCandidate."""
        backend = _make_backend()
        backend.get_experiment.return_value = _make_experiment(current_step=1)
        backend.get_step_result.side_effect = lambda eid, step: {
            "idea_discovery": {
                "id": 1,
                "experiment_id": 1,
                "step_name": "idea_discovery",
                "step_number": 0,
                "data": {
                    "experiment_id": 1,
                    "step_name": "idea_discovery",
                    "title": "Test Idea",
                    "one_liner": "A short test idea",
                    "category": "dev_tools",
                    "target_audience": "developers",
                    "problem_statement": "Testing is hard",
                    "pain_points": [],
                    "existing_solutions": [],
                    "differentiation": "Better approach",
                    "novelty_score": 0.8,
                    "discovery_type": "disruption",
                    "source_urls": [],
                },
                "worker_id": "w1",
                "created_at": "2026-01-01T00:00:00",
            },
        }.get(step)
        backend.get_all_step_results.return_value = []

        result = fetch_detail(backend, 1)
        assert result is not None
        assert result.idea is not None
        assert result.idea.title == "Test Idea"
        assert result.idea.novelty_score == pytest.approx(0.8)
        assert result.research is None

    def test_detail_dataclass_is_frozen(self) -> None:
        backend = _make_backend()
        backend.get_experiment.return_value = _make_experiment()
        backend.get_step_result.return_value = None
        backend.get_all_step_results.return_value = []

        detail = fetch_detail(backend, 1)
        assert detail is not None
        with pytest.raises(AttributeError):
            detail.idea = None  # type: ignore[misc]

    def test_summary_dataclass_is_frozen(self) -> None:
        s = ExperimentSummary(
            id=1,
            status="running",
            status_color="cyan",
            idea_title="Test",
            current_step=0,
            step_label="discovery",
            score=None,
            decision=None,
        )
        with pytest.raises(AttributeError):
            s.id = 2  # type: ignore[misc]
