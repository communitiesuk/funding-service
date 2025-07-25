# todo: propose moving common/helper/collections.py to common/collections/submission.py
from typing import TYPE_CHECKING, ClassVar, Optional
from uuid import UUID

from flask import url_for

from app.common.collections.forms import CheckYourAnswersForm, build_question_form
from app.common.data.types import FormRunnerState, SubmissionStatusEnum, TRunnerUrlMap
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper

if TYPE_CHECKING:
    from app.common.collections.forms import DynamicQuestionForm
    from app.common.data.models import Form, Question
    from app.common.data.models_user import User


class FormRunner:
    """Responsible for backing form runner pages, consistently takes care of:
        - managing routing backwards and forwards
        - integrity checks
        - setting up forms

    This allows us to implement the form runner in different domain environments consistently."""

    url_map: ClassVar[TRunnerUrlMap] = {}

    def __init__(
        self,
        submission: SubmissionHelper,
        question: Optional["Question"] = None,
        form: Optional["Form"] = None,
        source: Optional["FormRunnerState"] = None,
    ):
        if question and form:
            raise ValueError("Expected only one of question or form")

        self.submission = submission
        self.question = question
        self.form = form
        self.source = source

        self._valid: Optional[bool] = None

        self._tasklist_form = GenericSubmitForm()
        self._question_form: Optional[DynamicQuestionForm] = None
        self._check_your_answers_form: Optional[CheckYourAnswersForm] = None

        if self.question:
            self.form = self.question.form
            _QuestionForm = build_question_form(self.question, self.submission.expression_context)
            self._question_form = _QuestionForm(data=self.submission.form_data)

        if self.form:
            all_questions_answered, _ = self.submission.get_all_questions_are_answered_for_form(self.form)
            self._check_your_answers_form = CheckYourAnswersForm(
                section_completed=(
                    "yes" if self.submission.get_status_for_form(self.form) == SubmissionStatusEnum.COMPLETED else None
                ),
                all_questions_answered=all_questions_answered,
            )

    @classmethod
    def load(
        cls,
        *,
        submission_id: UUID,
        question_id: Optional[UUID] = None,
        form_id: Optional[UUID] = None,
        source: Optional[FormRunnerState] = None,
    ) -> "FormRunner":
        if question_id and form_id:
            raise ValueError("Expected only one of question_id or form_id")

        submission = SubmissionHelper.load(submission_id)
        question, form = None, None

        if question_id:
            question = submission.get_question(question_id)
        elif form_id:
            form = submission.get_form(form_id)

        return cls(submission=submission, question=question, form=form, source=source)

    @property
    def question_form(self) -> "DynamicQuestionForm":
        if not self.question or not self._question_form:
            raise RuntimeError("Question context not set")
        return self._question_form

    @property
    def check_your_answers_form(self) -> "CheckYourAnswersForm":
        if not self.form or not self._check_your_answers_form:
            raise RuntimeError("Form context not set")
        return self._check_your_answers_form

    @property
    def tasklist_form(self) -> "GenericSubmitForm":
        return self._tasklist_form

    def save_question_answer(self) -> None:
        if not self.question:
            raise RuntimeError("Question context not set")

        self.submission.submit_answer_for_question(self.question.id, self.question_form)

    def save_is_form_completed(self, user: "User") -> bool:
        if not self.form:
            raise RuntimeError("Form context not set")

        try:
            self.submission.toggle_form_completed(
                form=self.form,
                user=user,
                is_complete=self.check_your_answers_form.section_completed.data == "yes",
            )
            return True
        except ValueError:
            self.check_your_answers_form.section_completed.errors.append(  # type:ignore[attr-defined]
                "You must complete all questions before marking this task as complete"
            )
            return False

    def complete_submission(self, user: "User") -> bool:
        try:
            self.submission.submit(user)
            return True
        except ValueError:
            self._tasklist_form.submit.errors.append("You must complete all tasks before submitting")  # type:ignore[attr-defined]
            return False

    def to_url(
        self,
        state: FormRunnerState,
        *,
        question: Optional["Question"] = None,
        form: Optional["Form"] = None,
        source: Optional[FormRunnerState] = None,
    ) -> str:
        return self.url_map[state](self, question or self.question, form or self.form, source)

    @property
    def next_url(self) -> str:
        # if we're in the context of a question page, decide if we should go to the next question
        # or back to check your answers based on if the integrity checks pass
        if self.question:
            if not self._valid:
                return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)

            next_question = self.submission.get_next_question(self.question.id)

            # Regardless of where they're from (eg even check-your-answers), take them to the next unanswered question
            # this will let users stay in a data-submitting flow if they've changed a conditional answer which has
            # unlocked more questions.
            while next_question and self.submission.get_answer_for_question(next_question.id) is not None:
                next_question = self.submission.get_next_question(next_question.id)

            return (
                self.to_url(FormRunnerState.QUESTION, question=next_question)
                if next_question
                else self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)
            )

        # default back to the tasklist if we're routing forward outside of a question context (check your answers)
        return self.to_url(FormRunnerState.TASKLIST)

    def validate_can_show_question_page(self) -> bool:
        # for now we're only validating the question state, there may be integrity
        # checks for check your answers or tasklist in the future
        if not self.question:
            raise ValueError("Question context not set")

        context = self.submission.expression_context

        if not self.submission.is_question_visible(self.question, context):
            self._valid = False
        elif self.submission.is_completed:
            self._valid = False
        else:
            self._valid = True

        return self._valid

    @property
    def back_url(self) -> str:
        # todo: persist the "tasklist" source when going "back" to check your answers
        if self.source == FormRunnerState.TASKLIST:
            return self.to_url(FormRunnerState.TASKLIST)
        elif self.source == FormRunnerState.CHECK_YOUR_ANSWERS:
            return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)

        if self.question:
            previous_question = self.submission.get_previous_question(self.question.id)
        elif self.form:
            previous_question = self.submission.get_last_question_for_form(self.form)
        else:
            previous_question = None
        if previous_question:
            return self.to_url(FormRunnerState.QUESTION, question=previous_question)

        return self.to_url(FormRunnerState.TASKLIST)


class DGFFormRunner(FormRunner):
    url_map: ClassVar[TRunnerUrlMap] = {
        FormRunnerState.QUESTION: lambda runner, question, _form, source: url_for(
            "developers.deliver.ask_a_question",
            submission_id=runner.submission.id,
            question_id=question.id if question else None,
            source=source,
        ),
        FormRunnerState.TASKLIST: lambda runner, _question, _form, _source: url_for(
            "developers.deliver.submission_tasklist",
            submission_id=runner.submission.id,
            form_id=runner.form.id if runner.form else None,
        ),
        FormRunnerState.CHECK_YOUR_ANSWERS: lambda runner, _question, form, source: url_for(
            "developers.deliver.check_your_answers",
            submission_id=runner.submission.id,
            form_id=form.id if form else runner.form.id if runner.form else None,
            source=source,
        ),
    }


class AGFFormRunner(FormRunner):
    url_map: ClassVar[TRunnerUrlMap] = {
        FormRunnerState.QUESTION: lambda runner, question, _form, source: url_for(
            "developers.access.ask_a_question",
            submission_id=runner.submission.id,
            question_id=question.id if question else None,
            source=source,
        ),
        FormRunnerState.TASKLIST: lambda runner, _question, _form, _source: url_for(
            "developers.access.submission_tasklist",
            submission_id=runner.submission.id,
            form_id=runner.form.id if runner.form else None,
        ),
        FormRunnerState.CHECK_YOUR_ANSWERS: lambda runner, _question, form, source: url_for(
            "developers.access.check_your_answers",
            submission_id=runner.submission.id,
            form_id=form.id if form else runner.form.id if runner.form else None,
            source=source,
        ),
    }
