# todo: propose moving common/helper/collections.py to common/collections/submission.py
from typing import TYPE_CHECKING, Callable, ClassVar, Optional
from uuid import UUID

from app.common.collections.forms import CheckYourAnswersForm, build_question_form
from app.common.data.types import FormRunnerState, SubmissionStatusEnum
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper
from app.extensions import notification_service

if TYPE_CHECKING:
    from app.common.collections.forms import DynamicQuestionForm
    from app.common.data.models import Form, Question
    from app.common.data.models_user import User

runner_url_map = dict[
    FormRunnerState, Callable[["FormRunner", Optional["Question"], Optional["Form"], Optional[FormRunnerState]], str]
]


class FormRunner:
    """Responsible for backing form runner pages, consistently takes care of:
        - managing routing backwards and forwards
        - integrity checks
        - setting up forms

    This allows us to implement the form runner in different domain environments consistently."""

    url_map: ClassVar[runner_url_map] = {}

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
            context = self.submission.expression_context
            self._question_form = build_question_form(self.question, context)(data=context)

        if self.form:
            all_questions_answered, _ = self.submission.get_all_questions_are_answered_for_form(self.form)
            self._check_your_answers_form = CheckYourAnswersForm(
                section_completed=(
                    "yes" if self.submission.get_status_for_form(self.form) == SubmissionStatusEnum.COMPLETED else None
                )
            )
            self._check_your_answers_form.set_is_required(all_questions_answered)

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

    def save_is_form_completed(self, user: "User") -> None:
        if not self.form:
            raise RuntimeError("Form context not set")

        try:
            self.submission.toggle_form_completed(
                form=self.form,
                user=user,
                is_complete=self.check_your_answers_form.section_completed.data == "yes",
            )
        except ValueError as e:
            self.check_your_answers_form.section_completed.errors.append(  # type:ignore[attr-defined]
                "You must complete all questions before marking this section as complete"
            )
            raise ValueError("Failed to save form completed status") from e

    def submit(self, user: "User") -> None:
        try:
            self.submission.submit(user)
            notification_service.send_collection_submission(self.submission.submission)
        except ValueError as e:
            self._tasklist_form.submit.errors.append("You must complete all forms before submitting the collection")  # type:ignore[attr-defined]
            raise ValueError("Failed to submit") from e

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
        if self.question and self._valid is not None:
            if self._valid:
                if self.source == FormRunnerState.CHECK_YOUR_ANSWERS:
                    # todo: even if we came from check your answers, move to the next question
                    #       if it hasn't been answered
                    return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)

                next_question = self.submission.get_next_question(self.question.id)
                if next_question:
                    return self.to_url(FormRunnerState.QUESTION, question=next_question)

            return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)

        return self.to_url(FormRunnerState.TASKLIST)

    def validate(self) -> bool:
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
