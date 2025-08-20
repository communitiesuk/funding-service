import pytest
from flask import url_for

from app.common.forms import MarkdownToHtmlForm


class TestMarkdownToHtml:
    @pytest.mark.authenticate_as("person@gmail.com")
    def test_post_unauthorised_if_not_mhclg_email_address(self, authenticated_no_role_client):
        form = MarkdownToHtmlForm(markdown="")
        response = authenticated_no_role_client.post(url_for("common_api.markdown_to_html"), json=form.data)
        assert response.status_code == 401
        assert response.json["error"] == "Unauthorised"

    @pytest.mark.authenticate_as("person@communities.gov.uk")
    def test_post_success_with_mhclg_user(self, authenticated_no_role_client):
        form = MarkdownToHtmlForm(markdown="## Heading\n\n* list item\n\n[link](https://www.gov.uk)")
        response = authenticated_no_role_client.post(url_for("common_api.markdown_to_html"), json=form.data)
        assert response.status_code == 200
        assert response.json["preview_html"] == (
            '<h2 class="govuk-heading-m">Heading</h2>\n'
            '<ul class="govuk-list govuk-list--bullet">\n'
            "<li>list item</li>\n"
            "</ul>\n"
            "<p class='govuk-body'>"
            '<a href="https://www.gov.uk" class="govuk-link govuk-link--no-visited-state">link</a>'
            "</p>\n"
        )
