"""Abstract base class for pipeline steps and step context."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from pydantic import BaseModel

    from verdandi.config import Settings
    from verdandi.db import Database
    from verdandi.models.experiment import Experiment

logger = structlog.get_logger()


@dataclass(frozen=True, slots=True)
class StepContext:
    """Bundles everything a step needs to execute."""

    db: Database
    settings: Settings
    experiment: Experiment
    dry_run: bool = False
    worker_id: str = ""
    correlation_id: str = ""


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
        result = ctx.db.get_step_result(ctx.experiment.id, self.name)  # type: ignore[arg-type]
        return result is not None

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
