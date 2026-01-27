import uuid
from datetime import date

import pytest
from werkzeug.datastructures import MultiDict
from wtforms.fields.choices import SelectField
from wtforms.validators import DataRequired

from app.common.collections.forms import build_question_form
from app.common.data import interfaces
from app.common.data.interfaces.collections import create_question
from app.common.data.types import QuestionDataOptions, QuestionDataType
from app.common.expressions import ExpressionContext
from app.common.expressions.managed import GreaterThan, IsAfter, LessThan
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
    question = factories.question.create(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7b"),
        data_type=field_type,
        name="test_text",
    )

    _FormClass = build_question_form(
        [question], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
    )
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
        (None, "The answer must be a whole number, like 100"),
        ("abcd", "The answer must be a whole number, like 100"),
        ("100.10", "The answer must be a whole number, like 100"),
        ("", "Enter the test_integer"),
        ("1,000", "The answer must be less than 100"),  # comma-separated, fails validation
        ("50,000", "The answer must be less than 100"),  # comma-separated, fails validation
    ),
)
def test_validation_attached_to_field_and_runs__integer(factories, value, error_message):
    question = factories.question.create(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"),
        data_type=QuestionDataType.NUMBER,
        name="test_integer",
    )
    user = factories.user.create()
    interfaces.collections.add_question_validation(
        question, user, GreaterThan(question_id=question.id, minimum_value=0, inclusive=True)
    )
    interfaces.collections.add_question_validation(
        question, user, LessThan(question_id=question.id, maximum_value=100, inclusive=False)
    )

    _FormClass = build_question_form(
        [question], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
    )
    form = _FormClass(formdata=MultiDict({"q_e4bd98ab41ef4d23b1e59c0404891e7a": str(value)}))

    valid = form.validate()
    if error_message:
        assert valid is False
        assert error_message in form.errors["q_e4bd98ab41ef4d23b1e59c0404891e7a"]
    else:
        assert valid is True


@pytest.mark.parametrize(
    "value, error_message",
    (
        (-50, "The answer must be greater than or equal to 0"),
        (-50.0, "The answer must be greater than or equal to 0"),
        (1_000, "The answer must be less than 100"),
        (50, None),
        (0, None),
        (0.2, None),
        (56.234, None),
        (99.9999999999, None),
        (None, "Not a valid decimal value."),
        ("abcd", "Not a valid decimal value."),
        ("", "Enter the test_decimal"),
        (100.10, "The answer must be less than 100"),
        (1000.45, "The answer must be less than 100"),
        ("1,000.45", "Not a valid decimal value."),  # comma-separated, fails validation
        (50000.0, "The answer must be less than 100"),
    ),
)
def test_validation_attached_to_field_and_runs__decimal(factories, value, error_message):
    question = factories.question.create(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e8c"),
        data_type=QuestionDataType.NUMBER,
        data_options=QuestionDataOptions(allow_decimals=True),
        name="test_decimal",
    )
    user = factories.user.create()
    interfaces.collections.add_question_validation(
        question, user, GreaterThan(question_id=question.id, minimum_value=0, inclusive=True)
    )
    interfaces.collections.add_question_validation(
        question, user, LessThan(question_id=question.id, maximum_value=100, inclusive=False)
    )

    _FormClass = build_question_form(
        [question], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
    )
    form = _FormClass(formdata=MultiDict({"q_e4bd98ab41ef4d23b1e59c0404891e8c": str(value)}))

    valid = form.validate()
    if error_message:
        assert valid is False
        assert error_message in form.errors["q_e4bd98ab41ef4d23b1e59c0404891e8c"]
    else:
        assert valid is True


def test_special_radio_field_enhancement_to_autocomplete(factories, app, db_session):
    form = factories.form.create()
    q = create_question(
        expression_context=EC(),
        form=form,
        text="Question text",
        hint="Question hint",
        name="question",
        data_type=QuestionDataType.RADIOS,
        items=[str(i) for i in range(25)],
    )
    form = build_question_form([q], evaluation_context=EC(), interpolation_context=EC())()

    question_field = form.get_question_field(q)
    assert isinstance(question_field, SelectField)
    assert isinstance(question_field.widget, MHCLGAccessibleAutocomplete)
    assert question_field.label.text == "Question text"
    assert question_field.description == "Question hint"
    assert len(question_field.validators) == 1
    assert isinstance(question_field.validators[0], DataRequired)


def test_validation_attached_to_multiple_fields(factories, db_session):
    user = factories.user.create()
    q1 = factories.question.create(data_type=QuestionDataType.TEXT_SINGLE_LINE, name="q0")
    q2 = factories.question.create(data_type=QuestionDataType.NUMBER)
    q3 = factories.question.create(data_type=QuestionDataType.YES_NO)

    interfaces.collections.add_question_validation(
        q2, user, GreaterThan(question_id=q2.id, minimum_value=100, inclusive=True)
    )

    _FormClass = build_question_form(
        [q1, q2, q3], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
    )
    form = _FormClass(formdata=MultiDict({q1.safe_qid: "", q2.safe_qid: 50, q3.safe_qid: True}))

    valid = form.validate()

    assert valid is False

    # check wtforms validation
    assert "Enter the q0" in form.errors[q1.safe_qid]

    # check custom expression validators are applied at the same time
    assert "The answer must be greater than or equal to 100" in form.errors[q2.safe_qid]

    assert q3.safe_qid not in form.errors


def test_reference_data_validation__integer(factories, db_session):
    user = factories.user.create()
    form = factories.form.create()
    q1 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, name="First question")
    q2 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)

    if hasattr(form, "cached_all_components"):
        del form.cached_all_components

    interfaces.collections.add_question_validation(
        q2,
        user,
        GreaterThan(question_id=q2.id, minimum_value=None, minimum_expression=f"(({q1.safe_qid}))", inclusive=True),
    )

    _FormClass = build_question_form(
        [q2],
        evaluation_context=ExpressionContext({q1.safe_qid: 100}),
        interpolation_context=ExpressionContext({q1.safe_qid: "£100"}),
    )
    form = _FormClass(formdata=MultiDict({q2.safe_qid: 50}))

    valid = form.validate()

    assert valid is False

    # Check answer is validated against reference data value
    assert "The answer must be greater than or equal to £100" in form.errors[q2.safe_qid]


def test_reference_data_validation__date(factories, db_session):
    user = factories.user.create()
    form = factories.form.create()
    q1 = factories.question.create(form=form, data_type=QuestionDataType.DATE, name="First question")
    q2 = factories.question.create(form=form, data_type=QuestionDataType.DATE, name="Second question")

    if hasattr(form, "cached_all_components"):
        del form.cached_all_components

    interfaces.collections.add_question_validation(
        q2,
        user,
        IsAfter(question_id=q2.id, earliest_value=None, earliest_expression=f"(({q1.safe_qid}))", inclusive=True),
    )

    _FormClass = build_question_form(
        [q2],
        evaluation_context=ExpressionContext({q1.safe_qid: date(2025, 1, 1)}),
        interpolation_context=ExpressionContext({q1.safe_qid: "1 January 2025"}),
    )
    form = _FormClass(formdata=MultiDict({q2.safe_qid: "1 1 2020"}))

    valid = form.validate()

    assert valid is False

    # Check answer is validated against reference data value
    assert "The answer must be on or after 1 January 2025" in form.errors[q2.safe_qid]


@pytest.mark.parametrize(
    "user_input, will_validate, saved_input",
    [
        ("  email@email.com  ", True, "email@email.com"),
        ("  not-an-email  ", False, "not-an-email"),
    ],
)
def test_email_strips_empty_chars(factories, user_input, will_validate, saved_input) -> None:
    question = factories.question.create(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"),
        data_type=QuestionDataType.EMAIL,
        name="test email",
    )
    _FormClass = build_question_form(
        [question], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
    )
    form = _FormClass(formdata=MultiDict({question.safe_qid: user_input}))
    valid = form.validate()
    assert valid is will_validate
    assert form.get_answer_to_question(question) == saved_input


@pytest.mark.parametrize(
    "user_input, will_validate, saved_input",
    [
        ("  www.google.com  ", True, "www.google.com"),
        ("  not-a-url  ", False, "not-a-url"),
    ],
)
def test_url_strips_empty_chars(factories, user_input, will_validate, saved_input) -> None:
    question = factories.question.create(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"),
        data_type=QuestionDataType.URL,
        name="test url",
    )
    _FormClass = build_question_form(
        [question], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
    )
    form = _FormClass(formdata=MultiDict({question.safe_qid: user_input}))
    valid = form.validate()
    assert valid is will_validate
    assert form.get_answer_to_question(question) == saved_input


@pytest.mark.parametrize(
    "user_input, will_validate, saved_input",
    [
        ("1000000", True, 1000000),
        ("1,000,000", True, 1000000),
        ("1,000", True, 1000),
        ("42", True, 42),
        ("1,2,3,4", True, 1234),
        ("100,", True, 100),
        (",100", True, 100),
        ("1,,000", True, 1000),
        ("not-a-number", False, None),
        ("1,000.5", False, None),  # decimal not allowed for integer
    ],
)
def test_integer_accepts_commas(factories, user_input, will_validate, saved_input) -> None:
    """Test that IntegerField accepts comma-separated input and stores as integer."""
    question = factories.question.create(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"),
        data_type=QuestionDataType.NUMBER,
        name="test integer",
    )
    _FormClass = build_question_form(
        [question], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
    )
    form = _FormClass(formdata=MultiDict({question.safe_qid: user_input}))
    valid = form.validate()
    assert valid is will_validate
    if will_validate:
        assert form.get_answer_to_question(question) == saved_input
