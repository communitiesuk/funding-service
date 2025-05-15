from flask import Blueprint, redirect, render_template, request

from app.common.data.interfaces.collections import (
    add_test_grant_schema,
    get_collection_schema,
    get_form_by_slug,
)
from app.common.data.models import Condition, Form, Question, QuestionGroup, Submission
from app.extensions import auto_commit_after_request

test_blueprint = Blueprint(
    "test",
    __name__,
    url_prefix="/",
)


class FormHandler:
    form: Form

    def __init__(self, form: Form) -> None:
        self.form = form

    def _select_question_by_condition(self, current_question: Question) -> list[Question]:
        return [
            question
            for question in self.form.questions
            if question.order > current_question.order
            and all(self._evaluate_condition(condition, None) for condition in question.conditions)
        ]

    def get_questions_from_page_slug(self, page_slug: str) -> list[Question]:
        questions = [
            question
            for question in self.form.questions
            if question.slug == page_slug and (not question.group or not question.group.show_all_on_same_page)
        ]
        if questions:
            return questions

        group = next(
            (group for group in self.form.question_groups if group.slug == page_slug and group.show_all_on_same_page),
            None,
        )
        return group.questions if group else []

    def get_next_page_slug(self, page_slug: str) -> str | None:
        questions = self.get_questions_from_page_slug(page_slug)
        current_question = (
            questions[-1]
            if questions and questions[0].group and questions[0].group.show_all_on_same_page
            else questions[0]
            if questions
            else None
        )

        selected_questions = self._select_question_by_condition(current_question)
        if not selected_questions:
            return None
        first_question = selected_questions[0]
        if (
            first_question.group
            and first_question.group.show_all_on_same_page
            and first_question.group_id != current_question.group_id
        ):
            return first_question.group.slug
        elif (
            first_question.group
            and first_question.group.show_all_on_same_page
            and first_question.group_id == current_question.group_id
        ):
            filtered_questions = [
                question
                for question in selected_questions
                if not question.group or question.group.id != current_question.group_id
            ]
            if not filtered_questions:
                return None
            return filtered_questions[0].slug
        return first_question.slug

    def _evaluate_condition(self, condition: Condition, answers: Submission | None):
        # TODO implementing condition eval & get answer by the submission to eval
        return True


@test_blueprint.route("/add-schema", methods=["GET"])
@auto_commit_after_request
def add_collection_schema():
    add_test_grant_schema()
    return "Data added successfully"


@test_blueprint.route("/<string:form_slug>/<string:page_slug>", methods=["GET", "POST"])
def question_page(form_slug: str, page_slug: str):
    # Get the form by slug
    form = get_form_by_slug(form_slug)
    if not form:
        return "Form not found", 404

    form_handler = FormHandler(form)

    if request.method == "POST":
        page_slug = form_handler.get_next_page_slug(page_slug)
        if not page_slug:
            return "Page slug not found", 404
        return redirect(f"/{form_slug}/{page_slug}")

    # Get the page by slug
    questions = form_handler.get_questions_from_page_slug(page_slug)
    if not questions:
        return "Questions not found", 404

    # Render the page template
    return render_template("test/question_page.html", questions=questions)


@test_blueprint.route("/all-questions/<collection_schema_id>", methods=["GET"])
def all_questions(collection_schema_id):
    collection_schema = get_collection_schema(collection_id=collection_schema_id)
    if not collection_schema:
        return "Collection schema not found", 404
    # service = CollectionSchemaService(collection_schema=collection_schema)
    # questions = service.get_all_questions()
    return render_template("test/all_questions.html", collection_schema=collection_schema)
