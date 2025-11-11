from datetime import date

from app import CollectionStatusEnum
from app.common.data.models import get_ordered_nested_components


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
