from typing import TYPE_CHECKING, Optional
from uuid import UUID

from app.common.data.types import CollectionStatusEnum

if TYPE_CHECKING:
    from app.common.data.models import Collection, Form, Grant, Question, Section


class CollectionHelper:
    """
    This offensively-named class is a helper for the `app.common.data.models.Collection` and associated sub-models.

    It wraps a Collection instance from the DB and encapsulates the business logic that will make it easy to deal with
    conditionals, routing, storing+retrieving data, etc in one place, consistently.
    """

    def __init__(self, collection: "Collection"):
        self.collection = collection
        self.schema = collection.collection_schema

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
        return CollectionStatusEnum.NOT_STARTED

    def get_ordered_visible_sections(self) -> list["Section"]:
        """Returns the visible, ordered sections based upon the current state of this collection."""
        return sorted(self.sections, key=lambda s: s.order)

    def get_status_for_form(self, form: "Form") -> str:
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

        raise ValueError(f"Could not find form for {question_id=} in collection_schema={self.schema.id}")

    def get_next_question(self, current_question_id: UUID) -> Optional["Question"]:
        """
        Retrieve the next question that should be shown to the user, or None if this was the last relevant question.
        """
        form = self.get_form_for_question(current_question_id)
        questions = self.get_ordered_visible_questions_for_form(form)

        question_iterator = iter(questions)
        if not current_question_id:
            return next(question_iterator, None)

        for question in question_iterator:
            if question.id == current_question_id:
                return next(question_iterator, None)

        return None
