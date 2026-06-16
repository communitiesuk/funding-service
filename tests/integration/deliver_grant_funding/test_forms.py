import io

import pytest
from werkzeug.datastructures import FileStorage, MultiDict

from app import DATA_SET_EXTERNAL_ID_COLUMN_HEADER, DATA_SET_GRANT_RECIPIENT_COLUMN_HEADER, ExpressionReference
from app.common.data.models import Expression
from app.common.data.types import (
    DataSourceType,
    ExpressionType,
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


class TestUploadDataSetForm:
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
            assert "Column 'Allocation' is missing from the selected file" in form.file.errors[0]
            assert f"is being used in '{question.name}'" in form.file.errors[0]
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
        assert len(form.file.errors) == 2
        assert (
            f"Column 'British pounds' is missing from the selected file but is being used in '{question_1.name}' "
            + "Add the column to the file or remove the form reference"
        ) in form.file.errors
        assert (
            f"Column 'Just text' is missing from the selected file but is being used in '{question_2.name}' "
            + "Add the column to the file or remove the form reference"
        ) in form.file.errors

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
