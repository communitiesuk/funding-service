# todo: propose moving common/helper/collections.py to common/collections/submission.py
from typing import TYPE_CHECKING, ClassVar, Optional, Union, cast
from uuid import UUID

from flask import abort, current_app, url_for

from app.common.collections.forms import (
    AddAnotherSummaryForm,
    CheckYourAnswersForm,
    ConfirmRemoveAddAnotherForm,
    build_question_form,
)
from app.common.data import interfaces
from app.common.data.types import FormRunnerState, TasklistSectionStatusEnum, TRunnerUrlMap
from app.common.exceptions import RedirectException, SubmissionValidationFailed
from app.common.expressions import interpolate
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper

if TYPE_CHECKING:
    from app.common.collections.forms import DynamicQuestionForm
    from app.common.data.models import Form, Group, Question
    from app.common.data.models_user import User
    from app.common.expressions import ExpressionContext


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
        is_removing: bool = False,
    ):
        if question and form:
            raise ValueError("Expected only one of question or form")

        self.submission = submission
        self.form = form
        self.source = source
        self.add_another_index = add_another_index
        self.is_removing = is_removing

        self._valid: Optional[bool] = None

        self._tasklist_form = GenericSubmitForm()
        self._question_form: Optional[DynamicQuestionForm] = None
        self._check_your_answers_form: Optional[CheckYourAnswersForm] = None
        self._add_another_summary_form: Optional[AddAnotherSummaryForm] = None
        self._confirm_remove_form: Optional[ConfirmRemoveAddAnotherForm] = None

        self.add_another_summary_context = bool(
            (question and question.add_another_container) and self.add_another_index is None
        )

        if (
            self.add_another_summary_context and question and question.add_another_container
        ):  # redundant checks are for type narrowing
            self.component = cast("Question | Group", question.add_another_container)
            self.questions = (
                self.submission.cached_get_ordered_visible_questions(self.component)
                if self.component.is_group
                else [cast("Question", self.component)]
            )
        elif question and question.parent and question.parent.same_page:
            # if we've navigated to a question that belongs to a group that show on the same page
            # pass the whole group into the form runner
            self.component = question.parent
            self.questions = self.submission.cached_get_ordered_visible_questions(
                self.component,
                override_context=self.runner_evaluation_context if self.add_another_index is not None else None,
            )
        else:
            self.component = question
            self.questions = [self.component] if self.component else []

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
                # todo: cleanup this chain of logic to make this read more straight
                #       forwardly now that we have all the moving pieces
                if self.is_removing:
                    self._confirm_remove_form = ConfirmRemoveAddAnotherForm()
                else:
                    _QuestionForm = build_question_form(
                        self.questions,
                        evaluation_context=self.runner_evaluation_context,
                        interpolation_context=self.runner_interpolation_context,
                    )
                    self._question_form = _QuestionForm(
                        data=self.submission.form_data(
                            add_another_container=self.component.add_another_container
                            if self.component and self.add_another_index is not None
                            else None,
                            add_another_index=self.add_another_index,
                        )
                    )

        if self.form:
            all_questions_answered = self.submission.cached_get_all_questions_are_answered_for_form(
                self.form
            ).all_answered
            self._check_your_answers_form = CheckYourAnswersForm(
                section_completed=(
                    "yes"
                    if self.submission.get_status_for_form(self.form) == TasklistSectionStatusEnum.COMPLETED
                    else None
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
        grant_recipient_id: Optional[UUID] = None,
        is_removing: bool = False,
    ) -> "FormRunner":
        if question_id and form_id:
            raise ValueError("Expected only one of question_id or form_id")

        submission = SubmissionHelper.load(submission_id, grant_recipient_id=grant_recipient_id)

        # For test submissions, only the user who created the test submission should be able to preview it (we only
        # have test submissions for now.) When we come to have live submissions we can extend this check based on the
        # user's Organisation permissions.
        current_user = interfaces.user.get_current_user()

        # todo: rejecting based on the user who created it was based on pre-award logic
        #       functionality for monitoring likely covered by route decorators but making sure should
        #       be separated out into a story
        if submission.submission.grant_recipient is None and submission.created_by_email is not current_user.email:
            if submission.is_preview:
                current_app.logger.warning(
                    "User %(user_id)s tried to access submission for %(submitter_id)s, redirecting",
                    {"user_id": current_user.id, "submitter_id": submission.submission.created_by_id},
                )
                raise RedirectException(
                    url_for(
                        "deliver_grant_funding.list_report_sections",
                        grant_id=submission.collection.grant_id,
                        report_id=submission.collection_id,
                    )
                )

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
            is_removing=is_removing,
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
    def confirm_remove_form(self) -> "ConfirmRemoveAddAnotherForm":
        if not self.component or not self._confirm_remove_form:
            raise RuntimeError("Confirm remove context not set")
        return self._confirm_remove_form

    @property
    def question_with_add_another_summary_form(
        self,
    ) -> "DynamicQuestionForm | AddAnotherSummaryForm | ConfirmRemoveAddAnotherForm":
        if self.is_removing:
            return self.confirm_remove_form
        return self.add_another_summary_form if self.add_another_summary_context else self.question_form

    def save_question_answer(self) -> None:
        if not self.component:
            raise RuntimeError("Question context not set")

        for question in self.questions:
            self.submission.submit_answer_for_question(
                question.id, self.question_form, add_another_index=self.add_another_index
            )

    def save_add_another(self) -> None:
        if self.add_another_index is None or not (self.component and self.component.add_another_container):
            raise RuntimeError("Add another context not set")

        if self.is_removing:
            if self.confirm_remove_form.validate_on_submit():
                if self.confirm_remove_form.confirm_remove.data == "yes":
                    interfaces.collections.remove_add_another_answers_at_index(
                        submission=self.submission.submission,
                        add_another_container=self.component.add_another_container,
                        add_another_index=self.add_another_index,
                    )

    def interpolate(self, text: str, *, context: "ExpressionContext | None" = None) -> str:
        return interpolate(text, context=context or self.runner_interpolation_context)

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
                "You must complete all questions before marking this section as complete"
            )
            return False

    def complete_submission(self, user: "User") -> bool:
        try:
            if self.submission.collection.requires_certification:
                self.submission.mark_as_sent_for_certification(user)

            else:
                self.submission.submit(user)
            return True
        except SubmissionValidationFailed as e:
            self._tasklist_form.submit.errors.append(e.error_message)  # type:ignore[attr-defined]
            return False
        except ValueError:
            current_app.logger.warning(
                "ValueError when submitting id %(submission_id)s",
                exc_info=True,
                extra={"submission_id": str(self.submission.id)},
            )
            self._tasklist_form.submit.errors.append("You must complete all sections before submitting")  # type:ignore[attr-defined]
            return False

    def to_url(
        self,
        state: FormRunnerState,
        *,
        question: Optional["Question"] = None,
        form: Optional["Form"] = None,
        source: Optional[FormRunnerState] = None,
        add_another_index: Optional[int] = None,
        is_removing: Optional[bool] = None,
    ) -> str:
        # todo: resolve type hinting issues w/ circular dependencies and bringing in class for instance check
        return self.url_map[state](
            self,
            question or self.component,  # type: ignore[arg-type]
            form or self.form,
            source,
            add_another_index,
            is_removing,
        )

    @property
    def next_url(self) -> str:
        if self.add_another_summary_context and self.component and self.component.add_another_container:
            if (
                self.add_another_summary_form.validate_on_submit()
                and self.add_another_summary_form.add_another.data == "yes"
            ):
                new_index = self.submission.get_count_for_add_another(self.component.add_another_container)
                return self.to_url(FormRunnerState.QUESTION, question=self.questions[0], add_another_index=new_index)

        if self.is_removing and self.component and self.component.add_another_container:
            return self.to_url(FormRunnerState.QUESTION, question=self.questions[0], add_another_index=None)

        # if we're in the context of a question page, decide if we should go to the next question
        # or back to check your answers based on if the integrity checks pass
        if self.component:
            if not self._valid:
                return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)

            last_question = self.questions[-1] if self.component.is_group else self.component
            next_question = self.submission.get_next_question(
                last_question.id, add_another_index=self.add_another_index
            )

            # for now we'll always sequentially step through add another questions - this could be refined when we
            # refactor the "skip" logic below or move to using a check an add another entries details pattern
            if self.add_another_index is not None:
                if (next_question and next_question.add_another_container) != self.component.add_another_container:
                    # we've moved out of this add another context, return to the summary page
                    # todo: includes a check if we should back to check your answers - when the skip logic below
                    #       also includes this check we should defer to that logic
                    return (
                        self.to_url(FormRunnerState.QUESTION, question=self.questions[0], add_another_index=None)
                        if self.source != FormRunnerState.CHECK_YOUR_ANSWERS
                        else self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)
                    )
                else:
                    return self.to_url(
                        FormRunnerState.QUESTION, question=next_question, add_another_index=self.add_another_index
                    )

            # Regardless of where they're from (eg even check-your-answers), take them to the next unanswered question
            # this will let users stay in a data-submitting flow if they've changed a conditional answer which has
            # unlocked more questions.
            while next_question and (
                # skip questions that have already been answered
                (self.submission.cached_get_answer_for_question(next_question.id) is not None)
                # only if we know exactly which answer to check (its not add another)
                if not next_question.add_another_container
                # otherwise for add another questions skip if we've got at least one entry
                else (self.submission.get_count_for_add_another(next_question.add_another_container))
            ):
                next_question = self.submission.get_next_question(
                    next_question.id,
                    add_another_index=self.add_another_index
                    if next_question.add_another_container == self.component.add_another_container
                    else None,
                )

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

        if not self.submission.is_component_visible(self.component, self.runner_evaluation_context):
            self._valid = False
        elif self.submission.is_locked_state:
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

        if self.component:
            first_question = self.questions[0] if self.component.is_group else self.component
            previous_question = self.submission.get_previous_question(
                first_question.id, add_another_index=self.add_another_index
            )
        elif self.form:
            previous_question = self.submission.get_last_question_for_form(self.form)
        else:
            previous_question = None

        if previous_question:
            if (
                self.add_another_index is not None
                and self.component
                and previous_question.add_another_container != self.component.add_another_container
            ):
                # we've moved out of this add another context, return to the summary page
                return self.to_url(FormRunnerState.QUESTION, question=self.questions[0], add_another_index=None)
            else:
                return self.to_url(
                    FormRunnerState.QUESTION, question=previous_question, add_another_index=self.add_another_index
                )

        if self.add_another_index is not None:
            # todo: first question in the form so no previous questions, this should be encapsulated better above
            return self.to_url(FormRunnerState.QUESTION, question=self.questions[0], add_another_index=None)

        return self.to_url(FormRunnerState.TASKLIST)

    @property
    def question_page_heading(self) -> str | None:
        if not self.component:
            raise RuntimeError("Question context not set")

        # the question form will be used a heading if its a single question
        # groups of questions on the same page or questions with guidance will show headings
        heading = None
        if self.component.guidance_heading:
            heading = self.component.guidance_heading
        elif self.component.is_group:
            heading = self.component.name

        # we only want to show the add another index context on the heading if the add another container
        # is itself on the same page
        if heading and self.add_another_index is not None and self.component == self.component.add_another_container:
            heading = add_another_suffix(heading, self.add_another_index)

        return heading

    @property
    def question_page_caption(self) -> str:
        if not self.component:
            raise RuntimeError("Question context not set")

        caption = self.component.form.title

        # we'll show the add another context if its set, and all of the add another questions aren't on the same page
        if (
            self.add_another_index is not None
            and self.component.add_another_container
            and self.component != self.component.add_another_container
        ):
            caption = add_another_suffix(self.component.add_another_container.name, self.add_another_index)
        return caption

    @property
    def runner_evaluation_context(self) -> "ExpressionContext":
        if self.add_another_index is not None and self.component and self.component.add_another_container:
            return self.submission.cached_evaluation_context.with_add_another_context(
                self.component,
                submission_helper=self.submission,
                add_another_index=self.add_another_index,
                allow_new_index=True,
            )
        return self.submission.cached_evaluation_context

    @property
    def runner_interpolation_context(self) -> "ExpressionContext":
        if self.add_another_index is not None and self.component and self.component.add_another_container:
            return self.submission.cached_interpolation_context.with_add_another_context(
                self.component,
                submission_helper=self.submission,
                add_another_index=self.add_another_index,
                mode="interpolation",
                allow_new_index=True,
            )
        return self.submission.cached_interpolation_context


def add_another_suffix(heading: str, add_another_index: int) -> str:
    return f"{heading} ({add_another_index + 1})"


class DGFFormRunner(FormRunner):
    url_map: ClassVar[TRunnerUrlMap] = {
        FormRunnerState.QUESTION: lambda runner, question, _form, source, add_another_index, is_removing: url_for(
            "deliver_grant_funding.ask_a_question",
            grant_id=runner.submission.grant.id,
            submission_id=runner.submission.id,
            question_id=question.id if question else None,
            source=source,
            add_another_index=add_another_index,
            action="remove" if is_removing else None,
        ),
        FormRunnerState.TASKLIST: lambda runner, _question, _form, _source, _add_another_index, _is_removing: url_for(
            "deliver_grant_funding.submission_tasklist",
            grant_id=runner.submission.grant.id,
            submission_id=runner.submission.id,
            form_id=runner.form.id if runner.form else None,
        ),
        FormRunnerState.CHECK_YOUR_ANSWERS: lambda runner,
        _question,
        form,
        source,
        _add_another_index,
        _is_removing: url_for(
            "deliver_grant_funding.check_your_answers",
            grant_id=runner.submission.grant.id,
            submission_id=runner.submission.id,
            form_id=form.id if form else runner.form.id if runner.form else None,
            source=source,
        ),
    }


class AGFFormRunner(FormRunner):
    url_map: ClassVar[TRunnerUrlMap] = {
        FormRunnerState.QUESTION: lambda runner, question, _form, source, add_another_index, is_removing: url_for(
            "access_grant_funding.ask_a_question",
            organisation_id=runner.submission.submission.grant_recipient.organisation.id,
            grant_id=runner.submission.submission.grant_recipient.grant.id,
            submission_id=runner.submission.id,
            question_id=question.id if question else None,
            source=source,
            add_another_index=add_another_index,
            action="remove" if is_removing else None,
        ),
        FormRunnerState.TASKLIST: lambda runner, _question, _form, _source, _add_another_index, _is_removing: url_for(
            "access_grant_funding.tasklist",
            organisation_id=runner.submission.submission.grant_recipient.organisation.id,
            grant_id=runner.submission.submission.grant_recipient.grant.id,
            submission_id=runner.submission.id,
        ),
        FormRunnerState.CHECK_YOUR_ANSWERS: lambda runner,
        _question,
        form,
        source,
        _add_another_index,
        _is_removing: url_for(
            "access_grant_funding.check_your_answers",
            organisation_id=runner.submission.submission.grant_recipient.organisation.id,
            grant_id=runner.submission.submission.grant_recipient.grant.id,
            submission_id=runner.submission.id,
            section_id=form.id if form else runner.form.id if runner.form else None,
            source=source,
        ),
    }
