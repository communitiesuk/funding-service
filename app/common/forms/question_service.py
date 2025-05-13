from typing import List

from app.common.data.models import CollectionSchema, Question, Submission


class QuestionService:
    def __init__(self, collection_schema: CollectionSchema, submission: Submission):
        self.collection_schema = collection_schema
        self.submission = submission

    def get_answer_by_question_id(self, question_id) -> dict:
        pass

    def get_all_user_answers(self) -> dict:
        pass

    def get_next_unanswered_question(self) -> Question:
        pass

    def get_previous_question(self) -> Question:
        pass

    def validate_answer(self, question_id: str, answer: str) -> dict:
        pass

    def get_visible_questions(self) -> List[Question]:
        pass
