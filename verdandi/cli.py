"""Click CLI entry point for Verdandi."""

from __future__ import annotations

import json
import sys

import click

from verdandi.config import Settings
from verdandi.db import Database
from verdandi.logging import configure_logging


def _get_db(settings: Settings) -> Database:
    settings.ensure_data_dir()
    db = Database(settings.db_path)
    db.init_schema()
    return db


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
        runner = PipelineRunner(db=db, settings=settings, dry_run=dry_run)
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
        runner = PipelineRunner(db=db, settings=settings, dry_run=dry_run)
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
        runner = PipelineRunner(db=db, settings=settings, dry_run=dry_run)

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
    from verdandi.tasks import huey

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
    from verdandi.tasks import discover_ideas_task

    result = discover_ideas_task(max_ideas=max_ideas, dry_run=dry_run)
    click.echo(f"Discovery task enqueued: {result}")


@enqueue.command("run")
@click.argument("experiment_id", type=int)
@click.option("--stop-after", "stop_after", type=int, default=None, help="Stop after step N")
@click.option("--dry-run", is_flag=True)
def enqueue_run(experiment_id: int, stop_after: int | None, dry_run: bool) -> None:
    """Enqueue a pipeline run task."""
    from verdandi.tasks import run_pipeline_task

    result = run_pipeline_task(experiment_id=experiment_id, dry_run=dry_run, stop_after=stop_after)
    click.echo(f"Pipeline task enqueued: {result}")


@cli.command()
@click.option("--active-only/--all", default=True, help="Show only active reservations")
@click.pass_context
def reservations(ctx: click.Context, active_only: bool) -> None:
    """Show topic reservations."""
    from verdandi.coordination import TopicReservationManager

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
