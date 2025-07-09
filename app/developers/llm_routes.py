import json
import textwrap

import boto3
from flask import abort, current_app, jsonify
from flask.typing import ResponseReturnValue
from pydantic import BaseModel

from app import auto_commit_after_request
from app.common.auth.decorators import is_platform_admin
from app.config import Environment
from app.developers.deliver_routes import developers_deliver_blueprint
from app.developers.forms import GenerateQuestionNameForm


class GenerateQuestionNameResponse(BaseModel):
    name: str


@developers_deliver_blueprint.route(
    "/api/generate-question-name",
    methods=["POST"],
)
@is_platform_admin
@auto_commit_after_request
def generate_question_name() -> ResponseReturnValue:
    form = GenerateQuestionNameForm()
    if not form.validate_on_submit():
        abort(400)

    if current_app.config["FLASK_ENV"] not in {Environment.DEV, Environment.TEST, Environment.PROD}:
        return jsonify(GenerateQuestionNameResponse(name="[LLM unavailable]").model_dump())

    client = boto3.client("bedrock-runtime")
    system_prompt = textwrap.dedent(
        """
    You are an experienced content designer working for the UK Government. Your priorities when writing content are to use plain English, be concise, accurate, and easy to understand. You are working on a service that allows users to build forms that consist of questions. The questions can be long, complex, and dense. The service needs to have an alternative representation of the question, which we're calling the "question name", that simply and succinctly conveys the core meaning of the question. Question should ideally be 3 to 5 words long, and never more than 10 words when representing the most complex questions with nuance. This alternative representation should be a sentence fragment that can be used in the following ways:

    - As part of a sentence, for example: "Enter [question name]".
    - As the header of a CSV when answers for that question are exported for analysis

    Some examples of questions, and good question names:

    Question: "What is the name of your organisation?"
    Name: "organisation name"

    Question: "What is your email address?"
    Name: "email address"

    Question: "How many risks to delivery do you have, excluding fraud risks?"
    Name: "number of non-fraud risks"

    Question: "What is the plan to engage more users in the service offer?
    Name: "service engagement plan"

    Question: "Why is there a difference between the actual spend and the estimated spend?"
    Name: "explanation for difference between actual and estimated spend"

    Respond with ONLY the question name. Do not include any other conversational filler or explanation. Do not wrap your response in quotes or other formatting. It should not be in title case, ie don't start with a capitalised letter unless it's a proper noun.
    """.strip()  # noqa: E501
    )

    prompt = textwrap.dedent(
        """
    Context for the question:
    - It is part of a data collection called "{collection}"
    - Within the data collection, it's in a section called "{section}"
    - Within the section, it's in a form called "{form}"

    The question is: "{question}"

    What is the best name for this question?
    """  # noqa: E501
    ).format(
        collection=form.collection.data,
        section=form.section.data,
        form=form.form.data,
        question=form.question.data,
    )

    nova_llm_prompt = {
        "messages": [{"role": "user", "content": [{"text": prompt}]}],
        "system": [{"text": system_prompt}],
        "inferenceConfig": {"maxTokens": 15, "temperature": 0.7, "topP": 0.9},
    }

    api_response = client.invoke_model(modelId="amazon.nova-pro-v1:0", body=json.dumps(nova_llm_prompt))
    model_response = json.loads(api_response["body"].read())
    reply = model_response["output"]["message"]["content"][0]["text"]

    return jsonify(GenerateQuestionNameResponse(name=reply).model_dump())
