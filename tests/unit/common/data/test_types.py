from app import CollectionStatusEnum
from app.common.data.types import (
    FileUploadTypes,
    MaximumFileSize,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataOptionsPostgresType,
)


class TestCollectionStatusEnum:
    def test_lt_returns_false_when_equal(self):
        assert (CollectionStatusEnum.DRAFT < CollectionStatusEnum.DRAFT) is False

    def test_gt_returns_false_when_equal(self):
        assert (CollectionStatusEnum.DRAFT > CollectionStatusEnum.DRAFT) is False

    def test_lt_returns_true(self):
        assert (CollectionStatusEnum.DRAFT < CollectionStatusEnum.CLOSED) is True

    def test_gt_returns_false(self):
        assert (CollectionStatusEnum.DRAFT > CollectionStatusEnum.CLOSED) is False

    def test_gt_returns_true(self):
        assert (CollectionStatusEnum.CLOSED > CollectionStatusEnum.DRAFT) is True

    def test_lt_returns_false(self):
        assert (CollectionStatusEnum.CLOSED < CollectionStatusEnum.DRAFT) is False

    def test_sort_by_status(self):
        input = [
            CollectionStatusEnum.CLOSED,
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.CLOSED,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.SCHEDULED,
        ]
        expected = [
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.CLOSED,
            CollectionStatusEnum.CLOSED,
        ]
        assert sorted(input) == expected


class TestQuestionDataOptionsPostgresType:
    def test_defaults(self):
        options = QuestionDataOptions()
        data_options = QuestionDataOptionsPostgresType().process_bind_param(options, dialect=None)
        assert data_options == {}

    def test_allow_decimals(self):
        options = QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL)
        data_options = QuestionDataOptionsPostgresType().process_bind_param(options, dialect=None)
        assert data_options == {"number_type": "Decimal number"}

    def test_file_types_supported(self):
        options = QuestionDataOptions(file_types_supported=[FileUploadTypes.PDF, FileUploadTypes.IMAGE])
        data_options = QuestionDataOptionsPostgresType().process_bind_param(options, dialect=None)
        assert data_options == {"file_types_supported": ["PDF", "image"]}

    def test_maximum_file_size(self):
        options = QuestionDataOptions(maximum_file_size=MaximumFileSize.MEDIUM)
        data_options = QuestionDataOptionsPostgresType().process_bind_param(options, dialect=None)
        assert data_options == {"maximum_file_size": "Medium"}

    def test_file_upload_options_combined(self):
        options = QuestionDataOptions(
            file_types_supported=[FileUploadTypes.PDF],
            maximum_file_size=MaximumFileSize.LARGE,
        )
        data_options = QuestionDataOptionsPostgresType().process_bind_param(options, dialect=None)
        assert data_options == {
            "file_types_supported": ["PDF"],
            "maximum_file_size": "Large",
        }

    def test_round_trip_with_maximum_file_size(self):
        options = QuestionDataOptions(
            file_types_supported=[FileUploadTypes.PDF],
            maximum_file_size=MaximumFileSize.SMALL,
        )
        postgres_type = QuestionDataOptionsPostgresType()
        serialised = postgres_type.process_bind_param(options, dialect=None)
        deserialised = postgres_type.process_result_value(serialised, dialect=None)
        assert deserialised.maximum_file_size == MaximumFileSize.SMALL
        assert deserialised.file_types_supported == [FileUploadTypes.PDF]
