from pydantic import UUID4
from sqlalchemy.exc import IntegrityError

from app.common.data.interfaces.exceptions import DuplicateValueError
from app.common.data.models import CollectionSchema, Grant, User
from app.extensions import db


def create_collection_schema(*, name: str, user: User, grant: Grant, version: int = 1) -> CollectionSchema:
    schema = CollectionSchema(name=name, created_by=user, grant=grant, version=version)
    db.session.add(schema)

    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return schema


def get_collection_schema(collection_id: UUID4) -> CollectionSchema:
    return db.session.get_one(CollectionSchema, collection_id)


def update_collection_schema(collection: CollectionSchema, *, name: str) -> CollectionSchema:
    collection.name = name
    try:
        db.session.flush()
    except IntegrityError as e:
        db.session.rollback()
        raise DuplicateValueError(e) from e
    return collection
