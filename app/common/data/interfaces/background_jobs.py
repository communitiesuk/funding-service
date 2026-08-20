import datetime
import uuid
from collections.abc import Sequence
from typing import ClassVar

from pgqueuer.queries import Queries
from pydantic import BaseModel
from sqlalchemy import or_, select

from app.common.data.interfaces.collections import get_collection, update_collection
from app.common.data.models import Collection, Grant, GrantRecipient
from app.common.data.models_user import UserRole
from app.common.data.types import CollectionStatusEnum, GrantRecipientModeEnum, GrantStatusEnum, RoleEnum
from app.extensions import db

SCAN_COLLECTION_OPENINGS_SCHEDULE = "scan_collection_openings"
SCAN_COLLECTION_OPEN_NOTIFICATION_EMAILS_SCHEDULE = "scan_collection_open_notification_emails"


class OpenCollectionForSubmissionsJob(BaseModel):
    entrypoint: ClassVar[str] = "open_collection_for_submissions"

    collection_id: uuid.UUID

    @property
    def dedupe_key(self) -> str:
        return f"{self.entrypoint}:{self.collection_id}"


class SendCollectionOpenNotificationEmailsJob(BaseModel):
    entrypoint: ClassVar[str] = "send_collection_open_notification_emails"

    collection_id: uuid.UUID

    @property
    def dedupe_key(self) -> str:
        return f"{self.entrypoint}:{self.collection_id}"


type BackgroundJob = OpenCollectionForSubmissionsJob | SendCollectionOpenNotificationEmailsJob


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


def get_collection_ids_due_open_notification_emails() -> Sequence[uuid.UUID]:
    has_data_providers = (
        select(UserRole.id)
        .join(GrantRecipient, GrantRecipient.organisation_id == UserRole.organisation_id)
        .where(
            GrantRecipient.grant_id == Collection.grant_id,
            GrantRecipient.mode == GrantRecipientModeEnum.LIVE,
            or_(UserRole.grant_id.is_(None), UserRole.grant_id == Collection.grant_id),
            UserRole.permissions.contains([RoleEnum.DATA_PROVIDER]),
        )
    )

    statement = (
        select(Collection.id)
        .join(Collection.grant)
        .where(
            Collection.status == CollectionStatusEnum.OPEN,
            Collection.collection_open_notification_sent_at_utc.is_(None),
            Grant.status == GrantStatusEnum.LIVE,
            has_data_providers.exists(),
        )
        .order_by(Collection.submission_period_start_date, Collection.created_at_utc)
    )
    return db.session.scalars(statement).all()


async def enqueue(queries: Queries, job: BackgroundJob) -> bool:
    job_ids = await queries.enqueue(
        job.entrypoint,
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
        if await enqueue(queries, job):
            queued_count += 1

    return queued_count


async def enqueue_due_collection_open_notification_email_jobs(queries: Queries) -> int:
    queued_count = 0
    jobs = [
        SendCollectionOpenNotificationEmailsJob(collection_id=collection_id)
        for collection_id in get_collection_ids_due_open_notification_emails()
    ]

    for job in jobs:
        if await enqueue(queries, job):
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


def mark_collection_open_notification_emails_sent(job: SendCollectionOpenNotificationEmailsJob) -> None:
    collection = get_collection(job.collection_id)
    collection.collection_open_notification_sent_at_utc = datetime.datetime.now(datetime.UTC)
