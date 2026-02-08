"""Notification system: console output and email stubs."""

from __future__ import annotations

import structlog

logger = structlog.get_logger()


def notify_console(title: str, message: str, experiment_id: int | None = None) -> None:
    """Print a notification to the console."""
    prefix = f"[Experiment {experiment_id}] " if experiment_id else ""
    logger.info("%s%s: %s", prefix, title, message)


def notify_review_needed(experiment_id: int, idea_title: str) -> None:
    """Notify that an experiment needs human review."""
    notify_console(
        "Review Required",
        f"Experiment '{idea_title}' is ready for review. "
        f"Run: verdandi review {experiment_id} --approve",
        experiment_id=experiment_id,
    )


def notify_pipeline_complete(experiment_id: int, status: str) -> None:
    """Notify that a pipeline run completed."""
    notify_console(
        "Pipeline Complete",
        f"Final status: {status}",
        experiment_id=experiment_id,
    )


def notify_error(experiment_id: int, step_name: str, error: str) -> None:
    """Notify about a pipeline error."""
    notify_console(
        f"Error in {step_name}",
        error,
        experiment_id=experiment_id,
    )


def notify_email(to: str, subject: str, _body: str) -> None:
    """Send an email notification. Stub — not yet implemented."""
    logger.info("Email stub: to=%s subject=%s", to, subject)
