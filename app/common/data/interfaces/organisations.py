from sqlalchemy import func, select

from app.common.data.models import Organisation
from app.extensions import db


def get_organisation_count() -> int:
    statement = select(func.count()).select_from(Organisation).where(Organisation.can_manage_grants.is_(False))
    return db.session.scalar(statement) or 0
