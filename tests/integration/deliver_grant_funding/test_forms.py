import io

import pytest
from werkzeug.datastructures import FileStorage, MultiDict
from wtforms import ValidationError
from wtforms.validators import StopValidation

from app import (
    DATA_SET_EXTERNAL_ID_COLUMN_HEADER,
    DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER,
    ExpressionReference,
)
from app.common.collections.types import YesNoAnswer
from app.common.data.models import Expression
from app.common.data.types import (
    DataSourceType,
    ExpressionType,
    QuestionDataType,
    SubmissionEventType,
    TasklistSectionStatusEnum,
)
from app.common.expressions.managed import GreaterThan, IsYes, LessThan
from app.common.helpers.collections import SubmissionHelper
from app.deliver_grant_funding.forms import RequestChangesSubmissionForm, UploadDataSetForm
from tests.models import ALL_COLUMN_TYPE_HEADERS_STR, FactoryAnswer


def _build_file_upload_form_data(csv_content: str) -> MultiDict:
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
    return data


class TestUploadDataSetForm:
    def test_new_data_valid(
        self,
        factories,
    ):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        data = _build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR + "\na,b,£100,1.2,hello,5,$10,12km" + "\na,b,£100,1.2,hello,1,$10,12km"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is True

    def test_new_data_valid_with_missing_values(
        self,
        factories,
    ):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        data = _build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR + "\na,b,£100,,hello,5,$10,12km" + "\na,b,£100,1.2,hello,,$10,12km"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is True

    @pytest.mark.parametrize("is_existing", (True, False))
    def test_remove_referenced_column_raises_error(self, factories, is_existing):
        if is_existing:
            collection = factories.collection.create()
            data_source = factories.data_source.create(
                grant=collection.grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
            )
            question = factories.question.create(
                form__collection=collection, text=f"How did you spend the ((d_{data_source.id.hex}.c_allocation))?"
            )

            assert len(data_source.depended_on_by_columns) == 1

        data = _build_file_upload_form_data(
            csv_content=(
                f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER},{DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER},"
                + "Another column\na,b,1000\nc,d,3000"
            )
        )
        form = UploadDataSetForm(
            existing_data_source_names=[], existing_datasource=data_source if is_existing else None
        )
        form.process(data)

        if is_existing:
            assert form.validate() is False
            assert "Column 'Allocation' is missing from the selected file" in form.data_errors[0]
            assert f"is being used in '{question.name}'" in form.data_errors[0]
        else:
            assert form.validate() is True

    def test_remove_multiple_referenced_columns_raises_all_errors(self, factories):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            grant=collection.grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        question_1 = factories.question.create(
            form__collection=collection,
            text=f"How did you spend the ((d_{data_source.id.hex}.c_british_pounds))?",
        )
        question_2 = factories.question.create(
            form__collection=collection,
            text=f"Why did you pick ((d_{data_source.id.hex}.c_just_text))?",
        )

        assert len(data_source.depended_on_by_columns) == 2

        data = _build_file_upload_form_data(
            csv_content=(
                f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER},{DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER},"
                + "Another column\na,b,1000\nc,d,3000"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is False
        assert len(form.data_errors) == 2
        assert (
            f"Column 'British pounds' is missing from the selected file but is being used in '{question_1.name}' "
            + "Add the column to the file or remove the form reference"
        ) in form.data_errors
        assert (
            f"Column 'Just text' is missing from the selected file but is being used in '{question_2.name}' "
            + "Add the column to the file or remove the form reference"
        ) in form.data_errors

    def test_error_wording_for_different_types_of_reference_when_column_removed(self, factories):
        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        question_1 = factories.question.create(
            form__collection=collection,
            text=f"How did you approach the theme of ((d_{data_source.id.hex}.c_just_text))?",
        )
        question_2 = factories.question.create(
            form__collection=collection,
            text="How much did you spend in total?",
            expressions=[
                Expression.from_evaluatable_expression(
                    LessThan(
                        subject_reference=ExpressionReference.from_data_source_column(data_source, "c_british_pounds"),
                        maximum_value=100,
                    ),
                    ExpressionType.CONDITION,
                    factories.user.create(),
                )
            ],
        )
        question_3 = factories.question.create(
            form__collection=collection,
            text="How many staff in total worked on the project?",
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(
                        subject_reference=ExpressionReference.from_data_source_column(data_source, "c_decimal_number"),
                        minimum_value=100,
                    ),
                    ExpressionType.VALIDATION,
                    factories.user.create(),
                )
            ],
        )

        data = _build_file_upload_form_data(
            csv_content=(
                f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER},{DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER},"
                + "Another column\na,b,1000\nc,d,3000"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is False
        assert len(form.data_errors) == 3
        assert (
            f"Column 'Just text' is missing from the selected file but is being used in '{question_1.name}' "
            + "Add the column to the file or remove the form reference"
        ) in form.data_errors
        assert (
            "Column 'British pounds' is missing from the selected file but is being used in a condition for "
            + f"'{question_2.name}' Add the column to the file or remove the form reference"
        ) in form.data_errors
        assert (
            "Column 'Decimal number' is missing from the selected file but is being referenced in validation for "
            + f"'{question_3.name}' Add the column to the file or remove the form reference"
        ) in form.data_errors

    def test_same_column_referenced_in_multiple_places_raises_all_errors(
        self,
        factories,
    ):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
        )
        question_1 = factories.question.create(
            form__collection=collection, text=f"How did you spend the ((d_{data_source.id.hex}.c_allocation))?"
        )
        question_2 = factories.question.create(
            form__collection=collection,
            text="How did you spend the money?",
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(
                        subject_reference=ExpressionReference.from_data_source_column(data_source, "c_allocation"),
                        minimum_value=100,
                    ),
                    ExpressionType.CONDITION,
                    factories.user.create(),
                )
            ],
        )
        question_3 = factories.question.create(
            form__collection=collection,
            text="How did you spend the money?",
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(
                        subject_reference=ExpressionReference.from_data_source_column(data_source, "c_allocation"),
                        minimum_value=100,
                    ),
                    ExpressionType.VALIDATION,
                    factories.user.create(),
                )
            ],
        )

        data = _build_file_upload_form_data(
            csv_content=(
                f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER},{DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER},"
                + "Another column\na,b,1000\nc,d,3000"
            )
        )

        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is False
        assert len(form.data_errors) == 3
        assert (
            f"Column 'Allocation' is missing from the selected file but is being used in '{question_1.name}' "
            + "Add the column to the file or remove the form reference"
        ) in form.data_errors
        assert (
            "Column 'Allocation' is missing from the selected file but is being used in a condition for "
            + f"'{question_2.name}' Add the column to the file or remove the form reference"
        ) in form.data_errors
        assert (
            "Column 'Allocation' is missing from the selected file but is being referenced in validation for "
            + f"'{question_3.name}' Add the column to the file or remove the form reference"
        ) in form.data_errors

    @pytest.mark.parametrize("bad_value", ["£twelve", "abc", "$100", "£1oo"])
    def test_new_data_in_existing_columns_does_not_match_formatting_british_pounds(self, factories, bad_value):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        data = _build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR
                + "\na,b,£100,1.2,hello,5,$10,12km"
                + f"\na,b,{bad_value},1.2,hello,5,$10,12km"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is False
        assert (
            "One or more numbers in column 'British pounds' are not formatted as British pounds to 2 decimal places "
            + "with the '£' prefix. For example, £100.00"
        ) in form.data_errors

    def test_new_data_in_existing_columns_does_not_match_prefix(self, factories):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        data = _build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR + "\na,b,£100,1.2,hello,5,$10,12km" + "\na,b,£100,1.2,hello,5,€10,12km"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is False
        assert ("One or more numbers in column 'Whole number prefix' do not match the prefix ('$')") in form.data_errors

    def test_new_data_in_existing_columns_does_not_match_suffix(
        self,
        factories,
    ):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        data = _build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR + "\na,b,£100,1.2,hello,5,$10,12km" + "\na,b,£100,1.2,hello,5,$10,12miles"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is False
        assert (
            "One or more numbers in column 'Whole number suffix' do not match the suffix ('km')"
        ) in form.data_errors

    def test_new_data_in_existing_columns_does_not_match_integer(
        self,
        factories,
    ):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        data = _build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR + "\na,b,£100,1.2,hello,5,$10,12km" + "\na,b,£100,1.2,hello,1.5,$10,12km"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is False
        assert ("One or more numbers in column 'Whole number' are not whole numbers") in form.data_errors

    def test_new_data_in_existing_columns_is_not_a_decimal_number(
        self,
        factories,
    ):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        data = _build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR + "\na,b,£100,1.2,hello,5,$10,12km" + "\na,b,£100,hello,hello,5,$10,12km"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is False
        assert ("One or more numbers in column 'Decimal number' are not decimal numbers") in form.data_errors

    def test_new_data_in_existing_columns_has_too_many_decimal_places(
        self,
        factories,
    ):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        data = _build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR + "\na,b,£100,1.2,hello,5,$10,12km" + "\na,b,£100,1.2345,hello,5,$10,12km"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is False
        assert ("One or more numbers in column 'Decimal number' has more than 3 decimal places") in form.data_errors

    def test_multiple_format_errors_in_same_column_appear_once(
        self,
        factories,
    ):

        collection = factories.collection.create()
        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            has_column_of_each_type=True,
        )
        data = _build_file_upload_form_data(
            csv_content=(
                ALL_COLUMN_TYPE_HEADERS_STR
                + "\na,b,£100,1.2,hello,5,$10,12km"
                + "\na,b,£twelve,1.2,hello,5,$10,12km"
                + "\na,b,£1oo,1.2,hello,5,$10,12km"
                + "\na,b,£100,1.2,hello,5,$10,12km"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source)
        form.process(data)

        assert form.validate() is False
        assert len(form.data_errors) == 1
        assert (
            "One or more numbers in column 'British pounds' are not formatted as British pounds to 2 decimal places "
            + "with the '£' prefix. For example, £100.00"
        ) in form.data_errors

    def test_new_data_valid_but_changes_submitted_submission(
        self,
        factories,
    ):

        collection = factories.collection.create()
        gr1 = factories.grant_recipient.create(grant=collection.grant)
        gr2 = factories.grant_recipient.create(grant=collection.grant)

        data_source = factories.data_source.create(
            collection=collection,
            grant=collection.grant,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[100, 200],
        )
        factories.question.create(
            form__collection=collection,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text=f"How did you spend the ((d_{data_source.id.hex}.c_allocation))?",
        )

        data = _build_file_upload_form_data(
            csv_content=(
                f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER},{DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER},Allocation"
                + f"\n{gr1.organisation.external_id},{gr1.organisation.name},120"
                + f"\n{gr2.organisation.external_id},{gr2.organisation.name},200"
            )
        )
        form = UploadDataSetForm(
            existing_data_source_names=[],
            existing_datasource=data_source,
            submitted_orgs=[gr1.organisation],
        )
        form.process(data)

        assert form.validate() is False
        assert form.changed_column_errors["Allocation"][0] == gr1.organisation.name

    class TestValidateDataForExistingSubmissions:
        def test_valid_none_submitted(self, factories):
            collection = factories.collection.create()
            data_source = factories.data_source.create(
                collection=collection,
                grant=collection.grant,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
            )
            form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=data_source, submitted_orgs=[])
            form._validate_data_for_existing_submissions(
                existing_datasource=data_source,
                rows=[
                    {
                        DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E000123",
                        DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "test",
                        "Allocation": "123",
                    }
                ],
            )

        def test_valid_submitted_unchanged(self, factories):
            collection = factories.collection.create()
            gr1 = factories.grant_recipient.create(grant=collection.grant)
            data_source = factories.data_source.create(
                collection=collection,
                grant=collection.grant,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=["100"],
            )
            form = UploadDataSetForm(
                existing_data_source_names=[], existing_datasource=data_source, submitted_orgs=[gr1.organisation]
            )
            form._validate_data_for_existing_submissions(
                existing_datasource=data_source,
                rows=[
                    {
                        DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr1.organisation.external_id,
                        DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "test",
                        "Allocation": "100",
                    }
                ],
            )

        def test_valid_with_prefix(self, factories):
            collection = factories.collection.create()
            gr1 = factories.grant_recipient.create(grant=collection.grant)
            data_source = factories.data_source.create(
                collection=collection,
                grant=collection.grant,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=["100"],
            )
            form = UploadDataSetForm(
                existing_data_source_names=[], existing_datasource=data_source, submitted_orgs=[gr1.organisation]
            )
            form._validate_data_for_existing_submissions(
                existing_datasource=data_source,
                rows=[
                    {
                        DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr1.organisation.external_id,
                        DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "test",
                        "Allocation": "£100",  # same value, but with the optional prefix
                    }
                ],
            )

        def test_valid_with_formatting_mismatch(self, factories):
            collection = factories.collection.create()
            gr1 = factories.grant_recipient.create(grant=collection.grant)
            data_source = factories.data_source.create(
                collection=collection,
                grant=collection.grant,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=["100000000"],
            )
            form = UploadDataSetForm(
                existing_data_source_names=[], existing_datasource=data_source, submitted_orgs=[gr1.organisation]
            )
            form._validate_data_for_existing_submissions(
                existing_datasource=data_source,
                rows=[
                    {
                        DATA_SET_EXTERNAL_ID_COLUMN_HEADER: gr1.organisation.external_id,
                        DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "test",
                        "Allocation": "£1,0000000,0     ",  # same value, but with odd formatting
                    }
                ],
            )

        def test_invalid_missing_row_for_submitted_org(self, factories):
            collection = factories.collection.create()
            gr = factories.grant_recipient.create(grant=collection.grant, organisation__external_id="E000123")
            data_source = factories.data_source.create(
                collection=collection,
                grant=collection.grant,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=[100],
            )
            form = UploadDataSetForm(
                existing_data_source_names=[], existing_datasource=data_source, submitted_orgs=[gr.organisation]
            )
            with pytest.raises(ValidationError) as e:
                form._validate_data_for_existing_submissions(
                    existing_datasource=data_source,
                    rows=[
                        {
                            DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E000999",
                            DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "test999",
                            "Allocation": "123",
                        }
                    ],
                )
            assert str(e.value) == f"The file does not contain a row for grant recipient {gr.organisation.name}"

        def test_invalid_changes_data_for_submitted_org(self, factories):
            collection = factories.collection.create()
            gr = factories.grant_recipient.create(grant=collection.grant, organisation__external_id="E000123")
            data_source = factories.data_source.create(
                collection=collection,
                grant=collection.grant,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=[100],
            )
            form = UploadDataSetForm(
                existing_data_source_names=[], existing_datasource=data_source, submitted_orgs=[gr.organisation]
            )
            with pytest.raises(StopValidation) as e:
                form._validate_data_for_existing_submissions(
                    existing_datasource=data_source,
                    rows=[
                        {
                            DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E000123",
                            DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "test",
                            "Allocation": "123",
                        }
                    ],
                )
            assert str(e.value) == "There is a problem"
            assert form.changed_column_errors["Allocation"][0] == gr.organisation.name

        def test_invalid_missing_data_for_submitted_org(self, factories):
            collection = factories.collection.create()
            gr = factories.grant_recipient.create(grant=collection.grant, organisation__external_id="E000123")
            data_source = factories.data_source.create(
                collection=collection,
                grant=collection.grant,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=[100],
            )
            form = UploadDataSetForm(
                existing_data_source_names=[], existing_datasource=data_source, submitted_orgs=[gr.organisation]
            )
            with pytest.raises(StopValidation) as e:
                form._validate_data_for_existing_submissions(
                    existing_datasource=data_source,
                    rows=[
                        {
                            DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E000123",
                            DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "test",
                            "Allocation": "",
                        }
                    ],
                )
            assert str(e.value) == "There is a problem"
            assert form.changed_column_errors["Allocation"][0] == gr.organisation.name

        def test_invalid_removes_column_for_submitted_org(self, factories):
            collection = factories.collection.create()
            gr = factories.grant_recipient.create(grant=collection.grant, organisation__external_id="E000123")
            data_source = factories.data_source.create(
                collection=collection,
                grant=collection.grant,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=[100],
            )
            form = UploadDataSetForm(
                existing_data_source_names=[], existing_datasource=data_source, submitted_orgs=[gr.organisation]
            )
            with pytest.raises(StopValidation) as e:
                form._validate_data_for_existing_submissions(
                    existing_datasource=data_source,
                    rows=[
                        {
                            DATA_SET_EXTERNAL_ID_COLUMN_HEADER: "E000123",
                            DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER: "test",
                            "New column": "123",
                        }
                    ],
                )
            assert str(e.value) == "There is a problem"
            assert form.removed_column_errors["Allocation"][0] == gr.organisation.name


class TestRequestChangesSubmissionForm:
    def test_section_choices_exclude_not_needed_sections(self, factories):
        # Creating a Section with a Yes/No question - this will condition Section 2
        yes_no_question = factories.question.create(data_type=QuestionDataType.YES_NO)
        needed_form = yes_no_question.form

        # Creating Section 2 - this will be Not Needed when Section 1 is answered No
        not_needed_form = factories.form.create(collection=needed_form.collection)
        factories.question.create(
            form=not_needed_form,
            expressions=[
                Expression.from_evaluatable_expression(
                    IsYes(subject_reference=ExpressionReference.from_question(yes_no_question)),
                    ExpressionType.CONDITION,
                    needed_form.collection.created_by,
                )
            ],
        )

        # Create and submit submission with Section 1 answered No, which will make Section 2 Not Needed
        submission = factories.submission.create(
            collection=needed_form.collection,
            answers=[FactoryAnswer(yes_no_question, YesNoAnswer(False))],
        )
        factories.submission_event.create(
            submission=submission,
            related_entity_id=needed_form.id,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
        )

        # Check Section status are as expected
        helper = SubmissionHelper(submission)
        assert helper.get_tasklist_status_for_form(needed_form) == TasklistSectionStatusEnum.COMPLETED
        assert helper.get_tasklist_status_for_form(not_needed_form) == TasklistSectionStatusEnum.NOT_NEEDED

        form = RequestChangesSubmissionForm(submission_helper=helper)
        choice_ids = [choice[0] for choice in form.section_ids.choices]

        # Not needed form is not included in the choices, but the needed form is
        assert str(needed_form.id) in choice_ids
        assert str(not_needed_form.id) not in choice_ids
