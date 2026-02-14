"""Abstract base class for pipeline steps and step context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, TypeVar

import structlog

if TYPE_CHECKING:
    from pydantic import BaseModel

    from verdandi.config import Settings
    from verdandi.db import Database
    from verdandi.models.experiment import Experiment
    from verdandi.protocols import ReadOnlyMemory
    from verdandi.strategies import DiscoveryStrategy

logger = structlog.get_logger()

_T = TypeVar("_T", bound="BaseModel")


class PriorResults:
    """Read-only access to prior step results, pre-loaded by the orchestrator.

    Agents use this instead of querying the database directly, enforcing
    the separation between orchestrator (owns writes) and agents (read-only).
    """

    def __init__(self, results: dict[str, dict[str, object]]) -> None:
        self._results = results

    def get(self, step_name: str) -> dict[str, object] | None:
        """Return raw result dict for a step, or None if not found."""
        return self._results.get(step_name)

    def get_typed(self, step_name: str, model: type[_T]) -> _T:
        """Validate and return a typed Pydantic model from a prior step result.

        Raises RuntimeError if the step result is missing.
        """
        data = self._results.get(step_name)
        if data is None:
            raise RuntimeError(
                f"No result found for step '{step_name}'. "
                f"The preceding step must complete before this step can run."
            )
        return model.model_validate(data)

    def __contains__(self, step_name: str) -> bool:
        return step_name in self._results


@dataclass(frozen=True, slots=True)
class StepContext:
    """Bundles everything a step needs to execute.

    The orchestrator pre-loads ``prior_results`` and optionally provides
    a ``memory`` handle.  Direct ``db`` access is deprecated — agents
    should read prior data via ``prior_results`` instead.
    """

    settings: Settings
    experiment: Experiment
    db: Database | None = None  # Deprecated: use prior_results instead
    dry_run: bool = False
    worker_id: str = ""
    correlation_id: str = ""
    exclude_titles: tuple[str, ...] = ()
    discovery_strategy: DiscoveryStrategy | None = None
    prior_results: PriorResults | None = None
    memory: ReadOnlyMemory | None = None


class AbstractStep(ABC):
    """Base class for all pipeline steps."""

    name: str = ""
    step_number: int = -1

    @abstractmethod
    def run(self, ctx: StepContext) -> BaseModel:
        """Execute this step. Returns a Pydantic model to be stored."""
        ...

    def is_complete(self, ctx: StepContext) -> bool:
        """Check if this step has already been completed for the experiment."""
        if ctx.prior_results is not None:
            return ctx.prior_results.get(self.name) is not None
        if ctx.db is not None:
            result = ctx.db.get_step_result(ctx.experiment.id, self.name)  # type: ignore[arg-type]
            return result is not None
        return False

    def should_skip(self, _ctx: StepContext) -> bool:
        """Override to skip this step conditionally (e.g., human review in dry-run)."""
        return False


# Global step registry
_step_registry: dict[int, AbstractStep] = {}


def register_step(cls: type[AbstractStep]) -> type[AbstractStep]:
    """Decorator that registers a step class by its step_number."""
    instance = cls()
    if instance.step_number < 0:
        raise ValueError(f"Step {cls.__name__} must define step_number >= 0")
    if instance.step_number in _step_registry:
        existing = _step_registry[instance.step_number]
        raise ValueError(
            f"Step number {instance.step_number} already registered by {existing.__class__.__name__}"
        )
    _step_registry[instance.step_number] = instance
    logger.debug("Registered step %d: %s", instance.step_number, instance.name)
    return cls


def get_step_registry() -> dict[int, AbstractStep]:
    """Return the global step registry (step_number → instance)."""
    return _step_registry
