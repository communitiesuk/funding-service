from app.common.data.types import QuestionDataType
from app.common.expressions.registry import get_supported_form_questions


class TestManagedExpressions:
    def test_get_supported_form_questions_filters_question_types(self, factories):
        form = factories.form.build()
        supported_text_target = factories.question.build(data_type=QuestionDataType.TEXT_SINGLE_LINE, form=form)
        factories.question.build(data_type=QuestionDataType.TEXT_MULTI_LINE, form=form)
        supported_integer_target = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)
        question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        supported_questions = get_supported_form_questions(question)
        assert len(supported_questions) == 2
        assert any(sq.id == supported_text_target.id for sq in supported_questions)
        assert any(sq.id == supported_integer_target.id for sq in supported_questions)

    def test_get_supported_form_questions_filters_out_the_current_question(self, factories):
        form = factories.form.build()
        valid_question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        assert get_supported_form_questions(valid_question) == []

        second_question = factories.question.build(data_type=QuestionDataType.INTEGER, form=form)

        # make sure the original question under test does show up in the correct circumstances
        assert get_supported_form_questions(second_question) == [valid_question]
        assert get_supported_form_questions(valid_question) == [second_question]
