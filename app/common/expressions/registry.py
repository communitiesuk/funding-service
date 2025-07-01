"""
This module acts as a singleton that tracks our managed expressions and the question data types that they support. Any
managed expression class definitions should use the `@register_managed_expression` decorator to get pulled into the
registry. The registry is probed by the managed expression form builder to automatically update the "add condition" and
"add validation" forms with the appropriate fields, validation, rendering, instantiation, etc.
"""

from collections import defaultdict
from typing import TYPE_CHECKING

from app.common.data.types import ManagedExpressionsEnum, QuestionDataType

if TYPE_CHECKING:
    from app.common.data.models import Question
    from app.common.expressions.managed import ManagedExpression


_registry_by_expression_enum: dict[ManagedExpressionsEnum, type["ManagedExpression"]] = {}
_registry_by_data_type: dict[QuestionDataType, list[type["ManagedExpression"]]] = defaultdict(list)


def get_registered_data_types() -> set[QuestionDataType]:
    """Returns the set of question data types that have at least one managed expression supporting them."""
    return set(k for k, v in _registry_by_data_type.items() if v)


def get_managed_expressions_for_question_type(question_type: QuestionDataType) -> list[type["ManagedExpression"]]:
    """Returns the list of managed expressions supported for a particular question type."""
    return _registry_by_data_type[question_type]


def lookup_managed_expression(expression_enum: ManagedExpressionsEnum) -> type["ManagedExpression"]:
    return _registry_by_expression_enum[expression_enum]


def register_managed_expression(cls: type["ManagedExpression"]) -> type["ManagedExpression"]:
    """
    A decorator that can be used to include a managed expression definition (subclass of
    app.common.expressions.managed.ManagedExpression) in this registry, which should allow it to automatically show up
    in the UI and forms for creating and editing instances of those expressions (conditions and validators).
    """
    for supported_question_data_type in cls.question_data_types:
        _registry_by_data_type[supported_question_data_type].append(cls)
        _registry_by_expression_enum[cls.name] = cls
    return cls


def get_supported_form_questions(question: "Question") -> list["Question"]:
    questions = question.form.questions
    return [q for q in questions if q.data_type in get_registered_data_types() and q.id != question.id]
