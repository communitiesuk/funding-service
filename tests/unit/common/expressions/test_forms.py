from app.common.data.types import ManagedExpressionsEnum
from app.common.expressions.forms import AddIntegerExpressionForm


class TestAddIntegerValidationForm:
    def test_custom_between_validator(self):
        form = AddIntegerExpressionForm(type=ManagedExpressionsEnum.BETWEEN.value, bottom_of_range=10, top_of_range=5)
        assert not form.validate()
        assert "The minimum value must be lower than the maximum value" in form.errors["bottom_of_range"]
