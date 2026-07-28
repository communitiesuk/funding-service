from collections.abc import Sequence

from app.common.data.models import ReleaseNote
from app.extensions import db


def get_published_release_notes() -> Sequence[ReleaseNote]:
    return (
        db.session.query(ReleaseNote)
        .where(ReleaseNote.is_published.is_(True))
        .order_by(ReleaseNote.release_date.desc())
        .all()
    )
