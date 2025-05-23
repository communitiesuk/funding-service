import pytest
from govuk_frontend_wtf.wtforms_widgets import GovTextArea, GovTextInput
from wtforms.fields.numeric import IntegerField
from wtforms.fields.simple import StringField

from app.common.collections.forms import build_question_form
from app.common.data.models import Question
from app.common.data.types import QuestionDataType


class TestBuildQuestionForm:
    def test_expected_fields_exist(self, app):
        q = Question(text="Question text", data_type=QuestionDataType.TEXT_SINGLE_LINE)
        form = build_question_form(q)
        assert hasattr(form, "question")
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
        q = Question(text="Question text", hint="Question hint", data_type=data_type)
        form = build_question_form(q)

        assert isinstance(form.question, expected_field_type)
        assert isinstance(form.question.widget, expected_widget)
        assert form.question.label.text == "Question text"
        assert form.question.description == "Question hint"
