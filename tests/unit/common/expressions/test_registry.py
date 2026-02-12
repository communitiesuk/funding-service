import pytest

from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType
from app.common.expressions.registry import (
    _registry_by_expression_enum,
    get_managed_conditions_by_data_type,
    get_managed_validators_by_data_type,
    get_registered_data_types,
    validate_dependent_question_data_type_for_expression,
)


class TestManagedExpressions:
    def test_get_registered_data_types(self, factories):
        unsupported_question_type = QuestionDataType.TEXT_MULTI_LINE

        # because we're using a defaultdict we should make sure reading empty values can't change the logic
        assert get_managed_conditions_by_data_type(unsupported_question_type) == []
        assert get_managed_validators_by_data_type(unsupported_question_type) == []
        assert unsupported_question_type not in get_registered_data_types()

    def test_new_managed_expressions_added(self):
        assert len(_registry_by_expression_enum) == 12, (
            "If you've added a new managed expression, update this test and add "
            "suitable tests in `tests/integration/common/expressions/test_managed.py`"
        )

    @pytest.mark.parametrize(
        "target_expression_type, target_managed_expression_name, dependent_question_data_type, exp_result",
        [
            (ExpressionType.VALIDATION, ManagedExpressionsEnum.CUSTOM, QuestionDataType.NUMBER, True),
            (ExpressionType.VALIDATION, ManagedExpressionsEnum.CUSTOM, QuestionDataType.DATE, False),
            (ExpressionType.VALIDATION, ManagedExpressionsEnum.GREATER_THAN, QuestionDataType.DATE, False),
            (ExpressionType.VALIDATION, ManagedExpressionsEnum.GREATER_THAN, QuestionDataType.NUMBER, True),
            (ExpressionType.VALIDATION, ManagedExpressionsEnum.BETWEEN_DATES, QuestionDataType.DATE, True),
            (ExpressionType.VALIDATION, ManagedExpressionsEnum.BETWEEN_DATES, QuestionDataType.NUMBER, False),
            (ExpressionType.CONDITION, ManagedExpressionsEnum.CUSTOM, QuestionDataType.NUMBER, False),
            (ExpressionType.CONDITION, ManagedExpressionsEnum.GREATER_THAN, QuestionDataType.DATE, False),
            (ExpressionType.CONDITION, ManagedExpressionsEnum.GREATER_THAN, QuestionDataType.NUMBER, True),
            (ExpressionType.CONDITION, ManagedExpressionsEnum.BETWEEN_DATES, QuestionDataType.DATE, True),
            (ExpressionType.CONDITION, ManagedExpressionsEnum.BETWEEN_DATES, QuestionDataType.NUMBER, False),
        ],
    )
    def test_validate_data_type(
        self, target_expression_type, target_managed_expression_name, dependent_question_data_type, exp_result
    ):
        assert (
            validate_dependent_question_data_type_for_expression(
                target_managed_expression_name, target_expression_type, dependent_question_data_type
            )
            is exp_result
        )
