import asyncio

import click

from app.background_jobs import background_jobs_blueprint
from app.background_jobs.worker import run_worker, scan_due_background_jobs


@background_jobs_blueprint.cli.command(
    "scan",
    help="Local dev helper: scan current app state and enqueue due background jobs",
)
def scan() -> None:
    queued_count = asyncio.run(scan_due_background_jobs())
    click.echo(f"Queued {queued_count} background jobs")


@background_jobs_blueprint.cli.command(
    "worker",
    help="Run the pgqueuer background worker. In production this is the ECS service entrypoint.",
)
@click.option("--once", is_flag=True, help="Local dev helper: process currently queued jobs once, then exit")
@click.option("--once-timeout-seconds", default=30, show_default=True, help="Maximum runtime when using --once")
def worker(once: bool, once_timeout_seconds: int) -> None:
    asyncio.run(run_worker(once=once, once_timeout_seconds=once_timeout_seconds))
