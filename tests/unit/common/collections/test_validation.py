import uuid

import pytest

from app.common.collections.types import IntegerAnswer, YesNoAnswer
from app.common.collections.validation import SubmissionValidator
from app.common.data.types import ExpressionType, ManagedExpressionsEnum, QuestionDataType, QuestionPresentationOptions
from app.common.exceptions import SubmissionValidationFailed
from app.common.expressions import ExpressionReference
from app.common.expressions.custom import CustomExpression
from app.common.helpers.collections import SubmissionHelper
from tests.models import FactoryAnswer


class TestSubmissionValidator:
    def test_all_valid_answers_pass(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=1)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q2.safe_qid} > {q1.safe_qid}",
            context={
                "subject_reference": ExpressionReference.from_question(q2),
                "minimum_value": None,
                "minimum_expression": ExpressionReference.from_question(q1),
            },
        )

        submission = factories.submission.build(
            collection=form.collection,
            answers=[FactoryAnswer(q1, IntegerAnswer(value=50)), FactoryAnswer(q2, IntegerAnswer(value=100))],
        )

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        assert validator.validate_all_reachable_questions() is None

    def test_invalid_answer_caught(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=1)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q2.safe_qid} > {q1.safe_qid}",
            context={
                "subject_reference": ExpressionReference.from_question(q2),
                "minimum_value": None,
                "minimum_expression": ExpressionReference.from_question(q1),
            },
        )

        submission = factories.submission.build(
            collection=form.collection,
            answers=[FactoryAnswer(q1, IntegerAnswer(value=100)), FactoryAnswer(q2, IntegerAnswer(value=50))],
        )

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
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=1)
        q3 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=2)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q2.safe_qid} > {q1.safe_qid}",
            context={
                "subject_reference": ExpressionReference.from_question(q2),
                "minimum_value": None,
                "minimum_expression": ExpressionReference.from_question(q1),
            },
        )

        factories.expression.build(
            question=q3,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.LESS_THAN,
            statement=f"{q3.safe_qid} < {q1.safe_qid}",
            context={
                "subject_reference": ExpressionReference.from_question(q3),
                "maximum_value": None,
                "maximum_expression": ExpressionReference.from_question(q1),
            },
        )

        submission = factories.submission.build(
            collection=form.collection,
            answers=[
                FactoryAnswer(q1, IntegerAnswer(value=50)),
                FactoryAnswer(q2, IntegerAnswer(value=30)),
                FactoryAnswer(q3, IntegerAnswer(value=70)),
            ],
        )

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
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=1)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.CONDITION,
            managed_name=ManagedExpressionsEnum.IS_YES,
            statement=f"{q1.safe_qid} is True",
            context={"subject_reference": ExpressionReference.from_question(q1)},
        )

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q2.safe_qid} > 100",
            context={
                "subject_reference": ExpressionReference.from_question(q2),
                "minimum_value": 100,
                "minimum_expression": None,
            },
        )

        submission = factories.submission.build(
            collection=form.collection,
            answers=[FactoryAnswer(q1, YesNoAnswer(False)), FactoryAnswer(q2, IntegerAnswer(value=50))],
        )

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        assert validator.validate_all_reachable_questions() is None

    def test_changed_validation_rules(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=1)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q2.safe_qid} > {q1.safe_qid}",
            context={
                "subject_reference": ExpressionReference.from_question(q2),
                "minimum_value": None,
                "minimum_expression": ExpressionReference.from_question(q1),
            },
        )

        submission = factories.submission.build(
            collection=form.collection,
            answers=[FactoryAnswer(q1, IntegerAnswer(value=50)), FactoryAnswer(q2, IntegerAnswer(value=100))],
        )

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        assert validator.validate_all_reachable_questions() is None

        submission.data_manager.set(q1, IntegerAnswer(value=150))
        helper.clear_caches()

        with pytest.raises(SubmissionValidationFailed) as e:
            validator.validate_all_reachable_questions()

        errors = e.value.errors
        assert len(errors) == 1
        assert errors[0].question_id == q2.id

    def test_questions_without_validations(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=1)

        submission = factories.submission.build(
            collection=form.collection,
            answers=[FactoryAnswer(q1, IntegerAnswer(value=50)), FactoryAnswer(q2, IntegerAnswer(value=100))],
        )

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        assert validator.validate_all_reachable_questions() is None

    def test_unanswered_questions_skipped(self, factories):
        form = factories.form.build()
        q1 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0)
        q2 = factories.question.build(form=form, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=1)

        factories.expression.build(
            question=q2,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q2.safe_qid} > {q1.safe_qid}",
            context={
                "subject_reference": ExpressionReference.from_question(q2),
                "minimum_value": None,
                "minimum_expression": ExpressionReference.from_question(q1),
            },
        )

        submission = factories.submission.build(
            collection=form.collection, answers=[FactoryAnswer(q1, IntegerAnswer(value=50))]
        )

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)

        assert validator.validate_all_reachable_questions() is None

    def test_add_another_all_entries_valid(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, id=uuid.uuid4(), add_another=True, order=0)
        q1 = factories.question.build(
            form=form, parent=group, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0
        )

        factories.expression.build(
            question=q1,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q1.safe_qid} > 0",
            context={
                "subject_reference": ExpressionReference.from_question(q1),
                "minimum_value": 0,
                "minimum_expression": None,
            },
        )

        submission = factories.submission.build(
            collection=form.collection,
            answers=[
                FactoryAnswer(q1, IntegerAnswer(value=10), add_another_index=0),
                FactoryAnswer(q1, IntegerAnswer(value=20), add_another_index=1),
                FactoryAnswer(q1, IntegerAnswer(value=30), add_another_index=2),
            ],
        )

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)
        assert validator.validate_all_reachable_questions() is None

    def test_add_another_invalid_entry_caught(self, factories):
        form = factories.form.build()
        group = factories.group.build(form=form, id=uuid.uuid4(), add_another=True, order=0)
        q1 = factories.question.build(
            form=form, parent=group, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0
        )

        factories.expression.build(
            question=q1,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"{q1.safe_qid} > 0",
            context={
                "subject_reference": ExpressionReference.from_question(q1),
                "minimum_value": 0,
                "minimum_expression": None,
            },
        )

        submission = factories.submission.build(
            collection=form.collection,
            answers=[
                FactoryAnswer(q1, IntegerAnswer(value=10), add_another_index=0),
                FactoryAnswer(q1, IntegerAnswer(value=-5), add_another_index=1),
                FactoryAnswer(q1, IntegerAnswer(value=30), add_another_index=2),
            ],
        )

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)

        with pytest.raises(SubmissionValidationFailed) as e:
            validator.validate_all_reachable_questions()

        errors = e.value.errors
        assert len(errors) == 1
        assert errors[0].question_id == q1.id
        assert errors[0].add_another_index == 1

    def test_add_another_same_page_group_validation_caught(self, factories):
        form = factories.form.build()
        group = factories.group.build(
            form=form,
            id=uuid.uuid4(),
            add_another=True,
            order=0,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        q1 = factories.question.build(
            form=form, parent=group, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0
        )
        q2 = factories.question.build(
            form=form, parent=group, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=1
        )

        custom = CustomExpression(
            custom_expression=f"(({q1.safe_qid})) + (({q2.safe_qid})) == 100",
            custom_message="Total must be 100",
        )
        factories.expression.build(
            question=group,
            type_=ExpressionType.VALIDATION,
            statement=custom.statement,
            context=custom.model_dump(mode="json"),
        )

        submission = factories.submission.build(
            collection=form.collection,
            answers=[
                FactoryAnswer(q1, IntegerAnswer(value=60), add_another_index=0),
                FactoryAnswer(q2, IntegerAnswer(value=40), add_another_index=0),
                FactoryAnswer(q1, IntegerAnswer(value=30), add_another_index=1),
                FactoryAnswer(q2, IntegerAnswer(value=30), add_another_index=1),
            ],
        )

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)

        with pytest.raises(SubmissionValidationFailed) as e:
            validator.validate_all_reachable_questions()

        errors = e.value.errors
        assert len(errors) == 1
        assert errors[0].question_id == group.id
        assert errors[0].form_id == form.id
        assert errors[0].error_message == "Total must be 100"

    def test_add_another_nested_same_page_group_validation_caught(self, factories):
        form = factories.form.build()
        outer_group = factories.group.build(form=form, id=uuid.uuid4(), add_another=True, order=0)
        inner_group = factories.group.build(
            form=form,
            parent=outer_group,
            id=uuid.uuid4(),
            order=0,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        q1 = factories.question.build(
            form=form, parent=inner_group, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0
        )
        q2 = factories.question.build(
            form=form, parent=inner_group, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=1
        )

        custom = CustomExpression(
            custom_expression=f"(({q1.safe_qid})) + (({q2.safe_qid})) == 100",
            custom_message="Total must be 100",
        )
        factories.expression.build(
            question=inner_group,
            type_=ExpressionType.VALIDATION,
            statement=custom.statement,
            context=custom.model_dump(mode="json"),
        )

        submission = factories.submission.build(
            collection=form.collection,
            answers=[
                FactoryAnswer(q1, IntegerAnswer(value=60), add_another_index=0),
                FactoryAnswer(q2, IntegerAnswer(value=40), add_another_index=0),
                FactoryAnswer(q1, IntegerAnswer(value=30), add_another_index=1),
                FactoryAnswer(q2, IntegerAnswer(value=30), add_another_index=1),
            ],
        )

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)

        with pytest.raises(SubmissionValidationFailed) as e:
            validator.validate_all_reachable_questions()

        errors = e.value.errors
        assert len(errors) == 1
        assert errors[0].question_id == inner_group.id
        assert errors[0].form_id == form.id
        assert errors[0].error_message == "Total must be 100"

    def test_group_validation_passes_when_referenced_number_question_is_conditionally_hidden(self, factories):
        is_yes_question = factories.question.build(id=uuid.uuid4(), data_type=QuestionDataType.YES_NO, order=0)
        group = factories.group.build(
            form=is_yes_question.form,
            id=uuid.uuid4(),
            order=1,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        question_number_one = factories.question.build(
            form=is_yes_question.form, parent=group, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=0
        )
        factories.expression.build(
            question=question_number_one,
            type_=ExpressionType.CONDITION,
            managed_name=ManagedExpressionsEnum.IS_YES,
            statement=f"{is_yes_question.safe_qid} is True",
            context={"subject_reference": ExpressionReference.from_question(is_yes_question)},
        )
        question_number_two = factories.question.build(
            form=is_yes_question.form, parent=group, id=uuid.uuid4(), data_type=QuestionDataType.NUMBER, order=1
        )
        custom = CustomExpression(
            custom_expression=f"(({question_number_one.safe_qid})) + (({question_number_two.safe_qid})) == 50",
            custom_message="Total must be 50",
        )
        factories.expression.build(
            question=group,
            type_=ExpressionType.VALIDATION,
            statement=custom.statement,
            context=custom.model_dump(mode="json"),
        )

        submission = factories.submission.build(
            collection=is_yes_question.form.collection,
            answers=[
                FactoryAnswer(is_yes_question, YesNoAnswer(False)),
                FactoryAnswer(question_number_two, IntegerAnswer(value=50)),
            ],
        )

        helper = SubmissionHelper(submission)
        validator = SubmissionValidator(helper)

        assert validator.validate_all_reachable_questions() is None
