import pytest

from app.common.collections.question_display import get_question_setting_details
from app.common.data.models import Question
from app.common.data.types import (
    FileUploadTypes,
    MaximumFileSize,
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)


def _question(
    data_type: QuestionDataType,
    presentation_options: QuestionPresentationOptions | None = None,
    data_options: QuestionDataOptions | None = None,
) -> Question:
    return Question(
        data_type=data_type,
        presentation_options=presentation_options or QuestionPresentationOptions(),
        data_options=data_options or QuestionDataOptions(),
    )


class TestGetQuestionSettingDetails:
    def test_multiline_word_limit(self):
        question = _question(QuestionDataType.TEXT_MULTI_LINE, QuestionPresentationOptions(word_limit=200))
        assert get_question_setting_details(question) == ["200 words"]

    def test_multiline_without_word_limit_has_no_details(self):
        question = _question(QuestionDataType.TEXT_MULTI_LINE)
        assert get_question_setting_details(question) == []

    def test_number_prefix_and_type(self):
        question = _question(
            QuestionDataType.NUMBER,
            QuestionPresentationOptions(prefix="£"),
            QuestionDataOptions(number_type=NumberTypeEnum.INTEGER),
        )
        assert get_question_setting_details(question) == ["£, whole number"]

    def test_number_suffix_and_decimal_type(self):
        question = _question(
            QuestionDataType.NUMBER,
            QuestionPresentationOptions(suffix="%"),
            QuestionDataOptions(number_type=NumberTypeEnum.DECIMAL),
        )
        assert get_question_setting_details(question) == ["%, decimal number"]

    def test_file_upload_specific_types_and_size(self):
        question = _question(
            QuestionDataType.FILE_UPLOAD,
            data_options=QuestionDataOptions(
                file_types_supported=[FileUploadTypes.PDF, FileUploadTypes.DOCUMENT],
                maximum_file_size=MaximumFileSize.SMALL,
            ),
        )
        assert get_question_setting_details(question) == ["PDF or Microsoft Word Document, up to 7MB"]

    def test_file_upload_all_types_shows_only_size(self):
        question = _question(
            QuestionDataType.FILE_UPLOAD,
            data_options=QuestionDataOptions(
                file_types_supported=list(FileUploadTypes),
                maximum_file_size=MaximumFileSize.MEDIUM,
            ),
        )
        assert get_question_setting_details(question) == ["up to 30MB"]

    @pytest.mark.parametrize(
        "data_type",
        (QuestionDataType.TEXT_SINGLE_LINE, QuestionDataType.EMAIL, QuestionDataType.YES_NO, QuestionDataType.DATE),
    )
    def test_types_without_surfaced_settings(self, data_type):
        assert get_question_setting_details(_question(data_type)) == []
