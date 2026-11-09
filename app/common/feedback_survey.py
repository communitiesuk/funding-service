from typing import TypedDict
from urllib.parse import quote, urlencode, urljoin

from app.common.data.models import Collection, GrantRecipient


class FeedbackSurveyPrefillConfig(TypedDict):
    # Form ID
    form_id: str

    # Form fields to prefill
    grant_field: str
    organisation_field: str
    collection_field: str


def prefill_survey_link(
    feedback_url: str,
    prefill_config: FeedbackSurveyPrefillConfig,
    grant_recipient: GrantRecipient,
    collection: Collection,
) -> str:
    query_params = {
        "id": prefill_config["form_id"],
        prefill_config["grant_field"]: grant_recipient.grant.name,
        prefill_config["organisation_field"]: grant_recipient.organisation.name,
        prefill_config["collection_field"]: collection.name,
    }

    return urljoin(feedback_url, f"?{urlencode(query_params, quote_via=quote)}")
