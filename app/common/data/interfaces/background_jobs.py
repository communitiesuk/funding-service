import datetime
import uuid

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.common.data.models import BackgroundJob, Collection
from app.common.data.types import BackgroundJobStatusEnum, BackgroundJobTypeEnum, CollectionStatusEnum
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


def claim_next_due_background_job(*, now: datetime.datetime | None = None) -> BackgroundJob | None:
    now = now or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    job = db.session.scalar(
        select(BackgroundJob)
        .where(BackgroundJob.status == BackgroundJobStatusEnum.PENDING)
        .where(BackgroundJob.run_after_utc <= now)
        .order_by(BackgroundJob.run_after_utc, BackgroundJob.created_at_utc)
        .with_for_update(skip_locked=True)
        .limit(1)
    )
    if not job:
        return None

    job.status = BackgroundJobStatusEnum.RUNNING
    job.attempts += 1
    job.locked_at_utc = now
    return job


def mark_background_job_completed(job: BackgroundJob, *, now: datetime.datetime | None = None) -> None:
    now = now or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    job.status = BackgroundJobStatusEnum.COMPLETED
    job.completed_at_utc = now
    job.failed_at_utc = None
    job.last_error = None


def mark_background_job_failed(job: BackgroundJob, *, error: Exception, now: datetime.datetime | None = None) -> None:
    now = now or datetime.datetime.now(datetime.UTC).replace(tzinfo=None)
    job.status = BackgroundJobStatusEnum.FAILED
    job.failed_at_utc = now
    job.last_error = str(error)


def open_collection_for_submissions(job: BackgroundJob) -> None:
    from app.common.data.interfaces.collections import update_collection

    collection = job.collection
    if not collection:
        raise ValueError(f"Background job {job.id} has no collection")

    if collection.status == CollectionStatusEnum.OPEN:
        return

    if collection.status != CollectionStatusEnum.SCHEDULED:
        raise ValueError(
            f"Cannot open collection {collection.id} from status {collection.status.value}; expected Scheduled to open"
        )

    update_collection(collection, status=CollectionStatusEnum.OPEN)
