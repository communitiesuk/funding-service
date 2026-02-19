from pydantic import BaseModel, Field


class PreviewGuidanceBadRequestResponse(BaseModel):
    errors: list[str] = Field(default_factory=list)


class PreviewGuidanceSuccessResponse(BaseModel):
    # `str` here is actually a `Markup` object, as preview guidance calls `interpolate` with
    # `with_interpolation_highlighting=True`, which wraps any resolved data references in a highlighting span.
    guidance_html: str | None = None
    errors: list[str] = Field(default_factory=list)


class PreviewGuidanceUnauthorisedResponse(BaseModel):
    error: str = "Unauthorised"


class PreviewQuestionSuccessResponse(BaseModel):
    question_html: str | None = None
    errors: list[str] = Field(default_factory=list)


class PreviewQuestionBadRequestResponse(BaseModel):
    errors: list[str] = Field(default_factory=list)
