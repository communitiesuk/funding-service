import pytest

from app import QuestionDataType
from app.common.data.types import ExpressionType, QuestionPresentationOptions, SubmissionModeEnum


class TestSubmissionModel:
    def test_test_submission_property_only_includes_test_submissions(self, factories):
        # what a test name
        collection = factories.collection.create()
        test_submission = factories.submission.create(collection=collection, mode=SubmissionModeEnum.TEST)
        live_submission = factories.submission.create(collection=collection, mode=SubmissionModeEnum.LIVE)

        assert collection.test_submissions == [test_submission]
        assert collection.live_submissions == [live_submission]


class TestQuestionModel:
    def test_question_property_selects_expressions(self, factories):
        question = factories.question.create()
        condition_expression = factories.expression.create(
            question=question, type_=ExpressionType.CONDITION, statement=""
        )
        validation_expression = factories.expression.create(
            question=question, type_=ExpressionType.VALIDATION, statement=""
        )
        assert question.conditions == [condition_expression]
        assert question.validations == [validation_expression]

    def test_question_gets_a_valid_expression_that_belongs_to_it(self, factories):
        question = factories.question.create()
        expression = factories.expression.create(question=question, type_=ExpressionType.CONDITION, statement="")
        assert question.get_expression(expression.id) == expression

    def test_question_does_not_get_a_valid_expression_that_does_not_belong_to_it(self, factories):
        question = factories.question.create()
        expression_on_other_question = factories.expression.create(type_=ExpressionType.CONDITION, statement="")

        with pytest.raises(ValueError) as e:
            question.get_expression(expression_on_other_question.id)

        assert (
            str(e.value)
            == f"Could not find an expression with id={expression_on_other_question.id} in question={question.id}"
        )

    def test_data_source_items(self, factories):
        factories.data_source_item.reset_sequence()
        question = factories.question.create(
            data_type=QuestionDataType.RADIOS,
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=False),
        )
        other_question = factories.question.create(data_type=QuestionDataType.TEXT_MULTI_LINE)

        assert question.data_source_items == "Option 0\nOption 1\nOption 2"
        assert other_question.data_source_items is None

        assert question.separate_option_if_no_items_match is False
        assert other_question.separate_option_if_no_items_match is None
        assert question.none_of_the_above_item_text == "Other"
        assert other_question.none_of_the_above_item_text is None

    def test_data_source_items_last_item_is_distinct(self, factories):
        factories.data_source_item.reset_sequence()
        question = factories.question.create(
            data_type=QuestionDataType.RADIOS,
            presentation_options=QuestionPresentationOptions(last_data_source_item_is_distinct_from_others=True),
        )
        assert question.data_source_items == "Option 0\nOption 1"
        assert question.separate_option_if_no_items_match is True
        assert question.none_of_the_above_item_text == "Option 2"


class TestFormModel:
    def test_questions_property_filters_nested_questions(self, factories):
        form = factories.form.create()
        # asserting to a depth of 2
        question1 = factories.question.create(form=form, order=0)
        question2 = factories.question.create(form=form, order=1)
        group = factories.group.create(form=form, order=2)
        question3 = factories.question.create(form_id=form.id, parent=group, order=0)
        sub_group = factories.group.create(form_id=form.id, parent=group, order=1)
        question4 = factories.question.create(form_id=form.id, parent=sub_group, order=0)

        assert form.cached_questions == [question1, question2, question3, question4]


class TestGroupModel:
    def test_questions_property_filters_nested_questions(self, factories):
        form = factories.form.create()
        _question1 = factories.question.create(form=form, order=0)
        group = factories.group.create(form_id=form.id, order=1)
        question2 = factories.question.create(form_id=group.form_id, parent=group, order=0)
        question3 = factories.question.create(form_id=group.form_id, parent=group, order=1)
        sub_group = factories.group.create(form_id=group.form_id, parent=group, order=2)
        question4 = factories.question.create(form_id=group.form_id, parent=sub_group, order=0)

        assert group.cached_questions == [question2, question3, question4]
        assert sub_group.cached_questions == [question4]

    @pytest.mark.parametrize("show_questions_on_the_same_page", [True, False])
    def test_same_page_property(self, factories, show_questions_on_the_same_page):
        form = factories.form.create()
        group = factories.group.create(
            form_id=form.id,
            presentation_options=QuestionPresentationOptions(
                show_questions_on_the_same_page=show_questions_on_the_same_page
            ),
        )

        assert group.same_page is show_questions_on_the_same_page
