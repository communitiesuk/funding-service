import uuid
from typing import Sequence

from sqlalchemy import and_, delete, func, select

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models import Grant, GrantRecipient, Organisation
from app.common.data.models_user import User, UserRole
from app.common.data.types import RoleEnum
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


def all_grant_recipients_have_users(grant: "Grant") -> bool:
    grant_recipients = get_grant_recipients(grant)

    if not grant_recipients:
        return False

    for grant_recipient in grant_recipients:
        user_count = db.session.scalar(
            select(func.count())
            .select_from(UserRole)
            .join(UserRole.organisation)
            .where(
                UserRole.grant_id == grant.id,
                UserRole.organisation_id == grant_recipient.organisation_id,
                Organisation.can_manage_grants.is_(False),
                UserRole.role == RoleEnum.MEMBER,  # TODO: might become a 'DATA_PROVIDER' permission with Access work
            )
        )
        if not user_count or user_count == 0:
            return False

    return True


def get_grant_recipient_users_count(grant: Grant) -> int:
    statement = (
        select(func.count())
        .select_from(UserRole)
        .join(UserRole.organisation)
        .where(
            Organisation.can_manage_grants.is_(False),
            UserRole.grant_id == grant.id,
            UserRole.role == RoleEnum.MEMBER,  # TODO: might become a 'DATA_PROVIDER' permission with Access work
        )
    )
    return db.session.scalar(statement) or 0


def get_grant_recipient_users_by_organisation(grant: Grant) -> dict[GrantRecipient, Sequence[User]]:
    grant_recipients = get_grant_recipients(grant)
    result = {}

    for grant_recipient in grant_recipients:
        statement = (
            select(User)
            .join(UserRole)
            .join(UserRole.organisation)
            .where(
                Organisation.can_manage_grants.is_(False),
                UserRole.organisation_id == grant_recipient.organisation_id,
                UserRole.grant_id == grant.id,
                UserRole.role == RoleEnum.MEMBER,  # TODO: might become a 'DATA_PROVIDER' permission with Access work
            )
        )
        users = db.session.scalars(statement).all()
        result[grant_recipient] = users

    return result


def get_grant_recipient_user_roles(grant: Grant) -> Sequence[UserRole]:
    """Get all grant recipient user roles for a grant.

    Returns tuples of (user_id, organisation_id, user_name, user_email, organisation_name).
    """
    statement = (
        select(UserRole)
        .join(User, UserRole.user_id == User.id)
        .join(Organisation, Organisation.id == UserRole.organisation_id)
        .where(
            UserRole.grant_id == grant.id,
            UserRole.role == RoleEnum.MEMBER,  # TODO: might become a 'DATA_PROVIDER' permission with Access work
        )
    )

    return db.session.scalars(statement).all()


@flush_and_rollback_on_exceptions
def revoke_grant_recipient_user_role(user_id: uuid.UUID, organisation_id: uuid.UUID, grant_id: uuid.UUID) -> bool:
    subquery = (
        select(UserRole.id)
        .join(UserRole.organisation)
        .where(
            and_(
                UserRole.user_id == user_id,
                UserRole.organisation_id == organisation_id,
                Organisation.can_manage_grants.is_(False),
                UserRole.grant_id == grant_id,
                UserRole.role == RoleEnum.MEMBER,  # TODO: might become a 'DATA_PROVIDER' permission with Access work
            )
        )
    )

    statement = delete(UserRole).where(UserRole.id.in_(subquery))
    result = db.session.execute(statement)
    db.session.flush()

    user = db.session.get(User, user_id)
    if user:
        db.session.expire(user)

    return bool(result.rowcount > 0)  # type: ignore[attr-defined]
