import re
from typing import List, Tuple, cast

from email_validator import EmailNotValidError, validate_email
from flask import current_app
from wtforms import StringField
from wtforms.fields.choices import SelectMultipleField
from wtforms.fields.core import Field
from wtforms.form import BaseForm
from wtforms.validators import Email, HostnameValidation, Regexp, ValidationError


class WordRange:
    """
    Validates that the number of words in a field's data is within a specified range.
    """

    def __init__(
        self,
        min_words: int | None = None,
        max_words: int | None = None,
        field_display_name: str | None = None,
    ) -> None:
        if min_words is None and max_words is None:
            raise ValueError("min_words and max_words cannot both be None")
        if min_words is not None and max_words is not None and max_words < min_words:
            raise ValueError("max_words cannot be less than min_words")
        self.min_words = min_words
        self.max_words = max_words
        self.field_display_name = field_display_name

    def __call__(self, form: BaseForm, field: Field) -> None:
        if not field.data:
            return  # Don't validate empty fields - use DataRequired for that

        words = field.data.split()
        word_count = len(words)
        field_display_name = self.field_display_name or field.name

        # Ensure first character is uppercase since we start all validation messages with it.
        field_display_name = field_display_name[0].upper() + field_display_name[1:]

        if self.min_words is not None and self.max_words is not None:
            if self.min_words == self.max_words and word_count != self.min_words:
                raise ValidationError(f"{field_display_name} must contain exactly {self.min_words} words")

            if word_count < self.min_words or word_count > self.max_words:
                raise ValidationError(
                    f"{field_display_name} must be between {self.min_words} words and {self.max_words} words"
                )

        if self.min_words is not None:
            if word_count < self.min_words:
                raise ValidationError(f"{field_display_name} must be {self.min_words} words or more")

        if self.max_words is not None:
            if word_count > self.max_words:
                raise ValidationError(f"{field_display_name} must be {self.max_words} words or fewer")


class CommunitiesEmail(Email):
    def __call__(self, form: BaseForm, field: Field) -> None:
        allowed_domains = current_app.config["INTERNAL_DOMAINS"]
        try:
            result = validate_email(
                field.data,
                check_deliverability=self.check_deliverability,
                allow_smtputf8=self.allow_smtputf8,
                allow_empty_local=self.allow_empty_local,
            )
            domain = f"@{result.domain}"
        except EmailNotValidError as e:
            raise ValidationError("Enter an email address in the correct format, like name@example.com") from e

        if allowed_domains and domain.lower() not in [d.lower() for d in allowed_domains]:
            raise ValidationError(f"Email address must end with {' or '.join(allowed_domains)}")


class URLWithoutProtocol(Regexp):
    """
    Based off the `URL` validator from WTForms, except we specifically allow no protocol (eg https://) to be provided.
    """

    def __init__(self, require_tld: bool = True, allow_ip: bool = True, message: str | None = None) -> None:
        regex = (
            r"^(?P<protocol>https?://)?"
            r"(?P<host>[^\/\?:]+)"
            r"(?P<port>:[0-9]+)?"
            r"(?P<path>\/.*?)?"
            r"(?P<query>\?.*)?$"
        )
        super().__init__(regex, re.IGNORECASE, message)
        self.validate_hostname = HostnameValidation(require_tld=require_tld, allow_ip=allow_ip)

    def __call__(self, form: BaseForm, field: StringField, message: str | None = None) -> re.Match[str]:
        message = self.message
        if message is None:
            message = field.gettext("Invalid URL.")

        match = super().__call__(form, field, message)
        if not self.validate_hostname(match.group("host")):
            raise ValidationError(message)

        return match


class FinalOptionExclusive:
    """
    Validates that the user cannot select one or more checkbox options plus the final "Other" option, which should be
    exclusive.

    The GOV.UK Checkbox component does cater for this with an 'exclusive' property for the final option which will
    uncheck all options. This relies on Javascript however so we need some validation as a fallback should the user have
    Javascript disabled.

    This validator should only be used if the checkbox question type has been used with a separate final option.
    """

    def __init__(self, question_name: str, message: str | None = None) -> None:
        self.question_name = question_name
        self.message = message

    def __call__(self, form: BaseForm, field: SelectMultipleField) -> None:
        if not field.data:
            return  # Don't validate empty fields - use DataRequired for that

        checkbox_choices = field.data
        # MyPy expects field.choices to be a dict[str, Any] but in our implementation with wtforms it's a list of tuples
        form_choices = cast(List[Tuple[str, str]], field.choices)
        final_option_key, final_option_label, *_ = form_choices[-1]
        if final_option_key in checkbox_choices and len(checkbox_choices) > 1:
            message = self.message or f"Select {self.question_name}, or select {final_option_label}"
            raise ValidationError(message)
