from uuid import uuid4

import pytest

from app.common.data.types import (
    DataSourceType,
    QuestionDataType,
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

        def test_question_only_queries_db_on_first_access(self, factories, track_sql_queries):
            q = factories.question.create()
            reference = ExpressionReference(q.safe_qid)

            _ = reference.question

            with track_sql_queries() as queries:
                _ = reference.question
                _ = reference.question.text
                _ = reference.question.data_type

            assert queries == []

    class TestDataSourceColumn:
        def test_data_source_exists(self, factories):
            collection = factories.collection.create()
            data_source = factories.data_source.create(
                grant=collection.grant, collection=collection, type=DataSourceType.GRANT_RECIPIENT
            )

            reference = ExpressionReference(f"{data_source.safe_did}.c_allocation")
            assert reference.data_source_column == data_source.schema.root["c_allocation"]

        def test_data_source_does_not_exist(self):
            reference = ExpressionReference(f"d_{uuid4().hex}.c_col")
            assert reference.data_source_column is None

        def test_data_source_is_none_for_non_data_source_reference(self):
            reference = ExpressionReference(f"q_{uuid4().hex}")
            assert reference.data_source_column is None

        def test_data_source_column_only_queries_db_on_first_access(self, factories, track_sql_queries):
            collection = factories.collection.create()
            data_source = factories.data_source.create(
                grant=collection.grant, collection=collection, type=DataSourceType.GRANT_RECIPIENT
            )
            reference = ExpressionReference(f"{data_source.safe_did}.c_allocation")

            # warm the cache (first access)
            _ = reference.data_source_column

            # subsequent accesses should not fire additional queries
            with track_sql_queries() as queries:
                _ = reference.data_source_column
                _ = reference.data_source_column.data_type
                _ = reference.data_source_column.original_column_name

            assert queries == []

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
                grant=collection.grant, collection=collection, type=DataSourceType.GRANT_RECIPIENT
            )
            reference = ExpressionReference.from_data_source_column(data_source, "c_allocation")

            assert reference.data_type == QuestionDataType.NUMBER

        def test_raises_for_data_source_column_that_does_not_exist(self, factories):
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            data_source = factories.data_source.create(
                grant=collection.grant, collection=collection, type=DataSourceType.GRANT_RECIPIENT
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

    class TestGetDataSource:
        def test_data_source_exists(self, factories):
            collection = factories.collection.create()
            data_source = factories.data_source.create(
                grant=collection.grant, collection=collection, type=DataSourceType.GRANT_RECIPIENT
            )
            reference = ExpressionReference(f"{data_source.safe_did}.c_allocation")
            assert reference.data_source == data_source

        def test_data_source_does_not_exist(self):
            reference = ExpressionReference(f"d_{uuid4().hex}.c_col")
            assert reference.data_source is None

        def test_data_source_is_none_for_non_data_source_reference(self):
            reference = ExpressionReference(f"q_{uuid4().hex}")
            assert reference.data_source is None

        def test_data_source_only_queries_db_on_first_access(self, factories, track_sql_queries):
            collection = factories.collection.create()
            data_source = factories.data_source.create(
                grant=collection.grant, collection=collection, type=DataSourceType.GRANT_RECIPIENT
            )
            reference = ExpressionReference(f"{data_source.safe_did}.c_allocation")

            _ = reference.data_source

            with track_sql_queries() as queries:
                _ = reference.data_source
                _ = reference.data_source.name
                _ = reference.data_source.type

            assert queries == []

    class TestLabel:
        def test_question_label(self, factories):
            q = factories.question.create()

            reference = ExpressionReference(q.safe_qid)
            assert reference.label == q.data_reference_label

        def test_data_source_label(self, factories):
            collection = factories.collection.create()
            data_source = factories.data_source.create(
                grant=collection.grant, collection=collection, type=DataSourceType.GRANT_RECIPIENT
            )
            reference = ExpressionReference(f"{data_source.safe_did}.c_allocation")
            assert reference.label == f"Allocation from {data_source.name} data set"

        def test_invalid_reference_error(self):
            reference = ExpressionReference("something_else")

            with pytest.raises(ValueError):
                _ = reference.label
