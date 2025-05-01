from app.common.data.models import Schema, User
from app.extensions import db


def create_schema(name: str, user: User) -> Schema:
    schema = Schema(name=name, user=user)
    db.session.add(schema)
    db.session.flush()
    return schema
