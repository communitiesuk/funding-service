from typing import Any, NamedTuple
from uuid import UUID

from flask import render_template
from markupsafe import Markup


class RedirectException(Exception):
    def __init__(self, url: str) -> None:
        self.url = url


class ValidationError(NamedTuple):
    question_id: UUID
    question_name: str
    form_id: UUID
    form_title: str
    error_message: str
    answer: Any
    add_another_index: int | None = None


class SubmissionValidationFailed(ValueError):
    def __init__(self, message: str, errors: list[ValidationError]) -> None:
        self.message = message
        self.errors = errors

        super().__init__(self.message)

    @property
    def error_message(self) -> str:
        # TODO: refine this error content
        failed_questions_markup = render_template(
            "common/partials/validation-error-on-submission.html", errors=self.errors
        )
        return Markup(
            f"You cannot submit because you need to review some answers:"
            f"{failed_questions_markup}<br>"
            f"If you need help, contact our support desk."
        )
