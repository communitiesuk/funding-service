import pytest
from bs4 import BeautifulSoup

from app.common.data.interfaces.user import get_current_user
from app.common.data.types import RoleEnum
from tests.utils import get_h1_text


class TestListGrants:
    def test_list_grants_as_admin(
        self, app, authenticated_platform_admin_client, factories, templates_rendered, track_sql_queries
    ):
        factories.grant.create_batch(5)
        with track_sql_queries() as queries:
            result = authenticated_platform_admin_client.get("/deliver/grants")
        assert result.status_code == 200
        assert len(templates_rendered.get("deliver_grant_funding.list_grants").context.get("grants")) == 5
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
            result = authenticated_grant_member_client.get("/deliver/grants", follow_redirects=True)
        assert result.status_code == 200
        soup = BeautifulSoup(result.data, "html.parser")

        nav_items = [item.text.strip() for item in soup.select(".govuk-service-navigation__item")]
        assert nav_items == ["Grant details", "Reports", "Grant team"]
        assert len(queries) == 4  # 1) select user, 2) select user_role, 3) select org, 4) select grants

    def test_list_grants_as_member_with_multiple_grants(
        self, app, authenticated_grant_member_client, factories, templates_rendered, track_sql_queries
    ):
        grants = factories.grant.create_batch(5)
        user = get_current_user()
        for grant in grants:
            factories.user_role.create(user_id=user.id, user=user, role=RoleEnum.MEMBER, grant=grant)

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
                factories.user_role.create(user=client.user, role=role, grant=grant)

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
        assert len(draft_grant_rows) == 2  # 2 draft
