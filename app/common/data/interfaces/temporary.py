"""
This module contains temporary functions that are used to support the scaffolding of the core platform functionality.

We anticipate that they should not be used by any of the real domains themselves (eg apply, assess, monitor), but are
required to support the technical build-out of the platform.

This file should be removed once the scaffolding is complete and some domain skins are in place.

The only place that should import from here is the `app.developers` package.
"""

from uuid import UUID

from app.common.data.models import (
    Collection,
    CollectionSchema,
    Grant,
)
from app.extensions import db


def delete_collections_created_by_user(*, grant_id: UUID, created_by_id: UUID) -> None:
    collections = (
        db.session.query(Collection)
        .join(CollectionSchema)
        .where(
            CollectionSchema.grant_id == grant_id,
            Collection.created_by_id == created_by_id,
        )
        .all()
    )

    for collection in collections:
        db.session.delete(collection)
    db.session.flush()


def delete_grant(grant_id: UUID) -> None:
    # Not optimised; do not lift+shift unedited.
    grant = db.session.query(Grant).where(Grant.id == grant_id).one()
    db.session.delete(grant)
    db.session.flush()
