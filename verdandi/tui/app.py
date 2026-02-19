"""Verdandi TUI application."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from textual.app import App

from verdandi.tui.screens.list_screen import ExperimentListScreen

if TYPE_CHECKING:
    from verdandi.protocols import CliBackend

_STYLES_DIR = Path(__file__).parent / "styles"


class VerdandiApp(App[None]):
    """Interactive experiment browser."""

    TITLE = "Verdandi"
    CSS_PATH: ClassVar[list[str]] = [str(_STYLES_DIR / "app.tcss")]  # type: ignore[assignment]

    def __init__(self, backend: CliBackend) -> None:
        super().__init__()
        self.backend = backend

    def on_mount(self) -> None:
        self.push_screen(ExperimentListScreen())  # type: ignore[unused-awaitable]
