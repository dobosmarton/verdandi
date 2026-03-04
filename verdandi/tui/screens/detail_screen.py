"""Experiment detail screen with scrollable research report."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, ClassVar

from rich import box
from rich.console import Console as RichConsole
from rich.panel import Panel
from rich.table import Table as RichTable
from rich.text import Text
from textual import work
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.screen import Screen
from textual.widgets import Footer, Header, Static

from verdandi.tui.data import STATUS_COLORS, ExperimentDetail, fetch_detail

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from verdandi.tui.app import VerdandiApp

# Shared console for rendering Rich objects to plain text (no ANSI codes).
_PLAIN_CONSOLE = RichConsole(width=120, no_color=True, highlight=False)


def _rich_to_text(renderable: object) -> str:
    """Render any Rich renderable to plain text without ANSI codes or borders."""
    # Unwrap Panel to get inner content (avoids box-drawing border characters).
    if isinstance(renderable, Panel):
        title = renderable.title
        inner = renderable.renderable
        parts: list[str] = []
        if title:
            parts.append(f"── {title} ──")
        with _PLAIN_CONSOLE.capture() as capture:
            _PLAIN_CONSOLE.print(inner)
        parts.append(capture.get().rstrip())
        return "\n".join(parts)
    with _PLAIN_CONSOLE.capture() as capture:
        _PLAIN_CONSOLE.print(renderable)
    return capture.get().rstrip()


def _trunc(items: list[str], limit: int, full: bool) -> list[str]:
    return items if full else items[:limit]


def _trunc_str(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 3] + "..."


def _join_lines(lines: list[Text | str]) -> Text:
    """Join a list of Text/str items into a single Text with newlines."""
    return Text("\n").join(Text(str(line)) if isinstance(line, str) else line for line in lines)


# Section widget IDs in display order (excluding loading).
_SECTION_IDS = (
    "header-section",
    "idea-section",
    "research-section",
    "competitors-section",
    "scoring-section",
    "dissent-section",
    "steps-section",
)


class ExperimentDetailScreen(Screen[None]):
    """Scrollable research report for a single experiment."""

    BINDINGS: ClassVar[list[Binding]] = [  # type: ignore[assignment]
        Binding("escape", "go_back", "Back"),
        Binding("q", "app.quit", "Quit"),
        Binding("f", "toggle_full", "Toggle Full"),
        Binding("c", "copy_section", "Copy Section"),
        Binding("C", "copy_all", "Copy All"),
    ]
    CSS_PATH = None  # Styles inherited from app

    def __init__(self, experiment_id: int) -> None:
        super().__init__()
        self.experiment_id = experiment_id
        self._full = False
        self._detail: ExperimentDetail | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with VerticalScroll(id="detail-scroll"):
            yield Static(id="loading", classes="section")
            yield Static(id="header-section", classes="section")
            yield Static(id="idea-section", classes="section")
            yield Static(id="research-section", classes="section")
            yield Static(id="competitors-section", classes="section")
            yield Static(id="scoring-section", classes="section")
            yield Static(id="dissent-section", classes="section")
            yield Static(id="steps-section", classes="section")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#loading", Static).update("Loading...")
        self._load_data()

    @work(thread=True)
    def _load_data(self) -> None:
        app: VerdandiApp = self.app  # type: ignore[assignment]
        detail = fetch_detail(app.backend, self.experiment_id)
        self.app.call_from_thread(self._populate, detail)

    def _populate(self, detail: ExperimentDetail | None) -> None:
        self.query_one("#loading", Static).update("")
        if detail is None:
            self.query_one("#header-section", Static).update(
                f"Experiment {self.experiment_id} not found."
            )
            return
        self._detail = detail
        self._render_header(detail)
        self._render_idea(detail)
        self._render_research(detail)
        self._render_competitors(detail)
        self._render_scoring(detail)
        self._render_dissent(detail)
        self._render_steps(detail)

    # ── Section renderers ────────────────────────────────────────────

    def _render_header(self, detail: ExperimentDetail) -> None:
        exp = detail.experiment
        status_color = STATUS_COLORS.get(exp.status.value, "white")
        title = Text.assemble(
            ("Experiment #", "bold"),
            (str(exp.id or "?"), "bold"),
            " — ",
            (exp.idea_title, "bold cyan"),
        )
        status_line = Text.assemble(
            ("Status: ", ""),
            (exp.status.value, f"bold {status_color}"),
            (f"  |  Step: {exp.current_step}", ""),
            (f"  |  Worker: {exp.worker_id}" if exp.worker_id else "", "dim"),
        )
        panel = Panel(
            Text.assemble(title, "\n", status_line),
            border_style="bright_blue",
        )
        self.query_one("#header-section", Static).update(panel)

    def _render_idea(self, detail: ExperimentDetail) -> None:
        widget = self.query_one("#idea-section", Static)
        idea = detail.idea
        if idea is None:
            widget.update(Panel("(idea discovery not yet run)", title="Idea", border_style="dim"))
            return

        lines: list[Text | str] = []
        lines.append(Text.assemble(("One-liner: ", "bold"), idea.one_liner))
        lines.append(Text.assemble(("Category: ", "bold"), idea.category))
        lines.append(Text.assemble(("Target: ", "bold"), idea.target_audience))
        lines.append(
            Text.assemble(
                ("Novelty: ", "bold"),
                f"{idea.novelty_score:.2f}",
                ("  |  Discovery: ", "bold"),
                idea.discovery_type.value,
            )
        )

        if idea.problem_statement:
            lines.append("")
            lines.append(Text("Problem", style="bold underline"))
            lines.append(idea.problem_statement)

        if idea.pain_points:
            lines.append("")
            shown = idea.pain_points if self._full else idea.pain_points[:5]
            lines.append(Text(f"Pain Points ({len(idea.pain_points)})", style="bold underline"))
            lines.extend(f"  [{pp.severity}/10] {pp.frequency} — {pp.description}" for pp in shown)
            if not self._full and len(idea.pain_points) > 5:
                lines.append(
                    Text(f"  ... and {len(idea.pain_points) - 5} more (press f)", style="dim")
                )

        if idea.existing_solutions:
            lines.append("")
            lines.append(
                Text(f"Known Solutions ({len(idea.existing_solutions)})", style="bold underline")
            )
            lines.extend(f"  * {sol}" for sol in _trunc(idea.existing_solutions, 5, self._full))

        if idea.differentiation:
            lines.append("")
            lines.append(Text("Differentiation", style="bold underline"))
            lines.append(f"  {idea.differentiation}")

        widget.update(Panel(_join_lines(lines), title="Idea", border_style="green"))

    def _render_research(self, detail: ExperimentDetail) -> None:
        widget = self.query_one("#research-section", Static)
        mkt = detail.research
        if mkt is None:
            widget.update(
                Panel("(deep research not yet run)", title="Market Research", border_style="dim")
            )
            return

        lines: list[Text | str] = []

        if mkt.tam_estimate:
            lines.append(Text.assemble(("TAM: ", "bold"), _trunc_str(mkt.tam_estimate, 200)))
        if mkt.market_growth:
            lines.append(Text.assemble(("Growth: ", "bold"), _trunc_str(mkt.market_growth, 200)))
        if mkt.target_audience_size:
            lines.append(
                Text.assemble(("Audience: ", "bold"), _trunc_str(mkt.target_audience_size, 200))
            )
        if mkt.willingness_to_pay:
            lines.append(Text.assemble(("WTP: ", "bold"), _trunc_str(mkt.willingness_to_pay, 200)))

        if mkt.demand_signals:
            lines.append("")
            lines.append(
                Text(f"Demand Signals ({len(mkt.demand_signals)})", style="bold underline")
            )
            lines.extend(f"  * {sig}" for sig in _trunc(mkt.demand_signals, 5, self._full))
            if not self._full and len(mkt.demand_signals) > 5:
                lines.append(
                    Text(f"  ... and {len(mkt.demand_signals) - 5} more (press f)", style="dim")
                )

        if mkt.key_findings:
            lines.append("")
            lines.append(Text(f"Key Findings ({len(mkt.key_findings)})", style="bold underline"))
            lines.extend(f"  * {kf}" for kf in _trunc(mkt.key_findings, 5, self._full))

        if mkt.common_complaints:
            lines.append("")
            lines.append(
                Text(f"Common Complaints ({len(mkt.common_complaints)})", style="bold underline")
            )
            lines.extend(f"  * {cc}" for cc in _trunc(mkt.common_complaints, 5, self._full))

        if mkt.competitor_gaps:
            lines.append("")
            lines.append(Text(f"Gaps ({len(mkt.competitor_gaps)})", style="bold underline"))
            lines.extend(f"  * {gap}" for gap in _trunc(mkt.competitor_gaps, 5, self._full))

        # Source summary
        if mkt.search_results:
            source_counts: Counter[str] = Counter(sr.source for sr in mkt.search_results)
            parts = ", ".join(f"{s}: {c}" for s, c in source_counts.most_common())
            lines.append("")
            lines.append(
                Text(
                    f"Sources: {len(mkt.search_results)} results from "
                    f"{len(source_counts)} APIs ({parts})",
                    style="dim",
                )
            )

        # Gap analysis confidence
        if mkt.gap_analysis:
            ga = mkt.gap_analysis
            lines.append("")
            lines.append(
                Text.assemble(
                    ("Research Confidence: ", "bold"),
                    (f"{ga.overall_confidence:.0%}", "bold cyan"),
                    (f"  (rounds: {mkt.research_rounds_completed})", "dim"),
                )
            )
            for dim in ga.dimension_scores:
                conf = dim.confidence
                color = "green" if conf >= 0.6 else "yellow" if conf >= 0.4 else "red"
                lines.append(
                    Text.assemble(
                        (f"  {dim.dimension:<22s}", ""),
                        (f"{conf:.0%}", color),
                    )
                )

        widget.update(Panel(_join_lines(lines), title="Market Research", border_style="blue"))

    def _render_competitors(self, detail: ExperimentDetail) -> None:
        widget = self.query_one("#competitors-section", Static)
        mkt = detail.research
        if mkt is None or not mkt.competitors:
            widget.update("")
            return

        table = RichTable(
            title=f"Competitors ({len(mkt.competitors)})",
            box=box.SIMPLE_HEAVY,
            show_lines=True,
            expand=True,
        )
        table.add_column("Name", style="bold", ratio=2)
        table.add_column("Pricing", ratio=2)
        table.add_column("Strengths", ratio=3)
        table.add_column("Weaknesses", ratio=3)

        shown = mkt.competitors if self._full else mkt.competitors[:5]
        for comp in shown:
            strengths = "\n".join(
                f"+ {s}" for s in (comp.strengths if self._full else comp.strengths[:2])
            )
            weaknesses = "\n".join(
                f"- {w}" for w in (comp.weaknesses if self._full else comp.weaknesses[:2])
            )
            table.add_row(
                comp.name,
                comp.pricing or "N/A",
                Text(strengths, style="green"),
                Text(weaknesses, style="red"),
            )

        if not self._full and len(mkt.competitors) > 5:
            table.add_row(
                Text(f"... {len(mkt.competitors) - 5} more (press f)", style="dim"),
                "",
                "",
                "",
            )

        widget.update(table)

    def _render_scoring(self, detail: ExperimentDetail) -> None:
        widget = self.query_one("#scoring-section", Static)
        score = detail.score
        if score is None:
            widget.update(Panel("(scoring not yet run)", title="Scoring", border_style="dim"))
            return

        decision_color = {"go": "green", "no_go": "red", "iterate": "yellow"}.get(
            score.decision.value, "white"
        )

        # Component breakdown table
        comp_table = RichTable(box=box.SIMPLE, expand=True)
        comp_table.add_column("Component", style="bold")
        comp_table.add_column("Score", justify="right")
        comp_table.add_column("Weight", justify="right")
        comp_table.add_column("Reasoning")

        for sc in score.components:
            sc_color = "green" if sc.score >= 70 else "yellow" if sc.score >= 40 else "red"
            reasoning = sc.reasoning if self._full else _trunc_str(sc.reasoning, 60)
            comp_table.add_row(
                sc.name,
                Text(f"{sc.score}/100", style=sc_color),
                f"x{sc.weight:.2f}",
                reasoning,
            )

        lines: list[Text | str | RichTable] = []

        # Header with score + decision
        lines.append(
            Text.assemble(
                ("Score: ", "bold"),
                (f"{score.total_score}/100", "bold"),
                (" → ", ""),
                (score.decision.value.upper(), f"bold {decision_color}"),
            )
        )

        if score.council_votes:
            go_count = sum(1 for v in score.council_votes if v.decision.value == "go")
            lines.append(
                Text(
                    f"Council: {go_count}/{len(score.council_votes)} GO",
                    style="dim",
                )
            )

        lines.append("")
        lines.append(comp_table)

        if score.reasoning:
            lines.append("")
            lines.append(Text("Reasoning", style="bold underline"))
            text = score.reasoning if self._full else _trunc_str(score.reasoning, 300)
            lines.append(text)

        if score.risks:
            lines.append("")
            lines.append(Text(f"Risks ({len(score.risks)})", style="bold red"))
            lines.extend(f"  * {risk}" for risk in score.risks)

        if score.opportunities:
            lines.append("")
            lines.append(Text(f"Opportunities ({len(score.opportunities)})", style="bold green"))
            lines.extend(f"  * {opp}" for opp in score.opportunities)

        # Build the panel content — RichTable needs special handling
        from rich.console import Group

        renderables = [
            item if isinstance(item, (Text, RichTable)) else Text(str(item)) for item in lines
        ]

        widget.update(Panel(Group(*renderables), title="Scoring", border_style="yellow"))

    def _render_dissent(self, detail: ExperimentDetail) -> None:
        widget = self.query_one("#dissent-section", Static)
        score = detail.score
        if (
            score is None
            or score.dissent_analysis is None
            or not score.dissent_analysis.dissent_detected
        ):
            widget.update("")
            return

        da = score.dissent_analysis
        lines: list[Text | str] = []

        flip_text = " [DECISION FLIPPED]" if da.decision_flipped else ""
        lines.append(
            Text.assemble(
                ("Score: ", "bold"),
                (f"{da.initial_score} \u2192 {da.final_score}", ""),
                (f"  ({len(da.resolution_rounds)} round(s))", "dim"),
                (flip_text, "bold red" if da.decision_flipped else ""),
            )
        )

        if da.dimension_dissents:
            lines.append("")
            lines.append(Text("Contested Dimensions", style="bold underline"))
            for dd in da.dimension_dissents:
                scores_str = ", ".join(f"{p}: {s}" for p, s in dd.scores_by_provider.items())
                color = "red" if dd.spread >= 40 else "yellow"
                lines.append(
                    Text.assemble(
                        (f"  {dd.dimension:<24s}", ""),
                        (f"spread: {dd.spread}", color),
                        (f"  ({scores_str})", "dim"),
                    )
                )

        for rr in da.resolution_rounds:
            lines.append("")
            changed = " [changed]" if rr.decision_changed else ""
            lines.append(
                Text.assemble(
                    (f"Round {rr.round_number}: ", "bold"),
                    (f"{rr.score_before} \u2192 {rr.score_after}", ""),
                    (f"  ({rr.new_sources_count} new sources)", "dim"),
                    (changed, "bold yellow"),
                )
            )
            if self._full:
                lines.extend(Text(f"    Q: {q}", style="dim") for q in rr.followup_queries)

        widget.update(Panel(_join_lines(lines), title="Dissent Analysis", border_style="magenta"))

    def _render_steps(self, detail: ExperimentDetail) -> None:
        widget = self.query_one("#steps-section", Static)
        if not detail.all_steps:
            widget.update("")
            return

        lines: list[str] = []
        for step in detail.all_steps:
            name = step["step_name"]
            num = step["step_number"]
            ts = step["created_at"][:19] if step["created_at"] else ""
            lines.append(f"  Step {num}: {name}  ({ts})")

        content = "\n".join(lines)
        widget.update(Panel(content, title="Completed Steps", border_style="dim"))

    # ── Copy actions ─────────────────────────────────────────────────

    def _widget_to_text(self, widget: Static) -> str:
        """Render a Static widget's content to clean plain text."""
        from textual.visual import RichVisual

        visual = widget._render()
        if isinstance(visual, RichVisual):
            return _rich_to_text(visual._renderable)
        return str(visual).strip()

    def action_copy_section(self) -> None:
        """Copy the topmost visible section to clipboard."""
        scroll = self.query_one("#detail-scroll", VerticalScroll)
        scroll_y = scroll.scroll_offset.y

        # Find the first section whose top edge is at or above the current scroll position.
        best_widget: Static | None = None
        for sid in _SECTION_IDS:
            widget = self.query_one(f"#{sid}", Static)
            # Skip empty sections (hidden with empty string)
            content = self._widget_to_text(widget)
            if not content.strip():
                continue
            if widget.region.y <= scroll_y + scroll.region.y + 2:
                best_widget = widget
            else:
                # Past the viewport top — use this one if we haven't found any yet
                if best_widget is None:
                    best_widget = widget
                break

        if best_widget is None:
            self.notify("Nothing to copy", severity="warning")
            return

        text = self._widget_to_text(best_widget)
        if not text.strip():
            self.notify("Section is empty", severity="warning")
            return

        self.app.copy_to_clipboard(text)
        self.notify("Section copied!")

    def action_copy_all(self) -> None:
        """Copy all experiment sections to clipboard."""
        parts: list[str] = []
        for sid in _SECTION_IDS:
            widget = self.query_one(f"#{sid}", Static)
            text = self._widget_to_text(widget)
            if text.strip():
                parts.append(text)

        if not parts:
            self.notify("Nothing to copy", severity="warning")
            return

        self.app.copy_to_clipboard("\n\n".join(parts))
        self.notify("All sections copied!")

    # ── Navigation ───────────────────────────────────────────────────

    def action_go_back(self) -> None:
        self.app.pop_screen()  # type: ignore[unused-awaitable]

    def action_toggle_full(self) -> None:
        self._full = not self._full
        if self._detail is not None:
            self._populate(self._detail)
