import json
from pathlib import Path

import pytest
from pydantic import BaseModel

from app.common.data.types import DataSourceType
from app.common.expressions.references import (
    DataSourceReference,
    EvaluationStatement,
    ExpressionReference,
    ExpressionStatement,
    InterpolationStatement,
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


class TestExpressionStatement:
    def test_base_class_references_raises(self):
        statement = ExpressionStatement("anything")
        with pytest.raises(NotImplementedError):
            _ = statement.references


class TestEvaluationStatementReferences:
    def test_empty_returns_no_references(self):
        assert EvaluationStatement("").references == []

    def test_plain_constant_returns_no_references(self):
        assert EvaluationStatement("1 + 2").references == []

    def test_bare_name_becomes_a_reference(self):
        assert EvaluationStatement("potato").references == [ExpressionReference("potato")]

    def test_dotted_attribute_chain_becomes_single_reference(self):
        references = EvaluationStatement("a.b.c.d").references
        assert references == [ExpressionReference("a.b.c.d")]

    def test_attribute_chain_is_not_also_split_into_bare_parts(self):
        references = EvaluationStatement("a.b").references
        assert references == [ExpressionReference("a.b")]

    def test_function_callees_are_not_treated_as_references(self):
        assert EvaluationStatement("q_123 > Decimal('100')").references == [ExpressionReference("q_123")]

    def test_date_function_call_does_not_yield_date_as_a_reference(self):
        assert EvaluationStatement("q_123 <= date(2024, 1, 2)").references == [ExpressionReference("q_123")]

    def test_wrapped_references_are_picked_up_via_ast_grouping(self):
        references = EvaluationStatement("((q_123)) + ((q_234)) == 100").references
        assert references == [ExpressionReference("q_123"), ExpressionReference("q_234")]

    def test_multiple_distinct_references_preserve_insertion_order(self):
        references = EvaluationStatement("q_123 > 1 and q_234 < 2").references
        assert references == [ExpressionReference("q_123"), ExpressionReference("q_234")]

    def test_duplicate_references_are_deduplicated(self):
        references = EvaluationStatement("q_123 > q_123").references
        assert references == [ExpressionReference("q_123")]

    def test_function_argument_extracted_but_callee_is_not(self):
        references = EvaluationStatement("uk_postcode_match(q_123)").references
        assert references == [ExpressionReference("q_123")]

    def test_syntax_error_returns_empty_without_crashing(self):
        assert EvaluationStatement("q_123 > (").references == []

    def test_reference_shaped_token_inside_string_literal_is_ignored(self):
        references = EvaluationStatement("'q_123' == q_234").references
        assert references == [ExpressionReference("q_234")]

    def test_non_reference_shaped_identifier_is_still_extracted(self):
        # The extractor does not filter by reference shape; downstream validation can reject.
        references = EvaluationStatement("q_123 + x").references
        assert references == [ExpressionReference("q_123"), ExpressionReference("x")]

    def test_malformed_safe_qid_is_still_extracted(self):
        references = EvaluationStatement("q_not_a_uuid > 1").references
        assert references == [ExpressionReference("q_not_a_uuid")]

    def test_count_references(self):
        statement = EvaluationStatement("q_123 + q_123 > q_234 + q_345")

        assert statement.count_references(ExpressionReference("q_123")) == 2
        assert statement.count_references(ExpressionReference("q_234")) == 1
        assert statement.count_references(ExpressionReference("q_345")) == 1


class TestInterpolationStatementReferences:
    def test_empty_returns_no_references(self):
        assert InterpolationStatement("").references == []

    def test_plain_text_returns_no_references(self):
        assert InterpolationStatement("hello world").references == []

    def test_single_wrapped_reference(self):
        references = InterpolationStatement("Your answer was ((q_123))").references
        assert references == [ExpressionReference("q_123")]

    def test_wrapped_nested_reference(self):
        references = InterpolationStatement("Value: ((d_123.c_col))").references
        assert references == [ExpressionReference("d_123.c_col")]

    def test_multiple_references_dedup_and_preserve_order(self):
        references = InterpolationStatement("Hi ((q_123)) / ((q_123)) / ((q_234))").references
        assert references == [ExpressionReference("q_123"), ExpressionReference("q_234")]

    @pytest.mark.xfail
    def test_complex_interpolation_expression_contributes_all_inner_references(self):
        # Note: as of 20/04/2026, interpolation statements can't be set up with complex inner statements like this
        # but theoretically they could/should be supported. Supporting this requires increased complexity in parsing
        # EvaluationStatements embedded inside InterpolationStatements, so is left as an exercise for the future when we
        # need it.
        references = InterpolationStatement("Total is ((q_123 + q_234))").references
        assert references == [ExpressionReference("q_123"), ExpressionReference("q_234")]

    @pytest.mark.parametrize(
        "case",
        json.loads((Path(__file__).parents[3] / "fixtures" / "reference-regex-validation.json").read_text())[
            "test_cases"
        ],
        ids=lambda case: case["pattern"],
    )
    def test_find_references_in_expression_shared_fixtures(self, case):
        assert InterpolationStatement(case["pattern"]).references == [
            ExpressionReference(ref).unwrapped for ref in case["references"]
        ]

    def test_count_references(self):
        statement = InterpolationStatement("Hello ((q_123)). How are you today, (( q_123))? Do you like ((q_234))?")

        assert statement.count_references(ExpressionReference("q_123")) == 2
        assert statement.count_references(ExpressionReference("q_234")) == 1
