from graphlib import CycleError

import pytest

from app.common.collections.types import IntegerAnswer, TextSingleLineAnswer
from app.common.data.models import ComponentReference
from app.common.data.types import (
    ComponentVisibilityState,
    ConditionsOperator,
    ExpressionType,
    QuestionDataType,
)
from app.common.helpers.collections import SubmissionHelper
from app.common.helpers.visibility import CollectionDependencyGraph


class TestComponentDependencyGraph:
    def test_no_dependencies_preserves_form_order(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0)
        q2 = factories.question.build(form=form, order=1)
        q3 = factories.question.build(form=form, order=2)

        graph = CollectionDependencyGraph(form.collection)

        ids = [c.id for c in graph.sorted_components]
        assert ids == [q1.id, q2.id, q3.id]

    def test_linear_chain_dependency_order(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0)
        q2 = factories.question.build(form=form, order=1)
        q3 = factories.question.build(form=form, order=2)

        cond_q2 = factories.expression.build(
            question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} == 'yes'"
        )
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        cond_q3 = factories.expression.build(
            question=q3, type_=ExpressionType.CONDITION, statement=f"{q2.safe_qid} == 'go'"
        )
        q3.owned_component_references = [ComponentReference(component=q3, expression=cond_q3, depends_on_component=q2)]

        graph = CollectionDependencyGraph(form.collection)

        ids = [c.id for c in graph.sorted_components]
        assert ids.index(q1.id) < ids.index(q2.id)
        assert ids.index(q2.id) < ids.index(q3.id)

    def test_parent_child_dependency(self, factories):
        group = factories.group.build()
        q1 = factories.question.build(form=group.form, parent=group, order=0)

        graph = CollectionDependencyGraph(group.form.collection)

        ids = [c.id for c in graph.sorted_components]
        assert ids.index(group.id) < ids.index(q1.id)

    def test_diamond_dependency(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0)
        q2 = factories.question.build(form=form, order=1)
        q3 = factories.question.build(form=form, order=2)
        q4 = factories.question.build(form=form, order=3)

        cond_q2 = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        cond_q3 = factories.expression.build(question=q3, type_=ExpressionType.CONDITION, statement="True")
        q3.owned_component_references = [ComponentReference(component=q3, expression=cond_q3, depends_on_component=q1)]

        cond_q4 = factories.expression.build(question=q4, type_=ExpressionType.CONDITION, statement="True")
        q4.owned_component_references = [
            ComponentReference(component=q4, expression=cond_q4, depends_on_component=q2),
            ComponentReference(component=q4, expression=cond_q4, depends_on_component=q3),
        ]

        graph = CollectionDependencyGraph(form.collection)

        ids = [c.id for c in graph.sorted_components]
        assert ids.index(q1.id) < ids.index(q2.id)
        assert ids.index(q1.id) < ids.index(q3.id)
        assert ids.index(q2.id) < ids.index(q4.id)
        assert ids.index(q3.id) < ids.index(q4.id)

    def test_cycle_raises(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0)
        q2 = factories.question.build(form=form, order=1)

        cond_q1 = factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="True")
        q1.owned_component_references = [ComponentReference(component=q1, expression=cond_q1, depends_on_component=q2)]

        cond_q2 = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        with pytest.raises(CycleError):
            CollectionDependencyGraph(form.collection)

    def test_cross_form_dependencies(self, factories):
        collection = factories.collection.build()
        form1 = factories.form.build(collection=collection, order=0)
        form2 = factories.form.build(collection=collection, order=1)
        q1 = factories.question.build(form=form1, order=0)
        q2 = factories.question.build(form=form2, order=0)

        cond_q2 = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        graph = CollectionDependencyGraph(collection)

        ids = [c.id for c in graph.sorted_components]
        assert ids.index(q1.id) < ids.index(q2.id)

    def test_is_conditional_ignoring_parents(self, factories):
        form = factories.form.build()
        q1, q2, q3 = factories.question.build_batch(3, form=form)
        g1 = factories.group.build(form=form)
        q4, q5 = factories.question.build_batch(2, form=form, parent=g1)

        cond_q2 = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        cond_q3 = factories.expression.build(question=q3, type_=ExpressionType.CONDITION, statement="True")
        q3.owned_component_references = [ComponentReference(component=q3, expression=cond_q3, depends_on_component=q2)]

        cond_g1 = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        g1.owned_component_references = [ComponentReference(component=g1, expression=cond_g1, depends_on_component=q1)]

        cond_q5 = factories.expression.build(question=q5, type_=ExpressionType.CONDITION, statement="True")
        q5.owned_component_references = [ComponentReference(component=q5, expression=cond_q5, depends_on_component=q4)]

        graph = CollectionDependencyGraph(form.collection)

        assert graph.is_conditional_ignoring_parents(q1) is False
        assert graph.is_conditional_ignoring_parents(q2) is True
        assert graph.is_conditional_ignoring_parents(q3) is True
        assert graph.is_conditional_ignoring_parents(g1) is True
        assert graph.is_conditional_ignoring_parents(q4) is False
        assert graph.is_conditional_ignoring_parents(q5) is True


class TestVisibilityResolver:
    def test_no_conditions_all_visible(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0)
        q2 = factories.question.build(form=form, order=1)
        submission = factories.submission.build(collection=form.collection)
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) == ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q2) == ComponentVisibilityState.VISIBLE

    def test_static_false_condition_hidden(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0)
        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")
        submission = factories.submission.build(collection=form.collection)
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) == ComponentVisibilityState.HIDDEN

    def test_chained_hide_propagation(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0, data_type=QuestionDataType.YES_NO)
        q2 = factories.question.build(form=form, order=1)
        q3 = factories.question.build(form=form, order=2)

        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")

        cond_q2 = factories.expression.build(
            question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} == 'yes'"
        )
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        cond_q3 = factories.expression.build(
            question=q3, type_=ExpressionType.CONDITION, statement=f"{q2.safe_qid} == 'go'"
        )
        q3.owned_component_references = [ComponentReference(component=q3, expression=cond_q3, depends_on_component=q2)]

        submission = factories.submission.build(collection=form.collection)
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) == ComponentVisibilityState.HIDDEN
        assert helper.get_component_visibility_state(q2) == ComponentVisibilityState.HIDDEN
        assert helper.get_component_visibility_state(q3) == ComponentVisibilityState.HIDDEN

    def test_undetermined_when_reference_unanswered(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0, data_type=QuestionDataType.YES_NO)
        q2 = factories.question.build(form=form, order=1)

        cond_q2 = factories.expression.build(
            question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} == 'yes'"
        )
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        submission = factories.submission.build(collection=form.collection)
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) == ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q2) == ComponentVisibilityState.UNDETERMINED

    def test_parent_hidden_hides_children(self, factories):
        group = factories.group.build()
        q1 = factories.question.build(form=group.form, parent=group, order=0)

        factories.expression.build(question=group, type_=ExpressionType.CONDITION, statement="False")

        submission = factories.submission.build(collection=group.form.collection)
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(group) == ComponentVisibilityState.HIDDEN
        assert helper.get_component_visibility_state(q1) == ComponentVisibilityState.HIDDEN

    def test_any_operator_one_true_is_visible(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0, conditions_operator=ConditionsOperator.ANY)

        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")
        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="True")

        submission = factories.submission.build(collection=form.collection)
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) == ComponentVisibilityState.VISIBLE

    def test_any_operator_all_false_is_hidden(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0, conditions_operator=ConditionsOperator.ANY)

        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")
        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")

        submission = factories.submission.build(collection=form.collection)
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) == ComponentVisibilityState.HIDDEN

    def test_all_operator_requires_all_true(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0, conditions_operator=ConditionsOperator.ALL)

        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="True")
        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")

        submission = factories.submission.build(collection=form.collection)
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) == ComponentVisibilityState.HIDDEN

    def test_add_another_per_index_visibility(self, factories):
        group = factories.group.build(add_another=True)
        q1 = factories.question.build(form=group.form, parent=group, data_type=QuestionDataType.NUMBER, order=0)
        q2 = factories.question.build(form=group.form, parent=group, order=1)

        cond = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} > 50")
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond, depends_on_component=q1)]

        submission = factories.submission.build(collection=group.form.collection)
        submission.data_manager.set(q1, IntegerAnswer(value=55), add_another_index=0)
        submission.data_manager.set(q1, IntegerAnswer(value=20), add_another_index=1)
        helper = SubmissionHelper(submission)

        assert helper.is_component_visible(q2, add_another_index=0) is True
        assert helper.is_component_visible(q2, add_another_index=1) is False

    def test_hidden_propagation_with_multiple_refs(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0, data_type=QuestionDataType.YES_NO)
        q2 = factories.question.build(form=form, order=1)
        q3 = factories.question.build(form=form, order=2)
        q4 = factories.question.build(form=form, order=3)

        cond_q2 = factories.expression.build(
            question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} is True"
        )
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        factories.expression.build(question=q3, type_=ExpressionType.CONDITION, statement="False")

        q4.owned_component_references = [
            ComponentReference(component=q4, depends_on_component=q2),
            ComponentReference(component=q4, depends_on_component=q3),
        ]

        submission = factories.submission.build(collection=form.collection)
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) == ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q2) == ComponentVisibilityState.UNDETERMINED
        assert helper.get_component_visibility_state(q3) == ComponentVisibilityState.HIDDEN
        assert helper.get_component_visibility_state(q4) == ComponentVisibilityState.HIDDEN

    def test_any_condition_visibility(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0, data_type=QuestionDataType.YES_NO)
        q2 = factories.question.build(form=form, order=1, data_type=QuestionDataType.YES_NO)
        q3 = factories.question.build(form=form, order=1, data_type=QuestionDataType.YES_NO)
        q4 = factories.question.build(
            form=form, order=2, data_type=QuestionDataType.TEXT_SINGLE_LINE, conditions_operator=ConditionsOperator.ANY
        )

        cond_q2 = factories.expression.build(
            question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} is True"
        )
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        cond_q4_q2 = factories.expression.build(
            question=q4, type_=ExpressionType.CONDITION, statement=f"{q2.safe_qid} is True"
        )
        cond_q4_q3 = factories.expression.build(
            question=q4, type_=ExpressionType.CONDITION, statement=f"{q3.safe_qid} is True"
        )
        q4.owned_component_references = [
            ComponentReference(component=q4, expression=cond_q4_q2, depends_on_component=q2),
            ComponentReference(component=q4, expression=cond_q4_q3, depends_on_component=q3),
        ]

        submission = factories.submission.build(collection=form.collection)
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q2) is ComponentVisibilityState.UNDETERMINED
        assert helper.get_component_visibility_state(q3) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q4) is ComponentVisibilityState.UNDETERMINED

        submission = factories.submission.build(collection=form.collection)
        submission.data_manager.set(q1, TextSingleLineAnswer("no"))
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q2) is ComponentVisibilityState.HIDDEN
        assert helper.get_component_visibility_state(q3) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q4) is ComponentVisibilityState.UNDETERMINED

        submission = factories.submission.build(collection=form.collection)
        submission.data_manager.set(q1, TextSingleLineAnswer("no"))
        submission.data_manager.set(q3, TextSingleLineAnswer("yes"))
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q2) is ComponentVisibilityState.HIDDEN
        assert helper.get_component_visibility_state(q3) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q4) is ComponentVisibilityState.VISIBLE

        submission = factories.submission.build(collection=form.collection)
        submission.data_manager.set(q1, TextSingleLineAnswer("no"))
        submission.data_manager.set(q3, TextSingleLineAnswer("yes"))
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q2) is ComponentVisibilityState.HIDDEN
        assert helper.get_component_visibility_state(q3) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q4) is ComponentVisibilityState.VISIBLE

        submission = factories.submission.build(collection=form.collection)
        submission.data_manager.set(q1, TextSingleLineAnswer("no"))
        submission.data_manager.set(q3, TextSingleLineAnswer("no"))
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q2) is ComponentVisibilityState.HIDDEN
        assert helper.get_component_visibility_state(q3) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q4) is ComponentVisibilityState.HIDDEN

        submission = factories.submission.build(collection=form.collection)
        submission.data_manager.set(q1, TextSingleLineAnswer("yes"))
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q2) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q3) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q4) is ComponentVisibilityState.UNDETERMINED

        submission = factories.submission.build(collection=form.collection)
        submission.data_manager.set(q1, TextSingleLineAnswer("yes"))
        submission.data_manager.set(q2, TextSingleLineAnswer("yes"))
        helper = SubmissionHelper(submission)

        assert helper.get_component_visibility_state(q1) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q2) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q3) is ComponentVisibilityState.VISIBLE
        assert helper.get_component_visibility_state(q4) is ComponentVisibilityState.VISIBLE
