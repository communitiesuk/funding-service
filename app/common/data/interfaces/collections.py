from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import Grant, Schema, User
from app.extensions import db


def create_collection(name: str, user: User, grant: Grant) -> Schema:
    schema = Schema(name=name, created_by=user, grant=grant)
    db.session.add(schema)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return schema
