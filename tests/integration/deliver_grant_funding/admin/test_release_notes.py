import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.models import ReleaseNote
from app.deliver_grant_funding.forms import PreviewGuidanceForm


class TestReleaseNotePreviewMarkdownAccess:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 200),
            ("authenticated_platform_data_analyst_client", 403),
            ("authenticated_platform_member_client", 403),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_endpoint_access(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        form = PreviewGuidanceForm(guidance="some markdown")
        response = client.post(url_for("release_note.preview_markdown"), json=form.data)
        assert response.status_code == expected_code


class TestReleaseNotePreviewMarkdown:
    def test_post_returns_rendered_markdown(self, authenticated_platform_admin_client):
        form = PreviewGuidanceForm(guidance="## Heading\n\n* list item\n\n[link](https://www.gov.uk)")
        response = authenticated_platform_admin_client.post(url_for("release_note.preview_markdown"), json=form.data)
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

    def test_post_with_script_tags_are_escaped(self, authenticated_platform_admin_client):
        form = PreviewGuidanceForm(guidance="<script>alert('bad user input')</script>")
        response = authenticated_platform_admin_client.post(url_for("release_note.preview_markdown"), json=form.data)
        assert response.status_code == 200
        assert "<script>" not in response.json["guidance_html"]
        assert "&lt;script&gt;" in response.json["guidance_html"]


class TestReleaseNoteCreateEditPages:
    def _assert_markdown_editor_present(self, soup):
        wrapper = soup.select_one('[data-module="ajax-markdown-preview"]')
        assert wrapper is not None
        assert wrapper["data-ajax-markdown-endpoint"] == url_for("release_note.preview_markdown")

        textarea = wrapper.select_one("textarea[name=content]")
        assert textarea is not None
        assert textarea.has_attr("data-ajax-markdown-source")
        assert textarea.has_attr("data-markdown-toolbar")

        assert wrapper.select_one("[data-ajax-markdown-target]") is not None
        assert wrapper.select_one("h2[data-preview-title-target]") is not None
        assert soup.select_one("input[name=title][data-preview-title-source]") is not None
        assert soup.select_one("input[name=csrf_token]") is not None

    def test_create_page_has_markdown_editor(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get(url_for("release_note.create_view"))
        assert response.status_code == 200
        self._assert_markdown_editor_present(BeautifulSoup(response.data, "html.parser"))

    def test_edit_page_has_markdown_editor_and_existing_content(self, authenticated_platform_admin_client, factories):
        release_note = factories.release_note.create(title="July release", content="## Existing content")
        response = authenticated_platform_admin_client.get(url_for("release_note.edit_view", id=release_note.id))
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        self._assert_markdown_editor_present(soup)

        assert soup.select_one("textarea[name=content]").text.strip() == "## Existing content"
        preview_title = soup.select_one("h2[data-preview-title-target]")
        assert preview_title.text.strip() == "July release"
        assert not preview_title.has_attr("hidden")
        preview_area = soup.select_one("[data-ajax-markdown-target]")
        assert preview_area.select_one("h2") is not None
        assert preview_area.select_one("h2").text == "Existing content"

    def test_create_page_hides_empty_preview_title(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get(url_for("release_note.create_view"))
        soup = BeautifulSoup(response.data, "html.parser")
        assert soup.select_one("h2[data-preview-title-target]").has_attr("hidden")

    def test_create_saves_release_note(self, authenticated_platform_admin_client, db_session):
        response = authenticated_platform_admin_client.post(
            url_for("release_note.create_view"),
            data={
                "title": "A new release note",
                "content": "## Some markdown content",
                "release_date": ["20", "07", "2026"],
            },
        )
        assert response.status_code == 302

        release_note = db_session.query(ReleaseNote).one()
        assert release_note.title == "A new release note"
        assert release_note.content == "## Some markdown content"
        assert release_note.is_published is False
