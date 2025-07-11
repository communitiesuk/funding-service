from typing import Any, Protocol

from pydantic import RootModel


class SubmissionAnswerProtocol(Protocol):
    # We have to underscore this because of the composition with pydantic's base model meta class
    # pydantic models don't let you have non-underscores properties defined outright on classes.
    _render_answer_template: str

    def get_value_for_submission(self) -> Any: ...
    def get_value_for_form(self) -> Any: ...
    def get_value_for_expression(self) -> Any: ...
    def get_value_for_text_export(self) -> Any: ...


class SubmissionAnswerRootModel[T](RootModel[T]):
    @property
    def _render_answer_template(self) -> str:
        return "common/partials/answers/root.html"

    def get_value_for_submission(self) -> T:
        return self.root

    def get_value_for_form(self) -> T:
        return self.root

    def get_value_for_expression(self) -> T:
        return self.root

    def get_value_for_text_export(self) -> T:
        return self.root


TextSingleLine = SubmissionAnswerRootModel[str]
TextMultiLine = SubmissionAnswerRootModel[str]
Integer = SubmissionAnswerRootModel[int]
