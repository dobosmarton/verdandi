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


def _get_db(settings: Settings) -> Database:
    settings.ensure_data_dir()
    db = Database(settings.db_path)
    db.init_schema()
    return db


def _get_ltm(settings: Settings) -> LongTermMemory | None:
    """Construct LongTermMemory if Qdrant is configured, else None."""
    if not settings.qdrant_url:
        return None
    from verdandi.memory import long_term

    return long_term.LongTermMemory(settings.qdrant_url, settings.qdrant_api_key)


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Verdandi — autonomous product validation factory."""
    ctx.ensure_object(dict)
    settings = Settings()
    log_level = "DEBUG" if verbose else settings.log_level
    configure_logging(log_level=log_level, log_format=settings.log_format)
    ctx.obj["settings"] = settings
    ctx.obj["verbose"] = verbose


@cli.command()
@click.option("--max-ideas", default=3, type=int, help="Number of ideas to discover")
@click.option(
    "--strategy",
    type=click.Choice(["auto", "disruption", "moonshot"], case_sensitive=False),
    default="auto",
    help="Discovery strategy: auto (portfolio-balanced), disruption, or moonshot",
)
@click.option("--dry-run", is_flag=True, help="Use mock data")
@click.pass_context
def discover(ctx: click.Context, max_ideas: int, strategy: str, dry_run: bool) -> None:
    """Discover new product ideas."""
    from verdandi.orchestrator import PipelineRunner

    strategy_override = None
    if strategy != "auto":
        from verdandi.strategies import DISRUPTION_STRATEGY, MOONSHOT_STRATEGY

        strategy_override = DISRUPTION_STRATEGY if strategy == "disruption" else MOONSHOT_STRATEGY

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
    db = _get_db(settings)
    try:
        exp_status = ExperimentStatus(status) if status else None
        experiments = db.list_experiments(exp_status)
        if not experiments:
            click.echo("No experiments found.")
            return
        for exp in experiments:
            click.echo(
                f"  [{exp.id}] {exp.status.value:16s} {exp.idea_title} (step {exp.current_step})"
            )
    finally:
        db.close()


@cli.command()
@click.argument("experiment_id", type=int)
@click.option("--step", type=str, default=None, help="Show specific step result")
@click.option("--log", "show_log", is_flag=True, help="Show pipeline log")
@click.pass_context
def inspect(ctx: click.Context, experiment_id: int, step: str | None, show_log: bool) -> None:
    """Inspect an experiment's results."""
    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        exp = db.get_experiment(experiment_id)
        if exp is None:
            click.echo(f"Experiment {experiment_id} not found.", err=True)
            sys.exit(1)

        click.echo(f"Experiment {exp.id}: {exp.idea_title}")
        click.echo(f"  Status: {exp.status.value}")
        click.echo(f"  Step: {exp.current_step}")
        click.echo(f"  Worker: {exp.worker_id}")

        if show_log:
            click.echo("\nPipeline Log:")
            for entry in db.get_log(experiment_id):
                click.echo(f"  [{entry['created_at']}] {entry['event']}: {entry['message']}")
        elif step:
            result = db.get_step_result(experiment_id, step)
            if result:
                click.echo(f"\nStep '{step}' result:")
                click.echo(json.dumps(result["data"], indent=2))
            else:
                click.echo(f"No result for step '{step}'")
        else:
            results = db.get_all_step_results(experiment_id)
            if results:
                click.echo("\nCompleted steps:")
                for r in results:
                    click.echo(f"  Step {r['step_number']}: {r['step_name']}")
    finally:
        db.close()


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
    db = _get_db(settings)
    try:
        exp = db.get_experiment(experiment_id)
        if exp is None:
            click.echo(f"Experiment {experiment_id} not found.", err=True)
            sys.exit(1)

        idea_result = db.get_step_result(experiment_id, "idea_discovery")
        research_result = db.get_step_result(experiment_id, "deep_research")
        scoring_result = db.get_step_result(experiment_id, "scoring")

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
            out(f"\n  SCORING \u2014 {score.total_score}/100 \u2192 {decision_str}")
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

        # --- Footer ---
        out(f"\n  {_DOUBLE_LINE}\n")

        if not mkt and not score:
            out("  Hint: run the pipeline further to generate research and scoring data.")
            out(f"    verdandi run {experiment_id}\n")

    finally:
        db.close()


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
    db = _get_db(settings)
    try:
        exp = db.get_experiment(experiment_id)
        if exp is None:
            click.echo(f"Experiment {experiment_id} not found.", err=True)
            sys.exit(1)

        db.update_experiment_review(experiment_id, approved=approve, notes=notes)
        action = "approved" if approve else "rejected"
        click.echo(f"Experiment {experiment_id} {action}.")
    finally:
        db.close()


@cli.command()
@click.option("--all-live", is_flag=True, help="Monitor all live experiments")
@click.pass_context
def monitor(ctx: click.Context, all_live: bool) -> None:
    """Show monitoring status for live experiments."""
    from verdandi.models.experiment import ExperimentStatus

    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        experiments = db.list_experiments(ExperimentStatus.RUNNING)
        if not experiments:
            click.echo("No running experiments.")
            return
        for exp in experiments:
            click.echo(f"  [{exp.id}] {exp.idea_title} — step {exp.current_step}")
    finally:
        db.close()


@cli.command()
@click.argument("experiment_id", type=int)
@click.pass_context
def archive(ctx: click.Context, experiment_id: int) -> None:
    """Archive an experiment."""
    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        db.archive_experiment(experiment_id)
        click.echo(f"Experiment {experiment_id} archived.")
    finally:
        db.close()


@cli.command()
@click.pass_context
def check(ctx: click.Context) -> None:
    """Verify which API keys are configured."""
    settings = ctx.obj["settings"]
    keys = {
        "Anthropic": bool(settings.anthropic_api_key),
        "Tavily": bool(settings.tavily_api_key),
        "Serper": bool(settings.serper_api_key),
        "Exa": bool(settings.exa_api_key),
        "Perplexity": bool(settings.perplexity_api_key),
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


@cli.group()
def cache() -> None:
    """Manage the research data cache (Redis)."""


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


@cli.command()
@click.option("--workers", default=4, type=int, help="Number of worker processes")
@click.pass_context
def worker(ctx: click.Context, workers: int) -> None:
    """Start Huey worker consumer."""
    from verdandi.orchestrator.scheduler import huey

    click.echo(f"Starting Huey consumer with {workers} workers...")
    consumer = huey.create_consumer(workers=workers)
    consumer.run()


@cli.group()
def enqueue() -> None:
    """Enqueue tasks to the worker queue."""


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
    from verdandi.orchestrator.coordination import TopicReservationManager

    settings = ctx.obj["settings"]
    db = _get_db(settings)
    try:
        mgr = TopicReservationManager(db.Session)
        rows = mgr.list_active() if active_only else mgr.list_all()
        if not rows:
            click.echo("No reservations found.")
            return
        for r in rows:
            click.echo(
                f"  [{r['id']}] {r['topic_key']} — worker={r['worker_id']} "
                f"expires={r.get('expires_at', 'N/A')}"
            )
    finally:
        db.close()


@cli.command()
@click.option("--host", type=str, default=None, help="Bind host")
@click.option("--port", type=int, default=None, help="Bind port")
@click.pass_context
def serve(ctx: click.Context, host: str | None, port: int | None) -> None:
    """Start the FastAPI API server."""
    import uvicorn

    settings = ctx.obj["settings"]
    uvicorn.run(
        "verdandi.api.app:create_app",
        factory=True,
        host=host or settings.api_host,
        port=port or settings.api_port,
    )
