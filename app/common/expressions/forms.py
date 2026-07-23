from typing import TYPE_CHECKING, Any, Protocol, cast

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput, GovTextArea, GovTextInput
from markupsafe import Markup
from wtforms import RadioField, StringField, SubmitField
from wtforms.validators import DataRequired

from app.common.data.interfaces.collections import (
    IncompatibleDataTypeException,
    IncompatibleDataTypeInCalculationException,
    _validate_reference,
)
from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType
from app.common.exceptions import WTFormRenderableException
from app.common.expressions import (
    DisallowedExpression,
    ExpressionContext,
    InvalidEvaluationResult,
    get_restricted_evaluator,
    run_evaluation,
)
from app.common.expressions.references import (
    EvaluationStatement,
    ExpressionReference,
    ExpressionStatement,
    InterpolationStatement,
)
from app.common.expressions.registry import (
    get_managed_conditions_by_data_type,
    get_managed_validators_by_data_type,
    lookup_managed_expression,
)
from app.common.forms.fields import EvaluationStatementField, InterpolationStatementField
from app.metrics import MetricAttributeName, MetricEventName, emit_metric_count

if TYPE_CHECKING:
    from app.common.data.models import Component, Expression, Group, Question
    from app.common.expressions.managed import ManagedExpression


class _ManagedExpressionForm(FlaskForm):
    _managed_expressions: list[type[ManagedExpression]]
    _subject_reference: ExpressionReference
    type: RadioField

    def get_managed_expression_radio_conditional_items(self) -> list[dict[str, dict[str, Markup]]]:
        items = []
        for _managed_expression in self._managed_expressions:
            # format the radio items for `govuk-frontend-wtf` macro syntax
            items.append(
                {
                    "conditional": {
                        "html": _managed_expression.concatenate_all_wtf_fields_html(
                            self, subject_reference=self._subject_reference
                        )
                    }
                }
            )
        return items

    def is_submitted_to_add_context(self) -> bool:
        """Check if user clicked any managed expression Reference Data button"""
        add_context_field = self._fields.get("add_context")
        return bool(
            self.is_submitted()
            and add_context_field is not None
            and hasattr(add_context_field, "data")
            and add_context_field.data
        )

    def is_submitted_to_remove_context(self) -> bool:
        """Check if user clicked any managed expression Remove Data button"""
        remove_context_field = self._fields.get("remove_context")
        return bool(
            self.is_submitted()
            and remove_context_field is not None
            and hasattr(remove_context_field, "data")
            and remove_context_field.data
        )

    def get_expression_form_data(self) -> dict[str, Any]:
        if not self.type.data:
            return {}
        expression = lookup_managed_expression(ManagedExpressionsEnum(self.type.data))
        expression_keys = expression.get_form_fields(self._subject_reference).keys()
        data = {k: v for k, v in self.data.items() if k in expression_keys}
        return data

    def validate(self, extra_validators=None):
        if self.is_submitted_to_add_context():
            return True

        for _managed_expression in self._managed_expressions:
            if _managed_expression.name == self.type.data:
                _managed_expression.update_validators(self)

        return super().validate(extra_validators=extra_validators)

    def get_expression(self, subject_reference: ExpressionReference) -> ManagedExpression:
        for _managed_expression in self._managed_expressions:
            if _managed_expression.name == self.type.data:
                return _managed_expression.build_from_form(self, subject_reference)

        raise RuntimeError(f"Unknown expression type: {self.type.data}")


def build_managed_expression_form(
    type_: ExpressionType,
    subject_reference: ExpressionReference,
    expression: Expression | None = None,
) -> type[_ManagedExpressionForm] | None:
    """
    For a given subject reference, generate a FlaskForm that will allow a user to select one of the managed
    expressions applicable to its data type.

    The subject reference may point at a question (``q_<hex>``) or a data source column
    (``d_<hex>.c_<col>``). The set of managed expressions offered is determined by the subject's resolved
    ``QuestionDataType``. Subclasses that need attributes only questions have (e.g. ``.data_source.items``
    on RADIOS questions, ``.approximate_date`` on DATE questions) resolve the reference to a Question
    internally — they're only ever reached when the data type filter means the subject is a question
    (data source columns only support TEXT_SINGLE_LINE / NUMBER).
    """
    match type_:
        case ExpressionType.CONDITION:
            type_validation_message = "Select what the value should be to show this question"
            managed_expressions = get_managed_conditions_by_data_type(subject_reference.data_type)
        case ExpressionType.VALIDATION:
            type_validation_message = "Select the kind of validation to apply"
            managed_expressions = get_managed_validators_by_data_type(subject_reference.data_type)
        case _:
            raise RuntimeError("unknown expression type")

    if not managed_expressions:
        return None

    class ManagedExpressionForm(_ManagedExpressionForm):
        _subject_reference = subject_reference
        _managed_expressions = managed_expressions
        _expression_type = type_
        _show_calculated_validation_option: bool = False

        type = RadioField(
            choices=[],
            default=expression.managed_name if expression else None,
            validators=[DataRequired(type_validation_message)],
            widget=GovRadioInput(),
        )
        submit = SubmitField("Add validation", widget=GovSubmitInput())

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self._show_calculated_validation_option = (
                self._subject_reference.data_type == QuestionDataType.NUMBER
                and self._expression_type == ExpressionType.VALIDATION
            )
            self.type.choices = [
                (managed_expression.name, managed_expression.name) for managed_expression in self._managed_expressions
            ]
            if self._show_calculated_validation_option:
                # This creates a placeholder which is then replaced by the 'or' divider at render time below
                self.type.choices.append((None, None))  # ty: ignore[invalid-argument-type]
                self.type.choices.append(("CUSTOM", "Calculation with two or more numbers"))  # ty: ignore[invalid-argument-type]

        def get_managed_expression_radio_items(self) -> list[dict[str, dict[str, Markup]]]:
            items = super().get_managed_expression_radio_conditional_items()
            if self._show_calculated_validation_option:
                items.append({"divider": "or"})  # ty:ignore[invalid-argument-type]
                items.append({"hint": {"text": "Adding, subtracting, multiplying and dividing"}})  # ty:ignore[invalid-argument-type]
            return items

    for managed_expression in managed_expressions:
        pass_expression = expression and expression.managed_name == managed_expression.name
        for field_name, field in managed_expression.get_form_fields(
            expression=expression if pass_expression else None, subject_reference=subject_reference
        ).items():
            setattr(ManagedExpressionForm, field_name, field)

    return ManagedExpressionForm


class HasFormErrors(Protocol):
    form_errors: list[str]


class ExceptionRenderingFormMixin:
    def handle_exception(self: HasFormErrors, e: WTFormRenderableException, field_name: str | None = None) -> None:
        if e.field_name:
            field_with_error = getattr(self, e.field_name)
        elif field_name:
            field_with_error = getattr(self, field_name)
        else:
            self.form_errors.append(e.form_error_message)
            return
        field_with_error.errors.append(e.form_error_message)


def _fake_submission_data(component: Component, validated_references: list[ExpressionReference]) -> dict[str, int]:
    if not component:
        raise ValueError("component must be provided")

    fake_submission_data = {}
    for ref in validated_references:
        # assume these are numbers as we can't do custom expressions unless using non number data
        # types but we could check this
        fake_submission_data[ref] = 1

    return fake_submission_data


def _fake_data_source_data(component: Component) -> dict[str, dict[str, str | int]]:
    fake_data_sources_data = {}
    data_sources = component.form.collection.data_sources
    for data_source in data_sources:
        if not data_source.schema:
            # CUSTOM data sources - not
            raise NotImplementedError(
                "What does it even mean to reference a custom data source in custom validation or expressions?"
            )

        if not data_source.schema.root:
            raise ValueError("Non-CUSTOM data source must have a schema")

        fake_data_sources_data[data_source.safe_did] = {}
        for column_name, colum_schema in data_source.schema.ordered_items():
            match colum_schema.data_type:
                case QuestionDataType.TEXT_SINGLE_LINE:
                    fake_data_sources_data[data_source.safe_did][column_name] = "foo"

                case QuestionDataType.NUMBER:
                    fake_data_sources_data[data_source.safe_did][column_name] = 1

                case _:
                    raise NotImplementedError("need to handle faking data set data for new data types")

    return fake_data_sources_data


# TODO break this down so it's less complicated
def _validate_custom_syntax(  # noqa:C901
    component: Component,
    interpolation_context: ExpressionContext,
    statement: ExpressionStatement,
    expression_type: ExpressionType,
    field_name: str,
    evaluation_context: ExpressionContext | None = None,
) -> None:
    validated_references = []

    try:
        for ref in statement.references:
            validated_ref = _validate_reference(
                reference=ref,
                attached_to_component=component,
                expression_context=interpolation_context,
                expression_type=expression_type,
                field_name_for_error_message=field_name,
                question_to_test=None,
            )
            validated_references.append(validated_ref)

        if not isinstance(statement, EvaluationStatement):
            # No further validation needed for custom error message
            return

        statement.validate_syntax()

        if evaluation_context is None:
            raise ValueError("evaluation_context must be provided for EvaluationStatements")

        if expression_type == ExpressionType.VALIDATION:
            if component.is_question:
                references_to_self_count = statement.count_references(
                    ExpressionReference.from_question(cast("Question", component))
                )
                if references_to_self_count != 1:
                    raise DisallowedExpression(
                        message=(
                            f"Expression contains {references_to_self_count} references to question {component.id}, "
                            "should contain exactly 1"
                        ),
                        form_error_message="The expression must include exactly one reference to this question",
                    )
            else:
                component = cast("Group", component)
                if not any(q.safe_qid in validated_references for q in component.cached_questions):
                    raise DisallowedExpression(
                        message=(
                            f"Expression contains no references to questions in group {component.id}, "
                            "should contain at least 1"
                        ),
                        form_error_message=(
                            "The calculation must include at least one reference to a question in this group"
                        ),
                    )

        # Workaround: start - FSPT-1257
        # When ExpressionContexts populate data source data, they need the context of a submission to know
        # which grant recipient's data to pull in (for grant-recipient data sets). We don't have that grant
        # recipient context here, so evaluation ExpressionContexts don't pull in any data set data currently.
        # This feels like a significant hack/workaround that we should really tidy up.
        fake_submission_data = _fake_submission_data(component, validated_references)
        fake_data_sources_data = _fake_data_source_data(component)

        faked_data_expression_context = ExpressionContext(
            submission_data=fake_submission_data,
            expression_context=evaluation_context._expression_context,
            add_another_context=evaluation_context._add_another_context,
            data_source_context=fake_data_sources_data,
            question_form_context=evaluation_context._question_form_context,
        )
        # Workaround: end

        evaluator = get_restricted_evaluator(names=faked_data_expression_context, required_functions={})

        result = run_evaluation(evaluator, statement)
        if not isinstance(result, bool):
            raise InvalidEvaluationResult(statement, result, bool)

    except WTFormRenderableException as e:
        emit_metric_count(
            MetricEventName.CALCULATION_FIELD_INVALID,
            1,
            custom_attributes={
                MetricAttributeName.CALCULATION_INVALID_FIELD: field_name,
                MetricAttributeName.CALCULATION_INVALID_REASON: e.__class__.__name__,
            },
        )
        if isinstance(e, IncompatibleDataTypeException):
            raise IncompatibleDataTypeInCalculationException(e) from e
        raise


class CustomValidationExpressionForm(ExceptionRenderingFormMixin, FlaskForm):
    def is_submitted_to_add_context(self) -> bool:
        return bool(self.is_submitted() and self.add_context.data and not self.submit.data)

    custom_expression = EvaluationStatementField(
        "Calculation",
        widget=GovTextArea(),
        validators=[DataRequired()],
    )
    custom_message = InterpolationStatementField(
        "Error message",
        widget=GovTextArea(),
        validators=[DataRequired()],
    )
    add_context = StringField(
        "Reference data",
        widget=GovSubmitInput(),
    )
    submit = SubmitField("Add validation", widget=GovSubmitInput())

    def __init__(
        self,
        *args,
        component: "Component",
        interpolation_context: ExpressionContext,
        evaluation_context: ExpressionContext,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.component = component
        self.interpolation_context = interpolation_context
        self.evaluation_context = evaluation_context

    def get_expression_form_data(self) -> dict[str, Any]:
        data = {
            "custom_expression": self.custom_expression.data,
            "custom_message": self.custom_message.data,
            "add_context": self.add_context.data,
        }
        return data

    def validate(self, extra_validators=None) -> bool:

        if not super().validate(extra_validators):
            return False

        try:
            _validate_custom_syntax(
                self.component,
                self.interpolation_context,
                EvaluationStatement(self.custom_expression.data or ""),
                ExpressionType.VALIDATION,
                "custom_expression",
                evaluation_context=self.evaluation_context,
            )
        except WTFormRenderableException as e:
            self.handle_exception(e, field_name="custom_expression")
            return False
        try:
            _validate_custom_syntax(
                self.component,
                self.interpolation_context,
                InterpolationStatement(self.custom_message.data or ""),
                ExpressionType.VALIDATION,
                "custom_message",
            )
        except WTFormRenderableException as e:
            self.handle_exception(e, field_name="custom_message")
            return False

        return True


class CalculatedConditionForm(ExceptionRenderingFormMixin, FlaskForm):
    def is_submitted_to_add_context(self) -> bool:
        return bool(self.is_submitted() and self.add_context.data and not self.submit.data)

    expression_name = StringField("Condition name", widget=GovTextInput(), validators=[DataRequired()])

    custom_expression = EvaluationStatementField(
        "Calculation",
        widget=GovTextArea(),
        validators=[DataRequired()],
    )
    add_context = StringField(
        "Reference data",
        widget=GovSubmitInput(),
    )
    submit = SubmitField("Add calculated condition", widget=GovSubmitInput())

    def __init__(
        self,
        *args,
        component: Component,
        interpolation_context: ExpressionContext,
        evaluation_context: ExpressionContext,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.component = component
        self.interpolation_context = interpolation_context
        self.evaluation_context = evaluation_context

    def get_expression_form_data(self) -> dict[str, Any]:
        data = {
            "expression_name": self.expression_name.data,
            "custom_expression": self.custom_expression.data,
            "add_context": self.add_context.data,
        }
        return data

    def validate(self, extra_validators=None) -> bool:

        if not super().validate(extra_validators):
            return False

        try:
            _validate_custom_syntax(
                self.component,
                self.interpolation_context,
                EvaluationStatement(self.custom_expression.data or ""),
                ExpressionType.CONDITION,
                "custom_expression",
                evaluation_context=self.evaluation_context,
            )
        except WTFormRenderableException as e:
            self.handle_exception(e)
            return False

        return True
