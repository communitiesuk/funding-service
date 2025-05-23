"""
This module contains temporary functions that are used to support the scaffolding of the core platform functionality.

We anticipate that they should not be used by any of the real domains themselves (eg apply, assess, monitor), but are
required to support the technical build-out of the platform.

This file should be removed once the scaffolding is complete and some domain skins are in place.

The only place that should import from here is the `app.developers` package.
"""

from uuid import UUID

from sqlalchemy import delete

from app.common.data.models import (
    Collection,
    CollectionSchema,
)
from app.extensions import db


def delete_collections_created_by_user(*, grant_id: UUID, created_by_id: UUID) -> None:
    db.session.execute(
        delete(Collection).where(
            Collection.collection_schema_id == CollectionSchema.id,
            CollectionSchema.grant_id == grant_id,
            Collection.created_by_id == created_by_id,
        )
    )
    db.session.flush()
