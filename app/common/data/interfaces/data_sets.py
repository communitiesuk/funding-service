from decimal import Decimal

from app.common.data.interfaces.exceptions import flush_and_rollback_on_exceptions
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
from app.deliver_grant_funding.session_models import DataSetColumnMapping
from app.extensions import db


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
        external_id = row.get("ONS code", "").strip()
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
    if len(column_mappings) != 2:
        raise ValueError("STATIC data sources must have exactly two columns")
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


@flush_and_rollback_on_exceptions
def create_uploaded_data_source(
    *,
    name: str,
    data_source_type: DataSourceType,
    grant_id: str | None,
    collection_id: str | None,
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
        schema=schema if data_source_type != DataSourceType.STATIC else None,
        created_by=user,
    )
    db.session.add(data_source)

    identifier_columns = ["ONS code", "Grant recipient"]

    match data_source_type:
        case DataSourceType.GRANT_RECIPIENT:
            _create_organisation_items(data_source, all_rows, column_mappings, identifier_columns)
        case DataSourceType.PROJECT_LEVEL:
            _create_organisation_items(
                data_source, all_rows, column_mappings, identifier_columns, is_project_level=True
            )
        case DataSourceType.STATIC:
            _create_static_items(data_source, all_rows, column_mappings)
        case _:
            raise ValueError(f"Unsupported data source type: {data_source_type}")

    return data_source
