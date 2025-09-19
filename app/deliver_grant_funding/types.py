from pydantic import BaseModel, Field


class PreviewGuidanceBadRequestResponse(BaseModel):
    errors: list[str] = Field(default_factory=list)


class PreviewGuidanceSuccessResponse(BaseModel):
    guidance_html: str | None = None
    errors: list[str] = Field(default_factory=list)


class PreviewGuidanceUnauthorisedResponse(BaseModel):
    error: str = "Unauthorised"
