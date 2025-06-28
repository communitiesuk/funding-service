from collections import defaultdict
from functools import partial
from typing import Any, Callable, Mapping, cast

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextArea, GovTextInput
from immutabledict import immutabledict
from wtforms import Field, Form
from wtforms.fields.numeric import IntegerField
from wtforms.fields.simple import StringField, SubmitField
from wtforms.validators import ValidationError

from app.common.data.models import Expression, Question
from app.common.data.types import QuestionDataType, immutable_json_flat_scalars
from app.common.expressions import ExpressionContext, evaluate

_accepted_fields = StringField | IntegerField


# FIXME: Ideally this would do an intersection between FlaskForm and QuestionFormProtocol, but type hinting in
#        python doesn't currently support this. As of May 2025, it looks like we might be close to some progress on
#        this in https://github.com/python/typing/issues/213.
# This is a bit of a hack so that we have an externally-accessible type that represents the kind of form returned
# by `build_question_form`. This gives us nicer intellisense/etc. The downside is that this class needs to be kept
# in sync manually with the one inside `build_question_form`.
class DynamicQuestionForm(FlaskForm):
    _expression_context: ExpressionContext
    _questions: list[Question]
    submit: SubmitField

    def _build_form_context(self) -> immutable_json_flat_scalars:
        """
        Extract all of the data from the form and return an immutabledict suitable for setting on an expression
        context (ExpressionContext.form_context). This data will override any data from the existing submission
        to allow for evaluations against the most up-to-date data (ie from the submission as a whole, plus the data
        the user has just submitted as part of this form.
        """
        # fixme: when adding multi-field/complex question support, we'll need to think more carefully about
        #        transforming the data here to a format that matches our serialised submission format (which passes
        #        through pydantic models. Otherwise we risk exposing different views of the data to the expressions
        #        system (fully serialised+normalised in the submission context, and more raw in the form context).
        data = {k: v for k, v in self.data.items() if k not in {"csrf_token", "submit"}}
        return immutabledict(data)

    def validate(self, extra_validators: Mapping[str, list[Any]] | None = None) -> Any:
        """
        Run the form's validation chain. This works in two steps:
        - WTForm's built-in field-level validation (eg for IntegerField, that data has been provided, and that it
          can be coerced to an integer value.
        - Our own validation based on the expression framework. As of 27/06/2025, this supports only "managed"
          validation, but we expect to support fully-custom user-provided validation using expressions as well.
        """
        # Run the native WTForm field validation, which will do things like check data types are correct (eg for
        # IntegerFields.
        valid = super().validate(extra_validators)
        if not valid:
            # If initial validation fails, don't run any of our custom validation chains.
            return valid

        extra_validators = defaultdict(list, extra_validators or {})

        # Inject the latest data from this form submission into the context for validators to use.
        self._expression_context.form_context = self._build_form_context()
        for q in self._questions:
            extra_validators[q.safe_qid].extend(build_validators(q, self._expression_context))

        # Do a second validation pass that includes all of our managed/custom validation. This has a small bit of
        # redundancy because it will run the data validation checks again, but it means that all of our own
        # validators can rely on the data being, at the least, the right shape.
        return super().validate(extra_validators)

    @classmethod
    def attach_field(cls, question: Question, field: Field) -> None:
        setattr(cls, question.safe_qid, cast(_accepted_fields, field))

    def render_question(self, question: Question, params: dict[str, Any] | None = None) -> str:
        return cast(str, getattr(self, question.safe_qid)(params=params))

    def get_question_field(self, question: Question) -> Field:
        return cast(Field, getattr(self, question.safe_qid))

    def get_answer_to_question(self, question: Question) -> Any:
        return getattr(self, question.safe_qid).data


def build_validators(question: Question, expression_context: ExpressionContext) -> list[Callable[[Form, Field], None]]:
    validators = []

    for _validation in question.validations:

        def run_validation(form: Form, field: Field, validation: Expression) -> None:
            if not validation.managed:
                raise RuntimeError("Support for un-managed validation has not been implemented yet.")

            if not evaluate(expression=validation, context=expression_context):
                raise ValidationError(validation.managed.message)

        validators.append(cast(Callable[[Form, Field], None], partial(run_validation, validation=_validation)))

    return validators


def build_question_form(question: Question, expression_context: ExpressionContext) -> type[DynamicQuestionForm]:
    # NOTE: Keep the fields+types in sync with the class of the same name above.
    class _DynamicQuestionForm(DynamicQuestionForm):  # noqa
        _expression_context = expression_context
        _questions = [question]

        submit = SubmitField("Continue", widget=GovSubmitInput())

    field: _accepted_fields
    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE:
            field = StringField(
                label=question.text,
                description=question.hint or "",
                widget=GovTextInput(),
            )
        case QuestionDataType.TEXT_MULTI_LINE:
            field = StringField(
                label=question.text,
                description=question.hint or "",
                widget=GovTextArea(),
            )
        case QuestionDataType.INTEGER:
            field = IntegerField(
                label=question.text,
                description=question.hint or "",
                widget=GovTextInput(),
            )
        case _:
            raise Exception("Unable to generate dynamic form for question type {_}")

    _DynamicQuestionForm.attach_field(question, field)

    return _DynamicQuestionForm
