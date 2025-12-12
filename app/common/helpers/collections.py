import csv
import json
import uuid
from datetime import date, datetime
from functools import cached_property, lru_cache, partial
from io import StringIO
from itertools import chain
from typing import TYPE_CHECKING, Any, Callable, List, NamedTuple, Optional, Union, cast
from uuid import UUID

from flask import current_app
from pydantic import BaseModel as PydanticBaseModel
from pydantic import TypeAdapter

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.collections.forms import DynamicQuestionForm
from app.common.collections.types import (
    NOT_ANSWERED,
    NOT_ASKED,
    AllAnswerTypes,
    ChoiceDict,
    DateAnswer,
    EmailAnswer,
    IntegerAnswer,
    MultipleChoiceFromListAnswer,
    SingleChoiceFromListAnswer,
    TextMultiLineAnswer,
    TextSingleLineAnswer,
    UrlAnswer,
    YesNoAnswer,
)
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    get_all_submissions_with_mode_for_collection_with_full_schema,
    get_submission,
)
from app.common.data.models_user import User
from app.common.data.types import (
    ConditionsOperator,
    GrantRecipientModeEnum,
    QuestionDataType,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
    TasklistSectionStatusEnum,
)
from app.common.expressions import (
    ExpressionContext,
    UndefinedVariableInExpression,
    evaluate,
    interpolate,
)
from app.common.filters import format_datetime
from app.common.helpers.submission_events import SubmissionEventHelper

if TYPE_CHECKING:
    from app.common.data.models import (
        Collection,
        Component,
        Form,
        Grant,
        Group,
        Question,
        Submission,
    )


class FormQuestionsAnswered(NamedTuple):
    all_answered: bool
    some_answered: bool


class AddAnotherAnswerSummary(NamedTuple):
    summary: str
    is_answered: bool


class SubmissionAuthorisationError(Exception):
    def __init__(self, message: str, user: User, submission_id: UUID, required_permission: RoleEnum):
        super().__init__(message)
        self.message = message
        self.user = user
        self.submission_id = submission_id
        self.required_permission = required_permission

        current_app.logger.warning(
            (
                "Submission authorisation failure: %(message)s | User: %(user_id)s | "
                "Submission: %(submission_id)s | Required: %(permission)s"
            ),
            dict(
                message=message,
                user_id=user.id,
                submission_id=submission_id,
                permission=required_permission.value,
            ),
        )


class SubmissionHelper:
    """
    This offensively-named class is a helper for the `app.common.data.models.Submission` and associated sub-models.

    It wraps a Submission instance from the DB and encapsulates the business logic that will make it easy to deal with
    conditionals, routing, storing+retrieving data, etc in one place, consistently.
    """

    def __init__(self, submission: "Submission"):
        """
        Initialise the SubmissionHelper; the `submission` instance passed in should have been retrieved from the DB
        with the collection and related tables (eg form, question) eagerly loaded to prevent this helper from
        making any further DB queries. Use `get_submission` with the `with_full_schema=True` option.
        :param submission:
        """
        self.submission = submission
        self.collection = self.submission.collection
        self.events = SubmissionEventHelper(self.submission)

        self.cached_get_ordered_visible_questions = lru_cache(maxsize=None)(self._get_ordered_visible_questions)
        self.cached_get_answer_for_question = lru_cache(maxsize=None)(self._get_answer_for_question)
        self.cached_get_all_questions_are_answered_for_form = lru_cache(maxsize=None)(
            self._get_all_questions_are_answered_for_form
        )
        self.cached_evaluation_context = ExpressionContext.build_expression_context(
            collection=self.submission.collection,
            submission_helper=self,
            mode="evaluation",
        )
        self.cached_interpolation_context = ExpressionContext.build_expression_context(
            collection=self.submission.collection,
            submission_helper=self,
            mode="interpolation",
        )

    @classmethod
    def load(cls, submission_id: uuid.UUID, *, grant_recipient_id: uuid.UUID | None = None) -> "SubmissionHelper":
        return cls(get_submission(submission_id, with_full_schema=True, grant_recipient_id=grant_recipient_id))

    @staticmethod
    def get_interpolator(
        collection: "Collection",
        submission_helper: Optional["SubmissionHelper"] = None,
    ) -> Callable[[str], str]:
        return partial(
            interpolate,
            context=ExpressionContext.build_expression_context(
                collection=collection,
                mode="interpolation",
                submission_helper=submission_helper,
            ),
        )

    @property
    def grant(self) -> "Grant":
        return self.collection.grant

    @property
    def name(self) -> str:
        return self.collection.name

    @property
    def reference(self) -> str:
        return self.submission.reference

    def form_data(
        self, *, add_another_container: "Component | None" = None, add_another_index: int | None = None
    ) -> dict[str, Any]:
        form_data: dict[str, Any] = {}

        for form in self.collection.forms:
            for question in form.cached_questions:
                # we'll only add add another answers if a context is provided which will be hooked in
                # with the form runner
                if not question.add_another_container:
                    answer = self.cached_get_answer_for_question(question.id)
                    if answer is not None:
                        form_data[question.safe_qid] = answer.get_value_for_form()
                else:
                    if add_another_container and add_another_index is not None:
                        count = self.get_count_for_add_another(add_another_container)
                        if question.add_another_container == add_another_container and add_another_index < count:
                            answer = self.cached_get_answer_for_question(
                                question.id, add_another_index=add_another_index
                            )
                            if answer is not None:
                                form_data[question.safe_qid] = answer.get_value_for_form()

        return form_data

    def get_count_for_add_another(self, add_another_container: "Component") -> int:
        if answers := self.submission.data.get(str(add_another_container.id)):
            return len(answers)
        return 0

    @property
    def all_visible_questions(self) -> dict[UUID, "Question"]:
        return {
            question.id: question
            for form in self.get_ordered_visible_forms()
            for question in self.cached_get_ordered_visible_questions(form)
        }

    @property
    def status(self) -> SubmissionStatusEnum:
        submission_state = self.events.submission_state
        # todo: make sure this is resilient to timezones, drift, etc. this is likely something that should
        #       a batch job decision that is then added as a submission event rather than calculated by the server
        submission_is_overdue = (
            self.collection.submission_period_end_date and self.collection.submission_period_end_date < date.today()
        )

        form_statuses = set([self.get_status_for_form(form) for form in self.collection.forms])
        if {TasklistSectionStatusEnum.COMPLETED} == form_statuses and submission_state.is_submitted:
            return SubmissionStatusEnum.SUBMITTED
        elif submission_is_overdue:
            return SubmissionStatusEnum.OVERDUE
        elif {TasklistSectionStatusEnum.COMPLETED} == form_statuses and submission_state.is_awaiting_sign_off:
            return SubmissionStatusEnum.AWAITING_SIGN_OFF
        elif (
            {TasklistSectionStatusEnum.COMPLETED} == form_statuses
            and (
                self.is_preview
                or not self.submission.collection.requires_certification
                or submission_state.is_approved
                or (self.submission.collection.requires_certification and not submission_state.is_awaiting_sign_off)
            )
            and not submission_state.is_submitted
        ):
            return SubmissionStatusEnum.READY_TO_SUBMIT
        elif {TasklistSectionStatusEnum.NOT_STARTED} == form_statuses:
            return SubmissionStatusEnum.NOT_STARTED
        else:
            return SubmissionStatusEnum.IN_PROGRESS

    @property
    def submitted_at_utc(self) -> datetime | None:
        return self.events.submission_state.submitted_at_utc

    @property
    def is_locked_state(self) -> bool:
        return self.is_submitted or self.is_awaiting_sign_off

    @property
    def is_submitted(self) -> bool:
        return self.status == SubmissionStatusEnum.SUBMITTED

    @property
    def is_awaiting_sign_off(self) -> bool:
        return self.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

    @property
    def is_preview(self) -> bool:
        return self.submission.mode == SubmissionModeEnum.PREVIEW

    @property
    def is_test(self) -> bool:
        return self.submission.mode == SubmissionModeEnum.TEST

    @property
    def is_live(self) -> bool:
        return self.submission.mode == SubmissionModeEnum.LIVE

    @property
    def created_by_email(self) -> str:
        return self.submission.created_by.email

    @property
    def sent_for_certification_at_utc(self) -> datetime | None:
        return self.events.submission_state.sent_for_certification_at_utc

    @property
    def sent_for_certification_by(self) -> User | None:
        return self.events.submission_state.sent_for_certification_by

    @property
    def submitted_by(self) -> User | None:
        return self.events.submission_state.submitted_by

    @property
    def certified_by(self) -> User | None:
        return self.events.submission_state.certified_by

    @property
    def certified_at_utc(self) -> datetime | None:
        return self.events.submission_state.certified_at_utc

    @property
    def created_at_utc(self) -> datetime:
        return self.submission.created_at_utc

    @property
    def id(self) -> UUID:
        return self.submission.id

    @property
    def collection_id(self) -> UUID:
        return self.collection.id

    def get_form(self, form_id: uuid.UUID) -> "Form":
        try:
            return next(filter(lambda f: f.id == form_id, self.collection.forms))
        except StopIteration as e:
            raise ValueError(f"Could not find a form with id={form_id} in collection={self.collection.id}") from e

    def get_question(self, question_id: uuid.UUID) -> "Question":
        try:
            return next(
                filter(
                    lambda q: q.id == question_id,
                    chain.from_iterable(form.cached_questions for form in self.collection.forms),
                )
            )
        except StopIteration as e:
            raise ValueError(
                f"Could not find a question with id={question_id} in collection={self.collection.id}"
            ) from e

    def _get_all_questions_are_answered_for_form(self, form: "Form") -> FormQuestionsAnswered:
        question_answer_status = []

        for question in form.cached_questions:
            if question.add_another_container:
                for i in range(self.get_count_for_add_another(question.add_another_container)):
                    context = self.cached_evaluation_context.with_add_another_context(
                        question, submission_helper=self, add_another_index=i
                    )
                    if self.is_component_visible(question, context):
                        question_answer_status.append(
                            self.cached_get_answer_for_question(question.id, add_another_index=i) is not None
                        )
            else:
                if self.is_component_visible(question, self.cached_evaluation_context):
                    question_answer_status.append(self.cached_get_answer_for_question(question.id) is not None)

        return FormQuestionsAnswered(
            all_answered=all(question_answer_status), some_answered=any(question_answer_status)
        )

    @cached_property
    def all_forms_are_completed(self) -> bool:
        form_statuses = set([self.get_status_for_form(form) for form in self.collection.forms])
        return {TasklistSectionStatusEnum.COMPLETED} == form_statuses

    def get_tasklist_status_for_form(self, form: "Form") -> TasklistSectionStatusEnum:
        if len(form.cached_questions) == 0:
            return TasklistSectionStatusEnum.NO_QUESTIONS

        return self.get_status_for_form(form)

    def get_status_for_form(self, form: "Form") -> TasklistSectionStatusEnum:
        form_questions_answered = self.cached_get_all_questions_are_answered_for_form(form)
        marked_as_complete = self.events.form_state(form.id).is_completed
        if form.cached_questions and form_questions_answered.all_answered and marked_as_complete:
            return TasklistSectionStatusEnum.COMPLETED
        elif form_questions_answered.some_answered:
            return TasklistSectionStatusEnum.IN_PROGRESS
        else:
            return TasklistSectionStatusEnum.NOT_STARTED

    def get_ordered_visible_forms(self) -> list["Form"]:
        """Returns the visible, ordered forms based upon the current state of this collection."""
        return sorted(self.collection.forms, key=lambda f: f.order)

    def is_component_visible(
        self, component: "Component", context: "ExpressionContext", add_another_index: int | None = None
    ) -> bool:
        # we can optimise this to exit early and do this in a sensible order if we switch
        # to going through questions in a nested way rather than flat
        def evaluate_component_conditions(comp: "Component") -> bool:
            """Evaluates a component's own conditions using its operator."""
            if not comp.conditions:
                return True

            match comp.conditions_operator:
                case ConditionsOperator.ANY:
                    return any(evaluate(condition, context) for condition in comp.conditions)
                case ConditionsOperator.ALL:
                    return all(evaluate(condition, context) for condition in comp.conditions)
                case _:
                    raise RuntimeError(f"Unknown condition operator={comp.conditions_operator}")

        try:
            if component.add_another_container and add_another_index is not None:
                context = context.with_add_another_context(
                    component, submission_helper=self, add_another_index=add_another_index
                )

            current = component
            while current.parent:
                if not evaluate_component_conditions(current.parent):
                    return False
                current = current.parent

            # Finally evaluate this component's own conditions
            return evaluate_component_conditions(component)

        except UndefinedVariableInExpression:
            # todo: fail open for now - this method should accept an optional bool that allows this condition to fail
            #       or not- checking visibility on the question page itself should never fail - the summary page could
            # todo: check dependency chain for conditions when undefined variables are encountered to avoid
            #       always suppressing errors and not surfacing issues on misconfigured forms
            return False

    def _get_ordered_visible_questions(
        self, parent: Union["Form", "Group"], *, override_context: "ExpressionContext | None" = None
    ) -> list["Question"]:
        """Returns the visible, ordered questions based upon the current state of this collection."""
        context = override_context or self.cached_evaluation_context
        return [question for question in parent.cached_questions if self.is_component_visible(question, context)]

    def get_first_question_for_form(self, form: "Form") -> Optional["Question"]:
        questions = self.cached_get_ordered_visible_questions(form)
        if questions:
            return questions[0]
        return None

    def get_last_question_for_form(self, form: "Form") -> Optional["Question"]:
        questions = self.cached_get_ordered_visible_questions(form)
        if questions:
            return questions[-1]
        return None

    def get_form_for_question(self, question_id: UUID) -> "Form":
        for form in self.collection.forms:
            if any(q.id == question_id for q in form.cached_questions):
                return form

        raise ValueError(f"Could not find form for question_id={question_id} in collection={self.collection.id}")

    def _get_answer_for_question(
        self, question_id: UUID, add_another_index: int | None = None
    ) -> AllAnswerTypes | None:
        question = self.get_question(question_id)

        if question.add_another_container:
            if add_another_index is None:
                raise ValueError("add_another_index must be provided for questions within an add another container")
            if self.submission.data.get(str(question.add_another_container.id)) is None or add_another_index >= len(
                self.submission.data.get(str(question.add_another_container.id), [])
            ):
                # we raise here instead of returning None as the consuming code should never ask for an answer to an
                # add another entry that doesn't exist
                raise ValueError("no add another entry exists at this index")

        data_entry = (
            self.submission.data
            if not question.add_another_container
            else self.submission.data.get(str(question.add_another_container.id), [])[add_another_index]
        )
        serialised_data = data_entry.get(str(question_id))
        return _deserialise_question_type(question, serialised_data) if serialised_data is not None else None

    def submit_answer_for_question(
        self, question_id: UUID, form: DynamicQuestionForm, *, add_another_index: int | None = None
    ) -> None:
        if self.is_locked_state:
            raise ValueError(
                f"Could not submit answer for question_id={question_id} "
                f"because submission id={self.id} is already submitted."
            )

        question = self.get_question(question_id)
        data = _form_data_to_question_type(question, form)
        interfaces.collections.update_submission_data(
            self.submission, question, data, add_another_index=add_another_index
        )
        self.cached_get_answer_for_question.cache_clear()
        self.cached_get_all_questions_are_answered_for_form.cache_clear()

        # FIXME: work out why end to end tests aren't happy without this here
        #        I've made it work but not happy with not clearly pointing to where
        #        an instance was failing to route (next_url) appropriately without it
        self.cached_get_ordered_visible_questions.cache_clear()

    def submit(self, user: "User") -> None:
        if self.is_submitted:
            return

        if not self.all_forms_are_completed:
            raise ValueError(f"Could not submit submission id={self.id} because not all forms are complete.")

        # TODO: FSPT-1049 - the 'Overdue' status currently blocks anything from progressing but shouldn't do. In order
        # to get by this now we check the underlying submission_state rather than the status, but we should refactor
        # this when a decision is made on 'Overdue' behaviour and make the submission status the source of truth.
        if self.collection.requires_certification and not self.events.submission_state.is_approved and self.is_live:
            raise ValueError(f"Could not submit submission id={self.id} because it has not been approved.")

        if self.is_live and self.status != SubmissionStatusEnum.READY_TO_SUBMIT:
            raise ValueError(f"Could not submit submission id={self.id} because it is not ready to submit.")

        if (
            self.is_live
            and self.collection.requires_certification
            and not AuthorisationHelper.is_access_grant_certifier(
                self.grant.id, self.submission.grant_recipient.organisation.id, user
            )
        ):
            raise SubmissionAuthorisationError(
                f"User does not have certifier permission to submit submission {self.id}",
                user,
                self.id,
                RoleEnum.CERTIFIER,
            )

        interfaces.collections.add_submission_event(
            self.submission, event_type=SubmissionEventType.SUBMISSION_SUBMITTED, user=user
        )

    def mark_as_sent_for_certification(self, user: "User") -> None:
        if self.is_locked_state:
            return

        if not self.collection.requires_certification:
            raise ValueError(
                f"Could not send submission id={self.id} for sign off because this report does not require "
                f"certification."
            )

        if self.all_forms_are_completed:
            interfaces.collections.add_submission_event(
                self.submission, event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION, user=user
            )
        else:
            raise ValueError(f"Could not send submission id={self.id} for sign off because not all forms are complete.")

    def decline_certification(self, user: "User", declined_reason: str) -> None:
        if not self.collection.requires_certification:
            raise ValueError(
                f"Could not decline certification for submission id={self.id} because this report does not require "
                f"certification."
            )

        if self.is_live and not AuthorisationHelper.is_access_grant_certifier(
            self.grant.id, self.submission.grant_recipient.organisation.id, user
        ):
            raise SubmissionAuthorisationError(
                f"User does not have certifier permission to decline submission {self.id}",
                user,
                self.id,
                RoleEnum.CERTIFIER,
            )

        if self.status == SubmissionStatusEnum.AWAITING_SIGN_OFF:
            interfaces.collections.add_submission_event(
                self.submission,
                event_type=SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER,
                user=user,
                declined_reason=declined_reason,
            )
            for form in self.collection.forms:
                interfaces.collections.add_submission_event(
                    self.submission,
                    event_type=SubmissionEventType.FORM_RUNNER_FORM_RESET_BY_CERTIFIER,
                    user=user,
                    related_entity_id=form.id,
                )
        else:
            raise ValueError(
                f"Could not decline certification for submission id={self.id} because it is not awaiting sign off."
            )

    def certify(self, user: "User") -> None:
        if not self.collection.requires_certification:
            raise ValueError(
                f"Could not approve certification for submission id={self.id} because this report does not require "
                f"certification."
            )

        if self.is_live and not AuthorisationHelper.is_access_grant_certifier(
            self.grant.id, self.submission.grant_recipient.organisation.id, user
        ):
            raise SubmissionAuthorisationError(
                f"User does not have certifier permission to certify submission {self.id}",
                user,
                self.id,
                RoleEnum.CERTIFIER,
            )

        # TODO: FSPT-1049 - the 'Overdue' status currently blocks anything from progressing but shouldn't do. In order
        # to get by this now we check the underlying submission_state rather than the status, but we should refactor
        # this when a decision is made on 'Overdue' behaviour and make the submission status the source of truth.
        if self.events.submission_state.is_awaiting_sign_off:
            interfaces.collections.add_submission_event(
                self.submission, event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER, user=user
            )
        else:
            raise ValueError(
                f"Could not approve certification for submission id={self.id} because it is not awaiting sign off."
            )

    def toggle_form_completed(self, form: "Form", user: "User", is_complete: bool) -> None:
        form_complete = self.get_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED
        if is_complete == form_complete:
            return

        if is_complete:
            all_questions_answered = self.cached_get_all_questions_are_answered_for_form(form).all_answered
            if not all_questions_answered:
                raise ValueError(
                    f"Could not mark form id={form.id} as complete because not all questions have been answered."
                )

            interfaces.collections.add_submission_event(
                self.submission,
                event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
                user=user,
                related_entity_id=form.id,
            )
        else:
            interfaces.collections.add_submission_event(
                self.submission,
                event_type=SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS,
                user=user,
                related_entity_id=form.id,
            )

    # todo: decide if the add another index should be available submission helper wide where it just checks self
    #       does having it on lots of methods increase the cognitive load/ complexity
    def get_next_question(
        self, current_question_id: UUID, *, add_another_index: int | None = None
    ) -> Optional["Question"]:
        """
        Retrieve the next question that should be shown to the user, or None if this was the last relevant question.
        """
        form = self.get_form_for_question(current_question_id)
        question = self.get_question(current_question_id)

        context_override = None
        if question.add_another_container and add_another_index is not None:
            context_override = self.cached_evaluation_context.with_add_another_context(
                question, submission_helper=self, add_another_index=add_another_index
            )

        questions = self.cached_get_ordered_visible_questions(
            form, override_context=context_override if context_override else None
        )

        question_iterator = iter(questions)
        for question in question_iterator:
            if question.id == current_question_id:
                return next(question_iterator, None)

        raise ValueError(f"Could not find a question with id={current_question_id} in collection={self.collection}")

    def get_previous_question(
        self, current_question_id: UUID, add_another_index: int | None = None
    ) -> Optional["Question"]:
        """
        Retrieve the question that was asked before this one, or None if this was the first relevant question.
        """
        form = self.get_form_for_question(current_question_id)

        question = self.get_question(current_question_id)

        context_override = None
        if question.add_another_container and add_another_index is not None:
            context_override = self.cached_evaluation_context.with_add_another_context(
                question, submission_helper=self, add_another_index=add_another_index, allow_new_index=True
            )

        questions = self.cached_get_ordered_visible_questions(
            form, override_context=context_override if context_override else None
        )

        # Reverse the list of questions so that we're working from the end to the start.
        question_iterator = iter(reversed(questions))
        for question in question_iterator:
            if question.id == current_question_id:
                return next(question_iterator, None)

        raise ValueError(f"Could not find a question with id={current_question_id} in collection={self.collection}")

    def get_answer_summary_for_add_another(
        self, component: "Component", *, add_another_index: int
    ) -> AddAnotherAnswerSummary:
        if not component.add_another_container:
            raise ValueError("answer summaries can only be generated for components in an add another container")

        context = self.cached_evaluation_context.with_add_another_context(
            submission_helper=self, component=component, add_another_index=add_another_index
        )
        visible_questions = (
            self.cached_get_ordered_visible_questions(component.add_another_container, override_context=context)
            if component.add_another_container.is_group
            else [cast("Question", component)]
        )

        questions = []
        if component.add_another_container.is_group:
            for question in cast("Group", component.add_another_container).questions_in_add_another_summary:
                if question in visible_questions:
                    questions.append(question)
        else:
            questions = [cast("Question", component)]

        answers = []
        for question in questions:
            answer = self.cached_get_answer_for_question(question.id, add_another_index=add_another_index)
            if answer:
                answers.append(answer.get_value_for_text_export())

        answer_status = []

        for question in visible_questions:
            answer = self.cached_get_answer_for_question(question.id, add_another_index=add_another_index)
            answer_status.append(answer is not None)

        return AddAnotherAnswerSummary(summary=", ".join(answers), is_answered=all(answer_status))


class CollectionHelper:
    collection: "Collection"
    submission_mode: SubmissionModeEnum
    submissions: List["Submission"]
    submission_helpers: dict[UUID, SubmissionHelper]

    def __init__(self, collection: "Collection", submission_mode: SubmissionModeEnum):
        if submission_mode == SubmissionModeEnum.PREVIEW:
            raise ValueError("Cannot create a collection helper for preview submissions.")

        self.collection = collection
        self.submission_mode = submission_mode
        self.submissions = [
            s for s in (get_all_submissions_with_mode_for_collection_with_full_schema(collection.id, submission_mode))
        ]
        self.submission_helpers = {s.id: SubmissionHelper(s) for s in self.submissions}

        grant_recipient_mode = (
            GrantRecipientModeEnum.TEST if submission_mode == SubmissionModeEnum.TEST else GrantRecipientModeEnum.LIVE
        )
        self.grant_recipients = [gr for gr in self.collection.grant.grant_recipients if gr.mode == grant_recipient_mode]
        self.grant_recipients_submission_helpers: dict[UUID, SubmissionHelper | None] = {
            gr.id: None for gr in self.grant_recipients
        }
        self.grant_recipients_submission_helpers.update(
            {s.grant_recipient.id: self.submission_helpers[s.id] for s in self.submissions}
        )

    @property
    def is_test_mode(self) -> bool:
        return self.submission_mode == SubmissionModeEnum.TEST

    def get_submission_helper_by_id(self, submission_id: UUID) -> SubmissionHelper | None:
        return self.submission_helpers.get(submission_id, None)

    def get_submission_helper_by_reference(self, submission_reference: str) -> SubmissionHelper | None:
        for _, submission in self.submission_helpers.items():
            if submission.reference == submission_reference:
                return submission

        return None

    def get_all_possible_questions_for_collection(self) -> list["Question"]:
        """
        Returns a list of all questions that are part of the collection, across all forms.
        """
        return [
            question
            for form in sorted(self.collection.forms, key=lambda f: f.order)
            for question in sorted(form.cached_questions, key=lambda q: q.order)
        ]

    # todo: split this method up into smaller parts that can be individually tested (i.e submission -> CSV row dict)
    def generate_csv_content_for_all_submissions(self) -> str:  # noqa: C901
        metadata_headers = (
            ["Submission reference", "Grant recipient", "Created by", "Created at"]
            + (["Certified by", "Certified at"] if self.collection.requires_certification else [])
            + [
                "Status",
                "Submitted at",
            ]
        )

        question_headers: list[tuple["Question", str, int | None]] = []
        processed_add_another_contexts = []
        for question in self.get_all_possible_questions_for_collection():
            if not question.add_another_container:
                question_headers.append((question, f"[{question.form.title}] {question.name}", None))
            else:
                if question.add_another_container not in processed_add_another_contexts:
                    processed_add_another_contexts.append(question.add_another_container)

                    # if its an add another question context we need to know the count to make the
                    # maximum number of headers
                    counts = [
                        submission.get_count_for_add_another(question.add_another_container)
                        for submission in self.submission_helpers.values()
                    ]
                    count = max(counts) if counts else 1

                    for i in range(count):
                        questions = (
                            cast("Group", question.add_another_container).cached_questions
                            if question.add_another_container.is_group
                            else [cast("Question", question.add_another_container)]
                        )
                        for add_another_question in questions:
                            assert add_another_question.add_another_container is not None
                            question_headers.append(
                                (
                                    add_another_question,
                                    f"[{add_another_question.form.title}]"
                                    f" [{add_another_question.add_another_container.name}]"
                                    f" {add_another_question.name} ({i + 1})",
                                    i,
                                )
                            )

        all_headers = metadata_headers + [header_string for (_, header_string, _) in question_headers]

        csv_output = StringIO()
        csv_writer = csv.DictWriter(csv_output, fieldnames=all_headers)
        csv_writer.writeheader()
        for submission in [value for key, value in self.submission_helpers.items()]:
            submission_csv_data = {
                "Submission reference": submission.reference,
                "Grant recipient": (
                    submission.submission.grant_recipient.organisation.name
                    if submission.submission.grant_recipient
                    else None
                ),
                "Created by": submission.created_by_email,
                "Created at": format_datetime(submission.created_at_utc),
                "Status": submission.status,
                "Submitted at": format_datetime(submission.submitted_at_utc) if submission.submitted_at_utc else None,
            }

            if self.collection.requires_certification:
                submission_csv_data["Certified by"] = (
                    submission.events.submission_state.certified_by.email
                    if submission.events.submission_state.certified_by
                    else None
                )
                submission_csv_data["Certified at"] = (
                    format_datetime(submission.events.submission_state.certified_at_utc)
                    if submission.events.submission_state.certified_at_utc
                    else None
                )

            visible_questions = submission.all_visible_questions
            cached_contexts: dict[str, "ExpressionContext"] = {}
            for question, header_string, index in question_headers:
                if not question.add_another_container:
                    if question.id not in visible_questions.keys():
                        submission_csv_data[header_string] = NOT_ASKED
                    else:
                        answer = submission.cached_get_answer_for_question(question.id)
                        submission_csv_data[header_string] = (
                            answer.get_value_for_text_export() if answer is not None else NOT_ANSWERED
                        )
                else:
                    assert index is not None
                    if submission.get_count_for_add_another(question.add_another_container) <= index:
                        # this submission didn't provide this many answers as so wasn't asked this question
                        submission_csv_data[header_string] = NOT_ASKED
                    else:
                        context_key = f"{question.add_another_container.id}{index}"
                        context = cached_contexts.get(context_key)
                        if not context:
                            context = submission.cached_evaluation_context.with_add_another_context(
                                question.add_another_container,
                                submission_helper=submission,
                                add_another_index=index,
                            )
                            cached_contexts[context_key] = context

                        if submission.is_component_visible(question, context):
                            answer = submission.cached_get_answer_for_question(question.id, add_another_index=index)
                            submission_csv_data[header_string] = (
                                answer.get_value_for_text_export() if answer is not None else NOT_ANSWERED
                            )
                        else:
                            submission_csv_data[header_string] = NOT_ASKED

            csv_writer.writerow(submission_csv_data)

        return csv_output.getvalue()

    def generate_json_content_for_all_submissions(self) -> str:
        submissions_data: dict[str, Any] = {"submissions": []}
        for submission in self.submission_helpers.values():
            submission_data: dict[str, Any] = {
                "reference": submission.reference,
                "grant_recipient": submission.submission.grant_recipient.organisation.name
                if submission.submission.grant_recipient
                else None,
                "created_by": submission.created_by_email,
                "created_at_utc": format_datetime(submission.created_at_utc),
                "status": submission.status,
                "submitted_at_utc": format_datetime(submission.submitted_at_utc)
                if submission.submitted_at_utc
                else None,
                "sections": [],
            }

            if self.collection.requires_certification:
                submission_data["certified_by"] = (
                    submission.events.submission_state.certified_by.email
                    if submission.events.submission_state.certified_by
                    else None
                )
                submission_data["certified_at_utc"] = (
                    format_datetime(submission.events.submission_state.certified_at_utc)
                    if submission.events.submission_state.certified_at_utc
                    else None
                )

            for form in submission.get_ordered_visible_forms():
                task_data: dict[str, Any] = {"name": form.title, "answers": {}}

                add_another_contexts = []
                for question in submission.cached_get_ordered_visible_questions(form):
                    if question.add_another_container:
                        if question.add_another_container.id not in add_another_contexts:
                            add_another_contexts.append(question.add_another_container.id)
                            task_data["answers"][question.add_another_container.name.lower()] = []

                            for i in range(submission.get_count_for_add_another(question.add_another_container)):
                                entry = {}

                                context = submission.cached_evaluation_context.with_add_another_context(
                                    question.add_another_container, submission_helper=submission, add_another_index=i
                                )
                                for q in submission.cached_get_ordered_visible_questions(
                                    question.add_another_container, override_context=context
                                ):
                                    answer = submission.cached_get_answer_for_question(q.id, add_another_index=i)
                                    entry[q.name] = answer.get_value_for_json_export() if answer is not None else None
                                task_data["answers"][question.add_another_container.name.lower()].append(entry)
                    else:
                        answer = submission.cached_get_answer_for_question(question.id)
                        task_data["answers"][question.name] = (
                            answer.get_value_for_json_export() if answer is not None else None
                        )
                submission_data["sections"].append(task_data)  # ty: ignore[possibly-missing-attribute]

            submissions_data["submissions"].append(submission_data)

        return json.dumps(submissions_data)


def _form_data_to_question_type(question: "Question", form: DynamicQuestionForm) -> AllAnswerTypes:
    _QuestionModel: type[PydanticBaseModel]

    answer = form.get_answer_to_question(question)

    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE | QuestionDataType.EMAIL | QuestionDataType.URL:
            return TextSingleLineAnswer(answer)  # ty: ignore[missing-argument]
        case QuestionDataType.TEXT_MULTI_LINE:
            return TextMultiLineAnswer(answer)  # ty: ignore[missing-argument]
        case QuestionDataType.INTEGER:
            return IntegerAnswer(value=answer, prefix=question.prefix, suffix=question.suffix)  # ty: ignore[missing-argument]
        case QuestionDataType.YES_NO:
            return YesNoAnswer(answer)  # ty: ignore[missing-argument]
        case QuestionDataType.RADIOS:
            label = next(item.label for item in question.data_source.items if item.key == answer)
            return SingleChoiceFromListAnswer(key=answer, label=label)
        case QuestionDataType.CHECKBOXES:
            choices = [
                ChoiceDict({"key": item.key, "label": item.label})
                for item in question.data_source.items
                if item.key in answer
            ]
            return MultipleChoiceFromListAnswer(choices=choices)
        case QuestionDataType.DATE:
            return DateAnswer(answer=answer, approximate_date=question.approximate_date or False)  # ty: ignore[missing-argument]

    raise ValueError(f"Could not parse data for question type={question.data_type}")


def _deserialise_question_type(question: "Question", serialised_data: str | int | float | bool) -> AllAnswerTypes:
    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE:
            return TypeAdapter(TextSingleLineAnswer).validate_python(serialised_data)
        case QuestionDataType.URL:
            return TypeAdapter(UrlAnswer).validate_python(serialised_data)
        case QuestionDataType.EMAIL:
            return TypeAdapter(EmailAnswer).validate_python(serialised_data)
        case QuestionDataType.TEXT_MULTI_LINE:
            return TypeAdapter(TextMultiLineAnswer).validate_python(serialised_data)
        case QuestionDataType.INTEGER:
            return TypeAdapter(IntegerAnswer).validate_python(serialised_data)
        case QuestionDataType.YES_NO:
            return TypeAdapter(YesNoAnswer).validate_python(serialised_data)
        case QuestionDataType.RADIOS:
            return TypeAdapter(SingleChoiceFromListAnswer).validate_python(serialised_data)
        case QuestionDataType.CHECKBOXES:
            return TypeAdapter(MultipleChoiceFromListAnswer).validate_python(serialised_data)
        case QuestionDataType.DATE:
            return TypeAdapter(DateAnswer).validate_python(serialised_data)

    raise ValueError(f"Could not deserialise data for question type={question.data_type}")
