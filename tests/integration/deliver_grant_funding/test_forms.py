import io

import pytest
from werkzeug.datastructures import FileStorage, MultiDict

from app import DATA_SET_EXTERNAL_ID_COLUMN_HEADER, DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER, ExpressionReference
from app.common.data.models import Expression
from app.common.data.types import (
    DataSourceSchema,
    DataSourceSchemaColumn,
    DataSourceType,
    ExpressionType,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions.managed import GreaterThan, LessThan
from app.deliver_grant_funding.forms import UploadDataSetForm


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


@pytest.fixture(scope="function")
def dataset_with_column_of_each_type(factories):
    grant_recipient = factories.grant_recipient.create()
    collection = factories.collection.create()
    schema = DataSourceSchema.model_validate(
        {
            "c_british_pounds": DataSourceSchemaColumn(
                data_type=QuestionDataType.NUMBER,
                presentation_options=QuestionPresentationOptions(prefix="£"),
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=2),
                original_column_name="British pounds",
            ),
            "c_decimal_number": DataSourceSchemaColumn(
                data_type=QuestionDataType.NUMBER,
                presentation_options=QuestionPresentationOptions(),
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=3),
                original_column_name="Decimal number",
            ),
            "c_just_text": DataSourceSchemaColumn(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                presentation_options=QuestionPresentationOptions(),
                data_options=QuestionDataOptions(),
                original_column_name="Just text",
            ),
            "c_whole_number": DataSourceSchemaColumn(
                data_type=QuestionDataType.NUMBER,
                presentation_options=QuestionPresentationOptions(),
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                original_column_name="Whole number",
            ),
            "c_whole_number_prefix": DataSourceSchemaColumn(
                data_type=QuestionDataType.NUMBER,
                presentation_options=QuestionPresentationOptions(prefix="$"),
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                original_column_name="Whole number prefix",
            ),
            "c_whole_number_suffix": DataSourceSchemaColumn(
                data_type=QuestionDataType.NUMBER,
                presentation_options=QuestionPresentationOptions(prefix="km"),
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                original_column_name="Whole number suffix",
            ),
        }
    )
    data_source = factories.data_source.create(
        grant=grant_recipient.grant, collection=collection, type=DataSourceType.GRANT_RECIPIENT, schema=schema
    )
    yield data_source


class TestUploadDataSetForm:
    @pytest.mark.parametrize("is_existing", (True, False))
    def test_remove_referenced_column_raises_error(self, factories, is_existing):
        if is_existing:
            grant_recipient = factories.grant_recipient.create()
            collection = factories.collection.create()
            data_source = factories.data_source.create(
                grant=grant_recipient.grant,
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
            assert "Column 'Allocation' is missing from the selected file" in form.file.errors[0]
            assert f"is being used in '{question.name}'" in form.file.errors[0]
        else:
            assert form.validate() is True

    def test_remove_multiple_referenced_columns_raises_all_errors(self, factories, dataset_with_column_of_each_type):

        collection = dataset_with_column_of_each_type.collection
        question_1 = factories.question.create(
            form__collection=collection,
            text=f"How did you spend the ((d_{dataset_with_column_of_each_type.id.hex}.c_british_pounds))?",
        )
        question_2 = factories.question.create(
            form__collection=collection,
            text=f"Why did you pick ((d_{dataset_with_column_of_each_type.id.hex}.c_just_text))?",
        )

        assert len(dataset_with_column_of_each_type.depended_on_by_columns) == 2

        data = _build_file_upload_form_data(
            csv_content=(
                f"{DATA_SET_EXTERNAL_ID_COLUMN_HEADER},{DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER},"
                + "Another column\na,b,1000\nc,d,3000"
            )
        )
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=dataset_with_column_of_each_type)
        form.process(data)

        assert form.validate() is False
        assert len(form.file.errors) == 2
        assert (
            f"Column 'British pounds' is missing from the selected file but is being used in '{question_1.name}' "
            + "Add the column to the file or remove the form reference"
        ) in form.file.errors
        assert (
            f"Column 'Just text' is missing from the selected file but is being used in '{question_2.name}' "
            + "Add the column to the file or remove the form reference"
        ) in form.file.errors

    def test_error_wording_for_different_types_of_reference_when_column_removed(
        self, factories, dataset_with_column_of_each_type
    ):

        collection = dataset_with_column_of_each_type.collection
        question_1 = factories.question.create(
            form__collection=collection,
            text=f"How did you approach the theme of ((d_{dataset_with_column_of_each_type.id.hex}.c_just_text))?",
        )
        question_2 = factories.question.create(
            form__collection=collection,
            text="How much did you spend in total?",
            expressions=[
                Expression.from_evaluatable_expression(
                    LessThan(
                        subject_reference=ExpressionReference.from_data_source_column(
                            dataset_with_column_of_each_type, "c_british_pounds"
                        ),
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
                        subject_reference=ExpressionReference.from_data_source_column(
                            dataset_with_column_of_each_type, "c_decimal_number"
                        ),
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
        form = UploadDataSetForm(existing_data_source_names=[], existing_datasource=dataset_with_column_of_each_type)
        form.process(data)

        assert form.validate() is False
        assert len(form.file.errors) == 3
        assert (
            f"Column 'Just text' is missing from the selected file but is being used in '{question_1.name}' "
            + "Add the column to the file or remove the form reference"
        ) in form.file.errors
        assert (
            "Column 'British pounds' is missing from the selected file but is being used in a condition for "
            + f"'{question_2.name}' Add the column to the file or remove the form reference"
        ) in form.file.errors
        assert (
            "Column 'Decimal number' is missing from the selected file but is being referenced in validation for "
            + f"'{question_3.name}' Add the column to the file or remove the form reference"
        ) in form.file.errors

    def test_same_column_referenced_in_multiple_places_raises_all_errors(
        self,
        factories,
    ):

        grant_recipient = factories.grant_recipient.create()
        collection = factories.collection.create()
        data_source = factories.data_source.create(
            grant=grant_recipient.grant,
            collection=collection,
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
        assert len(form.file.errors) == 3
        assert (
            f"Column 'Allocation' is missing from the selected file but is being used in '{question_1.name}' "
            + "Add the column to the file or remove the form reference"
        ) in form.file.errors
        assert (
            "Column 'Allocation' is missing from the selected file but is being used in a condition for "
            + f"'{question_2.name}' Add the column to the file or remove the form reference"
        ) in form.file.errors
        assert (
            "Column 'Allocation' is missing from the selected file but is being referenced in validation for "
            + f"'{question_3.name}' Add the column to the file or remove the form reference"
        ) in form.file.errors
