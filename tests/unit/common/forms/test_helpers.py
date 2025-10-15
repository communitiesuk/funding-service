from app.common.data.types import QuestionPresentationOptions
from app.common.forms.helpers import get_referenceable_questions, questions_in_same_page_group


class TestQuestionsInSamePageGroup:
    def test_components_not_in_any_group(self, factories):
        form = factories.form.build()
        q1, q2 = factories.question.build_batch(2, form=form, parent=None)
        assert questions_in_same_page_group(q1, q2) is False

    def test_only_one_parent_component(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form)
        q1 = factories.question.build(form=form, parent=None)
        q2 = factories.question.build(form=form, parent=group)

        assert questions_in_same_page_group(q1, q2) is False

    def test_components_in_different_groups(self, factories):
        form = factories.form.build()
        group1 = factories.group.build(form=form)
        group2 = factories.group.build(form=form)
        q1 = factories.question.build(form=form, parent=group1)
        q2 = factories.question.build(form=form, parent=group2)

        assert questions_in_same_page_group(q1, q2) is False

    def test_components_in_same_group_same_page(self, factories):
        form = factories.form.build()
        group = factories.group.build(
            form=form, presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True)
        )
        q1 = factories.question.build(form=form, parent=group)
        q2 = factories.question.build(form=form, parent=group)

        assert questions_in_same_page_group(q1, q2) is True


class TestGetReferenceableQuestions:
    def test_no_current_component_returns_all_questions(self, factories):
        form = factories.form.build()
        questions = factories.question.build_batch(3, form=form)

        assert get_referenceable_questions(form, current_component=None) == questions

    def test_single_question_returns_empty_list(self, factories):
        """Test that a form with no questions returns empty list"""
        form = factories.form.build()
        current_question = factories.question.build(form=form)

        assert get_referenceable_questions(form, current_component=current_question) == []

    def test_filters_out_questions_that_come_after_current_component(self, factories):
        form = factories.form.build()
        q1, q2, q3 = factories.question.build_batch(3, form=form)

        referenceable_questions = get_referenceable_questions(form, current_component=q2)

        assert referenceable_questions == [q1]

    def test_filters_out_questions_in_same_page_group(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        group = factories.group.build(
            form=form, presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True)
        )
        factories.question.build(form=form, parent=group)
        q3 = factories.question.build(form=form, parent=group)

        referenceable_questions = get_referenceable_questions(form, current_component=q3)

        assert referenceable_questions == [q1]
