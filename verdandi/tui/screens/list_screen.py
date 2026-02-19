"""Experiment list screen with navigable DataTable."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.screen import Screen
from textual.widgets import DataTable, Footer, Header

from verdandi.tui.data import ExperimentSummary, fetch_summaries

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from verdandi.tui.app import VerdandiApp

    # Enable typed access to app.backend
    app: VerdandiApp


class ExperimentListScreen(Screen[None]):
    """Browsable list of all experiments."""

    BINDINGS: ClassVar[list[Binding]] = [  # type: ignore[assignment]
        Binding("q", "app.quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("escape", "app.quit", "Quit"),
    ]

    def compose(self) -> ComposeResult:
        yield Header()
        yield DataTable(id="experiments")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#experiments", DataTable)
        table.cursor_type = "row"
        table.zebra_stripes = True
        table.add_columns("ID", "Status", "Idea", "Step", "Score", "Decision")
        self._load_data()

    @work(thread=True)
    def _load_data(self) -> None:
        app: VerdandiApp = self.app  # type: ignore[assignment]
        summaries = fetch_summaries(app.backend)
        self.app.call_from_thread(self._populate_table, summaries)

    def _populate_table(self, summaries: list[ExperimentSummary]) -> None:
        table = self.query_one("#experiments", DataTable)
        table.clear()
        for s in summaries:
            status_text = Text(s.status, style=s.status_color)
            score_text = str(s.score) if s.score is not None else "-"
            decision_text = s.decision.upper() if s.decision else "-"
            decision_style = {
                "go": "bold green",
                "no_go": "bold red",
                "iterate": "bold yellow",
            }.get(s.decision or "", "")
            table.add_row(
                str(s.id),
                status_text,
                s.idea_title,
                s.step_label,
                score_text,
                Text(decision_text, style=decision_style),
                key=str(s.id),
            )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.row_key is not None and event.row_key.value is not None:
            experiment_id = int(event.row_key.value)
            from verdandi.tui.screens.detail_screen import ExperimentDetailScreen

            self.app.push_screen(ExperimentDetailScreen(experiment_id))  # type: ignore[unused-awaitable]

    def action_refresh(self) -> None:
        self._load_data()
