import abc
import enum
from uuid import UUID

from pydantic import BaseModel

# Define any "managed" expressions that can be applied to common conditions or validations
# that are built through the UI. These will be used alongside custom expressions


class ManagedExpressions(enum.StrEnum):
    GREATER_THAN = "Greater than"


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

    @property
    def description(self) -> str:
        return "Is greater than"

    @property
    def message(self) -> str:
        # todo: optionally include the question name in the default message
        # todo: do you allow the form builder to override this if they need to
        #       - does that persist in the context (inherited from BaseExpression) or as a separate
        #         property on the model
        # todo: make this use expression evaluation/interpolation rather than f-strings
        return f"The answer must be {self.minimum_value} or greater"

    @property
    def expression(self) -> str:
        # todo: are UUIDs parsable by the expression parser/ language
        return f"(( {self.question_id} )) > {self.minimum_value}"
