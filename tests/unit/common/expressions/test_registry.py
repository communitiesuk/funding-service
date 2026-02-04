from app.common.data.types import QuestionDataType
from app.common.expressions.registry import (
    _registry_by_expression_enum,
    get_managed_conditions_by_data_type,
    get_managed_validators_by_data_type,
    get_registered_data_types,
)


class TestManagedExpressions:
    def test_get_registered_data_types(self, factories):
        unsupported_question_type = QuestionDataType.TEXT_MULTI_LINE

        # because we're using a defaultdict we should make sure reading empty values can't change the logic
        assert get_managed_conditions_by_data_type(unsupported_question_type) == []
        assert get_managed_validators_by_data_type(unsupported_question_type) == []
        assert unsupported_question_type not in get_registered_data_types()

    def test_new_managed_expressions_added(self):
        assert len(_registry_by_expression_enum) == 11, (
            "If you've added a new managed expression, update this test and add"
            "suitable tests in `tests/integration/common/expressions/test_managed.py`"
        )
