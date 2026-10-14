import datetime

import pytest

from app.common.data.types import CollectionType
from app.common.data.utils import format_datetime_for_internal_export, generate_submission_reference


def test_format_datetime_for_internal_export():
    assert format_datetime_for_internal_export(datetime.datetime(2025, 1, 1, 9, 1, 2)) == "01/01/2025 09:01:02"
    assert format_datetime_for_internal_export(datetime.datetime(2025, 6, 1, 9, 1, 2)) == "01/06/2025 10:01:02"
    assert format_datetime_for_internal_export(None) == ""


class TestGenerateSubmissionReference:
    def test_generate_code(self, factories, mocker):
        mocker.patch("random.choices", return_value=["1", "2", "3", "4", "5", "6"])

        report = factories.collection.build(grant__code="TEST", type=CollectionType.MONITORING_REPORT)
        application = factories.collection.build(grant__code="TEST", type=CollectionType.APPLICATION)

        assert generate_submission_reference(report) == "TEST-R123456"
        assert generate_submission_reference(application) == "TEST-A123456"

    def test_avoid_reference(self, factories, mocker):
        mocker.patch(
            "random.choices",
            side_effect=[
                ["1", "2", "3", "4", "5", "6"],
                ["1", "2", "3", "4", "5", "7"],
            ],
        )

        collection = factories.collection.build(grant__code="TEST", type=CollectionType.MONITORING_REPORT)

        assert generate_submission_reference(collection, avoid_references=["TEST-R123456"]) == "TEST-R123457"

    def test_max_100_attempts(self, factories, mocker):
        mocker.patch("random.choices", return_value=["1", "2", "3", "4", "5", "6"])

        collection = factories.collection.build(grant__code="TEST", type=CollectionType.MONITORING_REPORT)

        with pytest.raises(RuntimeError, match="Could not generate a unique submission reference"):
            generate_submission_reference(collection, avoid_references=["TEST-R123456"])
