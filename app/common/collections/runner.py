# todo: propose moving common/helper/collections.py to common/collections/submission.py
from typing import TYPE_CHECKING, ClassVar, Optional, Union, cast
from uuid import UUID

from flask import abort, url_for

from app.common.collections.forms import AddAnotherSummaryForm, CheckYourAnswersForm, build_question_form
from app.common.data import interfaces
from app.common.data.types import FormRunnerState, SubmissionStatusEnum, TRunnerUrlMap
from app.common.expressions import interpolate
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper

if TYPE_CHECKING:
    from app.common.collections.forms import DynamicQuestionForm
    from app.common.data.models import Form, Group, Question
    from app.common.data.models_user import User


class FormRunner:
    """Responsible for backing form runner pages, consistently takes care of:
        - managing routing backwards and forwards
        - integrity checks
        - setting up forms

    This allows us to implement the form runner in different domain environments consistently."""

    url_map: ClassVar[TRunnerUrlMap] = {}
    component: Optional[Union["Question", "Group"]]
    questions: list["Question"]

    def __init__(
        self,
        submission: SubmissionHelper,
        question: Optional["Question"] = None,
        form: Optional["Form"] = None,
        source: Optional["FormRunnerState"] = None,
        add_another_index: Optional[int] = None,
    ):
        if question and form:
            raise ValueError("Expected only one of question or form")

        self.submission = submission
        self.form = form
        self.source = source
        self.add_another_index = add_another_index

        # if we've navigated to a question that belongs to a group that show on the same page
        # pass the whole group into the form runner
        if question and question.parent and question.parent.same_page:
            self.component = question.parent
            # wip: this probably wants to happen inside with add another index rather than anywhere its consumed
            context = self.submission.cached_evaluation_context
            if self.add_another_index is not None:
                count = self.submission.get_count_for_add_another(self.component.add_another_container)
                # avoid the first time the page is loaded - imporant if its add another and a question group
                if self.add_another_index < count:
                    context = self.submission.cached_evaluation_context.with_add_another_context(question, self.submission, add_another_index=self.add_another_index)
            self.questions = self.submission.cached_get_ordered_visible_questions(self.component, override_context=context)
        else:
            self.component = question
            self.questions = [self.component] if self.component else []

        self._valid: Optional[bool] = None

        self._tasklist_form = GenericSubmitForm()
        self._question_form: Optional[DynamicQuestionForm] = None
        self._check_your_answers_form: Optional[CheckYourAnswersForm] = None
        self._add_another_summary_form: Optional[AddAnotherSummaryForm] = None

        self.add_another_summary_context = bool(
            (self.component and self.component.add_another_container) and self.add_another_index is None
        )

        if self.component:
            self.form = self.component.form

            if self.component and self.component.add_another_container and self.add_another_summary_context:
                _AddAnotherSummaryForm = AddAnotherSummaryForm(
                    add_another_required=bool(
                        self.submission.get_count_for_add_another(self.component.add_another_container)
                    )
                )
                self._add_another_summary_form = _AddAnotherSummaryForm
            else:
                _QuestionForm = build_question_form(
                    self.questions,
                    evaluation_context=self.submission.cached_evaluation_context,
                    interpolation_context=self.submission.cached_interpolation_context,
                )
                self._question_form = _QuestionForm(data=self.submission.cached_form_data(
                    add_another_container=self.component.add_another_container if self.component and self.add_another_index is not None else None,
                    add_another_index=self.add_another_index
                ))

        if self.form:
            all_questions_answered = self.submission.cached_get_all_questions_are_answered_for_form(
                self.form
            ).all_answered
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
        add_another_index: Optional[int] = None,
    ) -> "FormRunner":
        if question_id and form_id:
            raise ValueError("Expected only one of question_id or form_id")

        submission = SubmissionHelper.load(submission_id)

        # For test submissions, only the user who created the test submission should be able to preview it (we only
        # have test submissions for now.) When we come to have live submissions we can extend this check based on the
        # user's Organisation permissions.
        current_user = interfaces.user.get_current_user()
        if submission.created_by_email is not current_user.email:
            return abort(403)

        question, form = None, None

        if question_id:
            question = submission.get_question(question_id)
        elif form_id:
            form = submission.get_form(form_id)

        return cls(
            submission=submission,
            question=question,
            form=form,
            source=source,
            add_another_index=add_another_index,
        )

    @property
    def question_form(self) -> "DynamicQuestionForm":
        if not self.component or not self._question_form:
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

    @property
    def add_another_summary_form(self) -> "AddAnotherSummaryForm":
        if not self.component or not self._add_another_summary_form:
            raise RuntimeError("Add another summary context not set")
        return self._add_another_summary_form

    @property
    def question_with_add_another_summary_form(self) -> "DynamicQuestionForm | AddAnotherSummaryForm":
        return self.add_another_summary_form if self.add_another_summary_context else self.question_form

    def save_question_answer(self) -> None:
        if not self.component:
            raise RuntimeError("Question context not set")

        for question in self.questions:
            self.submission.submit_answer_for_question(question.id, self.question_form, add_another_index=self.add_another_index)

    def interpolate(self, text: str) -> str:
        return interpolate(text, context=self.submission.cached_interpolation_context)

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
        add_another_index: Optional[int] = None,
    ) -> str:
        # todo: resolve type hinting issues w/ circular dependencies and bringing in class for instance check
        # no default value for add another index as we want to clear it
        return self.url_map[state](self, question or self.component, form or self.form, source, add_another_index)  # type: ignore[arg-type]

    @property
    def next_url(self) -> str:
        if self.add_another_summary_context and self.component.add_another_container:
            if self.add_another_summary_form.validate_on_submit() and self.add_another_summary_form.add_another.data == "yes":
                # create a new entry and go to the first
                # wip: everywhere we're doing add another questions this will just be the default questions if the summary uses the container as the component
                add_another_questions = cast("Group", self.component.add_another_container).cached_questions if self.component.add_another_container.is_group else [ cast("Question", self.component.add_another_container) ]
                new_index = self.submission.get_count_for_add_another(self.component.add_another_container)
                return self.to_url(FormRunnerState.QUESTION, question=add_another_questions[0], add_another_index=new_index)
            else:
                # go to the question after this add another container
                # todo: extract this out as its used below into a little method
                last_question = cast("Group", self.component.add_another_container).cached_questions[-1] if self.component.add_another_container.is_group else cast("Question", self.component.add_another_container)
                next_question = self.submission.get_next_question(last_question.id)
                if self.source == FormRunnerState.CHECK_YOUR_ANSWERS:
                    while next_question and ((self.submission.cached_get_answer_for_question(next_question.id, add_another_index=self.add_another_index) is not None) if not next_question.add_another_container else (self.submission.get_count_for_add_another(next_question.add_another_container))):
                    # while next_question and self.submission.cached_get_answer_for_question(next_question.id) is not None:
                        next_question = self.submission.get_next_question(next_question.id)
                return (
                    self.to_url(FormRunnerState.QUESTION, question=next_question)
                    if next_question
                    else self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)
                ) 
    
        # if we're in the context of a question page, decide if we should go to the next question
        # or back to check your answers based on if the integrity checks pass
        if self.component:
            if not self._valid:
                return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)
        
            # todo: don't make this a complete fork
            if self.add_another_index is not None:
                # if we're the last question
                add_another_questions = cast("Group", self.component.add_another_container).cached_questions if self.component.add_another_container.is_group else [ cast("Question", self.component.add_another_container) ]
                
                # fixme: might need to just be self.component.is_group 
                # fixme: the last check here is absolutely scuffed - will be worked out by the refactor to make the container the component probably or having a consistent set of questions
                if self.component == add_another_questions[-1] or (self.component.is_group and self.component.add_another_container == self.component) or (self.component.is_group and self.questions[-1] == add_another_questions[-1]):
                    # go to the add another summary
                    return self.to_url(FormRunnerState.QUESTION, question=self.component if not self.component.is_group else add_another_questions[0], add_another_index=None)

                # don't skip empty answers when going back through an add another for now
                last_question = self.questions[-1] if self.component.is_group else self.component
                next_question = self.submission.get_next_question(last_question.id, add_another_index=self.add_another_index)

                return (self.to_url(FormRunnerState.QUESTION, question=next_question, add_another_index=self.add_another_index))

            last_question = self.questions[-1] if self.component.is_group else self.component
            next_question = self.submission.get_next_question(last_question.id)

            # Regardless of where they're from (eg even check-your-answers), take them to the next unanswered question
            # this will let users stay in a data-submitting flow if they've changed a conditional answer which has
            # unlocked more questions.

            # todo: what does it mean to check this for an add another question? is it that the count of its answers is more than 0?
            #       actively within a group is probably different
            # wip: for now we're definitely not in an index when we're at this stage

            # todo: this feels like it should only be skipping if we've come from the check your answers page? otherwise the user might expect to step through the form
            # fixme: this changes behaviour for the current form runner dont do it here but get this changed
            if self.source == FormRunnerState.CHECK_YOUR_ANSWERS:
                while next_question and ((self.submission.cached_get_answer_for_question(next_question.id, add_another_index=self.add_another_index) is not None) if not next_question.add_another_container else (self.submission.get_count_for_add_another(next_question.add_another_container))):
                    next_question = self.submission.get_next_question(next_question.id)

            return (
                self.to_url(FormRunnerState.QUESTION, question=next_question, add_another_index=self.add_another_index)
                if next_question
                else self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)
            )

        # default back to the tasklist if we're routing forward outside of a question context (check your answers)
        return self.to_url(FormRunnerState.TASKLIST)

    def validate_can_show_question_page(self) -> bool:
        # for now we're only validating the question state, there may be integrity
        # checks for check your answers or tasklist in the future
        if not self.component:
            raise ValueError("Question context not set")

        if not self.submission.is_component_visible(self.component, self.submission.cached_evaluation_context):
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

        # wip: this could be streamlined possibly by always putting us on the first question in the container or something
        if self.add_another_summary_context and self.component.add_another_container:
            # wip: it would be helpful if this was already part of the runner init - this probably works if the container is made the main component
            add_another_questions = cast("Group", self.component.add_another_container).cached_questions if self.component.add_another_container.is_group else [ cast("Question", self.component.add_another_container) ]
            previous_question = self.submission.get_previous_question(add_another_questions[0].id)
            if previous_question:
                return self.to_url(FormRunnerState.QUESTION, question=previous_question)

        # wip: this would change if the component was the add another container 
        if self.add_another_index is not None:
            # todo: a lot of this needs simplifying by reasoning about what should be set as the primrary component when on an add another summary
            add_another_questions = cast("Group", self.component.add_another_container).cached_questions if self.component.add_another_container.is_group else [ cast("Question", self.component.add_another_container) ]

            # it will be a group if its showing on the same page
            if self.component == add_another_questions[0] or (self.component.is_group and self.component == self.component.add_another_container):
                # we're at the first question in the add another set, go back to the summary
                return self.to_url(FormRunnerState.QUESTION, question=self.component if not self.component.is_group else add_another_questions[0], add_another_index=None)


        if self.component:
            # todo: fixme: wip: is this a fix needed for same page groups in general - the change here 
            #       is that if the first question is conditional it might not consistently navigate - probably true of the last question too
            # update: the fixe is probably wrong
            # first_question = self.component.cached_questions[0] if self.component.is_group else self.component
            first_question = self.questions[0] if self.component.is_group else self.component
            previous_question = self.submission.get_previous_question(first_question.id, add_another_index=self.add_another_index)
        elif self.form:
            previous_question = self.submission.get_last_question_for_form(self.form)
        else:
            previous_question = None
        if previous_question:
            return self.to_url(FormRunnerState.QUESTION, question=previous_question, add_another_index=self.add_another_index)

        return self.to_url(FormRunnerState.TASKLIST)


class DGFFormRunner(FormRunner):
    url_map: ClassVar[TRunnerUrlMap] = {
        FormRunnerState.QUESTION: lambda runner, question, _form, source, add_another_index: url_for(
            "deliver_grant_funding.ask_a_question",
            grant_id=runner.submission.grant.id,
            submission_id=runner.submission.id,
            question_id=question.id if question else None,
            source=source,
            add_another_index=add_another_index
        ),
        FormRunnerState.TASKLIST: lambda runner, _question, _form, _source, _add_another_index: url_for(
            "deliver_grant_funding.submission_tasklist",
            grant_id=runner.submission.grant.id,
            submission_id=runner.submission.id,
            form_id=runner.form.id if runner.form else None,
        ),
        FormRunnerState.CHECK_YOUR_ANSWERS: lambda runner, _question, form, source, _add_another_index: url_for(
            "deliver_grant_funding.check_your_answers",
            grant_id=runner.submission.grant.id,
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
