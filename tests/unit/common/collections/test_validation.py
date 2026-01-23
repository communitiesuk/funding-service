import uuid

import pytest

from app.common.collections.validation import SubmissionValidator
from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType
from app.common.exceptions import SubmissionValidationFailed
from app.common.helpers.collections import SubmissionHelper


class TestSubmissionValidator:
    def test_all_valid_answers_pass(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=1)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({q2.safe_qid})) > (({q1.safe_qid}))",
            context={
                "question_id": str(q2.id),
                "collection_id": str(form.collection_id),
                "minimum_value": None,
                "minimum_expression": f"(({q1.safe_qid}))",
            },
        )

        submission = factories.submission.build(collection=form.collection)
        submission.data = {str(q1.id): {"value": 50}, str(q2.id): {"value": 100}}

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        assert validator.validate_all_reachable_questions() is None

    def test_invalid_answer_caught(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=1)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({q2.safe_qid})) > (({q1.safe_qid}))",
            context={
                "question_id": str(q2.id),
                "collection_id": str(form.collection_id),
                "minimum_value": None,
                "minimum_expression": f"(({q1.safe_qid}))",
            },
        )

        submission = factories.submission.build(collection=form.collection)
        submission.data = {str(q1.id): {"value": 100}, str(q2.id): {"value": 50}}

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        with pytest.raises(SubmissionValidationFailed) as e:
            validator.validate_all_reachable_questions()

        errors = e.value.errors
        assert len(errors) == 1
        assert errors[0].question_id == q2.id
        assert errors[0].form_id == form.id

    def test_multiple_validation_errors_collected(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=1)
        q3 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=2)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({q2.safe_qid})) > (({q1.safe_qid}))",
            context={
                "question_id": str(q2.id),
                "collection_id": str(form.collection_id),
                "minimum_value": None,
                "minimum_expression": f"(({q1.safe_qid}))",
            },
        )

        factories.expression.build(
            question=q3,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.LESS_THAN,
            statement=f"(({q3.safe_qid})) < (({q1.safe_qid}))",
            context={
                "question_id": str(q3.id),
                "collection_id": str(form.collection_id),
                "maximum_value": None,
                "maximum_expression": f"(({q1.safe_qid}))",
            },
        )

        submission = factories.submission.build(collection=form.collection)
        submission.data = {str(q1.id): {"value": 50}, str(q2.id): {"value": 30}, str(q3.id): {"value": 70}}

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        with pytest.raises(SubmissionValidationFailed) as e:
            validator.validate_all_reachable_questions()

        errors = e.value.errors
        assert len(errors) == 2
        error_question_ids = {e.question_id for e in errors}
        assert error_question_ids == {q2.id, q3.id}

    def test_unreachable_questions_not_validated(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.YES_NO, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=1)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.CONDITION,
            managed_name=ManagedExpressionsEnum.IS_YES,
            statement=f"{q1.safe_qid} is True",
            context={"question_id": str(q1.id), "collection_id": str(form.collection_id)},
        )

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({q2.safe_qid})) > 100",
            context={
                "question_id": str(q2.id),
                "collection_id": str(form.collection_id),
                "minimum_value": 100,
                "minimum_expression": None,
            },
        )

        submission = factories.submission.build(collection=form.collection)
        submission.data = {str(q1.id): False, str(q2.id): {"value": 50}}

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        assert validator.validate_all_reachable_questions() is None

    def test_changed_validation_rules(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=1)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({q2.safe_qid})) > (({q1.safe_qid}))",
            context={
                "question_id": str(q2.id),
                "collection_id": str(form.collection_id),
                "minimum_value": None,
                "minimum_expression": f"(({q1.safe_qid}))",
            },
        )

        submission = factories.submission.build(collection=form.collection)
        submission.data = {str(q1.id): {"value": 50}, str(q2.id): {"value": 100}}

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        assert validator.validate_all_reachable_questions() is None

        submission.data[str(q1.id)] = {"value": 150}
        helper.cached_get_answer_for_question.cache_clear()
        from app.common.expressions import ExpressionContext

        helper.cached_evaluation_context = ExpressionContext.build_expression_context(
            collection=submission.collection, submission_helper=helper, mode="evaluation"
        )

        with pytest.raises(SubmissionValidationFailed) as e:
            validator.validate_all_reachable_questions()

        errors = e.value.errors
        assert len(errors) == 1
        assert errors[0].question_id == q2.id

    def test_questions_without_validations(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=1)

        submission = factories.submission.build(collection=form.collection)
        submission.data = {str(q1.id): {"value": 50}, str(q2.id): {"value": 100}}

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        assert validator.validate_all_reachable_questions() is None

    def test_unanswered_questions_skipped(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=1)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({q2.safe_qid})) > (({q1.safe_qid}))",
            context={
                "question_id": str(q2.id),
                "collection_id": str(form.collection_id),
                "minimum_value": None,
                "minimum_expression": f"(({q1.safe_qid}))",
            },
        )

        submission = factories.submission.build(collection=form.collection)
        submission.data = {str(q1.id): {"value": 50}}

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)

        assert validator.validate_all_reachable_questions() is None

    def test_add_another_all_entries_valid(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, id=uuid.uuid4(), add_another=True, order=0)
        q1 = factories.question.build(
            form=form, parent=group, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=0
        )

        factories.expression.build(
            question=q1,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({q1.safe_qid})) > 0",
            context={
                "question_id": str(q1.id),
                "collection_id": str(form.collection_id),
                "minimum_value": 0,
                "minimum_expression": None,
            },
        )

        submission = factories.submission.build(collection=form.collection)
        submission.data = {
            str(group.id): [
                {str(q1.id): {"value": 10}},
                {str(q1.id): {"value": 20}},
                {str(q1.id): {"value": 30}},
            ]
        }

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        assert validator.validate_all_reachable_questions() is None

    def test_add_another_invalid_entry_caught(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, id=uuid.uuid4(), add_another=True, order=0)
        q1 = factories.question.build(
            form=form, parent=group, id=uuid.uuid4(), data_type=QuestionDataType.INTEGER, order=0
        )

        factories.expression.build(
            question=q1,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({q1.safe_qid})) > 0",
            context={
                "question_id": str(q1.id),
                "collection_id": str(form.collection_id),
                "minimum_value": 0,
                "minimum_expression": None,
            },
        )

        submission = factories.submission.build(collection=form.collection)
        submission.data = {
            str(group.id): [
                {str(q1.id): {"value": 10}},
                {str(q1.id): {"value": -5}},
                {str(q1.id): {"value": 30}},
            ]
        }

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)

        with pytest.raises(SubmissionValidationFailed) as e:
            validator.validate_all_reachable_questions()

        errors = e.value.errors
        assert len(errors) == 1
        assert errors[0].question_id == q1.id
        assert errors[0].add_another_index == 1
