from app.common.data.models import (
    Submission,
    SubmissionEvent,
)
from app.common.data.types import (
    DataSourceType,
    NumberTypeEnum,
    QuestionDataType,
    SubmissionModeEnum,
)
from app.deliver_grant_funding.helpers import (
    start_previewing_collection,
    validate_data_set,
    validate_data_set_grant_recipients,
)
from app.deliver_grant_funding.session_models import DataSetColumnMapping, DataSetUploadSessionModel
from tests.utils import AnyStringMatching


def test_start_previewing_collection(authenticated_grant_admin_client, db_session, factories, mock_s3_service_calls):
    user = authenticated_grant_admin_client.user
    collection = factories.collection.create(create_completed_submissions_each_question_type__preview=1)

    for submission in collection.preview_submissions:
        submission.created_by = user
        factories.submission_event.create(submission=submission, created_by=submission.created_by)

    old_preview_submissions_from_db = (
        db_session.query(Submission).where(Submission.mode == SubmissionModeEnum.PREVIEW).all()
    )
    old_submission_events_from_db = db_session.query(SubmissionEvent).all()

    assert len(old_preview_submissions_from_db) == 1
    assert len(old_submission_events_from_db) == 1

    # Test that old submissions are deleted and you get redirected to the preview tasklist
    response = start_previewing_collection(collection=collection)
    assert response.status_code == 302
    assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/submissions/[a-z0-9-]{36}$")
    test_submissions_from_db = db_session.query(Submission).where(Submission.mode == SubmissionModeEnum.PREVIEW).all()
    assert len(test_submissions_from_db) == 1
    assert test_submissions_from_db[0].id is not old_preview_submissions_from_db[0].id
    assert len(mock_s3_service_calls.delete_prefix_calls) == 1
    assert str(old_preview_submissions_from_db[0].id) in mock_s3_service_calls.delete_prefix_calls[0].args[0]

    # When passing a form, test that old submissions are deleted and you get redirected to the specific
    # ask a question preview
    form = collection.forms[0]
    response = start_previewing_collection(collection=collection, form=form)
    assert response.status_code == 302
    assert response.location == AnyStringMatching(
        "/deliver/grant/[a-z0-9-]{36}/submissions/[a-z0-9-]{36}/[a-z0-9-]{36}"
    )
    second_test_submissions_from_db = (
        db_session.query(Submission).where(Submission.mode == SubmissionModeEnum.PREVIEW).all()
    )
    assert len(second_test_submissions_from_db) == 1
    assert second_test_submissions_from_db[0].id not in [
        old_preview_submissions_from_db[0].id,
        test_submissions_from_db[0].id,
    ]
    assert len(mock_s3_service_calls.delete_prefix_calls) == 2
    assert str(test_submissions_from_db[0].id) in mock_s3_service_calls.delete_prefix_calls[1].args[0]


def _make_data_set(
    *,
    data_source_type: DataSourceType = DataSourceType.GRANT_RECIPIENT,
    data_columns: list[str] | None = None,
    column_mappings: list[DataSetColumnMapping] | None = None,
    all_rows: list[dict] | None = None,
) -> DataSetUploadSessionModel:
    """Build a minimal DataSetUploadSessionModel — handles the boilerplate that rarely varies between tests."""
    return DataSetUploadSessionModel(
        name="Test Data Set",
        data_source_type=data_source_type,
        grant_recipient_identifier_columns=["ONS code", "Grant recipient"]
        if data_source_type != DataSourceType.STATIC
        else [],
        data_columns=data_columns or [],
        preview_rows=[],
        column_mappings=column_mappings or [],
        all_rows=all_rows or [],
    )


class TestValidateDataSet:
    def test_returns_no_errors_for_valid_data(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        data_set = _make_data_set(
            data_columns=["Capital allocation", "Revenue allocation"],
            column_mappings=[
                DataSetColumnMapping(
                    column_name="Capital allocation",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.DECIMAL,
                    prefix="£",
                    max_decimal_places=2,
                ),
                DataSetColumnMapping(
                    column_name="Revenue allocation",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.INTEGER,
                ),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Capital allocation": "£1000.00",
                    "Revenue allocation": "500",
                },
            ],
        )

        result = validate_data_set(data_set)

        assert not result.has_blocking_errors
        assert not result.has_missing_data
        assert result.blocking_errors == []

    def test_missing_value_is_blocking_for_static(self):
        data_set = _make_data_set(
            data_source_type=DataSourceType.STATIC,
            data_columns=["theme id", "theme name"],
            column_mappings=[
                DataSetColumnMapping(column_name="theme id", data_type=QuestionDataType.TEXT_SINGLE_LINE),
                DataSetColumnMapping(column_name="theme name", data_type=QuestionDataType.TEXT_SINGLE_LINE),
            ],
            all_rows=[
                {"theme id": "electric", "theme name": "Electricity"},
                {"theme id": "water", "theme name": "Water supply"},
                {"theme id": "garbage", "theme name": ""},
            ],
        )

        result = validate_data_set(data_set)

        assert result.has_blocking_errors
        cell_error = result.cell_errors_by_row[2]["theme name"]
        assert cell_error.table_message == "Data missing"
        assert cell_error.original_value == ""
        assert "'theme name' in row 3 is missing a value" in result.blocking_errors

    def test_missing_value_is_non_blocking_for_grant_recipient(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        data_set = _make_data_set(
            data_columns=["Notes"],
            column_mappings=[
                DataSetColumnMapping(column_name="Notes", data_type=QuestionDataType.TEXT_SINGLE_LINE),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Notes": "",
                }
            ],
        )

        result = validate_data_set(data_set)

        assert not result.has_blocking_errors
        assert result.has_missing_data
        assert result.missing_columns_by_row[0] == ["Notes"]

    def test_missing_columns_by_row_tracks_correct_columns(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(organisation__external_id="EC456")
        data_set = _make_data_set(
            data_columns=["Notes", "Summary"],
            column_mappings=[
                DataSetColumnMapping(column_name="Notes", data_type=QuestionDataType.TEXT_SINGLE_LINE),
                DataSetColumnMapping(column_name="Summary", data_type=QuestionDataType.TEXT_SINGLE_LINE),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Notes": "",
                    "Summary": "ok",
                },
                {
                    "ONS code": gr2.organisation.external_id,
                    "Grant recipient": gr2.organisation.name,
                    "Notes": "",
                    "Summary": "",
                },
            ],
        )

        result = validate_data_set(data_set)

        assert result.missing_columns_by_row[0] == ["Notes"]
        assert result.missing_columns_by_row[1] == ["Notes", "Summary"]

    def test_wrong_prefix_symbol_is_incorrect_data_type(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        data_set = _make_data_set(
            data_columns=["Capital allocation"],
            column_mappings=[
                DataSetColumnMapping(
                    column_name="Capital allocation",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.DECIMAL,
                    prefix="£",
                    max_decimal_places=2,
                ),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Capital allocation": "$1000.00",
                }
            ],
        )

        result = validate_data_set(data_set)

        cell_error = result.cell_errors_by_row[0]["Capital allocation"]
        assert cell_error.table_message == "Incorrect data type"
        assert cell_error.original_value == "$1000.00"

    def test_missing_prefix_is_valid(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        data_set = _make_data_set(
            data_columns=["Capital allocation"],
            column_mappings=[
                DataSetColumnMapping(
                    column_name="Capital allocation",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.DECIMAL,
                    prefix="£",
                    max_decimal_places=2,
                ),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Capital allocation": "1000.00",
                }
            ],
        )

        result = validate_data_set(data_set)

        assert not result.has_blocking_errors

    def test_missing_suffix_is_valid(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        data_set = _make_data_set(
            data_columns=["Rate"],
            column_mappings=[
                DataSetColumnMapping(
                    column_name="Rate",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.DECIMAL,
                    suffix="%",
                    max_decimal_places=2,
                ),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Rate": "50.00",
                }
            ],
        )

        result = validate_data_set(data_set)

        assert not result.has_blocking_errors

    def test_too_many_decimal_places_is_blocking_cell_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        data_set = _make_data_set(
            data_columns=["Capital allocation"],
            column_mappings=[
                DataSetColumnMapping(
                    column_name="Capital allocation",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.DECIMAL,
                    prefix="£",
                    max_decimal_places=2,
                ),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Capital allocation": "£1000.123",
                }
            ],
        )

        result = validate_data_set(data_set)

        cell_error = result.cell_errors_by_row[0]["Capital allocation"]
        assert cell_error.table_message == "Too many decimal places"
        assert cell_error.original_value == "£1000.123"
        assert "'Capital allocation' in row 1 has too many decimal places (maximum 2)" in result.blocking_errors

    def test_incorrect_data_type_integer(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        data_set = _make_data_set(
            data_columns=["Revenue allocation"],
            column_mappings=[
                DataSetColumnMapping(
                    column_name="Revenue allocation",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.INTEGER,
                ),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Revenue allocation": "abc",
                }
            ],
        )

        result = validate_data_set(data_set)

        cell_error = result.cell_errors_by_row[0]["Revenue allocation"]
        assert cell_error.table_message == "Incorrect data type"
        assert "'Revenue allocation' in row 1 must be a whole number" in result.blocking_errors

    def test_incorrect_data_type_decimal(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        data_set = _make_data_set(
            data_columns=["Rate"],
            column_mappings=[
                DataSetColumnMapping(
                    column_name="Rate",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.DECIMAL,
                    max_decimal_places=2,
                ),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Rate": "not-a-number",
                }
            ],
        )

        result = validate_data_set(data_set)

        cell_error = result.cell_errors_by_row[0]["Rate"]
        assert cell_error.table_message == "Incorrect data type"
        assert "'Rate' in row 1 must be a decimal number" in result.blocking_errors

    def test_row_with_both_blocking_error_and_missing_column(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        data_set = _make_data_set(
            data_columns=["Capital allocation", "Notes"],
            column_mappings=[
                DataSetColumnMapping(
                    column_name="Capital allocation",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.DECIMAL,
                    prefix="£",
                    max_decimal_places=2,
                ),
                DataSetColumnMapping(column_name="Notes", data_type=QuestionDataType.TEXT_SINGLE_LINE),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Capital allocation": "not-a-number",
                    "Notes": "",
                }
            ],
        )

        result = validate_data_set(data_set)

        assert result.has_blocking_errors
        assert result.has_missing_data
        assert result.cell_errors_by_row[0]["Capital allocation"].table_message == "Incorrect data type"
        assert result.missing_columns_by_row[0] == ["Notes"]

    def test_clean_rows_are_excluded_from_row_results(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(organisation__external_id="EC456")
        data_set = _make_data_set(
            data_columns=["Capital allocation"],
            column_mappings=[
                DataSetColumnMapping(
                    column_name="Capital allocation",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.DECIMAL,
                    prefix="£",
                    max_decimal_places=2,
                ),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Capital allocation": "£1000.00",
                },
                {
                    "ONS code": gr2.organisation.external_id,
                    "Grant recipient": gr2.organisation.name,
                    "Capital allocation": "$1000.00",
                },
            ],
        )

        result = validate_data_set(data_set)
        assert len(result.blocking_errors) == 1

    def test_multiple_errors_across_rows(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(organisation__external_id="EC456")
        data_set = _make_data_set(
            data_columns=["Capital allocation", "Revenue allocation"],
            column_mappings=[
                DataSetColumnMapping(
                    column_name="Capital allocation",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.DECIMAL,
                    prefix="£",
                    max_decimal_places=2,
                ),
                DataSetColumnMapping(
                    column_name="Revenue allocation",
                    data_type=QuestionDataType.NUMBER,
                    number_type=NumberTypeEnum.INTEGER,
                ),
            ],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "Capital allocation": "$1000.00",
                    "Revenue allocation": "500",
                },
                {
                    "ONS code": gr2.organisation.external_id,
                    "Grant recipient": gr2.organisation.name,
                    "Capital allocation": "£1000.123",
                    "Revenue allocation": "not-a-number",
                },
            ],
        )

        result = validate_data_set(data_set)

        assert result.has_blocking_errors
        assert any("must be a decimal number" in e for e in result.blocking_errors)
        assert any("too many decimal places" in e for e in result.blocking_errors)
        assert any("must be a whole number" in e for e in result.blocking_errors)
        assert len(result.blocking_errors) == 3


class TestValidateDataSetGrantRecipients:
    def test_returns_empty_for_static(self):
        data_set = _make_data_set(data_source_type=DataSourceType.STATIC)
        assert validate_data_set_grant_recipients(data_set, []) == []

    def test_valid_csv_returns_no_errors(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        data_set = _make_data_set(
            data_columns=["Amount"],
            all_rows=[
                {"ONS code": gr.organisation.external_id, "Grant recipient": gr.organisation.name, "Amount": "100"}
            ],
        )
        assert validate_data_set_grant_recipients(data_set, [gr]) == []

    def test_unknown_ons_code_is_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        data_set = _make_data_set(
            data_columns=["Amount"],
            all_rows=[{"ONS code": "UNKNOWN", "Grant recipient": gr.organisation.name, "Amount": "100"}],
        )
        errors = validate_data_set_grant_recipients(data_set, [gr])
        assert any("ONS code 'UNKNOWN' not found in grant recipients" in e for e in errors)

    def test_unknown_recipient_name_is_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        data_set = _make_data_set(
            data_columns=["Amount"],
            all_rows=[
                {"ONS code": gr.organisation.external_id, "Grant recipient": "Rogue Organisation", "Amount": "100"}
            ],
        )
        errors = validate_data_set_grant_recipients(data_set, [gr])
        assert any("Grant recipient 'Rogue Organisation' not found in grant recipients" in e for e in errors)

    def test_duplicate_ons_code_is_error_for_grant_recipient_type(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        data_set = _make_data_set(
            data_columns=["Amount"],
            all_rows=[
                {"ONS code": gr.organisation.external_id, "Grant recipient": gr.organisation.name, "Amount": "100"},
                {"ONS code": gr.organisation.external_id, "Grant recipient": gr.organisation.name, "Amount": "200"},
            ],
        )
        errors = validate_data_set_grant_recipients(data_set, [gr])
        assert any(f"ONS code '{gr.organisation.external_id}' already appears" in e for e in errors)

    def test_duplicate_ons_code_is_not_error_for_project_level(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        data_set = _make_data_set(
            data_source_type=DataSourceType.PROJECT_LEVEL,
            data_columns=["Amount"],
            all_rows=[
                {"ONS code": gr.organisation.external_id, "Grant recipient": gr.organisation.name, "Amount": "100"},
                {"ONS code": gr.organisation.external_id, "Grant recipient": gr.organisation.name, "Amount": "200"},
            ],
        )
        errors = validate_data_set_grant_recipients(data_set, [gr])
        assert not errors

    def test_grant_recipient_missing_from_csv(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        gr2 = factories.grant_recipient.create(organisation__external_id="T0002")
        data_set = _make_data_set(
            data_columns=["Amount"],
            all_rows=[
                {"ONS code": gr.organisation.external_id, "Grant recipient": gr.organisation.name, "Amount": "100"}
            ],
        )
        errors = validate_data_set_grant_recipients(data_set, [gr, gr2])
        assert any(f"ONS code '{gr2.organisation.external_id}' is missing from the CSV" in e for e in errors)
        assert any(f"'{gr2.organisation.name}' is missing from the CSV" in e for e in errors)

    def test_ons_code_without_recipient_name_is_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        data_set = _make_data_set(
            data_columns=["Amount"],
            all_rows=[{"ONS code": gr.organisation.external_id, "Grant recipient": "", "Amount": "100"}],
        )
        errors = validate_data_set_grant_recipients(data_set, [gr])
        assert any("Both ONS code and grant recipient name are required" in e for e in errors)

    def test_data_present_but_no_identifiers_is_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        data_set = _make_data_set(
            data_source_type=DataSourceType.PROJECT_LEVEL,
            data_columns=["project name", "project cost"],
            all_rows=[
                {
                    "ONS code": gr.organisation.external_id,
                    "Grant recipient": gr.organisation.name,
                    "project name": "Roads",
                    "project cost": "1000",
                },
                {
                    "ONS code": "",
                    "Grant recipient": "",
                    "project name": "Orphan project",
                    "project cost": "500",
                },
            ],
        )
        errors = validate_data_set_grant_recipients(data_set, [gr])
        assert any("Data is present but ONS code and grant recipient are missing" in e for e in errors)

    def test_fully_empty_row_is_skipped(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        data_set = _make_data_set(
            data_columns=["Amount"],
            all_rows=[
                {"ONS code": gr.organisation.external_id, "Grant recipient": gr.organisation.name, "Amount": "100"},
                {"ONS code": "", "Grant recipient": "", "Amount": ""},
            ],
        )
        errors = validate_data_set_grant_recipients(data_set, [gr])
        assert errors == []

    def test_unknown_ons_code_suppresses_recipient_duplicate_check(self, factories):
        gr = factories.grant_recipient.create(
            organisation__external_id="T0001",
            organisation__name="Ministry of Testing",
        )
        data_set = _make_data_set(
            data_columns=["Amount"],
            all_rows=[
                {"ONS code": "T0001", "Grant recipient": "Ministry of Testing", "Amount": "100"},  # valid
                {"ONS code": "T9999", "Grant recipient": "Ministry of Testing", "Amount": "200"},  # unknown ONS code
            ],
        )
        errors = validate_data_set_grant_recipients(data_set, [gr])

        assert any("ONS code 'T9999' not found" in e for e in errors)
        assert not any("Ministry of Testing" in e and "already appears" in e for e in errors)

    def test_duplicates_missing_and_unknown_combined(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(organisation__external_id="EC456")
        gr3 = factories.grant_recipient.create(organisation__external_id="EC789")
        data_set = _make_data_set(
            data_columns=["Amount"],
            all_rows=[
                {"ONS code": gr.organisation.external_id, "Grant recipient": gr.organisation.name, "Amount": "100"},
                {"ONS code": gr2.organisation.external_id, "Grant recipient": gr2.organisation.name, "Amount": "200"},
                {"ONS code": gr.organisation.external_id, "Grant recipient": gr.organisation.name, "Amount": "300"},
                {"ONS code": "AB1111", "Grant recipient": "Rivendell", "Amount": "400"},
            ],
        )

        errors = validate_data_set_grant_recipients(data_set, [gr, gr2, gr3])

        assert any(f"ONS code '{gr.organisation.external_id}' already appears" in e for e in errors)
        assert any(f"Grant recipient '{gr.organisation.name}' already appears" in e for e in errors)
        assert any(f"ONS code '{gr3.organisation.external_id}' is missing from the CSV" in e for e in errors)
        assert any(f"'{gr3.organisation.name}' is missing from the CSV" in e for e in errors)
        assert any("ONS code 'AB1111' not found in grant recipients" in e for e in errors)
        assert any("Grant recipient 'Rivendell' not found in grant recipients" in e for e in errors)
