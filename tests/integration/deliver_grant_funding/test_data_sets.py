import csv
import uuid
from io import StringIO

import pytest

from app.common.data.interfaces.data_sets import get_data_source
from app.common.data.types import (
    DataSourceSchemaColumn,
    DataSourceType,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.constants import (
    DATA_SET_EXTERNAL_ID_COLUMN_HEADER,
    DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER,
    DATA_SET_IDENTIFIER_COLUMN_HEADERS,
)
from app.deliver_grant_funding.data_sets import (
    BritishPoundsError,
    DataTypeError,
    build_current_data_set_view,
    build_data_display_rows_with_missing_tags,
    find_grant_recipient_mismatches,
    generate_latest_csv_template,
    upload_header_only_data_set_files,
    validate_data_set,
    validate_data_set_grant_recipients,
)
from app.deliver_grant_funding.session_models import DataSetColumnMapping, DataSetUploadSessionModel


def _make_data_set(
    *,
    data_source_type: DataSourceType = DataSourceType.GRANT_RECIPIENT,
    data_columns: list[str] | None = None,
    column_mappings: list[DataSetColumnMapping] | None = None,
) -> DataSetUploadSessionModel:
    return DataSetUploadSessionModel(
        name="Test Data Set",
        data_source_type=data_source_type,
        data_columns=data_columns or [],
        preview_data={},
        column_mappings=column_mappings or [],
        data_source_id=uuid.uuid4(),
        original_filename="test.csv",
        s3_key="data-set-uploads/test.csv",
    )


class TestValidateDataSet:
    def test_returns_no_errors_for_valid_data(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        data_set = _make_data_set(
            data_columns=["Capital allocation", "Revenue allocation"],
            column_mappings=[
                DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS"),
                DataSetColumnMapping(column_name="Revenue allocation", column_type="INTEGER"),
            ],
        )

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "£1000.00",
                "Revenue allocation": "500",
            },
        ]

        result = validate_data_set(data_set, all_rows)

        assert not result.blocking_errors

    def test_wrong_prefix_symbol_for_british_pounds_collapses_to_single_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        data_set = _make_data_set(
            data_columns=["Capital allocation"],
            column_mappings=[DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS")],
        )

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "$1000.00",
            }
        ]

        result = validate_data_set(data_set, all_rows)

        assert len(result.blocking_errors) == 1
        assert isinstance(result.blocking_errors[0], BritishPoundsError)

    def test_missing_prefix_is_valid(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        data_set = _make_data_set(
            data_columns=["Capital allocation"],
            column_mappings=[DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS")],
        )

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "1000.00",
            }
        ]

        result = validate_data_set(data_set, all_rows)
        assert not result.blocking_errors

    def test_missing_suffix_is_valid(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        data_set = _make_data_set(
            data_columns=["Rate"],
            column_mappings=[
                DataSetColumnMapping(column_name="Rate", column_type="DECIMAL", suffix="%", max_decimal_places=2)
            ],
        )

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Rate": "50.00",
            }
        ]

        result = validate_data_set(data_set, all_rows)
        assert not result.blocking_errors

    def test_too_many_decimal_places_in_british_pounds_is_blocking_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        data_set = _make_data_set(
            data_columns=["Capital allocation"],
            column_mappings=[DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS")],
        )

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "£1000.123",
            }
        ]

        result = validate_data_set(data_set, all_rows)

        assert len(result.blocking_errors) == 1
        assert isinstance(result.blocking_errors[0], BritishPoundsError)

    def test_incorrect_data_type_integer(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        data_set = _make_data_set(
            data_columns=["Revenue allocation"],
            column_mappings=[DataSetColumnMapping(column_name="Revenue allocation", column_type="INTEGER")],
        )
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Revenue allocation": "abc",
            }
        ]
        result = validate_data_set(data_set, all_rows)

        assert result.blocking_errors
        assert any(isinstance(e, DataTypeError) for e in result.blocking_errors)

    def test_incorrect_data_type_decimal(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        data_set = _make_data_set(
            data_columns=["Rate"],
            column_mappings=[DataSetColumnMapping(column_name="Rate", column_type="DECIMAL", max_decimal_places=2)],
        )

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Rate": "not-a-number",
            }
        ]

        result = validate_data_set(data_set, all_rows)

        assert result.blocking_errors
        assert any(isinstance(e, DataTypeError) for e in result.blocking_errors)

    def test_row_with_blocking_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        data_set = _make_data_set(
            data_columns=["Capital allocation", "Notes"],
            column_mappings=[
                DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS"),
                DataSetColumnMapping(column_name="Notes", column_type="TEXT"),
            ],
        )

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "not-a-number",
                "Notes": "",
            }
        ]

        result = validate_data_set(data_set, all_rows)

        assert result.blocking_errors
        assert any(isinstance(e, BritishPoundsError) for e in result.blocking_errors)

    def test_multiple_errors_across_rows(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        gr2 = factories.grant_recipient.create(organisation__external_id="E06000456")
        data_set = _make_data_set(
            data_columns=["Capital allocation", "Revenue allocation"],
            column_mappings=[
                DataSetColumnMapping(column_name="Capital allocation", column_type="BRITISH_POUNDS"),
                DataSetColumnMapping(column_name="Revenue allocation", column_type="INTEGER"),
            ],
        )

        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Capital allocation": "$1000.00",
                "Revenue allocation": "500",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr2.organisation.name,
                "Capital allocation": "£1000.123",
                "Revenue allocation": "not-a-number",
            },
        ]

        result = validate_data_set(data_set, all_rows)

        assert result.blocking_errors
        assert len(result.row_results) == 2
        assert len(result.blocking_errors) == 3

        assert sum(isinstance(e, BritishPoundsError) for e in result.blocking_errors) == 2
        assert sum(isinstance(e, DataTypeError) for e in result.blocking_errors) == 1


class TestBuildDisplayRowsWithMissingTags:
    def test_returns_empty_list_when_no_missing_data(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        gr2 = factories.grant_recipient.create(organisation__external_id="E06000456")
        data_set = _make_data_set(
            data_columns=["Notes"],
            column_mappings=[DataSetColumnMapping(column_name="Notes", column_type="TEXT")],
        )
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Notes": "Some notes",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr2.organisation.name,
                "Notes": "More notes",
            },
        ]

        display_rows = build_data_display_rows_with_missing_tags(data_set.data_columns, all_rows, [gr, gr2])

        assert display_rows == []

    def test_returns_row_for_csv_row_with_missing_column(self, factories):
        gr = factories.grant_recipient.create()
        data_set = _make_data_set(
            data_columns=["Notes", "Summary"],
            column_mappings=[
                DataSetColumnMapping(column_name="Notes", column_type="TEXT"),
                DataSetColumnMapping(column_name="Summary", column_type="TEXT"),
            ],
        )
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Notes": "",
                "Summary": "ok",
            }
        ]

        display_rows = build_data_display_rows_with_missing_tags(data_set.data_columns, all_rows, [gr])

        assert len(display_rows) == 1
        row = display_rows[0]
        assert row.external_id == gr.organisation.external_id
        assert row.grant_recipient_name == gr.organisation.name
        assert row.missing_columns == ["Notes"]
        assert row.grant_recipient_entirely_missing is False
        assert row.row_number == 0

    def test_tracks_multiple_missing_columns_for_a_row(self, factories):
        gr = factories.grant_recipient.create()
        data_set = _make_data_set(
            data_columns=["Notes", "Summary"],
            column_mappings=[
                DataSetColumnMapping(column_name="Notes", column_type="TEXT"),
                DataSetColumnMapping(column_name="Summary", column_type="TEXT"),
            ],
        )
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Notes": "",
                "Summary": "",
            }
        ]

        display_rows = build_data_display_rows_with_missing_tags(data_set.data_columns, all_rows, [gr])

        assert len(display_rows) == 1
        assert display_rows[0].missing_columns == ["Notes", "Summary"]

    def test_uses_service_name_not_csv_name_for_recipient_with_missing_data(self, factories):
        gr = factories.grant_recipient.create(organisation__name="Birmingham City Council")
        data_set = _make_data_set(
            data_columns=["Notes", "Summary"],
            column_mappings=[
                DataSetColumnMapping(column_name="Notes", column_type="TEXT"),
                DataSetColumnMapping(column_name="Summary", column_type="TEXT"),
            ],
        )
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Birmingham CC",
                "Notes": "",
            }
        ]
        display_rows = build_data_display_rows_with_missing_tags(data_set.data_columns, all_rows, [gr])

        assert len(display_rows) == 1
        assert display_rows[0].grant_recipient_name == gr.organisation.name

    def test_adds_phantom_row_for_grant_recipient_missing_from_csv(self, factories):
        gr = factories.grant_recipient.create()
        gr2 = factories.grant_recipient.create()
        data_set = _make_data_set(
            data_columns=["Notes"],
            column_mappings=[DataSetColumnMapping(column_name="Notes", column_type="TEXT")],
        )
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Notes": "Some notes",
            },
        ]

        display_rows = build_data_display_rows_with_missing_tags(data_set.data_columns, all_rows, [gr, gr2])

        assert len(display_rows) == 1
        row = display_rows[0]
        assert row.external_id == gr2.organisation.external_id
        assert row.grant_recipient_name == gr2.organisation.name
        assert row.missing_columns == ["Notes"]
        assert row.grant_recipient_entirely_missing is True
        assert row.row_number is None

    def test_sorts_mixed_rows_alphabetically_by_recipient_name(self, factories):
        gr_a = factories.grant_recipient.create(organisation__name="AAAA Council")
        gr_b = factories.grant_recipient.create(organisation__name="BBBB Council")
        gr_c = factories.grant_recipient.create(organisation__name="CCCC Council")
        data_set = _make_data_set(
            data_columns=["Notes"],
            column_mappings=[DataSetColumnMapping(column_name="Notes", column_type="TEXT")],
        )
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr_a.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr_a.organisation.name,
                "Notes": "",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr_c.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr_c.organisation.name,
                "Notes": "",
            },
        ]

        display_rows = build_data_display_rows_with_missing_tags(data_set.data_columns, all_rows, [gr_a, gr_b, gr_c])

        assert [row.grant_recipient_name for row in display_rows] == [
            "AAAA Council",
            "BBBB Council",
            "CCCC Council",
        ]
        assert display_rows[1].grant_recipient_entirely_missing is True

    def test_respects_include_all_grant_recipients(self, factories):
        gr_a = factories.grant_recipient.create(organisation__name="AAAA Council")
        gr_b = factories.grant_recipient.create(organisation__name="BBBB Council")
        gr_c = factories.grant_recipient.create(organisation__name="CCCC Council")
        data_set = _make_data_set(
            data_columns=["Notes"],
            column_mappings=[DataSetColumnMapping(column_name="Notes", column_type="TEXT")],
        )
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr_a.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr_a.organisation.name,
                "Notes": "",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr_c.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr_c.organisation.name,
                "Notes": "some info",
            },
        ]

        display_rows = build_data_display_rows_with_missing_tags(
            data_set.data_columns, all_rows, [gr_a, gr_b, gr_c], include_all_grant_recipients=True
        )

        assert [row.grant_recipient_name for row in display_rows] == [
            "AAAA Council",
            "BBBB Council",
            "CCCC Council",
        ]

        display_rows = build_data_display_rows_with_missing_tags(
            data_set.data_columns, all_rows, [gr_a, gr_b, gr_c], include_all_grant_recipients=False
        )

        assert [row.grant_recipient_name for row in display_rows] == [
            "AAAA Council",
            "BBBB Council",
        ]


class TestValidateDataSetGrantRecipients:
    def test_valid_csv_returns_no_errors(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000501")
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Amount": "100",
            }
        ]
        assert validate_data_set_grant_recipients(data_set, [gr], all_rows) == []

    def test_unknown_external_id_is_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000501")
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "UNKNOWN",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Amount": "100",
            }
        ]
        errors = validate_data_set_grant_recipients(data_set, [gr], all_rows)
        assert any(f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER} 'UNKNOWN' not found in grant recipients" in e for e in errors)

    def test_duplicate_external_id_is_error_for_grant_recipient_type(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000501")
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Amount": "100",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Amount": "200",
            },
        ]
        errors = validate_data_set_grant_recipients(data_set, [gr], all_rows)
        assert any(
            f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER} '{gr.organisation.external_id}' already appears" in e for e in errors
        )

    def test_external_id_without_recipient_name_is_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000501")
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "",
                "Amount": "100",
            }
        ]
        errors = validate_data_set_grant_recipients(data_set, [gr], all_rows)
        assert any(
            f"Both {DATA_SET_EXTERNAL_ID_COLUMN_HEADER} and grant recipient name are required" in e for e in errors
        )

    def test_data_present_but_no_identifiers_is_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000501")
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "",
                "Amount": "100",
            }
        ]
        errors = validate_data_set_grant_recipients(data_set, [gr], all_rows)
        assert any(
            f"Data is present but {DATA_SET_EXTERNAL_ID_COLUMN_HEADER} and grant recipient are missing" in e
            for e in errors
        )

    def test_fully_empty_row_is_skipped(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000501")
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Amount": "100",
            },
            {DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "", DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "", "Amount": ""},
        ]
        errors = validate_data_set_grant_recipients(data_set, [gr], all_rows)
        assert errors == []

    def test_unknown_external_id_suppresses_recipient_duplicate_check(self, factories):
        gr = factories.grant_recipient.create(
            organisation__external_id="E06000501",
            organisation__name="Ministry of Testing",
        )
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E06000501",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Ministry of Testing",
                "Amount": "100",
            },  # valid
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "T9999",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Ministry of Testing",
                "Amount": "200",
            },  # unknown external_id
        ]
        errors = validate_data_set_grant_recipients(data_set, [gr], all_rows)

        assert any(f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER} 'T9999' not found" in e for e in errors)
        assert not any("Ministry of Testing" in e and "already appears" in e for e in errors)

    def test_duplicates_missing_and_unknown_combined(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="E06000123")
        gr2 = factories.grant_recipient.create(organisation__external_id="E06000456")
        gr3 = factories.grant_recipient.create(organisation__external_id="E06000789")
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Amount": "100",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr2.organisation.name,
                "Amount": "200",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Amount": "300",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "AB1111",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rivendell",
                "Amount": "400",
            },
        ]

        errors = validate_data_set_grant_recipients(data_set, [gr, gr2, gr3], all_rows)

        assert any(
            f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER} '{gr.organisation.external_id}' already appears" in e for e in errors
        )
        assert any(f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER} 'AB1111' not found in grant recipients" in e for e in errors)


class TestFindGrantRecipientMismatches:
    def test_returns_no_mismatches_when_names_match(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123", organisation__name="Brighton Council")
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Amount": "100",
            }
        ]

        mismatches = find_grant_recipient_mismatches(all_rows, [gr])

        assert mismatches == []

    def test_returns_mismatch_when_name_differs_from_service(self, factories):
        gr = factories.grant_recipient.create(organisation__name="Birmingham City Council")
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Birmingham CC",
                "Amount": "100",
            }
        ]

        mismatches = find_grant_recipient_mismatches(all_rows, [gr])

        assert len(mismatches) == 1
        mismatch = mismatches[0]
        assert mismatch.row_number == 0
        assert mismatch.external_id == gr.organisation.external_id
        assert mismatch.csv_organisation_name == "Birmingham CC"
        assert mismatch.service_organisation_name == "Birmingham City Council"

    def test_no_mismatch_when_external_id_not_recognised(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123", organisation__name="Brighton Council")
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "UNKNOWN",
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Some Other Name",
                "Amount": "100",
            }
        ]

        mismatches = find_grant_recipient_mismatches(all_rows, [gr])

        assert mismatches == []

    def test_returns_multiple_mismatches_with_correct_row_numbers(self, factories):
        gr = factories.grant_recipient.create(
            organisation__external_id="EC123", organisation__name="Birmingham City Council"
        )
        gr2 = factories.grant_recipient.create(
            organisation__external_id="EC456", organisation__name="Leeds City Council"
        )
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Amount": "100",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Birmingham CC",
                "Amount": "200",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Leeds CC",
                "Amount": "300",
            },
        ]

        mismatches = find_grant_recipient_mismatches(all_rows, [gr, gr2])

        assert len(mismatches) == 2
        assert mismatches[0].row_number == 1
        assert mismatches[0].external_id == gr.organisation.external_id
        assert mismatches[0].csv_organisation_name == "Birmingham CC"
        assert mismatches[0].service_organisation_name == "Birmingham City Council"

        assert mismatches[1].row_number == 2
        assert mismatches[1].external_id == gr2.organisation.external_id
        assert mismatches[1].csv_organisation_name == "Leeds CC"
        assert mismatches[1].service_organisation_name == "Leeds City Council"


class TestBuildCurrentDataSetView:
    def test_returns_rows_sorted_alphabetically_with_no_changes(self, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        gr_b = factories.grant_recipient.create(grant=grant, organisation__name="BBBB Council")
        gr_a = factories.grant_recipient.create(grant=grant, organisation__name="AAAA Council")
        data_source = factories.data_source.create(
            grant=grant,
            collection=report,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[111, 222],
        )

        view = build_current_data_set_view(data_source, [gr_b, gr_a])

        assert [row.grant_recipient_name for row in view.rows] == ["AAAA Council", "BBBB Council"]
        assert [row.external_id for row in view.rows] == [
            gr_a.organisation.external_id,
            gr_b.organisation.external_id,
        ]
        assert all(row.organisation_item is not None for row in view.rows)
        assert view.added_grant_recipient_names == []
        assert view.removed_external_ids == []

    def test_grant_recipient_added_since_upload_has_no_organisation_item(self, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        existing_gr = factories.grant_recipient.create(grant=grant, organisation__name="Existing Council")
        data_source = factories.data_source.create(
            grant=grant,
            collection=report,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
        )
        new_gr = factories.grant_recipient.create(grant=grant, organisation__name="New Council")

        view = build_current_data_set_view(data_source, [existing_gr, new_gr])

        new_row = next(row for row in view.rows if row.external_id == new_gr.organisation.external_id)
        existing_row = next(row for row in view.rows if row.external_id == existing_gr.organisation.external_id)
        assert new_row.organisation_item is None
        assert existing_row.organisation_item is not None
        assert view.added_grant_recipient_names == ["New Council"]
        assert view.removed_external_ids == []

    def test_multiple_added_grant_recipients_sorted_by_name(self, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=report,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        gr_z = factories.grant_recipient.create(grant=grant, organisation__name="ZZZZ Council")
        gr_a = factories.grant_recipient.create(grant=grant, organisation__name="AAAA Council")

        view = build_current_data_set_view(data_source, [gr_z, gr_a])

        assert view.added_grant_recipient_names == ["AAAA Council", "ZZZZ Council"]

    def test_organisation_item_without_current_grant_recipient_is_removed(self, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        gr = factories.grant_recipient.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=report,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        factories.data_source_organisation_item.create(
            data_source=data_source, external_id=gr.organisation.external_id, _data={"c_allocation": 100}
        )
        factories.data_source_organisation_item.create(
            data_source=data_source, external_id="REMOVED-ID", _data={"c_allocation": 200}
        )

        view = build_current_data_set_view(data_source, [gr])

        assert [row.external_id for row in view.rows] == [gr.organisation.external_id]
        assert view.removed_external_ids == ["REMOVED-ID"]
        assert view.added_grant_recipient_names == []

    def test_multiple_removed_external_ids_sorted(self, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        gr = factories.grant_recipient.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=report,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        factories.data_source_organisation_item.create(
            data_source=data_source, external_id=gr.organisation.external_id, _data={"c_allocation": 100}
        )
        factories.data_source_organisation_item.create(
            data_source=data_source, external_id="ZZZZ-REMOVED", _data={"c_allocation": 200}
        )
        factories.data_source_organisation_item.create(
            data_source=data_source, external_id="AAAA-REMOVED", _data={"c_allocation": 300}
        )

        view = build_current_data_set_view(data_source, [gr])

        assert view.removed_external_ids == ["AAAA-REMOVED", "ZZZZ-REMOVED"]

    def test_handles_added_and_removed_simultaneously(self, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        gr_existing = factories.grant_recipient.create(grant=grant, organisation__name="Existing Council")
        data_source = factories.data_source.create(
            grant=grant,
            collection=report,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
        )
        factories.data_source_organisation_item.create(
            data_source=data_source, external_id="REMOVED-ID", _data={"c_allocation": 999}
        )
        gr_new = factories.grant_recipient.create(grant=grant, organisation__name="New Council")

        view = build_current_data_set_view(data_source, [gr_existing, gr_new])

        assert view.added_grant_recipient_names == ["New Council"]
        assert view.removed_external_ids == ["REMOVED-ID"]
        assert [row.external_id for row in view.rows] == [
            gr_existing.organisation.external_id,
            gr_new.organisation.external_id,
        ]

    def test_returns_empty_rows_and_all_removed_when_no_grant_recipients_passed(self, factories):
        grant = factories.grant.create()
        report = factories.collection.create(grant=grant)
        data_source = factories.data_source.create(
            grant=grant,
            collection=report,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        factories.data_source_organisation_item.create(
            data_source=data_source, external_id="AAA", _data={"c_allocation": 1}
        )
        factories.data_source_organisation_item.create(
            data_source=data_source, external_id="BBB", _data={"c_allocation": 2}
        )

        view = build_current_data_set_view(data_source, [])

        assert view.rows == []
        assert view.added_grant_recipient_names == []
        assert view.removed_external_ids == ["AAA", "BBB"]


class TestGenerateLatestCsvTemplate:
    def test_generate_no_changes(self, factories):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Org A"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="Org B"
        )
        gr3 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000789", organisation__name="Org C"
        )

        collection = factories.collection.create(grant=grant)

        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[123, 456, 789],
        )

        csv_content = generate_latest_csv_template(data_source)
        reader = csv.reader(StringIO(csv_content.getvalue()))

        rows = list(reader)
        assert len(rows) == 4

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation"]
        assert rows[1] == ["E06000123", gr.organisation.name, "123"]
        assert rows[2] == ["E06000456", gr2.organisation.name, "456"]
        assert rows[3] == ["E06000789", gr3.organisation.name, "789"]

    def test_generate_grant_recipient_added(self, factories):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="AAA org"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="BBB org"
        )
        gr3 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000789", organisation__name="CCC org"
        )

        collection = factories.collection.create(grant=grant)

        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[123, 456, 789],
        )
        gr4 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000124", organisation__name="AAB org"
        )

        csv_content = generate_latest_csv_template(data_source)
        reader = csv.reader(StringIO(csv_content.getvalue()))

        rows = list(reader)
        assert len(rows) == 5

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation"]
        assert rows[1] == ["E06000123", gr.organisation.name, "123"]
        assert rows[2] == ["E06000124", gr4.organisation.name, ""]
        assert rows[3] == ["E06000456", gr2.organisation.name, "456"]
        assert rows[4] == ["E06000789", gr3.organisation.name, "789"]

    def test_generate_grant_recipient_removed(self, factories, db_session):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Org A"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="Org B"
        )
        gr3 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000999", organisation__name="Org C"
        )

        collection = factories.collection.create(grant=grant)

        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[123, 456, 789],
        )

        db_session.delete(gr3)

        csv_content = generate_latest_csv_template(data_source)
        reader = csv.reader(StringIO(csv_content.getvalue()))

        rows = list(reader)
        assert len(rows) == 3

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation"]
        assert rows[1] == ["E06000123", gr.organisation.name, "123"]
        assert rows[2] == ["E06000456", gr2.organisation.name, "456"]

    def test_generate_no_changes_data_missing(self, factories):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Org A"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="Org B"
        )
        gr3 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000789", organisation__name="Org C"
        )

        collection = factories.collection.create(grant=grant)

        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[123, None, 789],
        )

        csv_content = generate_latest_csv_template(data_source)
        reader = csv.reader(StringIO(csv_content.getvalue()))

        rows = list(reader)
        assert len(rows) == 4

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation"]
        assert rows[1] == ["E06000123", gr.organisation.name, "123"]
        assert rows[2] == ["E06000456", gr2.organisation.name, ""]
        assert rows[3] == ["E06000789", gr3.organisation.name, "789"]

    def test_generate_columns_added_with_data(self, factories, db_session):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Org A"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="Org B"
        )
        gr3 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000789", organisation__name="Org C"
        )

        collection = factories.collection.create(grant=grant)

        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        ds_org_item_1 = factories.data_source_organisation_item.create(
            data_source=data_source, external_id="E06000123", _data={"c_allocation": "123"}
        )
        ds_org_item_2 = factories.data_source_organisation_item.create(
            data_source=data_source, external_id="E06000456", _data={"c_allocation": "456"}
        )
        ds_org_item_3 = factories.data_source_organisation_item.create(
            data_source=data_source, external_id="E06000789", _data={"c_allocation": "789"}
        )
        data_source.schema.root["c_added_col"] = DataSourceSchemaColumn(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            presentation_options=QuestionPresentationOptions(),
            data_options=QuestionDataOptions(),
            original_column_name="Added column",
        )
        ds_org_item_1._data["c_added_col"] = "one"
        ds_org_item_2._data["c_added_col"] = "two"
        ds_org_item_3._data["c_added_col"] = "three"
        db_session.flush()

        csv_content = generate_latest_csv_template(data_source)
        reader = csv.reader(StringIO(csv_content.getvalue()))

        rows = list(reader)
        assert len(rows) == 4

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation", "Added column"]
        assert rows[1] == ["E06000123", gr.organisation.name, "123", "one"]
        assert rows[2] == ["E06000456", gr2.organisation.name, "456", "two"]
        assert rows[3] == ["E06000789", gr3.organisation.name, "789", "three"]

    def test_generate_columns_added_no_data(self, factories, db_session):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000123", organisation__name="Org A"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000456", organisation__name="Org B"
        )
        gr3 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="E06000789", organisation__name="Org C"
        )

        collection = factories.collection.create(grant=grant)

        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[1, 2, 3],
        )

        data_source.schema.root["c_added_col"] = DataSourceSchemaColumn(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            presentation_options=QuestionPresentationOptions(),
            data_options=QuestionDataOptions(),
            original_column_name="Added column",
        )
        db_session.flush()

        csv_content = generate_latest_csv_template(data_source)
        reader = csv.reader(StringIO(csv_content.getvalue()))

        rows = list(reader)
        assert len(rows) == 4

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation", "Added column"]
        assert rows[1] == ["E06000123", gr.organisation.name, "1", ""]
        assert rows[2] == ["E06000456", gr2.organisation.name, "2", ""]
        assert rows[3] == ["E06000789", gr3.organisation.name, "3", ""]

    def test_generate_csv_large(self, factories, track_sql_queries, db_session):
        grant = factories.grant.create()
        factories.grant_recipient.create_batch(20, grant=grant)

        collection = factories.collection.create(grant=grant)

        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
        )
        db_session.expire_all()

        # retrieve this here to mimic the behaviour of the route
        data_source = get_data_source(data_source_id=data_source.id, with_organisation_items=True)
        with track_sql_queries() as queries:
            result = generate_latest_csv_template(data_source)

        reader = csv.reader(StringIO(result.getvalue()))

        rows = list(reader)
        assert len(rows) == 21
        assert len(queries) == 3


class TestUploadHeaderOnlyDataSetFiles:
    def test_uploads_csv_with_identifier_and_schema_headers(self, factories, mock_s3_service_calls):
        collection = factories.collection.create()
        data_source = factories.data_source.create(
            grant=collection.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        assert len(data_source.organisation_items) == 0

        upload_header_only_data_set_files(data_source)

        assert len(mock_s3_service_calls.upload_file_calls) == 1
        upload_call = mock_s3_service_calls.upload_file_calls[0]
        uploaded_file = upload_call.args[0]
        uploaded_content = uploaded_file.read().decode("utf-8")
        reader = csv.reader(StringIO(uploaded_content))
        headers = next(reader)
        expected_headers = DATA_SET_IDENTIFIER_COLUMN_HEADERS + [
            column.original_column_name for column in data_source.schema.root.values()
        ]
        assert headers == expected_headers

    def test_uploaded_csv_contains_only_headers_no_data_rows(self, factories, mock_s3_service_calls):
        collection = factories.collection.create()
        data_source = factories.data_source.create(
            grant=collection.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        upload_header_only_data_set_files(data_source)

        uploaded_file = mock_s3_service_calls.upload_file_calls[0].args[0]
        uploaded_content = uploaded_file.read().decode("utf-8")
        reader = csv.reader(StringIO(uploaded_content))
        rows = list(reader)
        assert len(rows) == 1

    def test_updates_file_metadata_with_new_key(self, factories, mock_s3_service_calls):
        collection = factories.collection.create()
        data_source = factories.data_source.create(
            grant=collection.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        original_filename = data_source.file_metadata.original_filename

        upload_header_only_data_set_files(data_source)

        assert data_source.file_metadata.original_filename == original_filename
        assert str(data_source.grant_id) in data_source.file_metadata.s3_key
        assert str(data_source.id) in data_source.file_metadata.s3_key

    def test_raises_for_non_grant_recipient_type(self, factories, mock_s3_service_calls):
        collection = factories.collection.create()
        data_source = factories.data_source.create(
            grant=collection.grant,
            collection=collection,
            type=DataSourceType.CUSTOM,
        )

        with pytest.raises(ValueError, match="Cannot upload a non-grant-recipient data set"):
            upload_header_only_data_set_files(data_source)

    def test_raises_when_missing_grant_id(self, factories, mock_s3_service_calls):
        data_source = factories.data_source.build(
            type=DataSourceType.GRANT_RECIPIENT,
            grant=None,
            grant_id=None,
        )

        with pytest.raises(ValueError, match="Cannot upload a non-grant-recipient data set"):
            upload_header_only_data_set_files(data_source)

    def test_raises_when_missing_file_metadata(self, factories, mock_s3_service_calls):
        data_source = factories.data_source.build(
            type=DataSourceType.GRANT_RECIPIENT,
            grant_id=uuid.uuid4(),
            file_metadata=None,
        )

        with pytest.raises(ValueError, match="Cannot upload a non-grant-recipient data set"):
            upload_header_only_data_set_files(data_source)

    def test_raises_when_missing_schema(self, factories, mock_s3_service_calls):
        data_source = factories.data_source.build(
            type=DataSourceType.GRANT_RECIPIENT,
            grant_id=uuid.uuid4(),
        )
        data_source.schema = None

        with pytest.raises(ValueError, match="Cannot upload a non-grant-recipient data set"):
            upload_header_only_data_set_files(data_source)
