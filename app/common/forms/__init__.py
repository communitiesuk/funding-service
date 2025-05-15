from typing import List

from flask import Blueprint, render_template

from app.common.data.interfaces.collections import add_test_grant_schema, get_collection_schema
from app.common.data.models import Question

# from app.common.forms.collection_schema_service import CollectionSchemaService
from app.common.forms.question_service import QuestionService
from app.extensions import auto_commit_after_request

test_blueprint = Blueprint(
    "test",
    __name__,
    url_prefix="/",
)


@test_blueprint.route("/add-schema", methods=["GET"])
@auto_commit_after_request
def add_collection_schema():
    add_test_grant_schema()
    return "Data added successfully"


@test_blueprint.route("/form/next/<string:form_slug>", methods=["GET"])
@test_blueprint.route("/form/next/<string:form_slug>/<string:question_slug>", methods=["GET"])
@auto_commit_after_request
def next_question(form_slug: str, question_slug: str | None = None):
    # First time going inside the form
    question_service: QuestionService = QuestionService()
    questions: List[Question] = question_service.get_next_unanswered_questions(
        form_slug=form_slug, question_slug=question_slug, answers=None
    )
    if questions:
        return render_template("test/next_question.html", question_dict=question_service.questions_to_dict(questions))
    return render_template("test/next_question.html", question_dict=None)


@test_blueprint.route("/all-questions/<collection_schema_id>", methods=["GET"])
def all_questions(collection_schema_id):
    collection_schema = get_collection_schema(collection_id=collection_schema_id)
    if not collection_schema:
        return "Collection schema not found", 404
    # service = CollectionSchemaService(collection_schema=collection_schema)
    # questions = service.get_all_questions()
    return render_template("test/all_questions.html", collection_schema=collection_schema)
