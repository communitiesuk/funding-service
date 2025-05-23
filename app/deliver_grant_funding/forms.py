from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput, GovTextArea, GovTextInput
from wtforms.fields.choices import RadioField
from wtforms.fields.simple import StringField, SubmitField
from wtforms.validators import DataRequired

from app.common.data.types import QuestionDataType


def strip_string_if_not_empty(value: str) -> str | None:
    return value.strip() if value else value


class GrantForm(FlaskForm):
    name = StringField(
        "Grant name",
        validators=[DataRequired("Enter a grant name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class SchemaForm(FlaskForm):
    name = StringField(
        "What is the name of the schema?",
        validators=[DataRequired("Enter a schema name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class SectionForm(FlaskForm):
    title = StringField(
        "What is the name of the section?",
        validators=[DataRequired("Enter a section title")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class FormForm(FlaskForm):
    title = StringField(
        "What is the name of the form?",
        validators=[DataRequired("Enter a form name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class QuestionTypeForm(FlaskForm):
    question_data_type = RadioField(
        "What is the type of the question?",
        choices=[
            (QuestionDataType.TEXT_SINGLE_LINE.name, QuestionDataType.TEXT_SINGLE_LINE.value),
            (QuestionDataType.TEXT_MULTI_LINE.name, QuestionDataType.TEXT_MULTI_LINE.value),
            (QuestionDataType.INTEGER.name, QuestionDataType.INTEGER.value),
        ],
        validators=[DataRequired("Select a question type")],
        widget=GovRadioInput(),
        name="question type",
    )
    submit = SubmitField(widget=GovSubmitInput())


class QuestionForm(FlaskForm):
    text = StringField(
        "What is the question?",
        validators=[DataRequired("Enter the question text")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    hint = StringField(
        "Question hint",
        filters=[strip_string_if_not_empty],
        widget=GovTextArea(),
        description="The question hint will be shown to users when they are answering the question.",
    )
    name = StringField(
        "Question name",
        validators=[DataRequired("Enter the question name")],
        description="The question name will be shown when exporting submissions from your users.",
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())
