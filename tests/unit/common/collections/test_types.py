import itertools

import pytest

from app.common.collections.types import (
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

    assert len(root_model_types + base_model_types) == 7, (
        "If adding a new answer type, update the appropriate test below"
    )


@pytest.mark.parametrize(
    "model, data, expected_text_export",
    (
        (TextSingleLineAnswer, "hello", "hello"),
        (TextMultiLineAnswer, "hello\nthere", "hello\nthere"),
        (IntegerAnswer, 5, "5"),
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

    def test_get_value_for_expression(self, model, data, expected_text_export):
        assert model(data).get_value_for_expression() == data

    def test_get_value_for_text_export(self, model, data, expected_text_export):
        assert model(data).get_value_for_text_export() == expected_text_export


class TestSubmissionAnswerBaseModels:
    @pytest.mark.parametrize(
        "model, data, submission_data",
        ((SingleChoiceFromListAnswer, {"key": "key", "label": "label"}, {"key": "key", "label": "label"}),),
    )
    def test_get_value_for_submission(self, model, data, submission_data):
        assert model(**data).get_value_for_submission() == submission_data

    @pytest.mark.parametrize(
        "model, data, form_value",
        ((SingleChoiceFromListAnswer, {"key": "key", "label": "label"}, "key"),),
    )
    def test_get_value_for_form(self, model, data, form_value):
        assert model(**data).get_value_for_form() == form_value

    @pytest.mark.parametrize(
        "model, data, expression_value",
        ((SingleChoiceFromListAnswer, {"key": "key", "label": "label"}, "key"),),
    )
    def test_get_value_for_expression(self, model, data, expression_value):
        assert model(**data).get_value_for_expression() == expression_value

    @pytest.mark.parametrize(
        "model, data, text_export_value",
        ((SingleChoiceFromListAnswer, {"key": "key", "label": "label"}, "label"),),
    )
    def test_get_value_for_text_export(self, model, data, text_export_value):
        assert model(**data).get_value_for_text_export() == text_export_value
