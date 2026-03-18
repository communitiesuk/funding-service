import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.common.data.interfaces.exceptions import DuplicateDataSourceItemError, flush_and_rollback_on_exceptions
from app.common.data.models import DataSource, DataSourceItem, DataSourceOrganisationItem
from app.common.data.models_user import User
from app.common.data.types import (
    DataSourceSchema,
    DataSourceSchemaColumn,
    DataSourceType,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.utils import slugify
from app.constants import DATA_SET_EXTERNAL_ID_COLUMN_HEADER, DATA_SET_IDENTIFIER_COLUMN_HEADERS
from app.deliver_grant_funding.session_models import DataSetColumnMapping
from app.extensions import db


def get_data_source(
    data_source_id: uuid.UUID,
    *,
    with_organisation_items: bool = False,
    with_data_source_items: bool = False,
) -> DataSource:
    stmt = select(DataSource).where(DataSource.id == data_source_id)

    if with_organisation_items:
        stmt = stmt.options(selectinload(DataSource.organisation_items))

    if with_data_source_items:
        stmt = stmt.options(selectinload(DataSource.items))

    return db.session.execute(stmt).scalar_one()


def _build_schema_from_column_mappings(column_mappings: list[DataSetColumnMapping]) -> DataSourceSchema:
    schema_dict = {}
    for mapping in column_mappings:
        if mapping.data_type == QuestionDataType.NUMBER:
            presentation_options = QuestionPresentationOptions(
                prefix=mapping.prefix if mapping.prefix is not None else "",
                suffix=mapping.suffix if mapping.suffix is not None else "",
            )
            data_options = QuestionDataOptions(
                number_type=mapping.number_type,
                max_decimal_places=mapping.max_decimal_places if mapping.max_decimal_places is not None else None,
            )
        else:
            presentation_options = QuestionPresentationOptions()
            data_options = QuestionDataOptions()

        schema_dict[slugify(mapping.column_name)] = DataSourceSchemaColumn(
            data_type=mapping.data_type,
            presentation_options=presentation_options,
            data_options=data_options,
            original_column_name=mapping.column_name,
        )
    return DataSourceSchema.model_validate(schema_dict)


def _clean_value(val: str, mapping: DataSetColumnMapping) -> str | int | None:
    if not val:
        return None
    val = val.strip()
    if mapping.data_type != QuestionDataType.NUMBER or not val:
        return val

    if mapping.prefix:
        val = val.removeprefix(mapping.prefix)
    if mapping.suffix:
        val = val.removesuffix(mapping.suffix)
    val = val.replace(",", "").strip()

    if mapping.number_type == NumberTypeEnum.INTEGER:
        return int(val)
    elif mapping.number_type == NumberTypeEnum.DECIMAL:
        return str(Decimal(val))

    return val


def _build_data_blob(
    row: dict[str, str],
    mappings: dict[str, DataSetColumnMapping],
    identifier_columns: list[str],
) -> dict[str, str | int | None]:
    return {
        slugify(col): _clean_value(row.get(col, ""), mappings[col])
        for col in row
        if col not in identifier_columns and col in mappings
    }


def _create_organisation_items(
    data_source: DataSource,
    all_rows: list[dict[str, str]],
    column_mappings: list[DataSetColumnMapping],
    identifier_columns: list[str],
    is_project_level: bool = False,
) -> None:
    mappings = {m.column_name: m for m in column_mappings}
    grouped: dict[str, list[dict[str, str]]] = {}
    for row in all_rows:
        external_id = row.get(DATA_SET_EXTERNAL_ID_COLUMN_HEADER, "").strip()
        grouped.setdefault(external_id, []).append(row)

    for external_id, rows in grouped.items():
        data_blobs = [_build_data_blob(row, mappings, identifier_columns) for row in rows]
        item = DataSourceOrganisationItem(
            data_source_id=data_source.id,
            external_id=external_id,
            data=data_blobs if is_project_level else data_blobs[0],
        )
        data_source.organisation_items.append(item)
        db.session.add(item)


def _create_static_items(
    data_source: DataSource,
    all_rows: list[dict[str, str]],
    column_mappings: list[DataSetColumnMapping],
) -> None:
    key_col, value_col = column_mappings[0].column_name, column_mappings[1].column_name
    for idx, row in enumerate(all_rows):
        item = DataSourceItem(
            data_source_id=data_source.id,
            key=row.get(key_col, ""),
            label=row.get(value_col, ""),
            order=idx,
        )
        data_source.items.append(item)
        db.session.add(item)


@flush_and_rollback_on_exceptions(coerce_exceptions=[(IntegrityError, DuplicateDataSourceItemError)])
def create_uploaded_data_source(
    *,
    name: str,
    data_source_type: DataSourceType,
    grant_id: uuid.UUID | None,
    collection_id: uuid.UUID | None,
    column_mappings: list["DataSetColumnMapping"],
    all_rows: list[dict[str, str]],
    user: User,
) -> DataSource:
    schema = _build_schema_from_column_mappings(column_mappings).model_dump(mode="json", exclude_none=True)
    data_source = DataSource(
        name=name,
        type=data_source_type,
        grant_id=grant_id,
        collection_id=collection_id,
        schema=schema,
        created_by=user,
    )
    db.session.add(data_source)

    match data_source_type:
        case DataSourceType.GRANT_RECIPIENT:
            _create_organisation_items(data_source, all_rows, column_mappings, DATA_SET_IDENTIFIER_COLUMN_HEADERS)
        case DataSourceType.PROJECT_LEVEL:
            _create_organisation_items(
                data_source, all_rows, column_mappings, DATA_SET_IDENTIFIER_COLUMN_HEADERS, is_project_level=True
            )
        case DataSourceType.STATIC:
            _create_static_items(data_source, all_rows, column_mappings)
        case _:
            raise ValueError(f"Unsupported data source type: {data_source_type}")

    return data_source


@flush_and_rollback_on_exceptions
def delete_data_source(data_source: DataSource) -> None:
    # TODO: Add guardrails against deleting datasource where it's been used in a reference
    db.session.delete(data_source)
