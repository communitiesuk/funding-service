import pytest

from app.common.data.interfaces.collections import DependencyOrderException, IncompatibleDataTypeInCalculationException
from app.common.data.interfaces.exceptions import InvalidReferenceInExpression
from app.common.data.types import ExpressionType, NumberTypeEnum, QuestionDataOptions, QuestionDataType
from app.common.expressions import (
    DisallowedExpression,
    ExpressionContext,
    InvalidEvaluationResult,
    UndefinedFunctionInExpression,
    UndefinedOperatorInExpression,
    UndefinedVariableInExpression,
)
from app.common.expressions.forms import _validate_custom_syntax
from app.metrics import MetricAttributeName, MetricEventName


class TestValidateCustomSyntax:
    def test_valid_expression_same_section(self, factories):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid}))"

        expr_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        assert (
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )
            is None
        )
        assert (
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", False
            )
            is None
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

        test_expression = (
            f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid})) + (({previous_question.safe_qid}))"
        )

        expr_context = ExpressionContext(
            submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33, previous_question.safe_qid: 44}
        )

        assert (
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )
            is None
        )

    def test_invalid_expression_out_of_order(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = f"(({q1.safe_qid})) < (({q2.safe_qid}))"

        expr_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(DependencyOrderException) as e:
            _validate_custom_syntax(
                q1, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )
        assert e.value.form_error_message == f"You cannot use {q2.name} because it comes after this question"

        with pytest.raises(DependencyOrderException) as e:
            _validate_custom_syntax(
                q1,
                expr_context,
                f"The answer must be less than (({q2.safe_qid}))",
                ExpressionType.VALIDATION,
                "custom_message",
                False,
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

        test_expression = (
            f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid})) + (({later_form_question.safe_qid}))"
        )

        expr_context = ExpressionContext(
            submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33, later_form_question.safe_qid: 55}
        )

        with pytest.raises(DependencyOrderException) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )
        assert (
            e.value.form_error_message
            == f"You cannot use {later_form_question.name} because it comes after this question"
        )

        with pytest.raises(DependencyOrderException) as e:
            _validate_custom_syntax(
                q3,
                expr_context,
                (
                    f"The answer must be less than (({q2.safe_qid})) + (({q1.safe_qid})) + "
                    f"(({later_form_question.safe_qid}))"
                ),
                ExpressionType.VALIDATION,
                "custom_message",
                False,
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

        test_expression = f"(({q3.safe_qid})) < (({q2.safe_qid})) + ((some_bad_ref))"

        expr_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(InvalidReferenceInExpression) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )

        assert e.value.form_error_message == "You cannot use ((some_bad_ref)) because it does not exist"

        with pytest.raises(InvalidReferenceInExpression) as e:
            _validate_custom_syntax(
                q3,
                expr_context,
                f"The answer must be less than (({q2.safe_qid})) + ((some_bad_ref))",
                ExpressionType.VALIDATION,
                "custom_message",
                False,
            )

        assert e.value.form_error_message == "You cannot use ((some_bad_ref)) because it does not exist"

    def test_invalid_expression_reference_missing_from_context(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        test_expression = f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid}))"

        # exclude q1 from the context
        expr_context = ExpressionContext(submission_data={q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(InvalidReferenceInExpression) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )

        assert e.value.form_error_message == f"You cannot use (({q1.safe_qid})) because it does not exist"

        with pytest.raises(InvalidReferenceInExpression) as e:
            _validate_custom_syntax(
                q3,
                expr_context,
                f"Must be less than (({q2.safe_qid})) + (({q1.safe_qid}))",
                ExpressionType.VALIDATION,
                "custom_message",
                False,
            )

        assert e.value.form_error_message == f"You cannot use (({q1.safe_qid})) because it does not exist"

    def test_invalid_expression_incompatible_data_type(self, factories, mocker):
        db_form = factories.form.create()
        q1 = factories.question.create(form=db_form, data_type=QuestionDataType.TEXT_MULTI_LINE)
        q2, q3 = factories.question.create_batch(
            2,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid}))"

        expr_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(IncompatibleDataTypeInCalculationException) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )

        assert (
            e.value.form_error_message
            == f"You cannot reference {q1.name} because only numbers can be referenced in calculations"
        )

        with pytest.raises(IncompatibleDataTypeInCalculationException) as e:
            _validate_custom_syntax(
                q3,
                expr_context,
                f"Must be less than (({q2.safe_qid})) + (({q1.safe_qid}))",
                ExpressionType.VALIDATION,
                "custom_message",
                False,
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

        test_expression = f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid}))"

        expr_context = ExpressionContext()

        side_effect = [q3.safe_qid, q2.safe_qid, None]

        # mock the call the _validate_reference as it will raise an exception due to references not being there
        # but we want to test an error at evaluation time instead
        mocker.patch(
            "app.common.expressions.forms._validate_reference",
            side_effect=side_effect,
        )

        with pytest.raises(UndefinedVariableInExpression) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
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
        test_expression = f"(({q3.safe_qid})) < sum( (({q2.safe_qid})), (({q1.safe_qid})) )"

        # exclude q1 from the context
        expr_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(UndefinedFunctionInExpression) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
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
        test_expression = f"(({q3.safe_qid})) < hello there"

        # exclude q1 from the context
        expr_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(DisallowedExpression) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
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
        test_expression = f"(({q3.safe_qid})) < 2**3"

        # exclude q1 from the context
        expr_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(UndefinedOperatorInExpression) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )

        assert e.value.form_error_message == "You cannot use Pow() in calculations"

    def test_invalid_expression_multiple_references_to_self(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = (
            f"(({q3.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid})) + (({q3.safe_qid})) + "
            f"(({q3.safe_qid})) + (({q3.safe_qid}))"
        )

        expr_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(DisallowedExpression) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
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

        test_expression = f"(({q2.safe_qid})) < (({q2.safe_qid})) + (({q1.safe_qid}))"

        expr_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(DisallowedExpression) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )

        assert e.value.form_error_message == "The expression must include exactly one reference to this question"

    def test_invalid_expression_does_not_evaluate_to_true_or_false(self, factories, mocker):
        db_form = factories.form.create()
        q1, q2, q3 = factories.question.create_batch(
            3,
            form=db_form,
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = f"(({q3.safe_qid})) + (({q2.safe_qid})) + (({q1.safe_qid}))"

        expr_context = ExpressionContext(submission_data={q1.safe_qid: 11, q2.safe_qid: 22, q3.safe_qid: 33})

        with pytest.raises(InvalidEvaluationResult) as e:
            _validate_custom_syntax(
                q3, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )

        assert e.value.form_error_message == "The expression must evaluate to true or false"

    def test_metrics_success(self, factories, mock_sentry_metrics):
        q1 = factories.question.create(
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = f"(({q1.safe_qid})) < 5"

        expr_context = ExpressionContext(
            submission_data={
                q1.safe_qid: 1,
            }
        )

        assert (
            _validate_custom_syntax(
                q1, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
            )
            is None
        )
        assert mock_sentry_metrics.call_count == 0
        assert (
            _validate_custom_syntax(
                q1, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", False
            )
            is None
        )
        assert mock_sentry_metrics.call_count == 0

    def test_metrics_failure(self, factories, mock_sentry_metrics):
        q1 = factories.question.create(
            data_type=QuestionDataType.NUMBER,
            data_options=QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )

        test_expression = f"(({q1.safe_qid})) < syntax error"

        expr_context = ExpressionContext(
            submission_data={
                q1.safe_qid: 1,
            }
        )

        with pytest.raises(DisallowedExpression):
            _validate_custom_syntax(
                q1, expr_context, test_expression, ExpressionType.VALIDATION, "custom_expression", True
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
