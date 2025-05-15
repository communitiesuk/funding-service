from flask import Blueprint, redirect, render_template, request

from app.common.data.interfaces.collections import (
    add_test_grant_schema,
    add_test_grant_submission,
    get_collection_schema,
    get_form_by_slug,
)
from app.common.forms.form_service import FormService
from app.extensions import auto_commit_after_request

test_blueprint = Blueprint(
    "test",
    __name__,
    url_prefix="/",
)


@test_blueprint.route("/add-data", methods=["GET"])
@auto_commit_after_request
def add_data():
    add_test_grant_schema()
    add_test_grant_submission()
    return "Data added successfully"


@test_blueprint.route("/<string:form_slug>/<string:page_slug>", methods=["GET", "POST"])
def question_page(form_slug: str, page_slug: str):
    # Get the form by slug
    form = get_form_by_slug(form_slug)
    if not form:
        return "Form not found", 404

    form_srv = FormService(form)

    if request.method == "POST":
        try:
            page_slug = form_srv.get_next_slug(page_slug)
            if not page_slug:
                return "Page slug not found", 404
        except Exception:
            return "Page slug not found", 404
        return redirect(f"/{form_slug}/{page_slug}")

    # Get the page by slug
    questions = form_srv.get_questions(page_slug)
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
