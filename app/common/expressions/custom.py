from typing import TYPE_CHECKING, ClassVar, Literal

from pydantic import TypeAdapter

from app.common.expressions import EvaluatableExpression

if TYPE_CHECKING:
    from app.common.data.models import Expression
    from app.common.expressions.forms import CalculatedConditionForm, CustomValidationExpressionForm


class CustomExpression(EvaluatableExpression):
    name: ClassVar[Literal["CUSTOM"]] = "CUSTOM"
    _key: None = None
    expression_name: str | None = None
    custom_expression: str
    custom_message: str | None = None

    @property
    def statement(self) -> str:
        # NOTE: Custom expression statements must currently wrap any ExpressionReferences (eg q_123) in double parens
        #       as if they're an interpolation eg `((q_123)) + ((q_234)) == 100` in order for ComponentReferences to be
        #       set up correctly. Ideally this would not be a requirement, but these are processed by
        #       `_validate_and_sync_expression_references` which searches for references using the interpolation regex.
        #       In the long term we should address this so that references can still be extracted without expecting
        #       double parens here. Those are meant to be reserved for interpolation, where we're embedding some
        #       expression within text strings.
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
