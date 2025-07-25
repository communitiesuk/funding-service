import uuid

import pytest
from werkzeug.datastructures import MultiDict
from wtforms.fields.choices import SelectField
from wtforms.validators import DataRequired

from app.common.collections.forms import build_question_form
from app.common.data import interfaces
from app.common.data.interfaces.collections import create_question
from app.common.data.types import QuestionDataType
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import GreaterThan, LessThan
from app.common.forms.fields import MHCLGAccessibleAutocomplete

EC = ExpressionContext


@pytest.mark.parametrize(
    "value, error_message, field_type",
    (
        ("This is an answer\non multiple lines", None, QuestionDataType.TEXT_MULTI_LINE),
        ("Test string", None, QuestionDataType.TEXT_MULTI_LINE),
        ("", "Enter the test_text", QuestionDataType.TEXT_MULTI_LINE),
        ("Test string", None, QuestionDataType.TEXT_SINGLE_LINE),
        ("", "Enter the test_text", QuestionDataType.TEXT_SINGLE_LINE),
    ),
)
def test_validation_attached_to_field_and_runs__text(factories, value, error_message, field_type):
    question = factories.question.build(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7b"),
        data_type=field_type,
        name="test_text",
    )

    _FormClass = build_question_form(question, expression_context=ExpressionContext())
    form = _FormClass(formdata=MultiDict({"q_e4bd98ab41ef4d23b1e59c0404891e7b": str(value)}))

    valid = form.validate()
    if error_message:
        assert valid is False
        assert error_message in form.errors["q_e4bd98ab41ef4d23b1e59c0404891e7b"]
    else:
        assert valid is True


@pytest.mark.parametrize(
    "value, error_message",
    (
        (-50, "The answer must be greater than or equal to 0"),
        (1_000, "The answer must be less than 100"),
        (50, None),
        (0, None),
        (None, "Not a valid integer value."),
        ("abcd", "Not a valid integer value."),
        ("", "Enter the test_integer"),
    ),
)
def test_validation_attached_to_field_and_runs__integer(factories, value, error_message):
    question = factories.question.build(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"),
        data_type=QuestionDataType.INTEGER,
        name="test_integer",
    )
    user = factories.user.build()
    interfaces.collections.add_question_validation(
        question, user, GreaterThan(question_id=question.id, minimum_value=0, inclusive=True)
    )
    interfaces.collections.add_question_validation(
        question, user, LessThan(question_id=question.id, maximum_value=100, inclusive=False)
    )

    _FormClass = build_question_form(question, expression_context=ExpressionContext())
    form = _FormClass(formdata=MultiDict({"q_e4bd98ab41ef4d23b1e59c0404891e7a": str(value)}))

    valid = form.validate()
    if error_message:
        assert valid is False
        assert error_message in form.errors["q_e4bd98ab41ef4d23b1e59c0404891e7a"]
    else:
        assert valid is True


def test_special_radio_field_enhancement_to_autocomplete(factories, app, db_session):
    form = factories.form.create()
    q = create_question(
        form=form,
        text="Question text",
        hint="Question hint",
        name="question",
        data_type=QuestionDataType.RADIOS,
        items=[str(i) for i in range(25)],
    )
    form = build_question_form(q, expression_context=EC())()

    question_field = form.get_question_field(q)
    assert isinstance(question_field, SelectField)
    assert isinstance(question_field.widget, MHCLGAccessibleAutocomplete)
    assert question_field.label.text == "Question text"
    assert question_field.description == "Question hint"
    assert len(question_field.validators) == 1
    assert isinstance(question_field.validators[0], DataRequired)
