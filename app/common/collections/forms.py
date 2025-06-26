from typing import Any, cast

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextArea, GovTextInput
from immutabledict import immutabledict
from pydantic.v1.class_validators import Validator
from wtforms import Field
from wtforms.fields.numeric import IntegerField
from wtforms.fields.simple import StringField, SubmitField

from app.common.data.models import Question
from app.common.data.types import QuestionDataType
from app.common.expressions import ExpressionContext, evaluate, mangle_question_id_for_context
from app.common.helpers.collections import _form_data_to_question_type

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


def build_integrity_validators(question: Question) -> list[Validator]:
    validators = []

    # todo: some question types will likely have validators that are not additional expressions
    #       for example if we have a URL question type it should make sure the URL is well formed
    #       these would likely be added before going through the validation expressions

    # 1. optional or mandatory validator
    # 2. data type validators
    # -> integrity passed
    return validators


def build_question_form(question: Question, context: ExpressionContext) -> type[DynamicQuestionForm]:
    # NOTE: Keep the fields+types in sync with the class of the same name above.
    class _DynamicQuestionForm(DynamicQuestionForm):  # noqa
        submit = SubmitField("Continue", widget=GovSubmitInput())

        # note: one little thought while doing this is we probably want to be able to run validations across all
        #       questions before submission so we'll want checking a questions valid to be able to be run independently
        #       of the form too
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

            # the form context should be calculated after the integrity checks so we can be confident we can serialise the
            # question type fully
            if not super().validate(extra_validators):
                return False

            # todo: each question type probably wants to tell us what shape it should take, for all of our "primitive" types this
            #       will be OK
            serialised = _form_data_to_question_type(question, self)
            context.form_context = immutabledict({[mangle_question_id_for_context(question.id)]: serialised.root})

            # todo: if there can more questions this is another thing to loop over
            for validation in question.validations:
                if not evaluate(validation, context):
                    # todo: question types that involve more than one field will want to have a say here
                    self.errors[mangle_question_id_for_context(question.id)] = [validation.managed.message]
                    return False

            return True

    # todo: when we're accepting multiple questions for a single form this will need validators for all of them
    #       and they'll need to be appropriately assigned based on the question id
    validators = build_integrity_validators(question)

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
