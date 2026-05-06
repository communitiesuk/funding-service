import pytest
from flask import url_for

from app.deliver_grant_funding.forms import PreviewGuidanceForm


class TestPreviewGuidance:
    @pytest.mark.authenticate_as("person@gmail.com")
    def test_post_unauthorised_if_not_mhclg_email_address(self, authenticated_no_role_client, factories):
        collection = factories.collection.create()

        form = PreviewGuidanceForm(markdown="")
        response = authenticated_no_role_client.post(
            url_for("deliver_grant_funding.api.preview_guidance", collection_id=collection.id), json=form.data
        )
        assert response.status_code == 401
        assert response.json["error"] == "Unauthorised"

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_success_with_mhclg_user(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant)
        form = PreviewGuidanceForm(guidance="## Heading\n\n* list item\n\n[link](https://www.gov.uk)")
        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_guidance", collection_id=collection.id),
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

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_interpolates_guidance(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Collection")
        q = factories.question.create(form__collection=collection, form__title="Form", name="my question name")
        form = PreviewGuidanceForm(guidance=f"Test interpolation: (({q.safe_qid}))")
        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_guidance", collection_id=collection.id),
            json=form.data,
        )
        assert response.status_code == 200
        assert response.json["guidance_html"] == (
            "<p class='govuk-body'>Test interpolation: "
            '<span class="app-context-aware-editor--valid-reference">((Collection → Form → my question name))</span>'
            "</p>\n"
        )

    def test_post_with_script_tags_are_escaped(self, authenticated_grant_member_client, factories):
        collection = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Collection")
        q = factories.question.create(form__collection=collection, form__title="Form", name="my question name")
        form = PreviewGuidanceForm(guidance=f"<script>alert('bad user input')</script>: (({q.safe_qid}))")
        response = authenticated_grant_member_client.post(
            url_for("deliver_grant_funding.api.preview_guidance", collection_id=collection.id),
            json=form.data,
        )
        assert response.status_code == 200
        assert response.json["guidance_html"] == (
            "&lt;script&gt;alert(&#x27;bad user input&#x27;)&lt;/script&gt;: "
            '<span class="app-context-aware-editor--valid-reference">((Collection → Form → my question name))</span>\n'
        )
