import pytest

from app.common.collections.types import Integer, TextMultiLine, TextSingleLine, YesNo


@pytest.mark.parametrize(
    "model, data, expected_text_export",
    (
        (TextSingleLine, "hello", "hello"),
        (TextMultiLine, "hello\nthere", "hello\nthere"),
        (Integer, 5, "5"),
        (YesNo, True, "Yes"),
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
