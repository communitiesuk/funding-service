import asyncio
import uuid

import psycopg
from flask import Flask
from pgqueuer.db import PsycopgDriver
from pgqueuer.queries import Queries
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.common.data.interfaces.background_jobs import SendCollectionOpenNotificationEmailsJob, enqueue
from app.extensions import db


def _pgqueuer_dsn(app: Flask) -> str:
    url = make_url(app.config["SQLALCHEMY_ENGINES"]["default"])
    return url.set(drivername="postgresql").render_as_string(hide_password=False)


async def _enqueue_with_pgqueuer(app: Flask, job: SendCollectionOpenNotificationEmailsJob) -> bool:
    async with await psycopg.AsyncConnection.connect(_pgqueuer_dsn(app), autocommit=True) as connection:
        queries = Queries(PsycopgDriver(connection))
        return await enqueue(queries, job)


def test_async_pgqueuer_enqueue_is_visible_to_the_sync_db_session(app: Flask, db_session: Session) -> None:
    # This is mostly here to prove that the async pgqueuer bits can live alongside the rest of our sync Flask/SQLAlchemy
    # test setup. pgqueuer uses its own psycopg connection, so it doesn't participate in the db_session transaction that
    # most integration tests rely on. That is fine, but it means two things:
    # - if the async side needs to see data created by db_session, that data has to have been flushed/committed first
    # - anything written by pgqueuer needs cleaning up explicitly, because the normal test rollback won't catch it
    job = SendCollectionOpenNotificationEmailsJob(collection_id=uuid.uuid4())

    try:
        queued = asyncio.run(_enqueue_with_pgqueuer(app, job))

        queued_job = (
            db_session.execute(
                text(
                    """
                    SELECT entrypoint, payload
                    FROM pgqueuer
                    WHERE dedupe_key = :dedupe_key
                    """
                ),
                {"dedupe_key": job.dedupe_key},
            )
            .mappings()
            .one()
        )

        assert queued is True
        assert queued_job["entrypoint"] == job.entrypoint
        assert SendCollectionOpenNotificationEmailsJob.model_validate_json(queued_job["payload"]) == job
    finally:
        # pgqueuer writes through its own connection, outside the test transaction managed by db_session
        with db.engine.begin() as connection:
            connection.execute(
                text("DELETE FROM pgqueuer WHERE dedupe_key = :dedupe_key"), {"dedupe_key": job.dedupe_key}
            )
