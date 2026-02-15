"""HTTP client for the Verdandi remote API.

Implements the CliBackend protocol so CLI commands work transparently
against either a local SQLite database or a remote FastAPI server.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import click
import httpx
import structlog

if TYPE_CHECKING:
    from collections.abc import Iterator

    from verdandi.db import LogEntryDict, StepResultDict
    from verdandi.models.experiment import Experiment

logger = structlog.get_logger()


class RemoteApiError(Exception):
    """Raised when the remote API returns an error."""

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(f"API error {status_code}: {detail}")


@contextmanager
def handle_remote_errors() -> Iterator[None]:
    """Context manager that catches remote API errors and exits cleanly."""
    try:
        yield
    except RemoteApiError as exc:
        click.echo(f"Remote API error: {exc.detail}", err=True)
        raise SystemExit(1) from exc
    except httpx.ConnectError as exc:
        click.echo(f"Error: cannot connect to remote API ({exc}).", err=True)
        raise SystemExit(1) from exc
    except httpx.TimeoutException as exc:
        click.echo("Error: remote API request timed out.", err=True)
        raise SystemExit(1) from exc


def _parse_dt(value: str) -> datetime:
    """Parse an ISO datetime string to a datetime object."""
    for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(value, fmt).replace(tzinfo=UTC)
        except ValueError:
            continue
    # Fallback: return current time if unparseable
    return datetime.now(UTC)


def _response_to_experiment(data: dict[str, Any]) -> Experiment:
    """Convert an ExperimentResponse JSON dict to an Experiment domain model."""
    from verdandi.models.experiment import Experiment, ExperimentStatus

    reviewed_at = data.get("reviewed_at")
    return Experiment(
        id=data.get("id"),
        idea_title=str(data.get("idea_title", "")),
        idea_summary=str(data.get("idea_summary", "")),
        status=ExperimentStatus(str(data["status"])),
        current_step=int(data.get("current_step", 0)),
        worker_id=str(data.get("worker_id", "")),
        reviewed_by=str(data.get("reviewed_by", "")),
        review_notes=str(data.get("review_notes", "")),
        reviewed_at=_parse_dt(str(reviewed_at)) if reviewed_at else None,
        created_at=_parse_dt(str(data.get("created_at", ""))),
        updated_at=_parse_dt(str(data.get("updated_at", ""))),
    )


def _response_to_step_result(data: dict[str, Any]) -> StepResultDict:
    """Convert a StepResultResponse JSON dict to StepResultDict."""
    return {
        "id": int(data["id"]),
        "experiment_id": int(data["experiment_id"]),
        "step_name": str(data["step_name"]),
        "step_number": int(data["step_number"]),
        "data": data["data"],
        "worker_id": str(data.get("worker_id", "")),
        "created_at": str(data.get("created_at", "")),
    }


def _response_to_log_entry(data: dict[str, Any]) -> LogEntryDict:
    """Convert a LogEntryResponse JSON dict to LogEntryDict."""
    return {
        "id": int(data["id"]),
        "experiment_id": data.get("experiment_id"),
        "step_name": str(data.get("step_name", "")),
        "event": str(data.get("event", "")),
        "message": str(data.get("message", "")),
        "worker_id": str(data.get("worker_id", "")),
        "created_at": str(data.get("created_at", "")),
    }


class ApiClient:
    """Talks to the Verdandi FastAPI server over HTTP.

    Implements the CliBackend protocol so CLI commands work transparently
    against either a local Database or this remote client.
    """

    def __init__(self, base_url: str, *, timeout: float = 30.0) -> None:
        url = base_url.rstrip("/")
        self._base = url
        self._http = httpx.Client(base_url=f"{url}/api/v1", timeout=timeout)

    def close(self) -> None:
        self._http.close()

    # ------------------------------------------------------------------
    # CliBackend protocol methods (shared with Database)
    # ------------------------------------------------------------------

    def get_experiment(self, experiment_id: int) -> Experiment | None:
        resp = self._http.get(f"/experiments/{experiment_id}")
        if resp.status_code == 404:
            return None
        # The existing API raises ValueError (-> 500) for not found,
        # so also handle 500 with "not found" in the detail.
        if resp.status_code >= 400 and "not found" in resp.text.lower():
            return None
        self._check(resp)
        return _response_to_experiment(resp.json())

    def list_experiments(self, status: object = None) -> list[Experiment]:
        params: dict[str, str] = {}
        if status is not None:
            params["status"] = str(status)
        resp = self._http.get("/experiments", params=params)
        self._check(resp)
        data = resp.json()
        return [_response_to_experiment(e) for e in data["experiments"]]

    def get_step_result(self, experiment_id: int, step_name: str) -> StepResultDict | None:
        resp = self._http.get(f"/experiments/{experiment_id}/steps/{step_name}")
        self._check(resp)
        data = resp.json()
        if data is None:
            return None
        return _response_to_step_result(data)

    def get_all_step_results(self, experiment_id: int) -> list[StepResultDict]:
        resp = self._http.get(f"/experiments/{experiment_id}/steps")
        self._check(resp)
        return [_response_to_step_result(r) for r in resp.json()]

    def get_log(self, experiment_id: int) -> list[LogEntryDict]:
        resp = self._http.get(f"/experiments/{experiment_id}/log")
        self._check(resp)
        return [_response_to_log_entry(e) for e in resp.json()]

    def update_experiment_review(
        self,
        experiment_id: int,
        approved: bool,
        reviewed_by: str = "cli",
        notes: str = "",
    ) -> None:
        resp = self._http.post(
            f"/reviews/{experiment_id}",
            json={"approved": approved, "reviewed_by": reviewed_by, "notes": notes},
        )
        self._check(resp)

    def archive_experiment(self, experiment_id: int) -> None:
        resp = self._http.post(f"/experiments/{experiment_id}/archive")
        self._check(resp)

    # ------------------------------------------------------------------
    # ApiClient-specific methods (not in CliBackend protocol)
    # ------------------------------------------------------------------

    def trigger_discover(
        self,
        max_ideas: int = 3,
        dry_run: bool = False,
        strategy: str | None = None,
    ) -> dict[str, Any]:
        """Trigger idea discovery via the API."""
        body: dict[str, Any] = {"max_ideas": max_ideas, "dry_run": dry_run}
        if strategy is not None:
            body["strategy"] = strategy
        resp = self._http.post("/actions/discover", json=body)
        self._check(resp)
        return resp.json()  # type: ignore[no-any-return]

    def trigger_run(
        self,
        experiment_id: int,
        dry_run: bool = False,
        stop_after: int | None = None,
    ) -> dict[str, Any]:
        """Trigger a pipeline run via the API."""
        body: dict[str, Any] = {"dry_run": dry_run}
        if stop_after is not None:
            body["stop_after"] = stop_after
        resp = self._http.post(f"/actions/run/{experiment_id}", json=body)
        self._check(resp)
        return resp.json()  # type: ignore[no-any-return]

    def get_report(self, experiment_id: int) -> dict[str, Any]:
        """Get a structured research report."""
        resp = self._http.get(f"/experiments/{experiment_id}/report")
        self._check(resp)
        return resp.json()  # type: ignore[no-any-return]

    def list_reservations(self, active_only: bool = True) -> list[dict[str, Any]]:
        """List topic reservations."""
        resp = self._http.get("/reservations", params={"active_only": str(active_only).lower()})
        self._check(resp)
        return resp.json()  # type: ignore[no-any-return]

    def config_check(self) -> dict[str, bool]:
        """Check which API keys are configured on the server."""
        resp = self._http.get("/config/check")
        self._check(resp)
        data = resp.json()
        configured: dict[str, bool] = data.get("configured", {})
        return configured

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _check(self, resp: httpx.Response) -> None:
        """Raise RemoteApiError on HTTP error responses."""
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("detail", resp.text)
            except Exception:
                detail = resp.text
            raise RemoteApiError(resp.status_code, str(detail))
