import io
from decimal import Decimal
from unittest import mock
from unittest.mock import patch

import pytest
from flask import Flask, request
from werkzeug.datastructures import FileStorage, MultiDict
from wtforms import ValidationError

from app.common.data.types import (
    DataSourceType,
    MaximumFileSize,
    NumberTypeEnum,
    QuestionDataType,
    RoleEnum,
)
from app.common.filters import format_thousands
from app.constants import DATA_SET_EXTERNAL_ID_COLUMN_HEADER, DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER
from app.deliver_grant_funding.admin.forms import PlatformAdminCreateCertifiersForm
from app.deliver_grant_funding.forms import (
    GrantAddUserForm,
    GrantGGISForm,
    GrantNameForm,
    QuestionForm,
    UploadDataSetForm,
    _validate_no_blank_lines,
    _validate_no_duplicates,
    strip_string_if_not_empty,
)


class TestFilters:
    def test_strip_string_if_not_empty(self):
        assert strip_string_if_not_empty("  blah ") == "blah"

    def test_format_thousands_integer(self):
        assert format_thousands(1000) == "1,000"
        assert format_thousands(1000000) == "1,000,000"
        assert format_thousands(0) == "0"

    def test_format_thousands_decimal(self):
        assert format_thousands(Decimal("1000.00")) == "1,000.00"
        assert format_thousands(Decimal("1000.123")) == "1,000.123"
        assert format_thousands(Decimal("1000000.34")) == "1,000,000.34"
        assert format_thousands(Decimal("0.0")) == "0.0"


class TestValidators:
    def test_validate_no_blank_lines(self):
        _validate_no_blank_lines(mock.Mock(), mock.Mock(data="  blah  "))

        with pytest.raises(ValidationError):
            _validate_no_blank_lines(mock.Mock(), mock.Mock(data="    "))

    def test_validate_no_duplicates(self):
        _validate_no_duplicates(mock.Mock(), mock.Mock(data="a\nb\nc"))

        with pytest.raises(ValidationError):
            _validate_no_duplicates(mock.Mock(), mock.Mock(data="a\na\na"))


def test_grant_name_form_passes_when_name_does_not_exist():
    form = GrantNameForm()
    form.name.data = "New Grant"

    with patch("app.deliver_grant_funding.forms.grant_name_exists", return_value=False):
        assert form.validate() is True
        assert len(form.name.errors) == 0


def test_grant_name_form_fails_when_name_exists():
    form = GrantNameForm()
    form.name.data = "Existing Grant"

    with patch("app.deliver_grant_funding.forms.grant_name_exists", return_value=True):
        assert form.validate() is False
        assert "Grant name already in use" in form.name.errors


def test_grant_ggis_form_validates_when_no_selected(app: Flask):
    print(request)
    form = GrantGGISForm(data={"has_ggis": "no", "ggis_number": ""})

    # Should return True when "no" is selected and GGIS number can be empty
    assert form.validate() is True
    assert len(form.ggis_number.errors) == 0


def test_grant_ggis_form_validates_when_yes_selected_with_ggis_number(app: Flask):
    form = GrantGGISForm(data={"has_ggis": "yes", "ggis_number": "GGIS123456"})

    # Should return True when "yes" is selected and GGIS number is provided
    assert form.validate() is True
    assert len(form.ggis_number.errors) == 0


def test_grant_ggis_form_fails_when_yes_selected_and_empty(app: Flask):
    form = GrantGGISForm(data={"has_ggis": "yes", "ggis_number": ""})

    # Should return False when "yes" is selected but GGIS number is empty
    assert form.validate() is False
    assert "Enter your GGIS reference number" in form.ggis_number.errors


def test_user_already_in_grant_users(app: Flask, factories, mocker):
    grant = factories.grant.build(name="Test Grant")
    user = factories.user.build(email="test.user@communities.gov.uk")
    factories.user_role.build(user=user, permissions=[RoleEnum.MEMBER], organisation=grant.organisation, grant=grant)
    mocker.patch("app.common.auth.authorisation_helper.get_grant", return_value=grant)

    form = GrantAddUserForm(grant=grant)
    form.user_email.data = "test.admin@communities.gov.uk"

    with (
        patch("app.deliver_grant_funding.forms.get_user_by_email", return_value=user),
    ):
        assert form.validate() is False
        assert "already is a member of" in form.user_email.errors[0]


def test_user_already_platform_admin(app: Flask, factories):
    grant = factories.grant.build(name="Test")
    user = factories.user.build(email="test.user@communities.gov.uk")
    factories.user_role.build(user=user, permissions=[RoleEnum.ADMIN])

    form = GrantAddUserForm(grant=grant)
    form.user_email.data = "test.admin@communities.gov.uk"

    with patch("app.deliver_grant_funding.forms.get_user_by_email", return_value=user):
        assert form.validate() is False
        assert 'This user already is an admin of "Test" so you cannot add them' in form.user_email.errors[0]


class TestQuestionForm:
    def test_max_data_source_items_radios(self, app):
        max_data_source_items = app.config["MAX_DATA_SOURCE_ITEMS_RADIOS"]
        form = QuestionForm(question_type=QuestionDataType.RADIOS)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("data_source_items", "\n".join(str(x) for x in range(max_data_source_items))),
            ]
        )

        form.process(formdata)

        assert form.validate() is True
        assert form.errors == {}

    def test_too_many_data_source_items_radios(self, app):
        max_data_source_items = app.config["MAX_DATA_SOURCE_ITEMS_RADIOS"]
        form = QuestionForm(question_type=QuestionDataType.RADIOS)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("data_source_items", "\n".join(str(x) for x in range(max_data_source_items + 1))),
            ]
        )

        form.process(formdata)

        assert form.validate() is False
        assert form.errors == {
            "data_source_items": [f"You have entered too many options. The maximum is {max_data_source_items}"]
        }

    def test_max_data_source_items_checkboxes(self, app):
        max_data_source_items = app.config["MAX_DATA_SOURCE_ITEMS_CHECKBOXES"]
        form = QuestionForm(question_type=QuestionDataType.CHECKBOXES)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("data_source_items", "\n".join(str(x) for x in range(max_data_source_items))),
            ]
        )

        form.process(formdata)

        assert form.validate() is True
        assert form.errors == {}

    def test_too_many_data_source_items_checkboxes(self, app):
        max_data_source_items = app.config["MAX_DATA_SOURCE_ITEMS_CHECKBOXES"]
        form = QuestionForm(question_type=QuestionDataType.CHECKBOXES)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("data_source_items", "\n".join(str(x) for x in range(max_data_source_items + 1))),
            ]
        )

        form.process(formdata)

        assert form.validate() is False
        assert form.errors == {
            "data_source_items": [f"You have entered too many options. The maximum is {max_data_source_items}"]
        }

    def test_prefixes_and_suffixes_blank_coerced_to_none(self, app):
        form = QuestionForm(question_type=QuestionDataType.NUMBER)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("prefix", ""),
                ("suffix", "   "),
                ("number_type", NumberTypeEnum.INTEGER.value),
            ]
        )

        form.process(formdata)

        assert form.validate() is True
        assert form.prefix.data is None
        assert form.suffix.data is None

    def test_prefixes_and_suffixes_mutually_exclusive(self, app):
        form = QuestionForm(question_type=QuestionDataType.NUMBER)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
                ("prefix", "£"),
                ("suffix", "lbs"),
                ("number_type", NumberTypeEnum.INTEGER.value),
            ]
        )

        form.process(formdata)

        assert form.validate() is False
        assert form.errors == {
            "prefix": ["Remove the suffix if you need a prefix"],
            "suffix": ["Remove the prefix if you need a suffix"],
        }

    def test_number_fields_not_validated_for_non_number_question(self, app):
        form = QuestionForm(question_type=QuestionDataType.TEXT_SINGLE_LINE)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
            ]
        )

        form.process(formdata)

        assert form.validate() is True

    def test_number_type_validated_for_numbers(self, app):
        form = QuestionForm(question_type=QuestionDataType.NUMBER)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
            ]
        )

        form.process(formdata)

        assert form.validate() is False
        assert form.errors == {
            "number_type": ["Select the type of number"],
        }

        formdata.add("number_type", NumberTypeEnum.DECIMAL.value)
        form.process(formdata)

        assert form.validate() is False
        assert form.errors == {
            "max_decimal_places": ["Enter the maximum number of decimal places"],
        }

        formdata.add("max_decimal_places", "2")
        form.process(formdata)
        assert form.validate() is True

    def test_file_upload_validates_file_types_and_maximum_file_size(self, app):
        form = QuestionForm(question_type=QuestionDataType.FILE_UPLOAD)

        formdata = MultiDict(
            [
                ("text", "question"),
                ("hint", ""),
                ("name", "name"),
            ]
        )

        form.process(formdata)

        assert form.validate() is False
        assert "Select at least one file type" in form.errors.get("file_types_supported", [])

        formdata.add("file_types_supported", "PDF")
        formdata.add("maximum_file_size", MaximumFileSize.MEDIUM.value)
        form.process(formdata)

        assert form.validate() is True
        assert form.errors == {}
        assert form.maximum_file_size.data == MaximumFileSize.MEDIUM.value


class TestPlatformAdminCreateCertifiersForm:
    def test_valid_certifiers_data(self, app, factories):
        organisations = factories.organisation.build_batch(3)
        form = PlatformAdminCreateCertifiersForm(organisations=organisations)
        form.certifiers_data.data = (
            "organisation-name\tfirst-name\tlast-name\temail-address\n"
            f"{organisations[0].name}\tJohn\tDoe\tjohn.doe@example.com\n"
            f"{organisations[1].name}\tJane\tSmith\tjane.smith@example.com"
        )

        assert form.validate() is True
        assert len(form.certifiers_data.errors) == 0

    def test_invalid_header_row(self, app, factories):
        organisations = factories.organisation.build_batch(3)
        form = PlatformAdminCreateCertifiersForm(organisations=organisations)
        form.certifiers_data.data = (
            "wrong-header\tfirst-name\tlast-name\temail-address\nTest Org\tJohn\tDoe\tjohn.doe@example.com"
        )

        assert form.validate() is False
        assert "The header row must be exactly" in form.certifiers_data.errors[0]

    def test_invalid_email_address(self, app, factories):
        organisations = factories.organisation.build_batch(3)
        form = PlatformAdminCreateCertifiersForm(organisations=organisations)
        form.certifiers_data.data = (
            f"organisation-name\tfirst-name\tlast-name\temail-address\n"
            f"{organisations[0].name}\tJohn\tDoe\tinvalid-email"
        )

        assert form.validate() is False
        assert "Invalid email address(es)" in form.certifiers_data.errors[0]
        assert "invalid-email" in form.certifiers_data.errors[0]

    def test_invalid_organisation_names_dont_fail_validation(self, app, factories):
        form = PlatformAdminCreateCertifiersForm(organisations=[])
        form.certifiers_data.data = (
            "organisation-name\tfirst-name\tlast-name\temail-address\nTest Org\tJohn\tDoe\tjohn.doe@example.com"
        )

        assert form.validate() is True

    def test_multiple_invalid_email_addresses(self, app, factories):
        organisations = factories.organisation.build_batch(3)
        form = PlatformAdminCreateCertifiersForm(organisations=organisations)
        form.certifiers_data.data = (
            "organisation-name\tfirst-name\tlast-name\temail-address\n"
            f"{organisations[0].name}\tJohn\tDoe\tinvalid-email\n"
            f"{organisations[1].name}\tJane\tSmith\talso-invalid\n"
            f"{organisations[1].name}\tJane\tSmith\tmostly-valid-email-with-smart’quote@example.com"
        )

        assert form.validate() is False
        assert "Invalid email address(es)" in form.certifiers_data.errors[0]
        assert "invalid-email" in form.certifiers_data.errors[0]
        assert "also-invalid" in form.certifiers_data.errors[0]
        assert "mostly-valid-email-with-smart’quote@example.com" in form.certifiers_data.errors[0]

    def test_invalid_tsv_format(self, app, factories):
        organisations = factories.organisation.build_batch(3)
        form = PlatformAdminCreateCertifiersForm(organisations=organisations)
        form.certifiers_data.data = "organisation-name\tfirst-name\tlast-name\temail-address\nTest Org\tJohn"

        assert form.validate() is False
        assert "The tab-separated data is not valid" in form.certifiers_data.errors[0]

    def test_get_normalised_certifiers_data(self, app, factories):
        organisations = factories.organisation.build_batch(3)
        form = PlatformAdminCreateCertifiersForm(organisations=organisations)
        form.certifiers_data.data = (
            "organisation-name\tfirst-name\tlast-name\temail-address\n"
            f"{organisations[0].name}\tJohn\tDoe\tjohn.doe@example.com\n"
            f"{organisations[1].name}\tJane\tSmith\tjane.smith@example.com"
        )

        normalised_data = form.get_normalised_certifiers_data()

        assert len(normalised_data) == 2
        assert normalised_data[0] == (organisations[0].name, "John Doe", "john.doe@example.com")
        assert normalised_data[1] == (organisations[1].name, "Jane Smith", "jane.smith@example.com")


class TestUploadDataSetForm:
    @pytest.mark.parametrize("is_existing", (True, False))
    def test_missing_name_raises_error(self, factories, is_existing):
        csv_content = "Organisation ID,Grant recipient,Amount\nE123,Lothlorien,1000"
        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", ""),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert "Enter the name for this data set" in form.name.errors[0]

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_duplicate_name_raises_error(self, factories, is_existing):
        csv_content = "Organisation ID,Grant recipient,Amount\nE123,Lothlorien,1000\nE456,Rivendell,2000"
        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=["Test Data Set"],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert "A data set with this name already exists for this monitoring report" in form.name.errors[0]

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_missing_file_raises_error(self, factories, is_existing):
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", None),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert "Select a file" in form.file.errors[0]

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_non_csv_file_raises_error(self, factories, is_existing):
        file = FileStorage(
            stream=io.BytesIO(b"not a csv"),
            filename="test.text",
            content_type="text/text",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert "The file must be a CSV" in form.file.errors[0]

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_empty_csv_raises_error(self, factories, is_existing):
        file = FileStorage(
            stream=io.BytesIO(b""),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert "The CSV file must have at least one column" in form.file.errors[0]

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_no_data_rows_csv_raises_error(self, factories, is_existing):
        csv_content = "Organisation ID,Grant recipient,Allocation"
        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert "The CSV file must contain at least one row of data" in form.file.errors[0]

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_empty_grant_recipient_csv_raises_error(self, factories, is_existing):
        csv_content = "Organisation ID,Grant recipient\nE123,Lothlorien\nE456,Numenor"
        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert "The CSV file must contain at least one column of data" in form.file.errors[0]

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_empty_csv_headers_raises_error(self, factories, is_existing):
        csv_content = "Organisation ID,Grant recipient,,Identifier\nE123,Lothlorien,Elves,Trees\nE456,Numenor,Men,Boats"
        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert "The CSV file must have a name for each column" in form.file.errors[0]

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_too_many_rows_raises_error(self, factories, is_existing):
        rows = ["Organisation ID,Grant recipient,Data"] + [f"val{i},val{i},val{i}" for i in range(10001)]
        csv_content = "\n".join(rows)

        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert "The file must contain no more than 10,000 rows" in form.file.errors[0]

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_too_many_headers_raises_error(self, factories, is_existing):
        csv_content = (
            "Organisation ID,Grant recipient,Capital allocation,Revenue allocation,extra header,and again"
            + "\nE123,Lothlorien,1000,2000\nE456,Numenor,3000,4000"
        )
        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert (
            "The CSV file contains rows which are longer or shorter than the number of columns" in form.file.errors[0]
        )

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_too_long_rows_raises_error(self, factories, is_existing):
        csv_content = (
            "Organisation ID,Grant recipient,Capital allocation" + "\nE123,Lothlorien,1000,,,,,\nE456,Numenor,3000"
        )
        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert (
            "The CSV file contains rows which are longer or shorter than the number of columns" in form.file.errors[0]
        )

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_duplicate_column_names_raises_error(self, factories, is_existing):
        csv_content = (
            f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER},{DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER},"
            + "Allocation,Allocation\na,b,1000,2000\nc,d,2000,3000"
        )
        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert "The CSV file contains duplicate column names: Allocation" in form.file.errors[0]

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_duplicate_column_names_after_safe_column_id_raises_error(self, factories, is_existing):
        csv_content = (
            f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER},{DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER},"
            + "Capital Allocation,(Capital-Allocation)\na,b,1000,2000\nc,d,2000,3000"
        )
        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert (
            "The CSV file contains duplicate column names: Capital Allocation, (Capital-Allocation)"
            in form.file.errors[0]
        )

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_missing_required_columns_for_grant_recipient_data_raises_error(self, factories, is_existing):
        csv_content = "Amount,Category\n1000,A\n2000,B"
        file = FileStorage(
            stream=io.BytesIO(csv_content.encode("utf-8")),
            filename="test.csv",
            content_type="text/csv",
        )
        data = MultiDict(
            [
                ("name", "Test Data Set"),
                ("data_source_type", DataSourceType.GRANT_RECIPIENT),
                ("file", file),
            ]
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=factories.data_source.build(type=DataSourceType.GRANT_RECIPIENT)
            if is_existing
            else None,
        )
        form.process(data)

        assert form.validate() is False
        assert (
            f"The CSV file must contain the columns: {DATA_SET_EXTERNAL_ID_COLUMN_HEADER}, "
            f"{DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER}"
        ) in form.file.errors[0]
