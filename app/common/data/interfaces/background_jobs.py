import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.common.data.models import BackgroundJob, Collection
from app.common.data.types import BackgroundJobStatusEnum, BackgroundJobTypeEnum
from app.extensions import db


def open_collection_for_submissions_idempotency_key(collection: Collection) -> str:
    return f"collection:{collection.id}:open-for-submissions"


def enqueue_open_collection_for_submissions_job(collection: Collection) -> BackgroundJob:
    """Create the background job that will eventually open a scheduled collection.

    This is intentionally small for the PoC.
    """
    if not collection.submission_period_start_date:
        raise ValueError("Cannot enqueue open collection job without a submission period start date")

    idempotency_key = open_collection_for_submissions_idempotency_key(collection)
    run_after_utc = datetime.datetime.combine(
        collection.submission_period_start_date,
        datetime.time.min,
    )

    db.session.execute(
        insert(BackgroundJob)
        .values(
            id=uuid.uuid4(),
            job_type=BackgroundJobTypeEnum.OPEN_COLLECTION_FOR_SUBMISSIONS,
            status=BackgroundJobStatusEnum.PENDING,
            idempotency_key=idempotency_key,
            payload={"collection_id": str(collection.id)},
            run_after_utc=run_after_utc,
            collection_id=collection.id,
        )
        .on_conflict_do_nothing(index_elements=["idempotency_key"])
    )
    job = db.session.scalar(select(BackgroundJob).where(BackgroundJob.idempotency_key == idempotency_key))
    if not job:
        raise RuntimeError(f"Could not enqueue or find background job for {idempotency_key}")
    return job
