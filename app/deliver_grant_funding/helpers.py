from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Sequence

from flask import redirect, session, url_for
from flask.typing import ResponseReturnValue
from pydantic import BaseModel

from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    create_submission,
    delete_collection_preview_submissions_created_by_user,
    get_submissions_by_user,
)
from app.common.data.types import DataSourceType, NumberTypeEnum, QuestionDataType, SubmissionModeEnum
from app.common.helpers.collections import SubmissionHelper
from app.deliver_grant_funding.session_models import DataSetColumnMapping, DataSetUploadSessionModel
from app.extensions import s3_service

if TYPE_CHECKING:
    from app.common.data.models import Collection, Form, GrantRecipient


def start_previewing_collection(collection: Collection, form: Form | None = None) -> ResponseReturnValue:
    user = interfaces.user.get_current_user()

    file_prefixes_to_delete = [
        submission.s3_key_prefix
        for submission in get_submissions_by_user(
            user, collection_id=collection.id, submission_mode=SubmissionModeEnum.PREVIEW
        )
    ]

    delete_collection_preview_submissions_created_by_user(collection=collection, created_by_user=user)
    submission = create_submission(collection=collection, created_by=user, mode=SubmissionModeEnum.PREVIEW)
    helper = SubmissionHelper(submission)

    for file_prefix in file_prefixes_to_delete:
        s3_service.delete_prefix(file_prefix)

    # Pop this if it exists; sanity check for not terminating a session correctly
    session.pop("test_submission_form_id", None)
    if form:
        question = helper.get_first_question_for_form(form)
        if question:
            session["test_submission_form_id"] = form.id
            return redirect(
                url_for(
                    "deliver_grant_funding.ask_a_question",
                    grant_id=collection.grant_id,
                    submission_id=helper.submission.id,
                    question_id=question.id,
                )
            )

    return redirect(
        url_for(
            "deliver_grant_funding.submission_tasklist",
            grant_id=collection.grant_id,
            submission_id=helper.submission.id,
        )
    )


class CellError(BaseModel):
    column: str
    original_value: str
    table_message: str
    summary_message: str


class RowValidationResult(BaseModel):
    row_number: int
    cell_errors: list[CellError] = []
    missing_columns: list[str] = []


class DataSetValidationResult(BaseModel):
    row_results: list[RowValidationResult] = []

    @property
    def blocking_errors(self) -> list[str]:
        return [e.summary_message for r in self.row_results for e in r.cell_errors]

    @property
    def cell_errors_by_row(self) -> dict[int, dict[str, CellError]]:
        return {r.row_number: {e.column: e for e in r.cell_errors} for r in self.row_results if r.cell_errors}

    @property
    def missing_columns_by_row(self) -> dict[int, list[str]]:
        return {r.row_number: r.missing_columns for r in self.row_results if r.missing_columns}

    @property
    def has_blocking_errors(self) -> bool:
        return any(r.cell_errors for r in self.row_results)

    @property
    def has_missing_data(self) -> bool:
        return any(r.missing_columns for r in self.row_results)


def _missing_value_error(column: str, row_number: int) -> CellError:
    return CellError(
        column=column,
        original_value="",
        table_message="Data missing",
        summary_message=f"'{column}' in row {row_number} is missing a value",
    )


def _too_many_decimal_places_error(column: str, value: str, row_number: int, max_dp: int) -> CellError:
    return CellError(
        column=column,
        original_value=value,
        table_message="Too many decimal places",
        summary_message=f"'{column}' in row {row_number} has too many decimal places (maximum {max_dp})",
    )


def _incorrect_data_type_error(column: str, value: str, row_number: int, number_type: NumberTypeEnum) -> CellError:
    expected = "a whole number" if number_type == NumberTypeEnum.INTEGER else "a decimal number"
    return CellError(
        column=column,
        original_value=value,
        table_message="Incorrect data type",
        summary_message=f"'{column}' in row {row_number} must be {expected}",
    )


def _validate_cell(column: str, value: str, row_number: int, mapping: DataSetColumnMapping) -> CellError | None:
    if mapping.data_type != QuestionDataType.NUMBER:
        return None

    stripped = value

    if mapping.prefix:
        stripped = value.removeprefix(mapping.prefix)

    if mapping.suffix:
        stripped = value.removesuffix(mapping.suffix)

    stripped = stripped.replace(",", "").strip()

    if mapping.number_type == NumberTypeEnum.INTEGER:
        if not stripped.lstrip("-").isdigit():
            return _incorrect_data_type_error(column, value, row_number, mapping.number_type)

    elif mapping.number_type == NumberTypeEnum.DECIMAL:
        try:
            Decimal(stripped)
        except InvalidOperation:
            return _incorrect_data_type_error(column, value, row_number, mapping.number_type)

        if mapping.max_decimal_places is not None:
            decimal_places = len(stripped.split(".")[1]) if "." in stripped else 0
            if decimal_places > mapping.max_decimal_places:
                return _too_many_decimal_places_error(column, value, row_number, mapping.max_decimal_places)

    return None


def _validate_row(row: dict[str, str], idx: int, data_set: DataSetUploadSessionModel) -> RowValidationResult:
    result = RowValidationResult(row_number=idx)
    is_static = data_set.data_source_type == DataSourceType.STATIC

    for column in data_set.data_columns:
        value = row.get(column, "").strip()
        mapping = data_set.get_column_mapping(column)

        if not value:
            if is_static:
                result.cell_errors.append(_missing_value_error(column, result.row_number))
            else:
                result.missing_columns.append(column)
        elif mapping:
            if error := _validate_cell(column, value, result.row_number, mapping):
                result.cell_errors.append(error)

    return result


def _check_grant_recipient_row(
    ons_code: str,
    recipient: str,
    row_number: int,
    ons_codes: set[str],
    recipient_names: set[str],
    seen_ons_codes: set[str],
    seen_recipient_names: set[str],
    check_duplicates: bool,
) -> list[str]:
    errors: list[str] = []
    ons_code_unknown = ons_code not in ons_codes

    if ons_code_unknown:
        errors.append(f"Row {row_number}: ONS code '{ons_code}' not found in grant recipients")
    elif check_duplicates and ons_code in seen_ons_codes:
        errors.append(f"Row {row_number}: ONS code '{ons_code}' already appears in the data set")

    if recipient not in recipient_names:
        errors.append(f"Row {row_number}: Grant recipient '{recipient}' not found in grant recipients")
    elif check_duplicates and not ons_code_unknown and recipient in seen_recipient_names:
        errors.append(f"Row {row_number}: Grant recipient '{recipient}' already appears in the data set")

    return errors


def validate_data_set_grant_recipients(
    data_set: DataSetUploadSessionModel,
    grant_recipients: Sequence[GrantRecipient],
) -> list[str]:
    if data_set.data_source_type == DataSourceType.STATIC:
        return []

    errors: list[str] = []
    ons_codes = {gr.organisation.external_id for gr in grant_recipients}
    recipient_names = {gr.organisation.name for gr in grant_recipients}
    seen_ons_codes: set[str] = set()
    seen_recipient_names: set[str] = set()
    check_duplicates = data_set.data_source_type == DataSourceType.GRANT_RECIPIENT

    for idx, row in enumerate(data_set.all_rows):
        ons_code = row.get("ONS code", "").strip()
        recipient = row.get("Grant recipient", "").strip()

        if not ons_code and not recipient:
            row_has_data = any(row.get(col, "").strip() for col in data_set.data_columns)
            if row_has_data:
                errors.append(f"Row {idx + 1}: Data is present but ONS code and grant recipient are missing")
            continue

        if bool(ons_code) != bool(recipient):
            errors.append(f"Row {idx + 1}: Both ONS code and grant recipient name are required")
            continue

        errors.extend(
            _check_grant_recipient_row(
                ons_code,
                recipient,
                idx + 1,
                ons_codes,
                recipient_names,
                seen_ons_codes,
                seen_recipient_names,
                check_duplicates,
            )
        )
        seen_ons_codes.add(ons_code)
        if ons_code in ons_codes:
            seen_recipient_names.add(recipient)

    for ons_code in sorted(ons_codes - seen_ons_codes):
        errors.append(f"Grant recipient with ONS code '{ons_code}' is missing from the CSV")
    for name in sorted(recipient_names - seen_recipient_names):
        errors.append(f"Grant recipient '{name}' is missing from the CSV")

    return errors


def validate_data_set(data_set: DataSetUploadSessionModel) -> DataSetValidationResult:
    result = DataSetValidationResult()
    for idx, row in enumerate(data_set.all_rows):
        row_result = _validate_row(row, idx, data_set)
        if row_result.cell_errors or row_result.missing_columns:
            result.row_results.append(row_result)
    return result
