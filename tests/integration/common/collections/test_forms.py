import io
import uuid
from datetime import date

import pytest
from werkzeug.datastructures import FileStorage, MultiDict
from wtforms.fields.choices import SelectField
from wtforms.validators import DataRequired

from app.common.collections.forms import build_question_form
from app.common.collections.types import IntegerAnswer, YesNoAnswer
from app.common.data import interfaces
from app.common.data.interfaces.collections import create_question
from app.common.data.types import (
    FileUploadTypes,
    MaximumFileSize,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.custom import CustomExpression
from app.common.expressions.managed import GreaterThan, IsAfter, IsYes, LessThan
from app.common.expressions.references import ExpressionReference
from app.common.forms.fields import MHCLGAccessibleAutocomplete
from app.common.helpers.collections import SubmissionHelper
from app.metrics import MetricEventName
from tests.models import FactoryAnswer

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
    interfaces.collections.add_component_validation(
        question,
        user,
        GreaterThan(subject_reference=ExpressionReference.from_question(question), minimum_value=0, inclusive=True),
    )
    interfaces.collections.add_component_validation(
        question,
        user,
        LessThan(subject_reference=ExpressionReference.from_question(question), maximum_value=100, inclusive=False),
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
        # TODO reinstate once we add support for decimal values in expressions
        #  ("0.001", None),
        (-50, "The answer must be greater than or equal to 0"),
        (-50.0, "The answer must be greater than or equal to 0"),
        (3_000, "The answer must be less than 2000"),
        (50, None),
        ("0.002", None),
        ("0.2", None),
        ("56.234", None),
        ("1,000", None),
        ("1,222.333", None),
        ("99.9999999999", "The answer cannot be more than 3 decimal places"),
        ("123.4567", "The answer cannot be more than 3 decimal places"),
        (None, "The answer must be a number, like 100.5"),
        ("abcd", "The answer must be a number, like 100.5"),
        ("", "Enter the test_decimal"),
        ("2000.10", "The answer must be less than 2000"),
        ("2000.45", "The answer must be less than 2000"),
        ("2,000.45", "The answer must be less than 2000"),
        ("50000.0", "The answer must be less than 2000"),
    ),
)
def test_validation_attached_to_field_and_runs__decimal(factories, value, error_message):
    question = factories.question.create(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e8c"),
        data_type=QuestionDataType.NUMBER,
        data_options=QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL, max_decimal_places=3),
        name="test_decimal",
    )
    user = factories.user.create()
    interfaces.collections.add_component_validation(
        question,
        user,
        GreaterThan(subject_reference=ExpressionReference.from_question(question), minimum_value=0, inclusive=True),
    )
    interfaces.collections.add_component_validation(
        question,
        user,
        LessThan(subject_reference=ExpressionReference.from_question(question), maximum_value=2000, inclusive=False),
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
        assert valid is True, f"Unexpected validation error: {form.errors}"


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

    interfaces.collections.add_component_validation(
        q2,
        user,
        GreaterThan(subject_reference=ExpressionReference.from_question(q2), minimum_value=100, inclusive=True),
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

    interfaces.collections.add_component_validation(
        q2,
        user,
        GreaterThan(
            subject_reference=ExpressionReference.from_question(q2),
            minimum_value=None,
            minimum_expression=ExpressionReference.from_question(q1),
            inclusive=True,
        ),
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


def test_reference_data_validation__number__custom(factories, db_session):
    user = factories.user.create()
    form = factories.form.create()
    q1 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, name="First question")
    q2 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, name="Second question")
    q3 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER)

    interfaces.collections.add_component_validation(
        q3,
        user,
        CustomExpression(
            custom_expression=f"(({q3.safe_qid}))<(({q1.safe_qid}))+(({q2.safe_qid}))",
            custom_message=f"The answer must be less than q1 ((({q1.safe_qid}))) + q2 ((({q2.safe_qid})))",
        ),
    )

    _FormClass = build_question_form(
        [q3],
        evaluation_context=ExpressionContext({q1.safe_qid: 100, q2.safe_qid: 200}),
        interpolation_context=ExpressionContext({q1.safe_qid: "£100", q2.safe_qid: "£200"}),
    )
    form = _FormClass(formdata=MultiDict({q3.safe_qid: 500}))

    valid = form.validate()

    assert valid is False

    # Check answer is validated against reference data value
    assert "The answer must be less than q1 (£100) + q2 (£200)" in form.errors[q3.safe_qid]


def test_reference_data_validation__date(factories, db_session):
    user = factories.user.create()
    form = factories.form.create()
    q1 = factories.question.create(form=form, data_type=QuestionDataType.DATE, name="First question")
    q2 = factories.question.create(form=form, data_type=QuestionDataType.DATE, name="Second question")

    interfaces.collections.add_component_validation(
        q2,
        user,
        IsAfter(
            subject_reference=ExpressionReference.from_question(q2),
            earliest_value=None,
            earliest_expression=ExpressionReference.from_question(q1),
            inclusive=True,
        ),
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


@pytest.mark.parametrize(
    "supported_types, file_input, will_validate",
    [
        ([FileUploadTypes.PDF], "document.pdf", True),
        ([FileUploadTypes.PDF], "image.png", False),
        ([FileUploadTypes.IMAGE], "image.png", True),
        ([FileUploadTypes.IMAGE], "document.pdf", False),
        ([FileUploadTypes.PDF, FileUploadTypes.IMAGE], "document.pdf", True),
        ([FileUploadTypes.PDF, FileUploadTypes.IMAGE], "image.png", True),
        ([t for t in FileUploadTypes], "application.exe", False),
    ],
)
def test_file_upload_field_accepts_file_types(factories, supported_types, file_input, will_validate):
    question = factories.question.create(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"),
        data_type=QuestionDataType.FILE_UPLOAD,
        name="test file",
        data_options=QuestionDataOptions(file_types_supported=supported_types),
    )
    _FormClass = build_question_form(
        [question], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
    )
    form = _FormClass(formdata=MultiDict({question.safe_qid: FileStorage(filename=file_input)}))
    valid = form.validate()
    assert valid is will_validate
    if will_validate:
        assert form.get_answer_to_question(question).filename == file_input


@pytest.mark.parametrize(
    "max_file_size, file_byte_length, will_validate",
    [
        (MaximumFileSize.SMALL, 7 * 1024 * 1024, True),
        (MaximumFileSize.SMALL, 7 * 1024 * 1024 + 1, False),
        (MaximumFileSize.MEDIUM, 30 * 1024 * 1024, True),
        (MaximumFileSize.MEDIUM, 30 * 1024 * 1024 + 1, False),
        (MaximumFileSize.LARGE, 100 * 1024 * 1024, True),
        (MaximumFileSize.LARGE, 100 * 1024 * 1024 + 1, False),
    ],
)
def test_file_upload_field_validates_maximum_file_size(factories, max_file_size, file_byte_length, will_validate):
    question = factories.question.create(
        id=uuid.UUID("e4bd98ab-41ef-4d23-b1e5-9c0404891e7a"),
        data_type=QuestionDataType.FILE_UPLOAD,
        name="test file",
        data_options=QuestionDataOptions(
            file_types_supported=[FileUploadTypes.PDF],
            maximum_file_size=max_file_size,
        ),
    )
    _FormClass = build_question_form(
        [question], evaluation_context=ExpressionContext(), interpolation_context=ExpressionContext()
    )
    file_storage = FileStorage(
        stream=io.BytesIO(b"\x00" * file_byte_length),
        filename="document.pdf",
    )
    form = _FormClass(formdata=MultiDict({question.safe_qid: file_storage}))
    valid = form.validate()
    assert valid is will_validate
    if not will_validate:
        assert (
            f"The selected file must be smaller than {max_file_size.human_readable}." in form.errors[question.safe_qid]
        )


class TestValidationMetrics:
    def test_validation_metrics_managed_success(self, factories, mock_sentry_metrics):
        q1 = factories.question.create(data_type=QuestionDataType.NUMBER)
        interfaces.collections.add_component_validation(
            q1,
            factories.user.create(),
            GreaterThan(
                subject_reference=ExpressionReference.from_question(q1),
                minimum_value=8,
            ),
        )

        _FormClass = build_question_form(
            [q1],
            evaluation_context=ExpressionContext({q1.safe_qid: 9}),
            interpolation_context=ExpressionContext({q1.safe_qid: 9}),
        )
        form = _FormClass(formdata=MultiDict({q1.safe_qid: 9}))

        valid = form.validate()

        assert valid is True
        assert mock_sentry_metrics.call_count == 2
        assert mock_sentry_metrics.call_args[0] == (MetricEventName.SUBMISSION_MANAGED_VALIDATION_SUCCESS, 1)

    def test_validation_metrics_managed_failure(self, factories, mock_sentry_metrics):
        q1 = factories.question.create(data_type=QuestionDataType.NUMBER)
        interfaces.collections.add_component_validation(
            q1,
            factories.user.create(),
            GreaterThan(
                subject_reference=ExpressionReference.from_question(q1),
                minimum_value=8,
            ),
        )

        _FormClass = build_question_form(
            [q1],
            evaluation_context=ExpressionContext({q1.safe_qid: 7}),
            interpolation_context=ExpressionContext({q1.safe_qid: 7}),
        )
        form = _FormClass(formdata=MultiDict({q1.safe_qid: 7}))

        valid = form.validate()

        assert valid is False
        assert mock_sentry_metrics.call_count == 2
        assert mock_sentry_metrics.call_args[0] == (MetricEventName.SUBMISSION_MANAGED_VALIDATION_ERROR, 1)

    def test_validation_metrics_custom_success(self, factories, mock_sentry_metrics):
        q1 = factories.question.create(data_type=QuestionDataType.NUMBER)
        interfaces.collections.add_component_validation(
            q1,
            factories.user.create(),
            CustomExpression(
                custom_expression=f"(({q1.safe_qid}))<5",
                custom_message="failure message",
            ),
        )

        _FormClass = build_question_form(
            [q1],
            evaluation_context=ExpressionContext({q1.safe_qid: 2}),
            interpolation_context=ExpressionContext({q1.safe_qid: 2}),
        )
        form = _FormClass(formdata=MultiDict({q1.safe_qid: 2}))

        valid = form.validate()

        assert valid is True
        assert mock_sentry_metrics.call_count == 2
        assert mock_sentry_metrics.call_args[0] == (MetricEventName.SUBMISSION_CUSTOM_VALIDATION_SUCCESS, 1)

    def test_validation_metrics_custom_failures(self, factories, mock_sentry_metrics):
        q1 = factories.question.create(data_type=QuestionDataType.NUMBER)
        interfaces.collections.add_component_validation(
            q1,
            factories.user.create(),
            CustomExpression(
                custom_expression=f"(({q1.safe_qid}))<5",
                custom_message="failure message",
            ),
        )

        _FormClass = build_question_form(
            [q1],
            evaluation_context=ExpressionContext({q1.safe_qid: 23}),
            interpolation_context=ExpressionContext({q1.safe_qid: 23}),
        )
        form = _FormClass(formdata=MultiDict({q1.safe_qid: 23}))

        valid = form.validate()

        assert valid is False
        assert mock_sentry_metrics.call_count == 2
        assert mock_sentry_metrics.call_args[0] == (MetricEventName.SUBMISSION_CUSTOM_VALIDATION_ERROR, 1)


class TestGroupValidationWithDefaultContext:
    def test_group_validation_passes_when_conditional_number_question_answer_is_missing(
        self, factories, mock_sentry_metrics
    ):
        user = factories.user.create()
        is_yes_question = factories.question.create(data_type=QuestionDataType.YES_NO, order=0)
        group = factories.group.create(
            form=is_yes_question.form,
            order=1,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        question_number_one = factories.question.create(
            form=is_yes_question.form, parent=group, data_type=QuestionDataType.NUMBER, order=0
        )
        question_number_two = factories.question.create(
            form=is_yes_question.form, parent=group, data_type=QuestionDataType.NUMBER, order=1
        )
        interfaces.collections.add_component_condition(
            question_number_two,
            user,
            IsYes(subject_reference=ExpressionReference.from_question(is_yes_question)),
        )
        interfaces.collections.add_component_validation(
            group,
            user,
            CustomExpression(
                custom_expression=f"(({question_number_two.safe_qid})) + (({question_number_one.safe_qid})) == 50",
                custom_message="Total must be 50",
            ),
        )

        submission = factories.submission.create(
            collection=is_yes_question.form.collection,
            answers=[FactoryAnswer(is_yes_question, YesNoAnswer(False))],
        )
        helper = SubmissionHelper(submission)

        _FormClass = build_question_form(
            [question_number_one],
            evaluation_context=helper.cached_evaluation_context,
            interpolation_context=helper.cached_interpolation_context,
            component=group,
            submission_helper=helper,
        )
        form_instance = _FormClass(formdata=MultiDict({question_number_one.safe_qid: "50"}))

        valid = form_instance.validate()

        assert valid is True
        assert form_instance.group_validation_error is None

    def test_group_validation_error_excludes_invisible_referenced_questions(self, factories, mock_sentry_metrics):
        user = factories.user.create()
        is_yes_question = factories.question.create(data_type=QuestionDataType.YES_NO, order=0)
        question_off_page_hidden = factories.question.create(
            form=is_yes_question.form, data_type=QuestionDataType.NUMBER, order=1
        )
        question_off_page_visible = factories.question.create(
            form=is_yes_question.form, data_type=QuestionDataType.NUMBER, order=2
        )
        interfaces.collections.add_component_condition(
            question_off_page_hidden,
            user,
            IsYes(subject_reference=ExpressionReference.from_question(is_yes_question)),
        )
        group = factories.group.create(
            form=is_yes_question.form,
            order=3,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        question_on_page = factories.question.create(
            form=is_yes_question.form, parent=group, data_type=QuestionDataType.NUMBER, order=0
        )
        interfaces.collections.add_component_validation(
            group,
            user,
            CustomExpression(
                custom_expression=f"(({question_on_page.safe_qid})) + (({question_off_page_visible.safe_qid})) "
                + f"+ (({question_off_page_hidden.safe_qid})) == 150",
                custom_message="Total must be 150",
            ),
        )

        submission = factories.submission.create(
            collection=is_yes_question.form.collection,
            answers=[
                FactoryAnswer(is_yes_question, YesNoAnswer(False)),
                FactoryAnswer(question_off_page_visible, IntegerAnswer(value=50)),
            ],
        )
        helper = SubmissionHelper(submission)

        _FormClass = build_question_form(
            [question_on_page],
            evaluation_context=helper.cached_evaluation_context,
            interpolation_context=helper.cached_interpolation_context,
            component=group,
            submission_helper=helper,
        )
        form_instance = _FormClass(formdata=MultiDict({question_on_page.safe_qid: "50"}))

        valid = form_instance.validate()

        # the condition was safely allowed to run, and fails
        assert valid is False
        # on_page_entries includes q_on_page (it's a visible field on this form)
        on_page_ids = {e.question.id for e in form_instance.group_validation_error.on_page_entries}
        off_page_ids = {e.question.id for e in form_instance.group_validation_error.off_page_entries}

        # errors off page includes visible question but don't include the question that is hidden
        # by a condition
        assert question_on_page.id in on_page_ids
        assert question_off_page_hidden.id not in off_page_ids
        assert question_off_page_visible.id in off_page_ids

    def test_group_validation_passes_when_hidden_question_has_stale_persisted_answer(
        self, factories, mock_sentry_metrics
    ):
        user = factories.user.create()
        is_yes_question = factories.question.create(data_type=QuestionDataType.YES_NO, order=0)
        group = factories.group.create(
            form=is_yes_question.form,
            order=1,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        question_number_one = factories.question.create(
            form=is_yes_question.form, parent=group, data_type=QuestionDataType.NUMBER, order=0
        )
        question_number_two = factories.question.create(
            form=is_yes_question.form, parent=group, data_type=QuestionDataType.NUMBER, order=1
        )
        interfaces.collections.add_component_condition(
            question_number_two,
            user,
            IsYes(subject_reference=ExpressionReference.from_question(is_yes_question)),
        )
        interfaces.collections.add_component_validation(
            group,
            user,
            CustomExpression(
                custom_expression=f"(({question_number_two.safe_qid})) + (({question_number_one.safe_qid})) == 50",
                custom_message="Total must be 50",
            ),
        )

        # question_number_two was answered earlier (when is_yes was True)
        # is_yes to False so question_number_two is now hidden
        submission = factories.submission.create(
            collection=is_yes_question.form.collection,
            answers=[
                FactoryAnswer(is_yes_question, YesNoAnswer(False)),
                FactoryAnswer(question_number_two, IntegerAnswer(value=100)),
            ],
        )
        helper = SubmissionHelper(submission)

        _FormClass = build_question_form(
            [question_number_one],
            evaluation_context=helper.cached_evaluation_context,
            interpolation_context=helper.cached_interpolation_context,
            component=group,
            submission_helper=helper,
        )
        form_instance = _FormClass(formdata=MultiDict({question_number_one.safe_qid: "50"}))

        valid = form_instance.validate()

        assert valid is True
        assert form_instance.group_validation_error is None
