import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import cast

import psycopg
from flask import current_app
from pgqueuer import PgQueuer
from pgqueuer.db import PsycopgDriver
from pgqueuer.domain.types import QueueExecutionMode
from pgqueuer.models import Job, Schedule
from pgqueuer.queries import Queries
from sqlalchemy.engine import make_url

from app.common.data.interfaces.background_jobs import (
    SCAN_COLLECTION_OPEN_NOTIFICATION_EMAILS_SCHEDULE,
    SCAN_COLLECTION_OPENINGS_SCHEDULE,
    OpenCollectionForSubmissionsJob,
    SendCollectionOpenNotificationEmailsJob,
    enqueue_due_collection_open_notification_email_jobs,
    enqueue_due_collection_opening_jobs,
    open_collection_for_submissions,
)
from app.common.helpers.background_jobs import send_collection_open_notification_emails
from app.extensions import db

WORKER_ENTRYPOINTS = [
    OpenCollectionForSubmissionsJob.entrypoint,
    SendCollectionOpenNotificationEmailsJob.entrypoint,
]


def _pgqueuer_dsn() -> str:
    url = make_url(current_app.config["SQLALCHEMY_ENGINES"]["default"])
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


@asynccontextmanager
async def _pgqueuer() -> AsyncIterator[PgQueuer]:
    async with await psycopg.AsyncConnection.connect(_pgqueuer_dsn(), autocommit=True) as connection:
        pgq = PgQueuer(PsycopgDriver(connection))
        queries = cast(Queries, pgq.queries)

        @pgq.entrypoint(OpenCollectionForSubmissionsJob.entrypoint)
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

        @pgq.entrypoint(SendCollectionOpenNotificationEmailsJob.entrypoint)
        async def _send_collection_open_notification_emails(job: Job) -> None:
            if job.payload is None:
                raise ValueError(f"Job {job.id} has no payload")

            payload = SendCollectionOpenNotificationEmailsJob.model_validate_json(job.payload)
            current_app.logger.info(
                "Sending collection open emails for collection %(collection_id)s from pgqueuer job %(job_id)s",
                {"collection_id": payload.collection_id, "job_id": job.id},
            )
            with db.session.begin():
                sent_count = send_collection_open_notification_emails(payload)
            current_app.logger.info(
                (
                    "Sent %(sent_count)s collection open emails for collection %(collection_id)s "
                    "from pgqueuer job %(job_id)s"
                ),
                {"collection_id": payload.collection_id, "job_id": job.id, "sent_count": sent_count},
            )

        @pgq.schedule(SCAN_COLLECTION_OPENINGS_SCHEDULE, "* * * * *")
        async def _scan_collection_openings(schedule: Schedule) -> None:
            del schedule
            queued_count = await enqueue_due_collection_opening_jobs(queries)
            current_app.logger.info(
                "Queued %(queued_count)s collection opening jobs",
                {"queued_count": queued_count},
            )

        @pgq.schedule(SCAN_COLLECTION_OPEN_NOTIFICATION_EMAILS_SCHEDULE, "* * * * *")
        async def _scan_collection_open_notification_emails(schedule: Schedule) -> None:
            del schedule
            queued_count = await enqueue_due_collection_open_notification_email_jobs(queries)
            current_app.logger.info(
                "Queued %(queued_count)s collection open email jobs",
                {"queued_count": queued_count},
            )

        yield pgq


async def scan_due_background_jobs() -> int:
    async with await psycopg.AsyncConnection.connect(_pgqueuer_dsn(), autocommit=True) as connection:
        queries = Queries(PsycopgDriver(connection))
        collection_opening_jobs = await enqueue_due_collection_opening_jobs(queries)
        email_jobs = await enqueue_due_collection_open_notification_email_jobs(queries)
        return collection_opening_jobs + email_jobs


async def run_worker(*, once: bool, once_timeout_seconds: int) -> None:
    async with _pgqueuer() as pgq:
        queries = cast(Queries, pgq.queries)
        if once:
            if await queries.queued_work(WORKER_ENTRYPOINTS) == 0:
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
