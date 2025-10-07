import csv
import json
import uuid
from datetime import datetime
from functools import cached_property, lru_cache, partial
from io import StringIO
from itertools import chain
from typing import TYPE_CHECKING, Any, Callable, List, Optional, Union
from uuid import UUID

from pydantic import BaseModel as PydanticBaseModel
from pydantic import TypeAdapter

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
    QuestionDataType,
    SubmissionEventKey,
    SubmissionModeEnum,
    SubmissionStatusEnum,
    TasklistTaskStatusEnum,
)
from app.common.expressions import (
    ExpressionContext,
    UndefinedVariableInExpression,
    evaluate,
    interpolate,
)
from app.common.filters import format_datetime

if TYPE_CHECKING:
    from app.common.data.models import (
        Collection,
        Component,
        Expression,
        Form,
        Grant,
        Group,
        Question,
        Submission,
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
    def load(cls, submission_id: uuid.UUID) -> "SubmissionHelper":
        return cls(get_submission(submission_id, with_full_schema=True))

    @staticmethod
    def get_interpolator(
        collection: "Collection", submission_helper: Optional["SubmissionHelper"] = None
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

    @cached_property
    def cached_form_data(self) -> dict[str, Any]:
        form_data = {
            question.safe_qid: (
                answer.get_value_for_form()
                if not question.add_another_container
                else [a.get_value_for_form() for a in answer]
            )
            for form in self.submission.collection.forms
            for question in form.cached_questions
            if (answer := self.cached_get_answer_for_question(question.id)) is not None
        }
        return form_data

    @property
    def all_visible_questions(self) -> dict[UUID, "Question"]:
        return {
            question.id: question
            for form in self.get_ordered_visible_forms()
            for question in self.cached_get_ordered_visible_questions(form)
        }

    @property
    def status(self) -> str:
        submitted = SubmissionEventKey.SUBMISSION_SUBMITTED in [x.key for x in self.submission.events]

        form_statuses = set([self.get_status_for_form(form) for form in self.collection.forms])
        if {SubmissionStatusEnum.COMPLETED} == form_statuses and submitted:
            return SubmissionStatusEnum.COMPLETED
        elif {SubmissionStatusEnum.NOT_STARTED} == form_statuses:
            return SubmissionStatusEnum.NOT_STARTED
        else:
            return SubmissionStatusEnum.IN_PROGRESS

    @property
    def submitted_at_utc(self) -> datetime | None:
        if not self.is_completed:
            return None

        submitted = next(
            filter(lambda e: e.key == SubmissionEventKey.SUBMISSION_SUBMITTED, reversed(self.submission.events)),
            None,
        )
        if not submitted:
            return None

        return submitted.created_at_utc

    @property
    def is_completed(self) -> bool:
        return self.status == SubmissionStatusEnum.COMPLETED

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

    def _get_all_questions_are_answered_for_form(self, form: "Form") -> tuple[bool, list[AllAnswerTypes]]:
        visible_questions = self.cached_get_ordered_visible_questions(form)
        answers = [
            answer for q in visible_questions if (answer := self.cached_get_answer_for_question(q.id)) is not None
        ]
        return len(visible_questions) == len(answers), answers

    @cached_property
    def all_forms_are_completed(self) -> bool:
        form_statuses = set([self.get_status_for_form(form) for form in self.collection.forms])
        return {SubmissionStatusEnum.COMPLETED} == form_statuses

    def get_tasklist_status_for_form(self, form: "Form") -> TasklistTaskStatusEnum:
        if len(form.cached_questions) == 0:
            return TasklistTaskStatusEnum.NO_QUESTIONS

        return TasklistTaskStatusEnum(self.get_status_for_form(form))

    def get_status_for_form(self, form: "Form") -> str:
        all_questions_answered, answers = self.cached_get_all_questions_are_answered_for_form(form)
        marked_as_complete = SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED in [
            x.key for x in self.submission.events if x.form and x.form.id == form.id
        ]
        if form.cached_questions and all_questions_answered and marked_as_complete:
            return SubmissionStatusEnum.COMPLETED
        elif answers:
            return SubmissionStatusEnum.IN_PROGRESS
        else:
            return SubmissionStatusEnum.NOT_STARTED

    def get_ordered_visible_forms(self) -> list["Form"]:
        """Returns the visible, ordered forms based upon the current state of this collection."""
        return sorted(self.collection.forms, key=lambda f: f.order)

    def is_component_visible(self, component: "Component", context: "ExpressionContext") -> bool:
        # we can optimise this to exit early and do this in a sensible order if we switch
        # to going through questions in a nested way rather than flat
        def get_all_conditions(component: "Component") -> list["Expression"]:
            conditions = []

            # start outside and move in from top level conditions to innermost
            if component.parent:
                conditions.extend(get_all_conditions(component.parent))
            conditions.extend(component.conditions)
            return conditions

        try:
            return all(evaluate(condition, context) for condition in get_all_conditions(component))
        except UndefinedVariableInExpression:
            # todo: fail open for now - this method should accept an optional bool that allows this condition to fail
            #       or not- checking visibility on the question page itself should never fail - the summary page could
            # todo: check dependency chain for conditions when undefined variables are encountered to avoid
            #       always suppressing errors and not surfacing issues on misconfigured forms
            return False

    def _get_ordered_visible_questions(self, parent: Union["Form", "Group"]) -> list["Question"]:
        """Returns the visible, ordered questions based upon the current state of this collection."""
        return [
            question
            for question in parent.cached_questions
            if self.is_component_visible(question, self.cached_evaluation_context)
        ]

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

    # TODO: if we need to fetch answers at a specific index we can add an add_another_index which would return
    #       a single value - this would have the benefit of checking that entry exists etc.
    def _get_answer_for_question(self, question_id: UUID) -> AllAnswerTypes | list[AllAnswerTypes] | None:
        question = self.get_question(question_id)

        if not question.add_another_container:
            serialised_data = self.submission.data.get(str(question_id))
            return _deserialise_question_type(question, serialised_data) if serialised_data is not None else None
        else:
            serialised_entries = self.submission.data.get(str(question.add_another_container.id), [])
            return [_deserialise_question_type(question, entry.get(str(question_id))) for entry in serialised_entries]

    def submit_answer_for_question(self, question_id: UUID, form: DynamicQuestionForm) -> None:
        if self.is_completed:
            raise ValueError(
                f"Could not submit answer for question_id={question_id} "
                f"because submission id={self.id} is already submitted."
            )

        question = self.get_question(question_id)
        data = _form_data_to_question_type(question, form)
        interfaces.collections.update_submission_data(self.submission, question, data)
        self.cached_get_answer_for_question.cache_clear()
        self.cached_get_all_questions_are_answered_for_form.cache_clear()

        # FIXME: work out why end to end tests aren't happy without this here
        #        I've made it work but not happy with not clearly pointing to where
        #        an instance was failing to route (next_url) appropriately without it
        self.cached_get_ordered_visible_questions.cache_clear()

    def submit(self, user: "User") -> None:
        if self.is_completed:
            return

        if self.all_forms_are_completed:
            interfaces.collections.add_submission_event(self.submission, SubmissionEventKey.SUBMISSION_SUBMITTED, user)
        else:
            raise ValueError(f"Could not submit submission id={self.id} because not all forms are complete.")

    def toggle_form_completed(self, form: "Form", user: "User", is_complete: bool) -> None:
        form_complete = self.get_status_for_form(form) == SubmissionStatusEnum.COMPLETED
        if is_complete == form_complete:
            return

        if is_complete:
            all_questions_answered, _ = self.cached_get_all_questions_are_answered_for_form(form)
            if not all_questions_answered:
                raise ValueError(
                    f"Could not mark form id={form.id} as complete because not all questions have been answered."
                )

            interfaces.collections.add_submission_event(
                self.submission, SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED, user, form
            )
        else:
            interfaces.collections.clear_submission_events(
                self.submission, SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED, form
            )

    def get_next_question(self, current_question_id: UUID) -> Optional["Question"]:
        """
        Retrieve the next question that should be shown to the user, or None if this was the last relevant question.
        """
        form = self.get_form_for_question(current_question_id)

        questions = self.cached_get_ordered_visible_questions(form)

        question_iterator = iter(questions)
        for question in question_iterator:
            if question.id == current_question_id:
                return next(question_iterator, None)

        raise ValueError(f"Could not find a question with id={current_question_id} in collection={self.collection}")

    def get_previous_question(self, current_question_id: UUID) -> Optional["Question"]:
        """
        Retrieve the question that was asked before this one, or None if this was the first relevant question.
        """
        form = self.get_form_for_question(current_question_id)
        questions = self.cached_get_ordered_visible_questions(form)

        # Reverse the list of questions so that we're working from the end to the start.
        question_iterator = iter(reversed(questions))
        for question in question_iterator:
            if question.id == current_question_id:
                return next(question_iterator, None)

        raise ValueError(f"Could not find a question with id={current_question_id} in collection={self.collection}")


class CollectionHelper:
    collection: "Collection"
    submission_mode: SubmissionModeEnum
    submissions: List["Submission"]
    submission_helpers: dict[UUID, SubmissionHelper]

    def __init__(self, collection: "Collection", submission_mode: SubmissionModeEnum):
        self.collection = collection
        self.submission_mode = submission_mode
        self.submissions = [
            s for s in (get_all_submissions_with_mode_for_collection_with_full_schema(collection.id, submission_mode))
        ]
        self.submission_helpers = {s.id: SubmissionHelper(s) for s in self.submissions}

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

    def generate_csv_content_for_all_submissions(self) -> str:
        metadata_headers = ["Submission reference", "Created by", "Created at", "Status", "Submitted at"]
        question_headers = {
            question.id: f"[{question.form.title}] {question.name}"
            for question in self.get_all_possible_questions_for_collection()
        }
        all_headers = metadata_headers + [header_string for _, header_string in question_headers.items()]

        csv_output = StringIO()
        csv_writer = csv.DictWriter(csv_output, fieldnames=all_headers)
        csv_writer.writeheader()
        for submission in [value for key, value in self.submission_helpers.items()]:
            submission_csv_data = {
                "Submission reference": submission.reference,
                "Created by": submission.created_by_email,
                "Created at": format_datetime(submission.created_at_utc),
                "Status": submission.status,
                "Submitted at": format_datetime(submission.submitted_at_utc) if submission.submitted_at_utc else None,
            }
            visible_questions = submission.all_visible_questions
            for question_id, header_string in question_headers.items():
                if question_id not in visible_questions.keys():
                    submission_csv_data[header_string] = NOT_ASKED
                else:
                    answer = submission.cached_get_answer_for_question(question_id)
                    submission_csv_data[header_string] = (
                        answer.get_value_for_text_export() if answer is not None else NOT_ANSWERED
                    )

            csv_writer.writerow(submission_csv_data)

        return csv_output.getvalue()

    def generate_json_content_for_all_submissions(self) -> str:
        submissions_data: dict[str, Any] = {"submissions": []}
        for submission in self.submission_helpers.values():
            submission_data: dict[str, Any] = {
                "reference": submission.reference,
                "created_by": submission.created_by_email,
                "created_at_utc": format_datetime(submission.created_at_utc),
                "status": submission.status,
                "submitted_at_utc": format_datetime(submission.submitted_at_utc)
                if submission.submitted_at_utc
                else None,
                "tasks": [],
            }

            for form in submission.get_ordered_visible_forms():
                task_data: dict[str, Any] = {"name": form.title, "answers": {}}
                for question in submission.cached_get_ordered_visible_questions(form):
                    answer = submission.cached_get_answer_for_question(question.id)
                    task_data["answers"][question.name] = (
                        answer.get_value_for_json_export() if answer is not None else None
                    )
                submission_data["tasks"].append(task_data)

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
