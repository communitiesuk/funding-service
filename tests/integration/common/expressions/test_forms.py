from datetime import date

import pytest
from werkzeug.datastructures import MultiDict

from app.common.data.interfaces.collections import DependencyOrderException, IncompatibleDataTypeInCalculationException
from app.common.data.interfaces.exceptions import InvalidReferenceInExpression
from app.common.data.types import (
    DataSourceType,
    ExpressionType,
    ManagedExpressionsEnum,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
)
from app.common.expressions import (
    DisallowedExpression,
    ExpressionContext,
    InvalidEvaluationResult,
    UndefinedFunctionInExpression,
    UndefinedOperatorInExpression,
    UndefinedVariableInExpression,
)
from app.common.expressions.forms import _validate_custom_syntax, build_managed_expression_form
from app.common.expressions.managed import Between
from app.common.expressions.references import EvaluationStatement, ExpressionReference, InterpolationStatement
from app.metrics import MetricAttributeName, MetricEventName


class TestBuildManagedExpressionForm:
    # Not intended to be an exhaustive check against all question data types, but to prove that fundamentally the
    # system/framework is capable.

    def test_integer_data_type_condition(self, factories):
        question = factories.question.create(data_type=QuestionDataType.NUMBER)
        _FormClass = build_managed_expression_form(
            ExpressionType.CONDITION, ExpressionReference.from_question(question)
        )
        assert _FormClass
        form = _FormClass()

        assert form.type.choices == [
            (ManagedExpressionsEnum.GREATER_THAN, ManagedExpressionsEnum.GREATER_THAN),
            (ManagedExpressionsEnum.LESS_THAN, ManagedExpressionsEnum.LESS_THAN),
            (ManagedExpressionsEnum.BETWEEN, ManagedExpressionsEnum.BETWEEN),
        ]

    def test_integer_data_type_validation(self, factories):
        question = factories.question.create(data_type=QuestionDataType.NUMBER)
        _FormClass = build_managed_expression_form(
            ExpressionType.VALIDATION, ExpressionReference.from_question(question)
        )
        assert _FormClass
        form = _FormClass()

        assert form.type.choices == [
            (ManagedExpressionsEnum.GREATER_THAN, ManagedExpressionsEnum.GREATER_THAN),
            (ManagedExpressionsEnum.LESS_THAN, ManagedExpressionsEnum.LESS_THAN),
            (ManagedExpressionsEnum.BETWEEN, ManagedExpressionsEnum.BETWEEN),
            (None, None),
            ("CUSTOM", "Calculation with two or more numbers"),
        ]

    def test_recognises_invalid_data_for_a_managed_expression(self, factories):
        question = factories.question.create(data_type=QuestionDataType.NUMBER)
        _FormClass = build_managed_expression_form(
            ExpressionType.CONDITION, ExpressionReference.from_question(question)
        )
        assert _FormClass
        form = _FormClass(
            formdata=MultiDict(
                {
                    "type": "Between",
                    "between_bottom_of_range": "",
                    "between_bottom_inclusive": "",
                    "between_top_of_range": "",
                    "between_top_inclusive": "",
                }
            )
        )
        assert form.validate() is False
        assert form.errors == {
            "between_bottom_of_range": [
                "Enter the minimum value allowed for this question",
            ],
            "between_top_of_range": [
                "Enter the maximum value allowed for this question",
            ],
        }

    def test_can_build_a_managed_expression_from_valid_data(self, factories):
        question = factories.question.create(data_type=QuestionDataType.NUMBER)
        subject_reference = ExpressionReference.from_question(question)

        _FormClass = build_managed_expression_form(ExpressionType.CONDITION, subject_reference)
        assert _FormClass
        form = _FormClass(
            formdata=MultiDict(
                {
                    "type": "Between",
                    "between_bottom_of_range": "0",
                    "between_bottom_inclusive": "",
                    "between_top_of_range": "100",
                    "between_top_inclusive": "1",
                }
            )
        )
        assert form.validate()
        expression: Between = form.get_expression(subject_reference)
        assert expression.name == "Between"
        assert expression.minimum_value == 0
        assert expression.minimum_inclusive is False
        assert expression.maximum_value == 100
        assert expression.maximum_inclusive is True

    def test_can_build_a_managed_expression_with_valid_reference_data__integer(self, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.NUMBER)
        question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.NUMBER)
        subject_reference = ExpressionReference.from_question(question)

        _FormClass = build_managed_expression_form(ExpressionType.VALIDATION, subject_reference)
        assert _FormClass
        form = _FormClass(
            formdata=MultiDict(
                {
                    "type": "Between",
                    "between_bottom_of_range": "0",
                    "between_bottom_inclusive": "",
                    "between_top_of_range": "",
                    "between_top_of_range_expression": ExpressionReference.from_question(referenced_question),
                    "between_top_inclusive": "1",
                }
            )
        )
        assert form.validate()
        expression: Between = form.get_expression(subject_reference)
        assert expression.name == "Between"
        assert expression.minimum_value == 0
        assert expression.minimum_expression is None
        assert expression.minimum_inclusive is False
        assert expression.maximum_value is None
        assert expression.maximum_expression == referenced_question.safe_qid
        assert expression.maximum_expression.wrapped == f"(({referenced_question.safe_qid}))"
        assert expression.maximum_inclusive is True

    def test_can_build_a_managed_expression_with_valid_reference_data__date(self, factories):
        referenced_question = factories.question.create(data_type=QuestionDataType.DATE)
        question = factories.question.create(form=referenced_question.form, data_type=QuestionDataType.DATE)
        subject_reference = ExpressionReference.from_question(question)

        _FormClass = build_managed_expression_form(ExpressionType.VALIDATION, subject_reference)
        assert _FormClass
        form = _FormClass(
            formdata=MultiDict(
                {
                    "type": "Between dates",
                    "between_bottom_of_range": "1 1 2025",
                    "between_bottom_of_range_expression": "",
                    "between_bottom_inclusive": "",
                    "between_top_of_range": "",
                    "between_top_of_range_expression": ExpressionReference.from_question(referenced_question),
                    "between_top_inclusive": "1",
                }
            )
        )
        assert form.validate()
        expression: Between = form.get_expression(subject_reference)
        assert expression.name == "Between dates"
        assert expression.earliest_value == date(2025, 1, 1)
        assert expression.earliest_expression is None
        assert expression.earliest_inclusive is False
        assert expression.latest_value is None
        assert expression.latest_expression == referenced_question.safe_qid
        assert expression.latest_expression.wrapped == f"(({referenced_question.safe_qid}))"
        assert expression.latest_inclusive is True


class TestValidateCustomSyntax:
    def test_valid_expression_same_section(self, factories):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid}))")

        interpolation_context = ExpressionContext.build_expression_context(db_form.collection, "interpolation")
        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        _validate_custom_syntax(
            q3,
            interpolation_context,
            test_expression,
            ExpressionType.VALIDATION,
            "custom_expression",
            evaluation_context=evaluation_context,
        )
        _validate_custom_syntax(
            q3,
            interpolation_context,
            test_expression,
            ExpressionType.VALIDATION,
            "custom_expression",
            evaluation_context=evaluation_context,
        )

    def test_valid_expression_previous_section(self, factories, mocker):
        db_form_0 = factories.form.create()
        previous_question = factories.question.create(
            form=db_form_0,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        db_form = factories.form.create(collection=db_form_0.collection)
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(
            f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid})) + (({previous_question.safe_qid}))"
        )

        evaluation_context = ExpressionContext(
            submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33, previous_question.safe_qid: 44}
        )

        _validate_custom_syntax(
            q3,
            ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
            test_expression,
            ExpressionType.VALIDATION,
            "custom_expression",
            evaluation_context=evaluation_context,
        )

    def test_invalid_expression_out_of_order(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(f"(({q1.safe_qid})) < (({q2.safe_qid}))")

        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(DependencyOrderException) as e:
            _validate_custom_syntax(
                q1,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )
        assert e.value.form_error_message == f"You cannot use {q2.name} because it comes after this question"

        with pytest.raises(DependencyOrderException) as e:
            _validate_custom_syntax(
                q1,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                InterpolationStatement(f"The answer must be less than (({q2.safe_qid}))"),
                ExpressionType.VALIDATION,
                "custom_message",
            )
        assert e.value.form_error_message == f"You cannot use {q2.name} because it comes after this question"

    def test_invalid_expression_forms_out_of_order(self, factories, mocker):
        db_form_0 = factories.form.create()
        db_form = factories.form.create(collection=db_form_0.collection)
        later_form_question = factories.question.create(
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form_0,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(
            f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid})) + (({later_form_question.safe_qid}))"
        )

        evaluation_context = ExpressionContext(
            submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33, later_form_question.safe_qid: 55}
        )

        with pytest.raises(DependencyOrderException) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )
        assert (
            e.value.form_error_message
            == f"You cannot use {later_form_question.name} because it comes after this question"
        )

        with pytest.raises(DependencyOrderException) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                InterpolationStatement(
                    f"The answer must be less than (({q2.safe_qid})) + (({q1.safe_qid})) + "
                    f"(({later_form_question.safe_qid}))"
                ),
                ExpressionType.VALIDATION,
                "custom_message",
            )
        assert (
            e.value.form_error_message
            == f"You cannot use {later_form_question.name} because it comes after this question"
        )

    def test_invalid_expression_bad_reference(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(f"(({q3.safe_qid})) < (({q2.safe_qid})) + ((some_bad_ref))")

        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(InvalidReferenceInExpression) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert e.value.form_error_message == "You cannot use ((some_bad_ref)) because it does not exist"

        with pytest.raises(InvalidReferenceInExpression) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                InterpolationStatement(f"The answer must be less than (({q2.safe_qid})) + ((some_bad_ref))"),
                ExpressionType.VALIDATION,
                "custom_message",
            )

        assert e.value.form_error_message == "You cannot use ((some_bad_ref)) because it does not exist"

    def test_invalid_expression_incompatible_data_type(self, factories, mocker):
        db_form = factories.form.create()
        q1 = factories.question.create(form=db_form, data_type=QuestionDataType.TEXT_MULTI_LINE)
        q2, q3 = factories.question.create_batch(
            2,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid}))")

        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(IncompatibleDataTypeInCalculationException) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert (
            e.value.form_error_message
            == f"You cannot reference {q1.name} because only numbers can be referenced in calculations"
        )

        with pytest.raises(IncompatibleDataTypeInCalculationException) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                InterpolationStatement(f"Must be less than (({q2.safe_qid})) + (({q1.safe_qid}))"),
                ExpressionType.VALIDATION,
                "custom_message",
            )

        assert (
            e.value.form_error_message
            == f"You cannot reference {q1.name} because only numbers can be referenced in calculations"
        )

    def test_invalid_expression_name_not_defined(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid}))")

        evaluation_context = ExpressionContext()

        side_effect = [q3.safe_qid, q2.safe_qid, None]

        # mock the call the _validate_reference as it will raise an exception due to references not being there
        # but we want to test an error at evaluation time instead
        mocker.patch(
            "app.common.expressions.forms._validate_reference",
            side_effect=side_effect,
        )

        with pytest.raises(UndefinedVariableInExpression) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert e.value.form_error_message == f"You cannot use {q1.safe_qid} because it does not exist"

    def test_invalid_expression_unavailable_function(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        test_expression = EvaluationStatement(f"(({q3.safe_qid})) < sum( (({q2.safe_qid})), (({q1.safe_qid})) )")

        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(UndefinedFunctionInExpression) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert e.value.form_error_message == "You cannot use sum in calculations"

    def test_invalid_expression_bad_syntax(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        test_expression = EvaluationStatement(f"(({q3.safe_qid})) < hello there")

        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(DisallowedExpression) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert (
            e.value.form_error_message
            == "The calculation does not make sense. Check it is a complete calculation that only uses accepted symbols"
        )

    def test_invalid_expression_bad_operator(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        test_expression = EvaluationStatement(f"(({q3.safe_qid})) < 2**3")

        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(UndefinedOperatorInExpression) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert (
            e.value.form_error_message
            == "The calculation does not make sense. Check it is a complete calculation that only uses accepted symbols"
        )

    def test_invalid_expression_multiple_references_to_self(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(
            f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid})) + (({q3.safe_qid})) + "
            f"(({q3.safe_qid})) + (({q3.safe_qid}))"
        )

        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(DisallowedExpression) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert e.value.form_error_message == "The expression must include exactly one reference to this question"

    def test_invalid_expression_no_references_to_self(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(f"(({q2.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid}))")

        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(DisallowedExpression) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert e.value.form_error_message == "The expression must include exactly one reference to this question"

    def test_invalid_validation_expression_no_references_to_questions_in_group(self, factories, mocker):
        db_form = factories.form.create()
        group = factories.group.create(form=db_form)
        factories.question.create(
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        evaluation_context = ExpressionContext(submission_data={})

        with pytest.raises(DisallowedExpression) as e:
            _validate_custom_syntax(
                group,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                EvaluationStatement("1 + 1 == 2"),
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert (
            e.value.form_error_message
            == "The calculation must include at least one reference to a question in this group"
        )

    def test_invalid_expression_does_not_evaluate_to_true_or_false(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(f"(({q3.safe_qid})) + (({q2.safe_qid})) + (({q1.safe_qid}))")

        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(InvalidEvaluationResult) as e:
            _validate_custom_syntax(
                q3,
                ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert e.value.form_error_message == "The expression must evaluate to true or false"

    def test_can_reference_data_set_columns(self, factories):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        data_source = factories.data_source.create(
            grant=db_form.collection.grant,
            collection=db_form.collection,
            type=DataSourceType.GRANT_RECIPIENT,
        )

        evaluation_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        # Should not raise any errors
        _validate_custom_syntax(
            q3,
            ExpressionContext.build_expression_context(db_form.collection, "interpolation"),
            EvaluationStatement(f"(({q3.safe_qid})) < (({data_source.safe_did}.c_allocation))"),
            ExpressionType.VALIDATION,
            "custom_expression",
            evaluation_context=evaluation_context,
        )

    def test_metrics_success(self, factories, mock_sentry_metrics):
        q1 = factories.question.create(
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(f"(({q1.safe_qid})) < 5")

        interpolation_context = ExpressionContext.build_expression_context(q1.form.collection, "interpolation")
        evaluation_context = ExpressionContext(
            submission_data={
                q1.safe_qid: 1,
            }
        )

        assert (
            _validate_custom_syntax(
                q1,
                interpolation_context,
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )
            is None
        )
        assert mock_sentry_metrics.call_count == 0
        assert (
            _validate_custom_syntax(
                q1,
                interpolation_context,
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )
            is None
        )
        assert mock_sentry_metrics.call_count == 0

    def test_metrics_failure(self, factories, mock_sentry_metrics):
        q1 = factories.question.create(
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = EvaluationStatement(f"(({q1.safe_qid})) < syntax error")

        evaluation_context = ExpressionContext(
            submission_data={
                q1.safe_qid: 1,
            }
        )

        with pytest.raises(DisallowedExpression):
            _validate_custom_syntax(
                q1,
                ExpressionContext.build_expression_context(q1.form.collection, "interpolation"),
                test_expression,
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=evaluation_context,
            )

        assert mock_sentry_metrics.call_count == 1
        assert mock_sentry_metrics.call_args[0] == (
            MetricEventName.CALCULATION_FIELD_INVALID,
            1,
        )
        assert mock_sentry_metrics.call_args_list[0].kwargs["attributes"] == {
            MetricAttributeName.CALCULATION_INVALID_FIELD.value: "custom_expression",
            MetricAttributeName.CALCULATION_INVALID_REASON.value: "DisallowedExpression",
        }
