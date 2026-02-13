import os
import uuid
from typing import Generator
from unittest.mock import patch

import pytest
from flask import Flask
from govuk_frontend_wtf.wtforms_widgets import (
    GovCharacterCount,
    GovDateInput,
    GovFileInput,
    GovRadioInput,
    GovTextArea,
    GovTextInput,
)
from werkzeug.datastructures import MultiDict
from wtforms import DateField, DecimalField
from wtforms.fields.choices import RadioField, SelectMultipleField
from wtforms.fields.numeric import IntegerField
from wtforms.fields.simple import EmailField, FileField, StringField
from wtforms.validators import DataRequired, Email, InputRequired

from app import create_app
from app.common.collections.forms import build_question_form
from app.common.data.models import Question
from app.common.data.types import NumberTypeEnum, QuestionDataOptions, QuestionDataType, QuestionPresentationOptions
from app.common.expressions import ExpressionContext
from app.common.forms.fields import MHCLGCheckboxesInput, MHCLGRadioInput
from app.common.forms.validators import URLWithoutProtocol
from tests.conftest import FundingServiceTestClient
from tests.utils import build_db_config

EC = ExpressionContext


class TestBuildQuestionForm:
    def test_question_attached_by_id(self, factories):
        question = factories.question.build(
            id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.NUMBER
        )

        _FormClass = build_question_form(
            [question], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
        )
        form = _FormClass()

        assert not hasattr(form, "csrf_token")
        assert hasattr(form, "submit")
        assert hasattr(form, "q_e4bd98ab41ef4d23b1e59c0404891e7a")

    def test_multiple_questions_attached_by_id(self, factories):
        questions = factories.question.build_batch(5, data_type=QuestionDataType.NUMBER)

        _FormClass = build_question_form(
            questions, evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
        )
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
                id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"), data_type=QuestionDataType.NUMBER
            )
            q2 = factories.question.build(
                id=uuid.UUID("4d188cd7-2603-4fd8-955d-40e3f65f9312"), data_type=QuestionDataType.TEXT_SINGLE_LINE
            )

            _FormClass = build_question_form(
                [q1, q2], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
            )
            form = _FormClass(
                formdata=MultiDict(
                    {"q_e4bd98ab41ef4d23b1e59c0404891e7a": "500", "q_4d188cd726034fd8955d40e3f65f9312": "Test value"}
                )
            )
            assert hasattr(form, "csrf_token")
            assert hasattr(form, "submit")
            assert form._extract_submission_answers() == {
                "q_e4bd98ab41ef4d23b1e59c0404891e7a": 500,
                "q_4d188cd726034fd8955d40e3f65f9312": "Test value",
            }

    def test_expected_fields_exist(self, app):
        q = Question(
            id=uuid.UUID("31673d51-95b0-4589-b254-33b866dfd94f"),
            text="Question text",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        form = build_question_form([q], evaluation_context=EC(), interpolation_context=EC())
        assert hasattr(form, "q_31673d5195b04589b25433b866dfd94f")
        assert hasattr(form, "submit")

    def test_the_next_test_exhausts_QuestionDataType(self):
        assert len(QuestionDataType) == 10, (
            "If this test breaks, tweak the number and update `test_expected_field_types` accordingly."
        )

    QPO = QuestionPresentationOptions
    QDO = QuestionDataOptions

    @pytest.mark.parametrize(
        "data_type, presentation_options, data_options, expected_field_type, expected_widget, expected_validators",
        (
            (QuestionDataType.TEXT_SINGLE_LINE, QPO(), None, StringField, GovTextInput, [DataRequired]),
            (QuestionDataType.TEXT_MULTI_LINE, QPO(), None, StringField, GovTextArea, [DataRequired]),
            (
                QuestionDataType.TEXT_MULTI_LINE,
                QPO(word_limit=500),
                None,
                StringField,
                GovCharacterCount,
                [DataRequired],
            ),
            (
                QuestionDataType.NUMBER,
                QPO(),
                QDO(number_type=NumberTypeEnum.INTEGER),
                IntegerField,
                GovTextInput,
                [InputRequired],
            ),
            (
                QuestionDataType.NUMBER,
                QPO(),
                QDO(number_type=NumberTypeEnum.DECIMAL),
                DecimalField,
                GovTextInput,
                [InputRequired],
            ),
            (QuestionDataType.YES_NO, QPO(), None, RadioField, GovRadioInput, [InputRequired]),
            (QuestionDataType.RADIOS, QPO(), None, RadioField, MHCLGRadioInput, []),
            (QuestionDataType.EMAIL, QPO(), None, EmailField, GovTextInput, [DataRequired, Email]),
            (QuestionDataType.URL, QPO(), None, StringField, GovTextInput, [DataRequired, URLWithoutProtocol]),
            (QuestionDataType.CHECKBOXES, QPO(), None, SelectMultipleField, MHCLGCheckboxesInput, [DataRequired]),
            (QuestionDataType.DATE, QPO(), None, DateField, GovDateInput, [DataRequired]),
            (QuestionDataType.FILE_UPLOAD, QPO(), None, FileField, GovFileInput, [DataRequired]),
        ),
    )
    def test_expected_field_types(
        self,
        factories,
        app,
        data_type,
        presentation_options,
        data_options,
        expected_field_type,
        expected_widget,
        expected_validators,
    ):
        """Feels like a bit of a redundant test that's just reimplementing the function, but ... :shrug:"""
        q = factories.question.build(
            text="Question text",
            hint="Question hint",
            data_type=data_type,
            presentation_options=presentation_options,
            data_options=data_options,
        )
        form = build_question_form([q], evaluation_context=EC(), interpolation_context=EC())()

        question_field = form.get_question_field(q)
        assert isinstance(question_field, expected_field_type)
        assert isinstance(question_field.widget, expected_widget)
        assert question_field.label.text == "Question text"
        assert question_field.description == "Question hint"
        for i, validator in enumerate(expected_validators):
            assert isinstance(question_field.validators[i], validator)

    def test_break_if_new_question_types_added(self):
        assert len(QuestionDataType) == 10, "Add a new parameter option above if adding a new question type"

    def test_question_text_and_hint_interpolation(self, factories):
        question = factories.question.build(
            text="How much do you like ((thing)) out of ((max_value))?",
            hint="If it's not at least ((suggested_min)) then maybe you should think again.",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )

        context = ExpressionContext({"thing": "LOTR", "max_value": "10", "suggested_min": "7"})
        form_class = build_question_form([question], evaluation_context=context, interpolation_context=context)
        form = form_class()

        question_field = form.get_question_field(question)
        assert question_field.label.text == "How much do you like LOTR out of 10?"
        assert question_field.description == "If it's not at least 7 then maybe you should think again."
