from typing import Any
from uuid import UUID

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

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data import interfaces
from app.common.data.interfaces.grants import grant_name_exists
from app.common.data.types import QuestionDataType
from app.common.forms.validators import CommunitiesEmail, WordRange


def strip_string_if_not_empty(value: str) -> str | None:
    return value.strip() if value else value


class GrantSetupForm(FlaskForm):
    SUBMIT_BUTTON_TEXT_SETUP = "Save and continue"
    SUBMIT_BUTTON_TEXT_CHANGE = "Update"
    submit = SubmitField(SUBMIT_BUTTON_TEXT_SETUP, widget=GovSubmitInput())

    def __init__(self, *args: Any, is_update: bool = False, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if is_update:
            self.submit.label.text = self.SUBMIT_BUTTON_TEXT_CHANGE


class GrantSetupIntroForm(FlaskForm):
    submit = SubmitField("Continue", widget=GovSubmitInput())


class GrantGGISForm(GrantSetupForm):
    has_ggis = RadioField(
        "Do you have a GGIS number?",
        # These choices have no effect on the frontend, but are used for validation. Frontend choices are found in the
        # template, currently at app/deliver_grant_funding/templates/deliver_grant_funding/grant_setup/ggis_number.html.
        # Developers will need to keep these in sync manually.
        choices=[("yes", "Yes"), ("no", "No")],
        validators=[DataRequired("Please select an option")],
        widget=GovRadioInput(),
    )
    ggis_number = StringField(
        "Enter your GGIS reference number",
        description="For example, G2-SCH-2025-05-12346",
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )

    def validate(self, extra_validators: dict[str, list[Any]] | None = None) -> bool:
        if not super().validate(extra_validators):
            return False

        if self.has_ggis.data == "yes" and not self.ggis_number.data:
            self.ggis_number.errors = list(self.ggis_number.errors) + ["Enter your GGIS reference number"]
            return False

        return True


class GrantNameForm(GrantSetupForm):
    name = StringField(
        "What is the name of this grant?",
        description="Use the full and official name of the grant - no abbreviations or acronyms",
        validators=[
            DataRequired("Enter the grant name"),
        ],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )

    def __init__(self, *args: Any, existing_grant_id: UUID | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.existing_grant_id = existing_grant_id

    def validate_name(self, field: StringField) -> None:
        if field.data and grant_name_exists(field.data, exclude_grant_id=self.existing_grant_id):
            raise ValidationError("Grant name already in use")


class GrantDescriptionForm(GrantSetupForm):
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


class GrantContactForm(GrantSetupForm):
    primary_contact_name = StringField(
        "Full name",
        validators=[DataRequired("Enter the full name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    primary_contact_email = StringField(
        "Email address",
        description="Use the shared email address for the grant team",
        validators=[
            DataRequired("Enter the email address"),
            Email(message="Enter an email address in the correct format, like name@example.com"),
        ],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )


class GrantCheckYourAnswersForm(FlaskForm):
    submit = SubmitField("Add grant", widget=GovSubmitInput())


class CollectionForm(GrantSetupForm):
    name = StringField(
        "What is the name of the collection?",
        validators=[DataRequired("Enter a collection name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )


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


class GrantAddUserForm(FlaskForm):
    def __init__(self, *args: Any, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.grant = kwargs["grant"]

    user_email = StringField(
        description="This needs to be the user’s personal 'communities.gov.uk' "
        "email address, not a shared email address.",
        validators=[
            DataRequired("Enter an email address"),
            CommunitiesEmail(),
        ],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())

    def validate(self, extra_validators: Any = None) -> bool:
        if not super().validate(extra_validators):
            return False

        if self.user_email.data:
            user_to_add = interfaces.user.get_user_by_email(self.user_email.data)
            if not user_to_add:
                return True

            if AuthorisationHelper.is_platform_admin(user_to_add) or AuthorisationHelper.is_grant_admin(
                grant_id=self.grant.id, user=user_to_add
            ):
                self.user_email.errors = list(self.user_email.errors) + [
                    "This user already exists as a Funding Service admin user so you cannot add them"
                ]
                return False
            if AuthorisationHelper.is_grant_member(grant_id=self.grant.id, user=user_to_add):
                self.user_email.errors = list(self.user_email.errors) + [
                    f'This user already is a member of "{self.grant.name}" so you cannot add them'
                ]
                return False

        return True
