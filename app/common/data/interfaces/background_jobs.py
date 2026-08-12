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

    @property
    def dedupe_key(self) -> str:
        return f"{OPEN_COLLECTION_FOR_SUBMISSIONS_ENTRYPOINT}:{self.collection_id}"


def get_collection_ids_due_to_open(*, today: datetime.date | None = None) -> Sequence[uuid.UUID]:
    today = today or datetime.datetime.now(datetime.UTC).date()
    statement = (
        select(Collection.id)
        .join(Collection.grant)
        .where(
            Collection.status == CollectionStatusEnum.SCHEDULED,
            Collection.submission_period_start_date.isnot(None),
            Collection.submission_period_start_date <= today,
            Grant.status == GrantStatusEnum.LIVE,
        )
        .order_by(Collection.submission_period_start_date, Collection.created_at_utc)
    )
    return db.session.scalars(statement).all()


async def enqueue_open_collection_for_submissions_job(
    queries: Queries,
    job: OpenCollectionForSubmissionsJob,
) -> bool:
    job_ids = await queries.enqueue(
        OPEN_COLLECTION_FOR_SUBMISSIONS_ENTRYPOINT,
        job.model_dump_json().encode(),
        dedupe_key=job.dedupe_key,
        on_conflict="skip",
    )
    return job_ids[0] is not None


async def enqueue_due_collection_opening_jobs(queries: Queries) -> int:
    queued_count = 0
    jobs = [
        OpenCollectionForSubmissionsJob(collection_id=collection_id)
        for collection_id in get_collection_ids_due_to_open()
    ]

    for job in jobs:
        if await enqueue_open_collection_for_submissions_job(queries, job):
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
