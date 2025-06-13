import abc
import enum
import uuid
from datetime import datetime
from itertools import chain
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic import BaseModel, RootModel, TypeAdapter

from app.common.collections.forms import DynamicQuestionForm
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_submission
from app.common.data.models_user import User
from app.common.data.types import QuestionDataType, SubmissionEventKey, SubmissionModeEnum, SubmissionStatusEnum

if TYPE_CHECKING:
    from app.common.data.models import Form, Grant, Question, Section, Submission


TextSingleLine = RootModel[str]
TextMultiLine = RootModel[str]
Integer = RootModel[int]


# todo: think about where this should go
class ManagedExpressions(enum.StrEnum):
    GREATER_THAN = "GREATER_THAN"


class BaseExpression(BaseModel):
    key: ManagedExpressions

    @property
    @abc.abstractmethod
    def expression(self) -> str:
        raise NotImplementedError


class GreaterThan(BaseExpression):
    key: ManagedExpressions = ManagedExpressions.GREATER_THAN
    question_id: UUID
    minimum_value: int

    @property
    def description(self) -> str:
        return "Is greater than"

    @property
    def message(self) -> str:
        # todo: optionally include the question name in the default message
        # todo: do you allow the form builder to override this if they need to
        #       - does that persist in the context (inherited from BaseExpression) or as a separate
        #         property on the model
        # todo: make this use expression evaluation/interpolation rather than f-strings
        return f"The answer must be {self.minimum_value} or greater"

    @property
    def expression(self) -> str:
        # todo: are UUIDs parsable by the expression parser/ language
        return f"(( {self.question_id} )) > {self.minimum_value}"


class SubmissionHelper:
    """
    This offensively-named class is a helper for the `app.common.data.models.Submission` and associated sub-models.

    It wraps a Submission instance from the DB and encapsulates the business logic that will make it easy to deal with
    conditionals, routing, storing+retrieving data, etc in one place, consistently.
    """

    def __init__(self, submission: "Submission"):
        """
        Initialise the SubmissionHelper; the `submission` instance passed in should have been retrieved from the DB
        with the collection and related tables (eg section, form, question) eagerly loaded to prevent this helper from
        making any further DB queries. Use `get_submission` with the `with_full_schema=True` option.
        :param submission:
        """
        self.submission = submission
        self.collection = self.submission.collection

    @classmethod
    def load(cls, submission_id: uuid.UUID) -> "SubmissionHelper":
        return cls(get_submission(submission_id, with_full_schema=True))

    @property
    def grant(self) -> "Grant":
        return self.collection.grant

    @property
    def sections(self) -> list["Section"]:
        return self.collection.sections

    @property
    def name(self) -> str:
        return self.collection.name

    @property
    def reference(self) -> str:
        return self.submission.reference

    @property
    def status(self) -> str:
        submitted = SubmissionEventKey.SUBMISSION_SUBMITTED in [x.key for x in self.submission.events]

        form_statuses = set(
            [
                self.get_status_for_form(form)
                for form in chain.from_iterable(section.forms for section in self.collection.sections)
            ]
        )
        if {SubmissionStatusEnum.COMPLETED} == form_statuses and submitted:
            return SubmissionStatusEnum.COMPLETED
        elif {SubmissionStatusEnum.NOT_STARTED} == form_statuses:
            return SubmissionStatusEnum.NOT_STARTED
        else:
            return SubmissionStatusEnum.IN_PROGRESS

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

    def get_section(self, section_id: uuid.UUID) -> "Section":
        try:
            return next(filter(lambda s: s.id == section_id, self.collection.sections))
        except StopIteration as e:
            raise ValueError(f"Could not find a section with id={section_id} in collection={self.collection.id}") from e

    def get_form(self, form_id: uuid.UUID) -> "Form":
        try:
            return next(
                filter(
                    lambda f: f.id == form_id,
                    chain.from_iterable(section.forms for section in self.collection.sections),
                )
            )
        except StopIteration as e:
            raise ValueError(f"Could not find a form with id={form_id} in collection={self.collection.id}") from e

    def get_question(self, question_id: uuid.UUID) -> "Question":
        try:
            return next(
                filter(
                    lambda q: q.id == question_id,
                    chain.from_iterable(
                        form.questions for section in self.collection.sections for form in section.forms
                    ),
                )
            )
        except StopIteration as e:
            raise ValueError(
                f"Could not find a question with id={question_id} in collection={self.collection.id}"
            ) from e

    def get_ordered_visible_sections(self) -> list["Section"]:
        """Returns the visible, ordered sections based upon the current state of this submission."""
        return sorted(self.sections, key=lambda s: s.order)

    def get_all_questions_are_answered_for_form(
        self, form: "Form"
    ) -> tuple[bool, list[TextSingleLine | TextMultiLine | Integer]]:
        visible_questions = self.get_ordered_visible_questions_for_form(form)
        answers = [answer for q in visible_questions if (answer := self.get_answer_for_question(q.id)) is not None]
        return len(visible_questions) == len(answers), answers

    @property
    def all_forms_are_completed(self) -> bool:
        form_statuses = set(
            [
                self.get_status_for_form(form)
                for form in chain.from_iterable(section.forms for section in self.collection.sections)
            ]
        )
        return {SubmissionStatusEnum.COMPLETED} == form_statuses

    def get_status_for_form(self, form: "Form") -> str:
        all_questions_answered, answers = self.get_all_questions_are_answered_for_form(form)
        marked_as_complete = SubmissionEventKey.FORM_RUNNER_FORM_COMPLETED in [
            x.key for x in self.submission.events if x.form and x.form.id == form.id
        ]
        if form.questions and all_questions_answered and marked_as_complete:
            return SubmissionStatusEnum.COMPLETED
        elif answers:
            return SubmissionStatusEnum.IN_PROGRESS
        else:
            return SubmissionStatusEnum.NOT_STARTED

    def get_ordered_visible_forms_for_section(self, section: "Section") -> list["Form"]:
        """Returns the visible, ordered forms for a given section based upon the current state of this collection."""
        return sorted(section.forms, key=lambda f: f.order)

    def get_ordered_visible_questions_for_form(self, form: "Form") -> list["Question"]:
        """Returns the visible, ordered questions for a given form based upon the current state of this collection."""
        return sorted(form.questions, key=lambda q: q.order)

    def get_first_question_for_form(self, form: "Form") -> Optional["Question"]:
        questions = self.get_ordered_visible_questions_for_form(form)
        if questions:
            return questions[0]
        return None

    def get_last_question_for_form(self, form: "Form") -> Optional["Question"]:
        questions = self.get_ordered_visible_questions_for_form(form)
        if questions:
            return questions[-1]
        return None

    def get_form_for_question(self, question_id: UUID) -> "Form":
        for section in self.collection.sections:
            for form in section.forms:
                if any(q.id == question_id for q in form.questions):
                    return form

        raise ValueError(f"Could not find form for question_id={question_id} in collection={self.collection.id}")

    def get_answer_for_question(self, question_id: UUID) -> TextSingleLine | TextMultiLine | Integer | None:
        question = self.get_question(question_id)
        serialised_data = self.submission.data.get(str(question_id))
        return _deserialise_question_type(question, serialised_data) if serialised_data else None

    def submit_answer_for_question(self, question_id: UUID, form: DynamicQuestionForm) -> None:
        if self.is_completed:
            raise ValueError(
                f"Could not submit answer for question_id={question_id} "
                f"because submission id={self.id} is already submitted."
            )

        question = self.get_question(question_id)
        data = _form_data_to_question_type(question, form)
        interfaces.collections.update_submission_data(self.submission, question, data)

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
            all_questions_answered, _ = self.get_all_questions_are_answered_for_form(form)
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
        questions = self.get_ordered_visible_questions_for_form(form)

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
        questions = self.get_ordered_visible_questions_for_form(form)

        # Reverse the list of questions so that we're working from the end to the start.
        question_iterator = iter(reversed(questions))
        for question in question_iterator:
            if question.id == current_question_id:
                return next(question_iterator, None)

        raise ValueError(f"Could not find a question with id={current_question_id} in collection={self.collection}")


def _form_data_to_question_type(
    question: "Question", form: DynamicQuestionForm
) -> TextSingleLine | TextMultiLine | Integer:
    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE:
            assert isinstance(form.question.data, str)
            return TextSingleLine(form.question.data)
        case QuestionDataType.TEXT_MULTI_LINE:
            assert isinstance(form.question.data, str)
            return TextMultiLine(form.question.data)
        case QuestionDataType.INTEGER:
            assert isinstance(form.question.data, int)
            return Integer(form.question.data)
        case _:
            raise ValueError(f"Could not parse data for question type={question.data_type}")


def _deserialise_question_type(
    question: "Question", serialised_data: str | int | float | bool
) -> TextSingleLine | TextMultiLine | Integer:
    match question.data_type:
        case QuestionDataType.TEXT_SINGLE_LINE:
            return TypeAdapter(TextSingleLine).validate_python(serialised_data)
        case QuestionDataType.TEXT_MULTI_LINE:
            return TypeAdapter(TextMultiLine).validate_python(serialised_data)
        case QuestionDataType.INTEGER:
            return TypeAdapter(Integer).validate_python(serialised_data)
        case _:
            raise ValueError(f"Could not deserialise data for question type={question.data_type}")
