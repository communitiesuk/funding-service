import uuid
from typing import Mapping, Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import joinedload

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models import Grant, GrantRecipient, Organisation
from app.common.data.models_user import User, UserRole
from app.common.data.types import RoleEnum
from app.extensions import db


def get_grant_recipients(grant: "Grant", *, with_data_providers: bool = False) -> Sequence["GrantRecipient"]:
    stmt = select(GrantRecipient).where(GrantRecipient.grant_id == grant.id)

    if with_data_providers:
        stmt = stmt.options(joinedload(GrantRecipient.data_providers))

    return db.session.scalars(stmt).unique().all()


def get_grant_recipients_count(grant: "Grant") -> int:
    statement = select(func.count()).select_from(GrantRecipient).where(GrantRecipient.grant_id == grant.id)
    return db.session.scalar(statement) or 0


@flush_and_rollback_on_exceptions()
def create_grant_recipients(grant: "Grant", organisation_ids: list[uuid.UUID]) -> None:
    grant_recipients = []

    for organisation_id in organisation_ids:
        grant_recipients.append(GrantRecipient(grant_id=grant.id, organisation_id=organisation_id))

    db.session.add_all(grant_recipients)


def all_grant_recipients_have_data_providers(grant: "Grant") -> bool:
    grant_recipients = get_grant_recipients(grant, with_data_providers=True)

    if not grant_recipients:
        return False

    return all(grant_recipient.data_providers for grant_recipient in grant_recipients)


def get_grant_recipient_data_providers_count(grant: Grant) -> int:
    return sum(
        len(grant_recipient.data_providers) for grant_recipient in get_grant_recipients(grant, with_data_providers=True)
    )


def get_grant_recipient_data_providers_by_organisation(grant: Grant) -> dict[GrantRecipient, Sequence[User]]:
    grant_recipients = get_grant_recipients(grant, with_data_providers=True)

    return {grant_recipient: grant_recipient.data_providers for grant_recipient in grant_recipients}


def get_grant_recipient_data_provider_roles(grant: Grant) -> Sequence[UserRole]:
    """Get all grant recipient data provider roles for a grant."""
    statement = (
        select(UserRole)
        .join(User, UserRole.user_id == User.id)
        .join(Organisation, Organisation.id == UserRole.organisation_id)
        .where(
            UserRole.grant_id == grant.id,
            UserRole.permissions.contains([RoleEnum.DATA_PROVIDER]),
        )
    )

    return db.session.scalars(statement).all()


def get_grant_recipient_data_providers(grant: Grant) -> Mapping[GrantRecipient, Sequence[User]]:
    grant_recipients = get_grant_recipients(grant, with_data_providers=True)

    data_providers = {}
    for grant_recipient in grant_recipients:
        data_providers[grant_recipient] = grant_recipient.data_providers

    return data_providers
