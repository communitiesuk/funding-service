from typing import Sequence, cast
from uuid import UUID

from flask_login import current_user
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


def get_all_grants_by_user() -> Sequence[Grant]:
    user = cast(User, current_user)
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


def update_grant(grant: Grant, name: str) -> Grant:
    grant.name = name
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return grant
