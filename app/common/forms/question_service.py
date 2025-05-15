import uuid
from typing import List

from app import User
from app.common.data.interfaces.collections import (
    get_all_questions_with_higher_order_from_current,
    get_form_by_slug,
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
        form_slug: str | None = None,
        question_slug: str | None = None,
    ) -> List[Question] | None:
        # If a current question is provided, we're mid-way through the form
        if question_slug:
            # Get the current question based on form and question ID
            current_question: Question = get_question_by_id_for_form_and_question(form_slug, question_slug)
            # check is the question is available
            if current_question:
                # Get all questions that come after the current one
                subsequent_questions: List[Question] = get_all_questions_with_higher_order_from_current(
                    current_question
                )
                if not subsequent_questions:
                    return None  # No more questions to display
                # Filter the later questions to only those that meet their conditional logic
                selected_questions = [
                    question
                    for question in subsequent_questions
                    if all(self._evaluate_condition(cond, answers) for cond in question.conditions)
                ]
                if not selected_questions:
                    return None
                # If the next question belongs to a new group and the group should be shown as a block (on same page),
                # return all questions in that group
                first_question = selected_questions[0]
                if (
                    first_question.group
                    and first_question.group.show_all_on_same_page
                    and first_question.group_id != current_question.group_id
                ):
                    return first_question.group.questions
                # check is selected first question and the current question is in the same group, and it says to have
                # same page then get next question which is out of the group, according to the order,
                # if there are not any return None
                elif (
                    first_question.group
                    and first_question.group.show_all_on_same_page
                    and first_question.group_id == current_question.group_id
                ):
                    filtered_questions = [
                        q for q in selected_questions if not q.group or q.group.id != current_question.group_id
                    ]
                    if filtered_questions:
                        return [filtered_questions[0]]
                    return None
                # Otherwise, return only the questions that passed the conditions
                return [first_question]
            return None
        else:
            # If no current question is provided, we are at the start of the form
            form = get_form_by_slug(form_slug)
            # Check is the form exists
            if form:
                # Find the question with the lowest order (i.e., the first question)
                selected_question = min(form.questions, key=lambda q: q.order, default=None)
                if not selected_question:
                    return None
                # If the first question is not part of a group, return it directly
                if selected_question.group is None:
                    return [selected_question]
                # If it is part of a group that should be shown all at once, return the whole group
                if selected_question.group.show_all_on_same_page:
                    return selected_question.group.questions
                # Otherwise, return just the first question
                return [selected_question]
            return None

    def get_previous_question(self, form_id: uuid.UUID) -> Question:
        pass

    def get_visible_questions(self) -> List[Question]:
        pass

    def _evaluate_condition(self, condition: Condition, answers: Submission | None):
        # TODO implementing condition eval & get answer by the submission to eval
        return True

    def questions_to_dict(self, questions: List[Question]) -> dict[str, dict]:
        question_dict = []

        for question in questions:
            question_dict.append(
                {
                    "title": question.title,
                    "name": question.name,
                    "next_page": f"/form/next/{question.form.slug}/{question.slug}",
                    "hint": question.hint,
                    "data_source": question.data_source,
                    "data_type": question.data_type.name
                    if hasattr(question.data_type, "name")
                    else str(question.data_type),
                    "order": question.order,
                    "form_id": str(question.form_id),
                    "group_id": str(question.group_id) if question.group_id else None,
                }
            )

        return question_dict
