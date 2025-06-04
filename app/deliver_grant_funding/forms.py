from typing import Any

from flask import current_app
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
from wtforms.validators import DataRequired, Email, ValidationError

from app.common.data.interfaces.grants import grant_name_exists
from app.common.data.types import QuestionDataType
from app.common.forms.validators import WordRange


def strip_string_if_not_empty(value: str) -> str | None:
    return value.strip() if value else value


def validate_communities_gov_uk_email(_form: FlaskForm, field: StringField) -> None:
    if field.data and "@" in field.data:
        internal_domains = current_app.config["INTERNAL_DOMAINS"]
        if not field.data.endswith(internal_domains):
            raise ValidationError(f"Email address must end with {' or '.join(internal_domains)}")


class UniqueGrantName:
    """Validator to ensure grant name is unique."""

    def __init__(self, message: str | None = None):
        self.message = message or "Grant name already in use"

    def __call__(self, form: FlaskForm, field: StringField) -> None:
        if field.data and grant_name_exists(field.data):
            raise ValidationError(self.message)


class GrantForm(FlaskForm):
    name = StringField(
        "Change grant name",
        validators=[DataRequired("Enter a grant name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField("Save", widget=GovSubmitInput())


class GrantSetupIntroForm(FlaskForm):
    submit = SubmitField("Continue", widget=GovSubmitInput())


class GrantGGISForm(FlaskForm):
    has_ggis = RadioField(
        "Do you have a Government Grants Information System (GGIS) reference number?",
        description="You'll need to provide your GGIS number before you can create forms or assess grant applications.",
        # These choices have no effect on the frontend, but are used for validation. Frontend choices are found in the
        # template, currently at app/deliver_grant_funding/templates/deliver_grant_funding/grant_setup/ggis_number.html.
        # Developers will need to keep these in sync manually.
        choices=[("yes", "Yes"), ("no", "No")],
        validators=[DataRequired("Please select an option")],
        widget=GovRadioInput(),
    )
    ggis_number = StringField(
        "Enter your GGIS reference number",
        description="For example, G2-SCH-2025-05-12346.",
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField("Save and continue", widget=GovSubmitInput())

    def validate(self, extra_validators: dict[str, list[Any]] | None = None) -> bool:
        if not super().validate(extra_validators):
            return False

        if self.has_ggis.data == "yes" and not self.ggis_number.data:
            self.ggis_number.errors = list(self.ggis_number.errors) + ["Enter your GGIS reference number"]
            return False

        return True


class GrantNameForm(FlaskForm):
    name = StringField(
        "What is the name of this grant?",
        description="This should be the full and official name of the grant. Do not include abbreviations or acronyms.",
        validators=[
            DataRequired("Enter the grant name"),
            UniqueGrantName(),
        ],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField("Save and continue", widget=GovSubmitInput())


class GrantDescriptionForm(FlaskForm):
    DESCRIPTION_MAX_WORDS = 200

    description = TextAreaField(
        "What is the main purpose of this grant?",
        validators=[
            DataRequired("Enter the main purpose of this grant"),
            WordRange(max_words=DESCRIPTION_MAX_WORDS, field_display_name="Description"),
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
        description="Use the shared email address for the grant team.",
        validators=[
            DataRequired("Enter the email address"),
            Email(message="Enter an email address in the correct format, like name@example.com"),
        ],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField("Save and continue", widget=GovSubmitInput())


class GrantCheckYourAnswersForm(FlaskForm):
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


class ShareGrantUserForm(FlaskForm):
    user_email = StringField(
        "This needs to be the user’s personal 'communities.gov.uk' email address, not a shared email address.",
        validators=[
            DataRequired("Enter the email address"),
            Email(message="Enter an email address in the correct format, like name@communities.gov.uk"),
            validate_communities_gov_uk_email,
        ],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())
