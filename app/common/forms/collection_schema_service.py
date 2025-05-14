from app.common.data.models import CollectionSchema, Question


class CollectionSchemaService:
    def __init__(self, collection_schema: CollectionSchema) -> None:
        self.collection_schema = collection_schema

    def get_all_questions(self) -> list[Question]:
        """
        Gets all questions for a collection schema. This can be used by e.g., internal users when they have finished
        work on an application tasklist.
        """
        all_questions = []
        for section in self.collection_schema.sections:
            for form in section.forms:
                for question in form.questions:
                    all_questions.append(question)
        return all_questions
