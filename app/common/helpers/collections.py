from uuid import UUID

from app.common.data.interfaces.collections import get_collection
from app.common.data.models import Collection, CollectionSchema, Form, Grant, Question, Section
from app.common.data.types import CollectionStatusEnum


class CollectionHelper:
    """
    This offensively-named class is a helper for the `app.common.data.models.Collection` and associated sub-models.

    It wraps a Collection instance from the DB and encapsulates the business logic that will make it easy to deal with
    conditionals, routing, storing+retrieving data, etc in one place, consistently.
    """

    def __init__(self, collection: Collection):
        self._collection = collection

    @classmethod
    def load(cls, collection_id: UUID) -> "CollectionHelper":
        return cls(get_collection(collection_id))

    @property
    def grant(self) -> Grant:
        return self._collection.collection_schema.grant

    @property
    def schema(self) -> CollectionSchema:
        return self._collection.collection_schema

    @property
    def sections(self) -> list[Section]:
        return self._collection.collection_schema.sections

    @property
    def name(self) -> str:
        return self._collection.collection_schema.name

    @property
    def status(self) -> str:
        return CollectionStatusEnum.NOT_STARTED

    def get_ordered_visible_sections(self) -> list[Section]:
        """Returns the visible, ordered sections based upon the current state of this collection."""
        return sorted(self.sections, key=lambda s: s.order)

    def get_status_for_form(self, form: Form) -> str:
        return CollectionStatusEnum.NOT_STARTED

    def get_ordered_visible_forms_for_section(self, section: Section) -> list[Form]:
        """Returns the visible, ordered forms for a given section based upon the current state of this collection."""
        return sorted(section.forms, key=lambda f: f.order)

    def get_ordered_visible_questions_for_form(self, form: Form) -> list[Question]:
        """Returns the visible, ordered questions for a given form based upon the current state of this collection."""
        return sorted(form.questions, key=lambda q: q.order)
