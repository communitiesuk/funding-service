import uuid
from graphlib import CycleError
from typing import TYPE_CHECKING

import pytest

from app.common.collections.types import IntegerAnswer, YesNoAnswer
from app.common.data.models import ComponentReference
from app.common.data.types import (
    ComponentVisibilityState,
    ConditionsOperator,
    ExpressionType,
    QuestionDataType,
)
from app.common.helpers.collections import SubmissionHelper
from app.common.helpers.visibility import CollectionDependencyGraph, VisibilityResolver
from tests.models import FactoryAnswer

if TYPE_CHECKING:
    from app.common.data.models import Submission


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

    def test_group_validation_referencing_child_is_not_a_dependency(self, factories):
        group = factories.group.build()
        q1 = factories.question.build(form=group.form, parent=group, order=0)

        group_validation = factories.expression.build(
            question=group, type_=ExpressionType.VALIDATION, statement=f"{q1.safe_qid} > 0"
        )
        group.owned_component_references = [
            ComponentReference(component=group, expression=group_validation, depends_on_component=q1)
        ]

        graph = CollectionDependencyGraph(group.form.collection)

        ids = [c.id for c in graph.sorted_components]
        assert ids.index(group.id) < ids.index(q1.id)
        assert q1.id not in graph.dependencies_of(group)

    def test_is_conditional_ignoring_parents(self, factories):
        form = factories.form.build()
        q1, q2, q3 = factories.question.build_batch(3, form=form)
        g1 = factories.group.build(form=form)
        q4, q5 = factories.question.build_batch(2, form=form, parent=g1)

        cond_q2 = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        cond_q3 = factories.expression.build(question=q3, type_=ExpressionType.CONDITION, statement="True")
        q3.owned_component_references = [ComponentReference(component=q3, expression=cond_q3, depends_on_component=q2)]

        cond_g1 = factories.expression.build(question=g1, type_=ExpressionType.CONDITION, statement="True")
        g1.owned_component_references = [ComponentReference(component=g1, expression=cond_g1, depends_on_component=q2)]

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
    @staticmethod
    def _get_resolver(submission: "Submission") -> VisibilityResolver:
        dependency_graph = CollectionDependencyGraph(submission.collection)
        helper = SubmissionHelper(submission)
        context = helper.cached_evaluation_context
        data_manager = submission.data_manager
        resolver = VisibilityResolver(dependency_graph, context, data_manager)
        return resolver

    def test_no_conditions_all_visible(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0)
        q2 = factories.question.build(form=form, order=1)
        submission = factories.submission.build(collection=form.collection)
        resolver = TestVisibilityResolver._get_resolver(submission)

        assert resolver.is_visible(q1) is True
        assert resolver.is_visible(q2) is True
        assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q2) == ComponentVisibilityState.VISIBLE

    def test_static_false_condition_hidden(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0)
        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")
        submission = factories.submission.build(collection=form.collection)
        resolver = TestVisibilityResolver._get_resolver(submission)

        assert resolver.is_visible(q1) is False
        assert resolver.get_visibility(q1) == ComponentVisibilityState.HIDDEN

    def test_static_true_condition_visible(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0)
        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="True")
        submission = factories.submission.build(collection=form.collection)
        resolver = TestVisibilityResolver._get_resolver(submission)

        assert resolver.is_visible(q1) is True
        assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE

    def test_undetermined_when_reference_unanswered(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0, data_type=QuestionDataType.YES_NO)
        q2 = factories.question.build(form=form, order=1)

        cond_q2 = factories.expression.build(
            question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} == 'yes'"
        )
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        submission = factories.submission.build(collection=form.collection)
        resolver = TestVisibilityResolver._get_resolver(submission)

        assert resolver.is_visible(q1) is True
        assert resolver.is_visible(q2) is False
        assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q2) == ComponentVisibilityState.UNDETERMINED

    def test_parent_hidden_hides_children(self, factories):
        group = factories.group.build()
        q1 = factories.question.build(form=group.form, parent=group, order=0)

        factories.expression.build(question=group, type_=ExpressionType.CONDITION, statement="False")

        submission = factories.submission.build(collection=group.form.collection)
        resolver = TestVisibilityResolver._get_resolver(submission)

        assert resolver.is_visible(group) is False
        assert resolver.is_visible(q1) is False
        assert resolver.get_visibility(group) == ComponentVisibilityState.HIDDEN
        assert resolver.get_visibility(q1) == ComponentVisibilityState.HIDDEN

    class TestNonConditionReferences:
        def test_is_component_visible_doesnt_understand_references_to_groups(self, factories):
            group = factories.group.build()
            q1 = factories.question.build(form=group.form)
            q1.owned_component_references = [ComponentReference(component=q1, depends_on_component=group)]
            submission = factories.submission.build(collection=group.form.collection)

            with pytest.raises(RuntimeError, match="Components can only depend on questions"):
                TestVisibilityResolver._get_resolver(submission)

        def test_is_component_visible_ignores_self_references(self, factories):
            q1 = factories.question.build()
            q1.owned_component_references = [ComponentReference(component=q1, depends_on_component=q1)]
            submission = factories.submission.build(collection=q1.form.collection)
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is True
            assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE

        def test_is_component_visible_ignores_data_source_column_references(self, factories):
            q1 = factories.question.build()
            q1.owned_component_references = [
                ComponentReference(component=q1, depends_on_data_source_id=uuid.uuid4(), depends_on_column_name="c_x")
            ]
            submission = factories.submission.build(collection=q1.form.collection)
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is True
            assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE

    class TestConditionsOperator:
        def test_any_operator_one_true_is_visible(self, factories):
            form = factories.form.build()
            q1 = factories.question.build(form=form, order=0, conditions_operator=ConditionsOperator.ANY)

            factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")
            factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="True")

            submission = factories.submission.build(collection=form.collection)
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is True
            assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE

        def test_any_operator_all_false_is_hidden(self, factories):
            form = factories.form.build()
            q1 = factories.question.build(form=form, order=0, conditions_operator=ConditionsOperator.ANY)

            factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")
            factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")

            submission = factories.submission.build(collection=form.collection)
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is False
            assert resolver.get_visibility(q1) == ComponentVisibilityState.HIDDEN

        def test_all_operator_requires_all_true(self, factories):
            form = factories.form.build()
            q1 = factories.question.build(form=form, order=0, conditions_operator=ConditionsOperator.ALL)

            factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="True")
            factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")

            submission = factories.submission.build(collection=form.collection)
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is False
            assert resolver.get_visibility(q1) == ComponentVisibilityState.HIDDEN

        def test_is_component_visible_with_nested_groups_different_operators(self, factories):
            group = factories.group.build(conditions_operator=ConditionsOperator.ANY)
            question = factories.question.build(
                form=group.form, parent=group, conditions_operator=ConditionsOperator.ALL
            )

            # Group has ANY operator with one True and one False condition
            factories.expression.build(question=group, type_=ExpressionType.CONDITION, statement="True")
            factories.expression.build(question=group, type_=ExpressionType.CONDITION, statement="False")

            # Question has ALL operator with all True conditions
            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="True")
            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="True")

            submission = factories.submission.build(collection=group.form.collection)
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(group) is True
            assert resolver.is_visible(question) is True
            assert resolver.get_visibility(group) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(question) is ComponentVisibilityState.VISIBLE

        def test_is_component_visible_child_hidden_when_parent_hidden_regardless_of_operator(self, factories):
            group = factories.group.build(conditions_operator=ConditionsOperator.ALL)
            question = factories.question.build(
                form=group.form, parent=group, conditions_operator=ConditionsOperator.ANY
            )

            # Group has ALL operator with one False condition (so hidden)
            factories.expression.build(question=group, type_=ExpressionType.CONDITION, statement="False")

            # Question has ANY operator with one True condition
            factories.expression.build(question=question, type_=ExpressionType.CONDITION, statement="True")

            submission = factories.submission.build(collection=group.form.collection)
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(group) is False
            assert resolver.is_visible(question) is False
            assert resolver.get_visibility(group) is ComponentVisibilityState.HIDDEN
            assert resolver.get_visibility(question) is ComponentVisibilityState.HIDDEN

        def test_any_condition_visibility(self, factories):
            form = factories.form.build()
            q1 = factories.question.build(form=form, order=0, data_type=QuestionDataType.YES_NO)
            q2 = factories.question.build(form=form, order=1, data_type=QuestionDataType.YES_NO)
            q3 = factories.question.build(form=form, order=1, data_type=QuestionDataType.YES_NO)
            q4 = factories.question.build(
                form=form,
                order=2,
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                conditions_operator=ConditionsOperator.ANY,
            )

            cond_q2 = factories.expression.build(
                question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} is True"
            )
            q2.owned_component_references = [
                ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)
            ]

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
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is True
            assert resolver.is_visible(q2) is False
            assert resolver.is_visible(q3) is True
            assert resolver.is_visible(q4) is False
            assert resolver.get_visibility(q1) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q2) is ComponentVisibilityState.UNDETERMINED
            assert resolver.get_visibility(q3) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q4) is ComponentVisibilityState.UNDETERMINED

            submission = factories.submission.build(
                collection=form.collection, answers=[FactoryAnswer(q1, YesNoAnswer(False))]
            )
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is True
            assert resolver.is_visible(q2) is False
            assert resolver.is_visible(q3) is True
            assert resolver.is_visible(q4) is False
            assert resolver.get_visibility(q1) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q2) is ComponentVisibilityState.HIDDEN
            assert resolver.get_visibility(q3) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q4) is ComponentVisibilityState.UNDETERMINED

            submission = factories.submission.build(
                collection=form.collection,
                answers=[FactoryAnswer(q1, YesNoAnswer(False)), FactoryAnswer(q3, YesNoAnswer(True))],
            )
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is True
            assert resolver.is_visible(q2) is False
            assert resolver.is_visible(q3) is True
            assert resolver.is_visible(q4) is True
            assert resolver.get_visibility(q1) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q2) is ComponentVisibilityState.HIDDEN
            assert resolver.get_visibility(q3) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q4) is ComponentVisibilityState.VISIBLE

            submission = factories.submission.build(
                collection=form.collection,
                answers=[FactoryAnswer(q1, YesNoAnswer(False)), FactoryAnswer(q3, YesNoAnswer(True))],
            )
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is True
            assert resolver.is_visible(q2) is False
            assert resolver.is_visible(q3) is True
            assert resolver.is_visible(q4) is True
            assert resolver.get_visibility(q1) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q2) is ComponentVisibilityState.HIDDEN
            assert resolver.get_visibility(q3) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q4) is ComponentVisibilityState.VISIBLE

            submission = factories.submission.build(
                collection=form.collection,
                answers=[FactoryAnswer(q1, YesNoAnswer(False)), FactoryAnswer(q3, YesNoAnswer(False))],
            )
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is True
            assert resolver.is_visible(q2) is False
            assert resolver.is_visible(q3) is True
            assert resolver.is_visible(q4) is False
            assert resolver.get_visibility(q1) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q2) is ComponentVisibilityState.HIDDEN
            assert resolver.get_visibility(q3) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q4) is ComponentVisibilityState.HIDDEN

            submission = factories.submission.build(
                collection=form.collection,
                answers=[FactoryAnswer(q1, YesNoAnswer(True))],
            )
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is True
            assert resolver.is_visible(q2) is True
            assert resolver.is_visible(q3) is True
            assert resolver.is_visible(q4) is False
            assert resolver.get_visibility(q1) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q2) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q3) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q4) is ComponentVisibilityState.UNDETERMINED

            submission = factories.submission.build(
                collection=form.collection,
                answers=[
                    FactoryAnswer(q1, YesNoAnswer(True)),
                    FactoryAnswer(q2, YesNoAnswer(True)),
                ],
            )
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q1) is True
            assert resolver.is_visible(q2) is True
            assert resolver.is_visible(q3) is True
            assert resolver.is_visible(q4) is True
            assert resolver.get_visibility(q1) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q2) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q3) is ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility(q4) is ComponentVisibilityState.VISIBLE

    class TestAddAnother:
        def test_add_another_per_index_visibility(self, factories):
            group = factories.group.build(add_another=True)
            q1 = factories.question.build(form=group.form, parent=group, data_type=QuestionDataType.NUMBER, order=0)
            q2 = factories.question.build(form=group.form, parent=group, order=1)

            cond = factories.expression.build(
                question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} > 50"
            )
            q2.owned_component_references = [ComponentReference(component=q2, expression=cond, depends_on_component=q1)]

            submission = factories.submission.build(collection=group.form.collection)
            submission.data_manager.set(q1, IntegerAnswer(value=55), add_another_index=0)
            submission.data_manager.set(q1, IntegerAnswer(value=20), add_another_index=1)
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q2, add_another_index=0) is True
            assert resolver.is_visible(q2, add_another_index=1) is False
            assert resolver.get_visibility_for_add_another(q2, add_another_index=0) == ComponentVisibilityState.VISIBLE
            assert resolver.get_visibility_for_add_another(q2, add_another_index=1) == ComponentVisibilityState.HIDDEN

        def test_nested_group_condition_inside_add_another(self, factories):
            outer = factories.group.build(add_another=True)
            show_nested = factories.question.build(
                form=outer.form, parent=outer, order=0, data_type=QuestionDataType.YES_NO
            )
            nested = factories.group.build(form=outer.form, parent=outer, order=1)
            q_nested = factories.question.build(form=outer.form, parent=nested, order=0)

            cond = factories.expression.build(
                question=nested, type_=ExpressionType.CONDITION, statement=f"{show_nested.safe_qid} is True"
            )
            nested.owned_component_references = [
                ComponentReference(component=nested, expression=cond, depends_on_component=show_nested)
            ]

            submission = factories.submission.build(collection=outer.form.collection)
            submission.data_manager.set(show_nested, YesNoAnswer(True), add_another_index=0)
            submission.data_manager.set(show_nested, YesNoAnswer(False), add_another_index=1)
            resolver = TestVisibilityResolver._get_resolver(submission)

            assert resolver.is_visible(q_nested, add_another_index=0) is True
            assert resolver.is_visible(q_nested, add_another_index=1) is False
            assert (
                resolver.get_visibility_for_add_another(q_nested, add_another_index=0)
                == ComponentVisibilityState.VISIBLE
            )
            assert (
                resolver.get_visibility_for_add_another(q_nested, add_another_index=1)
                == ComponentVisibilityState.HIDDEN
            )

    def test_chained_hide_propagation(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0, data_type=QuestionDataType.YES_NO)
        q2 = factories.question.build(form=form, order=1)
        q3 = factories.question.build(form=form, order=2)

        factories.expression.build(question=q1, type_=ExpressionType.CONDITION, statement="False")

        cond_q2 = factories.expression.build(
            question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} is True"
        )
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]

        cond_q3 = factories.expression.build(
            question=q3, type_=ExpressionType.CONDITION, statement=f"{q2.safe_qid} == 'go'"
        )
        q3.owned_component_references = [ComponentReference(component=q3, expression=cond_q3, depends_on_component=q2)]

        submission = factories.submission.build(collection=form.collection)
        resolver = TestVisibilityResolver._get_resolver(submission)
        assert resolver.is_visible(q1) is False
        assert resolver.is_visible(q2) is False
        assert resolver.is_visible(q3) is False
        assert resolver.get_visibility(q1) == ComponentVisibilityState.HIDDEN
        assert resolver.get_visibility(q2) == ComponentVisibilityState.HIDDEN
        assert resolver.get_visibility(q3) == ComponentVisibilityState.HIDDEN

    def test_nested_hide_propagation(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=0, data_type=QuestionDataType.YES_NO)
        group = factories.group.build(form=form, order=1)
        cond_group = factories.expression.build(
            question=group, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} is True"
        )
        group.owned_component_references = [
            ComponentReference(component=group, expression=cond_group, depends_on_component=q1)
        ]
        q2 = factories.question.build(form=form, parent=group, order=0, data_type=QuestionDataType.YES_NO)
        subgroup = factories.group.build(form=form, parent=group, order=1)
        cond_subgroup = factories.expression.build(
            question=subgroup, type_=ExpressionType.CONDITION, statement=f"{q2.safe_qid} is True"
        )
        subgroup.owned_component_references = [
            ComponentReference(component=subgroup, expression=cond_subgroup, depends_on_component=q2)
        ]
        q3 = factories.question.build(form=form, parent=subgroup, order=0)

        submission = factories.submission.build(collection=form.collection)
        resolver = TestVisibilityResolver._get_resolver(submission)
        assert resolver.is_visible(q1) is True
        assert resolver.is_visible(q2) is False
        assert resolver.is_visible(q3) is False
        assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q2) == ComponentVisibilityState.UNDETERMINED
        assert resolver.get_visibility(q3) == ComponentVisibilityState.UNDETERMINED

        submission = factories.submission.build(
            collection=form.collection, answers=[FactoryAnswer(q1, YesNoAnswer(True))]
        )
        resolver = TestVisibilityResolver._get_resolver(submission)
        assert resolver.is_visible(q1) is True
        assert resolver.is_visible(q2) is True
        assert resolver.is_visible(q3) is False
        assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q2) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q3) == ComponentVisibilityState.UNDETERMINED

        submission = factories.submission.build(
            collection=form.collection, answers=[FactoryAnswer(q1, YesNoAnswer(False))]
        )
        resolver = TestVisibilityResolver._get_resolver(submission)
        assert resolver.is_visible(q1) is True
        assert resolver.is_visible(q2) is False
        assert resolver.is_visible(q3) is False
        assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q2) == ComponentVisibilityState.HIDDEN
        assert resolver.get_visibility(q3) == ComponentVisibilityState.HIDDEN

        submission = factories.submission.build(
            collection=form.collection,
            answers=[FactoryAnswer(q1, YesNoAnswer(True)), FactoryAnswer(q2, YesNoAnswer(True))],
        )
        resolver = TestVisibilityResolver._get_resolver(submission)
        assert resolver.is_visible(q1) is True
        assert resolver.is_visible(q2) is True
        assert resolver.is_visible(q3) is True
        assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q2) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q3) == ComponentVisibilityState.VISIBLE

    def test_group_validation_referencing_child_does_not_affect_visibility(self, factories):
        group = factories.group.build()
        q1 = factories.question.build(form=group.form, parent=group, order=0, data_type=QuestionDataType.NUMBER)

        group_validation = factories.expression.build(
            question=group, type_=ExpressionType.VALIDATION, statement=f"{q1.safe_qid} > 0"
        )
        group.owned_component_references = [
            ComponentReference(component=group, expression=group_validation, depends_on_component=q1)
        ]

        submission = factories.submission.build(collection=group.form.collection)
        resolver = TestVisibilityResolver._get_resolver(submission)

        assert resolver.is_visible(group) is True
        assert resolver.is_visible(q1) is True
        assert resolver.get_visibility(group) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE

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
        resolver = TestVisibilityResolver._get_resolver(submission)

        assert resolver.get_visibility(q1) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q2) == ComponentVisibilityState.UNDETERMINED
        assert resolver.get_visibility(q3) == ComponentVisibilityState.HIDDEN
        assert resolver.get_visibility(q4) == ComponentVisibilityState.HIDDEN

    def test_any_operator_with_hidden_referenced_question(self, factories):
        """Scenario: Q1 yes/no, Q2 yes/no (show if Q1=yes), Q3 text (show if Q1=no OR Q2=yes).

        When Q1="no": Q2 is hidden (its condition Q1=="yes" fails). Q3 should be VISIBLE
        because ANY only needs one condition — Q1=="no" is True.
        When Q1="yes", Q2 unanswered: Q3 should be UNDETERMINED (Q1=="no" is False, Q2=="yes"
        can't be evaluated yet).
        When Q1="yes", Q2="yes": Q3 should be VISIBLE (Q2=="yes" passes).
        When Q1="yes", Q2="no": Q3 should be HIDDEN (both conditions fail).
        """
        q1 = factories.question.build(order=0, data_type=QuestionDataType.YES_NO)
        q2 = factories.question.build(form=q1.form, order=1, data_type=QuestionDataType.YES_NO)
        q2_expr1 = factories.expression.build(
            question=q2, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} is True"
        )
        q2.owned_component_references = [ComponentReference(component=q2, depends_on_component=q1, expression=q2_expr1)]

        q3 = factories.question.build(form=q1.form, order=2, conditions_operator=ConditionsOperator.ANY)
        q3_expr1 = factories.expression.build(
            question=q3, type_=ExpressionType.CONDITION, statement=f"{q1.safe_qid} is False"
        )
        q3_expr2 = factories.expression.build(
            question=q3, type_=ExpressionType.CONDITION, statement=f"{q2.safe_qid} is True"
        )
        q3.owned_component_references = [
            ComponentReference(component=q3, depends_on_component=q1, expression=q3_expr1),
            ComponentReference(component=q3, depends_on_component=q2, expression=q3_expr2),
        ]

        # Case 1: Q1="no" → Q2 hidden, Q3 visible (Q1=="no" is True)
        submission = factories.submission.build(
            collection=q1.form.collection, answers=[FactoryAnswer(q1, YesNoAnswer(False))]
        )
        resolver = TestVisibilityResolver._get_resolver(submission)
        assert resolver.is_visible(q2) is False
        assert resolver.is_visible(q3) is True
        assert resolver.get_visibility(q2) == ComponentVisibilityState.HIDDEN
        assert resolver.get_visibility(q3) == ComponentVisibilityState.VISIBLE

        # Case 2: Q1="yes", Q2 not answered → Q3 undetermined
        submission = factories.submission.build(
            collection=q1.form.collection, answers=[FactoryAnswer(q1, YesNoAnswer(True))]
        )
        resolver = TestVisibilityResolver._get_resolver(submission)
        assert resolver.is_visible(q2) is True
        assert resolver.is_visible(q3) is False
        assert resolver.get_visibility(q2) == ComponentVisibilityState.VISIBLE
        assert resolver.get_visibility(q3) == ComponentVisibilityState.UNDETERMINED

        # Case 3: Q1="yes", Q2="yes" → Q3 visible
        submission = factories.submission.build(
            collection=q1.form.collection,
            answers=[
                FactoryAnswer(q1, YesNoAnswer(True)),
                FactoryAnswer(q2, YesNoAnswer(True)),
            ],
        )
        resolver = TestVisibilityResolver._get_resolver(submission)
        assert resolver.is_visible(q3) is True
        assert resolver.get_visibility(q3) == ComponentVisibilityState.VISIBLE

        # Case 4: Q1="yes", Q2="no" → Q3 hidden
        submission = factories.submission.build(
            collection=q1.form.collection,
            answers=[FactoryAnswer(q1, YesNoAnswer(True)), FactoryAnswer(q2, YesNoAnswer(False))],
        )
        resolver = TestVisibilityResolver._get_resolver(submission)
        assert resolver.is_visible(q3) is False
        assert resolver.get_visibility(q3) == ComponentVisibilityState.HIDDEN
