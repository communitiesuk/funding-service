import uuid

from flask import Blueprint, redirect, render_template, request

from app.common.data.interfaces.collections import (
    add_test_grant_schema,
    get_collection_schema,
    get_form_by_id,
    get_form_by_slug,
)
from app.common.data.models import Form, Question, QuestionGroup
from app.extensions import auto_commit_after_request

test_blueprint = Blueprint(
    "test",
    __name__,
    url_prefix="/",
)


class FormHandler:
    form: Form

    def __init__(self, form_id: uuid.UUID) -> None:
        self.form = get_form_by_id(form_id)

    @property
    def standalone_questions(self) -> list[Question]:
        res = []
        for question in self.form.questions:
            if not question.group_id:
                res.append(question)
                continue
            if not question.group.show_all_on_same_page:
                res.append(question)
        res.sort(key=lambda q: q.order)
        return res

    @property
    def standalone_question_groups(self) -> list[QuestionGroup]:
        res = []
        for question_group in self.form.question_groups:
            if question_group.show_all_on_same_page:
                res.append(question_group)
        res.sort(key=lambda q: q.order)
        return res

    @staticmethod
    def page_to_questions(page: Question | QuestionGroup) -> list[Question]:
        if isinstance(page, Question):
            return [page]
        elif isinstance(page, QuestionGroup):
            return page.questions
        else:
            raise ValueError("Invalid page type")

    def page_slug_to_questions(self) -> dict[str, list[Question]]:
        standalone_questions = self.standalone_questions
        standalone_question_groups = self.standalone_question_groups
        pages = standalone_questions + standalone_question_groups
        page_slug_to_questions = {page.slug: self.page_to_questions(page) for page in pages}
        return page_slug_to_questions

    def get_questions_from_page_slug(self, page_slug: str) -> list[Question]:
        # Assumption is that list of slugs is unique across questions and question groups, need to look into this
        page_slug_to_questions = self.page_slug_to_questions()
        return page_slug_to_questions[page_slug]

    def get_next_page_slug(self, page_slug: str) -> str | None:
        page_slug_to_questions = self.page_slug_to_questions()
        page_slugs = list(page_slug_to_questions.keys())
        if page_slug not in page_slugs:
            return None
        current_index = page_slugs.index(page_slug)
        if current_index + 1 >= len(page_slugs):
            return None
        return page_slugs[current_index + 1]


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

    form_handler = FormHandler(form.id)

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
