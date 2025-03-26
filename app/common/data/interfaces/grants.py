from pydantic.v1 import UUID4

from app.common.data.models import Grant
from app.extensions import db


def get_grant(grant_id: UUID4) -> Grant | None:
    return db.get_session().get(Grant, grant_id)


def add_grant(name: str) -> Grant:
    # TODO update to use new request scoped session stuff once merged
    session = db.get_session()
    grant: Grant = Grant(name=name)
    session.add(grant)
    session.flush()
    return grant
