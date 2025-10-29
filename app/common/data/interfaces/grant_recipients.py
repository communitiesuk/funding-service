import uuid
from typing import Sequence

from sqlalchemy import func, select

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models import Grant, GrantRecipient
from app.extensions import db


def get_grant_recipients(grant: "Grant") -> Sequence["GrantRecipient"]:
    return db.session.scalars(select(GrantRecipient).where(GrantRecipient.grant_id == grant.id)).all()


def get_grant_recipients_count(grant: "Grant") -> int:
    statement = select(func.count()).select_from(GrantRecipient).where(GrantRecipient.grant_id == grant.id)
    return db.session.scalar(statement) or 0


@flush_and_rollback_on_exceptions()
def create_grant_recipients(grant: "Grant", organisation_ids: list[uuid.UUID]) -> None:
    grant_recipients = []

    for organisation_id in organisation_ids:
        grant_recipients.append(GrantRecipient(grant_id=grant.id, organisation_id=organisation_id))

    db.session.add_all(grant_recipients)
