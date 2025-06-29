import abc
from typing import TYPE_CHECKING

# Define any "managed" expressions that can be applied to common conditions or validations
# that are built through the UI. These will be used alongside custom expressions
from uuid import UUID

from pydantic import BaseModel, TypeAdapter

from app.common.data.types import ManagedExpressionsEnum
from app.common.qid import SafeQidMixin

if TYPE_CHECKING:
    from app.common.data.models import Expression, Question


class ManagedExpression(BaseModel, SafeQidMixin):
    _key: ManagedExpressionsEnum
    question_id: UUID

    @property
    @abc.abstractmethod
    def statement(self) -> str:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def description(self) -> str: ...

    @property
    @abc.abstractmethod
    def message(self) -> str: ...

    @property
    def referenced_question(self) -> "Question":
        # todo: split up the collections interface to let us sensibly reason about whats importing what
        from app.common.data.interfaces.collections import get_question_by_id

        # todo: this will do a database query per expression on the question - for now we'd anticipate
        #       questions only have one or two managed expressions but in the future we should probably
        #       optimise this to fetch the full schema once and then re-use that throughout these helpers
        return get_question_by_id(self.question_id)


class GreaterThan(ManagedExpression):
    _key: ManagedExpressionsEnum = ManagedExpressionsEnum.GREATER_THAN
    question_id: UUID
    minimum_value: int
    inclusive: bool = False

    @property
    def description(self) -> str:
        return f"Is greater than{' or equal to' if self.inclusive else ''}"

    @property
    def message(self) -> str:
        return f"The answer must be greater than {'or equal to ' if self.inclusive else ''}{self.minimum_value}"

    @property
    def statement(self) -> str:
        return f"{self.safe_qid} >{'=' if self.inclusive else ''} {self.minimum_value}"


class LessThan(ManagedExpression):
    _key: ManagedExpressionsEnum = ManagedExpressionsEnum.LESS_THAN
    question_id: UUID
    maximum_value: int
    inclusive: bool = False

    @property
    def description(self) -> str:
        return f"Is less than{' or equal to' if self.inclusive else ''}"

    @property
    def message(self) -> str:
        return f"The answer must be less than {'or equal to ' if self.inclusive else ''}{self.maximum_value}"

    @property
    def statement(self) -> str:
        return f"{self.safe_qid} <{'=' if self.inclusive else ''} {self.maximum_value}"


class Between(ManagedExpression):
    _key: ManagedExpressionsEnum = ManagedExpressionsEnum.BETWEEN
    question_id: UUID
    minimum_value: int
    minimum_inclusive: bool = False
    maximum_value: int
    maximum_inclusive: bool = False

    @property
    def description(self) -> str:
        return "Is between"

    @property
    def message(self) -> str:
        # todo: optionally include the question name in the default message
        # todo: do you allow the form builder to override this if they need to
        #       - does that persist in the context (inherited from BaseExpression) or as a separate
        #         property on the model
        # todo: make this use expression evaluation/interpolation rather than f-strings
        return (
            f"The answer must be between "
            f"{self.minimum_value}{' (inclusive)' if self.minimum_inclusive else ' (exclusive)'} and "
            f"{self.maximum_value}{' (inclusive)' if self.maximum_inclusive else ' (exclusive)'}"
        )

    @property
    def statement(self) -> str:
        # todo: do you refer to the question by ID or slugs - pros and cons - discuss - by the end of the epic
        return (
            f"{self.minimum_value} "
            f"<{'=' if self.minimum_inclusive else ''} "
            f"{self.safe_qid} "
            f"<{'=' if self.maximum_inclusive else ''} "
            f"{self.maximum_value}"
        )


def get_managed_expression(expression: "Expression") -> ManagedExpression:
    # todo: fetching this to know what type is starting to feel strange - maybe this should be a top level property
    match expression.managed_name:
        case ManagedExpressionsEnum.GREATER_THAN:
            return TypeAdapter(GreaterThan).validate_python(expression.context)
        case ManagedExpressionsEnum.LESS_THAN:
            return TypeAdapter(LessThan).validate_python(expression.context)
        case ManagedExpressionsEnum.BETWEEN:
            return TypeAdapter(Between).validate_python(expression.context)
        case _:
            raise ValueError(f"Unsupported managed expression type: {expression.type}")
