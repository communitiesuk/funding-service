from types import SimpleNamespace

import pytest
from markupsafe import Markup
from werkzeug.datastructures import MultiDict

from app.common.collections.question_display import (
    QuestionDisplayOptions,
    QuestionInfo,
    describe_component_validations,
    get_question_setting_details,
)
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


class TestQuestionDisplayOptions:
    def test_no_sentinel_shows_everything(self):
        # A fresh visit has no query args at all: the page shows every category.
        options = QuestionDisplayOptions.from_request_args(MultiDict())
        assert options.shown == frozenset(QuestionInfo)
        assert options.hint and options.settings and options.options
        assert options.guidance and options.conditions and options.validations

    def test_sentinel_with_selection_shows_only_those_categories(self):
        options = QuestionDisplayOptions.from_request_args(
            MultiDict([("filtered", "1"), ("show", "hint"), ("show", "conditions")])
        )
        assert options.shown == frozenset({QuestionInfo.HINT, QuestionInfo.CONDITIONS})
        assert options.hint and options.conditions
        assert not options.settings and not options.options
        assert not options.guidance and not options.validations

    def test_sentinel_without_selection_shows_nothing(self):
        # Unchecking everything and applying is distinct from a fresh visit.
        options = QuestionDisplayOptions.from_request_args(MultiDict([("filtered", "1")]))
        assert options.shown == frozenset()
        assert options.active_categories == []

    def test_unknown_show_values_are_ignored(self):
        options = QuestionDisplayOptions.from_request_args(
            MultiDict([("filtered", "1"), ("show", "hint"), ("show", "not-a-category")])
        )
        assert options.shown == frozenset({QuestionInfo.HINT})

    def test_active_categories_are_in_enum_order(self):
        options = QuestionDisplayOptions.from_request_args(
            MultiDict([("filtered", "1"), ("show", "validations"), ("show", "hint"), ("show", "guidance")])
        )
        assert options.active_categories == [QuestionInfo.HINT, QuestionInfo.GUIDANCE, QuestionInfo.VALIDATIONS]

    def test_checkbox_items_reflect_checked_state(self):
        options = QuestionDisplayOptions(shown=frozenset({QuestionInfo.HINT}))
        items = options.checkbox_items()
        assert [item["value"] for item in items] == [info.value for info in QuestionInfo]
        checked = {item["value"]: item["checked"] for item in items}
        assert checked["hint"] is True
        assert checked["settings"] is False

    def test_query_dict_round_trips_through_from_request_args(self):
        options = QuestionDisplayOptions(shown=frozenset({QuestionInfo.SETTINGS, QuestionInfo.OPTIONS}))
        query = options.query_dict()
        assert query["filtered"] == "1"
        assert set(query["show"]) == {"settings", "options"}
        assert QuestionDisplayOptions.from_request_args(MultiDict(list(_expand(query)))).shown == options.shown

    def test_without_hides_a_single_category(self):
        options = QuestionDisplayOptions.all_shown()
        reduced = options.without(QuestionInfo.HINT)
        assert QuestionInfo.HINT not in reduced.shown
        assert reduced.shown == frozenset(QuestionInfo) - {QuestionInfo.HINT}
        # The original is unchanged (frozen dataclass).
        assert QuestionInfo.HINT in options.shown

    def test_labels_are_human_readable(self):
        assert QuestionInfo.HINT.label == "Hint text"
        assert QuestionInfo.SETTINGS.label == "Question settings"
        assert QuestionInfo.OPTIONS.label == "Answer options"


def _expand(query):
    """Flatten a query_dict (with a list-valued ``show``) into (key, value) pairs for a MultiDict."""
    for key, value in query.items():
        if isinstance(value, list):
            for item in value:
                yield key, item
        else:
            yield key, value


class TestDescribeComponentValidations:
    def test_returns_interpolated_messages_for_each_validation(self):
        validations = [
            SimpleNamespace(evaluatable_expression=SimpleNamespace(message="The answer must be more than 100")),
            SimpleNamespace(evaluatable_expression=SimpleNamespace(message="The answer must be less than 1000")),
        ]
        component = SimpleNamespace(validations=validations)

        result = describe_component_validations(component, interpolate=lambda message, **kwargs: Markup(message))

        assert result == [
            Markup("The answer must be more than 100"),
            Markup("The answer must be less than 1000"),
        ]

    def test_returns_empty_list_when_no_validations(self):
        component = SimpleNamespace(validations=[])
        assert describe_component_validations(component, interpolate=lambda message, **kwargs: Markup(message)) == []
