import datetime

import pytest
from bs4 import BeautifulSoup

from app.common.data.interfaces.user import get_current_user
from app.common.data.types import RoleEnum
from tests.utils import AnyStringMatching, get_h1_text


class TestListGrants:
    def test_list_grants_as_admin(
        self, app, authenticated_platform_admin_client, factories, templates_rendered, track_sql_queries
    ):
        factories.grant.create_batch(5)
        with track_sql_queries() as queries:
            result = authenticated_platform_admin_client.get("/deliver/grants")
        assert result.status_code == 200
        assert len(templates_rendered.get("deliver_grant_funding.list_grants").context.get("grants")) == 6
        soup = BeautifulSoup(result.data, "html.parser")
        headers = soup.find_all("th")
        header_texts = [th.get_text(strip=True) for th in headers]
        expected_headers = ["Grant", "GGIS number", "Status"]
        for expected in expected_headers:
            assert expected in header_texts, f"Header '{expected}' not found in table"
        assert get_h1_text(soup) == "Grants"
        assert len(queries) == 3  # 1) select user, 2) select user_role, 3) select grants

    def test_list_grants_as_member_with_single_grant(
        self, app, authenticated_grant_member_client, factories, templates_rendered, track_sql_queries
    ):
        with track_sql_queries() as queries:
            result = authenticated_grant_member_client.get("/deliver/grants", follow_redirects=False)
        assert result.status_code == 302
        BeautifulSoup(result.data, "html.parser")

        assert len(queries) == 4  # 1) select user, 2) select user_role, 3) select org, 4) select grants
        assert result.location == AnyStringMatching(r"/deliver/.+/index")

    def test_list_grants_as_member_with_multiple_grants(
        self, app, authenticated_grant_member_client, factories, templates_rendered, track_sql_queries
    ):
        grants = factories.grant.create_batch(5)
        user = get_current_user()
        for grant in grants:
            factories.user_role.create(user_id=user.id, user=user, permissions=[RoleEnum.MEMBER], grant=grant)

        result = authenticated_grant_member_client.get("/deliver/grants")
        assert result.status_code == 200
        soup = BeautifulSoup(result.data, "html.parser")
        headers = soup.find_all("th")
        header_texts = [th.get_text(strip=True) for th in headers]
        expected_headers = ["Grant", "GGIS number", "Status"]
        for expected in expected_headers:
            assert expected in header_texts, f"Header '{expected}' not found in table"
        assert get_h1_text(soup) == "Grants"

    @pytest.mark.authenticate_as("test@google.com")
    def test_list_grant_requires_mhclg_user(self, authenticated_no_role_client, factories, templates_rendered):
        response = authenticated_no_role_client.get("/deliver/grants")
        assert response.status_code == 403

    @pytest.mark.parametrize(
        "client_fixture, should_show_button",
        [
            ("authenticated_platform_admin_client", True),
            ("authenticated_org_admin_client", True),
            ("authenticated_org_member_client", True),
            ("authenticated_grant_admin_client", False),
            ("authenticated_grant_member_client", False),
        ],
    )
    def test_set_up_grant_button_visibility(self, client_fixture, should_show_button, request, factories):
        client = request.getfixturevalue(client_fixture)

        grants = factories.grant.create_batch(3)

        if "grant_admin" in client_fixture or "grant_member" in client_fixture:
            role = RoleEnum.ADMIN if "admin" in client_fixture else RoleEnum.MEMBER
            for grant in grants:
                factories.user_role.create(user=client.user, permissions=[role], grant=grant)

        response = client.get("/deliver/grants")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        button = soup.find("a", string=lambda text: text and "Set up a grant" in text)

        if should_show_button:
            assert button is not None, f"'Set up a grant' button should be visible for {client_fixture}"
        else:
            assert button is None, f"'Set up a grant' button should not be visible for {client_fixture}"

    def test_get_list_grants_filters_drafts(self, authenticated_platform_admin_client, factories):
        factories.grant.create_batch(2, status="LIVE")
        factories.grant.create_batch(2, status="ONBOARDING")
        factories.grant.create_batch(2, status="DRAFT")

        response = authenticated_platform_admin_client.get("/deliver/grants")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        active_grant_rows = soup.select("#active-grants tbody tr")
        assert len(active_grant_rows) == 4  # 2 live and 2 onboarding

        draft_grant_rows = soup.select("#draft-grants tbody tr")
        assert len(draft_grant_rows) == 3  # 3 draft as admin_client creates a grant itself


class TestLatestUpdates:
    def test_lists_published_release_notes_most_recent_first(self, authenticated_grant_member_client, factories):
        factories.release_note.create(title="Older change", release_date=datetime.date(2026, 5, 1), is_published=True)
        factories.release_note.create(title="Newest change", release_date=datetime.date(2026, 7, 1), is_published=True)
        factories.release_note.create(title="Middle change", release_date=datetime.date(2026, 6, 1), is_published=True)

        result = authenticated_grant_member_client.get("/deliver/latest-updates")

        assert result.status_code == 200
        soup = BeautifulSoup(result.data, "html.parser")
        assert get_h1_text(soup) == "Latest updates"

        page_text = soup.get_text()
        assert page_text.index("Newest change") < page_text.index("Middle change") < page_text.index("Older change")

        captions = [span.get_text(strip=True) for span in soup.select("h2 .govuk-caption-m")]
        assert captions == ["1 July 2026", "1 June 2026", "1 May 2026"]

    def test_does_not_list_unpublished_release_notes(self, authenticated_grant_member_client, factories):
        factories.release_note.create(title="Published change", is_published=True)
        factories.release_note.create(title="Unpublished change", is_published=False)

        result = authenticated_grant_member_client.get("/deliver/latest-updates")

        assert result.status_code == 200
        page_text = BeautifulSoup(result.data, "html.parser").get_text()
        assert "Published change" in page_text
        assert "Unpublished change" not in page_text

    def test_renders_release_note_content_as_markdown(self, authenticated_grant_member_client, factories):
        factories.release_note.create(
            content="A paragraph of content.\n\n- first improvement\n- second improvement",
            is_published=True,
        )

        result = authenticated_grant_member_client.get("/deliver/latest-updates")

        assert result.status_code == 200
        soup = BeautifulSoup(result.data, "html.parser")
        paragraphs = [p.get_text(strip=True) for p in soup.select("p.govuk-body")]
        assert "A paragraph of content." in paragraphs
        bullets = [li.get_text(strip=True) for li in soup.select("ul.govuk-list--bullet li")]
        assert bullets == ["first improvement", "second improvement"]

    def test_footer_links_to_release_notes(self, authenticated_platform_admin_client):
        result = authenticated_platform_admin_client.get("/deliver/grants")

        assert result.status_code == 200
        soup = BeautifulSoup(result.data, "html.parser")
        footer_link = soup.select_one("footer a[href='/deliver/latest-updates']")
        assert footer_link is not None
        assert footer_link.get_text(strip=True) == "Latest updates"

    @pytest.mark.authenticate_as("test@google.com")
    def test_release_notes_requires_mhclg_user(self, authenticated_no_role_client):
        response = authenticated_no_role_client.get("/deliver/latest-updates")
        assert response.status_code == 403
