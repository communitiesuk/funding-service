from app.common.helpers.collections import CollectionHelper


class TestCollectionHelper:
    class TestGetOrderedVisibleSections:
        def test_ordering(self, db_session, factories):
            collection = factories.collection.build()
            _section_2 = factories.section.build(order=2, collection_schema=collection.collection_schema)
            _section_0 = factories.section.build(order=0, collection_schema=collection.collection_schema)
            _section_1 = factories.section.build(order=1, collection_schema=collection.collection_schema)
            _section_4 = factories.section.build(order=4, collection_schema=collection.collection_schema)
            _section_3 = factories.section.build(order=3, collection_schema=collection.collection_schema)

            helper = CollectionHelper(collection)
            helper_sections = helper.get_ordered_visible_sections()
            assert len(helper_sections) == 5
            assert [s.order for s in helper_sections] == [0, 1, 2, 3, 4]

    class TestGetOrderedVisibleForms:
        def test_ordering(self, db_session, factories):
            collection = factories.collection.build()
            section = factories.section.build(collection_schema=collection.collection_schema)
            _form_0 = factories.form.build(order=0, section=section)
            _form_2 = factories.form.build(order=2, section=section)
            _form_3 = factories.form.build(order=3, section=section)
            _form_1 = factories.form.build(order=1, section=section)

            helper = CollectionHelper(collection)
            helper_forms = helper.get_ordered_visible_forms_for_section(section)
            assert len(helper_forms) == 4
            assert [s.order for s in helper_forms] == [0, 1, 2, 3]

    class TestGetOrderedVisibleQuestions:
        def test_ordering(self, db_session, factories):
            collection = factories.collection.build()
            section = factories.section.build(collection_schema=collection.collection_schema)
            form = factories.form.build(order=0, section=section)
            _question_2 = factories.question.build(order=2, form=form)
            _question_0 = factories.question.build(order=0, form=form)
            _question_1 = factories.question.build(order=1, form=form)

            helper = CollectionHelper(collection)
            helper_questions = helper.get_ordered_visible_questions_for_form(form)
            assert len(helper_questions) == 3
            assert [s.order for s in helper_questions] == [0, 1, 2]
