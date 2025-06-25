import uuid

import pytest
from govuk_frontend_wtf.wtforms_widgets import GovTextArea, GovTextInput
from wtforms.fields.numeric import IntegerField
from wtforms.fields.simple import StringField

from app.common.collections.forms import build_question_form
from app.common.data.models import Question
from app.common.data.types import QuestionDataType


class TestBuildQuestionForm:
    def test_expected_fields_exist(self, app):
        q = Question(
            id=uuid.UUID("31673d51-95b0-4589-b254-33b866dfd94f"),
            text="Question text",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        form = build_question_form(q)
        assert hasattr(form, "q_31673d5195b04589b25433b866dfd94f")
        assert hasattr(form, "submit")

    def test_the_next_test_exhausts_QuestionDataType(self):
        assert len(QuestionDataType) == 3, (
            "If this test breaks, tweak the number and update `test_expected_field_types` accordingly."
        )

    @pytest.mark.parametrize(
        "data_type, expected_field_type, expected_widget",
        (
            (QuestionDataType.TEXT_SINGLE_LINE, StringField, GovTextInput),
            (QuestionDataType.TEXT_MULTI_LINE, StringField, GovTextArea),
            (QuestionDataType.INTEGER, IntegerField, GovTextInput),
        ),
    )
    def test_expected_field_types(self, app, data_type, expected_field_type, expected_widget):
        """Feels like a bit of a redundant test that's just reimplementing the function, but ... :shrug:"""
        q = Question(id=uuid.uuid4(), text="Question text", hint="Question hint", data_type=data_type)
        form = build_question_form(q)()

        question_field = form.get_question_field(q)
        assert isinstance(question_field, expected_field_type)
        assert isinstance(question_field.widget, expected_widget)
        assert question_field.label.text == "Question text"
        assert question_field.description == "Question hint"
