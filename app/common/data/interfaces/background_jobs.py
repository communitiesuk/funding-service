import datetime
import uuid
from collections.abc import Sequence

from pgqueuer.queries import Queries
from pydantic import BaseModel
from sqlalchemy import select

from app.common.data.interfaces.collections import get_collection, update_collection
from app.common.data.models import Collection, Grant
from app.common.data.types import CollectionStatusEnum, GrantStatusEnum
from app.extensions import db

OPEN_COLLECTION_FOR_SUBMISSIONS_ENTRYPOINT = "open_collection_for_submissions"
SCAN_COLLECTION_OPENINGS_SCHEDULE = "scan_collection_openings"


class OpenCollectionForSubmissionsJob(BaseModel):
    collection_id: uuid.UUID
    submission_period_start_date: datetime.date | None = None

    @property
    def dedupe_key(self) -> str:
        return f"{OPEN_COLLECTION_FOR_SUBMISSIONS_ENTRYPOINT}:{self.collection_id}"


def get_collections_to_schedule_opening() -> Sequence[Collection]:
    statement = (
        select(Collection)
        .join(Collection.grant)
        .where(
            Collection.status == CollectionStatusEnum.SCHEDULED,
            Collection.submission_period_start_date.isnot(None),
            Grant.status == GrantStatusEnum.LIVE,
        )
        .order_by(Collection.submission_period_start_date, Collection.created_at_utc)
    )
    return db.session.scalars(statement).unique().all()


def _execute_after_for_submission_start_date(submission_period_start_date: datetime.date) -> datetime.timedelta:
    run_at = datetime.datetime.combine(submission_period_start_date, datetime.time.min, tzinfo=datetime.UTC)
    return max(run_at - datetime.datetime.now(datetime.UTC), datetime.timedelta())


async def enqueue_or_update_open_collection_for_submissions_job(
    queries: Queries,
    job: OpenCollectionForSubmissionsJob,
) -> bool:
    if job.submission_period_start_date is None:
        raise ValueError("Cannot queue collection opening job without a submission start date")

    payload = job.model_dump_json().encode()
    execute_after = _execute_after_for_submission_start_date(job.submission_period_start_date)

    updated_rows = await queries.driver.fetch(
        """
        UPDATE pgqueuer
        SET
            payload = $1,
            execute_after = NOW() + $2::interval,
            updated = NOW()
        WHERE dedupe_key = $3
        AND entrypoint = $4
        AND status = 'queued'
        RETURNING id
        """,
        payload,
        execute_after,
        job.dedupe_key,
        OPEN_COLLECTION_FOR_SUBMISSIONS_ENTRYPOINT,
    )
    if updated_rows:
        return True

    job_ids = await queries.enqueue(
        OPEN_COLLECTION_FOR_SUBMISSIONS_ENTRYPOINT,
        payload,
        execute_after=execute_after,
        dedupe_key=job.dedupe_key,
        on_conflict="skip",
    )
    return job_ids[0] is not None


async def enqueue_collection_opening_jobs(queries: Queries) -> int:
    queued_count = 0
    jobs = [
        OpenCollectionForSubmissionsJob(
            collection_id=collection.id,
            submission_period_start_date=collection.submission_period_start_date,
        )
        for collection in get_collections_to_schedule_opening()
        if collection.submission_period_start_date
    ]
    db.session.rollback()

    for job in jobs:
        if await enqueue_or_update_open_collection_for_submissions_job(queries, job):
            queued_count += 1

    return queued_count


def open_collection_for_submissions(job: OpenCollectionForSubmissionsJob) -> bool:
    collection = get_collection(job.collection_id)

    if collection.status == CollectionStatusEnum.OPEN:
        return False

    if collection.status != CollectionStatusEnum.SCHEDULED:
        raise ValueError(
            f"Cannot open collection {collection.id} from status {collection.status.value}; expected Scheduled to open"
        )

    if collection.grant.status != GrantStatusEnum.LIVE:
        return False

    today = datetime.datetime.now(datetime.UTC).date()
    if collection.submission_period_start_date is None or collection.submission_period_start_date > today:
        return False

    update_collection(collection, status=CollectionStatusEnum.OPEN)
    return True
