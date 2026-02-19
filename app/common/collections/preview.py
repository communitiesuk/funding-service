from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from app.common.data.types import (
    NumberTypeEnum,
    QuestionDataOptions,
    QuestionDataType,
    QuestionPresentationOptions,
)
from app.common.qid import SafeQidMixin

if TYPE_CHECKING:
    from app.common.data.models import Expression


@dataclass
class PreviewDataSourceItem:
    key: str
    label: str


@dataclass
class PreviewDataSource:
    items: list[PreviewDataSourceItem] = field(default_factory=list)


@dataclass
class PreviewQuestion(SafeQidMixin):
    """A lightweight Question-like object for preview rendering.

    Implements the interface expected by `build_question_form` and the `collection_question` template macro,
    without requiring a database record.
    """

    id: UUID = field(default_factory=uuid4)
    text: str = ""
    hint: str | None = None
    name: str = ""
    data_type: QuestionDataType = QuestionDataType.TEXT_SINGLE_LINE
    presentation_options: QuestionPresentationOptions = field(default_factory=QuestionPresentationOptions)
    data_options: QuestionDataOptions = field(default_factory=QuestionDataOptions)
    data_source: PreviewDataSource = field(default_factory=PreviewDataSource)
    guidance_heading: str | None = None
    guidance_body: str | None = None
    _validations: list["Expression"] = field(default_factory=list)

    @property
    def question_id(self) -> UUID:
        return self.id

    @property
    def is_group(self) -> bool:
        return False

    @property
    def validations(self) -> list["Expression"]:
        return self._validations

    @property
    def separate_option_if_no_items_match(self) -> bool | None:
        if self.data_type not in [QuestionDataType.RADIOS, QuestionDataType.CHECKBOXES]:
            return None
        return self.presentation_options.last_data_source_item_is_distinct_from_others

    @property
    def approximate_date(self) -> bool | None:
        if self.data_type != QuestionDataType.DATE:
            return None
        return self.presentation_options.approximate_date

    @staticmethod
    def from_form_data(
        data_type: QuestionDataType,
        text: str,
        hint: str | None = None,
        name: str | None = None,
        rows: int | None = None,
        word_limit: int | None = None,
        prefix: str | None = None,
        suffix: str | None = None,
        width: str | None = None,
        number_type: str | None = None,
        max_decimal_places: int | None = None,
        data_source_items: list[str] | None = None,
        separate_option_if_no_items_match: bool = False,
        none_of_the_above_item_text: str | None = None,
        approximate_date: bool = False,
        guidance_heading: str | None = None,
        guidance_body: str | None = None,
        validations: list["Expression"] | None = None,
        question_id: UUID | None = None,
    ) -> "PreviewQuestion":
        presentation_options = QuestionPresentationOptions()
        data_options = QuestionDataOptions()
        data_source = PreviewDataSource()

        match data_type:
            case QuestionDataType.TEXT_MULTI_LINE:
                presentation_options = QuestionPresentationOptions(
                    rows=rows,
                    word_limit=word_limit,
                )
            case QuestionDataType.NUMBER:
                presentation_options = QuestionPresentationOptions(
                    prefix=prefix or None,
                    suffix=suffix or None,
                    width=width or None,
                )
                data_options = QuestionDataOptions(
                    number_type=NumberTypeEnum(number_type) if number_type else None,
                    max_decimal_places=max_decimal_places,
                )
            case QuestionDataType.DATE:
                presentation_options = QuestionPresentationOptions(approximate_date=approximate_date)
            case QuestionDataType.RADIOS | QuestionDataType.CHECKBOXES:
                items = []
                if data_source_items:
                    for item_label in data_source_items:
                        items.append(PreviewDataSourceItem(key=item_label, label=item_label))
                    if separate_option_if_no_items_match and none_of_the_above_item_text:
                        items.append(
                            PreviewDataSourceItem(key=none_of_the_above_item_text, label=none_of_the_above_item_text)
                        )

                data_source = PreviewDataSource(items=items)
                presentation_options = QuestionPresentationOptions(
                    last_data_source_item_is_distinct_from_others=separate_option_if_no_items_match or None,
                )

        kwargs = {}
        if question_id is not None:
            kwargs["id"] = question_id

        return PreviewQuestion(
            text=text or "",
            hint=hint,
            name=name or "",
            data_type=data_type,
            presentation_options=presentation_options,
            data_options=data_options,
            data_source=data_source,
            guidance_heading=guidance_heading,
            guidance_body=guidance_body,
            _validations=validations or [],
            **kwargs,
        )


@dataclass
class PreviewRunner:
    """A lightweight runner-like object for the `collection_question` template macro."""

    component: PreviewQuestion
    question_form: object
    question_page_caption: str = ""
    question_page_heading: str | None = None
    _interpolate: object = None

    @property
    def questions(self) -> list[PreviewQuestion]:
        return [self.component]

    def interpolate(self, text: str) -> str:
        if self._interpolate and text:
            return self._interpolate(text)
        return text or ""
