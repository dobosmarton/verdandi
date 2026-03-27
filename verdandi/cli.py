"""Click CLI entry point for Verdandi."""

from __future__ import annotations

import json
import sys
from typing import TYPE_CHECKING

import click

from verdandi.config import Settings
from verdandi.db import Database
from verdandi.logging import configure_logging

if TYPE_CHECKING:
    from verdandi.memory.long_term import LongTermMemory
    from verdandi.protocols import CliBackend


def _get_db(settings: Settings) -> Database:
    settings.ensure_data_dir()
    db = Database(settings.db_path)
    db.init_schema()
    return db


def _get_backend(settings: Settings, remote_url: str | None = None) -> CliBackend:
    """Return ApiClient if remote URL configured, else local Database."""
    url = remote_url or settings.api_url
    if url:
        from verdandi.api.client import ApiClient

        return ApiClient(url)
    return _get_db(settings)


def _is_remote(ctx: click.Context) -> bool:
    """Check if we're in remote mode."""
    return bool(ctx.obj.get("remote_url"))


def _require_local(ctx: click.Context, command_name: str) -> None:
    """Exit with error if in remote mode for a local-only command."""
    if _is_remote(ctx):
        click.echo(f"Error: '{command_name}' is not available in remote mode.", err=True)
        sys.exit(1)


def _get_ltm(settings: Settings) -> LongTermMemory | None:
    """Construct LongTermMemory if Qdrant is configured, else None."""
    if not settings.qdrant_url:
        return None
    from verdandi.memory import long_term

    return long_term.LongTermMemory(settings.qdrant_url, settings.qdrant_api_key)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
@click.option(
    "--remote",
    type=str,
    default=None,
    help="Remote API URL (e.g. http://server:8000)",
)
@click.pass_context
def cli(ctx: click.Context, verbose: bool, remote: str | None) -> None:
    """Verdandi — autonomous product validation factory."""
    ctx.ensure_object(dict)
    settings = Settings()
    log_level = "DEBUG" if verbose else settings.log_level
    configure_logging(log_level=log_level, log_format=settings.log_format)
    ctx.obj["settings"] = settings
    ctx.obj["verbose"] = verbose
    ctx.obj["remote_url"] = remote or settings.api_url or None


@cli.command()
@click.option("--max-ideas", default=3, type=int, help="Number of ideas to discover")
@click.option(
    "--strategy",
    type=str,
    default="auto",
    help="Discovery strategy: auto, disruption, moonshot, or custom strategy name",
)
@click.option("--dry-run", is_flag=True, help="Use mock data")
@click.pass_context
def discover(ctx: click.Context, max_ideas: int, strategy: str, dry_run: bool) -> None:
    """Discover new product ideas."""
    if _is_remote(ctx):
        from verdandi.api.client import ApiClient, handle_remote_errors

        client = ApiClient(ctx.obj["remote_url"])
        try:
            with handle_remote_errors():
                strat = strategy if strategy != "auto" else None
                result = client.trigger_discover(
                    max_ideas=max_ideas, dry_run=dry_run, strategy=strat
                )
                click.echo(f"Discovery triggered: {result['message']}")
                if result.get("task_id"):
                    click.echo(f"Task ID: {result['task_id']}")
        finally:
            client.close()
        return

    from verdandi.orchestrator import PipelineRunner
    from verdandi.strategy_loader import get_strategy_by_name

    strategy_override = None
    if strategy != "auto":
        settings = ctx.obj["settings"]
        strategy_obj = get_strategy_by_name(strategy, settings.strategies_dir)
        if strategy_obj is None:
            click.echo(f"Error: Strategy '{strategy}' not found", err=True)
            click.echo("\nAvailable strategies: auto, disruption, moonshot", err=True)
            click.echo("Use 'verdandi strategy list' to see custom strategies", err=True)
            sys.exit(1)
        strategy_override = strategy_obj

    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        runner = PipelineRunner(
            db=db, settings=settings, dry_run=dry_run, long_term_memory=_get_ltm(settings)
        )
        ids = runner.run_discovery_batch(max_ideas=max_ideas, strategy_override=strategy_override)
        click.echo(f"Created {len(ids)} experiments: {ids}")
    finally:
        db.close()


@cli.command()
@click.argument("experiment_id", type=int, required=False)
@click.option("--all", "run_all", is_flag=True, help="Run all pending experiments")
@click.option(
    "--stop-after",
    "stop_after",
    type=int,
    default=None,
    help="Stop after step N (e.g., 2 for scoring)",
)
@click.option("--dry-run", is_flag=True, help="Use mock data")
@click.pass_context
def run(
    ctx: click.Context,
    experiment_id: int | None,
    run_all: bool,
    stop_after: int | None,
    dry_run: bool,
) -> None:
    """Run the pipeline for an experiment."""
    if _is_remote(ctx):
        from verdandi.api.client import ApiClient, handle_remote_errors

        if experiment_id is None:
            click.echo("Error: provide an experiment ID for remote runs", err=True)
            sys.exit(1)
        client = ApiClient(ctx.obj["remote_url"])
        try:
            with handle_remote_errors():
                result = client.trigger_run(
                    experiment_id=experiment_id,
                    dry_run=dry_run,
                    stop_after=stop_after,
                )
                click.echo(f"Pipeline triggered: {result['message']}")
                if result.get("task_id"):
                    click.echo(f"Task ID: {result['task_id']}")
        finally:
            client.close()
        return

    from verdandi.orchestrator import PipelineRunner

    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        runner = PipelineRunner(
            db=db, settings=settings, dry_run=dry_run, long_term_memory=_get_ltm(settings)
        )
        if run_all:
            runner.run_all_pending(stop_after=stop_after)
        elif experiment_id is not None:
            runner.run_experiment(experiment_id, stop_after=stop_after)
        else:
            click.echo("Error: provide an experiment ID or use --all", err=True)
            sys.exit(1)
    finally:
        db.close()


@cli.command()
@click.option("--max-ideas", default=3, type=int, help="Number of ideas to discover and research")
@click.option("--dry-run", is_flag=True, help="Use mock data")
@click.pass_context
def research(ctx: click.Context, max_ideas: int, dry_run: bool) -> None:
    """Discover ideas, research them, and score GO/NO_GO (stops at Step 2)."""
    if _is_remote(ctx):
        from verdandi.api.client import ApiClient, handle_remote_errors

        client = ApiClient(ctx.obj["remote_url"])
        try:
            with handle_remote_errors():
                click.echo(f"Triggering discovery of {max_ideas} ideas on remote server...")
                result = client.trigger_discover(max_ideas=max_ideas, dry_run=dry_run)
                click.echo(f"Discovery triggered: {result['message']}")
                click.echo(
                    "Note: remote research runs asynchronously. "
                    "Use 'verdandi ls' to check progress."
                )
        finally:
            client.close()
        return

    from verdandi.orchestrator import PipelineRunner

    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        runner = PipelineRunner(
            db=db, settings=settings, dry_run=dry_run, long_term_memory=_get_ltm(settings)
        )

        click.echo(f"Discovering {max_ideas} ideas...")
        ids = runner.run_discovery_batch(max_ideas=max_ideas)
        click.echo(f"Created {len(ids)} experiments. Running research + scoring...")

        for exp_id in ids:
            runner.run_experiment(exp_id, stop_after=2)

        click.echo("\n--- Research Results ---")
        for exp_id in ids:
            exp = db.get_experiment(exp_id)
            if exp is None:
                continue
            scoring = db.get_step_result(exp_id, "scoring")
            if scoring and isinstance(scoring["data"], dict):
                score = scoring["data"].get("total_score", "?")
                decision = scoring["data"].get("decision", "?")
                click.echo(f"  [{exp_id}] {exp.idea_title}: {score}/100 ({decision})")
            else:
                click.echo(f"  [{exp_id}] {exp.idea_title}: (scoring incomplete)")
    finally:
        db.close()


@cli.command("ls")
@click.option("--status", type=str, default=None, help="Filter by status")
@click.pass_context
def list_experiments(ctx: click.Context, status: str | None) -> None:
    """List experiments."""
    from verdandi.models.experiment import ExperimentStatus

    settings = ctx.obj["settings"]
    backend = _get_backend(settings, ctx.obj.get("remote_url"))
    try:
        exp_status = ExperimentStatus(status) if status else None
        experiments = backend.list_experiments(exp_status)
        if not experiments:
            click.echo("No experiments found.")
            return
        for exp in experiments:
            click.echo(
                f"  [{exp.id}] {exp.status.value:16s} {exp.idea_title} (step {exp.current_step})"
            )
    finally:
        backend.close()


@cli.command()
@click.argument("experiment_id", type=int)
@click.option("--step", type=str, default=None, help="Show specific step result")
@click.option("--log", "show_log", is_flag=True, help="Show pipeline log")
@click.pass_context
def inspect(ctx: click.Context, experiment_id: int, step: str | None, show_log: bool) -> None:
    """Inspect an experiment's results."""
    settings = ctx.obj["settings"]
    backend = _get_backend(settings, ctx.obj.get("remote_url"))
    try:
        exp = backend.get_experiment(experiment_id)
        if exp is None:
            click.echo(f"Experiment {experiment_id} not found.", err=True)
            sys.exit(1)

        click.echo(f"Experiment {exp.id}: {exp.idea_title}")
        click.echo(f"  Status: {exp.status.value}")
        click.echo(f"  Step: {exp.current_step}")
        click.echo(f"  Worker: {exp.worker_id}")

        if show_log:
            click.echo("\nPipeline Log:")
            for entry in backend.get_log(experiment_id):
                click.echo(f"  [{entry['created_at']}] {entry['event']}: {entry['message']}")
        elif step:
            result = backend.get_step_result(experiment_id, step)
            if result:
                click.echo(f"\nStep '{step}' result:")
                click.echo(json.dumps(result["data"], indent=2))
            else:
                click.echo(f"No result for step '{step}'")
        else:
            results = backend.get_all_step_results(experiment_id)
            if results:
                click.echo("\nCompleted steps:")
                for r in results:
                    click.echo(f"  Step {r['step_number']}: {r['step_name']}")
    finally:
        backend.close()


def _trunc(items: list[str], limit: int, full: bool) -> list[str]:
    """Return items[:limit] unless full=True. Appends '...' marker if truncated."""
    if full or len(items) <= limit:
        return items
    return [*items[:limit], f"  ... and {len(items) - limit} more (use --full)"]


def _trunc_str(text: str, max_len: int) -> str:
    """Truncate a string with ellipsis if it exceeds max_len."""
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


_DOUBLE_LINE = "\u2550" * 62  # ═
_SINGLE_LINE = "\u2500" * 56  # ─


@cli.command()
@click.argument("experiment_id", type=int)
@click.option("--full", is_flag=True, help="Show full details (all results, competitors)")
@click.pass_context
def report(ctx: click.Context, experiment_id: int, full: bool) -> None:
    """Show a human-readable research report for an experiment."""
    from collections import Counter

    from verdandi.models.idea import IdeaCandidate
    from verdandi.models.research import MarketResearch
    from verdandi.models.scoring import PreBuildScore

    settings = ctx.obj["settings"]
    backend = _get_backend(settings, ctx.obj.get("remote_url"))
    try:
        exp = backend.get_experiment(experiment_id)
        if exp is None:
            click.echo(f"Experiment {experiment_id} not found.", err=True)
            sys.exit(1)

        idea_result = backend.get_step_result(experiment_id, "idea_discovery")
        research_result = backend.get_step_result(experiment_id, "deep_research")
        scoring_result = backend.get_step_result(experiment_id, "scoring")

        idea = (
            IdeaCandidate(**idea_result["data"])
            if idea_result and isinstance(idea_result["data"], dict)
            else None
        )
        mkt = (
            MarketResearch(**research_result["data"])
            if research_result and isinstance(research_result["data"], dict)
            else None
        )
        score = (
            PreBuildScore(**scoring_result["data"])
            if scoring_result and isinstance(scoring_result["data"], dict)
            else None
        )

        out = click.echo

        # --- Header ---
        out(f"\n  {_DOUBLE_LINE}")
        out(f"    RESEARCH REPORT \u2014 Experiment #{exp.id}")
        out(f"  {_DOUBLE_LINE}")

        # --- IDEA section ---
        if idea:
            out(f"\n  IDEA: {idea.title}")
            out(f"  {_SINGLE_LINE}")
            out(f"  {'One-liner:':<16s}{idea.one_liner}")
            out(f"  {'Category:':<16s}{idea.category}")
            out(f"  {'Target:':<16s}{idea.target_audience}")
            out(f"  {'Novelty:':<16s}{idea.novelty_score:.2f}")
            out(f"  {'Discovery:':<16s}{idea.discovery_type.value}")

            if idea.problem_statement:
                out("\n  Problem")
                for line in idea.problem_statement.splitlines():
                    out(f"    {line}")

            if idea.pain_points:
                out(f"\n  Pain Points ({len(idea.pain_points)})")
                for pp in idea.pain_points[:5] if not full else idea.pain_points:
                    out(
                        f"    [{pp.severity}/10] {pp.frequency:<8s}\u2014 {pp.description} ({pp.source})"
                    )
                if not full and len(idea.pain_points) > 5:
                    out(f"    ... and {len(idea.pain_points) - 5} more (use --full)")

            if idea.existing_solutions:
                out(f"\n  Known Solutions ({len(idea.existing_solutions)})")
                for sol in _trunc(idea.existing_solutions, 5, full):
                    out(f"    \u2022 {sol}")

            if idea.differentiation:
                out("\n  Differentiation")
                out(f"    {idea.differentiation}")
        else:
            out(f"\n  IDEA: {exp.idea_title}")
            out(f"  {_SINGLE_LINE}")
            out("  (idea discovery data not available)")

        # --- MARKET RESEARCH section ---
        if mkt:
            out("\n  MARKET RESEARCH")
            out(f"  {_SINGLE_LINE}")
            if mkt.tam_estimate:
                out(f"  {'TAM:':<16s}{mkt.tam_estimate}")
            if mkt.market_growth:
                out(f"  {'Growth:':<16s}{mkt.market_growth}")
            if mkt.target_audience_size:
                out(f"  {'Audience:':<16s}{mkt.target_audience_size}")
            if mkt.willingness_to_pay:
                out(f"  {'WTP:':<16s}{mkt.willingness_to_pay}")

            if mkt.demand_signals:
                out(f"\n  Demand Signals ({len(mkt.demand_signals)})")
                for sig in _trunc(mkt.demand_signals, 5, full):
                    out(f"    \u2022 {sig}")

            if mkt.key_findings:
                out(f"\n  Key Findings ({len(mkt.key_findings)})")
                for kf in _trunc(mkt.key_findings, 5, full):
                    out(f"    \u2022 {kf}")

            if mkt.common_complaints:
                out(f"\n  Common Complaints ({len(mkt.common_complaints)})")
                for cc in _trunc(mkt.common_complaints, 5, full):
                    out(f"    \u2022 {cc}")

            # --- COMPETITORS sub-section ---
            if mkt.competitors:
                out(f"\n  COMPETITORS ({len(mkt.competitors)} found)")
                out(f"  {_SINGLE_LINE}")
                show_competitors = mkt.competitors if full else mkt.competitors[:4]
                for i, comp in enumerate(show_competitors, 1):
                    pricing_str = comp.pricing or "N/A"
                    users_str = comp.estimated_users or ""
                    name_col = f"{i}. {comp.name}"
                    out(f"    {name_col:<24s}{pricing_str:<18s}{users_str}")
                    if comp.description and full:
                        out(f"       {comp.description}")
                    if comp.strengths:
                        shown = comp.strengths if full else comp.strengths[:2]
                        for s in shown:
                            out(f"       + {s}")
                    if comp.weaknesses:
                        shown = comp.weaknesses if full else comp.weaknesses[:2]
                        for w in shown:
                            out(f"       - {w}")
                    if i < len(show_competitors):
                        out("")
                if not full and len(mkt.competitors) > 4:
                    out(f"    ... and {len(mkt.competitors) - 4} more (use --full)")

            if mkt.competitor_gaps:
                out(f"\n  Gaps in Existing Solutions ({len(mkt.competitor_gaps)})")
                for gap in _trunc(mkt.competitor_gaps, 5, full):
                    out(f"    \u2022 {gap}")

            if mkt.research_summary and full:
                out("\n  Research Summary")
                for line in mkt.research_summary.splitlines():
                    out(f"    {line}")

            # --- Search results footer ---
            if mkt.search_results:
                source_counts: Counter[str] = Counter(sr.source for sr in mkt.search_results)
                source_parts = ", ".join(
                    f"{src}: {cnt}" for src, cnt in source_counts.most_common()
                )
                out(
                    f"\n  Sources: {len(mkt.search_results)} results "
                    f"from {len(source_counts)} APIs ({source_parts})"
                )
                if full:
                    out("")
                    for sr in mkt.search_results:
                        score_str = f" [{sr.relevance_score:.1f}]" if sr.relevance_score else ""
                        out(f"    [{sr.source}]{score_str} {sr.title}")
                        out(f"      {sr.url}")
                        if sr.snippet:
                            out(f"      {_trunc_str(sr.snippet, 120)}")

        # --- SCORING section ---
        if score:
            decision_str = score.decision.value.upper()
            council_indicator = ""
            if score.council_votes:
                go_count = sum(1 for v in score.council_votes if v.decision.value == "go")
                council_indicator = f" [Council: {go_count}/{len(score.council_votes)} GO]"
            out(
                f"\n  SCORING \u2014 {score.total_score}/100 \u2192 {decision_str}{council_indicator}"
            )
            out(f"  {_SINGLE_LINE}")

            if score.components:
                for sc in score.components:
                    reasoning_str = ""
                    if sc.reasoning:
                        r = sc.reasoning if full else _trunc_str(sc.reasoning, 60)
                        reasoning_str = f' \u2014 "{r}"'
                    out(
                        f"    {sc.name:<24s}{sc.score:>3d}/100  "
                        f"(\u00d7{sc.weight:.2f}){reasoning_str}"
                    )

            if score.reasoning:
                out("\n  Reasoning")
                text = score.reasoning if full else _trunc_str(score.reasoning, 300)
                for line in text.splitlines():
                    out(f"    {line}")

            if score.risks:
                out(f"\n  Risks ({len(score.risks)})")
                for r in score.risks:
                    out(f"    \u2022 {r}")

            if score.opportunities:
                out(f"\n  Opportunities ({len(score.opportunities)})")
                for o in score.opportunities:
                    out(f"    \u2022 {o}")

            if score.council_votes:
                out("\n  Council Member Votes")
                for vote in score.council_votes:
                    vote_decision = vote.decision.value.upper()
                    out(
                        f"    {vote.provider_name:<12s} ({vote.model_name}): "
                        f"{vote.base_score}/100 -> {vote_decision}"
                    )
                    if full:
                        for vc in vote.components:
                            out(f"      {vc.name:<24s}{vc.score:>3d}/100")

            # --- DISSENT ANALYSIS section ---
            if score.dissent_analysis and score.dissent_analysis.dissent_detected:
                da = score.dissent_analysis
                flip_tag = " [DECISION FLIPPED]" if da.decision_flipped else ""
                out(f"\n  Dissent Analysis{flip_tag}")
                out(f"  {_SINGLE_LINE}")
                out(
                    f"    Score: {da.initial_score} -> {da.final_score}  "
                    f"({len(da.resolution_rounds)} resolution round(s))"
                )

                if da.dimension_dissents:
                    out("\n    Contested Dimensions:")
                    for dd in da.dimension_dissents:
                        scores_str = ", ".join(
                            f"{p}: {s}" for p, s in dd.scores_by_provider.items()
                        )
                        out(f"      {dd.dimension:<24s}spread: {dd.spread}  ({scores_str})")

                for rr in da.resolution_rounds:
                    changed_tag = " [decision changed]" if rr.decision_changed else ""
                    out(
                        f"\n    Round {rr.round_number}: "
                        f"{rr.score_before} -> {rr.score_after}"
                        f"  ({rr.new_sources_count} new sources){changed_tag}"
                    )
                    if full:
                        for q in rr.followup_queries:
                            out(f"      Q: {q}")

        # --- Footer ---
        out(f"\n  {_DOUBLE_LINE}\n")

        if not mkt and not score:
            out("  Hint: run the pipeline further to generate research and scoring data.")
            out(f"    verdandi run {experiment_id}\n")

    finally:
        backend.close()


@cli.command()
@click.argument("experiment_id", type=int)
@click.option("--approve", is_flag=True, help="Approve the experiment")
@click.option("--reject", is_flag=True, help="Reject the experiment")
@click.option("--notes", type=str, default="", help="Review notes")
@click.pass_context
def review(ctx: click.Context, experiment_id: int, approve: bool, reject: bool, notes: str) -> None:
    """Approve or reject an experiment awaiting review."""
    if not approve and not reject:
        click.echo("Error: use --approve or --reject", err=True)
        sys.exit(1)
    if approve and reject:
        click.echo("Error: cannot both approve and reject", err=True)
        sys.exit(1)

    settings = ctx.obj["settings"]
    backend = _get_backend(settings, ctx.obj.get("remote_url"))
    try:
        exp = backend.get_experiment(experiment_id)
        if exp is None:
            click.echo(f"Experiment {experiment_id} not found.", err=True)
            sys.exit(1)

        backend.update_experiment_review(experiment_id, approved=approve, notes=notes)
        action = "approved" if approve else "rejected"
        click.echo(f"Experiment {experiment_id} {action}.")
    finally:
        backend.close()


@cli.command()
@click.option("--all-live", is_flag=True, help="Monitor all live experiments")
@click.pass_context
def monitor(ctx: click.Context, all_live: bool) -> None:
    """Show monitoring status for live experiments."""
    from verdandi.models.experiment import ExperimentStatus

    settings = ctx.obj["settings"]
    backend = _get_backend(settings, ctx.obj.get("remote_url"))
    try:
        experiments = backend.list_experiments(ExperimentStatus.RUNNING)
        if not experiments:
            click.echo("No running experiments.")
            return
        for exp in experiments:
            click.echo(f"  [{exp.id}] {exp.idea_title} — step {exp.current_step}")
    finally:
        backend.close()


@cli.command()
@click.argument("experiment_id", type=int)
@click.pass_context
def archive(ctx: click.Context, experiment_id: int) -> None:
    """Archive an experiment."""
    settings = ctx.obj["settings"]
    backend = _get_backend(settings, ctx.obj.get("remote_url"))
    try:
        backend.archive_experiment(experiment_id)
        click.echo(f"Experiment {experiment_id} archived.")
    finally:
        backend.close()


@cli.command()
@click.pass_context
def check(ctx: click.Context) -> None:
    """Verify which API keys are configured."""
    if _is_remote(ctx):
        from verdandi.api.client import ApiClient, handle_remote_errors

        client = ApiClient(ctx.obj["remote_url"])
        try:
            with handle_remote_errors():
                click.echo(f"  Remote server: {ctx.obj['remote_url']}")
                keys = client.config_check()
                for name, configured in sorted(keys.items()):
                    status = "OK" if configured else "-- not set"
                    click.echo(f"  {name:16s} {status}")
        finally:
            client.close()
        return

    settings = ctx.obj["settings"]
    keys = {
        "Anthropic": bool(settings.anthropic_api_key),
        "OpenAI": bool(settings.openai_api_key),
        "Google AI": bool(settings.google_api_key),
        "Tavily": bool(settings.tavily_api_key),
        "Serper": bool(settings.serper_api_key),
        "Exa": bool(settings.exa_api_key),
        "Perplexity": bool(settings.perplexity_api_key),
        "Firecrawl": bool(settings.firecrawl_api_key),
        "Porkbun": bool(settings.porkbun_api_key),
        "Cloudflare": bool(settings.cloudflare_api_token),
        "Umami": bool(settings.umami_api_key),
        "EmailOctopus": bool(settings.emailoctopus_api_key),
        "Twitter/X": bool(settings.twitter_bearer_token),
        "LinkedIn": bool(settings.linkedin_access_token),
        "Reddit": bool(settings.reddit_client_id),
        "Bluesky": bool(settings.bluesky_handle),
    }
    for name, configured in keys.items():
        status = "OK" if configured else "-- not set"
        click.echo(f"  {name:16s} {status}")


@cli.command()
@click.pass_context
def tui(ctx: click.Context) -> None:
    """Launch interactive experiment browser."""
    try:
        from verdandi.tui import VerdandiApp
    except ImportError:
        click.echo("TUI requires: pip install -e '.[tui]'", err=True)
        sys.exit(1)

    settings: Settings = ctx.obj["settings"]
    backend = _get_backend(settings, ctx.obj.get("remote_url"))
    try:
        app = VerdandiApp(backend=backend)
        app.run()
    finally:
        backend.close()


@cli.group()
@click.pass_context
def cache(ctx: click.Context) -> None:
    """Manage the research data cache (Redis)."""
    _require_local(ctx, "cache")


@cache.command("ping")
@click.pass_context
def cache_ping(ctx: click.Context) -> None:
    """Check Redis connectivity."""
    from verdandi.cache import ResearchCache

    settings = ctx.obj["settings"]
    if not settings.redis_url:
        click.echo("Redis not configured (REDIS_URL is empty).")
        return

    rc = ResearchCache(settings)
    if rc.ping():
        click.echo("Redis: OK")
    else:
        click.echo("Redis: unreachable", err=True)
        sys.exit(1)


@cache.command("stats")
@click.pass_context
def cache_stats(ctx: click.Context) -> None:
    """Show research cache statistics."""
    from verdandi.cache import ResearchCache

    settings = ctx.obj["settings"]
    if not settings.redis_url:
        click.echo("Redis not configured (REDIS_URL is empty).")
        return

    rc = ResearchCache(settings)
    if not rc.ping():
        click.echo("Redis: unreachable", err=True)
        sys.exit(1)

    stats = rc.stats()
    click.echo(f"  Total cached entries: {stats['total']}")
    if stats["by_source"]:
        for source in sorted(stats["by_source"]):
            click.echo(f"    {source}: {stats['by_source'][source]}")
    else:
        click.echo("  (no cached entries)")


@cache.command("purge")
@click.pass_context
def cache_purge(ctx: click.Context) -> None:
    """Delete all research cache entries."""
    from verdandi.cache import ResearchCache

    settings = ctx.obj["settings"]
    if not settings.redis_url:
        click.echo("Redis not configured (REDIS_URL is empty).")
        return

    rc = ResearchCache(settings)
    if not rc.ping():
        click.echo("Redis: unreachable", err=True)
        sys.exit(1)

    count = rc.purge_all()
    click.echo(f"Purged {count} cache entries.")


@cli.group()
@click.pass_context
def analytics(ctx: click.Context) -> None:
    """Historical analytics: GO rates, score trends, provider reliability."""


@analytics.command("overview")
@click.option("--from", "date_from", type=str, default=None, metavar="YYYY-MM-DD", help="Start date")
@click.option("--to", "date_to", type=str, default=None, metavar="YYYY-MM-DD", help="End date")
@click.pass_context
def analytics_overview(ctx: click.Context, date_from: str | None, date_to: str | None) -> None:
    """Show total experiments, GO rate, and average score."""
    from verdandi.analytics import get_overview

    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        result = get_overview(db, date_from=date_from, date_to=date_to)
        click.echo(f"  Total experiments   : {result.total_experiments}")
        click.echo(f"  GO rate             : {result.go_rate:.1%}")
        if result.avg_score is not None:
            click.echo(f"  Average score       : {result.avg_score:.1f}/100")
        else:
            click.echo("  Average score       : (no scored experiments)")
        click.echo(f"  Experiments scored  : {result.experiments_with_score}")
        click.echo("  By status:")
        for status, cnt in sorted(result.by_status.items()):
            click.echo(f"    {status:<20s}: {cnt}")
    finally:
        db.close()


@analytics.command("providers")
@click.option("--from", "date_from", type=str, default=None, metavar="YYYY-MM-DD", help="Start date")
@click.option("--to", "date_to", type=str, default=None, metavar="YYYY-MM-DD", help="End date")
@click.pass_context
def analytics_providers(ctx: click.Context, date_from: str | None, date_to: str | None) -> None:
    """Show per-provider research API reliability statistics."""
    from verdandi.analytics import get_provider_analytics

    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        result = get_provider_analytics(db, date_from=date_from, date_to=date_to)
        if not result.providers:
            click.echo("  No provider data available (run some experiments first).")
            return
        click.echo(f"  {'Provider':<16s} {'Calls':>6s}  {'OK':>6s}  {'Fail':>6s}  {'Rate':>7s}")
        click.echo(f"  {'-' * 16}  {'-' * 6}  {'-' * 6}  {'-' * 6}  {'-' * 7}")
        for p in result.providers:
            click.echo(
                f"  {p.provider:<16s} {p.total_calls:>6d}  {p.successful_calls:>6d}  "
                f"{p.failed_calls:>6d}  {p.success_rate:>6.1%}"
            )
    finally:
        db.close()


@analytics.command("scores")
@click.option("--from", "date_from", type=str, default=None, metavar="YYYY-MM-DD", help="Start date")
@click.option("--to", "date_to", type=str, default=None, metavar="YYYY-MM-DD", help="End date")
@click.pass_context
def analytics_scores(ctx: click.Context, date_from: str | None, date_to: str | None) -> None:
    """Show score distribution histogram and daily trend."""
    from verdandi.analytics import get_score_analytics

    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        result = get_score_analytics(db, date_from=date_from, date_to=date_to)

        click.echo("  Score Distribution")
        for bucket in result.distribution:
            bar = "\u2588" * bucket.count
            click.echo(f"    {bucket.bucket_label:>7s}  {bucket.count:>4d}  {bar}")

        click.echo("\n  Decision Counts")
        for decision, cnt in sorted(result.decision_counts.items()):
            click.echo(f"    {decision:<12s}: {cnt}")

        if result.trend:
            click.echo(f"\n  Daily Trend ({len(result.trend)} days)")
            for pt in result.trend[-10:]:
                click.echo(f"    {pt.date}  avg={pt.avg_score:>5.1f}  n={pt.count}")
        else:
            click.echo("\n  No trend data available.")
    finally:
        db.close()


@analytics.command("pipeline")
@click.option("--from", "date_from", type=str, default=None, metavar="YYYY-MM-DD", help="Start date")
@click.option("--to", "date_to", type=str, default=None, metavar="YYYY-MM-DD", help="End date")
@click.pass_context
def analytics_pipeline(ctx: click.Context, date_from: str | None, date_to: str | None) -> None:
    """Show step completion counts and pipeline throughput."""
    from verdandi.analytics import get_pipeline_analytics

    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        result = get_pipeline_analytics(db, date_from=date_from, date_to=date_to)
        click.echo(f"  Total experiments   : {result.total_experiments}")
        click.echo(f"  Completed           : {result.completed_experiments}")
        click.echo(f"  Completion rate     : {result.completion_rate:.1%}")

        if result.steps:
            click.echo(f"\n  {'Step':<32s}  {'#':>3s}  {'Runs':>6s}  {'Exps':>6s}")
            click.echo(f"  {'-' * 32}  {'-' * 3}  {'-' * 6}  {'-' * 6}")
            for s in result.steps:
                click.echo(
                    f"  {s.step_name:<32s}  {s.step_number:>3d}  {s.total_executions:>6d}  "
                    f"{s.experiments_with_step:>6d}"
                )
        else:
            click.echo("  No step data available (run some experiments first).")
    finally:
        db.close()


@cli.command()
@click.option("--workers", default=4, type=int, help="Number of worker processes")
@click.pass_context
def worker(ctx: click.Context, workers: int) -> None:
    """Start Huey worker consumer."""
    _require_local(ctx, "worker")
    from verdandi.orchestrator.scheduler import huey

    click.echo(f"Starting Huey consumer with {workers} workers...")
    consumer = huey.create_consumer(workers=workers)
    consumer.run()


@cli.group()
@click.pass_context
def enqueue(ctx: click.Context) -> None:
    """Enqueue tasks to the worker queue."""
    _require_local(ctx, "enqueue")


@enqueue.command("discover")
@click.option("--max-ideas", default=3, type=int)
@click.option("--dry-run", is_flag=True)
def enqueue_discover(max_ideas: int, dry_run: bool) -> None:
    """Enqueue a discovery task."""
    from verdandi.orchestrator.scheduler import discover_ideas_task

    result = discover_ideas_task(max_ideas=max_ideas, dry_run=dry_run)
    click.echo(f"Discovery task enqueued: {result}")


@enqueue.command("run")
@click.argument("experiment_id", type=int)
@click.option("--stop-after", "stop_after", type=int, default=None, help="Stop after step N")
@click.option("--dry-run", is_flag=True)
def enqueue_run(experiment_id: int, stop_after: int | None, dry_run: bool) -> None:
    """Enqueue a pipeline run task."""
    from verdandi.orchestrator.scheduler import run_pipeline_task

    result = run_pipeline_task(experiment_id=experiment_id, dry_run=dry_run, stop_after=stop_after)
    click.echo(f"Pipeline task enqueued: {result}")


@cli.command()
@click.option("--active-only/--all", default=True, help="Show only active reservations")
@click.pass_context
def reservations(ctx: click.Context, active_only: bool) -> None:
    """Show topic reservations."""
    if _is_remote(ctx):
        from verdandi.api.client import ApiClient, handle_remote_errors

        client = ApiClient(ctx.obj["remote_url"])
        try:
            with handle_remote_errors():
                remote_rows = client.list_reservations(active_only=active_only)
                if not remote_rows:
                    click.echo("No reservations found.")
                    return
                for r in remote_rows:
                    click.echo(
                        f"  [{r['id']}] {r['topic_key']} — worker={r['worker_id']} "
                        f"expires={r.get('expires_at', 'N/A')}"
                    )
        finally:
            client.close()
        return

    from verdandi.orchestrator.coordination import TopicReservationManager

    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        mgr = TopicReservationManager(db.Session)
        local_rows = mgr.list_active() if active_only else mgr.list_all()
        if not local_rows:
            click.echo("No reservations found.")
            return
        for res in local_rows:
            click.echo(
                f"  [{res['id']}] {res['topic_key']} — worker={res['worker_id']} "
                f"expires={res.get('expires_at', 'N/A')}"
            )
    finally:
        db.close()


@cli.group()
def strategy() -> None:
    """Manage discovery strategies."""
    pass


@strategy.command("list")
@click.pass_context
def strategy_list(ctx: click.Context) -> None:
    """Show all available strategies (built-in + custom)."""
    from verdandi.strategy_loader import list_all_strategies

    settings = ctx.obj["settings"]
    strategies = list_all_strategies(settings.strategies_dir)

    click.echo("\n📚 Available Strategies\n")

    click.echo("Built-in:")
    for s in strategies["builtin"]:
        click.echo(f"  • {s.discovery_type.value.lower():<12} — {s.name}")

    if strategies["custom"]:
        click.echo("\nCustom:")
        for s in strategies["custom"]:
            click.echo(f"  • {s.name:<12} — {s.discovery_output_model}")
    else:
        click.echo("\nCustom:")
        click.echo("  (none — create one with 'verdandi strategy create')")

    click.echo("\nUse: verdandi discover --strategy <NAME>")


@strategy.command("show")
@click.argument("name")
@click.pass_context
def strategy_show(ctx: click.Context, name: str) -> None:
    """Display strategy details."""
    from verdandi.strategy_loader import get_strategy_by_name

    settings = ctx.obj["settings"]
    strategy_obj = get_strategy_by_name(name, settings.strategies_dir)

    if strategy_obj is None:
        click.echo(f"Error: Strategy '{name}' not found", err=True)
        sys.exit(1)

    click.echo(f"\n📋 Strategy: {strategy_obj.name}\n")
    click.echo(f"Discovery type: {strategy_obj.discovery_type.value}")
    click.echo(f"Output model: {strategy_obj.discovery_output_model}")

    click.echo(f"\nDiscovery queries ({len(strategy_obj.discovery_queries)}):")
    for i, query in enumerate(strategy_obj.discovery_queries, 1):
        click.echo(f"  {i}. {query}")

    click.echo("\nPerplexity question:")
    click.echo(f"  {strategy_obj.discovery_perplexity_question[:100]}...")

    click.echo("\nSource preferences:")
    click.echo(f"  Reddit: {strategy_obj.prioritize_reddit}")
    click.echo(f"  HN: {strategy_obj.prioritize_hn}")
    click.echo(f"  Twitter: {strategy_obj.prioritize_twitter}")

    if strategy_obj.scoring_guidance:
        click.echo("\nScoring guidance:")
        click.echo(f"  {strategy_obj.scoring_guidance[:100]}...")


@strategy.command("validate")
@click.argument("file_path", type=click.Path(exists=True))
def strategy_validate(file_path: str) -> None:
    """Validate a strategy YAML file."""
    from pathlib import Path

    from pydantic import ValidationError

    from verdandi.strategy_loader import load_strategy_from_yaml

    path = Path(file_path)

    try:
        strategy_obj = load_strategy_from_yaml(path)
        click.echo(f"✅ Strategy '{strategy_obj.name}' is valid")
        click.echo(f"   Type: {strategy_obj.discovery_type.value}")
        click.echo(f"   Queries: {len(strategy_obj.discovery_queries)}")
        click.echo(f"   Output: {strategy_obj.discovery_output_model}")
    except FileNotFoundError:
        click.echo(f"❌ File not found: {file_path}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"❌ YAML error: {e}", err=True)
        sys.exit(1)
    except ValidationError as e:
        click.echo("❌ Validation failed:\n", err=True)
        for error in e.errors():
            field = " -> ".join(str(loc) for loc in error["loc"])
            click.echo(f"   {field}: {error['msg']}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--host", type=str, default=None, help="Bind host")
@click.option("--port", type=int, default=None, help="Bind port")
@click.pass_context
def serve(ctx: click.Context, host: str | None, port: int | None) -> None:
    """Start the FastAPI API server."""
    _require_local(ctx, "serve")
    import uvicorn

    settings = ctx.obj["settings"]
    uvicorn.run(
        "verdandi.api.app:create_app",
        factory=True,
        host=host or settings.api_host,
        port=port or settings.api_port,
    )
