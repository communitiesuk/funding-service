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
from tests.utils import build_db_config


class TestBuildQuestionForm:
    def test_question_attached_by_id(self, factories):
        question = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.INTEGER
        )

        _FormClass = build_question_form(question, expression_context=ExpressionContext())
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

            _FormClass = build_question_form(question, expression_context=ExpressionContext())
            form = _FormClass(formdata=MultiDict({"q_e4bd98ab41ef4d23b1e59c0404891e7a": "500"}))
            assert hasattr(form, "csrf_token")
            assert hasattr(form, "submit")
            assert form._build_form_context() == {"q_e4bd98ab41ef4d23b1e59c0404891e7a": 500}
