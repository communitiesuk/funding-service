"""Helpers for the read-only "View all questions" page.

These turn a collection's questions and groups into short, human-readable strings for a reference
page that lists every question a user could be asked (see the admin "View all questions" route).

They are intentionally presentation-only: no database writes and no submission data, so they can be
unit tested against plain model instances.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar

from markupsafe import Markup

from app.common.data.types import FileUploadTypes, QuestionDataType

if TYPE_CHECKING:
    from werkzeug.datastructures import MultiDict

    from app.common.data.models import Component, Question


class QuestionInfo(enum.StrEnum):
    """A single, independently toggleable category of information on the "View all questions" page.

    Each member is one filter on the page: whether that piece of information is shown for every
    question (or group) that has it. The value is the query-string token used in the ``show`` filter.
    """

    HINT = "hint"
    SETTINGS = "settings"
    OPTIONS = "options"
    GUIDANCE = "guidance"
    CONDITIONS = "conditions"
    VALIDATIONS = "validations"

    @property
    def label(self) -> str:
        """The human-readable name shown on the filter checkbox and its "selected filter" tag."""
        return {
            QuestionInfo.HINT: "Hint text",
            QuestionInfo.SETTINGS: "Question settings",
            QuestionInfo.OPTIONS: "Answer options",
            QuestionInfo.GUIDANCE: "Guidance",
            QuestionInfo.CONDITIONS: "Conditions",
            QuestionInfo.VALIDATIONS: "Validations",
        }[self]


@dataclass(frozen=True)
class QuestionDisplayOptions:
    """Which categories of question information the "View all questions" page is currently showing.

    The page's MOJ filters are a set of independent on/off toggles, one per :class:`QuestionInfo`.
    With no filtering applied (a fresh visit) everything is shown; once the user applies the filter
    form a sentinel query arg is present, so an empty selection means "show nothing" rather than
    "not filtered yet".
    """

    shown: frozenset[QuestionInfo]

    # Query-string contract shared by the filter form, the "remove filter" tag links and the PDF link.
    SENTINEL_PARAM: ClassVar[str] = "filtered"
    FILTER_PARAM: ClassVar[str] = "show"

    @classmethod
    def all_shown(cls) -> QuestionDisplayOptions:
        return cls(shown=frozenset(QuestionInfo))

    @classmethod
    def from_request_args(cls, args: MultiDict[str, str]) -> QuestionDisplayOptions:
        """Build display options from ``request.args``.

        Absent the sentinel (a fresh visit) everything is shown. Once filters have been applied the
        selection is exactly the recognised ``show`` values, so unchecking everything shows nothing.
        """
        if cls.SENTINEL_PARAM not in args:
            return cls.all_shown()

        selected = set()
        for value in args.getlist(cls.FILTER_PARAM):
            try:
                selected.add(QuestionInfo(value))
            except ValueError:
                continue
        return cls(shown=frozenset(selected))

    @property
    def hint(self) -> bool:
        return QuestionInfo.HINT in self.shown

    @property
    def settings(self) -> bool:
        return QuestionInfo.SETTINGS in self.shown

    @property
    def options(self) -> bool:
        return QuestionInfo.OPTIONS in self.shown

    @property
    def guidance(self) -> bool:
        return QuestionInfo.GUIDANCE in self.shown

    @property
    def conditions(self) -> bool:
        return QuestionInfo.CONDITIONS in self.shown

    @property
    def validations(self) -> bool:
        return QuestionInfo.VALIDATIONS in self.shown

    @property
    def active_categories(self) -> list[QuestionInfo]:
        """The shown categories, in a stable order for rendering the "selected filters" tags."""
        return [info for info in QuestionInfo if info in self.shown]

    def checkbox_items(self) -> list[dict[str, Any]]:
        """Items for the ``govukCheckboxes`` filter form, one per category with its checked state."""
        return [{"value": info.value, "text": info.label, "checked": info in self.shown} for info in QuestionInfo]

    def query_dict(self) -> dict[str, Any]:
        """Query args (for ``url_for``) that reproduce this exact selection, including the sentinel."""
        return {
            self.SENTINEL_PARAM: "1",
            self.FILTER_PARAM: [info.value for info in self.active_categories],
        }

    def without(self, info: QuestionInfo) -> QuestionDisplayOptions:
        """The same options with one category hidden - used to build a tag's "remove filter" link."""
        return QuestionDisplayOptions(shown=self.shown - {info})


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
    renders any references embedded in the message, in whichever display style the caller bound (the
    web page highlights references; the printable PDF underlines the question name). Any answer
    references that can't be resolved on this reference page are left in place, as a placeholder, on purpose.
    """
    descriptions: list[Markup] = []

    for condition in component.conditions:
        if condition.is_managed:
            managed = condition.managed
            subject = managed.subject_reference
            referenced_question = subject.question
            name = referenced_question.name if referenced_question else subject.label
            message = interpolate(managed.message)
            descriptions.append(Markup("Only applicable if “{}”: ").format(name) + message)
        else:
            custom = condition.custom
            message = interpolate(custom.message or custom.description)
            descriptions.append(Markup("Only applicable if ") + message)

    return descriptions


def describe_component_validations(
    component: Component,
    interpolate: Callable[..., Markup],
) -> list[Markup]:
    """Return human-readable validation-rule strings for a component's validations.

    Works for both questions and groups. Uses each validation's evaluatable-expression message, the
    same text the question builder shows when listing validations (see the
    ``_explicit-validations.html`` partial). ``interpolate`` renders any embedded references in
    whichever display style the caller bound (highlighted on the web page, underlined in the PDF).
    """
    return [interpolate(validation.evaluatable_expression.message) for validation in component.validations]
