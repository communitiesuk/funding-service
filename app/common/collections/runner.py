# todo: propose moving common/helper/collections.py to common/collections/submission.py
from typing import TYPE_CHECKING, ClassVar, Optional, Union
from uuid import UUID

from flask import abort, url_for

from app.common.collections.forms import AddAnotherForm, CheckYourAnswersForm, build_question_form
from app.common.data import interfaces
from app.common.data.types import FormRunnerState, SubmissionStatusEnum, TRunnerUrlMap
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
            self.questions = self.submission.cached_get_ordered_visible_questions(self.component)

        # here wants to differentiatae between a group page loading the add another check page and a question itself being loaded
        elif question and question.parent and question.parent.is_add_another and self.add_another_index is None:
            self.component = question.parent
            # todo: this could pass in the index which _could_ allow conditions to reference quesstions within their loop
            self.questions = self.submission.cached_get_ordered_visible_questions(self.component)
        else:
            self.component = question
            self.questions = [self.component] if self.component else []

            # todo: mutating the state here feels a bit gnarly but there are _so_ many places we access safe qid which would
            #       need to be done uniformly - whats the trade of, is there a nicer pattern for working this out
            #       the index we're interested in is really only known at runtime (not generically when fetched from the db)
            # todo: needs to think through if this needs to happen for all questions if its a group - probably
            if self.component:
                self.component.add_another_index = add_another_index if add_another_index else None

        self._valid: Optional[bool] = None

        self._tasklist_form = GenericSubmitForm()
        self._question_form: Optional[DynamicQuestionForm] = None
        self._check_your_answers_form: Optional[CheckYourAnswersForm] = None

        if self.component:
            self.form = self.component.form
            _QuestionForm = build_question_form(
                self.questions, self.submission.cached_expression_context, add_another_index=self.add_another_index
            )
            self._question_form = _QuestionForm(data=self.submission.cached_form_data)

            if self.component.is_add_another and not self.add_another_index:
                is_group_first = self.component.is_group and not self.submission.get_count_group_total(
                    self.component.id
                )
                self._add_another_form = AddAnotherForm(is_group_first=is_group_first)

        if self.form:
            all_questions_answered, _ = self.submission.cached_get_all_questions_are_answered_for_form(self.form)
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
            # it would be nice to assert this is a question any time that its not an add another list page
            # question = submission.get_component(question_id)
            question = submission.get_question(question_id)
        elif form_id:
            form = submission.get_form(form_id)

        return cls(
            submission=submission, question=question, form=form, source=source, add_another_index=add_another_index
        )

    @property
    def question_form(self) -> "DynamicQuestionForm":
        if not self.component or not self._question_form:
            raise RuntimeError("Question context not set")
        return self._question_form

    @property
    def add_another_form(self) -> "AddAnotherForm":
        if not self.component:
            raise RuntimeError("Question context not set")
        return self._add_another_form

    @property
    def check_your_answers_form(self) -> "CheckYourAnswersForm":
        if not self.form or not self._check_your_answers_form:
            raise RuntimeError("Form context not set")
        return self._check_your_answers_form

    @property
    def tasklist_form(self) -> "GenericSubmitForm":
        return self._tasklist_form

    def save_question_answer(self) -> None:
        if not self.component:
            raise RuntimeError("Question context not set")

        # presume the runner knows the list ID/ index by the time its loading up the question form
        # either its new and there is no ID/ index or its adding multiple questions to a given identifier or updating a known answer
        for question in self.questions:
            add_another_group_id = None
            if self.component.parent and self.component.parent.is_group and self.add_another_index is not None:
                add_another_group_id = self.component.parent.id
            if self.component.is_group and self.component.add_another and self.add_another_index is not None:
                add_another_group_id = self.component.id
            self.submission.submit_answer_for_question(
                question.id,
                self.question_form,
                add_another_index=self.add_another_index,
                add_another_group_id=add_another_group_id,
            )

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
        return self.url_map[state](self, question or self.component, form or self.form, source, add_another_index)  # type: ignore[arg-type]

    @property
    def next_url(self) -> str:
        # if we're in the context of a question page, decide if we should go to the next question
        # or back to check your answers based on if the integrity checks pass
        if self.component:
            last_question = self.questions[-1] if self.component.is_group else self.component

            if self._valid is False:
                # now the direct link to add another question is handled here - the comment below isn't fully correct
                if self.component.is_add_another or last_question.is_add_another:
                    # todo: this will need to updated for working with groups
                    if self.component.is_add_another and not self.component.is_group:
                        # todo: this should check if the question answer has a length
                        answer = self.submission.cached_get_answer_for_question(self.component.id)

                        # we'll go straight to the question if its simpler and not part of a group
                        # for group specific behaviour - a question won't be add another specifically if its part of an add another group
                        # the "add to a list" behaviour should start on the list page to give you context thats what you're doing
                        if not answer and self.component.add_another:
                            return self.to_url(FormRunnerState.QUESTION, question=last_question, add_another_index=0)

                        # we'll always go to the list first when adding multiple structured bits of data, the page should reflect that
                        # (likely group name heading at the top, a paragraph saying you haven't added anything, or how many you've added)
                        if self.component.parent:
                            # need to decide if this is desirable or not, we probably do want any "change" within the group to end up here
                            return self.to_url(
                                FormRunnerState.CHECK_ADD_ANOTHER, question=self.component, source=self.source
                            )
                    return self.to_url(FormRunnerState.CHECK_ADD_ANOTHER, question=last_question, source=self.source)
                else:
                    return self.to_url(FormRunnerState.CHECK_YOUR_ANSWERS)

            # navigates for both if the index is set or not (if we've linked directly to the question and its not valid to show the question page)
            # todo: this will need to be thought through for if its a group and is stepping through questions _with_ an index
            #       thats then probably checking for something breaking out of that group or something
            # todo: is this the thing that decides to forward you on to answering the first question if its _not_ a group
            if self.component.is_add_another or last_question.is_add_another:
                # routing for groups will need to be a bit more sophisticated
                if self.add_another_index is not None:
                    # fixme: there will be a crossover of same page and add another that won't be covered here which will need thinking through
                    # fixme: right now same page means everything has to be asked at once - if you can have group in a group this logic will need to be more robust
                    if self.component.parent and not self.component.parent.same_page:
                        next_question = self.submission.get_next_question(last_question.id)

                        while (
                            next_question
                            and self.submission.cached_get_answer_for_question(next_question.id) is not None
                        ):
                            next_question = self.submission.get_next_question(next_question.id)

                        return (
                            self.to_url(
                                FormRunnerState.QUESTION,
                                question=next_question,
                                add_another_index=self.add_another_index,
                            )
                            if next_question and next_question.parent == self.component.parent
                            else self.to_url(FormRunnerState.CHECK_ADD_ANOTHER, question=self.component)
                        )

                    # we'll go to the check add another
                    # this _feels_ like its runner specific and the submission should focus on the next logical quqestion
                    return self.to_url(FormRunnerState.CHECK_ADD_ANOTHER, question=last_question)
                elif self.add_another_form.validate_on_submit() and self.add_another_form.add_another.data == "yes":
                    # todo: this should be calculated somewhere thats easy to cover and tweak based on business logic
                    # todo: how we're getting the answer for groups and checking its valid etc. needs to be thought through
                    # this is always a list by this point although types will need some convincing

                    # todo: this should use a generic count that could be used by a structured group or simple list
                    if self.component.is_group:
                        new_index = self.submission.get_count_group_total(self.component.id)
                    else:
                        answer = self.submission.cached_get_answer_for_question(self.component.id)
                        new_index = len(answer) if answer else 0

                    # todo: this will have to do something to point to the _first_ question in the group
                    #       if it is a group but for now it can just go to the question with a newly created index
                    return self.to_url(
                        FormRunnerState.QUESTION, question=self.questions[0], add_another_index=new_index
                    )
                elif self.component.is_group and not self.submission.get_count_group_total(self.component.id):
                    # kick off the first answer
                    return self.to_url(FormRunnerState.QUESTION, question=self.questions[0], add_another_index=0)

                # else:
            next_question = self.submission.get_next_question(last_question.id)

            # Regardless of where they're from (eg even check-your-answers), take them to the next unanswered question
            # this will let users stay in a data-submitting flow if they've changed a conditional answer which has
            # unlocked more questions.
            while next_question and self.submission.cached_get_answer_for_question(next_question.id) is not None:
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
        if not self.component:
            raise ValueError("Question context not set")

        # this feels like a workaround and might have a clearer way of being represented
        # (current best guess is the question page just doubles up as the check add another page)
        # but this should work for now
        # we've been navigated to but don't have a index into the data
        if self.component.is_add_another and self.add_another_index is None:
            self._valid = False
            return self._valid

        context = self.submission.cached_expression_context

        if not self.submission.is_component_visible(self.component, context):
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

        if self.component:
            first_question = self.questions[0] if self.component.is_group else self.component
            if self.component.parent and self.component.parent.add_another:
                previous_question = self.submission.get_previous_question(first_question.id)
                if previous_question and (previous_question.parent == self.component.parent):
                    return self.to_url(
                        FormRunnerState.QUESTION, question=previous_question, add_another_index=self.add_another_index
                    )

            # todo: this will need to factor in more scenarios if its a group but for now
            if self.component.is_add_another and self.add_another_index is not None:
                return self.to_url(FormRunnerState.CHECK_ADD_ANOTHER, question=self.component)

            previous_question = self.submission.get_previous_question(first_question.id)
        elif self.form:
            previous_question = self.submission.get_last_question_for_form(self.form)
        else:
            previous_question = None
        if previous_question:
            return self.to_url(FormRunnerState.QUESTION, question=previous_question)

        return self.to_url(FormRunnerState.TASKLIST)


class DGFFormRunner(FormRunner):
    url_map: ClassVar[TRunnerUrlMap] = {
        FormRunnerState.QUESTION: lambda runner, question, _form, source, add_another_index: url_for(
            "deliver_grant_funding.ask_a_question",
            grant_id=runner.submission.grant.id,
            submission_id=runner.submission.id,
            question_id=question.id if question else None,
            source=source,
            add_another_index=add_another_index,
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
        FormRunnerState.CHECK_ADD_ANOTHER: lambda runner, question, _form, source, _add_another_index: url_for(
            "deliver_grant_funding.check_add_another",
            grant_id=runner.submission.grant.id,
            submission_id=runner.submission.id,
            question_id=question.id if question else None,
            source=source,
        ),
    }


class AGFFormRunner(FormRunner):
    url_map: ClassVar[TRunnerUrlMap] = {
        FormRunnerState.QUESTION: lambda runner, question, _form, source, add_another_index: url_for(
            "developers.access.ask_a_question",
            submission_id=runner.submission.id,
            question_id=question.id if question else None,
            source=source,
            add_another_index=add_another_index,
        ),
        FormRunnerState.TASKLIST: lambda runner, _question, _form, _source, _add_another_index: url_for(
            "developers.access.submission_tasklist",
            submission_id=runner.submission.id,
            form_id=runner.form.id if runner.form else None,
        ),
        FormRunnerState.CHECK_YOUR_ANSWERS: lambda runner, _question, form, source, _add_another_index: url_for(
            "developers.access.check_your_answers",
            submission_id=runner.submission.id,
            form_id=form.id if form else runner.form.id if runner.form else None,
            source=source,
        ),
    }
