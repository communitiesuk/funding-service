from datetime import date

from app import CollectionStatusEnum
from app.common.data.models import ComponentReference, get_ordered_nested_components
from app.common.data.types import ExpressionType


class TestNestedComponents:
    def test_get_components_empty(self):
        assert get_ordered_nested_components([]) == []

    def test_get_components_flat(self, factories):
        form = factories.form.build()
        questions = factories.question.build_batch(3, form=form)
        assert get_ordered_nested_components(form.components) == questions

    def test_get_components_nested(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        group = factories.group.build(form=form)
        nested_questions = factories.question.build_batch(3, parent=group)
        g2 = factories.group.build(parent=group)
        nested_questions2 = factories.question.build_batch(3, parent=g2)
        q2 = factories.question.build(form=form)

        assert get_ordered_nested_components(form.components) == [
            q1,
            group,
            *nested_questions,
            g2,
            *nested_questions2,
            q2,
        ]

    def test_get_components_filters_nested(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        group = factories.group.build(form=form)
        nested_questions = factories.question.build_batch(3, parent=group)
        g2 = factories.group.build(parent=group)
        nested_questions2 = factories.question.build_batch(3, parent=g2)
        q2 = factories.question.build(form=form)

        assert form.cached_questions == [q1, *nested_questions, *nested_questions2, q2]
        assert group.cached_questions == [*nested_questions, *nested_questions2]

    def test_get_components_nested_orders(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=2)
        group = factories.group.build(form=form, order=0)
        nested_q = factories.question.build(parent=group, order=0)
        q2 = factories.question.build(form=form, order=1)

        assert get_ordered_nested_components(form.components) == [group, nested_q, q2, q1]
        assert form.cached_questions == [nested_q, q2, q1]

    def test_get_components_nested_depth_5(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        group1 = factories.group.build(form=form)
        group2 = factories.group.build(parent=group1)
        group3 = factories.group.build(parent=group2)
        group4 = factories.group.build(parent=group3)
        group5 = factories.group.build(parent=group4)
        nested_q = factories.question.build(parent=group5)
        q2 = factories.question.build(form=form)

        assert get_ordered_nested_components(form.components) == [
            q1,
            group1,
            group2,
            group3,
            group4,
            group5,
            nested_q,
            q2,
        ]
        assert form.cached_questions == [q1, nested_q, q2]


class TestAddAnother:
    def test_add_another_false(self, factories):
        question = factories.question.build()
        assert question.add_another is False

    def test_add_another_true(self, factories):
        question = factories.question.build(add_another=True)
        assert question.add_another is True

    def test_no_add_another_container(self, factories):
        form = factories.form.build()
        question1 = factories.question.build(form=form)

        assert question1.add_another is False
        assert question1.add_another_container is None

        group1 = factories.group.build(form=form)
        question2 = factories.question.build(parent=group1)
        assert question2.add_another is False
        assert question2.add_another_container is None
        assert group1.add_another is False
        assert group1.add_another_container is None

        group2 = factories.group.build(parent=group1)
        question3 = factories.question.build(parent=group2)
        assert question3.add_another is False
        assert question3.add_another_container is None
        assert group2.add_another is False
        assert group2.add_another_container is None

    def test_add_another_container_is_self(self, factories):
        form = factories.form.build()
        question = factories.question.build(form=form, add_another=True)

        assert question.add_another_container == question

    def test_add_another_container_is_immediate_group_parent(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, add_another=True)
        question = factories.question.build(parent=group)

        assert question.add_another is False
        assert group.add_another is True
        assert question.add_another_container == group
        assert group.add_another_container == group

    def test_add_another_container_is_ancestor_group(self, factories):
        form = factories.form.build()
        group1 = factories.group.build(form=form, add_another=True)
        group2 = factories.group.build(parent=group1)
        question = factories.question.build(parent=group2)

        assert question.add_another is False
        assert group1.add_another is True
        assert group2.add_another is False
        assert question.add_another_container == group1
        assert group2.add_another_container == group1
        assert group1.add_another_container == group1


class TestGrantAccessReports:
    def test_access_reports(self, factories):
        grant = factories.grant.build()
        report1 = factories.collection.build(grant=grant, status=CollectionStatusEnum.OPEN)
        report2 = factories.collection.build(grant=grant, status=CollectionStatusEnum.CLOSED)
        _ = factories.collection.build(grant=grant, status=CollectionStatusEnum.DRAFT)

        result = grant.access_reports
        assert len(result) == 2
        assert result[0].id == report1.id
        assert result[1].id == report2.id

    def test_get_access_reports_no_collections(self, db_session, factories):
        grant = factories.grant.build()

        results_grant_has_no_collections = grant.access_reports
        assert len(results_grant_has_no_collections) == 0

    def test_get_access_reports_wrong_state(self, factories):
        grant = factories.grant.build()
        factories.collection.build(grant=grant, status=CollectionStatusEnum.DRAFT)

        results_grant_has_collections_in_wrong_state = grant.access_reports
        assert len(results_grant_has_collections_in_wrong_state) == 0

    def test_get_access_reports_sort_order_status(self, factories):
        grant = factories.grant.build()
        report1 = factories.collection.build(grant=grant, status=CollectionStatusEnum.OPEN)
        report2 = factories.collection.build(grant=grant, status=CollectionStatusEnum.CLOSED)
        report3 = factories.collection.build(grant=grant, status=CollectionStatusEnum.OPEN)

        results = grant.access_reports
        assert len(results) == 3
        assert results[0].id == report1.id
        assert results[1].id == report3.id
        assert results[2].id == report2.id

    def test_get_access_reports_sort_order_date(self, factories):
        grant = factories.grant.build()
        report1 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2024, 1, 1)
        )
        report2 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2023, 1, 1)
        )
        report3 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2022, 1, 1)
        )

        results = grant.access_reports
        assert len(results) == 3
        assert results[0].id == report3.id
        assert results[1].id == report2.id
        assert results[2].id == report1.id

    def test_get_access_reports_sort_order_date_and_status(self, factories):
        grant = factories.grant.build()
        report0 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.CLOSED, submission_period_end_date=None
        )
        report1 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2024, 1, 1)
        )
        report2 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2023, 1, 1)
        )
        report3 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.OPEN, submission_period_end_date=date(2022, 1, 2)
        )
        report4 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.CLOSED, submission_period_end_date=date(2023, 2, 1)
        )
        report5 = factories.collection.build(
            grant=grant, status=CollectionStatusEnum.CLOSED, submission_period_end_date=date(2022, 1, 1)
        )

        results = grant.access_reports
        assert len(results) == 6
        assert results[0].id == report3.id
        assert results[1].id == report2.id
        assert results[2].id == report1.id
        assert results[3].id == report5.id
        assert results[4].id == report4.id
        assert results[5].id == report0.id


class TestFullConditionChain:
    def test_no_conditions(self, factories):
        q = factories.question.build()
        assert q.full_condition_chain == []

    def test_own_condition(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        q2 = factories.question.build(form=form)
        cond = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond, depends_on_component=q1)]
        assert q2.full_condition_chain == [cond]

    def test_chain_collects_transitive_conditions(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        q2 = factories.question.build(form=form)
        q3 = factories.question.build(form=form)
        cond_q2 = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        cond_q3 = factories.expression.build(question=q3, type_=ExpressionType.CONDITION, statement="True")
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]
        q3.owned_component_references = [ComponentReference(component=q3, expression=cond_q3, depends_on_component=q2)]
        assert q3.full_condition_chain == [cond_q3, cond_q2]

    def test_does_not_revisit_components(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        q2 = factories.question.build(form=form)
        q3 = factories.question.build(form=form)
        cond_q2 = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        cond_q3 = factories.expression.build(question=q3, type_=ExpressionType.CONDITION, statement="True")
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond_q2, depends_on_component=q1)]
        q3.owned_component_references = [
            ComponentReference(component=q3, expression=cond_q3, depends_on_component=q2),
            ComponentReference(component=q3, depends_on_component=q1),
        ]
        assert q3.full_condition_chain == [cond_q3, cond_q2]

    def test_skips_self_references(self, factories):
        q = factories.question.build()
        cond = factories.expression.build(question=q, type_=ExpressionType.CONDITION, statement="True")
        q.owned_component_references = [ComponentReference(component=q, expression=cond, depends_on_component=q)]
        assert q.full_condition_chain == [cond]

    def test_excludes_validation_expressions(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        q2 = factories.question.build(form=form)
        cond = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        factories.expression.build(question=q2, type_=ExpressionType.VALIDATION, statement="len(value) > 0")
        q2.owned_component_references = [ComponentReference(component=q2, expression=cond, depends_on_component=q1)]
        assert q2.full_condition_chain == [cond]


class TestAllConditionalDependedOnComponents:
    def test_no_conditions(self, factories):
        q = factories.question.build()
        assert q.all_conditional_depended_on_components == set()

    def test_single_condition(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        q2 = factories.question.build(form=form)
        cond = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        cr = ComponentReference(component=q2, depends_on_component=q1)
        cond.component_references = [cr]
        q2.owned_component_references = [cr]
        assert q2.all_conditional_depended_on_components == {q2}

    def test_chain_returns_all_conditional_components(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        q2 = factories.question.build(form=form)
        q3 = factories.question.build(form=form)
        cond_q2 = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        cond_q3 = factories.expression.build(question=q3, type_=ExpressionType.CONDITION, statement="True")
        cr_q2 = ComponentReference(component=q2, depends_on_component=q1)
        cond_q2.component_references = [cr_q2]
        q2.owned_component_references = [cr_q2]
        cr_q3 = ComponentReference(component=q3, depends_on_component=q2)
        cond_q3.component_references = [cr_q3]
        q3.owned_component_references = [cr_q3]
        assert q3.all_conditional_depended_on_components == {q3, q2}

    def test_condition_without_component_references_excluded(self, factories):
        q = factories.question.build()
        factories.expression.build(question=q, type_=ExpressionType.CONDITION, statement="False")
        assert q.all_conditional_depended_on_components == set()


class TestIsConditional:
    def test_not_conditional(self, factories):
        q = factories.question.build()
        assert q.is_conditional is False

    def test_is_conditional(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form)
        q2 = factories.question.build(form=form)
        cond = factories.expression.build(question=q2, type_=ExpressionType.CONDITION, statement="True")
        cr = ComponentReference(component=q2, depends_on_component=q1)
        cond.component_references = [cr]
        q2.owned_component_references = [cr]
        assert q2.is_conditional is True

    def test_conditional_with_hardcoded_conditions(self, factories):
        q = factories.question.build()
        factories.expression.build(question=q, type_=ExpressionType.CONDITION, statement="False")
        assert q.is_conditional is True
