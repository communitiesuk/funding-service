import pytest
from flask import url_for

from app.deliver_grant_funding.forms import PreviewGuidanceForm


class TestPreviewGuidance:
    @pytest.mark.authenticate_as("person@gmail.com")
    def test_post_unauthorised_if_not_mhclg_email_address(self, authenticated_no_role_client, factories):
        grant = factories.grant.create()

        form = PreviewGuidanceForm(markdown="")
        response = authenticated_no_role_client.post(
            url_for("deliver_grant_funding.api.preview_guidance", grant_id=grant.id), json=form.data
        )
        assert response.status_code == 401
        assert response.json["error"] == "Unauthorised"

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_success_with_mhclg_user(self, authenticated_grant_member_client):
        form = PreviewGuidanceForm(guidance="## Heading\n\n* list item\n\n[link](https://www.gov.uk)")
        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_guidance", grant_id=authenticated_grant_member_client.grant.id),
            json=form.data,
        )
        assert response.status_code == 200
        assert response.json["guidance_html"] == (
            '<h2 class="govuk-heading-m">Heading</h2>\n'
            '<ul class="govuk-list govuk-list--bullet">\n'
            "<li>list item</li>\n"
            "</ul>\n"
            "<p class='govuk-body'>"
            '<a href="https://www.gov.uk" class="govuk-link govuk-link--no-visited-state">link</a>'
            "</p>\n"
        )
