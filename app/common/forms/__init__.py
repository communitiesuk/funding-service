from uuid import UUID

from flask import Blueprint

from app.common.data.interfaces.collections import add_test_grant_schema
from app.common.data.models import Question
from app.common.forms.question_service import QuestionService
from app.extensions import auto_commit_after_request

test_blueprint = Blueprint(
    "test",
    __name__,
    url_prefix="/",
)


@test_blueprint.route("/form/add-schema", methods=["GET"])
@auto_commit_after_request
def adding():
    uestion_service: QuestionService = QuestionService()
    uestion_service.create_test_data()
    return "Data added successfully"


@test_blueprint.route("/form/next/<uuid:form_id>", methods=["GET"])
@test_blueprint.route("/form/next/<uuid:form_id>/<uuid:question_id>", methods=["GET"])
@auto_commit_after_request
def next_question_test(form_id: UUID, question_id: UUID | None = None):
    # First time going inside the form
    question_service: QuestionService = QuestionService()
    question: Question = question_service.get_next_unanswered_questions(
        form_id=form_id, question_id=question_id, answers=None
    )
    return question_service.questions_to_dict([question])

    # If user is in specific question https://funding.communities.gov.localhost:8080/form/next/0b1521bc-360d-42d2-9cc1-aed3549b62eb/01b7803e-fb4c-4034-b12a-6df2001665da
    # If user is in form https://funding.communities.gov.localhost:8080/form/next/0b1521bc-360d-42d2-9cc1-aed3549b62eb
