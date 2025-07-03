# todo: propose moving common/helper/collections.py to common/collections/submission.py
from typing import TYPE_CHECKING, Callable, ClassVar, Optional
from uuid import UUID

from flask import request

from app.common.collections.forms import build_question_form
from app.common.data.types import FormRunnerState, SubmissionStatusEnum
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper
from app.developers.forms import CheckYourAnswersForm
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
    question: Optional["Question"] = None

    def __init__(self, submission: SubmissionHelper):
        self.submission = submission

        # todo: decide if this should be passed in the context setter to fully separate this from the flask context
        self.source = request.args.get("source", None)

        self._tasklist_form = GenericSubmitForm()

    @classmethod
    def load(cls, submission_id: UUID) -> "FormRunner":
        return cls(SubmissionHelper.load(submission_id))

    # todo: I think - accept source as a named argument and expect that this is always called
    # todo: separate out to an internal method to set up the forms
    def context(self, *, question_id: Optional[UUID] = None, form_id: Optional[UUID] = None) -> "FormRunner":
        if question_id and form_id:
            raise ValueError("Expected only one of question_id or form_id")

        if question_id:
            self.question = self.submission.get_question(question_id)
            self.form = self.question.form

            context = self.submission.expression_context
            self._question_form = build_question_form(self.question, context)(data=context)
        if form_id:
            self.question = None
            self.form = self.submission.get_form(form_id)

            all_questions_answered, _ = self.submission.get_all_questions_are_answered_for_form(self.form)

            self._check_your_answers_form = CheckYourAnswersForm(
                section_completed=(
                    "yes" if self.submission.get_status_for_form(self.form) == SubmissionStatusEnum.COMPLETED else None
                )
            )
            self._check_your_answers_form.set_is_required(all_questions_answered)

        return self

    @property
    def question_form(self) -> "DynamicQuestionForm":
        if not self.question:
            raise ValueError("Question context not set")
        return self._question_form

    @property
    def check_your_answers_form(self) -> "CheckYourAnswersForm":
        return self._check_your_answers_form

    @property
    def tasklist_form(self) -> "GenericSubmitForm":
        return self._tasklist_form

    def save_question_answer(self) -> None:
        if not self.question:
            raise ValueError("Question context not set")

        self.submission.submit_answer_for_question(self.question.id, self.question_form)

    # todo: the standard pattern in http controllers is to handle something raised - I think this should
    #       follow that and raise here, no reason the form error management can't be taken care of here
    # todo: the name is wrong
    def save_is_form_completed(self, user: "User") -> bool:
        try:
            self.submission.toggle_form_completed(
                form=self.form,
                user=user,
                is_complete=self.check_your_answers_form.section_completed.data == "yes",
            )
            return True
        except ValueError:
            self.check_your_answers_form.section_completed.errors.append(  # type:ignore[attr-defined]
                "You must complete all questions before marking this section as complete"
            )
            return False

    # todo: should this raise from the value error rather than returning
    def submit(self, user: "User") -> bool:
        try:
            self.submission.submit(user)
            notification_service.send_collection_submission(self.submission.submission)
            return True
        except ValueError:
            self._tasklist_form.submit.errors.append("You must complete all forms before submitting the collection")  # type:ignore[attr-defined]
            return False

    def to_url(
        self,
        state: FormRunnerState,
        *,
        question: Optional["Question"] = None,
        form: Optional["Form"] = None,
        source: Optional[FormRunnerState] = None,
    ) -> str:
        return self.url_map[state](self, question or self.question, form, source)

    # todo: with a consistent context setting at the start this should change to
    #       is _valid None, True or False - act based on that
    @property
    def next_url(self) -> str:
        # todo: this probably doesn't need to managed by this helper and could be done in the template
        # but i guess its consistent
        if not self.question:
            return self.to_url(FormRunnerState.TASKLIST)

        # the options here would be validation has run and is true or false
        # or validation has not run
        if self._valid:
            if self.source == FormRunnerState.CHECK_YOUR_ANSWERS:
                return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)

            next_question = self.submission.get_next_question(self.question.id)
            if next_question:
                return self.to_url(FormRunnerState.QUESTION, question=next_question)

            return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)
        else:
            # for now check your answers is the only place we go so could remove
            # the internal _next state for now
            return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)

    def validate(self) -> bool:
        context = self.submission.expression_context

        # if we're loading in a question context
        if self.question:
            # make sure the question is answerable
            if not self.submission.is_question_visible(self.question, context):
                # could flash here if we wanted to to make it clear to the user
                self._valid = False
                self._next = FormRunnerState.CHECK_YOUR_ANSWERS
                return self._valid

            # make sure the submission hasn't already been completed
            if self.submission.is_completed:
                self._valid = False
                self._next = FormRunnerState.CHECK_YOUR_ANSWERS
                return self._valid

            self._valid = True
            return self._valid

        return True

    # todo: it looks like this logic was gearing up to model more complex scenarios
    #       but for now this is just a question or tasklist so a few can be removed
    @property
    def back_url(self) -> str:
        # if not self.source:
        #     return None

        if self.source == FormRunnerState.QUESTION and self.question:
            return self.to_url(FormRunnerState.QUESTION, question=self.question)
        # todo: to get the desired return to tasklist on check your answers page this
        #       could also check we're not in a question page state and then we propegate
        #       the source as you step through
        elif self.source == FormRunnerState.TASKLIST:
            return self.to_url(FormRunnerState.TASKLIST)
        elif self.source == FormRunnerState.CHECK_YOUR_ANSWERS:
            return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)

        if self.question:
            previous_question = self.submission.get_previous_question(self.question.id)
        else:
            previous_question = self.submission.get_last_question_for_form(self.form)
        if previous_question:
            return self.to_url(FormRunnerState.QUESTION, question=previous_question)

        return self.to_url(FormRunnerState.TASKLIST)
