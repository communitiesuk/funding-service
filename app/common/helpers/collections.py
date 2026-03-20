import csv
import json
import uuid
from collections.abc import Callable
from datetime import datetime
from functools import cached_property, lru_cache, partial
from io import StringIO
from itertools import chain
from typing import TYPE_CHECKING, Any, NamedTuple, Sequence, cast
from uuid import UUID

from flask import current_app
from pydantic import BaseModel as PydanticBaseModel
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.collections.forms import DynamicQuestionForm
from app.common.collections.types import (
    NOT_ANSWERED,
    NOT_ASKED,
    AllAnswerTypes,
    ChoiceDict,
    DateAnswer,
    DecimalAnswer,
    FileUploadAnswer,
    IntegerAnswer,
    MultipleChoiceFromListAnswer,
    SingleChoiceFromListAnswer,
    TextMultiLineAnswer,
    TextSingleLineAnswer,
    YesNoAnswer,
)
from app.common.collections.validation import SubmissionValidator
from app.common.data import interfaces
from app.common.data.interfaces.collections import (
    get_all_submissions_with_mode_for_collection,
    get_submission,
    update_submission_data,
)
from app.common.data.interfaces.grant_recipients import get_grant_recipients
from app.common.data.models_user import User
from app.common.data.types import (
    ComponentVisibilityState,
    GrantRecipientModeEnum,
    NumberTypeEnum,
    QuestionDataType,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
    TasklistSectionStatusEnum,
)
from app.common.exceptions import SubmissionAnswerConflict
from app.common.expressions import (
    ExpressionContext,
    interpolate,
)
from app.common.helpers.submission_events import SubmissionEventHelper
from app.common.helpers.visibility import VisibilityResolver
from app.extensions import notification_service, s3_service

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

    def __init__(self, submission: Submission):
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

    @classmethod
    def load(cls, submission_id: uuid.UUID, *, grant_recipient_id: uuid.UUID | None = None) -> SubmissionHelper:
        return cls(get_submission(submission_id, with_full_schema=True, grant_recipient_id=grant_recipient_id))

    @staticmethod
    def get_interpolator(
        collection: Collection,
        submission_helper: SubmissionHelper | None = None,
    ) -> Callable[[str], str]:
        return partial(
            interpolate,
            context=ExpressionContext.build_expression_context(
                collection=collection,
                mode="interpolation",
                data_manager=submission_helper.submission.data_manager if submission_helper else None,
            ),
        )

    @cached_property
    def cached_evaluation_context(self) -> ExpressionContext:
        return ExpressionContext.build_expression_context(
            collection=self.submission.collection,
            data_manager=self.submission.data_manager,
            mode="evaluation",
        )

    @cached_property
    def cached_interpolation_context(self) -> ExpressionContext:
        return ExpressionContext.build_expression_context(
            collection=self.submission.collection,
            data_manager=self.submission.data_manager,
            mode="interpolation",
        )

    @cached_property
    def _visibility_resolver(self) -> VisibilityResolver:
        resolver = VisibilityResolver(
            self.collection.dependency_graph, self.cached_evaluation_context, self.submission.data_manager
        )
        resolver.resolve()
        return resolver

    @property
    def submission_name(self) -> str:
        """
        For submissions in a multi-submission collection, this provides a name for the submission based on a provided
        answer.

        For non-multi-submission collection we just return the submission's generated reference.
        """
        question = self.collection.submission_name_question
        if question:
            answer = self.cached_get_answer_for_question(question.id)
            if answer is not None:
                return answer.get_value_for_text_export()
        return self.submission.reference

    @property
    def long_collection_name(self) -> str:
        """
        Returns the name of the collection with, for multi-submission collections, the submission name.

        This helps provides enough context on Access grant funding as to what report they're working with.
        """
        if not self.submission.collection.allow_multiple_submissions:
            return self.submission.collection.name

        return f"{self.submission.collection.name} - {self.submission_name}"

    @property
    def grant(self) -> Grant:
        return self.collection.grant

    @property
    def name(self) -> str:
        return self.collection.name

    @property
    def reference(self) -> str:
        return self.submission.reference

    def form_data(
        self, *, add_another_container: Component | None = None, add_another_index: int | None = None
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

    def get_count_for_add_another(self, add_another_container: Component) -> int:
        return self.submission.data_manager.get_count_for_add_another(add_another_container)

    @property
    def all_visible_questions(self) -> dict[UUID, Question]:
        return {
            question.id: question
            for form in self.get_ordered_visible_forms()
            for question in self.cached_get_ordered_visible_questions(form)
        }

    @property
    def is_overdue(self) -> bool:
        # todo: make sure this is resilient to timezones, drift, etc. this is likely something that should
        #       a batch job decision that is then added as a submission event rather than calculated by the server
        return self.collection.is_overdue and not self.is_submitted

    @property
    def status(self) -> SubmissionStatusEnum:
        submission_state = self.events.submission_state

        form_statuses = {self.get_status_for_form(form) for form in self.collection.forms}
        if {TasklistSectionStatusEnum.COMPLETED} == form_statuses and submission_state.is_submitted:
            return SubmissionStatusEnum.SUBMITTED
        elif {TasklistSectionStatusEnum.COMPLETED} == form_statuses and submission_state.is_awaiting_sign_off:
            return SubmissionStatusEnum.AWAITING_SIGN_OFF
        elif (
            form_statuses <= {TasklistSectionStatusEnum.COMPLETED, TasklistSectionStatusEnum.NOT_NEEDED}
            and (
                self.is_preview
                or not self.submission.collection.requires_certification
                or submission_state.is_approved
                or (self.submission.collection.requires_certification and not submission_state.is_awaiting_sign_off)
            )
            and not submission_state.is_submitted
        ):
            return SubmissionStatusEnum.READY_TO_SUBMIT
        elif form_statuses <= {TasklistSectionStatusEnum.NOT_STARTED, TasklistSectionStatusEnum.NOT_NEEDED}:
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
    def declined_by(self) -> User | None:
        return self.events.submission_state.declined_by

    @property
    def created_at_utc(self) -> datetime:
        return self.submission.created_at_utc

    @property
    def last_updated_at_utc(self) -> datetime:
        return max(filter(None, [self.events.latest_event_utc, self.submission.updated_at_utc]))

    @property
    def id(self) -> UUID:
        return self.submission.id

    @property
    def collection_id(self) -> UUID:
        return self.collection.id

    def get_form(self, form_id: uuid.UUID) -> Form:
        try:
            return next(filter(lambda f: f.id == form_id, self.collection.forms))
        except StopIteration as e:
            raise ValueError(f"Could not find a form with id={form_id} in collection={self.collection.id}") from e

    def get_question(self, question_id: uuid.UUID) -> Question:
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

    def format_s3_key(self, question_id: uuid.UUID, add_another_index: int | None = None) -> str:
        key = f"{self.submission.s3_key_prefix}/{question_id}"
        if add_another_index is not None:
            key += f"/{add_another_index}"
        return key

    def answer_to_question_is_managed_by_service(self, question: Question) -> bool:
        if not self.collection.allow_multiple_submissions:
            return False

        if not self.collection.multiple_submissions_are_managed_by_service:
            return False

        if self.collection.submission_name_question_id is None:
            return False

        return self.collection.submission_name_question_id == question.id

    def _get_all_questions_are_answered_for_form(self, form: Form) -> FormQuestionsAnswered:
        question_answer_status = []

        for question in form.cached_questions:
            if self.answer_to_question_is_managed_by_service(question):
                continue

            if question.add_another_container:
                number_of_add_another_entries = self.get_count_for_add_another(question.add_another_container)
                if number_of_add_another_entries == 0:
                    # we don't currently support optional questions so anything without answers
                    # should be considered blocking
                    if self.is_component_visible(question):
                        question_answer_status.append(False)
                else:
                    # check each of this questions answers for each entry being complete
                    for i in range(number_of_add_another_entries):
                        if self.is_component_visible(question, add_another_index=i):
                            question_answer_status.append(
                                self.cached_get_answer_for_question(question.id, add_another_index=i) is not None
                            )
            else:
                if self.is_component_visible(question):
                    question_answer_status.append(self.cached_get_answer_for_question(question.id) is not None)

        return FormQuestionsAnswered(
            all_answered=all(question_answer_status), some_answered=any(question_answer_status)
        )

    def get_referenced_forms_with_unanswered_references(self, form: "Form") -> list["Form"]:
        """Returns a list of forms referenced by this form where required data doesn't exist yet."""
        unsatisfied_forms: dict[uuid.UUID, "Form"] = {}

        for component in form.cached_all_components:
            for ref in component.owned_component_references:
                depends_on = ref.depends_on_component
                if depends_on.form_id != form.id:
                    if depends_on.is_question:
                        answer = self.cached_get_answer_for_question(depends_on.id)
                        if answer is None:
                            # Only count as unsatisfied if the question is visible or undetermined.
                            # If definitively HIDDEN, the question won't be asked, so not blocking.
                            visibility = self.get_component_visibility_state(depends_on)
                            if visibility != ComponentVisibilityState.HIDDEN:
                                unsatisfied_forms[depends_on.form_id] = depends_on.form

        return sorted(unsatisfied_forms.values(), key=lambda f: f.order)

    def can_start_form(self, form: "Form") -> bool:
        """Returns False if this form requires data from other forms which hasn't been provided."""
        unsatisfied_forms = self.get_referenced_forms_with_unanswered_references(form)
        return len(unsatisfied_forms) == 0

    @cached_property
    def all_needed_forms_are_completed(self) -> bool:
        form_statuses = {self.get_status_for_form(form) for form in self.collection.forms}
        return form_statuses <= {TasklistSectionStatusEnum.COMPLETED, TasklistSectionStatusEnum.NOT_NEEDED}

    def get_tasklist_status_for_form(self, form: Form) -> TasklistSectionStatusEnum:
        if len(form.cached_questions) == 0:
            return TasklistSectionStatusEnum.NO_QUESTIONS

        if not self.can_start_form(form):
            return TasklistSectionStatusEnum.CANNOT_START_YET

        return self.get_status_for_form(form)

    def get_status_for_form(self, form: Form) -> TasklistSectionStatusEnum:
        form_questions_answered = self.cached_get_all_questions_are_answered_for_form(form)
        marked_as_complete = self.events.form_state(form.id).is_completed
        if form.cached_questions and form_questions_answered.all_answered and marked_as_complete:
            return TasklistSectionStatusEnum.COMPLETED
        elif form_questions_answered.some_answered:
            return TasklistSectionStatusEnum.IN_PROGRESS
        elif len(
            self.cached_get_ordered_visible_questions(form)
        ) == 0 and not self.get_referenced_forms_with_unanswered_references(form):
            return TasklistSectionStatusEnum.NOT_NEEDED
        else:
            return TasklistSectionStatusEnum.NOT_STARTED

    def get_ordered_visible_forms(self) -> list[Form]:
        """Returns the visible, ordered forms based upon the current state of this collection."""
        return sorted(self.collection.forms, key=lambda f: f.order)

    def is_component_visible(self, component: Component, add_another_index: int | None = None) -> bool:
        # TODO[deprecate-submission-helper-visibility]: deprecate this and shift everything onto VisibilityResolver
        state = self.get_component_visibility_state(component, add_another_index, check_undetermined=False)
        return state == ComponentVisibilityState.VISIBLE

    def get_component_visibility_state(
        self,
        component: Component,
        add_another_index: int | None = None,
        check_undetermined: bool = True,
    ) -> ComponentVisibilityState:
        """Returns the visibility state of a component, distinguishing between
        definitively hidden (conditions evaluated to False) and undetermined
        (conditions couldn't be evaluated due to missing data).

        - VISIBLE: Conditions evaluated to True
        - HIDDEN: Conditions evaluated to False (definitive - won't be asked)
        - UNDETERMINED: Conditions couldn't be evaluated due to missing data

        Uses a topological visibility resolver that walks components in dependency
        order, caching results so each component is resolved exactly once.
        """
        # TODO[deprecate-submission-helper-visibility]: deprecate this and shift everything onto VisibilityResolver
        if add_another_index is not None:
            state = self._visibility_resolver.get_visibility_for_add_another(component.id, add_another_index)
        else:
            state = self._visibility_resolver.get_visibility(component.id)

        # NOTE: should this also be part of the visibility resolver?
        if not check_undetermined and state == ComponentVisibilityState.UNDETERMINED:
            return ComponentVisibilityState.HIDDEN

        return state

    def _get_ordered_visible_questions(
        self,
        parent: Form | Group,
        *,
        add_another_index: int | None = None,
    ) -> list[Question]:
        """Returns the visible, ordered questions based upon the current state of this collection."""
        # TODO[deprecate-submission-helper-visibility]: deprecate this and shift everything onto VisibilityResolver
        return [
            question
            for question in parent.cached_questions
            if self.is_component_visible(question, add_another_index=add_another_index)
        ]

    def get_first_question_for_form(self, form: Form) -> Question | None:
        questions = self.cached_get_ordered_visible_questions(form)
        if questions:
            return questions[0]
        return None

    def get_last_question_for_form(self, form: Form) -> Question | None:
        questions = self.cached_get_ordered_visible_questions(form)
        if questions:
            return questions[-1]
        return None

    def get_form_for_question(self, question_id: UUID) -> Form:
        for form in self.collection.forms:
            if any(q.id == question_id for q in form.cached_questions):
                return form

        raise ValueError(f"Could not find form for question_id={question_id} in collection={self.collection.id}")

    def _statuses_for_all_forms(self) -> dict[Form, TasklistSectionStatusEnum]:
        return {form: self.get_status_for_form(form) for form in self.collection.forms}

    def _emit_submission_events_for_forms_reset_to_in_progress(
        self, current_form: Form, previous_form_statuses: dict[Form, TasklistSectionStatusEnum], user: User
    ) -> None:
        if previous_form_statuses[current_form] == TasklistSectionStatusEnum.COMPLETED:
            interfaces.collections.add_submission_event(
                self.submission,
                event_type=SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS,
                user=user,
                related_entity_id=current_form.id,
            )
            del previous_form_statuses[current_form]

        for form, old_form_status in previous_form_statuses.items():
            if (
                old_form_status == TasklistSectionStatusEnum.COMPLETED
                and self.get_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS
            ):
                interfaces.collections.add_submission_event(
                    self.submission,
                    event_type=SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS,
                    user=user,
                    related_entity_id=form.id,
                )

    def _get_answer_for_question(
        self, question_id: UUID, add_another_index: int | None = None, allow_new_index: bool = False
    ) -> AllAnswerTypes | None:
        question = self.get_question(question_id)

        if question.add_another_container:
            if add_another_index is None:
                raise ValueError("add_another_index must be provided for questions within an add another container")
            if add_another_index >= self.submission.data_manager.get_count_for_add_another(
                question.add_another_container
            ):
                if allow_new_index:
                    return None
                # we raise here instead of returning None as the consuming code should never ask for an answer to an
                # add another entry that doesn't exist
                raise ValueError("no add another entry exists at this index")

        return self.submission.data_manager.get(question, add_another_index=add_another_index)

    def submit_answer_for_question(
        self, question_id: UUID, form: DynamicQuestionForm, user: User, *, add_another_index: int | None = None
    ) -> None:
        if self.is_locked_state:
            raise ValueError(
                f"Could not submit answer for question_id={question_id} "
                f"because submission id={self.id} is already submitted."
            )

        question = self.get_question(question_id)
        current_form = self.get_form_for_question(question_id)
        current_form_statuses = self._statuses_for_all_forms()

        data = _form_data_to_question_type(question, form)

        if self.collection.allow_multiple_submissions and self.collection.submission_name_question == question:
            if question.add_another_container:
                raise RuntimeError(
                    "A multi-submission collection cannot have an add-another question as its submission name"
                )

            if self.submission.grant_recipient and self.submission.mode != SubmissionModeEnum.PREVIEW:
                multi_submissions = interfaces.collections.get_submissions_by_grant_recipient_collection(
                    self.submission.grant_recipient, self.collection.id
                )

                answer = data.get_value_for_text_export()
                current_answer = self.cached_get_answer_for_question(question_id)
                other_answers = [
                    SubmissionHelper(s).cached_get_answer_for_question(question_id)
                    for s in multi_submissions
                    if s != self.submission
                ]

                if any(
                    (other_answer.get_value_for_text_export().lower() == data.get_value_for_text_export().lower())
                    for other_answer in other_answers
                    if other_answer
                ):
                    raise SubmissionAnswerConflict(f"Another submission for “{answer}” already exists")

                if (
                    self.collection.multiple_submissions_are_managed_by_service
                    and current_answer is not None
                    and current_answer != data
                ):
                    raise RuntimeError(
                        f"The answer to the submission name question cannot be changed in managed multi-submission "
                        f"collections (submission_id={self.id}, question_id={question_id})"
                    )

        if question.data_type == QuestionDataType.FILE_UPLOAD:
            key = self.format_s3_key(question_id, add_another_index)
            file_storage = cast(FileStorage, form.get_answer_to_question(question))
            # ensure the file stream is at the beginning, it may have changed during validation or serialisation
            # todo: check the implications of this being off and remove if unnecessary
            file_storage.stream.seek(0)
            s3_service.upload_file(file_storage, key)
            assert isinstance(data, FileUploadAnswer)
            data.key = key

        self.submission.data_manager.set(question, data, add_another_index=add_another_index)
        update_submission_data(self.submission)

        self.cached_get_answer_for_question.cache_clear()
        self.cached_get_all_questions_are_answered_for_form.cache_clear()
        del self.cached_evaluation_context
        del self._visibility_resolver

        # FIXME: work out why end to end tests aren't happy without this here
        #        I've made it work but not happy with not clearly pointing to where
        #        an instance was failing to route (next_url) appropriately without it
        self.cached_get_ordered_visible_questions.cache_clear()

        self._emit_submission_events_for_forms_reset_to_in_progress(current_form, current_form_statuses, user)

    def remove_entry_for_add_another(self, add_another_container: Group, add_another_index: int) -> None:
        if self.is_locked_state:
            raise ValueError(
                f"Could not remove entry for add another id={add_another_container.id} "
                f"because submission id={self.id} is already submitted."
            )

        keys_to_delete = [
            answer.key
            for question in add_another_container.cached_questions
            if question.data_type == QuestionDataType.FILE_UPLOAD
            and (answer := self.cached_get_answer_for_question(question.id, add_another_index=add_another_index))
            and isinstance(answer, FileUploadAnswer)
            and answer.key
        ]
        self.submission.data_manager.remove_add_another_entry(
            add_another_container, add_another_index=add_another_index
        )
        update_submission_data(self.submission)

        for key in keys_to_delete:
            s3_service.delete_file(key)

        self.cached_get_answer_for_question.cache_clear()
        self.cached_get_all_questions_are_answered_for_form.cache_clear()
        del self.cached_evaluation_context
        del self._visibility_resolver
        self.cached_get_ordered_visible_questions.cache_clear()

    def remove_answer_for_question(self, question_id: UUID, *, add_another_index: int | None = None) -> None:
        if self.is_locked_state:
            raise ValueError(
                f"Could not remove answer for question_id={question_id} "
                f"because submission id={self.id} is already submitted."
            )

        question = self.get_question(question_id)

        keys_to_delete = []
        if question.data_type == QuestionDataType.FILE_UPLOAD:
            answer = self.cached_get_answer_for_question(question_id, add_another_index=add_another_index)
            if isinstance(answer, FileUploadAnswer) and answer.key:
                keys_to_delete.append(answer.key)

        self.submission.data_manager.remove(question, add_another_index=add_another_index)
        update_submission_data(self.submission)

        for key in keys_to_delete:
            s3_service.delete_file(key)

        self.cached_get_answer_for_question.cache_clear()
        self.cached_get_all_questions_are_answered_for_form.cache_clear()
        del self.cached_evaluation_context
        del self._visibility_resolver
        self.cached_get_ordered_visible_questions.cache_clear()

    def _data_providers_for_lifecycle_emails(self, user: User) -> Sequence[User]:
        if self.is_preview:
            return []

        if self.is_test:
            if user not in self.submission.grant_recipient.data_providers:
                current_app.logger.error(
                    (
                        "%(user_id)s is not a data provider for "
                        "test submission %(submission_id)s when sending lifecycle emails"
                    ),
                    dict(user_id=user.id, submission_id=self.id),
                )
            return [user]

        return self.submission.grant_recipient.data_providers

    def _certifiers_for_lifecycle_emails(self, user: User) -> Sequence[User]:
        if self.is_preview:
            return []

        if self.is_test:
            if user not in self.submission.grant_recipient.certifiers:
                current_app.logger.error(
                    (
                        "%(user_id)s is not a certifier for "
                        "test submission %(submission_id)s when sending lifecycle emails"
                    ),
                    dict(user_id=user.id, submission_id=self.id),
                )
            return [user]

        return self.submission.grant_recipient.certifiers

    @property
    def validator(self) -> SubmissionValidator:
        return SubmissionValidator(
            submission=self.submission,
            forms=self.get_ordered_visible_forms(),
            visibility_resolver=self._visibility_resolver,
            data_manager=self.submission.data_manager,
            evaluation_context=self.cached_evaluation_context,
            interpolation_context=self.cached_interpolation_context,
        )

    def submit(self, user: User) -> None:
        if self.is_submitted:
            return

        if not self.all_needed_forms_are_completed:
            raise ValueError(f"Could not submit submission id={self.id} because not all forms are complete.")

        if self.is_live:
            if self.status != SubmissionStatusEnum.READY_TO_SUBMIT:
                raise ValueError(f"Could not submit submission id={self.id} because it is not ready to submit.")

            if self.collection.requires_certification:
                if not self.events.submission_state.is_approved:
                    raise ValueError(f"Could not submit submission id={self.id} because it has not been approved.")

                if not AuthorisationHelper.is_access_grant_certifier(
                    self.grant.id, self.submission.grant_recipient.organisation.id, user
                ):
                    raise SubmissionAuthorisationError(
                        f"User does not have certifier permission to submit submission {self.id}",
                        user,
                        self.id,
                        RoleEnum.CERTIFIER,
                    )
            else:
                if not AuthorisationHelper.is_access_grant_data_provider(
                    self.grant.id, self.submission.grant_recipient.organisation.id, user
                ):
                    raise SubmissionAuthorisationError(
                        f"User does not have data provider permission to submit submission {self.id}",
                        user,
                        self.id,
                        RoleEnum.DATA_PROVIDER,
                    )

        self.validator.validate_all_reachable_questions()

        interfaces.collections.add_submission_event(
            self.submission,
            event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
            user=user,
            related_entity_id=self.submission.id,
        )

        unique_users = set(self._data_providers_for_lifecycle_emails(user)) | set(
            self._certifiers_for_lifecycle_emails(user)
        )
        for unique_user in unique_users:
            notification_service.send_access_submission_submitted(
                email_address=unique_user.email,
                submission_helper=self,
            )

    def mark_as_sent_for_certification(self, user: User) -> None:
        if self.is_locked_state:
            return

        if not self.collection.requires_certification:
            raise ValueError(
                f"Could not send submission id={self.id} for sign off because this report does not require "
                f"certification."
            )

        self.validator.validate_all_reachable_questions()

        if self.all_needed_forms_are_completed:
            interfaces.collections.add_submission_event(
                self.submission, event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION, user=user
            )

            for data_provider in self._data_providers_for_lifecycle_emails(user):
                notification_service.send_access_submission_sent_for_certification_confirmation(
                    data_provider.email, submission_helper=self
                )
            for certifier in self._certifiers_for_lifecycle_emails(user):
                assert self.sent_for_certification_by is not None
                notification_service.send_access_submission_ready_to_certify(
                    certifier.email,
                    submission_helper=self,
                    submitted_by=self.sent_for_certification_by,
                )
        else:
            raise ValueError(f"Could not send submission id={self.id} for sign off because not all forms are complete.")

    def decline_certification(self, user: User, declined_reason: str) -> None:
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

            # There are two distinct emails for data providers and certifiers in this flow so we want users to receive
            # the relevant ones, even if they have both permissions.
            for data_provider in self._data_providers_for_lifecycle_emails(user):
                notification_service.send_access_submitter_submission_declined(
                    user=data_provider, submission_helper=self
                )

            for certifier in self._certifiers_for_lifecycle_emails(user):
                notification_service.send_access_certifier_confirm_submission_declined(
                    user=certifier,
                    submission_helper=self,
                )

        else:
            raise ValueError(
                f"Could not decline certification for submission id={self.id} because it is not awaiting sign off."
            )

    def certify(self, user: User) -> None:
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

        if not self.status == SubmissionStatusEnum.AWAITING_SIGN_OFF:
            raise ValueError(
                f"Could not approve certification for submission id={self.id} because it is not awaiting sign off."
            )

        interfaces.collections.add_submission_event(
            self.submission, event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER, user=user
        )

    def toggle_form_completed(self, form: Form, user: User, is_complete: bool) -> None:
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
    def get_next_question(self, current_question_id: UUID, *, add_another_index: int | None = None) -> Question | None:
        """
        Retrieve the next question that should be shown to the user, or None if this was the last relevant question.
        """
        form = self.get_form_for_question(current_question_id)
        question = self.get_question(current_question_id)

        _add_another_index = add_another_index if question.add_another_container else None

        questions = self.cached_get_ordered_visible_questions(form, add_another_index=_add_another_index)

        question_iterator = iter(questions)
        for question in question_iterator:
            if question.id == current_question_id:
                return next(question_iterator, None)

        raise ValueError(f"Could not find a question with id={current_question_id} in collection={self.collection}")

    def get_previous_question(self, current_question_id: UUID, add_another_index: int | None = None) -> Question | None:
        """
        Retrieve the question that was asked before this one, or None if this was the first relevant question.
        """
        form = self.get_form_for_question(current_question_id)

        question = self.get_question(current_question_id)

        _add_another_index = add_another_index if question.add_another_container else None

        questions = self.cached_get_ordered_visible_questions(form, add_another_index=_add_another_index)

        # Reverse the list of questions so that we're working from the end to the start.
        question_iterator = iter(reversed(questions))
        for question in question_iterator:
            if question.id == current_question_id:
                return next(question_iterator, None)

        raise ValueError(f"Could not find a question with id={current_question_id} in collection={self.collection}")

    def get_answer_summary_for_add_another(
        self, component: Component, *, add_another_index: int
    ) -> AddAnotherAnswerSummary:
        if not component.add_another_container:
            raise ValueError("answer summaries can only be generated for components in an add another container")

        if self.get_count_for_add_another(component.add_another_container) <= add_another_index:
            return AddAnotherAnswerSummary(summary="", is_answered=False)

        visible_questions = (
            self.cached_get_ordered_visible_questions(
                component.add_another_container, add_another_index=add_another_index
            )
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
    collection: Collection
    submission_mode: SubmissionModeEnum
    submissions: list[Submission]
    submission_helpers: dict[UUID, SubmissionHelper]

    def __init__(self, collection: Collection, submission_mode: SubmissionModeEnum):
        if submission_mode == SubmissionModeEnum.PREVIEW:
            raise ValueError("Cannot create a collection helper for preview submissions.")

        self.collection = collection
        self.submission_mode = submission_mode
        self.submissions = [s for s in (get_all_submissions_with_mode_for_collection(collection.id, submission_mode))]
        self.submission_helpers = {s.id: SubmissionHelper(s) for s in self.submissions}

        grant_recipient_mode = (
            GrantRecipientModeEnum.TEST if submission_mode == SubmissionModeEnum.TEST else GrantRecipientModeEnum.LIVE
        )
        self.grant_recipients = get_grant_recipients(
            self.collection.grant, mode=grant_recipient_mode, with_organisations=True
        )
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

    def get_all_possible_questions_for_collection(self) -> list[Question]:
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
            ["Submission reference", "Grant recipient"]
            + (["Submission name"] if self.collection.allow_multiple_submissions else [])
            + ["Created by", "Created at"]
            + (["Certified by", "Certified at"] if self.collection.requires_certification else [])
            + [
                "Status",
                "Submitted at",
            ]
        )

        question_headers: list[tuple[Question, str, int | None]] = []
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
                "Created at": submission.created_at_utc.isoformat(" ", "seconds"),
                "Status": submission.status,
                "Submitted at": submission.submitted_at_utc.isoformat(" ", "seconds")
                if submission.submitted_at_utc
                else None,
            }

            if self.collection.requires_certification:
                submission_csv_data["Certified by"] = (
                    submission.events.submission_state.certified_by.email
                    if submission.events.submission_state.certified_by
                    else None
                )
                submission_csv_data["Certified at"] = (
                    submission.events.submission_state.certified_at_utc.isoformat(" ", "seconds")
                    if submission.events.submission_state.certified_at_utc
                    else None
                )

            if self.collection.allow_multiple_submissions:
                submission_csv_data["Submission name"] = submission.submission_name

            visible_questions = submission.all_visible_questions
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
                        if submission.is_component_visible(question, add_another_index=index):
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
                "grant_recipient": (
                    submission.submission.grant_recipient.organisation.name
                    if submission.submission.grant_recipient
                    else None
                ),
            }

            if self.collection.allow_multiple_submissions:
                submission_data["name"] = submission.submission_name

            submission_data["created_by"] = submission.created_by_email
            submission_data["created_at_utc"] = submission.created_at_utc.isoformat(" ", "seconds")
            submission_data["status"] = submission.status
            submission_data["submitted_at_utc"] = (
                submission.submitted_at_utc.isoformat(" ", "seconds") if submission.submitted_at_utc else None
            )

            if self.collection.requires_certification:
                submission_data["certified_by"] = (
                    submission.events.submission_state.certified_by.email
                    if submission.events.submission_state.certified_by
                    else None
                )
                submission_data["certified_at_utc"] = (
                    submission.events.submission_state.certified_at_utc.isoformat(" ", "seconds")
                    if submission.events.submission_state.certified_at_utc
                    else None
                )

            submission_data["sections"] = []

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

                                for q in submission.cached_get_ordered_visible_questions(
                                    question.add_another_container
                                ):
                                    answer = submission.cached_get_answer_for_question(q.id, add_another_index=i)
                                    entry[q.name] = answer.get_value_for_json_export() if answer is not None else None
                                task_data["answers"][question.add_another_container.name.lower()].append(entry)
                    else:
                        answer = submission.cached_get_answer_for_question(question.id)
                        task_data["answers"][question.name] = (
                            answer.get_value_for_json_export() if answer is not None else None
                        )
                submission_data["sections"].append(task_data)

            submissions_data["submissions"].append(submission_data)

        return json.dumps(submissions_data)


def _form_data_to_question_type(question: Question, form: DynamicQuestionForm) -> AllAnswerTypes:
    _QuestionModel: type[PydanticBaseModel]

    answer = form.get_answer_to_question(question)

    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE | QuestionDataType.EMAIL | QuestionDataType.URL:
            return TextSingleLineAnswer(answer)
        case QuestionDataType.TEXT_MULTI_LINE:
            return TextMultiLineAnswer(answer)
        case QuestionDataType.NUMBER:
            if question.data_options.number_type == NumberTypeEnum.DECIMAL:
                return DecimalAnswer(value=answer, prefix=question.prefix, suffix=question.suffix)
            return IntegerAnswer(value=answer, prefix=question.prefix, suffix=question.suffix)
        case QuestionDataType.YES_NO:
            return YesNoAnswer(answer)
        case QuestionDataType.RADIOS:
            assert question.data_source is not None
            label = next(item.label for item in question.data_source.items if item.key == answer)
            return SingleChoiceFromListAnswer(key=answer, label=label)
        case QuestionDataType.CHECKBOXES:
            assert question.data_source is not None
            choices = [
                ChoiceDict({"key": item.key, "label": item.label})
                for item in question.data_source.items
                if item.key in answer
            ]
            return MultipleChoiceFromListAnswer(choices=choices)
        case QuestionDataType.DATE:
            return DateAnswer(answer=answer, approximate_date=question.approximate_date or False)
        case QuestionDataType.FILE_UPLOAD:
            assert isinstance(answer, FileStorage)
            assert answer.filename is not None
            return FileUploadAnswer(
                filename=secure_filename(answer.filename),
                # todo: we'll probably have to seek through the file to find this
                #       which will have been done during validation which is an unfortunate duplication
                size=answer.content_length,
                mime_type=answer.mimetype,
            )

    raise ValueError(f"Could not parse data for question type={question.data_type}")
