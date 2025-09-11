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
        button = soup.find("a", string=lambda text: text and "Set up a grant" in text)
        assert button is not None, "'Set up a grant' button not found"
        headers = soup.find_all("th")
        header_texts = [th.get_text(strip=True) for th in headers]
        expected_headers = ["Grant", "GGIS number", "Email"]
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
        assert len(queries) == 3  # 1) select user, 2) select user_role, 3) select grants

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
        button = soup.find("a", string=lambda text: text and "Set up a grant" in text)
        assert button is None, "'Set up a grant' button found"
        headers = soup.find_all("th")
        header_texts = [th.get_text(strip=True) for th in headers]
        expected_headers = ["Grant", "GGIS number", "Email"]
        for expected in expected_headers:
            assert expected in header_texts, f"Header '{expected}' not found in table"
        assert get_h1_text(soup) == "Grants"

    @pytest.mark.authenticate_as("test@google.com")
    def test_list_grant_requires_mhclg_user(self, authenticated_no_role_client, factories, templates_rendered):
        response = authenticated_no_role_client.get("/deliver/grants")
        assert response.status_code == 403
