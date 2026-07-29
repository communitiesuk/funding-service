from app.common.collections.types import TextSingleLineAnswer
from app.common.collections.validation import SubmissionValidator
from app.common.helpers.collections import SubmissionHelper
from tests.models import FactoryAnswer


class TestSubmissionValidatorRepeatsOver:
    def test_validate_all_reachable_questions_reconciles_repeating_container_first(self, factories, db_session):
        source = factories.group.create(add_another=True)
        source_q = factories.question.create(form=source.form, parent=source)
        container = factories.group.create(form=source.form, add_another=True, add_another_repeats_over=source)
        factories.question.create(form=source.form, parent=container)

        submission = factories.submission.create(
            collection=source.form.collection,
            answers=[
                FactoryAnswer(source_q, TextSingleLineAnswer("Alice"), add_another_index=0),
                FactoryAnswer(source_q, TextSingleLineAnswer("Bob"), add_another_index=1),
            ],
        )

        # simulate never having visited the repeating container's page - it has no entries yet
        assert submission.data_manager.get_count_for_add_another(container) == 0

        helper = SubmissionHelper(submission)
        SubmissionValidator(helper).validate_all_reachable_questions()

        # submit-time validation reconciled the container so it now matches the tasklist's view of it
        assert helper.submission.data_manager.get_count_for_add_another(container) == 2
