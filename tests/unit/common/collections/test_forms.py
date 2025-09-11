import os
import uuid
from typing import Generator
from unittest.mock import patch

import pytest
from flask import Flask
from govuk_frontend_wtf.wtforms_widgets import GovCharacterCount, GovDateInput, GovRadioInput, GovTextArea, GovTextInput
from werkzeug.datastructures import MultiDict
from wtforms import DateField
from wtforms.fields.choices import RadioField, SelectMultipleField
from wtforms.fields.numeric import IntegerField
from wtforms.fields.simple import EmailField, StringField
from wtforms.validators import DataRequired, Email, InputRequired

from app import create_app
from app.common.collections.forms import build_question_form
from app.common.data.models import Question
from app.common.data.types import QuestionDataType, QuestionPresentationOptions
from app.common.expressions import ExpressionContext
from app.common.forms.fields import MHCLGCheckboxesInput, MHCLGRadioInput
from app.common.forms.validators import URLWithoutProtocol
from tests.conftest import FundingServiceTestClient
from tests.utils import build_db_config

EC = ExpressionContext


class TestBuildQuestionForm:
    def test_question_attached_by_id(self, factories):
        question = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
        )

        _FormClass = build_question_form([question], expression_context=ExpressionContext())
        form = _FormClass()

        assert not hasattr(form, "csrf_token")
        assert hasattr(form, "submit")
        assert hasattr(form, "q_e4bd98ab41ef4d23b1e59c0404891e7a")

    def test_multiple_questions_attached_by_id(self, factories):
        questions = factories.question.build_batch(5, data_type=QuestionDataType.INTEGER)

        _FormClass = build_question_form(questions, expression_context=ExpressionContext())
        form = _FormClass()

        for question in questions:
            assert hasattr(form, question.safe_qid)

    class TestBuildFormContext:
        @pytest.fixture(scope="function")
        def app(self) -> Generator[Flask, None, None]:
            overrides = build_db_config(None)
            overrides["WTF_CSRF_ENABLED"] = "true"

            with patch.dict(os.environ, overrides):
                app = create_app()

            app.test_client_class = FundingServiceTestClient
            app.config.update({"TESTING": True})

            yield app

        def test_build_form_context(self, factories):
            q1 = factories.question.build(
                id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
            )
            q2 = factories.question.build(
                id=uuid.UUID("4d188cd7-2603-4fd8-955d-40e3f65f9312"), data_type=QuestionDataType.TEXT_SINGLE_LINE
            )

            _FormClass = build_question_form([q1, q2], expression_context=ExpressionContext())
            form = _FormClass(
                formdata=MultiDict(
                    {"q_e4bd98ab41ef4d23b1e59c0404891e7a": "500", "q_4d188cd726034fd8955d40e3f65f9312": "Test value"}
                )
            )
            assert hasattr(form, "csrf_token")
            assert hasattr(form, "submit")
            assert form._build_form_context() == {
                "q_e4bd98ab41ef4d23b1e59c0404891e7a": 500,
                "q_4d188cd726034fd8955d40e3f65f9312": "Test value",
            }

    def test_expected_fields_exist(self, app):
        q = Question(
            id=uuid.UUID("31673d51-95b0-4589-b254-33b866dfd94f"),
            text="Question text",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        form = build_question_form([q], expression_context=EC())
        assert hasattr(form, "q_31673d5195b04589b25433b866dfd94f")
        assert hasattr(form, "submit")

    def test_the_next_test_exhausts_QuestionDataType(self):
        assert len(QuestionDataType) == 9, (
            "If this test breaks, tweak the number and update `test_expected_field_types` accordingly."
        )

    QPO = QuestionPresentationOptions

    @pytest.mark.parametrize(
        "data_type, presentation_options, expected_field_type, expected_widget, expected_validators",
        (
            (QuestionDataType.TEXT_SINGLE_LINE, QPO(), StringField, GovTextInput, [DataRequired]),
            (QuestionDataType.TEXT_MULTI_LINE, QPO(), StringField, GovTextArea, [DataRequired]),
            (QuestionDataType.TEXT_MULTI_LINE, QPO(word_limit=500), StringField, GovCharacterCount, [DataRequired]),
            (QuestionDataType.INTEGER, QPO(), IntegerField, GovTextInput, [InputRequired]),
            (QuestionDataType.YES_NO, QPO(), RadioField, GovRadioInput, [InputRequired]),
            (QuestionDataType.RADIOS, QPO(), RadioField, MHCLGRadioInput, []),
            (QuestionDataType.EMAIL, QPO(), EmailField, GovTextInput, [DataRequired, Email]),
            (QuestionDataType.URL, QPO(), StringField, GovTextInput, [DataRequired, URLWithoutProtocol]),
            (QuestionDataType.CHECKBOXES, QPO(), SelectMultipleField, MHCLGCheckboxesInput, [DataRequired]),
            (QuestionDataType.DATE, QPO(), DateField, GovDateInput, [DataRequired]),
        ),
    )
    def test_expected_field_types(
        self, factories, app, data_type, presentation_options, expected_field_type, expected_widget, expected_validators
    ):
        """Feels like a bit of a redundant test that's just reimplementing the function, but ... :shrug:"""
        q = factories.question.build(
            text="Question text", hint="Question hint", data_type=data_type, presentation_options=presentation_options
        )
        form = build_question_form([q], expression_context=EC())()

        question_field = form.get_question_field(q)
        assert isinstance(question_field, expected_field_type)
        assert isinstance(question_field.widget, expected_widget)
        assert question_field.label.text == "Question text"
        assert question_field.description == "Question hint"
        for i, validator in enumerate(expected_validators):
            assert isinstance(question_field.validators[i], validator)

    def test_break_if_new_question_types_added(self):
        assert len(QuestionDataType) == 9, "Add a new parameter option above if adding a new question type"
