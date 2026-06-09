import csv
import uuid
from io import StringIO

from app.common.data.types import (
    DataSourceSchemaColumn,
    DataSourceType,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.constants import DATA_SET_EXTERNAL_ID_COLUMN_HEADER, DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER
from app.deliver_grant_funding.data_sets import (
    BritishPoundsError,
    DataTypeError,
    check_missing_data,
    generate_latest_csv_template,
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
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
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
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
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
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
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
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
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
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
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
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
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
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
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
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
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
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(organisation__external_id="EC456")
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


class TestCheckMissingData:
    def test_missing_data_flagged_and_tracks_correct_columns(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(organisation__external_id="EC456")
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
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr2.organisation.name,
                "Notes": "",
                "Summary": "",
            },
        ]

        result = check_missing_data(data_set.data_columns, all_rows)

        assert result.row_results[0].missing_columns == ["Notes"]
        assert result.row_results[1].missing_columns == ["Notes", "Summary"]

    def test_missing_data_returns_empty_result_when_no_missing_data(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(organisation__external_id="EC456")
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
                "Notes": "Some notes",
                "Summary": "ok",
            },
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr2.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr2.organisation.name,
                "Notes": "Words",
                "Summary": "More words",
            },
        ]

        result = check_missing_data(data_set.data_columns, all_rows)

        assert result.has_missing_data is False
        assert result.row_results == []


class TestValidateDataSetGrantRecipients:
    def test_valid_csv_returns_no_errors(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
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
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
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

    def test_unknown_recipient_name_is_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "Rogue Organisation",
                "Amount": "100",
            }
        ]
        errors = validate_data_set_grant_recipients(data_set, [gr], all_rows)
        assert any("Grant recipient 'Rogue Organisation' not found in grant recipients" in e for e in errors)

    def test_duplicate_external_id_is_error_for_grant_recipient_type(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
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

    def test_grant_recipient_missing_from_csv(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
        gr2 = factories.grant_recipient.create(organisation__external_id="T0002")
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr.organisation.external_id,
                DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: gr.organisation.name,
                "Amount": "100",
            }
        ]
        errors = validate_data_set_grant_recipients(data_set, [gr, gr2], all_rows)
        assert any(
            f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER} '{gr2.organisation.external_id}' is missing from the CSV" in e
            for e in errors
        )
        assert any(f"'{gr2.organisation.name}' is missing from the CSV" in e for e in errors)

    def test_external_id_without_recipient_name_is_error(self, factories):
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
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
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
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
        gr = factories.grant_recipient.create(organisation__external_id="T0001")
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
            organisation__external_id="T0001",
            organisation__name="Ministry of Testing",
        )
        data_set = _make_data_set(data_columns=["Amount"])
        all_rows = [
            {
                DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "T0001",
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
        gr = factories.grant_recipient.create(organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(organisation__external_id="EC456")
        gr3 = factories.grant_recipient.create(organisation__external_id="EC789")
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
        assert any(f"Grant recipient '{gr.organisation.name}' already appears" in e for e in errors)
        assert any(
            f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER} '{gr3.organisation.external_id}' is missing from the CSV" in e
            for e in errors
        )
        assert any(f"'{gr3.organisation.name}' is missing from the CSV" in e for e in errors)
        assert any(f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER} 'AB1111' not found in grant recipients" in e for e in errors)
        assert any("Grant recipient 'Rivendell' not found in grant recipients" in e for e in errors)


class TestGenerateLatestCsvTemplate:
    def test_generate_no_changes(self, factories):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(grant=grant, organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(grant=grant, organisation__external_id="EC456")
        gr3 = factories.grant_recipient.create(grant=grant, organisation__external_id="EC789")

        collection = factories.collection.create(grant=grant)

        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[123, 456, 789],
        )

        csv_content = generate_latest_csv_template(data_source)
        reader = csv.reader(StringIO(csv_content))

        rows = list(reader)
        assert len(rows) == 4

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation"]
        assert rows[1] == ["EC123", gr.organisation.name, "123"]
        assert rows[2] == ["EC456", gr2.organisation.name, "456"]
        assert rows[3] == ["EC789", gr3.organisation.name, "789"]

    def test_generate_grant_recipient_added(self, factories):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(
            grant=grant, organisation__external_id="EC123", organisation__name="AAA org"
        )
        gr2 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="EC456", organisation__name="BBB org"
        )
        gr3 = factories.grant_recipient.create(
            grant=grant, organisation__external_id="EC789", organisation__name="CCC org"
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
            grant=grant, organisation__external_id="EC124", organisation__name="AAB org"
        )

        csv_content = generate_latest_csv_template(data_source)
        reader = csv.reader(StringIO(csv_content))

        rows = list(reader)
        assert len(rows) == 5

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation"]
        assert rows[1] == ["EC123", gr.organisation.name, "123"]
        assert rows[2] == ["EC124", gr4.organisation.name, ""]
        assert rows[3] == ["EC456", gr2.organisation.name, "456"]
        assert rows[4] == ["EC789", gr3.organisation.name, "789"]

    def test_generate_grant_recipient_removed(self, factories, db_session):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(grant=grant, organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(grant=grant, organisation__external_id="EC456")
        gr3 = factories.grant_recipient.create(grant=grant, organisation__external_id="TO_REMOVE")

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
        reader = csv.reader(StringIO(csv_content))

        rows = list(reader)
        assert len(rows) == 3

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation"]
        assert rows[1] == ["EC123", gr.organisation.name, "123"]
        assert rows[2] == ["EC456", gr2.organisation.name, "456"]

    def test_generate_no_changes_data_missing(self, factories):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(grant=grant, organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(grant=grant, organisation__external_id="EC456")
        gr3 = factories.grant_recipient.create(grant=grant, organisation__external_id="EC789")

        collection = factories.collection.create(grant=grant)

        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[123, None, 789],
        )

        csv_content = generate_latest_csv_template(data_source)
        reader = csv.reader(StringIO(csv_content))

        rows = list(reader)
        assert len(rows) == 4

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation"]
        assert rows[1] == ["EC123", gr.organisation.name, "123"]
        assert rows[2] == ["EC456", gr2.organisation.name, ""]
        assert rows[3] == ["EC789", gr3.organisation.name, "789"]

    def test_generate_columns_added_with_data(self, factories, db_session):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(grant=grant, organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(grant=grant, organisation__external_id="EC456")
        gr3 = factories.grant_recipient.create(grant=grant, organisation__external_id="EC789")

        collection = factories.collection.create(grant=grant)

        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        ds_org_item_1 = factories.data_source_organisation_item.create(
            data_source=data_source, external_id="EC123", _data={"c_allocation": "123"}
        )
        ds_org_item_2 = factories.data_source_organisation_item.create(
            data_source=data_source, external_id="EC456", _data={"c_allocation": "456"}
        )
        ds_org_item_3 = factories.data_source_organisation_item.create(
            data_source=data_source, external_id="EC789", _data={"c_allocation": "789"}
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
        reader = csv.reader(StringIO(csv_content))

        rows = list(reader)
        assert len(rows) == 4

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation", "Added column"]
        assert rows[1] == ["EC123", gr.organisation.name, "123", "one"]
        assert rows[2] == ["EC456", gr2.organisation.name, "456", "two"]
        assert rows[3] == ["EC789", gr3.organisation.name, "789", "three"]

    def test_generate_columns_added_no_data(self, factories, db_session):
        grant = factories.grant.create()
        gr = factories.grant_recipient.create(grant=grant, organisation__external_id="EC123")
        gr2 = factories.grant_recipient.create(grant=grant, organisation__external_id="EC456")
        gr3 = factories.grant_recipient.create(grant=grant, organisation__external_id="EC789")

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
        reader = csv.reader(StringIO(csv_content))

        rows = list(reader)
        assert len(rows) == 4

        assert rows[0] == ["Organisation ID", "Grant recipient", "Allocation", "Added column"]
        assert rows[1] == ["EC123", gr.organisation.name, "1", ""]
        assert rows[2] == ["EC456", gr2.organisation.name, "2", ""]
        assert rows[3] == ["EC789", gr3.organisation.name, "3", ""]
