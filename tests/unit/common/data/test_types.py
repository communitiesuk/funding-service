from app import CollectionStatusEnum
from app.common.data.types import (
    FileUploadTypes,
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
        options = QuestionDataOptions(file_types_supported=[FileUploadTypes.CSV, FileUploadTypes.PDF])
        data_options = QuestionDataOptionsPostgresType().process_bind_param(options, dialect=None)
        assert data_options == {"file_types_supported": ["CSV", "PDF"]}

    def test_file_types_supported_all(self):
        options = QuestionDataOptions(file_types_supported=list(FileUploadTypes))
        data_options = QuestionDataOptionsPostgresType().process_bind_param(options, dialect=None)
        assert data_options == {
            "file_types_supported": [
                "CSV",
                "image",
                "Microsoft Excel Spreadsheet",
                "Microsoft Word Document",
                "PDF",
                "text",
            ]
        }


class TestFileUploadTypes:
    def test_human_readable_values(self):
        assert FileUploadTypes.CSV.value == "CSV"
        assert FileUploadTypes.IMAGE.value == "image"
        assert FileUploadTypes.SPREADSHEET.value == "Microsoft Excel Spreadsheet"
        assert FileUploadTypes.DOCUMENT.value == "Microsoft Word Document"
        assert FileUploadTypes.PDF.value == "PDF"
        assert FileUploadTypes.TEXT.value == "text"

    def test_extensions(self):
        assert FileUploadTypes.CSV.extensions == [".csv"]
        assert FileUploadTypes.IMAGE.extensions == [".jpeg", ".jpg", ".png"]
        assert FileUploadTypes.SPREADSHEET.extensions == [".xlsx"]
        assert FileUploadTypes.DOCUMENT.extensions == [".docx", ".doc"]
        assert FileUploadTypes.PDF.extensions == [".pdf"]
        assert FileUploadTypes.TEXT.extensions == [".json", ".odt", ".rtf", ".txt"]

    def test_all_members_have_extensions(self):
        for file_type in FileUploadTypes:
            assert len(file_type.extensions) > 0

    def test_mime_types(self):
        assert FileUploadTypes.CSV.mime_types == ["text/csv"]
        assert FileUploadTypes.IMAGE.mime_types == ["image/jpeg", "image/png"]
        assert FileUploadTypes.SPREADSHEET.mime_types == [
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ]
        assert FileUploadTypes.DOCUMENT.mime_types == [
            "application/msword",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ]
        assert FileUploadTypes.PDF.mime_types == ["application/pdf"]
        assert FileUploadTypes.TEXT.mime_types == [
            "application/json",
            "application/vnd.oasis.opendocument.text",
            "application/rtf",
            "text/plain",
        ]

    def test_all_members_have_mime_types(self):
        for file_type in FileUploadTypes:
            assert len(file_type.mime_types) > 0
