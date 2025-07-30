import abc
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


class TextSingleLineAnswer(SubmissionAnswerRootModel[str]):
    pass


class TextMultiLineAnswer(SubmissionAnswerRootModel[str]):
    pass


class IntegerAnswer(SubmissionAnswerRootModel[int]):
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


class MultipleChoiceFromListAnswer(SubmissionAnswerBaseModel):
    choices: list[ChoiceDict]

    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/multiple_choice_from_list.html"

    def get_value_for_submission(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    def get_value_for_form(self) -> list[str]:
        return [choice["key"] for choice in self.choices]

    def get_value_for_expression(self) -> list[str]:
        return [choice["key"] for choice in self.choices]

    def get_value_for_text_export(self) -> str:
        return "\n".join(choice["label"] for choice in self.choices)


AllAnswerTypes = Union[
    TextSingleLineAnswer
    | TextMultiLineAnswer
    | IntegerAnswer
    | EmailAnswer
    | UrlAnswer
    | YesNoAnswer
    | SingleChoiceFromListAnswer
    | MultipleChoiceFromListAnswer
]
