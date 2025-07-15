from typing import Any, Protocol, cast

from pydantic import BaseModel, RootModel


class SubmissionAnswerProtocol(Protocol):
    # We have to underscore this because of the composition with pydantic's base model meta class
    # pydantic models don't let you have non-underscores properties defined outright on classes.
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


TextSingleLine = SubmissionAnswerRootModel[str]
TextMultiLine = SubmissionAnswerRootModel[str]
Integer = SubmissionAnswerRootModel[int]


class YesNo(SubmissionAnswerRootModel[bool]):
    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/yes_no.html"

    def get_value_for_submission(self) -> bool:
        return cast(bool, self.model_dump(mode="json"))

    def get_value_for_form(self) -> bool:
        return self.root

    def get_value_for_expression(self) -> bool:
        return self.root

    def get_value_for_text_export(self) -> str:
        return "Yes" if self.root else "No"


class SingleChoiceFromList(BaseModel):
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
