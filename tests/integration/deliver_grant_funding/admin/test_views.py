import pytest
from bs4 import BeautifulSoup

from app.common.data.types import GrantStatusEnum, RoleEnum
from tests.utils import get_h1_text, get_h2_text, page_has_error, page_has_flash


class TestFlaskAdminAccess:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 403),
        ],
    )
    def test_admin_index_denied_for_non_platform_admin(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/")
        assert response.status_code == expected_code

    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 403),
        ],
    )
    def test_admin_user_list_denied_for_non_platform_admin(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/user/")
        assert response.status_code == expected_code

    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 403),
        ],
    )
    def test_admin_user_detail_denied_for_non_platform_admin(
        self, client_fixture, expected_code, request, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        user = factories.user.create()

        response = client.get(f"/deliver/admin/user/details/?id={user.id}", follow_redirects=True)
        assert response.status_code == expected_code


class TestReportingLifecycleSelectGrant:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 403),
        ],
    )
    def test_select_grant_permissions(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/reporting-lifecycle/")
        assert response.status_code == expected_code

    def test_get_select_grant_page(self, authenticated_platform_admin_client, factories, db_session):
        draft_grant = factories.grant.create(name="Test Draft Grant", status=GrantStatusEnum.DRAFT)
        live_grant = factories.grant.create(name="Test Live Grant", status=GrantStatusEnum.LIVE)

        response = authenticated_platform_admin_client.get("/deliver/admin/reporting-lifecycle/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Reporting lifecycle"

        select_element = soup.find("select", {"id": "grant_id"})
        assert select_element is not None

        options = select_element.find_all("option")
        option_texts = [opt.get_text(strip=True) for opt in options]
        option_values = [opt.get("value") for opt in options]

        assert "Test Draft Grant" in option_texts
        assert "Test Live Grant" in option_texts
        assert str(draft_grant.id) in option_values
        assert str(live_grant.id) in option_values

    def test_post_with_valid_grant_id_redirects_to_tasklist(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()

        response = authenticated_platform_admin_client.post(
            "/deliver/admin/reporting-lifecycle/",
            data={"grant_id": str(grant.id), "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/reporting-lifecycle/{grant.id}"

    def test_post_without_grant_id_shows_validation_error(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        factories.grant.create()

        response = authenticated_platform_admin_client.post(
            "/deliver/admin/reporting-lifecycle/",
            data={"grant_id": "", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h2_text(soup) == "There is a problem"
        assert page_has_error(soup, "Select a grant to view its reporting lifecycle")


class TestReportingLifecycleTasklist:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 403),
        ],
    )
    def test_tasklist_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}")
        assert response.status_code == expected_code

    def test_get_tasklist_with_draft_grant_shows_to_do_status(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Draft Grant")

        response = authenticated_platform_admin_client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == f"{grant.name} Reporting lifecycle"

        task_list = soup.find("ul", {"class": "govuk-task-list"})
        assert task_list is not None

        task_items = task_list.find_all("li", {"class": "govuk-task-list__item"})
        assert len(task_items) == 1

        task_title = task_items[0].find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Make the grant live"
        assert f"/deliver/admin/reporting-lifecycle/{grant.id}/make-live" in task_title.get("href")

        task_status = task_items[0].find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "To do" in task_status.get_text(strip=True)
        assert "govuk-tag--grey" in task_status.get("class")

    def test_get_tasklist_with_live_grant_shows_completed_status(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Live Grant", status=GrantStatusEnum.LIVE)

        response = authenticated_platform_admin_client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == f"{grant.name} Reporting lifecycle"

        task_list = soup.find("ul", {"class": "govuk-task-list"})
        assert task_list is not None

        task_items = task_list.find_all("li", {"class": "govuk-task-list__item"})
        assert len(task_items) == 1

        task_title = task_items[0].find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert "Make the grant live" in task_title.get_text(strip=True)

        task_link = task_items[0].find("a", {"class": "govuk-link"})
        assert task_link is None

        task_status = task_items[0].find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Completed" in task_status.get_text(strip=True)
        assert "govuk-tag--green" in task_status.get("class")


class TestReportingLifecycleMakeGrantLive:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 403),
        ],
    )
    def test_confirm_page_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/make-live")
        assert response.status_code == expected_code

    def test_get_confirm_page_with_draft_grant(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")

        response = authenticated_platform_admin_client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/make-live")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test Grant Make grant live"

    def test_get_confirm_page_with_live_grant_redirects(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Already Live Grant", status=GrantStatusEnum.LIVE)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/make-live", follow_redirects=True
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Already Live Grant is already live")

    def test_post_makes_grant_live_with_enough_team_members(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.DRAFT)
        factories.user_role.create(grant=grant, role=RoleEnum.MEMBER)
        factories.user_role.create(grant=grant, role=RoleEnum.ADMIN)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/make-live",
            data={"submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/reporting-lifecycle/{grant.id}"

        db_session.refresh(grant)
        assert grant.status == GrantStatusEnum.LIVE

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Test Grant is now live")

    def test_post_fails_without_enough_team_members(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.DRAFT)
        factories.user_role.create(grant=grant, role=RoleEnum.MEMBER)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/make-live",
            data={"submit": "Make grant live"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        db_session.refresh(grant)
        assert grant.status == GrantStatusEnum.DRAFT

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "You must add at least two grant team users before making the grant live")
