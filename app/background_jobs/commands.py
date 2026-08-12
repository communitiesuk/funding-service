import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import cast

import click
import psycopg
from flask import current_app
from pgqueuer import PgQueuer
from pgqueuer.db import PsycopgDriver
from pgqueuer.domain.types import QueueExecutionMode
from pgqueuer.models import Job, Schedule
from pgqueuer.queries import Queries

from app.background_jobs import background_jobs_blueprint
from app.common.data.interfaces.background_jobs import (
    OPEN_COLLECTION_FOR_SUBMISSIONS_ENTRYPOINT,
    SCAN_COLLECTION_OPENINGS_SCHEDULE,
    OpenCollectionForSubmissionsJob,
    enqueue_collection_opening_jobs,
    open_collection_for_submissions,
)
from app.extensions import db


def _pgqueuer_dsn() -> str:
    return current_app.config["SQLALCHEMY_ENGINES"]["default"].replace("postgresql+psycopg://", "postgresql://", 1)


@asynccontextmanager
async def _pgqueuer() -> AsyncIterator[PgQueuer]:
    async with await psycopg.AsyncConnection.connect(_pgqueuer_dsn(), autocommit=True) as connection:
        pgq = PgQueuer(PsycopgDriver(connection))
        queries = cast(Queries, pgq.queries)

        @pgq.entrypoint(OPEN_COLLECTION_FOR_SUBMISSIONS_ENTRYPOINT)
        async def _open_collection_for_submissions(job: Job) -> None:
            if job.payload is None:
                raise ValueError(f"Job {job.id} has no payload")

            payload = OpenCollectionForSubmissionsJob.model_validate_json(job.payload)
            current_app.logger.info(
                "Opening collection %(collection_id)s from pgqueuer job %(job_id)s",
                {"collection_id": payload.collection_id, "job_id": job.id},
            )
            with db.session.begin():
                opened = open_collection_for_submissions(payload)
            if not opened:
                current_app.logger.info(
                    "Skipped opening collection %(collection_id)s from pgqueuer job %(job_id)s",
                    {"collection_id": payload.collection_id, "job_id": job.id},
                )

        @pgq.schedule(SCAN_COLLECTION_OPENINGS_SCHEDULE, "* * * * *")
        async def _scan_collection_openings(schedule: Schedule) -> None:
            del schedule
            queued_count = await enqueue_collection_opening_jobs(queries)
            current_app.logger.info(
                "Queued %(queued_count)s collection opening jobs",
                {"queued_count": queued_count},
            )

        yield pgq


async def _scan_jobs() -> int:
    async with await psycopg.AsyncConnection.connect(_pgqueuer_dsn(), autocommit=True) as connection:
        queries = Queries(PsycopgDriver(connection))
        return await enqueue_collection_opening_jobs(queries)


async def _ready_job_count(queries: Queries) -> int:
    rows = await queries.driver.fetch(
        """
        SELECT COUNT(*) AS count
        FROM pgqueuer
        WHERE status = 'queued'
        AND execute_after <= NOW()
        """
    )
    return rows[0]["count"]


async def _run_worker(*, once: bool, once_timeout_seconds: int) -> None:
    async with _pgqueuer() as pgq:
        queries = cast(Queries, pgq.queries)
        if once:
            if await _ready_job_count(queries) == 0:
                return
            try:
                await asyncio.wait_for(
                    pgq.qm.run(
                        mode=QueueExecutionMode.drain,
                        dequeue_timeout=timedelta(milliseconds=250),
                    ),
                    timeout=once_timeout_seconds,
                )
            except TimeoutError:
                pgq.shutdown.set()
                current_app.logger.info(
                    "Stopped one-off worker after %(seconds)s seconds", {"seconds": once_timeout_seconds}
                )
        else:
            await pgq.run(dequeue_timeout=timedelta(seconds=30))


@background_jobs_blueprint.cli.command("scan", help="Scan current app state and enqueue or update background jobs")
def scan() -> None:
    queued_count = asyncio.run(_scan_jobs())
    click.echo(f"Queued {queued_count} collection opening jobs")


@background_jobs_blueprint.cli.command("worker", help="Run the pgqueuer background worker")
@click.option("--once", is_flag=True, help="Process currently queued jobs once, then exit")
@click.option("--once-timeout-seconds", default=30, show_default=True, help="Maximum runtime when using --once")
def worker(once: bool, once_timeout_seconds: int) -> None:
    asyncio.run(_run_worker(once=once, once_timeout_seconds=once_timeout_seconds))
