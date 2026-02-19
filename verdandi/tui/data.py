"""Data bridge between CliBackend and TUI display models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from verdandi.db import StepResultDict
    from verdandi.models.experiment import Experiment
    from verdandi.models.idea import IdeaCandidate
    from verdandi.models.research import MarketResearch
    from verdandi.models.scoring import PreBuildScore
    from verdandi.protocols import CliBackend

STATUS_COLORS: dict[str, str] = {
    "pending": "yellow",
    "running": "cyan",
    "awaiting_review": "magenta",
    "approved": "green",
    "rejected": "red",
    "completed": "green",
    "failed": "red",
    "archived": "dim",
    "no_go": "red",
}

STEP_NAMES: dict[int, str] = {
    0: "discovery",
    1: "research",
    2: "scoring",
    3: "mvp",
    4: "landing page",
    5: "review",
    6: "domain",
    7: "deploy",
    8: "analytics",
    9: "distribution",
    10: "monitor",
}


@dataclass(frozen=True)
class ExperimentSummary:
    """Row data for the list view."""

    id: int
    status: str
    status_color: str
    idea_title: str
    current_step: int
    step_label: str
    score: int | None
    decision: str | None


@dataclass(frozen=True)
class ExperimentDetail:
    """All data needed for the detail view."""

    experiment: Experiment
    idea: IdeaCandidate | None
    research: MarketResearch | None
    score: PreBuildScore | None
    all_steps: list[StepResultDict]


def fetch_summaries(backend: CliBackend) -> list[ExperimentSummary]:
    """Fetch all experiments with optional score/decision for the list view."""
    experiments = backend.list_experiments()
    summaries: list[ExperimentSummary] = []
    for exp in experiments:
        score_val: int | None = None
        decision_val: str | None = None
        if exp.id is not None and exp.current_step >= 2:
            scoring = backend.get_step_result(exp.id, "scoring")
            if scoring and isinstance(scoring["data"], dict):
                raw_score = scoring["data"].get("total_score")
                if isinstance(raw_score, int):
                    score_val = raw_score
                raw_dec = scoring["data"].get("decision")
                if isinstance(raw_dec, str):
                    decision_val = raw_dec
        summaries.append(
            ExperimentSummary(
                id=exp.id or 0,
                status=exp.status.value,
                status_color=STATUS_COLORS.get(exp.status.value, "white"),
                idea_title=exp.idea_title,
                current_step=exp.current_step,
                step_label=STEP_NAMES.get(exp.current_step, f"step {exp.current_step}"),
                score=score_val,
                decision=decision_val,
            )
        )
    return summaries


def fetch_detail(backend: CliBackend, experiment_id: int) -> ExperimentDetail | None:
    """Fetch full detail for a single experiment."""
    from verdandi.models.idea import IdeaCandidate
    from verdandi.models.research import MarketResearch
    from verdandi.models.scoring import PreBuildScore

    exp = backend.get_experiment(experiment_id)
    if exp is None:
        return None

    idea_result = backend.get_step_result(experiment_id, "idea_discovery")
    research_result = backend.get_step_result(experiment_id, "deep_research")
    scoring_result = backend.get_step_result(experiment_id, "scoring")

    idea = (
        IdeaCandidate(**idea_result["data"])
        if idea_result and isinstance(idea_result["data"], dict)
        else None
    )
    research = (
        MarketResearch(**research_result["data"])
        if research_result and isinstance(research_result["data"], dict)
        else None
    )
    score = (
        PreBuildScore(**scoring_result["data"])
        if scoring_result and isinstance(scoring_result["data"], dict)
        else None
    )

    all_steps = backend.get_all_step_results(experiment_id)

    return ExperimentDetail(
        experiment=exp,
        idea=idea,
        research=research,
        score=score,
        all_steps=all_steps,
    )
