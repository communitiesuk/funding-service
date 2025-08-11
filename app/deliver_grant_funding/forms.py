from typing import TYPE_CHECKING, Any, Callable, cast
from uuid import UUID

from flask import current_app
from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import (
    GovCharacterCount,
    GovCheckboxInput,
    GovRadioInput,
    GovSelect,
    GovSubmitInput,
    GovTextArea,
    GovTextInput,
)
from wtforms import Field, HiddenField, SelectField
from wtforms.fields.choices import RadioField
from wtforms.fields.simple import BooleanField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional, ValidationError

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.interfaces.collections import get_question_by_id, is_component_dependency_order_valid
from app.common.data.interfaces.grants import grant_name_exists
from app.common.data.interfaces.user import get_user_by_email
from app.common.data.types import QuestionDataType
from app.common.expressions.registry import get_supported_form_questions
from app.common.forms.validators import CommunitiesEmail, WordRange

if TYPE_CHECKING:
    from app.common.data.models import Question


def strip_string_if_not_empty(value: str) -> str | None:
    return value.strip() if value else value


def _validate_no_blank_lines(form: FlaskForm, field: Field) -> None:
    choices = field.data.split("\n")
    if any(choice.strip() == "" for choice in choices):
        raise ValidationError("Remove blank lines from the list")


def _validate_no_duplicates(form: FlaskForm, field: Field) -> None:
    choices = [choice.strip() for choice in field.data.split("\n")]
    if len(choices) != len(set(choices)):
        raise ValidationError("Remove duplicate options from the list")


def _validate_max_list_length(max_length: int) -> Callable[[Any, Any], None]:
    def validator(form: FlaskForm, field: Field) -> None:
        if len(field.data.split("\n")) > max_length:
            raise ValidationError(f"You have entered too many options. The maximum is {max_length}")

    return validator


class GrantSetupForm(FlaskForm):
    SUBMIT_BUTTON_TEXT_SETUP = "Save and continue"
    SUBMIT_BUTTON_TEXT_CHANGE = "Update"
    submit = SubmitField(SUBMIT_BUTTON_TEXT_SETUP, widget=GovSubmitInput())

    def __init__(self, *args: Any, is_update: bool = False, **kwargs: Any):
        super().__init__(*args, **kwargs)
        if is_update:
            self.submit.label.text = self.SUBMIT_BUTTON_TEXT_CHANGE


class GrantGGISForm(FlaskForm):
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
    submit = SubmitField("Save and continue", widget=GovSubmitInput())

    def validate(self, extra_validators: dict[str, list[Any]] | None = None) -> bool:
        if not super().validate(extra_validators):
            return False

        if self.has_ggis.data == "yes" and not self.ggis_number.data:
            self.ggis_number.errors = list(self.ggis_number.errors) + ["Enter your GGIS reference number"]
            return False

        return True


class GrantChangeGGISForm(FlaskForm):
    ggis_number = StringField(
        "What is the GGIS reference number?",
        description="For example, G2-SCH-2025-05-12346",
        filters=[strip_string_if_not_empty],
        validators=[DataRequired("Enter your GGIS reference number")],
        widget=GovTextInput(),
    )
    submit = SubmitField("Update", widget=GovSubmitInput())


class GrantNameForm(GrantSetupForm):
    name = StringField(
        "Enter the grant name",
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
        "Enter the main purpose of this grant",
        validators=[
            DataRequired("Enter the main purpose of this grant"),
            WordRange(max_words=DESCRIPTION_MAX_WORDS, field_display_name="description"),
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


class CollectionForm(GrantSetupForm):
    name = StringField(
        "What is the name of this monitoring report?",
        validators=[DataRequired("Enter a monitoring report name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )


class SectionForm(FlaskForm):
    title = StringField(
        "What is the name of the new section?",
        validators=[DataRequired("Enter a section title")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class FormForm(FlaskForm):
    title = StringField(
        "What is the name of the task?",
        validators=[DataRequired("Enter a task name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    section_id = RadioField(
        "Task section",
        description="A section is a group of related tasks",
        widget=GovRadioInput(),
        choices=[],
        validators=[Optional()],
    )
    submit = SubmitField(widget=GovSubmitInput())

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.show_section_field = False

        if (obj := kwargs.get("obj")) and not obj.section.is_default_section:
            self.show_section_field = True
            sections = obj.section.collection.sections
            self.section_id.choices = [(str(section.id), section.title) for section in sections]
            self.section_forms = [[form for form in section.forms] for section in sections]
            self.section_id.validators = [DataRequired("Select a section for the task")]


class QuestionTypeForm(FlaskForm):
    question_data_type = RadioField(
        "What type of question do you need?",
        choices=[(qdt.name, qdt.value) for qdt in QuestionDataType],
        validators=[DataRequired("Select a question type")],
        widget=GovRadioInput(),
    )
    parent = HiddenField(
        "Parent",
        description="The parent this question will belong to. If not set the question belongs to the form directly",
    )
    submit = SubmitField(widget=GovSubmitInput())


class GroupForm(FlaskForm):
    name = StringField(
        "Group name",
        validators=[DataRequired("Enter the group name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
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
        "Question hint (optional)",
        filters=[strip_string_if_not_empty],
        widget=GovTextArea(),
        description=(
            "If needed, provide a single sentence without a full stop to help someone answer the question correctly"
        ),
        render_kw={"params": {"rows": 2}},
    )
    name = StringField(
        "Question reference",
        validators=[DataRequired("Enter the question reference")],
        description=(
            "A short name for the answer in lower case, for example “risk category” or “contact email address”"
        ),
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )

    # Note: the next three fields all read from properties on the `Question` model because the names match. This
    # implicit connection needs to be maintained.
    data_source_items = StringField(
        "List of options",
        validators=[Optional()],
        description="Each option must be on its own line",
        filters=[strip_string_if_not_empty, lambda val: val.replace("\r", "") if val else val],
        widget=GovTextArea(),
    )
    separate_option_if_no_items_match = BooleanField(
        "Include a final answer for users if none of the options are appropriate",
        validators=[Optional()],
        widget=GovCheckboxInput(),
    )
    none_of_the_above_item_text = StringField(
        "Fallback option",
        default="None of the above",
        validators=[Optional()],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())

    def __init__(self, *args: Any, question_type: QuestionDataType, **kwargs: Any) -> None:
        super(QuestionForm, self).__init__(*args, **kwargs)

        self._question_type = question_type
        self._original_separate_option_if_no_items_match = self.separate_option_if_no_items_match.data

        if question_type in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
            max_length = (
                current_app.config["MAX_DATA_SOURCE_ITEMS_RADIOS"]
                if question_type == QuestionDataType.RADIOS
                else current_app.config["MAX_DATA_SOURCE_ITEMS_CHECKBOXES"]
            )
            self.data_source_items.validators = [
                DataRequired("Enter the options for your list"),
                _validate_no_blank_lines,
                _validate_no_duplicates,
                _validate_max_list_length(max_length=max_length),
            ]

            if self.separate_option_if_no_items_match.raw_data:
                self.none_of_the_above_item_text.validators = [
                    DataRequired("Enter the text to show for the fallback option")
                ]

        if question_type == QuestionDataType.CHECKBOXES:
            self.data_source_items.description = (
                "Each option must be on its own line. You can add a maximum of 10 options"
            )

    @property
    def normalised_data_source_items(self) -> list[str] | None:
        """For radios questions, we might want to display a final item beneath an 'or' divider, to signify that
        the choice is semantically unrelated to all of the other answers. The most common usecase for this is something
        like a "None of the above" answer.

        This answer is stored in the data source like a normal item. We store it as the last item and then record on
        the question that the last item in the data source should be presented distinctly.

        This form is essentially just responsible for appending the "None of the above" item to the data source items
        explicitly set by the form builder.
        """
        if self._question_type not in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
            return None

        data_source_items: list[str] = []
        if self.data_source_items.data is not None:
            data_source_items.extend(item.strip() for item in self.data_source_items.data.split("\n") if item.strip())

            if self.separate_option_if_no_items_match.data is True:
                data_source_items.append(cast(str, self.none_of_the_above_item_text.data))

        return data_source_items


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
            user_to_add = get_user_by_email(self.user_email.data)
            if not user_to_add:
                return True

            if AuthorisationHelper.is_platform_admin(user_to_add):
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


class SetUpReportForm(FlaskForm):
    name = StringField(
        "What is the name of the monitoring report?",
        widget=GovTextInput(),
        validators=[DataRequired("Enter a name for the monitoring report")],
    )

    submit = SubmitField("Continue and set up report", widget=GovSubmitInput())


class AddTaskForm(FlaskForm):
    title = StringField(
        "Task name",
        widget=GovTextInput(),
        validators=[DataRequired("Enter a name for the task")],
    )
    submit = SubmitField("Add task", widget=GovSubmitInput())


class ConditionSelectQuestionForm(FlaskForm):
    question = SelectField(
        "Which answer should the condition check?",
        choices=[],
        validators=[DataRequired("Select a question")],
        widget=GovSelect(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())

    def __init__(self, *args, question: "Question", **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)

        self.target_question = question

        self.question.choices = [
            (question.id, f"{question.text} ({question.name})") for question in get_supported_form_questions(question)
        ]

    def validate_question(self: "ConditionSelectQuestionForm", field: "Field") -> None:
        depends_on_question = get_question_by_id(self.question.data)
        if not is_component_dependency_order_valid(self.target_question, depends_on_question):
            raise ValidationError("Select an answer that comes before this question in the form")
