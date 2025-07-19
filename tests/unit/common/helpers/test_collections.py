import uuid

import pytest

from app.common.data.types import ExpressionType, SubmissionEventKey
from app.common.helpers.collections import SubmissionHelper
from tests.utils import AnyStringMatching


class TestSubmissionHelper:
    class TestGetOrderedVisibleSections:
        def test_ordering(self, db_session, factories):
            submission = factories.submission.build(collection__default_section=False)
            _section_2 = factories.section.build(order=2, collection=submission.collection)
            _section_0 = factories.section.build(order=0, collection=submission.collection)
            _section_1 = factories.section.build(order=1, collection=submission.collection)
            _section_4 = factories.section.build(order=4, collection=submission.collection)
            _section_3 = factories.section.build(order=3, collection=submission.collection)

            helper = SubmissionHelper(submission)
            helper_sections = helper.get_ordered_visible_sections()
            assert len(helper_sections) == 5
            assert [s.order for s in helper_sections] == [0, 1, 2, 3, 4]

    class TestGetOrderedVisibleForms:
        def test_ordering(self, db_session, factories):
            submission = factories.submission.build()
            section = submission.collection.sections[0]
            _form_0 = factories.form.build(order=0, section=section)
            _form_2 = factories.form.build(order=2, section=section)
            _form_3 = factories.form.build(order=3, section=section)
            _form_1 = factories.form.build(order=1, section=section)

            helper = SubmissionHelper(submission)
            helper_forms = helper.get_ordered_visible_forms_for_section(section)
            assert len(helper_forms) == 4
            assert [s.order for s in helper_forms] == [0, 1, 2, 3]

    class TestGetOrderedVisibleQuestions:
        def test_ordering(self, db_session, factories):
            submission = factories.submission.build()
            section = submission.collection.sections[0]
            form = factories.form.build(order=0, section=section)
            _question_2 = factories.question.build(order=2, form=form)
            _question_0 = factories.question.build(order=0, form=form)
            _question_1 = factories.question.build(order=1, form=form)

            helper = SubmissionHelper(submission)
            helper_questions = helper.get_ordered_visible_questions_for_form(form)
            assert len(helper_questions) == 3
            assert [s.order for s in helper_questions] == [0, 1, 2]

        def test_visible_questions_filtered(self, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.section.collection)
            visible_question = factories.question.build(form=form)

            invisible_question = factories.question.build(form=form)
            factories.expression.build(question=invisible_question, type=ExpressionType.CONDITION, statement="False")

            helper = SubmissionHelper(submission)
            helper_questions = helper.get_ordered_visible_questions_for_form(form)
            assert len(helper_questions) == 1
            assert helper_questions[0].id == visible_question.id

    class TestGetSection:
        def test_exists(self, db_session, factories):
            section = factories.section.build()
            submission = factories.submission.build(collection=section.collection)

            helper = SubmissionHelper(submission)
            assert helper.get_section(section.id) == section

        def test_does_not_exist(self, db_session, factories):
            section = factories.section.build()
            submission = factories.submission.build(collection=section.collection)

            helper = SubmissionHelper(submission)
            with pytest.raises(ValueError) as e:
                assert helper.get_section(uuid.uuid4())

            assert str(e.value) == AnyStringMatching(
                r"Could not find a section with id=[a-z0-9-]+ in collection=[a-z0-9-]+"
            )

    class TestGetForm:
        def test_exists(self, db_session, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)
            assert helper.get_form(form.id) == form

        def test_does_not_exist(self, db_session, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)
            with pytest.raises(ValueError) as e:
                assert helper.get_form(uuid.uuid4())

            assert str(e.value) == AnyStringMatching(
                r"Could not find a form with id=[a-z0-9-]+ in collection=[a-z0-9-]+"
            )

    class TestGetQuestion:
        def test_exists(self, db_session, factories):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.section.collection)

            helper = SubmissionHelper(submission)
            assert helper.get_question(question.id) == question

        def test_does_not_exist(self, db_session, factories):
            question = factories.question.build()
            submission = factories.submission.build(collection=question.form.section.collection)

            helper = SubmissionHelper(submission)
            with pytest.raises(ValueError) as e:
                assert helper.get_question(uuid.uuid4())

            assert str(e.value) == AnyStringMatching(
                r"Could not find a question with id=[a-z0-9-]+ in collection=[a-z0-9-]+"
            )

    class TestGetFirstQuestionForForm:
        def test_at_least_one_question_in_form(self, db_session, factories):
            form = factories.form.build()

            for x in reversed(range(5)):
                factories.question.build(form=form, id=uuid.UUID(int=x), order=x)

            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)
            question = helper.get_first_question_for_form(form)
            assert question.id == uuid.UUID("00000000-0000-0000-0000-000000000000")  # ty: ignore[possibly-unbound-attribute]

        def test_no_visible_questions_in_form(self, db_session, factories):
            form = factories.form.build()

            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)
            assert helper.get_first_question_for_form(form) is None

    class TestGetLastQuestionForForm:
        def test_at_least_one_question_in_form(self, db_session, factories):
            form = factories.form.build()

            for x in reversed(range(5)):
                factories.question.build(form=form, id=uuid.UUID(int=x), order=x)

            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)
            question = helper.get_last_question_for_form(form)
            assert question.id == uuid.UUID("00000000-0000-0000-0000-000000000004")  # ty: ignore[possibly-unbound-attribute]

        def test_no_visible_questions_in_form(self, db_session, factories):
            form = factories.form.build()

            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)
            assert helper.get_last_question_for_form(form) is None

    class TestGetFormForQuestion:
        def test_question_exists_in_collection_forms(self, db_session, factories):
            section = factories.section.build()
            form = factories.form.build(section=section)

            for x in reversed(range(5)):
                factories.question.build(form=form, id=uuid.UUID(int=x), order=x)

            submission = factories.submission.build(collection=section.collection)

            helper = SubmissionHelper(submission)

            for question in form.questions:
                assert helper.get_form_for_question(question.id) == form

        def test_question_does_not_exist_in_collection_forms(self, db_session, factories):
            form = factories.form.build()
            factories.question.build(form=form, id=uuid.UUID(int=0), order=0)
            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError) as e:
                helper.get_form_for_question(uuid.UUID(int=1))

            assert str(e.value) == AnyStringMatching(
                r"Could not find form for question_id=00000000-0000-0000-0000-000000000001 "
                r"in collection=[a-z0-9-]+"
            )

    class TestGetNextQuestion:
        def test_current_question_exists_and_is_not_last_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)

            assert helper.get_next_question(uuid.UUID(int=0)).id == uuid.UUID(int=1)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_next_question(uuid.UUID(int=1)).id == uuid.UUID(int=2)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_next_question(uuid.UUID(int=2)).id == uuid.UUID(int=3)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_next_question(uuid.UUID(int=3)).id == uuid.UUID(int=4)  # ty: ignore[possibly-unbound-attribute]

        def test_current_question_exists_but_is_last_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)

            assert helper.get_next_question(uuid.UUID(int=4)) is None

        def test_current_question_does_not_exist(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError) as e:
                helper.get_next_question(uuid.UUID(int=9))

            assert str(e.value) == AnyStringMatching(
                r"Could not find form for question_id=00000000-0000-0000-0000-000000000009 "
                r"in collection=[a-z0-9-]+"
            )

        def test_next_question_ignores_not_visible_questions(self, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.section.collection)
            question_one = factories.question.build(form=form, id=uuid.UUID(int=0), order=0)
            question_two = factories.question.build(form=form, id=uuid.UUID(int=1), order=1)
            question_three = factories.question.build(form=form, id=uuid.UUID(int=2), order=2)

            factories.expression.build(question=question_two, type=ExpressionType.CONDITION, statement="False")

            helper = SubmissionHelper(submission)

            question = helper.get_next_question(question_one.id)
            assert question
            assert question.id == question_three.id

    class TestGetPreviousQuestion:
        def test_current_question_exists_and_is_not_first_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)

            assert helper.get_previous_question(uuid.UUID(int=1)).id == uuid.UUID(int=0)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_previous_question(uuid.UUID(int=2)).id == uuid.UUID(int=1)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_previous_question(uuid.UUID(int=3)).id == uuid.UUID(int=2)  # ty: ignore[possibly-unbound-attribute]
            assert helper.get_previous_question(uuid.UUID(int=4)).id == uuid.UUID(int=3)  # ty: ignore[possibly-unbound-attribute]

        def test_current_question_exists_but_is_first_question(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)

            assert helper.get_previous_question(uuid.UUID(int=0)) is None

        def test_current_question_does_not_exist(self, db_session, factories):
            form = factories.form.build()
            for x in range(5):
                factories.question.build(form=form, id=uuid.UUID(int=x))
            submission = factories.submission.build(collection=form.section.collection)

            helper = SubmissionHelper(submission)

            with pytest.raises(ValueError) as e:
                helper.get_previous_question(uuid.UUID(int=9))

            assert str(e.value) == AnyStringMatching(
                r"Could not find form for question_id=00000000-0000-0000-0000-000000000009 "
                r"in collection=[a-z0-9-]+"
            )

        def test_previous_question_ignores_not_visible_questions(self, factories):
            form = factories.form.build()
            submission = factories.submission.build(collection=form.section.collection)
            question_one = factories.question.build(form=form, id=uuid.UUID(int=0), order=0)
            question_two = factories.question.build(form=form, id=uuid.UUID(int=1), order=1)
            question_three = factories.question.build(form=form, id=uuid.UUID(int=2), order=2)

            factories.expression.build(question=question_two, type=ExpressionType.CONDITION, statement="False")

            helper = SubmissionHelper(submission)

            question = helper.get_previous_question(question_three.id)
            assert question
            assert question.id == question_one.id

    class TestStatuses:
        def test_all_forms_are_completed(self, db_session, factories):
            form_one = factories.form.build()
            form_two = factories.form.build(section=form_one.section)
            question_one = factories.question.build(form=form_one)
            question_two = factories.question.build(form=form_two)

            submission = factories.submission.build(collection=form_one.section.collection)
            helper = SubmissionHelper(submission)

            # empty collections are not completed
            assert helper.all_forms_are_completed is False

            submission.data[str(question_one.id)] = "User submitted data"
            submission.events = [
                factories.submission_event.build(
                    submission=submission, form=form_one, key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED
                )
            ]

            # one complete form and one incomplete is still not completed
            assert helper.all_forms_are_completed is False

            submission.data[str(question_two.id)] = "User submitted data"

            # all questions complete but a form not marked as completed is still not completed
            assert helper.all_forms_are_completed is False

            submission.events.append(
                factories.submission_event.build(
                    submission=submission, form=form_two, key=SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED
                )
            )

            # all questions answered and all marked as complete is complete
            assert helper.all_forms_are_completed is True

    class TestVisibleQuestion:
        def test_is_question_always_visible_with_no_conditions(self, factories):
            question = factories.question.build()
            helper = SubmissionHelper(factories.submission.build(collection=question.form.section.collection))

            assert helper.is_question_visible(question, helper.expression_context) is True

        def test_is_question_visible_not_visible_with_failing_condition(self, factories):
            question = factories.question.build()
            helper = SubmissionHelper(factories.submission.build(collection=question.form.section.collection))

            factories.expression.build(question=question, type=ExpressionType.CONDITION, statement="False")

            assert helper.is_question_visible(question, helper.expression_context) is False

        def test_is_question_visible_visible_with_passing_condition(self, factories):
            question = factories.question.build()
            helper = SubmissionHelper(factories.submission.build(collection=question.form.section.collection))

            factories.expression.build(question=question, type=ExpressionType.CONDITION, statement="True")

            assert helper.is_question_visible(question, helper.expression_context) is True
