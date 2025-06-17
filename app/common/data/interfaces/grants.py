from enum import Enum
from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import Grant
from app.common.data.models_user import User
from app.extensions import db


def get_grant(grant_id: UUID) -> Grant:
    return db.session.get_one(Grant, grant_id)


def grant_name_exists(name: str) -> bool:
    statement = select(Grant).where(Grant.name == name)
    grant = db.session.scalar(statement)
    return grant is not None


def get_all_grants_by_user(user: User) -> Sequence[Grant]:
    if user.is_platform_admin:
        statement = select(Grant).order_by(Grant.name)
        return db.session.scalars(statement).all()
    else:
        grant_ids = [role.grant_id for role in user.roles]
        if not grant_ids:
            return []
        statement = select(Grant).where(Grant.id.in_(grant_ids)).order_by(Grant.name)
        return db.session.scalars(statement).all()


def get_all_grants() -> Sequence[Grant]:
    statement = select(Grant).order_by(Grant.name)
    return db.session.scalars(statement).all()


def create_grant(
    *,
    name: str,
    description: str,
    primary_contact_name: str,
    primary_contact_email: str,
    ggis_number: str | None = None,
) -> Grant:
    grant: Grant = Grant(
        name=name,
        ggis_number=ggis_number,
        description=description,
        primary_contact_name=primary_contact_name,
        primary_contact_email=primary_contact_email,
    )
    db.session.add(grant)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return grant


class _NotProvided(Enum):
    token = 0


NOT_PROVIDED = _NotProvided.token


def update_grant(
    grant: Grant,
    *,
    name: str | _NotProvided = NOT_PROVIDED,
    description: str | _NotProvided = NOT_PROVIDED,
    primary_contact_name: str | _NotProvided = NOT_PROVIDED,
    primary_contact_email: str | _NotProvided = NOT_PROVIDED,
    ggis_number: str | None | _NotProvided = NOT_PROVIDED,
) -> Grant:
    if name is not NOT_PROVIDED:
        grant.name = name
    if description is not NOT_PROVIDED:
        grant.description = description
    if primary_contact_name is not NOT_PROVIDED:
        grant.primary_contact_name = primary_contact_name
    if primary_contact_email is not NOT_PROVIDED:
        grant.primary_contact_email = primary_contact_email
    if ggis_number is not NOT_PROVIDED:
        grant.ggis_number = ggis_number
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return grant
