import datetime

import pytest
from bs4 import BeautifulSoup

from app.common.data.interfaces.organisations import get_organisation_count
from app.common.data.models import Organisation
from app.common.data.types import GrantStatusEnum, OrganisationStatus, OrganisationType, RoleEnum
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

    def test_get_tasklist_shows_organisations_task(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.organisation.create(name="Org 2", can_manage_grants=False)
        factories.organisation.create(name="Org 3", can_manage_grants=False)

        response = authenticated_platform_admin_client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        task_list = soup.find("ul", {"class": "govuk-task-list"})
        assert task_list is not None

        task_items = task_list.find_all("li", {"class": "govuk-task-list__item"})
        assert len(task_items) == 3

        organisations_task = task_items[0]
        task_title = organisations_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set up organisations"
        assert f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-organisations" in task_title.get("href")

        task_status = organisations_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "3 organisations" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

    def test_get_tasklist_shows_correct_organisation_count_singular(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        factories.organisation.create(name="Org 1", can_manage_grants=False)

        response = authenticated_platform_admin_client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        task_list = soup.find("ul", {"class": "govuk-task-list"})
        task_items = task_list.find_all("li", {"class": "govuk-task-list__item"})

        organisations_task = task_items[0]
        task_status = organisations_task.find("strong", {"class": "govuk-tag"})
        assert "1 organisation" in task_status.get_text(strip=True)

    def test_get_tasklist_excludes_grant_managing_organisations_from_count(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        factories.organisation.create(name="Regular Org", can_manage_grants=False)

        response = authenticated_platform_admin_client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        task_list = soup.find("ul", {"class": "govuk-task-list"})
        task_items = task_list.find_all("li", {"class": "govuk-task-list__item"})

        organisations_task = task_items[0]
        task_status = organisations_task.find("strong", {"class": "govuk-tag"})
        assert "1 organisation" in task_status.get_text(strip=True)

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
        assert len(task_items) == 3

        task_title = task_items[1].find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Make the grant live"
        assert f"/deliver/admin/reporting-lifecycle/{grant.id}/make-live" in task_title.get("href")

        task_status = task_items[1].find("strong", {"class": "govuk-tag"})
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
        assert len(task_items) == 3

        task_title = task_items[1].find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert "Make the grant live" in task_title.get_text(strip=True)

        task_link = task_items[1].find("a", {"class": "govuk-link"})
        assert task_link is None

        task_status = task_items[1].find("strong", {"class": "govuk-tag"})
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


class TestManageOrganisations:
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
    def test_manage_organisations_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-organisations")
        assert response.status_code == expected_code

    def test_get_manage_organisations_page(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-organisations"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Set up organisations"

        textarea = soup.find("textarea", {"id": "organisations_data"})
        assert textarea is not None
        assert "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n" in textarea.get_text()

    def test_post_creates_new_organisations(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        initial_count = get_organisation_count()

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tTest Department\tCentral Government\t01/01/2020\t\n"
            "E06000001\tTest Council\tUnitary Authority\t15/06/2021\t"
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Created or updated 2 organisations.")

        assert get_organisation_count() == initial_count + 2

        org1 = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert org1.name == "Test Department"
        assert org1.type == OrganisationType.CENTRAL_GOVERNMENT
        assert org1.status == OrganisationStatus.ACTIVE
        assert org1.active_date == datetime.date(2020, 1, 1)
        assert org1.retirement_date is None

        org2 = db_session.query(Organisation).filter_by(external_id="E06000001").one()
        assert org2.name == "Test Council"
        assert org2.type == OrganisationType.UNITARY_AUTHORITY
        assert org2.status == OrganisationStatus.ACTIVE
        assert org2.active_date == datetime.date(2021, 6, 15)
        assert org2.retirement_date is None

    def test_post_updates_existing_organisations(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        factories.organisation.create(
            external_id="GB-GOV-123",
            name="Old Name",
            type=OrganisationType.CENTRAL_GOVERNMENT,
            can_manage_grants=False,
        )
        initial_count = get_organisation_count()

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tUpdated Name\tCentral Government\t01/01/2020\t"
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Created or updated 1 organisations.")

        assert get_organisation_count() == initial_count

        org = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert org.name == "Updated Name"

    def test_post_creates_retired_organisation(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tRetired Department\tCentral Government\t01/01/2020\t31/12/2023"
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        org = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert org.status == OrganisationStatus.RETIRED
        assert org.retirement_date == datetime.date(2023, 12, 31)

    def test_post_with_invalid_header_shows_error(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()

        tsv_data = "Wrong Header\nGB-GOV-123\tTest Department\tCentral Government\t01/01/2020\t"

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "The header row must be exactly: organisation-id\torganisation-name\ttype\tactive-date\tretirement-date",
        )

    def test_post_with_invalid_organisation_type_shows_error(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tTest Department\tInvalid Type\t01/01/2020\t"
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "The tab-separated data is not valid:")

    def test_post_with_invalid_date_format_shows_error(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tTest Department\tCentral Government\t2020-01-01\t"
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "The tab-separated data is not valid:")


class TestManageGrantRecipients:
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
    def test_manage_grant_recipients_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-grant-recipients")
        assert response.status_code == expected_code

    def test_get_manage_grant_recipients_page(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.organisation.create(name="Org 2", can_manage_grants=False)
        factories.organisation.create(name="Org 3", can_manage_grants=False)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-grant-recipients"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Set up grant recipients"

        select_element = soup.find("select", {"id": "recipients"})
        assert select_element is not None

        options = select_element.find_all("option")
        option_texts = [opt.get_text(strip=True) for opt in options]

        assert "Org 1" in option_texts
        assert "Org 2" in option_texts
        assert "Org 3" in option_texts

    def test_get_excludes_grant_managing_organisations(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        from tests.models import _get_grant_managing_organisation

        grant = factories.grant.create(name="Test Grant")
        grant_managing_org = _get_grant_managing_organisation()
        factories.organisation.create(name="Regular Org", can_manage_grants=False)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-grant-recipients"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        select_element = soup.find("select", {"id": "recipients"})
        options = select_element.find_all("option")
        option_texts = [opt.get_text(strip=True) for opt in options]

        assert grant_managing_org.name not in option_texts
        assert "Regular Org" in option_texts

    def test_get_excludes_existing_grant_recipients(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.organisation.create(name="Org 2", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org1)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-grant-recipients"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        select_element = soup.find("select", {"id": "recipients"})
        options = select_element.find_all("option")
        option_texts = [opt.get_text(strip=True) for opt in options]

        assert "Org 1" not in option_texts
        assert "Org 2" in option_texts

    def test_post_creates_grant_recipients(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Org 2", can_manage_grants=False)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-grant-recipients",
            data={"recipients": [str(org1.id), str(org2.id)], "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Created 2 grant recipients.")

        from app.common.data.interfaces.grant_recipients import get_grant_recipients

        grant_recipients = get_grant_recipients(grant)
        assert len(grant_recipients) == 2
        recipient_org_ids = {gr.organisation_id for gr in grant_recipients}
        assert org1.id in recipient_org_ids
        assert org2.id in recipient_org_ids

    def test_post_redirects_to_tasklist(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(name="Org 1", can_manage_grants=False)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-grant-recipients",
            data={"recipients": [str(org.id)], "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/reporting-lifecycle/{grant.id}"

    def test_post_without_recipients_shows_validation_error(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        factories.organisation.create(name="Org 1", can_manage_grants=False)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-grant-recipients",
            data={"recipients": [], "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "This field is required.")

    def test_get_with_no_available_organisations_shows_empty_select(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        from tests.models import _get_grant_managing_organisation

        grant = factories.grant.create(name="Test Grant")
        _get_grant_managing_organisation()

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/set-up-grant-recipients"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        select_element = soup.find("select", {"id": "recipients"})
        assert select_element is not None

        options = select_element.find_all("option")
        assert len(options) == 0
