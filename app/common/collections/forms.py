from functools import partial
from typing import Any, cast

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextArea, GovTextInput
from immutabledict import immutabledict
from pydantic.v1.class_validators import Validator
from wtforms import Field
from wtforms.fields.numeric import IntegerField
from wtforms.fields.simple import StringField, SubmitField
from wtforms.validators import ValidationError

from app.common.data.models import Expression, Question
from app.common.data.types import QuestionDataType
from app.common.expressions import ExpressionContext, evaluate, mangle_question_id_for_context

_accepted_fields = StringField | IntegerField


# FIXME: Ideally this would do an intersection between FlaskForm and QuestionFormProtocol, but type hinting in
#        python doesn't currently support this. As of May 2025, it looks like we might be close to some progress on
#        this in https://github.com/python/typing/issues/213.
# This is a bit of a hack so that we have an externally-accessible type that represents the kind of form returned
# by `build_question_form`. This gives us nicer intellisense/etc. The downside is that this class needs to be kept
# in sync manually with the one inside `build_question_form`.
class DynamicQuestionForm(FlaskForm):
    submit: SubmitField

    @classmethod
    def attach_field(cls, question: Question, field: Field):
        setattr(cls, mangle_question_id_for_context(question.id), cast(_accepted_fields, field))

    def render_question(self, question: Question, *args, **kwargs) -> str:
        return getattr(self, mangle_question_id_for_context(question.id))(*args, **kwargs)

    def get_question_field(self, question: Question) -> Field:
        return getattr(self, mangle_question_id_for_context(question.id))

    def get_answer_to_question(self, question: Question) -> Any:
        return getattr(self, mangle_question_id_for_context(question.id)).data


def build_validators(question: Question, context: ExpressionContext) -> list[Validator]:
    validators = []

    for validation in question.validations:
        # todo: support non-managed validation
        if not validation.managed:
            raise RuntimeError("Support for custom validation not yet implemented.")

        def run_validation(form, field, _validation: Expression):
            if not evaluate(_validation, context):
                raise ValidationError(_validation.managed.message)

        validators.append(partial(run_validation, _validation=validation))

    return validators


def build_question_form(question: Question, context: ExpressionContext) -> type[DynamicQuestionForm]:
    # NOTE: Keep the fields+types in sync with the class of the same name above.
    class _DynamicQuestionForm(DynamicQuestionForm):  # noqa
        submit = SubmitField("Continue", widget=GovSubmitInput())

        def validate(self, extra_validators=None):
            cleaned_data = self.data.copy()
            cleaned_data.pop("csrf_token")
            cleaned_data.pop("submit")

            # note: this is a bit magical and might be tricky to follow - this directly updates the `ExpressionContext`.
            #       All of the validators have a reference to this same expression context instance, so when they run
            #       as part of this validate call, this provides them the form data that contains the latest
            #       answers submitted by the user. These will override any historical answers provided by the user which
            #       are available from the submission as a whole.
            #       There's definitely a slightly invisible thread here that maybe could be solved by doing a different
            #       implementation, but I haven't quite cracked that nut in my head yet and so this is the best I've
            #       got. It's hard because we need to pull together all of the context for the expressions, which
            #       feels like it needs to happen at a high level (the endpoint, where we have the submission/helper,
            #       which has access to all of the info) but then pass that down into the very low level areas where
            #       expressions actually get evaluated. And there's a lot of internals in between there.
            context.form_context = immutabledict(cleaned_data)

            return super().validate(extra_validators)

    validators = build_validators(question, context)

    field: _accepted_fields
    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE:
            field = StringField(
                label=question.text,
                validators=validators,
                description=question.hint or "",
                widget=GovTextInput(),
            )
        case QuestionDataType.TEXT_MULTI_LINE:
            field = StringField(
                label=question.text,
                validators=validators,
                description=question.hint or "",
                widget=GovTextArea(),
            )
        case QuestionDataType.INTEGER:
            field = IntegerField(
                label=question.text,
                validators=validators,
                description=question.hint or "",
                widget=GovTextInput(),
            )
        case _:
            raise Exception("Unable to generate dynamic form for question type {_}")

    _DynamicQuestionForm.attach_field(question, field)

    return _DynamicQuestionForm
