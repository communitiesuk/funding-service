from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovSubmitInput, GovTextArea, GovTextInput
from wtforms.fields.choices import RadioField
from wtforms.fields.simple import StringField, SubmitField
from wtforms.validators import DataRequired

from app.common.data.models import QuestionDataType


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


class CollectionForm(FlaskForm):
    name = StringField(
        "What is the name of the collection?",
        validators=[DataRequired("Enter a collection name")],
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
    data_type = RadioField(
        "Question type",
        choices=[
            (QuestionDataType.TEXT.name, QuestionDataType.TEXT.value),
        ],
        validators=[DataRequired("Select a question type")],
        widget=GovRadioInput(),
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
