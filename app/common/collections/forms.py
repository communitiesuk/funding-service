from typing import Protocol, runtime_checkable

from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovSubmitInput, GovTextArea, GovTextInput
from wtforms.fields.numeric import IntegerField
from wtforms.fields.simple import StringField, SubmitField

from app.common.data.models import Question
from app.common.data.types import QuestionDataType

_accepted_fields = StringField | IntegerField


@runtime_checkable
class QuestionFormProtocol(Protocol):
    question: _accepted_fields
    submit: SubmitField


# FIXME: Ideally this would do an intersection between FlaskForm and QuestionFormProtocol, but type hinting in
#        python doesn't currently support this. As of May 2025, it looks like we might be close to some progress on
#        this in https://github.com/python/typing/issues/213.
def build_question_form(question: Question) -> FlaskForm:
    class DynamicQuestionForm(FlaskForm):
        question: _accepted_fields
        submit = SubmitField("Continue", widget=GovSubmitInput())

    field: _accepted_fields
    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE:
            field = StringField(label=question.text, description=question.hint or "", widget=GovTextInput())
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

    DynamicQuestionForm.question = field

    if not isinstance(DynamicQuestionForm, QuestionFormProtocol):
        raise RuntimeError("DynamicQuestionForm must implement QuestionFormProtocol")

    return DynamicQuestionForm()
