from typing import Sequence, cast

from psycopg.errors import UniqueViolation
from pydantic.v1 import UUID4
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.common.data.models import Grant
from app.extensions import db


def get_grant(grant_id: UUID4) -> Grant | None:
    return db.get_session().get(Grant, grant_id)


def get_all_grants() -> Sequence[Grant]:
    statement = select(Grant).order_by(Grant.name)
    return db.get_session().scalars(statement).all()


def create_grant(name: str) -> Grant:
    # TODO update to use new request scoped session stuff once merged
    session = db.get_session()
    grant: Grant = Grant(name=name)
    try:
        session.add(grant)
        session.flush()
    except IntegrityError as e:
        session.rollback()
        raise DuplicateValueError(e) from e
    return grant


class DuplicateValueError(Exception):
    model_name: str | None
    field_name: str
    new_value: str

    constraint_name_map: dict[str, str] = {"uq_grant_name": "name"}

    def __init__(self, integrity_error: IntegrityError) -> None:
        diagnostics = cast(UniqueViolation, integrity_error.orig).diag
        self.model_name = diagnostics.table_name
        if not isinstance(diagnostics.constraint_name, str):
            raise ValueError("Diagnostic constraint_name must be a string")
        self.field_name = DuplicateValueError.constraint_name_map[diagnostics.constraint_name]
        if not isinstance(integrity_error.params, dict):
            raise ValueError("IntegrityError params must be a dict")
        self.new_value = integrity_error.params[self.field_name]


def update_grant(grant: Grant, name: str) -> Grant:
    session = db.get_session()
    grant.name = name
    try:
        session.flush()
    except IntegrityError as e:
        session.rollback()
        raise DuplicateValueError(e) from e
    return grant
