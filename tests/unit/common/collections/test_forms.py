import os
import uuid
from typing import Generator
from unittest.mock import patch

import pytest
from flask import Flask
from werkzeug.datastructures import MultiDict

from app import create_app
from app.common.collections.forms import build_question_form
from app.common.data.types import QuestionDataType
from app.common.expressions import ExpressionContext
from tests.conftest import FundingServiceTestClient
from tests.utils import AnySupersetOf, build_db_config


class TestBuildQuestionForm:
    def test_single_question(self, factories):
        question = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
        )

        _FormClass = build_question_form([question], expression_context=ExpressionContext())
        form = _FormClass()

        assert not hasattr(form, "csrf_token")
        assert hasattr(form, "submit")
        assert hasattr(form, "q_e4bd98ab41ef4d23b1e59c0404891e7a")

    def test_basic_validation_with_single_questions(self, factories):
        question_one = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
        )

        _FormClass = build_question_form([question_one], expression_context=ExpressionContext())
        form = _FormClass(formdata=MultiDict({"q_e4bd98ab41ef4d23b1e59c0404891e7a": "500"}))

        form.validate()

        assert form.data == AnySupersetOf(
            {
                "q_e4bd98ab41ef4d23b1e59c0404891e7a": 500,
            }
        )

    def test_multiple_questions(self, factories):
        question_one = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
        )
        question_two = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7b"), data_type=QuestionDataType.TEXT_SINGLE_LINE
        )

        _FormClass = build_question_form([question_one, question_two], expression_context=ExpressionContext())
        form = _FormClass(
            formdata=MultiDict(
                {
                    "q_e4bd98ab41ef4d23b1e59c0404891e7a": "500",
                    "q_e4bd98ab41ef4d23b1e59c0404891e7b": "a line of text",
                }
            )
        )

        assert not hasattr(form, "csrf_token")
        assert hasattr(form, "submit")
        assert hasattr(form, "q_e4bd98ab41ef4d23b1e59c0404891e7a")
        assert hasattr(form, "q_e4bd98ab41ef4d23b1e59c0404891e7a")

    def test_basic_validation_with_multiple_questions(self, factories):
        question_one = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
        )
        question_two = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7b"), data_type=QuestionDataType.TEXT_SINGLE_LINE
        )

        _FormClass = build_question_form([question_one, question_two], expression_context=ExpressionContext())
        form = _FormClass(
            formdata=MultiDict(
                {
                    "q_e4bd98ab41ef4d23b1e59c0404891e7a": "500",
                    "q_e4bd98ab41ef4d23b1e59c0404891e7b": "a line of text",
                }
            )
        )

        form.validate()

        assert form.data == AnySupersetOf(
            {
                "q_e4bd98ab41ef4d23b1e59c0404891e7a": 500,
                "q_e4bd98ab41ef4d23b1e59c0404891e7b": "a line of text",
            }
        )

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

            _FormClass = build_question_form([question], expression_context=ExpressionContext())
            form = _FormClass(formdata=MultiDict({"q_e4bd98ab41ef4d23b1e59c0404891e7a": "500"}))
            assert hasattr(form, "csrf_token")
            assert hasattr(form, "submit")
            assert form._build_form_context() == {"q_e4bd98ab41ef4d23b1e59c0404891e7a": 500}
