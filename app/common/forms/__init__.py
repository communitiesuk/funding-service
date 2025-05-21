import uuid

from flask import Blueprint, redirect, render_template, request

from app.common.data.interfaces.collections import (
    add_test_grant_schema,
    add_test_grant_submission,
    get_collection_schema,
    get_form_by_slug,
    get_submission_by_id,
)
from app.common.data.models import Submission
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
@test_blueprint.route("/<string:form_slug>/<string:page_slug>/<uuid:submission_id>", methods=["GET", "POST"])
def question_page(form_slug: str, page_slug: str, submission_id: uuid.UUID | None = None):
    # Get the form by slug
    form = get_form_by_slug(form_slug)
    submission: Submission = get_submission_by_id(submission_id)
    if not form:
        return "Form not found", 404

    form_srv = FormService(form, submission)
    # Get the page by slug
    questions = form_srv.get_questions(page_slug)
    if not questions:
        return "Questions not found", 404

    if request.method == "POST":
        form_data = request.form.to_dict()
        errors = form_srv.validate(form_data, page_slug)
        if not errors:
            try:
                form_srv.submission = form_srv.question_submission(form_data, page_slug, submission_id)
                submission_id = form_srv.submission.id
                page_slug = form_srv.get_next_slug(page_slug)
                if not page_slug:
                    return "Page slug not found", 404
            except Exception:
                return "Page slug not found", 404
            if submission_id is None:
                return redirect(f"/{form_slug}/{page_slug}")
            return redirect(f"/{form_slug}/{page_slug}/{submission_id}")
        return render_template("test/question_page.html", questions=questions, errors=errors)

    # Render the page template
    return render_template("test/question_page.html", questions=questions, submission=submission)


@test_blueprint.route("/all-questions/<collection_schema_id>", methods=["GET"])
def all_questions(collection_schema_id):
    collection_schema = get_collection_schema(collection_id=collection_schema_id)
    if not collection_schema:
        return "Collection schema not found", 404
    # service = CollectionSchemaService(collection_schema=collection_schema)
    # questions = service.get_all_questions()
    return render_template("test/all_questions.html", collection_schema=collection_schema)
