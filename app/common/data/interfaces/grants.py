from typing import Sequence
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import Grant
from app.extensions import db


def get_grant(grant_id: UUID) -> Grant:
    return db.session.get_one(Grant, grant_id)


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
