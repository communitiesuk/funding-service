import os
import uuid
from typing import Generator
from unittest.mock import patch

import pytest
from flask import Flask
from govuk_frontend_wtf.wtforms_widgets import GovRadioInput, GovTextArea, GovTextInput
from werkzeug.datastructures import MultiDict
from wtforms.fields.choices import RadioField
from wtforms.fields.numeric import IntegerField
from wtforms.fields.simple import EmailField, StringField
from wtforms.validators import URL, DataRequired, Email, InputRequired

from app import create_app
from app.common.collections.forms import build_question_form
from app.common.data.models import Question
from app.common.data.types import QuestionDataType
from app.common.expressions import ExpressionContext
from tests.conftest import FundingServiceTestClient
from tests.utils import build_db_config

EC = ExpressionContext


class TestBuildQuestionForm:
    def test_question_attached_by_id(self, factories):
        question = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
        )

        _FormClass = build_question_form([ question ], expression_context=ExpressionContext())
        form = _FormClass()

        assert not hasattr(form, "csrf_token")
        assert hasattr(form, "submit")
        assert hasattr(form, "q_e4bd98ab41ef4d23b1e59c0404891e7a")

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
            question = factories.question.build(
                id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
            )

            _FormClass = build_question_form([ question ], expression_context=ExpressionContext())
            form = _FormClass(formdata=MultiDict({"q_e4bd98ab41ef4d23b1e59c0404891e7a": "500"}))
            assert hasattr(form, "csrf_token")
            assert hasattr(form, "submit")
            assert form._build_form_context() == {"q_e4bd98ab41ef4d23b1e59c0404891e7a": 500}

    def test_expected_fields_exist(self, app):
        q = Question(
            id=uuid.UUID("31673d51-95b0-4589-b254-33b866dfd94f"),
            text="Question text",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        form = build_question_form([ q ], expression_context=EC())
        assert hasattr(form, "q_31673d5195b04589b25433b866dfd94f")
        assert hasattr(form, "submit")

    def test_the_next_test_exhausts_QuestionDataType(self):
        assert len(QuestionDataType) == 7, (
            "If this test breaks, tweak the number and update `test_expected_field_types` accordingly."
        )

    @pytest.mark.parametrize(
        "data_type, expected_field_type, expected_widget, expected_validators",
        (
            (QuestionDataType.TEXT_SINGLE_LINE, StringField, GovTextInput, [DataRequired]),
            (QuestionDataType.TEXT_MULTI_LINE, StringField, GovTextArea, [DataRequired]),
            (QuestionDataType.INTEGER, IntegerField, GovTextInput, [InputRequired]),
            (QuestionDataType.YES_NO, RadioField, GovRadioInput, [InputRequired]),
            (QuestionDataType.RADIOS, RadioField, GovRadioInput, []),
            (QuestionDataType.EMAIL, EmailField, GovTextInput, [DataRequired, Email]),
            (QuestionDataType.URL, StringField, GovTextInput, [DataRequired, URL]),
        ),
    )
    def test_expected_field_types(
        self, factories, app, data_type, expected_field_type, expected_widget, expected_validators
    ):
        """Feels like a bit of a redundant test that's just reimplementing the function, but ... :shrug:"""
        q = factories.question.build(text="Question text", hint="Question hint", data_type=data_type)
        form = build_question_form([ q ], expression_context=EC())()

        question_field = form.get_question_field(q)
        assert isinstance(question_field, expected_field_type)
        assert isinstance(question_field.widget, expected_widget)
        assert question_field.label.text == "Question text"
        assert question_field.description == "Question hint"
        for i, validator in enumerate(expected_validators):
            assert isinstance(question_field.validators[i], validator)
