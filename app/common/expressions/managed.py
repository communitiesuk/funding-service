import abc

# Define any "managed" expressions that can be applied to common conditions or validations
# that are built through the UI. These will be used alongside custom expressions
from uuid import UUID

from pydantic import BaseModel

from app.common.data.types import ManagedExpressions
from app.common.expressions import mangle_question_id_for_context


class BaseExpression(BaseModel):
    key: ManagedExpressions

    @property
    @abc.abstractmethod
    def expression(self) -> str:
        raise NotImplementedError


class GreaterThan(BaseExpression):
    key: ManagedExpressions = ManagedExpressions.GREATER_THAN
    question_id: UUID
    minimum_value: int
    inclusive: bool = False

    @property
    def description(self) -> str:
        return f"Is greater than{' or equal to' if self.inclusive else ''}"

    @property
    def message(self) -> str:
        # todo: optionally include the question name in the default message
        # todo: do you allow the form builder to override this if they need to
        #       - does that persist in the context (inherited from BaseExpression) or as a separate
        #         property on the model
        # todo: make this use expression evaluation/interpolation rather than f-strings
        return f"The answer must be greater than {'or equal to ' if self.inclusive else ''}{self.minimum_value}"

    @property
    def expression(self) -> str:
        # todo: do you refer to the question by ID or slugs - pros and cons - discuss - by the end of the epic
        qid = mangle_question_id_for_context(self.question_id)
        return f"{qid} >{'=' if self.inclusive else ''} {self.minimum_value}"


class LessThan(BaseExpression):
    key: ManagedExpressions = ManagedExpressions.LESS_THAN
    question_id: UUID
    maximum_value: int
    inclusive: bool = False

    @property
    def description(self) -> str:
        return f"Is less than{' or equal to' if self.inclusive else ''}"

    @property
    def message(self) -> str:
        # todo: optionally include the question name in the default message
        # todo: do you allow the form builder to override this if they need to
        #       - does that persist in the context (inherited from BaseExpression) or as a separate
        #         property on the model
        # todo: make this use expression evaluation/interpolation rather than f-strings
        return f"The answer must be less than {'or equal to ' if self.inclusive else ''}{self.maximum_value}"

    @property
    def expression(self) -> str:
        # todo: do you refer to the question by ID or slugs - pros and cons - discuss - by the end of the epic
        qid = mangle_question_id_for_context(self.question_id)
        return f"{qid} >{'=' if self.inclusive else ''} {self.maximum_value}"


class Between(BaseExpression):
    key: ManagedExpressions = ManagedExpressions.BETWEEN
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
    def expression(self) -> str:
        # todo: do you refer to the question by ID or slugs - pros and cons - discuss - by the end of the epic
        qid = mangle_question_id_for_context(self.question_id)
        return (
            f"{self.minimum_value} "
            f"<{'=' if self.minimum_inclusive else ''} "
            f"{qid} "
            f"<{'=' if self.maximum_inclusive else ''} "
            f"{self.maximum_value}"
        )
