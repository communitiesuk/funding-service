import abc
from datetime import date, datetime
from typing import Any, Protocol, TypedDict, Union, cast

from pydantic import BaseModel, RootModel

NOT_ASKED = "NOT_ASKED"
NOT_ANSWERED = "NOT_ANSWERED"


class ChoiceDict(TypedDict):
    key: str
    label: str


class SubmissionAnswerProtocol(Protocol):
    # All classes in this module must implement this protocol. For now, we can't tie this up to type hinting nicely -
    # waiting on Python to support type intersections so that we say that all answers must be BaseModel &
    # AnswerProtocol. So for now - developers will need to manually keep this lined up.

    _render_answer_template: str

    def get_value_for_submission(self) -> Any: ...
    def get_value_for_form(self) -> Any: ...
    def get_value_for_expression(self) -> Any: ...
    def get_value_for_text_export(self) -> str: ...


class SubmissionAnswerRootModel[T](RootModel[T]):
    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/root.html"

    def get_value_for_submission(self) -> T:
        return cast(T, self.model_dump(mode="json"))

    def get_value_for_form(self) -> T:
        return self.root

    def get_value_for_expression(self) -> T:
        return self.root

    def get_value_for_text_export(self) -> str:
        return str(self.root)

    def get_value_for_json_export(self) -> T:
        return cast(T, self.model_dump(mode="json"))


class SubmissionAnswerBaseModel(BaseModel, abc.ABC):
    @property
    @abc.abstractmethod
    def _render_answer_template(self) -> str: ...
    @abc.abstractmethod
    def get_value_for_submission(self) -> Any: ...
    @abc.abstractmethod
    def get_value_for_form(self) -> Any: ...
    @abc.abstractmethod
    def get_value_for_expression(self) -> Any: ...
    @abc.abstractmethod
    def get_value_for_text_export(self) -> str: ...
    @abc.abstractmethod
    def get_value_for_json_export(self) -> Any: ...


class TextSingleLineAnswer(SubmissionAnswerRootModel[str]):
    pass


class TextMultiLineAnswer(SubmissionAnswerRootModel[str]):
    pass


class EmailAnswer(SubmissionAnswerRootModel[str]):
    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/email.html"


class UrlAnswer(SubmissionAnswerRootModel[str]):
    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/url.html"


class YesNoAnswer(SubmissionAnswerRootModel[bool]):
    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/yes_no.html"

    def get_value_for_submission(self) -> bool:
        return cast(bool, self.model_dump(mode="json"))

    def get_value_for_text_export(self) -> str:
        return "Yes" if self.root else "No"

    def get_value_for_json_export(self) -> bool:
        return cast(bool, self.model_dump(mode="json"))


class IntegerAnswer(SubmissionAnswerBaseModel):
    value: int
    prefix: str | None = None
    suffix: str | None = None

    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/integer.html"

    def get_value_for_submission(self) -> dict[str, Any]:
        return self.model_dump(mode="json", exclude_none=True)

    def get_value_for_form(self) -> int:
        return self.value

    def get_value_for_expression(self) -> int:
        return self.value

    def get_value_for_text_export(self) -> str:
        return f"{self.prefix or ''}{self.value:,d}{self.suffix or ''}"

    def get_value_for_json_export(self) -> dict[str, Any]:
        data: dict[str, str | int] = {"value": self.value}

        if self.prefix:
            data["prefix"] = self.prefix
        if self.suffix:
            data["suffix"] = self.suffix

        return data


class SingleChoiceFromListAnswer(SubmissionAnswerBaseModel):
    key: str
    label: str

    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/single_choice_from_list.html"

    def get_value_for_submission(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def get_value_for_form(self) -> str:
        return self.key

    def get_value_for_expression(self) -> str:
        return self.key

    def get_value_for_text_export(self) -> str:
        return self.label

    def get_value_for_json_export(self) -> ChoiceDict:
        return {"key": self.key, "label": self.label}


class MultipleChoiceFromListAnswer(SubmissionAnswerBaseModel):
    choices: list[ChoiceDict]

    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/multiple_choice_from_list.html"

    def get_value_for_submission(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def get_value_for_form(self) -> list[str]:
        return [choice["key"] for choice in self.choices]

    def get_value_for_expression(self) -> set[str]:
        return {choice["key"] for choice in self.choices}

    def get_value_for_text_export(self) -> str:
        return "\n".join(choice["label"] for choice in self.choices)

    def get_value_for_json_export(self) -> list[ChoiceDict]:
        return self.choices


class DateAnswer(SubmissionAnswerBaseModel):
    date_as_date: date
    date_as_entered: list[str]

    _valid_formats = ["%d %m %Y", "%d %b %Y", "%d %B %Y"]

    def _parse_date_from_date_as_entered(self) -> date | None:
        for fmt in self._valid_formats:
            try:
                return datetime.strptime(" ".join(self.date_as_entered), fmt).date()
            except ValueError:
                continue
        return None

    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/date.html"

    def get_value_for_submission(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def get_value_for_form(self) -> date:
        return self._parse_date_from_date_as_entered()

    def get_value_for_expression(self) -> date:
        return self._parse_date_from_date_as_entered()

    def get_value_for_text_export(self) -> str:
        # TODO export in a format for excel
        return self.date_as_date.strftime("%d %m %Y")

    def get_value_for_json_export(self) -> str:
        # TODO export in iso format
        return self.date_as_date.strftime("%d %m %Y")


AllAnswerTypes = Union[
    TextSingleLineAnswer
    | TextMultiLineAnswer
    | IntegerAnswer
    | EmailAnswer
    | UrlAnswer
    | YesNoAnswer
    | SingleChoiceFromListAnswer
    | MultipleChoiceFromListAnswer
    | DateAnswer
]
