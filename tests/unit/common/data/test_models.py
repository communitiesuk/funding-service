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

        assert form.questions == [q1, *nested_questions, *nested_questions2, q2]
        assert group.questions == [*nested_questions, *nested_questions2]

    def test_get_components_nested_orders(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, order=2)
        group = factories.group.build(form=form, order=0)
        nested_q = factories.question.build(parent=group, order=0)
        q2 = factories.question.build(form=form, order=1)

        assert get_ordered_nested_components(form.components) == [group, nested_q, q2, q1]
        assert form.questions == [nested_q, q2, q1]

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
        assert form.questions == [q1, nested_q, q2]
