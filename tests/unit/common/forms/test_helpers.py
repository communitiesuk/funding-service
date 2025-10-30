import pytest

from app.common.data.interfaces.collections import (
    AddAnotherNotValidException,
    raise_if_add_another_not_valid_here,
)
from app.common.data.types import QuestionPresentationOptions
from app.common.forms.helpers import (
    get_referenceable_questions,
    questions_in_same_add_another_container,
    questions_in_same_page_group,
)


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


class TestQuestionsInSameAddAnotherGroup:
    def test_components_in_same_add_another_group(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, add_another=True)
        q1 = factories.question.build(form=form, parent=group)
        q2 = factories.question.build(form=form, parent=group)
        assert questions_in_same_add_another_container(q1, q2) is True

    def test_components_not_in_add_another_group(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, add_another=False)
        q1 = factories.question.build(form=form, parent=group)
        q2 = factories.question.build(form=form, parent=group)
        q3 = factories.question.build(form=form, parent=None)
        q4 = factories.question.build(form=form, parent=None)

        assert questions_in_same_add_another_container(q1, q2) is False
        assert questions_in_same_add_another_container(q2, q3) is False
        assert questions_in_same_add_another_container(q3, q4) is False

    def test_components_not_in_same_add_another_group(self, factories):
        form = factories.form.build()
        g1 = factories.group.build(form=form, add_another=True)
        g2 = factories.group.build(form=form, add_another=True)
        g3 = factories.group.build(form=form, add_another=False)
        q1 = factories.question.build(form=form, parent=g1)
        q2 = factories.question.build(form=form, parent=g2)
        q3 = factories.question.build(form=form, parent=g3)
        q4 = factories.question.build(form=form, parent=None)

        assert questions_in_same_add_another_container(q1, q2) is False
        assert questions_in_same_add_another_container(q1, q3) is False
        assert questions_in_same_add_another_container(q2, q4) is False
        assert questions_in_same_add_another_container(q3, q4) is False

    def test_components_not_in_same_add_another_group_add_another_question(self, factories):
        form = factories.form.build()
        g1 = factories.group.build(form=form, add_another=False)
        g2 = factories.group.build(form=form, add_another=True)
        q1 = factories.question.build(form=form, parent=g1, add_another=True)
        q2 = factories.question.build(form=form, parent=g2)
        q3 = factories.question.build(form=form, parent=None)

        assert questions_in_same_add_another_container(q1, q2) is False
        assert questions_in_same_add_another_container(q1, q3) is False
        assert questions_in_same_add_another_container(q2, q3) is False


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

    def test_includes_questions_in_group_if_not_same_page_when_creating_questions(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        group = factories.group.build(
            form=form, presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False)
        )
        q2 = factories.question.build(form=form, parent=group)

        referenceable_questions = get_referenceable_questions(form, current_component=None, parent_component=group)

        assert referenceable_questions == [q1, q2]

    def test_filters_out_same_page_question_when_creating_questions(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        group = factories.group.build(
            form=form, presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True)
        )
        factories.question.build(form=form, parent=group)

        referenceable_questions = get_referenceable_questions(form, current_component=None, parent_component=group)

        assert referenceable_questions == [q1]

    def test_filters_out_add_another_question(self, factories):
        form = factories.form.build()
        factories.question.build(form=form, add_another=True)
        q2, q3 = factories.question.build_batch(2, form=form)

        referenceable_questions = get_referenceable_questions(form, current_component=q3)
        assert referenceable_questions == [q2]

        referenceable_questions = get_referenceable_questions(form, current_component=q2)
        assert referenceable_questions == []

    def test_filters_out_add_another_group(self, factories):
        form = factories.form.build()
        g1 = factories.group.build(form=form, add_another=True)
        factories.question.build_batch(3, form=form, parent=g1)
        q4 = factories.question.build(form=form, parent=None)

        referenceable_questions = get_referenceable_questions(form, current_component=q4)
        assert referenceable_questions == []

    def test_filters_out_add_another_in_same_group_that_comes_later(self, factories):
        form = factories.form.build()
        g1 = factories.group.build(form=form, add_another=True)
        q1, q2, q3 = factories.question.build_batch(3, form=form, parent=g1)

        referenceable_questions = get_referenceable_questions(form, current_component=q3)
        assert referenceable_questions == [q1, q2]

        referenceable_questions = get_referenceable_questions(form, current_component=q2)
        assert referenceable_questions == [q1]


class TestAddAnother:
    def test_raise_if_add_another_not_valid_question_in_group(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, add_another=True)
        question = factories.question.build(form=form, parent=group, add_another=True)
        with pytest.raises(AddAnotherNotValidException) as e:
            raise_if_add_another_not_valid_here(question)
        assert e.value.component == question
        assert e.value.add_another_container == group

    def test_raise_if_add_another_not_valid_nested_group(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, add_another=True)
        group2 = factories.group.build(form=form, parent=group, add_another=True)
        with pytest.raises(AddAnotherNotValidException) as e:
            raise_if_add_another_not_valid_here(group2)
        assert e.value.component == group2
        assert e.value.add_another_container == group

    def test_raise_if_add_another_not_valid_question_in_nested_group_immediate_parent_is_add_another(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, add_another=False)
        group2 = factories.group.build(form=form, parent=group, add_another=True)
        question = factories.question.build(form=form, parent=group2, add_another=True)
        with pytest.raises(AddAnotherNotValidException) as e:
            raise_if_add_another_not_valid_here(question)
        assert e.value.component == question
        assert e.value.add_another_container == group2

    def test_raise_if_add_another_not_valid_question_in_nested_group_ancestor_parent_is_add_another(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, add_another=True)
        group2 = factories.group.build(form=form, parent=group, add_another=False)
        question = factories.question.build(form=form, parent=group2, add_another=True)
        with pytest.raises(AddAnotherNotValidException) as e:
            raise_if_add_another_not_valid_here(question)
        assert e.value.component == question
        assert e.value.add_another_container == group

    def test_raise_if_add_another_not_valid_does_not_raise_for_non_add_another_question(self, factories):
        form = factories.form.build()
        question = factories.question.build(form=form, add_another=False)
        raise_if_add_another_not_valid_here(question)

        group = factories.group.build(form=form, add_another=False)
        raise_if_add_another_not_valid_here(group)

    def test_raise_if_add_another_not_valid_does_not_raise_for_non_add_another_group_question(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, add_another=False)
        group2 = factories.group.build(form=form, parent=group, add_another=True)
        question2 = factories.question.build(form=form, parent=group2, add_another=False)
        raise_if_add_another_not_valid_here(question2)
        group3 = factories.group.build(form=form, parent=group2, add_another=False)
        raise_if_add_another_not_valid_here(group3)

    def test_raise_if_add_another_not_valid_does_not_raise_for_non_add_another_nested_group_question(self, factories):
        form = factories.form.build()
        group1 = factories.group.build(form=form, add_another=False)
        group2 = factories.group.build(form=form, parent=group1, add_another=False)
        question1 = factories.question.build(form=form, parent=group2, add_another=False)
        raise_if_add_another_not_valid_here(question1)
        group3 = factories.group.build(form=form, parent=group2, add_another=False)
        raise_if_add_another_not_valid_here(group3)

    def test_raise_if_add_another_not_valid_does_not_raise_for_valid_question(self, factories):
        form = factories.form.build()
        question = factories.question.build(form=form, add_another=True)
        raise_if_add_another_not_valid_here(question)

    def test_raise_if_add_another_not_valid_does_not_raise_for_valid_question_in_group(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form)
        question = factories.question.build(form=form, parent=group, add_another=True)
        raise_if_add_another_not_valid_here(question)

    def test_raise_if_add_another_not_valid_does_not_raise_for_valid_question_in_nested_group(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form)
        group2 = factories.group.build(form=form, parent=group)
        question = factories.question.build(form=form, parent=group2, add_another=True)
        raise_if_add_another_not_valid_here(question)

    def test_raise_if_add_another_not_valid_does_not_raise_for_valid_group(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, add_another=True)
        raise_if_add_another_not_valid_here(group)

    def test_raise_if_add_another_not_valid_does_not_raise_for_valid_nested_group(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form)
        group2 = factories.group.build(form=form, parent=group, add_another=True)
        raise_if_add_another_not_valid_here(group2)
