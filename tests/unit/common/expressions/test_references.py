import pytest
from pydantic import BaseModel

from app.common.data.types import DataSourceType
from app.common.expressions.references import (
    DataSourceReference,
    ExpressionReference,
)


class TestExpressionReference:
    class TestConstruction:
        def test_direct_construction_stores_unwrapped(self):
            reference = ExpressionReference("q_abc123")
            assert reference == "q_abc123"
            assert reference.unwrapped == "q_abc123"
            assert reference.wrapped == "((q_abc123))"

        def test_direct_construction_allows_wrapped_input(self):
            ref = ExpressionReference("(( q_abc123 ))")
            assert ref == "q_abc123"
            assert ref.unwrapped == "q_abc123"
            assert ref.wrapped == "((q_abc123))"

        def test_from_wrapped_strips_parens(self):
            reference = ExpressionReference.from_wrapped("(( q_abc123 ))")
            assert reference == "q_abc123"

        def test_from_wrapped_tolerates_whitespace(self):
            reference = ExpressionReference.from_wrapped("  ((  q_abc123  ))  ")
            assert reference == "q_abc123"

        def test_from_wrapped_rejects_unwrapped_input(self):
            with pytest.raises(ValueError, match="Expected a wrapped reference"):
                ExpressionReference.from_wrapped("q_abc123")

        def test_from_wrapped_rejects_triple_paren_input(self):
            with pytest.raises(ValueError, match="Expected a wrapped reference"):
                ExpressionReference.from_wrapped("(((q_abc123)))")

    class TestDecomposition:
        def test_question_reference_decomposes_to_question_id(self, factories):
            question = factories.question.build()
            reference = ExpressionReference.from_question(question)
            assert reference.question_id == question.id
            assert reference.data_source_reference is None

        def test_data_source_reference_decomposes_to_ds_ref(self, factories):
            collection = factories.collection.build()
            data_source = factories.data_source.build(
                grant=collection.grant, collection=collection, type=DataSourceType.GRANT_RECIPIENT
            )

            reference = ExpressionReference.from_data_source_column(data_source, "c_allocation")
            assert reference.data_source_reference == DataSourceReference(data_source.id, "c_allocation")
            assert reference.question_id is None

        def test_unknown_shape_decomposes_to_nothing(self):
            reference = ExpressionReference("something_else")
            assert reference.question_id is None
            assert reference.data_source_reference is None

    class TestPydantic:
        def test_round_trips_through_pydantic_model(self):
            class Container(BaseModel):
                ref: ExpressionReference | None = None

            container = Container(ref=ExpressionReference("q_abc"))
            dumped = container.model_dump()
            assert dumped == {"ref": "q_abc"}

            restored = Container.model_validate(dumped)
            assert isinstance(restored.ref, ExpressionReference)
            assert restored.ref == "q_abc"

        def test_accepts_plain_string_on_validation(self):
            class Container(BaseModel):
                ref: ExpressionReference

            restored = Container.model_validate({"ref": "q_abc"})
            assert isinstance(restored.ref, ExpressionReference)
            assert restored.ref == "q_abc"

        def test_accepts_wrapped_string_on_validation_for_backwards_compat(self):
            class Container(BaseModel):
                ref: ExpressionReference

            restored = Container.model_validate({"ref": "((q_abc))"})
            assert isinstance(restored.ref, ExpressionReference)
            assert restored.ref == "q_abc"
            assert restored.ref.wrapped == "((q_abc))"

        def test_json_serialisation_is_plain_string(self):
            class Container(BaseModel):
                ref: ExpressionReference

            container = Container(ref=ExpressionReference("d_xyz.c_col"))
            assert container.model_dump_json() == '{"ref":"d_xyz.c_col"}'
