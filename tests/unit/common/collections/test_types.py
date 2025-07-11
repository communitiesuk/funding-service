import pytest

from app.common.collections.types import Integer, TextMultiLine, TextSingleLine


@pytest.mark.parametrize(
    "model, data",
    (
        (TextSingleLine, "hello"),
        (TextMultiLine, "hello\nthere"),
        (Integer, 5),
    ),
)
class TestSubmissionAnswerRootModels:
    def test_get_value_for_submission(self, model, data):
        assert model(data).get_value_for_submission() == data

    def test_get_value_for_form(self, model, data):
        assert model(data).get_value_for_form() == data

    def test_get_value_for_expression(self, model, data):
        assert model(data).get_value_for_expression() == data

    def test_get_value_for_text_export(self, model, data):
        assert model(data).get_value_for_text_export() == data
