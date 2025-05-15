from app.common.data.models import Form, Question, Condition, Submission


class FormService:
    form: Form

    def __init__(self, form: Form) -> None:
        self.form = form

    def _higher_order_relevant_questions(self, current_question: Question) -> list[Question]:
        return [
            question
            for question in self.form.questions
            if question.order > current_question.order
               and all(self._evaluate_condition(condition, None) for condition in question.conditions)
        ]

    def get_questions(self, page_slug: str) -> list[Question]:
        for question in self.form.questions:
            if question.slug == page_slug:
                if question.group and question.group.show_all_on_same_page:
                    continue
                return [question]

        for group in self.form.question_groups:
            if group.slug == page_slug and group.show_all_on_same_page:
                return group.questions
        raise Exception("Page slug not found")

    def get_next_slug(self, page_slug: str) -> str | None:
        questions = self.get_questions(page_slug)
        current_question = questions[-1]
        selected_questions = self._higher_order_relevant_questions(current_question)
        if not selected_questions:
            return None
        first_question = selected_questions[0]
        if first_question.group and first_question.group.show_all_on_same_page:
            return first_question.group.slug
        return first_question.slug

    def get_previous_slug(self, page_slug: str) -> str | None:
        pass

    def move_up_page(self, page_slug: str) -> list[Question]|None:
        pass

    def move_down_page(self, question_slug: str) -> list[Question]:
        pass

    def _evaluate_condition(self, condition: Condition, answers: Submission | None):
        # TODO implementing condition eval & get answer by the submission to eval
        return True
