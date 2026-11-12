from urllib.parse import parse_qs, urlsplit

from app.common.feedback_survey import FeedbackSurveyPrefillConfig, prefill_survey_link

PREFILL_CONFIG: FeedbackSurveyPrefillConfig = {
    "ms_form_id": "test-form-id",
    "grant_field": "r-grant",
    "organisation_field": "r-organisation",
    "collection_field": "r-collection",
}


class TestPrefillSurveyLink:
    def test_builds_link_with_form_id_and_prefilled_fields(self, factories):
        grant_recipient = factories.grant_recipient.build(grant__name="Test Grant", organisation__name="Test Org")
        collection = factories.collection.build(grant=grant_recipient.grant, name="Test Report")

        link = prefill_survey_link(
            feedback_url="https://forms.example.com/Pages/ResponsePage.aspx",
            prefill_config=PREFILL_CONFIG,
            grant_recipient=grant_recipient,
            collection=collection,
        )

        split_link = urlsplit(link)
        assert split_link.scheme == "https"
        assert split_link.netloc == "forms.example.com"
        assert split_link.path == "/Pages/ResponsePage.aspx"
        assert parse_qs(split_link.query) == {
            "id": ["test-form-id"],
            "r-grant": ["Test Grant"],
            "r-organisation": ["Test Org"],
            "r-collection": ["Test Report"],
        }

    def test_percent_encodes_names_so_they_survive_as_query_values(self, factories):
        grant_recipient = factories.grant_recipient.build(
            grant__name="Test Grant & Fund 2026", organisation__name="Test Org"
        )
        collection = factories.collection.build(grant=grant_recipient.grant, name="Q1 report: Jan–Mar")

        link = prefill_survey_link(
            feedback_url="https://forms.example.com/Pages/ResponsePage.aspx",
            prefill_config=PREFILL_CONFIG,
            grant_recipient=grant_recipient,
            collection=collection,
        )

        assert "r-grant=Test%20Grant%20%26%20Fund%202026" in link
        assert "r-collection=Q1%20report%3A%20Jan%E2%80%93Mar" in link
        assert parse_qs(urlsplit(link).query)["r-grant"] == ["Test Grant & Fund 2026"]
        assert parse_qs(urlsplit(link).query)["r-collection"] == ["Q1 report: Jan–Mar"]
