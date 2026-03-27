from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import TypeAdapter

from app.common.expressions import EvaluatableExpression

if TYPE_CHECKING:
    from app.common.data.models import Expression
    from app.common.expressions.forms import CalculatedConditionForm, CustomValidationExpressionForm


class CustomExpression(EvaluatableExpression):
    name: ClassVar[Literal["CUSTOM"]] = "CUSTOM"
    question_id: None = None
    _key: None = None
    expression_name: str | None = None
    custom_expression: str
    custom_message: str | None = None

    @property
    def statement(self) -> str:
        return self.custom_expression

    @property
    def message(self) -> str | None:
        return self.custom_message

    @property
    def description(self) -> str:
        return self.expression_name or "Custom expression"

    @property
    def reference_aware_fields(self) -> set[str]:
        return {"custom_expression", "custom_message"}

    @classmethod
    def build_from_form(cls, form: CustomValidationExpressionForm | CalculatedConditionForm) -> CustomExpression:
        from app.common.expressions.forms import CustomValidationExpressionForm

        if isinstance(form, CustomValidationExpressionForm):
            return CustomExpression(
                custom_expression=form.custom_expression.data,  # ty:ignore[invalid-argument-type]
                custom_message=form.custom_message.data,
            )
        else:
            return CustomExpression(
                expression_name=form.expression_name.data,
                custom_expression=form.custom_expression.data,  # ty:ignore[invalid-argument-type]
            )


def get_custom_expression(expression: Expression) -> CustomExpression:
    if not expression.is_custom:
        raise ValueError(f"Expression {expression.id} is not a custom expression.")

    ExpressionType = TypeAdapter(CustomExpression)

    return ExpressionType.validate_python(expression.context)
