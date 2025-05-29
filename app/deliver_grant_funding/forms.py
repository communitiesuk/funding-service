from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import (
    GovCharacterCount,
    GovRadioInput,
    GovSubmitInput,
    GovTextArea,
    GovTextInput,
)
from wtforms.fields.choices import RadioField
from wtforms.fields.simple import StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional, ValidationError

from app.common.data.interfaces.grants import grant_name_exists
from app.common.data.types import QuestionDataType
from app.common.forms.validators import MaxWords


def strip_string_if_not_empty(value: str) -> str | None:
    return value.strip() if value else value


class UniqueGrantName:
    """Validator to ensure grant name is unique."""

    def __init__(self, message: str | None = None):
        self.message = message or "Grant name already in use"

    def __call__(self, form: FlaskForm, field: StringField) -> None:
        if field.data and grant_name_exists(field.data):
            raise ValidationError(self.message)


class GrantForm(FlaskForm):
    name = StringField(
        "Grant name",
        validators=[DataRequired("Enter a grant name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class GrantSetupIntroForm(FlaskForm):
    submit = SubmitField("Continue", widget=GovSubmitInput())


class GrantGGISForm(FlaskForm):
    has_ggis = RadioField(
        "Do you have a Government Grants Information System (GGIS) reference number?",
        choices=[("yes", "Yes"), ("no", "No")],
        validators=[DataRequired("Select yes if you have a GGIS reference number")],
        widget=GovRadioInput(),
        default="no",
    )
    ggis_number = StringField(
        "Enter your GGIS reference number",
        validators=[Optional()],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField("Save and continue", widget=GovSubmitInput())


class GrantNameSetupForm(FlaskForm):
    name = StringField(
        "What is the name of this grant?",
        validators=[
            DataRequired("Enter the grant name"),
            UniqueGrantName(),
        ],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField("Save and continue", widget=GovSubmitInput())


class GrantDescriptionForm(FlaskForm):
    description = TextAreaField(
        "What is the main purpose of this grant?",
        validators=[
            DataRequired("Enter the main purpose of this grant"),
            MaxWords(200, "Description must be 200 words or fewer"),
        ],
        filters=[strip_string_if_not_empty],
        widget=GovCharacterCount(),
    )
    submit = SubmitField("Save and continue", widget=GovSubmitInput())


class GrantContactForm(FlaskForm):
    primary_contact_name = StringField(
        "Full name",
        validators=[DataRequired("Enter the full name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    primary_contact_email = StringField(
        "Email address",
        validators=[
            DataRequired("Enter the email address"),
            Email(message="Enter an email address in the correct format, like name@example.com"),
        ],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField("Add grant", widget=GovSubmitInput())


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
