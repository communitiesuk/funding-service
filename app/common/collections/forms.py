from collections import defaultdict
from functools import partial
from typing import Any, Callable, Mapping, cast

from flask import current_app
from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import (
    GovCharacterCount,
    GovDateInput,
    GovRadioInput,
    GovSubmitInput,
    GovTextArea,
    GovTextInput,
)
from wtforms import DateField, Field, Form, RadioField
from wtforms.fields.choices import SelectField, SelectMultipleField
from wtforms.fields.numeric import IntegerField
from wtforms.fields.simple import EmailField, StringField, SubmitField
from wtforms.validators import DataRequired, Email, InputRequired, Optional, ValidationError

from app.common.data.models import Expression, Question
from app.common.data.types import QuestionDataType
from app.common.expressions import ExpressionContext, evaluate, interpolate
from app.common.forms.fields import (
    IntegerWithCommasField,
    MHCLGAccessibleAutocomplete,
    MHCLGApproximateDateInput,
    MHCLGCheckboxesInput,
    MHCLGRadioInput,
)
from app.common.forms.validators import FinalOptionExclusive, URLWithoutProtocol, WordRange
from app.metrics import MetricEventName, emit_metric_count

_accepted_fields = (
    EmailField
    | StringField
    | IntegerField
    | IntegerWithCommasField
    | RadioField
    | SelectField
    | SelectMultipleField
    | DateField
)


# FIXME: Ideally this would do an intersection between FlaskForm and QuestionFormProtocol, but type hinting in
#        python doesn't currently support this. As of May 2025, it looks like we might be close to some progress on
#        this in https://github.com/python/typing/issues/213.
# This is a bit of a hack so that we have an externally-accessible type that represents the kind of form returned
# by `build_question_form`. This gives us nicer intellisense/etc. The downside is that this class needs to be kept
# in sync manually with the one inside `build_question_form`.
class DynamicQuestionForm(FlaskForm):
    _evaluation_context: ExpressionContext
    _interpolation_context: ExpressionContext
    _questions: list[Question]

    submit: SubmitField

    def _extract_submission_answers(self) -> dict[str, Any]:
        """
        Extract all of the data from the form and return a dict suitable for using in an ExpressionContext instance.
        This data will override any data from the existing submission to allow for evaluations against the most
        up-to-date data (ie from the submission as a whole, plus the data the user has just submitted as part of this
        form.
        """
        # fixme: when adding multi-field/complex question support, we'll need to think more carefully about
        #        transforming the data here to a format that matches our serialised submission format (which passes
        #        through pydantic models. Otherwise we risk exposing different views of the data to the expressions
        #        system (fully serialised+normalised in the submission context, and more raw in the form context).
        data = {k: v for k, v in self.data.items() if k not in {"csrf_token", "submit"}}
        return data

    def validate(self, extra_validators: Mapping[str, list[Any]] | None = None) -> Any:  # ty: ignore[invalid-method-override]
        """
        Run the form's validation chain. This works in two steps:
        - WTForm's built-in field-level validation (eg for IntegerField, that data has been provided, and that it
          can be coerced to an integer value.
        - Our own validation based on the expression framework. As of 27/06/2025, this supports only "managed"
          validation, but we expect to support fully-custom user-provided validation using expressions as well.
        """
        # Run the native WTForm field validation, which will do things like check data types are correct (eg for
        # IntegerFields.
        super().validate(extra_validators)

        extra_validators = defaultdict(list, extra_validators or {})

        # Inject the latest data from this form submission into the context for validators to use. This will override
        # any existing data for expression contexts from the current state of the submission with the data submitted
        # in this form by the user.
        self._evaluation_context.update_submission_answers(self._extract_submission_answers())

        for q in self._questions:
            # only add custom validators if that question hasn't already failed basic validation
            # (it's may not be well formed data of that type)
            if not self[q.safe_qid].errors:
                extra_validators[q.safe_qid].extend(
                    build_validators(q, self._evaluation_context, self._interpolation_context)
                )

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


def build_validators(
    question: Question, evaluation_context: ExpressionContext, interpolation_context: ExpressionContext
) -> list[Callable[[Form, Field], None]]:
    validators = []

    for _validation in question.validations:

        def run_validation(form: Form, field: Field, validation: Expression) -> None:
            if not validation.managed:
                raise RuntimeError("Support for un-managed validation has not been implemented yet.")

            if not evaluate(expression=validation, context=evaluation_context):
                emit_metric_count(
                    MetricEventName.SUBMISSION_MANAGED_VALIDATION_ERROR, managed_expression=validation.managed
                )
                raise ValidationError(interpolate(validation.managed.message, context=interpolation_context))

            emit_metric_count(
                MetricEventName.SUBMISSION_MANAGED_VALIDATION_SUCCESS, managed_expression=validation.managed
            )

        validators.append(cast(Callable[[Form, Field], None], partial(run_validation, validation=_validation)))

    return validators


def build_question_form(  # noqa: C901
    questions: list[Question], evaluation_context: ExpressionContext, interpolation_context: ExpressionContext
) -> type[DynamicQuestionForm]:
    # NOTE: Keep the fields+types in sync with the class of the same name above.
    class _DynamicQuestionForm(DynamicQuestionForm):  # noqa
        _evaluation_context = evaluation_context
        _interpolation_context = interpolation_context
        _questions = questions

        submit = SubmitField("Continue", widget=GovSubmitInput())

    field: _accepted_fields
    for question in questions:
        match question.data_type:
            case QuestionDataType.EMAIL:
                field = EmailField(
                    label=interpolate(text=question.text, context=interpolation_context),
                    description=interpolate(text=question.hint or "", context=interpolation_context),
                    widget=GovTextInput(),
                    validators=[
                        DataRequired(f"Enter the {question.name}"),
                        Email(message="Enter an email address in the correct format, like name@example.com"),
                    ],
                    filters=[lambda x: x.strip() if x else x],
                )
            case QuestionDataType.TEXT_SINGLE_LINE:
                field = StringField(
                    label=interpolate(text=question.text, context=interpolation_context),
                    description=interpolate(text=question.hint or "", context=interpolation_context),
                    widget=GovTextInput(),
                    validators=[DataRequired(f"Enter the {question.name}")],
                    filters=[lambda x: x.strip() if x else x],
                )
            case QuestionDataType.TEXT_MULTI_LINE:
                field = StringField(
                    label=interpolate(text=question.text, context=interpolation_context),
                    description=interpolate(text=question.hint or "", context=interpolation_context),
                    widget=GovCharacterCount() if question.presentation_options.word_limit else GovTextArea(),
                    validators=[DataRequired(f"Enter the {question.name}")]
                    + (
                        [
                            WordRange(
                                max_words=question.presentation_options.word_limit, field_display_name=question.name
                            )
                        ]
                        if question.presentation_options.word_limit
                        else []
                    ),
                    filters=[lambda x: x.strip() if x else x],
                )
            case QuestionDataType.INTEGER:
                field = IntegerWithCommasField(
                    label=interpolate(text=question.text, context=interpolation_context),
                    description=interpolate(text=question.hint or "", context=interpolation_context),
                    widget=GovTextInput(),
                    validators=[InputRequired(f"Enter the {question.name}")],
                )
            case QuestionDataType.YES_NO:
                field = RadioField(
                    label=interpolate(text=question.text, context=interpolation_context),
                    description=interpolate(text=question.hint or "", context=interpolation_context),
                    widget=GovRadioInput(),
                    choices=[(1, "Yes"), (0, "No")],
                    validators=[InputRequired("Select yes or no")],
                    coerce=lambda val: bool(int(val)),
                )
            case QuestionDataType.RADIOS:
                if len(question.data_source.items) > current_app.config["ENHANCE_RADIOS_TO_AUTOCOMPLETE_AFTER_X_ITEMS"]:
                    fallback_option = (
                        question.data_source.items[-1].label if question.separate_option_if_no_items_match else None
                    )
                    field = SelectField(
                        label=interpolate(text=question.text, context=interpolation_context),
                        description=interpolate(text=question.hint or "", context=interpolation_context),
                        widget=MHCLGAccessibleAutocomplete(fallback_option=fallback_option),
                        choices=[("", "")] + [(item.key, item.label) for item in question.data_source.items],
                        validators=[DataRequired("Select an option")],
                    )
                else:
                    choices = [(item.key, item.label) for item in question.data_source.items]
                    field = RadioField(
                        label=interpolate(text=question.text, context=interpolation_context),
                        description=interpolate(text=question.hint or "", context=interpolation_context),
                        widget=MHCLGRadioInput(
                            insert_divider_before_last_item=bool(question.separate_option_if_no_items_match)
                        ),
                        choices=choices,
                    )
            case QuestionDataType.URL:
                field = StringField(
                    label=interpolate(text=question.text, context=interpolation_context),
                    description=interpolate(text=question.hint or "", context=interpolation_context),
                    widget=GovTextInput(),
                    validators=[
                        DataRequired(f"Enter the {question.name}"),
                        URLWithoutProtocol(
                            message="Enter a website address in the correct format, like www.gov.uk",
                            require_tld=True,
                        ),
                    ],
                    filters=[lambda x: x.strip() if x else x],
                )
            case QuestionDataType.CHECKBOXES:
                choices = [(item.key, item.label) for item in question.data_source.items]
                validators: list[Callable[[Any, Any], None]] = [DataRequired(f"Select {question.name}")]
                if question.separate_option_if_no_items_match:
                    # This is a fallback validator in case JS is disabled, to prevent the user selecting both the
                    # separated final checkbox option and another checkbox
                    validators.append(FinalOptionExclusive(question_name=question.name))

                field = SelectMultipleField(
                    label=interpolate(text=question.text, context=interpolation_context),
                    description=interpolate(text=question.hint or "", context=interpolation_context),
                    widget=MHCLGCheckboxesInput(
                        insert_divider_before_last_item=bool(question.separate_option_if_no_items_match)
                    ),
                    choices=choices,
                    validators=validators,
                )

            case QuestionDataType.DATE:
                field = DateField(
                    label=interpolate(text=question.text, context=interpolation_context),
                    description=interpolate(text=question.hint or "", context=interpolation_context),
                    widget=GovDateInput() if not question.approximate_date else MHCLGApproximateDateInput(),
                    validators=[DataRequired(f"Enter the {question.name}")],
                    format=["%d %m %Y", "%d %b %Y", "%d %B %Y"]
                    if not question.approximate_date
                    else ["%m %Y", "%b %Y", "%B %Y"],  # multiple formats to help user input
                )

            case _:
                raise Exception("Unable to generate dynamic form for question type {_}")

        _DynamicQuestionForm.attach_field(question, field)

    return _DynamicQuestionForm


class CheckYourAnswersForm(FlaskForm):
    section_completed = RadioField(
        "Have you completed this section?",
        choices=[("yes", "Yes, I’ve completed this section"), ("no", "No, I’ll come back to it later")],
        widget=GovRadioInput(),
    )
    submit = SubmitField("Save and continue", widget=GovSubmitInput())

    def __init__(self, *args: Any, all_questions_answered: bool, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)

        # the form should be validly optional unless all questions in the section have been answered
        if all_questions_answered:
            self.section_completed.validators = [DataRequired("Select if you have completed this section")]
        else:
            self.section_completed.validators = [Optional()]


class AddAnotherSummaryForm(FlaskForm):
    def __init__(self, *args: Any, add_another_required: bool = False, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if add_another_required:
            self.add_another.validators = [DataRequired("Select yes if you need to add another answer")]

    add_another = RadioField(
        "Do you need to add another answer?",
        choices=[("yes", "Yes"), ("no", "No")],
        widget=GovRadioInput(),
        validators=[Optional()],
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())


class ConfirmRemoveAddAnotherForm(FlaskForm):
    confirm_remove = RadioField(
        "Are you sure you want to remove this answer?",
        choices=[("yes", "Yes"), ("no", "No")],
        widget=GovRadioInput(),
        validators=[DataRequired("Select yes if you want to remove this answer")],
    )
    submit = SubmitField("Save and continue", widget=GovSubmitInput())
