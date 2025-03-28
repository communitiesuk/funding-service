from typing import Sequence

from pydantic.v1 import UUID4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import Grant
from app.extensions import db_request_session


def get_grant(grant_id: UUID4) -> Grant | None:
    return db_request_session.request_session.get(Grant, grant_id)


def get_all_grants() -> Sequence[Grant]:
    statement = select(Grant).order_by(Grant.name)
    return db_request_session.request_session.scalars(statement).all()


def create_grant(name: str) -> Grant:
    session = db_request_session.request_session
    grant: Grant = Grant(name=name)
    try:
        session.add(grant)
        session.flush()
    except IntegrityError as e:
        session.rollback()
        raise DuplicateValueError(e) from e
    return grant


def update_grant(grant: Grant, name: str) -> Grant:
    session = db_request_session.request_session
    grant.name = name
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        raise DuplicateValueError(e) from e
    return grant
