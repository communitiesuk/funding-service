class TestFactories:
    def test_mock_form_component_join(self, factories):
        """
        Tests adding questions to a form after it is created, and that the cached_questions property works as expected.

        We have post generation hooks on the question and group factories to enforce this behaviour, so this test is
        testing that factory setup, not the underlying model implementations
        """
        form = factories.form.build()
        g1 = factories.group.build(form=form, add_another=True)
        assert len(form.cached_questions) == 0
        assert len(form.cached_all_components) == 1

        factories.question.build(form=form, parent=None)
        assert len(form.cached_questions) == 1
        assert len(form.cached_all_components) == 2

        factories.question.build(form=form, parent=g1)

        assert len(form.cached_questions) == 2

        factories.question.build_batch(2, form=form, parent=g1)

        assert len(form.cached_questions) == 4
        assert len(form.cached_all_components) == 5
