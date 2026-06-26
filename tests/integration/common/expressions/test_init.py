import datetime
import uuid
from decimal import Decimal
from unittest.mock import PropertyMock

import pytest

from app.common.collections.types import IntegerAnswer, TextSingleLineAnswer
from app.common.data.models import DataSourceOrganisationItem, Expression
from app.common.data.types import (
    DataSourceSchema,
    DataSourceSchemaColumn,
    DataSourceType,
    ExpressionType,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions import ExpressionContext, UndefinedFunctionInExpression, evaluate, interpolate
from app.common.expressions.managed import BetweenDates, GreaterThan
from app.common.expressions.references import ExpressionReference
from app.common.helpers.collections import SubmissionHelper
from tests.models import FactoryAnswer


class TestExpressionContext:
    def test_layering(self):
        ex = ExpressionContext(
            submission_data={"a": 1, "b": 1, "e": 1, "j": 1},
            expression_context={"a": 2, "c": 2, "d": 2},
            question_form_context={"a": 3, "f": 3, "g": 3},
            default_context={"a": 0, "h": 0, "j": 0},
        )
        assert ex["a"] == 3
        assert ex["b"] == 1
        assert ex["c"] == 2
        assert ex["d"] == 2
        assert ex["e"] == 1
        assert ex["f"] == 3
        assert ex["g"] == 3
        assert ex["h"] == 0

        # for now default context is above submission data to avoid
        # stale data (on now hidden questions) being used in validations
        assert ex["j"] == 0

        with pytest.raises(KeyError):
            assert ex["i"]

    def test_get(self):
        ex = ExpressionContext(
            submission_data={"a": 1, "b": 1, "e": 1},
            expression_context={"a": 2, "c": 2, "d": 2},
        )
        assert ex.get("a") == 1
        assert ex.get("b") == 1
        assert ex.get("c") == 2
        assert ex.get("d") == 2
        assert ex.get("e") == 1
        assert ex.get("f") is None

    def test_length(self):
        ex = ExpressionContext(
            submission_data={"a": 1, "b": 1, "e": 1},
            expression_context={"a": 2, "c": 2, "d": 2},
        )
        assert len(ex) == 5

    def test_contains(self):
        ex = ExpressionContext(
            submission_data={"a": 1, "b": 1, "e": 1},
            expression_context={"a": 2, "c": 2, "d": 2},
        )
        assert "a" in ex
        assert "b" in ex
        assert "c" in ex
        assert "d" in ex
        assert "e" in ex
        assert "f" not in ex

    class TestBuildExpressionContextCrossFormReferences:
        def test_includes_questions_from_earlier_forms(self, factories):
            collection = factories.collection.create(name="My Collection")
            form1 = factories.form.create(collection=collection, title="First Form")
            form2 = factories.form.create(collection=collection, title="Second Form")
            q1 = factories.question.create(form=form1, name="earlier question")
            q2 = factories.question.create(form=form2, name="later question")

            context = ExpressionContext.build_expression_context(
                collection=collection,
                mode="interpolation",
                expression_context_end_point=q2,
                include_children_of_context_end_point=True,
            )

            assert context.is_valid_reference(q1.safe_qid)
            assert context.is_valid_reference(q2.safe_qid)

        def test_excludes_questions_from_later_forms(self, factories):
            collection = factories.collection.create(name="My Collection")
            form1 = factories.form.create(collection=collection, title="First Form")
            form2 = factories.form.create(collection=collection, title="Second Form")
            q1 = factories.question.create(form=form1, name="earlier question")
            q2 = factories.question.create(form=form2, name="later question")

            context = ExpressionContext.build_expression_context(
                collection=collection,
                mode="interpolation",
                expression_context_end_point=q1,
                include_children_of_context_end_point=True,
            )

            assert context.is_valid_reference(q1.safe_qid)
            assert not context.is_valid_reference(q2.safe_qid)

    class TestBuildExpressionContextEndPoints:
        def test_value_error_from_invalid_end_point_combination(self, factories):
            collection = factories.collection.create(name="My Collection")
            form1 = factories.form.create(collection=collection, title="First Form")
            q1 = factories.question.create(form=form1, name="earlier question")

            with pytest.raises(
                ValueError,
                match="include_children_of_context_end_point must be set only when expression_context_end_point is set",
            ):
                ExpressionContext.build_expression_context(
                    collection=collection,
                    mode="interpolation",
                    expression_context_end_point=q1,
                )
            with pytest.raises(
                ValueError,
                match="include_children_of_context_end_point must be set only when expression_context_end_point is set",
            ):
                ExpressionContext.build_expression_context(
                    collection=collection,
                    mode="interpolation",
                    include_children_of_context_end_point=True,
                )
            with pytest.raises(
                ValueError,
                match="include_children_of_context_end_point must be set only when expression_context_end_point is set",
            ):
                ExpressionContext.build_expression_context(
                    collection=collection,
                    mode="interpolation",
                    include_children_of_context_end_point=False,
                )

        def test_always_includes_own_question(self, factories):
            collection = factories.collection.create(name="My Collection")
            form1 = factories.form.create(collection=collection, title="First Form")
            q1 = factories.question.create(form=form1, name="earlier question")

            context = ExpressionContext.build_expression_context(
                collection=collection,
                mode="interpolation",
                expression_context_end_point=q1,
                include_children_of_context_end_point=False,
            )

            assert context.is_valid_reference(q1.safe_qid)

        def test_can_include_children_of_groups(self, factories):
            collection = factories.collection.create(name="My Collection")
            form = factories.form.create(collection=collection, title="First Form")
            g1 = factories.group.create(form=form)
            q1 = factories.question.create(form=form, parent=g1, name="q1")
            q2 = factories.question.create(form=form, parent=g1, name="q2")

            with_context = ExpressionContext.build_expression_context(
                collection=collection,
                mode="interpolation",
                expression_context_end_point=g1,
                include_children_of_context_end_point=True,
            )
            without_context = ExpressionContext.build_expression_context(
                collection=collection,
                mode="interpolation",
                expression_context_end_point=g1,
                include_children_of_context_end_point=False,
            )

            assert with_context.is_valid_reference(q1.safe_qid) is True
            assert with_context.is_valid_reference(q2.safe_qid) is True

            assert without_context.is_valid_reference(q1.safe_qid) is False
            assert without_context.is_valid_reference(q2.safe_qid) is False

    def test_interpolation_labels_include_collection_and_form(self, factories):
        collection = factories.collection.create(name="My Collection")
        form = factories.form.create(collection=collection, title="My Form")
        q = factories.question.create(form=form, name="my question")

        context = ExpressionContext.build_expression_context(collection=collection, mode="interpolation")

        assert context[q.safe_qid] == "((My Collection → My Form → my question))"

    class TestBuildDataSourceContext:
        def test_returns_empty_dict_when_no_submission_helper(self):
            context = ExpressionContext._build_data_source_context(mode="evaluation", submission_helper=None)
            assert context == {}

        def test_returns_empty_dict_when_data_sets_empty(self, factories):
            submission = factories.submission.create()
            helper = SubmissionHelper(submission)

            context = ExpressionContext._build_data_source_context(mode="evaluation", submission_helper=helper)
            assert context == {}

        def test_data_source_with_no_schema_continues(self, factories):
            # This shouldn't ever happen in reality, but testing the behaviour anyway
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            organisation = factories.organisation.create()
            grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
            submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
            data_source = factories.data_source.create(
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
            )
            data_source.schema = None
            helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
            context = ExpressionContext._build_data_source_context(mode="evaluation", submission_helper=helper)
            assert context == {}

        def test_data_source_with_empty_schema_root_raises_error(self, factories):
            # This also shouldn't happen in reality but testing the behaviour anyway
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            organisation = factories.organisation.create()
            grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
            submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
            factories.data_source.create(
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                schema=DataSourceSchema.model_validate({}),
            )

            helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
            with pytest.raises(ValueError):
                ExpressionContext._build_data_source_context(mode="evaluation", submission_helper=helper)

        def test_org_item_none_evaluation_exposes_none_values(self, factories):
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            organisation = factories.organisation.create()
            grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
            submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
            data_source = factories.data_source.create(
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
            )

            helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
            context = ExpressionContext._build_data_source_context(mode="evaluation", submission_helper=helper)

            assert data_source.safe_did in context
            assert context[data_source.safe_did]["c_allocation"] is None

        def test_org_item_none_interpolation_exposes_placeholder_labels(self, factories):
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            organisation = factories.organisation.create()
            grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
            submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
            data_source = factories.data_source.create(
                name="Allocations",
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
            )

            helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
            context = ExpressionContext._build_data_source_context(mode="interpolation", submission_helper=helper)

            assert data_source.safe_did in context
            assert context[data_source.safe_did]["c_allocation"] == "((Allocation from Allocations data set))"

        def test_non_dict_typed_data_is_skipped(self, factories, mocker):
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            organisation = factories.organisation.create()
            grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
            submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
            factories.data_source.create(
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=[1000],
            )

            mocker.patch.object(
                DataSourceOrganisationItem, "data", new_callable=PropertyMock, return_value=[{"col": "val"}]
            )

            helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
            context = ExpressionContext._build_data_source_context(mode="evaluation", submission_helper=helper)
            assert context == {}

        def test_real_org_item_evaluation_returns_typed_values(self, factories):
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            organisation = factories.organisation.create()
            grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
            submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
            data_source = factories.data_source.create(
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=[1000],
            )

            helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
            context = ExpressionContext._build_data_source_context(mode="evaluation", submission_helper=helper)

            assert data_source.safe_did in context
            assert context[data_source.safe_did]["c_allocation"] == 1000

        def test_data_source_organisation_item_filtering(self, factories):
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)

            grant_recipient = factories.grant_recipient.create(grant=grant)
            submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)

            grant_recipient_2 = factories.grant_recipient.create(grant=grant)
            submission_2 = factories.submission.create(collection=collection, grant_recipient=grant_recipient_2)

            data_source = factories.data_source.create(
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=[1000, 9999],
            )

            helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
            context = ExpressionContext._build_data_source_context(mode="interpolation", submission_helper=helper)
            assert context[data_source.safe_did]["c_allocation"] == "£1,000"

            helper = SubmissionHelper.load(submission_2.id, grant_recipient_id=grant_recipient_2.id)
            context = ExpressionContext._build_data_source_context(mode="interpolation", submission_helper=helper)
            assert context[data_source.safe_did]["c_allocation"] == "£9,999"

        def test_real_org_item_interpolation_returns_formatted_string(self, factories):
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            organisation = factories.organisation.create()
            grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
            submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
            data_source = factories.data_source.create(
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=[1000],
            )

            helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
            context = ExpressionContext._build_data_source_context(mode="interpolation", submission_helper=helper)

            assert data_source.safe_did in context
            assert context[data_source.safe_did]["c_allocation"] == "£1,000"

        def test_none_column_value_in_org_item_not_in_context(self, factories):
            # This is explicitly testing _build_data_source_context where _data with None values do not get added to
            # the context. In interpolation, these then get injected with the fallback reference in the normal
            # build_expression_context method.
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            organisation = factories.organisation.create()
            grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
            submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
            data_source = factories.data_source.create(
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                create_gr_org_items=True,
                create_gr_org_items__data=[None],
            )

            helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
            context = ExpressionContext._build_data_source_context(mode="evaluation", submission_helper=helper)

            assert "c_allocation" not in context[data_source.safe_did]

        def test_multiple_data_sources_all_included(self, factories):
            grant = factories.grant.create()
            collection = factories.collection.create(grant=grant)
            organisation = factories.organisation.create()
            grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
            submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)

            ds1 = factories.data_source.create(
                name="Test data set 1",
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
            )
            ds2 = factories.data_source.create(
                name="Test data set 2",
                grant=grant,
                collection=collection,
                type=DataSourceType.GRANT_RECIPIENT,
                schema=DataSourceSchema.model_validate(
                    {
                        "notes": DataSourceSchemaColumn(
                            data_type=QuestionDataType.TEXT_SINGLE_LINE,
                            presentation_options=QuestionPresentationOptions(),
                            data_options=QuestionDataOptions(),
                            original_column_name="Notes",
                        )
                    }
                ),
            )
            helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
            context = ExpressionContext._build_data_source_context(mode="evaluation", submission_helper=helper)

            assert ds1.safe_did in context
            assert ds2.safe_did in context
            assert ds1.safe_did != ds2.safe_did


class TestEvaluatingManagedExpressions:
    def test_greater_than_integer(self, factories):
        user = factories.user.create()
        q0 = factories.question.create()
        question = factories.question.create(
            form=q0.form,
        )
        question.expressions.append(
            Expression.from_evaluatable_expression(
                GreaterThan(subject_reference=ExpressionReference.from_question(q0), minimum_value=3000),
                ExpressionType.CONDITION,
                user,
            )
        )

        expr = question.expressions[0]

        assert evaluate(expr, ExpressionContext({q0.safe_qid: 500})) is False
        assert evaluate(expr, ExpressionContext({q0.safe_qid: 3000})) is False
        assert evaluate(expr, ExpressionContext({q0.safe_qid: 3001})) is True

    def test_greater_than_decimal(self, factories):
        user = factories.user.create()
        q0 = factories.question.create()
        question = factories.question.create(
            form=q0.form,
            expressions=[
                Expression.from_evaluatable_expression(
                    GreaterThan(
                        subject_reference=ExpressionReference.from_question(q0),
                        minimum_value=Decimal("3000.01"),
                    ),
                    ExpressionType.CONDITION,
                    user,
                )
            ],
        )

        expr = question.expressions[0]

        assert evaluate(expr, ExpressionContext({q0.safe_qid: Decimal("500.1")})) is False
        assert evaluate(expr, ExpressionContext({q0.safe_qid: Decimal("3000.0")})) is False
        assert evaluate(expr, ExpressionContext({q0.safe_qid: Decimal("3000.1")})) is True

    @pytest.mark.parametrize(
        "value, expected_result",
        (
            (500, False),
            (3000, False),
            (3001, True),
            (Decimal("500.1"), False),
            (Decimal("3000.0"), False),
            (Decimal("3000.2"), True),
        ),
    )
    def test_expression_with_numerical_reference_data(self, factories, value, expected_result):
        user = factories.user.create()
        q0 = factories.question.create(data_type=QuestionDataType.NUMBER)
        qid = uuid.uuid4()
        q1 = factories.question.create(
            id=qid,
            form=q0.form,
            data_type=QuestionDataType.NUMBER,
        )
        q1.expressions.append(
            Expression.from_evaluatable_expression(
                GreaterThan(
                    subject_reference=ExpressionReference.from_question(q1),
                    minimum_value=None,
                    minimum_expression=ExpressionReference.from_question(q0),
                ),
                ExpressionType.VALIDATION,
                user,
            )  # Double brackets should be ignored by the evaluation engine
        )

        expr = q1.expressions[0]

        assert evaluate(expr, ExpressionContext({q0.safe_qid: 3000, q1.safe_qid: value})) is expected_result

    @pytest.mark.parametrize(
        "value, expected_result",
        (
            (datetime.date(2020, 1, 1), False),
            (datetime.date(2025, 1, 1), False),
            (datetime.date(2023, 1, 1), True),
        ),
    )
    def test_expression_with_date_reference_data(self, factories, value, expected_result):
        user = factories.user.create()
        form = factories.form.create()
        q0, q1 = factories.question.create_batch(2, form=form, data_type=QuestionDataType.DATE)

        qid = uuid.uuid4()
        q2 = factories.question.create(
            id=qid,
            form=q0.form,
            data_type=QuestionDataType.DATE,
        )
        q2.expressions.append(
            Expression.from_evaluatable_expression(
                BetweenDates(
                    subject_reference=ExpressionReference.from_question(q2),
                    earliest_value=None,
                    latest_value=None,
                    earliest_expression=ExpressionReference.from_question(q0),
                    latest_expression=ExpressionReference.from_question(q1),
                ),
                ExpressionType.VALIDATION,
                user,
            )  # Double brackets should be ignored by the evaluation engine
        )

        expr = q2.expressions[0]

        assert (
            evaluate(
                expr,
                ExpressionContext(
                    {
                        q0.safe_qid: datetime.date(2020, 1, 1),
                        q1.safe_qid: datetime.date(2025, 1, 1),
                        q2.safe_qid: value,
                    }
                ),
            )
            is expected_result
        )


class TestEvaluatingManagedExpressionsWithRequiredFunctions:
    @pytest.mark.parametrize(
        "question_value, expected_result",
        [
            (datetime.date(2023, 12, 1), True),
            (datetime.date(2026, 12, 1), False),
        ],
    )
    def test_managed_expression_with_required_function_allowed_imported(
        self, factories, mocker, question_value, expected_result
    ):
        expr = factories.expression.create(statement="q_123 < date(2024, 1, 1)", type_=ExpressionType.VALIDATION)
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"date": datetime.date},
        )
        assert evaluate(expr, ExpressionContext(submission_data={"q_123": question_value})) is expected_result

    @pytest.mark.parametrize(
        "question_value, expected_result",
        [
            (309, True),
            (0, False),
        ],
    )
    def test_managed_expression_with_required_function_allowed_builtin(
        self, factories, mocker, question_value, expected_result
    ):
        expr = factories.expression.create(statement="q_123 > min(1,2)", type_=ExpressionType.VALIDATION)
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"min": min},
        )
        assert evaluate(expr, ExpressionContext(submission_data={"q_123": question_value})) is expected_result

    @pytest.mark.parametrize(
        "question_value, expected_result",
        [
            (100, True),
            (5, False),
        ],
    )
    def test_managed_expression_with_required_function_allowed_custom(
        self, factories, mocker, question_value, expected_result
    ):
        def _custom_test_function():
            return 42

        expr = factories.expression.create(statement="q_123 > calculate_result()", type_=ExpressionType.VALIDATION)
        mocker.patch(
            "app.common.data.models.Expression.required_functions",
            new_callable=PropertyMock,
            return_value={"calculate_result": _custom_test_function},
        )
        assert evaluate(expr, ExpressionContext(submission_data={"q_123": question_value})) is expected_result

    def test_managed_expression_with_required_function_builtin_not_present_builtin(self, factories):
        # test with a builtin function that isn't on the allowed list
        expr = factories.expression.create(statement="q_123 > max(1,2)", type_=ExpressionType.VALIDATION)
        # Don't patch the required_functions property, so it returns an empty dict
        with pytest.raises(UndefinedFunctionInExpression):
            evaluate(expr, ExpressionContext(submission_data={"q_123": 123}))

    def test_managed_expression_with_required_function_not_present_custom(self, factories):
        def _custom_test_function():
            return 42

        # Test with a custom function that isn't on the allowed list
        expr = factories.expression.create(statement="q_123 > _custom_test_function()", type_=ExpressionType.VALIDATION)
        # Don't patch the required_functions property, so it returns an empty dict
        with pytest.raises(UndefinedFunctionInExpression):
            evaluate(expr, ExpressionContext(submission_data={"q_123": 123}))


class TestExtendingWithAddAnotherContext:
    def test_extending_with_add_another_context(self, factories):
        group = factories.group.create(add_another=True)
        q1 = factories.question.create(parent=group)
        q2 = factories.question.create(parent=group)
        submission = factories.submission.create(
            collection=group.form.collection,
            answers=[
                FactoryAnswer(q1, TextSingleLineAnswer("v0"), add_another_index=0),
                FactoryAnswer(q2, TextSingleLineAnswer("e0"), add_another_index=0),
                FactoryAnswer(q1, TextSingleLineAnswer("v1"), add_another_index=1),
                FactoryAnswer(q2, TextSingleLineAnswer("e1"), add_another_index=1),
                FactoryAnswer(q1, TextSingleLineAnswer("v2"), add_another_index=2),
            ],
        )

        context = ExpressionContext.build_expression_context(
            collection=group.form.collection,
            submission_helper=SubmissionHelper(submission),
            data_manager=submission.data_manager,
            mode="evaluation",
        )
        assert context.get(q1.safe_qid) is None

        context = context.with_add_another_context(
            component=q1, data_manager=submission.data_manager, add_another_index=1
        )
        assert context.get(q1.safe_qid) == "v1"
        assert context.get(q2.safe_qid) == "e1"

    def test_extending_with_add_another_context_with_partial_submit_data(self, factories):
        group = factories.group.create(add_another=True)
        q1 = factories.question.create(parent=group)
        q2 = factories.question.create(parent=group)
        q3 = factories.question.create(parent=group)
        submission = factories.submission.create(
            collection=group.form.collection,
            answers=[
                FactoryAnswer(q1, TextSingleLineAnswer("v0"), add_another_index=0),
                FactoryAnswer(q2, TextSingleLineAnswer("e0"), add_another_index=0),
                FactoryAnswer(q2, TextSingleLineAnswer("e1"), add_another_index=1),
                FactoryAnswer(q1, TextSingleLineAnswer("v2"), add_another_index=2),
            ],
        )

        context = ExpressionContext.build_expression_context(
            collection=group.form.collection,
            submission_helper=SubmissionHelper(submission),
            data_manager=submission.data_manager,
            mode="evaluation",
        )
        assert context.get(q1.safe_qid) is None
        assert context.get(q2.safe_qid) is None
        assert context.get(q3.safe_qid) is None

        context = context.with_add_another_context(
            component=q1, data_manager=submission.data_manager, add_another_index=1
        )
        assert context.get(q1.safe_qid) is None
        assert context.get(q2.safe_qid) == "e1"
        assert context.get(q3.safe_qid) is None

    def test_extending_with_new_add_another_index(self, factories):
        component = factories.question.create(add_another=True)
        submission = factories.submission.create(
            collection=component.form.collection,
            answers=[FactoryAnswer(component, TextSingleLineAnswer("1"), add_another_index=0)],
        )
        context = ExpressionContext.build_expression_context(
            collection=component.form.collection,
            submission_helper=SubmissionHelper(submission),
            data_manager=submission.data_manager,
            mode="evaluation",
        )

        # if the add another entry hasn't been created yet we'd expect the context to be unchanged
        assert (
            context.with_add_another_context(component, data_manager=submission.data_manager, add_another_index=1)
            == context
        )

    def test_extending_with_different_add_another_context(self, factories):
        component = factories.question.create(add_another=True)
        submission = factories.submission.create(
            collection=component.form.collection,
            answers=[
                FactoryAnswer(component, TextSingleLineAnswer("1"), add_another_index=0),
                FactoryAnswer(component, TextSingleLineAnswer("2"), add_another_index=1),
                FactoryAnswer(component, TextSingleLineAnswer("3"), add_another_index=2),
            ],
        )
        submission_helper = SubmissionHelper(submission)
        ex = submission_helper.cached_evaluation_context
        with pytest.raises(
            ValueError,
            match="overriding with different add_another_context",
        ):
            ex.with_add_another_context(
                component, data_manager=submission_helper.submission.data_manager, add_another_index=0
            ).with_add_another_context(
                component, data_manager=submission_helper.submission.data_manager, add_another_index=1
            )

    def test_extending_with_same_add_another_context(self, factories):
        component = factories.question.create(add_another=True)
        submission = factories.submission.create(
            collection=component.form.collection,
            answers=[
                FactoryAnswer(component, TextSingleLineAnswer("1"), add_another_index=0),
                FactoryAnswer(component, TextSingleLineAnswer("2"), add_another_index=1),
                FactoryAnswer(component, TextSingleLineAnswer("3"), add_another_index=2),
            ],
        )

        submission_helper = SubmissionHelper(submission)
        ex = submission_helper.cached_evaluation_context

        # adding the same add another context should not raise
        ex.with_add_another_context(
            component, data_manager=submission_helper.submission.data_manager, add_another_index=0
        ).with_add_another_context(
            component, data_manager=submission_helper.submission.data_manager, add_another_index=0
        )

    def test_extending_with_non_add_another_component(self, factories):
        component = factories.question.create(add_another=False)
        submission = factories.submission.create(collection=component.form.collection)
        ex = ExpressionContext(submission_data={"a": [1, 2, 3], "b": 1, "c": 1})
        with pytest.raises(ValueError) as e:
            ex.with_add_another_context(
                component, data_manager=SubmissionHelper(submission).submission.data_manager, add_another_index=0
            )
        assert str(e.value) == "add_another_context can only be set for add another components"


class TestExtendingWithQuestionFormContext:
    def test_with_question_form_context_does_not_override_original_by_reference(self):
        ex = ExpressionContext(
            submission_data={"a": 1, "b": 1, "e": 1},
            expression_context={"a": 2, "c": 2, "d": 2},
        )
        question_form_expression_context = ex.with_question_form_context({"b": 3})
        assert question_form_expression_context["b"] == 3
        assert ex["b"] == 1

    class TestDataSourceContextPreservedOnContextExtension:
        def test_with_question_form_context_preserves_data_source_context(self):
            ex = ExpressionContext(
                submission_data={"q_abc": "answer"},
                data_source_context={"d_abc": {"capital_allocation": 1000}},
            )
            new_context = ex.with_question_form_context({"q_abc": "updated_answer"})

            assert new_context["d_abc"]["capital_allocation"] == 1000
            assert new_context["q_abc"] == "updated_answer"
            assert ex["q_abc"] == "answer"

        def test_with_add_another_context_preserves_data_source_context(self, factories):
            group = factories.group.create(add_another=True)
            q1 = factories.question.create(parent=group)
            submission = factories.submission.create(
                collection=group.form.collection,
                answers=[FactoryAnswer(q1, TextSingleLineAnswer("v0"), add_another_index=0)],
            )

            ex = ExpressionContext(
                submission_data={q1.safe_qid: "answer"},
                data_source_context={"d_abc": {"capital_allocation": 1000}},
            )

            helper = SubmissionHelper(submission=submission)
            new_context = ex.with_add_another_context(
                component=q1, data_manager=helper.submission.data_manager, add_another_index=0
            )

            assert new_context["d_abc"]["capital_allocation"] == 1000


class TestWithDefaultContext:
    def test_returns_unchanged_with_no_submission_helper(self):
        ctx = ExpressionContext(submission_data={"qid": 5})
        result = ctx.with_default_context(None)
        assert result is ctx

    def test_defaults_answers_set_based_on_visibility(self, factories):
        visible_question_with_answer = factories.question.create(data_type=QuestionDataType.NUMBER)
        visible_question_without_answer = factories.question.create(
            form=visible_question_with_answer.form, data_type=QuestionDataType.NUMBER
        )
        hidden_question = factories.question.create(
            form=visible_question_with_answer.form, data_type=QuestionDataType.NUMBER
        )
        factories.expression.create(
            question=hidden_question,
            statement="False",
            type_=ExpressionType.CONDITION,
        )
        submission = factories.submission.create(
            collection=visible_question_with_answer.form.collection,
            answers=[FactoryAnswer(visible_question_with_answer, IntegerAnswer(value=123))],
        )
        helper = SubmissionHelper(submission)

        result = ExpressionContext.build_expression_context(
            collection=visible_question_with_answer.form.collection,
            mode="evaluation",
            submission_helper=helper,
            data_manager=helper.submission.data_manager,
        ).with_default_context(helper)

        assert result.get(visible_question_with_answer.safe_qid) == 123
        assert result.get(visible_question_without_answer.safe_qid) is None
        assert result.get(hidden_question.safe_qid) == 0


class TestDataSourceInterpolation:
    def test_data_source_reference_interpolated_with_real_value(self, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        organisation = factories.organisation.create()
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
        submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[1000],
        )

        helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
        ds_context = ExpressionContext._build_data_source_context(mode="interpolation", submission_helper=helper)
        context = ExpressionContext(data_source_context=ds_context)

        result = interpolate(f"(({data_source.safe_did}.c_allocation))", context)
        assert result == "£1,000"

    def test_data_source_reference_with_no_org_item_renders_placeholder(self, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        organisation = factories.organisation.create()
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
        submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
        ds_context = ExpressionContext._build_data_source_context(mode="interpolation", submission_helper=helper)
        context = ExpressionContext(data_source_context=ds_context)

        result = interpolate(f"(({data_source.safe_did}.c_allocation))", context)
        assert result == "((Allocation from Grant allocation data set))"

    def test_unknown_data_source_reference_renders_raw(self):
        context = ExpressionContext(data_source_context={})

        result = interpolate("((d_doesnotexist.some_col))", context)
        assert result == "((d_doesnotexist.some_col))"


class TestDataSourceEvaluation:
    def test_real_column_value_evaluates_correctly(self, factories):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        organisation = factories.organisation.create()
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
        submission = factories.submission.create(collection=collection, grant_recipient=grant_recipient)
        data_source = factories.data_source.create(
            grant=grant,
            collection=collection,
            type=DataSourceType.GRANT_RECIPIENT,
            create_gr_org_items=True,
            create_gr_org_items__data=[1000],
        )

        helper = SubmissionHelper.load(submission.id, grant_recipient_id=grant_recipient.id)
        ds_context = ExpressionContext._build_data_source_context(mode="evaluation", submission_helper=helper)
        context = ExpressionContext(data_source_context=ds_context)

        expr = Expression(
            statement=f"{data_source.safe_did}.c_allocation > 500",
            type_=ExpressionType.CONDITION,
        )
        assert evaluate(expr, context) is True


class TestIsValidReferenceWithDataSources:
    def test_valid_data_source_column_reference(self):
        context = ExpressionContext(data_source_context={"d_abc": {"c_capital_allocation": 1000}})
        assert context.is_valid_reference("d_abc.c_capital_allocation") is True

    def test_invalid_data_source_key(self):
        context = ExpressionContext(data_source_context={"d_abc": {"c_capital_allocation": 1000}})
        assert context.is_valid_reference("d_xyz.c_capital_allocation") is False

    def test_invalid_data_source_column(self):
        context = ExpressionContext(data_source_context={"d_abc": {"c_capital_allocation": 1000}})
        assert context.is_valid_reference("d_abc.nonexistent_column") is False

    def test_valid_data_source_column_with_none_value(self):
        context = ExpressionContext(data_source_context={"d_abc": {"c_capital_allocation": None}})
        assert context.is_valid_reference("d_abc.c_capital_allocation") is True

    def test_data_source_key_without_column_returns_true(self):
        context = ExpressionContext(data_source_context={"d_abc": {"c_capital_allocation": 1000}})
        assert context.is_valid_reference("d_abc") is True
