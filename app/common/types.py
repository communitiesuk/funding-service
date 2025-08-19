from pydantic import BaseModel, Field


class MarkdownToHtmlSuccessResponse(BaseModel):
    preview_html: str | None = None
    errors: list[str] = Field(default_factory=list)


class MarkdownToHtmlUnauthorisedResponse(BaseModel):
    error: str = "Unauthorised"
