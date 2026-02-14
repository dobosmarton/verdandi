"""Port interfaces (Protocols) for hexagonal architecture."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pydantic import BaseModel

    from verdandi.db import LogEntryDict, StepResultDict
    from verdandi.memory.long_term import SimilarIdeaResult
    from verdandi.models.experiment import Experiment, ExperimentStatus


@runtime_checkable
class DatabasePort(Protocol):
    """Interface for experiment and step result persistence."""

    def init_schema(self) -> None: ...
    def close(self) -> None: ...
    def create_experiment(self, experiment: Experiment) -> Experiment: ...
    def get_experiment(self, experiment_id: int) -> Experiment | None: ...
    def list_experiments(self, status: ExperimentStatus | None = None) -> list[Experiment]: ...
    def update_experiment_status(
        self,
        experiment_id: int,
        status: ExperimentStatus,
        current_step: int | None = None,
        worker_id: str | None = None,
    ) -> None: ...
    def update_experiment_review(
        self,
        experiment_id: int,
        approved: bool,
        reviewed_by: str = "cli",
        notes: str = "",
    ) -> None: ...
    def save_step_result(
        self,
        experiment_id: int,
        step_name: str,
        step_number: int,
        data_json: str,
        worker_id: str = "",
    ) -> int: ...
    def get_step_result(self, experiment_id: int, step_name: str) -> StepResultDict | None: ...
    def get_all_step_results(self, experiment_id: int) -> list[StepResultDict]: ...
    def log_event(
        self,
        event: str,
        message: str = "",
        experiment_id: int | None = None,
        step_name: str = "",
        worker_id: str = "",
    ) -> None: ...
    def get_log(self, experiment_id: int) -> list[LogEntryDict]: ...


@runtime_checkable
class LLMPort(Protocol):
    """Interface for LLM text/structured generation."""

    @property
    def is_available(self) -> bool: ...

    def generate(
        self,
        prompt: str,
        response_model: type[BaseModel],
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> BaseModel: ...

    def generate_text(
        self,
        prompt: str,
        system: str = "",
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> str: ...


@runtime_checkable
class NotificationPort(Protocol):
    """Interface for sending notifications."""

    def notify_review_needed(self, experiment_id: int, idea_title: str) -> None: ...
    def notify_pipeline_complete(self, experiment_id: int, status: str) -> None: ...
    def notify_error(self, experiment_id: int, step_name: str, error: str) -> None: ...


@runtime_checkable
class SearchClientPort(Protocol):
    """Interface for web search clients (Tavily, Serper, Exa, etc.)."""

    @property
    def is_available(self) -> bool: ...

    def search(
        self, query: str, max_results: int = 10
    ) -> list[dict[str, str | int | float | None]]: ...


@runtime_checkable
class ReadOnlyMemory(Protocol):
    """Read-only interface to the orchestrator's long-term vector memory.

    Agents receive this to query similar ideas without being able to
    write to the vector store — only the orchestrator writes.
    """

    @property
    def is_available(self) -> bool: ...

    def find_similar_ideas(
        self,
        embedding: list[float],
        *,
        threshold: float = 0.82,
        limit: int = 5,
    ) -> list[SimilarIdeaResult]: ...
