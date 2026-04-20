from uuid import uuid4

import pytest

from app.common.data.types import (
    DataSourceSchema,
    DataSourceSchemaColumn,
    DataSourceType,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions.references import ExpressionReference


class TestExpressionReference:
    class TestQuestion:
        def test_question_exists(self, factories):
            q = factories.question.create()

            reference = ExpressionReference(q.safe_qid)
            assert reference.question == q

        def test_question_does_not_exist(self):
            reference = ExpressionReference(f"q_{uuid4().hex}")
            assert reference.question is None

        def test_question_is_none_for_non_question_reference(self):
            reference = ExpressionReference(f"d_{uuid4().hex}.c_col")
            assert reference.question is None

    class TestDataSourceColumn:
        def test_data_source_exists(self, factories):
            collection = factories.collection.create()
            allocation_column = DataSourceSchemaColumn(
                data_type=QuestionDataType.NUMBER,
                presentation_options=QuestionPresentationOptions(prefix="£"),
                data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                original_column_name="Allocation",
            )
            data_source = factories.data_source.create(
                grant=collection.grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                items=None,
                schema=DataSourceSchema.model_validate({"c_allocation": allocation_column}),
            )

            reference = ExpressionReference(f"{data_source.safe_did}.c_allocation")
            assert reference.data_source_column == allocation_column

        def test_data_source_does_not_exist(self):
            reference = ExpressionReference(f"d_{uuid4().hex}.c_col")
            assert reference.data_source_column is None

        def test_data_source_is_none_for_non_data_source_reference(self):
            reference = ExpressionReference(f"q_{uuid4().hex}")
            assert reference.data_source_column is None

    class TestGetDataType:
        def test_raises_none_for_question_reference_to_missing_question(self):
            reference = ExpressionReference(f"q_{uuid4().hex}")

            with pytest.raises(ValueError):
                _ = reference.data_type

        def test_returns_data_type_for_question_reference(self, factories):
            question = factories.question.create(data_type=QuestionDataType.NUMBER)
            reference = ExpressionReference.from_question(question)

            assert reference.data_type == QuestionDataType.NUMBER

        def test_returns_data_type_for_data_source_column_reference(self, factories):
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            data_source = factories.data_source.create(
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                items=None,
                schema=DataSourceSchema.model_validate(
                    {
                        "c_threshold": DataSourceSchemaColumn(
                            data_type=QuestionDataType.NUMBER,
                            presentation_options=QuestionPresentationOptions(prefix="£"),
                            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                            original_column_name="Threshold",
                        ),
                    }
                ),
            )
            reference = ExpressionReference.from_data_source_column(data_source, "c_threshold")

            assert reference.data_type == QuestionDataType.NUMBER

        def test_raises_for_data_source_column_that_does_not_exist(self, factories):
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            data_source = factories.data_source.create(
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                items=None,
                schema=DataSourceSchema.model_validate(
                    {
                        "c_threshold": DataSourceSchemaColumn(
                            data_type=QuestionDataType.NUMBER,
                            presentation_options=QuestionPresentationOptions(),
                            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
                            original_column_name="Threshold",
                        ),
                    }
                ),
            )
            reference = ExpressionReference.from_data_source_column(data_source, "c_missing")

            with pytest.raises(ValueError):
                _ = reference.data_type

        def test_raises_for_reference_to_missing_data_source(self):
            reference = ExpressionReference(f"d_{uuid4().hex}.c_col")

            with pytest.raises(ValueError):
                _ = reference.data_type

        def test_raises_for_unknown_reference_shape(self):
            reference = ExpressionReference("something_else")

            with pytest.raises(ValueError):
                _ = reference.data_type
