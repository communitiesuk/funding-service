import pytest

from app.common.data.utils import generate_submission_reference


class TestGenerateSubmissionReference:
    def test_generate_code(self, factories, mocker):
        mocker.patch("random.choices", return_value=["1", "2", "3", "4", "5", "6"])

        collection = factories.collection.build(grant__code="TEST")

        assert generate_submission_reference(collection) == "TEST-R123456"

    def test_avoid_reference(self, factories, mocker):
        mocker.patch(
            "random.choices",
            side_effect=[
                ["1", "2", "3", "4", "5", "6"],
                ["1", "2", "3", "4", "5", "7"],
            ],
        )

        collection = factories.collection.build(grant__code="TEST")

        assert generate_submission_reference(collection, avoid_references=["TEST-R123456"]) == "TEST-R123457"

    def test_max_100_attempts(self, factories, mocker):
        mocker.patch("random.choices", return_value=["1", "2", "3", "4", "5", "6"])

        collection = factories.collection.build(grant__code="TEST")

        with pytest.raises(RuntimeError, match="Could not generate a unique submission reference"):
            generate_submission_reference(collection, avoid_references=["TEST-R123456"])
