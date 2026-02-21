"""
This module contains temporary functions that are used to support the scaffolding of the core platform functionality.

We anticipate that they should not be used by any of the real domains themselves (eg apply, assess, monitor), but are
required to support the technical build-out of the platform.

This file should be removed once the scaffolding is complete and some domain skins are in place.

The only place that should import from here is the `app.developers` package.
"""

from uuid import UUID

from sqlalchemy import select

from app.common.data.models import (
    Collection,
    Grant,
    Submission,
)
from app.common.data.models_user import User
from app.common.data.types import DataSourceType
from app.extensions import db


def delete_grant(grant_id: UUID) -> None:
    # Not optimised; do not lift+shift unedited.
    grant = db.session.query(Grant).where(Grant.id == grant_id).one()
    data_sources_to_delete = [
        c.data_source
        for collection in grant.collections
        for form in collection.forms
        for c in form._all_components
        if hasattr(c, "data_source") and c.data_source and c.data_source.type == DataSourceType.CUSTOM
    ]

    db.session.delete(grant)

    for ds in data_sources_to_delete:
        db.session.delete(ds)

    db.session.flush()


def get_submission_by_collection_and_user(collection: Collection, user: User) -> Submission | None:
    return db.session.scalar(
        select(Submission).where(Submission.collection == collection, Submission.created_by == user)
    )
