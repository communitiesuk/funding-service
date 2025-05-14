import uuid
from typing import List

from app import User
from app.common.data.interfaces.collections import (
    get_all_questions_with_higher_order_from_current,
    get_form_by_id,
    get_question_by_id_for_form_and_question,
)
from app.common.data.models import Condition, Question, Submission


class QuestionService:
    # TODO possible submission service
    def get_answer_by_question_id(self, question_id) -> dict:
        pass

    # TODO possible submission service
    def get_all_user_answers(self, user: User) -> dict:
        pass

    # TODO possible submission service
    def get_all_users_answers(self) -> dict:
        pass

    def validate_answer(self, question_id: str, answer: str) -> dict:
        pass

    def get_next_unanswered_questions(
        self,
        *,
        answers: Submission | None,
        form_id: uuid.UUID | None = None,
        question_id: uuid.UUID | None = None,
    ) -> Question:
        if question_id:
            current_question: Question = get_question_by_id_for_form_and_question(form_id, question_id)
            # ------------------------------ Logic -------------------------------------------------------
            # Start with the current question.
            # Filter questions that belong to the same form and have a greater order.
            # Evaluate each question's conditions (which might depend on previous answers or other logic)
            # and Do Check is questions are answered or not.
            # Return the first question (by order).
            # --------------------------------------------------------------------------------------------
            # Step 1: Get all questions from the same form with higher order
            subsequent_questions: List[Question] = get_all_questions_with_higher_order_from_current(current_question)
            selected_questions: List[Question] = []
            # Step 2: Evaluate conditions & check answer is given init
            for question in subsequent_questions:
                all_conditions_met = True
                for condition in question.conditions:
                    if not self._evaluate_condition(condition, answers):
                        all_conditions_met = False
                        break
                if all_conditions_met:
                    selected_questions.append(question)
            # Step 3: Order the selected questions based on the order
            selected_questions.sort(key=lambda q: q.order)
            return selected_questions[0] if selected_questions else None
        else:
            # ------------------------------ Logic -------------------------------------------------------
            # If dont have the question but have the form id
            # Get the first question from the list to show
            return min(get_form_by_id(form_id).questions, key=lambda q: q.order, default=None)

    def get_previous_question(self, form_id: uuid.UUID) -> Question:
        pass

    def get_visible_questions(self) -> List[Question]:
        pass

    def _evaluate_condition(self, condition: Condition, answers: Submission | None):
        # TODO implementing condition eval & get answer by the submission to eval
        return True

    def questions_to_dict(self, questions: list[Question]) -> dict[str, dict]:
        question_dict = {}

        for question in questions:
            question_dict[str(question.id)] = {
                "title": question.title,
                "name": question.name,
                "slug": question.slug,
                "hint": question.hint,
                "data_source": question.data_source,
                "data_type": question.data_type.name
                if hasattr(question.data_type, "name")
                else str(question.data_type),
                "order": question.order,
                "form_id": str(question.form_id),
                "group_id": str(question.group_id) if question.group_id else None,
                "conditions": [
                    {
                        "expression": cond.expression,
                        "type": cond.type.name if hasattr(cond.type, "name") else str(cond.type),
                        "description": cond.description,
                        "context": cond.context,
                        "depends_on_question_id": str(cond.depends_on_question_id),
                    }
                    for cond in question.conditions
                ],
                "validations": [
                    {
                        "expression": val.expression,
                        "type": val.type.name if hasattr(val.type, "name") else str(val.type),
                        "description": val.description,
                        "message": val.message,
                        "context": val.context,
                    }
                    for val in question.validations
                ],
            }

        return question_dict
