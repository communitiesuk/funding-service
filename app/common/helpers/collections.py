import uuid
from itertools import chain
from typing import TYPE_CHECKING, Optional
from uuid import UUID

from pydantic import RootModel, TypeAdapter

from app.common.collections.forms import DynamicQuestionForm
from app.common.data import interfaces
from app.common.data.interfaces.collections import get_collection
from app.common.data.types import CollectionStatusEnum, QuestionDataType

if TYPE_CHECKING:
    from app.common.data.models import Collection, Form, Grant, Question, Section


TextSingleLine = RootModel[str]
TextMultiLine = RootModel[str]
Integer = RootModel[int]


class CollectionHelper:
    """
    This offensively-named class is a helper for the `app.common.data.models.Collection` and associated sub-models.

    It wraps a Collection instance from the DB and encapsulates the business logic that will make it easy to deal with
    conditionals, routing, storing+retrieving data, etc in one place, consistently.
    """

    def __init__(self, collection: "Collection"):
        """
        Initialise the CollectionHelper; the `collection` instance passed in should have been retrieved from the DB
        with the schema and related tables (eg section, form, question) eagerly loaded to prevent this helper from
        making any further DB queries. Use `get_collection` with the `with_full_schema=True` option.
        :param collection:
        """
        self.collection = collection
        self.schema = self.collection.collection_schema

    @classmethod
    def load(cls, collection_id: uuid.UUID) -> "CollectionHelper":
        return cls(get_collection(collection_id, with_full_schema=True))

    @property
    def grant(self) -> "Grant":
        return self.schema.grant

    @property
    def sections(self) -> list["Section"]:
        return self.schema.sections

    @property
    def name(self) -> str:
        return self.schema.name

    @property
    def status(self) -> str:
        form_statuses = set(
            [
                self.get_status_for_form(form)
                for form in chain.from_iterable(section.forms for section in self.schema.sections)
            ]
        )
        if {CollectionStatusEnum.COMPLETED} == form_statuses:
            return CollectionStatusEnum.COMPLETED
        elif {CollectionStatusEnum.NOT_STARTED} == form_statuses:
            return CollectionStatusEnum.NOT_STARTED
        else:
            return CollectionStatusEnum.IN_PROGRESS

    def get_section(self, section_id: uuid.UUID) -> "Section":
        try:
            return next(filter(lambda s: s.id == section_id, self.schema.sections))
        except StopIteration as e:
            raise ValueError(f"Could not find a section with id={section_id} in schema={self.schema.id}") from e

    def get_form(self, form_id: uuid.UUID) -> "Form":
        try:
            return next(
                filter(
                    lambda f: f.id == form_id, chain.from_iterable(section.forms for section in self.schema.sections)
                )
            )
        except StopIteration as e:
            raise ValueError(f"Could not find a form with id={form_id} in schema={self.schema.id}") from e

    def get_question(self, question_id: uuid.UUID) -> "Question":
        try:
            return next(
                filter(
                    lambda q: q.id == question_id,
                    chain.from_iterable(form.questions for section in self.schema.sections for form in section.forms),
                )
            )
        except StopIteration as e:
            raise ValueError(f"Could not find a question with id={question_id} in schema={self.schema.id}") from e

    def get_ordered_visible_sections(self) -> list["Section"]:
        """Returns the visible, ordered sections based upon the current state of this collection."""
        return sorted(self.sections, key=lambda s: s.order)

    def get_status_for_form(self, form: "Form") -> str:
        # there's likely a slicker interface for this helper but just brute forcing it for now
        visible_questions = self.get_ordered_visible_questions_for_form(form)
        answers = [answer for q in visible_questions if (answer := self.get_answer_for_question(q.id)) is not None]
        if visible_questions and len(visible_questions) == len(answers):
            return CollectionStatusEnum.COMPLETED
        elif answers:
            return CollectionStatusEnum.IN_PROGRESS
        else:
            return CollectionStatusEnum.NOT_STARTED

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

    def get_form_for_question(self, question_id: UUID) -> "Form":
        for section in self.schema.sections:
            for form in section.forms:
                if any(q.id == question_id for q in form.questions):
                    return form

        raise ValueError(f"Could not find form for question_id={question_id} in collection_schema={self.schema.id}")

    def get_answer_for_question(self, question_id: UUID) -> TextSingleLine | TextMultiLine | Integer | None:
        question = self.get_question(question_id)
        serialised_data = self.collection.data.get(str(question_id))
        return _deserialise_question_type(question, serialised_data) if serialised_data else None

    def submit_answer_for_question(self, question_id: UUID, form: DynamicQuestionForm) -> None:
        question = self.get_question(question_id)
        data = _form_data_to_question_type(question, form)
        interfaces.collections.update_collection_data(self.collection, question, data)

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

        raise ValueError(f"Could not find a question with id={current_question_id} in schema={self.schema}")

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

        raise ValueError(f"Could not find a question with id={current_question_id} in schema={self.schema}")


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
