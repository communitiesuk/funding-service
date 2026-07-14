"""Helpers for the read-only "View all questions" page.

These turn a collection's questions and groups into short, human-readable strings for a reference
page that lists every question a user could be asked (see the Access "View all questions" route).

They are intentionally presentation-only: no database writes and no submission data, so they can be
unit tested against plain model instances.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from markupsafe import Markup

from app.common.data.types import FileUploadTypes, QuestionDataType

if TYPE_CHECKING:
    from app.common.data.models import Component, Question


def _comma_or_join(items: list[str]) -> str:
    """Join a list for display, eg ["PDF", "CSV", "image"] -> "PDF, CSV or image"."""
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return f"{', '.join(items[:-1])} or {items[-1]}"


def get_question_setting_details(question: Question) -> list[str]:
    """Return short phrases describing a question's answer constraints.

    Each phrase is meant to be shown in brackets after the question text, eg
    "What is the project description (200 words)". Returns an empty list when the question has no
    settings worth surfacing on a reference page.
    """
    details: list[str] = []

    match question.data_type:
        case QuestionDataType.TEXT_MULTI_LINE:
            if question.word_limit:
                details.append(f"{question.word_limit} words")

        case QuestionDataType.NUMBER:
            number_parts: list[str] = []
            if question.prefix:
                number_parts.append(question.prefix)
            if question.suffix:
                number_parts.append(question.suffix)
            if question.number_type:
                number_parts.append(question.number_type.value.lower())
            if number_parts:
                details.append(", ".join(number_parts))

        case QuestionDataType.FILE_UPLOAD:
            file_types = question.file_types_supported or []
            max_size = question.maximum_file_size.human_readable if question.maximum_file_size else None

            # If every possible type is allowed there's little value in listing them all out.
            all_types_allowed = set(file_types) == set(FileUploadTypes)
            if file_types and not all_types_allowed:
                type_phrase = _comma_or_join([file_type.value for file_type in file_types])
                details.append(f"{type_phrase}, up to {max_size}" if max_size else type_phrase)
            elif max_size:
                details.append(f"up to {max_size}")

    return details


def describe_component_conditions(
    component: Component,
    interpolate: Callable[..., Markup],
) -> list[Markup]:
    """Return human-readable "Only applicable if …" strings for a component's conditions.

    Works for both questions and groups (a condition on a group applies to everything inside it).
    Managed conditions name the question they depend on plus the built-in condition message; custom
    conditions use their own message (falling back to a description if no message is set).

    `interpolate` is a context-bound interpolator (see ``SubmissionHelper.get_interpolator``) that
    renders any references embedded in the message. Any answer references that can't be resolved on
    this reference page are left in place, as a placeholder, on purpose.
    """
    descriptions: list[Markup] = []

    for condition in component.conditions:
        if condition.is_managed:
            managed = condition.managed
            subject = managed.subject_reference
            referenced_question = subject.question
            name = referenced_question.name if referenced_question else subject.label
            message = interpolate(managed.message, with_interpolation_highlighting=True)
            descriptions.append(Markup("Only applicable if “{}”: ").format(name) + message)
        else:
            custom = condition.custom
            message = interpolate(custom.message or custom.description, with_interpolation_highlighting=True)
            descriptions.append(Markup("Only applicable if ") + message)

    return descriptions
