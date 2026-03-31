import uuid
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Sequence

from flask import current_app
from pydantic import BaseModel, Field

from app.common.data.types import (
    DataSourceType,
    NumberTypeEnum,
    QuestionDataType,
    TUnvalidatedDataSetRow,
    TUnvalidatedDataSetRows,
)
from app.constants import DATA_SET_EXTERNAL_ID_COLUMN_HEADER, DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER
from app.deliver_grant_funding.session_models import DataSetColumnMapping, DataSetUploadSessionModel

if TYPE_CHECKING:
    from app.common.data.models import GrantRecipient


class CellError(BaseModel):
    column: str
    table_message: str


class PrefixError(CellError):
    table_message: str = "Incorrect prefix"


class SuffixError(CellError):
    table_message: str = "Incorrect suffix"


class DecimalError(CellError):
    table_message: str = "Too many decimal places"


class DataTypeError(CellError):
    table_message: str = "Incorrect data type"


class RowValidationResult(BaseModel):
    row_number: int
    cell_errors: list[CellError] = Field(default_factory=list)
    missing_columns: list[str] = Field(default_factory=list)


class DataSetValidationResult(BaseModel):
    row_results: list[RowValidationResult] = Field(default_factory=list)

    @property
    def blocking_errors(self) -> list[CellError]:
        return [e for r in self.row_results for e in r.cell_errors]

    @property
    def missing_columns_by_row(self) -> dict[int, list[str]]:
        return {r.row_number: r.missing_columns for r in self.row_results if r.missing_columns}

    @property
    def has_missing_data(self) -> bool:
        return any(r.missing_columns for r in self.row_results)


def _validate_decimal(stripped: str, mapping: DataSetColumnMapping, column: str) -> list[CellError]:
    errors: list[CellError] = []
    decimal_places = len(stripped.split(".")[1]) if "." in stripped else 0
    if mapping.max_decimal_places is not None and decimal_places > mapping.max_decimal_places:
        errors.append(DecimalError(column=column))
    try:
        Decimal(stripped)
    except InvalidOperation:
        errors.append(DataTypeError(column=column))
    return errors


def _validate_cell(column: str, value: str, mapping: DataSetColumnMapping) -> list[CellError]:
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
                errors.append(PrefixError(column=column))
            if mapping.suffix:
                errors.append(SuffixError(column=column))

    if mapping.number_type == NumberTypeEnum.INTEGER:
        if not stripped.lstrip("-").isdigit():
            errors.append(DataTypeError(column=column))

    if mapping.number_type == NumberTypeEnum.DECIMAL:
        errors.extend(_validate_decimal(stripped, mapping, column))

    return errors


def _validate_row(row: TUnvalidatedDataSetRow, idx: int, data_set: DataSetUploadSessionModel) -> RowValidationResult:
    result = RowValidationResult(row_number=idx)

    for column in data_set.data_columns:
        value = row.get(column, "").strip()
        mapping = data_set.get_column_mapping(column)

        if not value:
            result.missing_columns.append(column)
        elif mapping:
            result.cell_errors.extend(_validate_cell(column, value, mapping))

    return result


class GrantRecipientComparison(BaseModel):
    external_id: str
    csv_name: str
    db_name: str

    @property
    def has_discrepancy(self) -> bool:
        return self.csv_name != self.db_name


def build_grant_recipient_comparison(
    grant_recipients: "Sequence[GrantRecipient]",
    all_rows: TUnvalidatedDataSetRows,
) -> list[GrantRecipientComparison]:
    external_id_to_name = {gr.organisation.external_id: gr.organisation.name for gr in grant_recipients}
    comparisons: list[GrantRecipientComparison] = []
    seen: set[str] = set()

    for row in all_rows:
        external_id = row.get(DATA_SET_EXTERNAL_ID_COLUMN_HEADER, "").strip()
        csv_name = row.get(DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER, "").strip()

        if not external_id or external_id not in external_id_to_name or external_id in seen:
            continue

        seen.add(external_id)
        comparisons.append(
            GrantRecipientComparison(
                external_id=external_id,
                csv_name=csv_name,
                db_name=external_id_to_name[external_id],
            )
        )

    return comparisons


def _check_grant_recipient_row(
    external_id: str,
    index: int,
    external_ids: set[str],
    seen_external_ids: set[str],
    check_duplicates: bool,
) -> list[str]:
    errors: list[str] = []

    if external_id not in external_ids:
        errors.append(
            f"Row {index + 2}: {DATA_SET_EXTERNAL_ID_COLUMN_HEADER} '{external_id}' not found in grant recipients"
        )
    elif check_duplicates and external_id in seen_external_ids:
        errors.append(
            f"Row {index + 2}: {DATA_SET_EXTERNAL_ID_COLUMN_HEADER} '{external_id}' already appears in the data set"
        )

    return errors


def validate_data_set_grant_recipients(
    data_set: DataSetUploadSessionModel, grant_recipients: Sequence[GrantRecipient], all_rows: TUnvalidatedDataSetRows
) -> list[str]:
    if data_set.data_source_type == DataSourceType.STATIC:
        return []

    errors: list[str] = []
    external_ids = {gr.organisation.external_id for gr in grant_recipients}
    seen_external_ids: set[str] = set()
    check_duplicates = data_set.data_source_type == DataSourceType.GRANT_RECIPIENT

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

        errors.extend(
            _check_grant_recipient_row(
                external_id,
                idx,
                external_ids,
                seen_external_ids,
                check_duplicates,
            )
        )
        seen_external_ids.add(external_id)

    for external_id in sorted(external_ids - seen_external_ids):
        errors.append(
            f"Grant recipient with {DATA_SET_EXTERNAL_ID_COLUMN_HEADER} '{external_id}' is missing from the CSV"
        )

    return errors


def validate_data_set(
    data_set: DataSetUploadSessionModel, all_rows: TUnvalidatedDataSetRows
) -> DataSetValidationResult:
    result = DataSetValidationResult()
    for idx, row in enumerate(all_rows):
        row_result = _validate_row(row, idx, data_set)
        if row_result.cell_errors or row_result.missing_columns:
            result.row_results.append(row_result)
    return result


def build_data_set_upload_s3_key(grant_id: uuid.UUID, report_id: uuid.UUID, data_source_id: uuid.UUID) -> str:
    return f"{current_app.config['REFERENCE_FILES_PREFIX']}/{grant_id}/{report_id}/{data_source_id}"
