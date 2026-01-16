from typing import Any, Iterable, Sequence
from uuid import UUID

from sqlalchemy import ScalarResult, select
from sqlalchemy.dialects.postgresql import insert as postgresql_upsert

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
from app.common.data.models import UploadedDataset
from app.extensions import db


@flush_and_rollback_on_exceptions
def create_uploaded_dataset(
    *, name: str, grant_id: UUID | None, data: Iterable[dict[str, Any]], schema: Iterable[tuple[Any, Any]]
) -> ScalarResult[UploadedDataset]:
    dataset = db.session.scalars(
        postgresql_upsert(UploadedDataset)
        .values(
            name=name,
            grant_id=grant_id,
            data=list(data),
            schema=dict(schema),
        )
        .on_conflict_do_update(
            index_elements=["name"],
            set_={
                "grant_id": grant_id,
                "data": list(data),
                "schema": dict(schema),
            },
        )
        .returning(UploadedDataset),
        execution_options={"populate_existing": True},
    )
    return dataset


def get_uploaded_dataset(dataset_id: UUID) -> UploadedDataset:
    return db.session.get_one(UploadedDataset, dataset_id)


def get_all_uploaded_datasets() -> Sequence[UploadedDataset]:
    statement = select(UploadedDataset).order_by(UploadedDataset.name)
    return db.session.scalars(statement).all()
