import datetime
import itertools

import pytest

from app.common.collections.types import (
    DateAnswer,
    EmailAnswer,
    IntegerAnswer,
    SingleChoiceFromListAnswer,
    SubmissionAnswerBaseModel,
    SubmissionAnswerRootModel,
    TextMultiLineAnswer,
    TextSingleLineAnswer,
    UrlAnswer,
    YesNoAnswer,
)


def test_all_answer_types_tested():
    root_model_types = list(
        itertools.chain.from_iterable(scls.__subclasses__() for scls in SubmissionAnswerRootModel.__subclasses__())
    )
    base_model_types = list(SubmissionAnswerBaseModel.__subclasses__())

    assert len(root_model_types + base_model_types) == 9, (
        "If adding a new answer type, update the appropriate test below"
    )


@pytest.mark.parametrize(
    "model, data, expected_text_export",
    (
        (TextSingleLineAnswer, "hello", "hello"),
        (TextMultiLineAnswer, "hello\nthere", "hello\nthere"),
        (EmailAnswer, "name@example.com", "name@example.com"),
        (UrlAnswer, "https://www.gov.uk", "https://www.gov.uk"),
        (YesNoAnswer, True, "Yes"),
    ),
)
class TestSubmissionAnswerRootModels:
    def test_get_value_for_submission(self, model, data, expected_text_export):
        assert model(data).get_value_for_submission() == data

    def test_get_value_for_form(self, model, data, expected_text_export):
        assert model(data).get_value_for_form() == data

    def test_get_value_for_evaluation(self, model, data, expected_text_export):
        assert model(data).get_value_for_evaluation() == data

    def test_get_value_for_interpolation(self, model, data, expected_text_export):
        assert model(data).get_value_for_interpolation() == expected_text_export

    def test_get_value_for_text_export(self, model, data, expected_text_export):
        assert model(data).get_value_for_text_export() == expected_text_export


class TestSubmissionAnswerBaseModels:
    @pytest.mark.parametrize(
        "model, data, submission_data",
        (
            (IntegerAnswer, {"value": 50}, {"value": 50}),
            (IntegerAnswer, {"value": 50, "prefix": "£"}, {"value": 50, "prefix": "£"}),
            (IntegerAnswer, {"value": 50, "suffix": "lbs"}, {"value": 50, "suffix": "lbs"}),
            (SingleChoiceFromListAnswer, {"key": "key", "label": "label"}, {"key": "key", "label": "label"}),
            (
                DateAnswer,
                {"answer": datetime.date(2023, 10, 5), "approximate_date": False},
                {"answer": "2023-10-05", "approximate_date": False},
            ),
            (
                DateAnswer,
                {"answer": datetime.date(2023, 10, 1), "approximate_date": True},
                {"answer": "2023-10-01", "approximate_date": True},
            ),
        ),
    )
    def test_get_value_for_submission(self, model, data, submission_data):
        assert model(**data).get_value_for_submission() == submission_data

    @pytest.mark.parametrize(
        "model, data, form_value",
        (
            (IntegerAnswer, {"value": 50}, 50),
            (SingleChoiceFromListAnswer, {"key": "key", "label": "label"}, "key"),
        ),
    )
    def test_get_value_for_form(self, model, data, form_value):
        assert model(**data).get_value_for_form() == form_value

    @pytest.mark.parametrize(
        "model, data, evaluation_value",
        (
            (IntegerAnswer, {"value": 50}, 50),
            (SingleChoiceFromListAnswer, {"key": "key", "label": "label"}, "key"),
        ),
    )
    def test_get_value_for_evaluation(self, model, data, evaluation_value):
        assert model(**data).get_value_for_evaluation() == evaluation_value

    @pytest.mark.parametrize(
        "model, data, interpolation_value",
        (
            (IntegerAnswer, {"value": 50}, "50"),
            (IntegerAnswer, {"value": 9_999, "prefix": "£"}, "£9,999"),
            (IntegerAnswer, {"value": 1_000_000, "suffix": "kgs"}, "1,000,000kgs"),
            (SingleChoiceFromListAnswer, {"key": "key", "label": "label"}, "label"),
        ),
    )
    def test_get_value_for_interpolation(self, model, data, interpolation_value):
        assert model(**data).get_value_for_interpolation() == interpolation_value

    @pytest.mark.parametrize(
        "model, data, text_export_value",
        (
            (IntegerAnswer, {"value": 50}, "50"),
            (IntegerAnswer, {"value": 1_000_000, "prefix": "£"}, "£1,000,000"),
            (IntegerAnswer, {"value": 1_000_000, "suffix": "lbs"}, "1,000,000lbs"),
            (SingleChoiceFromListAnswer, {"key": "key", "label": "label"}, "label"),
            (DateAnswer, {"answer": datetime.date(2023, 10, 5), "approximate_date": False}, "2023-10-05"),
            (DateAnswer, {"answer": datetime.date(2023, 10, 1), "approximate_date": True}, "October 2023"),
        ),
    )
    def test_get_value_for_text_export(self, model, data, text_export_value):
        assert model(**data).get_value_for_text_export() == text_export_value

    @pytest.mark.parametrize(
        "model, data, json_export_value",
        (
            (IntegerAnswer, {"value": 50}, {"value": 50}),
            (IntegerAnswer, {"value": 1_000_000, "prefix": "£"}, {"value": 1_000_000, "prefix": "£"}),
            (IntegerAnswer, {"value": 1_000_000, "suffix": "lbs"}, {"value": 1_000_000, "suffix": "lbs"}),
            (SingleChoiceFromListAnswer, {"key": "key1", "label": "label1"}, {"key": "key1", "label": "label1"}),
            (DateAnswer, {"answer": datetime.date(2023, 10, 5), "approximate_date": False}, "2023-10-05"),
            (DateAnswer, {"answer": datetime.date(2023, 10, 1), "approximate_date": True}, "October 2023"),
        ),
    )
    def test_get_value_for_json_export(self, model, data, json_export_value):
        assert model(**data).get_value_for_json_export() == json_export_value
