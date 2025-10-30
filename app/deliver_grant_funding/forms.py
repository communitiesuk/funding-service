from typing import TYPE_CHECKING, Any, Callable, Mapping, Sequence, Union, cast
from typing import Optional as TOptional
from uuid import UUID

from flask import current_app
from flask_wtf import FlaskForm
from govuk_frontend_wtf.wtforms_widgets import (
    GovCharacterCount,
    GovCheckboxesInput,
    GovCheckboxInput,
    GovRadioInput,
    GovSelect,
    GovSubmitInput,
    GovTextArea,
    GovTextInput,
)
from wtforms import Field, HiddenField, IntegerField, SelectField, SelectMultipleField
from wtforms.fields.choices import RadioField
from wtforms.fields.simple import BooleanField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Email, Optional, ValidationError

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data.interfaces.collections import (
    group_name_exists,
)
from app.common.data.interfaces.grants import grant_name_exists
from app.common.data.interfaces.user import get_user_by_email
from app.common.data.types import GroupDisplayOptions, MultilineTextInputRows, NumberInputWidths, QuestionDataType
from app.common.expressions import ExpressionContext
from app.common.expressions.registry import get_supported_form_questions
from app.common.forms.fields import MHCLGAccessibleAutocomplete
from app.common.forms.helpers import get_referenceable_questions
from app.common.forms.validators import CommunitiesEmail, WordRange

if TYPE_CHECKING:
    from app.common.data.models import Component, Form, Group, Question
    from app.deliver_grant_funding.session_models import AddContextToComponentSessionModel


def strip_string_if_not_empty(value: str) -> str | None:
    return value.strip() if value else value


def strip_newlines(value: str) -> str | None:
    return value.replace("\n", "") if value else value


def empty_string_to_none(value: str) -> str | None:
    return value if value else None


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


def _validate_textarea_size(form: FlaskForm, field: Field) -> None:
    rows = int(field.data)
    if rows not in MultilineTextInputRows:
        raise ValidationError("Select a text area size")


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
        "Question group name",
        validators=[DataRequired("Enter question the group name")],
        filters=[strip_string_if_not_empty],
        widget=GovTextInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())

    def __init__(self, *args: Any, check_name_exists: bool = False, group_form_id: UUID | None = None, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.check_name_exists = check_name_exists
        self.group_form_id = group_form_id

    def validate_name(self, field: StringField) -> None:
        if field.data and self.check_name_exists:
            if not self.group_form_id:
                raise ValueError("group_form_id must be provided if check_name_exists is True")
            if group_name_exists(field.data, self.group_form_id):
                raise ValidationError("A question group with this name already exists")


class GroupDisplayOptionsForm(FlaskForm):
    show_questions_on_the_same_page = RadioField(
        "How do you want this question group to be displayed?",
        choices=[
            (GroupDisplayOptions.ONE_QUESTION_PER_PAGE, "One question per page"),
            (GroupDisplayOptions.ALL_QUESTIONS_ON_SAME_PAGE, "All questions on the same page"),
        ],
        default=GroupDisplayOptions.ONE_QUESTION_PER_PAGE,
        validators=[DataRequired("Select how you want this question group to be displayed")],
        widget=GovRadioInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class GroupAddAnotherOptionsForm(FlaskForm):
    question_group_is_add_another = RadioField(
        "Should people be able to answer all questions in this question group more than once?",
        choices=[
            ("yes", "Yes"),
            ("no", "No - questions can only be answered once"),
        ],
        default="no",
        validators=[
            DataRequired(
                "Select whether people should be able to answer all questions in this question group more than once"
            )
        ],
        widget=GovRadioInput(),
    )
    submit = SubmitField(widget=GovSubmitInput())


class GroupAddAnotherSummaryForm(FlaskForm):
    questions_to_show_in_add_another_summary = SelectMultipleField(
        "Which question answers should be included when showing a summary of each add another answer?",
        default=[],
        widget=GovCheckboxesInput(),
        choices=[],
        validators=[
            DataRequired(
                "Select which question answers should be included when showing a summary of each add another answer"
            )
        ],
        render_kw={"params": {"fieldset": {"legend": {"classes": "govuk-visually-hidden"}}}},
    )

    def __init__(self, *args: Any, group: "Group", **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.questions_to_show_in_add_another_summary.choices = [
            (str(question.id), question.name) for question in group.cached_questions
        ]

        if not self.is_submitted():
            self.questions_to_show_in_add_another_summary.data = [
                str(question.id) for question in group.questions_in_add_another_summary
            ]

    submit = SubmitField(widget=GovSubmitInput())


class QuestionForm(FlaskForm):
    text = StringField(
        "Question text",
        description="The text grant recipients will see on their report",
        validators=[DataRequired("Enter the question text")],
        filters=[strip_string_if_not_empty, strip_newlines],
        widget=GovTextArea(),
    )
    hint = StringField(
        "Question hint (optional)",
        filters=[strip_string_if_not_empty],
        widget=GovTextArea(),
        description=(
            "A single sentence to help someone answer the question, for example, ‘Must be between 6 and 8 digits long’"
        ),
        render_kw={"params": {"rows": 2}},
    )
    name = StringField(
        "Question name",
        validators=[DataRequired("Enter the question name")],
        description=(
            "A short name for this question that will be used for reference in monitoring reports (use lower-case text)"
        ),
        filters=[strip_string_if_not_empty, strip_newlines],
        widget=GovTextInput(),
    )
    add_context = StringField(widget=GovSubmitInput())

    # Note: the next fields all read from properties on the `Question` model because the names match. This
    # implicit connection needs to be maintained.
    data_source_items = StringField(
        "List of options",
        validators=[Optional()],
        description="Enter each option on a new line",
        filters=[strip_string_if_not_empty, lambda val: val.replace("\r", "") if val else val],
        widget=GovTextArea(),
    )
    separate_option_if_no_items_match = BooleanField(
        "Include an ‘other’ option",
        validators=[Optional()],
        widget=GovCheckboxInput(),
    )
    none_of_the_above_item_text = StringField(
        "‘Other’ option text",
        default="Other",
        validators=[Optional()],
        widget=GovTextInput(),
    )

    # Multiline textarea field presentation options
    rows = SelectField(
        "Text area size",
        widget=GovSelect(),
        validators=[Optional()],
        choices=[(opt.value, f"{opt.name.title()} ({opt.value} rows)") for opt in MultilineTextInputRows],
        default=MultilineTextInputRows.MEDIUM.value,
    )
    word_limit = IntegerField(
        "Word limit (optional)",
        widget=GovTextInput(),
        validators=[Optional()],
    )

    # Integer field presentation options
    prefix = StringField(
        "Prefix (optional)",
        widget=GovTextInput(),
        validators=[Optional()],
        filters=[strip_string_if_not_empty, empty_string_to_none],
    )
    suffix = StringField(
        "Suffix (optional)",
        widget=GovTextInput(),
        validators=[Optional()],
        filters=[strip_string_if_not_empty, empty_string_to_none],
    )
    width = SelectField(
        "Input width",
        description="Reduce the size of the input if you know the answer will be smaller",
        widget=GovSelect(),
        validators=[Optional()],
        choices=[(opt.value, f"{opt.name.title()}") for opt in NumberInputWidths],
        default=NumberInputWidths.BILLIONS.value,
    )

    # Date field presentation options
    approximate_date = BooleanField(
        "Ask for an approximate date (month and year only)",
        validators=[Optional()],
        widget=GovCheckboxInput(),
    )

    submit = SubmitField(widget=GovSubmitInput())

    def __init__(
        self,
        *args: Any,
        question_type: QuestionDataType,
        obj: TOptional[Union["Question", "AddContextToComponentSessionModel"]] = None,
        **kwargs: Any,
    ) -> None:
        super(QuestionForm, self).__init__(*args, obj=obj, **kwargs)

        self._question_type = question_type
        self._original_separate_option_if_no_items_match = self.separate_option_if_no_items_match.data

        match question_type:
            case QuestionDataType.RADIOS | QuestionDataType.CHECKBOXES:
                max_length = (
                    current_app.config["MAX_DATA_SOURCE_ITEMS_RADIOS"]
                    if question_type == QuestionDataType.RADIOS
                    else current_app.config["MAX_DATA_SOURCE_ITEMS_CHECKBOXES"]
                )
                self.data_source_items.validators = [  # ty: ignore[invalid-assignment]
                    DataRequired("Enter the options for your list"),
                    _validate_no_blank_lines,
                    _validate_no_duplicates,
                    _validate_max_list_length(max_length=max_length),
                ]

                if self.separate_option_if_no_items_match.raw_data:
                    self.none_of_the_above_item_text.validators = [  # ty: ignore[invalid-assignment]
                        DataRequired("Enter the text to show for the fallback option")
                    ]

                if question_type == QuestionDataType.CHECKBOXES:
                    self.data_source_items.description = (
                        "Enter each option on a new line - you can add a maximum of 10 options"
                    )

            case QuestionDataType.TEXT_MULTI_LINE:
                self.rows.validators = [_validate_textarea_size]  # ty: ignore[invalid-assignment]

    @property
    def normalised_data_source_items(self) -> list[str] | None:
        """For radios questions, we might want to display a final item beneath an 'or' divider, to signify that
        the choice is semantically unrelated to all of the other answers. The most common usecase for this is something
        like a "Other" answer.

        This answer is stored in the data source like a normal item. We store it as the last item and then record on
        the question that the last item in the data source should be presented distinctly.

        This form is essentially just responsible for appending the "Other" item to the data source items
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

    def validate_prefix(self, field: Field) -> None:
        if self.prefix.data and self.suffix.data:
            raise ValidationError("Remove the suffix if you need a prefix")

    def validate_suffix(self, field: Field) -> None:
        if self.prefix.data and self.suffix.data:
            raise ValidationError("Remove the prefix if you need a suffix")

    def is_submitted_to_add_context(self) -> bool:
        return bool(self.is_submitted() and self.add_context.data and not self.submit.data)

    def get_component_form_data(self) -> dict[str, Any]:
        return {key: data for key, data in self.data.items() if key not in {"csrf_token", "submit"}}


class AddContextSelectSourceForm(FlaskForm):
    data_source = RadioField(
        "Select a data source",
        choices=[(choice.name, choice.value) for choice in ExpressionContext.ContextSources],
        widget=GovRadioInput(),
    )

    submit = SubmitField(widget=GovSubmitInput())

    def __init__(self, *args: Any, form: "Form", current_component: TOptional["Component"], **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.form = form
        self.current_component = current_component

    def validate_data_source(self, field: Field) -> None:
        try:
            choice = ExpressionContext.ContextSources[field.data]
        except KeyError:
            return

        if choice == ExpressionContext.ContextSources.TASK:
            if not get_referenceable_questions(form=self.form, current_component=self.current_component):
                raise ValidationError("There are no available questions before this one in the form")


class SelectDataSourceQuestionForm(FlaskForm):
    question = SelectField(
        "Select which question's answer to use",
        choices=[],
        validators=[DataRequired("Select the question")],
        widget=MHCLGAccessibleAutocomplete(),
    )

    submit = SubmitField(widget=GovSubmitInput())

    def __init__(
        self,
        form: "Form",
        interpolate: Callable[[str], str],
        current_component: TOptional["Component"],
        expression: bool = False,
        *args: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)

        # If we're editing an existing question, then only list questions that are "before" this one in the form.
        # If it's not an existing question, then it gets added to the end of the form, so all questions are "before".

        # TODO: when using this for conditions and validation, we also need to filter the 'available' questions
        # based on the usable data types. Also below in SelectDataSourceQuestionForm. Think about if we can
        # centralise this logic sensibly.

        self.question.choices = [("", "")] + [
            (str(question.id), interpolate(question.text))
            for question in get_referenceable_questions(form, current_component)
            if (not expression or question.data_type == current_component.data_type)  # type: ignore[assignment, union-attr]
        ]


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

            if AuthorisationHelper.is_deliver_grant_admin(grant_id=self.grant.id, user=user_to_add):
                self.user_email.errors = list(self.user_email.errors) + [
                    f'This user already is an admin of "{self.grant.name}" so you cannot add them'
                ]
                return False
            if AuthorisationHelper.is_deliver_grant_member(grant_id=self.grant.id, user=user_to_add):
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
        widget=MHCLGAccessibleAutocomplete(),
    )
    submit = SubmitField("Continue", widget=GovSubmitInput())

    def __init__(self, *args, current_component: "Component", interpolate: Callable[[str], str], **kwargs):  # type: ignore[no-untyped-def]
        super().__init__(*args, **kwargs)

        self.target_question = current_component

        if len(get_supported_form_questions(current_component)) > 0:
            self.question.choices = [("", "")] + [
                (str(question.id), f"{interpolate(question.text)} ({question.name})")
                for question in get_supported_form_questions(current_component)
            ]  # type: ignore[assignment]


class AddGuidanceForm(FlaskForm):
    guidance_heading = StringField(
        "Give your page a heading",
        description=(
            "When you add guidance your question text will no longer be the main page heading, "
            "so you need to use a different one. "
            "Use a heading that’s a statement rather than a question - for example, ‘Interview needs’."
        ),
        widget=GovTextInput(),
        filters=[strip_string_if_not_empty],
    )
    guidance_body = StringField(
        "Add guidance text",
        description="Use Markdown if you need to format your guidance content. Formatting help can be found below.",
        widget=GovTextArea(),
        filters=[strip_string_if_not_empty],
    )
    add_context = StringField(widget=GovSubmitInput())

    preview = SubmitField("Save and preview guidance", widget=GovSubmitInput())
    submit = SubmitField("Save guidance", widget=GovSubmitInput())

    def __init__(self, *args: Any, heading_required: bool | None = True, **kwargs: Any):
        super().__init__(*args, **kwargs)
        self.heading_required = heading_required

    def validate(self, extra_validators: Mapping[str, Sequence[Any]] | None = None) -> bool:
        result: bool = super().validate(extra_validators=extra_validators)

        if not result:
            return result

        if (
            self.heading_required
            and (self.guidance_heading.data or self.guidance_body.data)
            and not (self.guidance_heading.data and self.guidance_body.data)
        ):
            self.form_errors.append("Provide both a page heading and guidance text, or neither")
            return False

        return result

    def is_submitted_to_add_context(self) -> bool:
        return bool(self.is_submitted() and self.add_context.data and not (self.submit.data or self.preview.data))

    def get_component_form_data(self) -> dict[str, Any]:
        return {key: data for key, data in self.data.items() if key not in {"csrf_token", "submit"}}


class PreviewGuidanceForm(FlaskForm):
    guidance = StringField()
