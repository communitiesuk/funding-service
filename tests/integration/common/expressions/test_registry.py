from app.common.data.types import QuestionDataType
from app.common.expressions.registry import (
    get_managed_conditions_by_data_type,
    get_managed_validators_by_data_type,
    get_registered_data_types,
    get_supported_form_questions,
)


class TestManagedExpressions:
    def test_get_registered_data_types(self, factories):
        unsupported_question_type = QuestionDataType.TEXT_SINGLE_LINE

        # because we're using a defaultdict we should make sure reading empty values can't change the logic
        assert get_managed_conditions_by_data_type(unsupported_question_type) == []
        assert get_managed_validators_by_data_type(unsupported_question_type) == []
        assert unsupported_question_type not in get_registered_data_types()

    def test_get_supported_form_questions_filters_question_types(self, factories):
        form = factories.form.build()
        factories.question.build_batch(3, data_type=QuestionDataType.TEXT_SINGLE_LINE, form=form)
        only_supported_target = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)
        question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)
        supported_questions = get_supported_form_questions(question)
        assert len(supported_questions) == 1
        assert supported_questions[0].id == only_supported_target.id

    def test_get_supported_form_questions_filters_out_the_current_question(self, factories):
        form = factories.form.build()
        valid_question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        assert get_supported_form_questions(valid_question) == []

        second_question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        # make sure the original question under test does show up in the correct circumstances
        assert get_supported_form_questions(second_question) == [valid_question]
        assert get_supported_form_questions(valid_question) == [second_question]
