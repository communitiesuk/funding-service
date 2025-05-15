import copy
import re

from app.common.data.interfaces.collections import get_submission, save_submission
from app.common.data.models import Condition, Form, Question, Submission, Validation
from app.common.data.types import SubmissionType


class FormService:
    form: Form

    def __init__(self, form: Form, submission: Submission) -> None:
        self.form = form
        self.submission = submission
        self.question_regex = re.compile(r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b")
        self.form_question_regex = re.compile(r"([0-9a-f-]+)\.([0-9a-f-]+)")
        self.section_form_question_regex = re.compile(r"([0-9a-f-]+)\.([0-9a-f-]+)\.([0-9a-f-]+)")

    def _higher_order_relevant_questions(self, current_question: Question) -> list[Question]:
        return [
            question
            for question in self.form.questions
            if question.order > current_question.order
            and all(self._evaluate_condition(condition) for condition in question.conditions)
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

    def question_submission(self, form_data: dict, page_slug: str, submission_id: str | None) -> Submission | None:
        mini_submission, questions = self._submission_converter(form_data, page_slug)
        if not submission_id:
            submission: Submission = Submission(
                data=mini_submission,
                status=SubmissionType.CREATED,
                collection_schema=self.form.section.collection_schema,
            )
            return save_submission(submission)
        else:
            submission: Submission = get_submission(submission_id)
            submission.data = self._deep_merge(mini_submission, submission.data)
            return save_submission(submission)

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

    def move_up_page(self, page_slug: str) -> list[Question] | None:
        pass

    def move_down_page(self, question_slug: str) -> list[Question]:
        pass

    def validate(self, form_data: dict, page_slug: str) -> dict:
        mini_submission, questions = self._submission_converter(form_data, page_slug)
        errors = {}
        for question in questions:
            error_list = self._evaluate_validation(question.validations, mini_submission)
            if error_list:
                errors.update({question.slug: error_list})
        return errors

    def _deep_merge(self, dict1, dict2):
        result = copy.deepcopy(dict1)  # don't modify the original dict
        for key1 in dict2:
            if key1 not in result:
                result[key1] = dict2[key1]
            else:
                for key2 in dict2[key1]:
                    if key2 not in result[key1]:
                        result[key1][key2] = dict2[key1][key2]
                    else:
                        # Merge the innermost dict
                        result[key1][key2].update(dict2[key1][key2])
        return result

    def _submission_converter(self, form_data, page_slug):
        mini_submission = {str(self.form.section.id): {str(self.form.id): {}}}
        questions = self.get_questions(page_slug)
        for question in questions:
            mini_submission[str(self.form.section.id)][str(self.form.id)].update(
                {str(question.id): form_data[question.slug]}
            )
        return mini_submission, questions

    def _evaluate_validation(self, validations: list[Validation], form_data: dict) -> []:
        errors = []
        for validation in validations:
            resolved_expr = self._replace_uuids(validation.expression, form_data)
            try:
                result = eval(resolved_expr)
                if not result:
                    errors.append(validation.message)
            except Exception as e:
                return f"Error: {e}"
        return errors

    def _evaluate_condition(self, condition: Condition):
        if condition and condition.expression and self.submission:
            resolved_expr = self._replace_uuids(condition.expression, self.submission.data)
            try:
                result = eval(resolved_expr)
                return result
            except Exception as e:
                return f"Error: {e}"
        elif condition and condition.expression and self.submission is None:
            return False
        return True

    def _flatten_question_data(self, data: dict) -> dict:
        flat_data = {}
        for section in data.values():
            for form in section.values():
                for question_id, value in form.items():
                    flat_data[question_id] = value
        return flat_data

    def _replace_uuids(self, expression: str, data: dict) -> str:
        def section_form_question_replacer(match: re.Match) -> str:
            section_id, form_id, question_id = match.groups()
            return repr(self._flatten_question_data(data).get(question_id, None))

        def form_question_replacer(match):
            form_id, question_id = match.groups()
            return repr(self._flatten_question_data(data).get(question_id, None))

        def question_replacer(match):
            question_id = match.group(0)
            return repr(self._flatten_question_data(data).get(question_id, None))

        expression = self.section_form_question_regex.sub(section_form_question_replacer, expression)
        expression = self.form_question_regex.sub(form_question_replacer, expression)
        expression = self.question_regex.sub(question_replacer, expression)

        return expression
