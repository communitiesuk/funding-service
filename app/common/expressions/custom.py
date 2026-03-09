from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import TypeAdapter

from app.common.expressions import EvaluatableExpression

if TYPE_CHECKING:
    from app.common.data.models import Expression


class CustomExpression(EvaluatableExpression):
    name: ClassVar[Literal["CUSTOM"]] = "CUSTOM"
    _key: None = None
    custom_expression: str
    custom_message: str
    custom_description: str = (
        "Custom calculation"  # This will be customisable when we allow creating reusable calculations
    )

    @property
    def statement(self) -> str:
        return self.custom_expression

    @property
    def description(self) -> str:
        return self.custom_description

    @property
    def message(self) -> str:
        return self.custom_message


def get_custom_expression(expression: Expression) -> CustomExpression:
    if not expression.is_custom:
        raise ValueError(f"Expression {expression.id} is not a custom expression.")

    ExpressionType = TypeAdapter(CustomExpression)

    return ExpressionType.validate_python(expression.context)
