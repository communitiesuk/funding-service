import csv
import io
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from io import StringIO
from typing import TYPE_CHECKING, Sequence

from flask import current_app
from pydantic import BaseModel, Field
from werkzeug.datastructures import FileStorage

from app.common.data.interfaces.grant_recipients import get_grant_recipients
from app.common.data.types import (
    DataSourceFileMetadata,
    DataSourceFileTagEnum,
    DataSourceType,
    GrantRecipientMismatch,
    NumberTypeEnum,
    OrganisationModeEnum,
    QuestionDataType,
    TUnvalidatedDataSetRow,
    TUnvalidatedDataSetRows,
)
from app.constants import (
    DATA_SET_EXTERNAL_ID_COLUMN_HEADER,
    DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER,
    DATA_SET_IDENTIFIER_COLUMN_HEADERS,
)
from app.deliver_grant_funding.session_models import DataSetColumnMapping, DataSetUploadSessionModel
from app.extensions import s3_service

if TYPE_CHECKING:
    from app.common.data.models import DataSource, DataSourceOrganisationItem, GrantRecipient


class CellError(BaseModel):
    column: str
    table_message: str


class PrefixError(CellError):
    table_message: str = "Incorrect prefix"
    prefix: str


class SuffixError(CellError):
    table_message: str = "Incorrect suffix"
    suffix: str


class DecimalError(CellError):
    table_message: str = "Too many decimal places"
    max_decimal_places: int


class DataTypeError(CellError):
    table_message: str = "Incorrect data type"
    expected_type: QuestionDataType | NumberTypeEnum


class BritishPoundsError(CellError):
    table_message: str = "Not valid British pounds"


class RowValidationResult(BaseModel):
    row_number: int
    cell_errors: list[CellError] = Field(default_factory=list)


class DataSetValidationResult(BaseModel):
    row_results: list[RowValidationResult] = Field(default_factory=list)

    @property
    def blocking_errors(self) -> list[CellError]:
        return [e for r in self.row_results for e in r.cell_errors]


def _validate_decimal(stripped: str, mapping: DataSetColumnMapping, column: str) -> list[CellError]:
    errors: list[CellError] = []
    decimal_places = len(stripped.split(".")[1]) if "." in stripped else 0
    if mapping.max_decimal_places is not None and decimal_places > mapping.max_decimal_places:
        errors.append(DecimalError(column=column, max_decimal_places=mapping.max_decimal_places))
    try:
        Decimal(stripped)
    except InvalidOperation:
        errors.append(DataTypeError(column=column, expected_type=NumberTypeEnum.DECIMAL))
    return errors


def validate_csv_cell_against_column_mapping(column: str, value: str, mapping: DataSetColumnMapping) -> list[CellError]:
    if mapping.data_type != QuestionDataType.NUMBER:
        return []

    errors: list[CellError] = []
    stripped = value.strip()

    if mapping.prefix:
        stripped = stripped.removeprefix(mapping.prefix)

    if mapping.suffix:
        stripped = stripped.removesuffix(mapping.suffix)

    stripped = stripped.replace(",", "").strip()

    if mapping.suffix or mapping.prefix:
        try:
            Decimal(stripped)
        except InvalidOperation:
            if mapping.prefix:
                errors.append(PrefixError(column=column, prefix=mapping.prefix))
            if mapping.suffix:
                errors.append(SuffixError(column=column, suffix=mapping.suffix))

    if mapping.number_type == NumberTypeEnum.INTEGER:
        if not stripped.lstrip("-").isdigit():
            errors.append(DataTypeError(column=column, expected_type=NumberTypeEnum.INTEGER))

    if mapping.number_type == NumberTypeEnum.DECIMAL:
        errors.extend(_validate_decimal(stripped, mapping, column))

    if mapping.column_type == "BRITISH_POUNDS" and errors:
        return [BritishPoundsError(column=column)]

    return errors


def _validate_row(row: TUnvalidatedDataSetRow, idx: int, data_set: DataSetUploadSessionModel) -> RowValidationResult:
    result = RowValidationResult(row_number=idx)

    for column in data_set.data_columns:
        value = row.get(column, "").strip()
        mapping = data_set.get_column_mapping(column)

        if value and mapping:
            result.cell_errors.extend(validate_csv_cell_against_column_mapping(column, value, mapping))

    return result


def validate_data_set_grant_recipients(
    data_set: DataSetUploadSessionModel, grant_recipients: Sequence[GrantRecipient], all_rows: TUnvalidatedDataSetRows
) -> list[str]:
    errors: list[str] = []
    external_ids = {gr.organisation.external_id for gr in grant_recipients}
    seen_external_ids: set[str] = set()

    for idx, row in enumerate(all_rows):
        external_id = row.get(DATA_SET_EXTERNAL_ID_COLUMN_HEADER, "").strip()
        recipient = row.get(DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER, "").strip()

        if not external_id and not recipient:
            row_has_data = any(row.get(col, "").strip() for col in data_set.data_columns)
            if row_has_data:
                errors.append(
                    f"Row {idx + 2}: Data is present but {DATA_SET_EXTERNAL_ID_COLUMN_HEADER} and grant recipient "
                    "are missing"
                )
            continue

        if bool(external_id) != bool(recipient):
            errors.append(
                f"Row {idx + 2}: Both {DATA_SET_EXTERNAL_ID_COLUMN_HEADER} and grant recipient name are required"
            )
            continue

        if external_id not in external_ids:
            errors.append(
                f"Row {idx + 2}: {DATA_SET_EXTERNAL_ID_COLUMN_HEADER} '{external_id}' not found in grant recipients"
            )
        elif external_id in seen_external_ids:
            errors.append(
                f"Row {idx + 2}: {DATA_SET_EXTERNAL_ID_COLUMN_HEADER} '{external_id}' already appears in the data set"
            )
        seen_external_ids.add(external_id)

    return errors


def validate_data_set(
    data_set: DataSetUploadSessionModel, all_rows: TUnvalidatedDataSetRows
) -> DataSetValidationResult:
    result = DataSetValidationResult()
    for idx, row in enumerate(all_rows):
        row_result = _validate_row(row, idx, data_set)
        if row_result.cell_errors:
            result.row_results.append(row_result)
    return result


def build_data_set_upload_s3_key(grant_id: uuid.UUID, collection_id: uuid.UUID, data_source_id: uuid.UUID) -> str:
    return f"{current_app.config['REFERENCE_FILES_PREFIX']}/{grant_id}/{collection_id}/{data_source_id}"


def find_grant_recipient_mismatches(
    all_rows: TUnvalidatedDataSetRows, grant_recipients: Sequence[GrantRecipient]
) -> list[GrantRecipientMismatch]:
    name_by_external_id = {gr.organisation.external_id: gr.organisation.name for gr in grant_recipients}
    mismatches = []
    for idx, row in enumerate(all_rows):
        external_id = row.get(DATA_SET_EXTERNAL_ID_COLUMN_HEADER, "").strip()
        csv_name = row.get(DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER, "").strip()
        service_name = name_by_external_id.get(external_id)
        if service_name and csv_name and service_name != csv_name:
            mismatches.append(
                GrantRecipientMismatch(
                    row_number=idx,
                    external_id=external_id,
                    csv_organisation_name=csv_name,
                    service_organisation_name=service_name,
                )
            )
    return mismatches


class MissingDataDisplayRow(BaseModel):
    external_id: str
    grant_recipient_name: str
    missing_columns: list[str] = Field(default_factory=list)
    grant_recipient_entirely_missing: bool = False
    row_number: int | None = None


def _get_grant_recipient_name_for_row(
    row: TUnvalidatedDataSetRow, grant_recipients: Sequence[GrantRecipient]
) -> str | None:
    external_id = row.get(DATA_SET_EXTERNAL_ID_COLUMN_HEADER, "").strip()
    organisation_name = next(
        (gr.organisation.name for gr in grant_recipients if gr.organisation.external_id == external_id),
        None,
    )
    return organisation_name


def build_data_display_rows_with_missing_tags(
    data_columns: list[str],
    all_rows: TUnvalidatedDataSetRows,
    grant_recipients: Sequence[GrantRecipient],
    include_all_grant_recipients: bool = False,
) -> list[MissingDataDisplayRow]:
    seen_external_ids: set[str] = set()
    display_rows: list[MissingDataDisplayRow] = []

    for idx, row in enumerate(all_rows):
        external_id = row.get(DATA_SET_EXTERNAL_ID_COLUMN_HEADER, "").strip()
        seen_external_ids.add(external_id)

        missing_columns = [col for col in data_columns if not row.get(col, "").strip()]
        if not missing_columns and not include_all_grant_recipients:
            continue

        name = _get_grant_recipient_name_for_row(row, grant_recipients) or row.get(
            DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER, ""
        )
        display_rows.append(
            MissingDataDisplayRow(
                external_id=external_id,
                grant_recipient_name=name,
                missing_columns=missing_columns,
                row_number=idx,
            )
        )

    for gr in grant_recipients:
        if gr.organisation.mode == OrganisationModeEnum.TEST:
            continue
        if gr.organisation.external_id not in seen_external_ids:
            display_rows.append(
                MissingDataDisplayRow(
                    external_id=gr.organisation.external_id,
                    grant_recipient_name=gr.organisation.name,
                    missing_columns=data_columns,
                    grant_recipient_entirely_missing=True,
                )
            )

    return sorted(display_rows, key=lambda r: r.grant_recipient_name)


@dataclass
class CurrentDataSetRow:
    external_id: str
    grant_recipient_name: str
    organisation_item: DataSourceOrganisationItem | None


@dataclass
class CurrentDataSetView:
    rows: list[CurrentDataSetRow]
    added_grant_recipient_names: list[str]
    removed_external_ids: list[str]


def build_current_data_set_view(
    data_source: DataSource, grant_recipients: Sequence[GrantRecipient]
) -> CurrentDataSetView:
    """
    Reflects a data source's organisation items against the grant's current live grant recipients.

    A grant recipient added to the grant since the data set was uploaded has no organisation item yet and
    appears as a row with no data. An organisation item belonging to a grant recipient who's since been removed
    from the grant is excluded from `rows` and reported via `removed_external_ids` instead.
    """
    items_by_external_id = data_source.get_organisation_items_by_external_id()
    rows = [
        CurrentDataSetRow(
            external_id=gr.organisation.external_id,
            grant_recipient_name=gr.organisation.name,
            organisation_item=items_by_external_id.get(gr.organisation.external_id),
        )
        for gr in sorted(grant_recipients, key=lambda gr: gr.organisation.name)
    ]

    return CurrentDataSetView(
        rows=rows,
        added_grant_recipient_names=sorted(row.grant_recipient_name for row in rows if row.organisation_item is None),
        removed_external_ids=sorted(data_source.get_removed_organisation_external_ids(grant_recipients)),
    )


def generate_latest_csv_template(data_source: DataSource) -> StringIO:
    if not data_source.type == DataSourceType.GRANT_RECIPIENT or not data_source.grant or not data_source.schema:
        raise NotImplementedError("Cannot generate latest CSV template for a non-grant recipient data source")

    headers = []
    headers += DATA_SET_IDENTIFIER_COLUMN_HEADERS
    for _, col_schema in data_source.schema.root.items():
        headers.append(col_schema.original_column_name)

    csv_output = StringIO()
    csv_writer = csv.DictWriter(csv_output, fieldnames=headers)
    csv_writer.writeheader()
    grant_recipients = get_grant_recipients(grant=data_source.grant, with_organisations=True)
    for gr in grant_recipients:
        if gr.organisation.mode == OrganisationModeEnum.TEST:
            continue

        row_data = {
            DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
            DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
        }
        organisation_data_item = data_source.get_filtered_organisation_item(
            organisation_external_id=gr.organisation.external_id
        )
        if organisation_data_item and organisation_data_item.data:
            for k, v in organisation_data_item.data.items():
                if not v:
                    continue
                row_data[data_source.schema.root[k].original_column_name] = str(v.get_value_for_evaluation())

        csv_writer.writerow(row_data)

    return csv_output


def upload_header_only_data_set_files(data_set: "DataSource") -> None:
    """Uploads a header-only CSV to S3 for a given data source after it's been copied

    `copy_collection` copies a data set's schema but not its rows' data or the original uploaded file, as the data may
    be collection-specific or sensitive. Upload a CSV containing just the column headers under a key owned by the new
    collection, so the copy's file metadata never points at the source collection's data.
    """
    if (
        not data_set.grant_id
        or not data_set.file_metadata
        or not data_set.schema
        or data_set.type != DataSourceType.GRANT_RECIPIENT
    ):
        raise ValueError("Cannot upload a non-grant-recipient data set")

    headers = DATA_SET_IDENTIFIER_COLUMN_HEADERS + [
        column.original_column_name for column in data_set.schema.root.values()
    ]
    header_csv = io.StringIO()
    csv.writer(header_csv).writerow(headers)

    new_key = build_data_set_upload_s3_key(data_set.grant_id, data_set.id, data_set.id)
    s3_service.upload_file(
        FileStorage(
            io.BytesIO(header_csv.getvalue().encode("utf-8")),
            filename=data_set.file_metadata.original_filename,
        ),
        new_key,
        {"status": DataSourceFileTagEnum.IN_USE},
    )
    data_set.file_metadata = DataSourceFileMetadata(
        s3_key=new_key,
        original_filename=data_set.file_metadata.original_filename,
    )
