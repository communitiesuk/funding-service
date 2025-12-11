import datetime

import pytest
from bs4 import BeautifulSoup

from app import ReportAdminEmailTypeEnum
from app.common.data.interfaces.organisations import get_organisation_count
from app.common.data.interfaces.user import get_user_by_email
from app.common.data.models import Organisation
from app.common.data.types import (
    CollectionStatusEnum,
    GrantStatusEnum,
    OrganisationModeEnum,
    OrganisationStatus,
    OrganisationType,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
)
from app.common.helpers.collections import SubmissionHelper
from tests.utils import get_h1_text, get_h2_text, page_has_error, page_has_flash


class TestFlaskAdminAccess:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
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
            ("anonymous_client", 302),
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
            ("anonymous_client", 302),
        ],
    )
    def test_admin_user_detail_denied_for_non_platform_admin(
        self, client_fixture, expected_code, request, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        user = factories.user.create()

        response = client.get(f"/deliver/admin/user/details/?id={user.id}", follow_redirects=False)
        assert response.status_code == expected_code


class TestReportingLifecycleSelectGrant:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
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

    def test_post_with_valid_grant_id_single_report_redirects_to_tasklist(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, name="Q1 Report")

        response = authenticated_platform_admin_client.post(
            "/deliver/admin/reporting-lifecycle/",
            data={"grant_id": str(grant.id), "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"

    def test_post_with_valid_grant_id_multiple_reports_redirects_to_select_report(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        factories.collection.create(grant=grant, name="Q1 Report")
        factories.collection.create(grant=grant, name="Q2 Report")

        response = authenticated_platform_admin_client.post(
            "/deliver/admin/reporting-lifecycle/",
            data={"grant_id": str(grant.id), "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/reporting-lifecycle/{grant.id}/select-report"

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


class TestReportingLifecycleSelectReport:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_select_report_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/select-report")
        assert response.status_code == expected_code

    def test_get_select_report_page(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection1 = factories.collection.create(grant=grant, name="Q1 Report")
        collection2 = factories.collection.create(grant=grant, name="Q2 Report")

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/select-report"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Select monitoring report"

        select_element = soup.find("select", {"id": "collection_id"})
        assert select_element is not None

        options = select_element.find_all("option")
        option_texts = [opt.get_text(strip=True) for opt in options]
        option_values = [opt.get("value") for opt in options]

        assert "Q1 Report" in option_texts
        assert "Q2 Report" in option_texts
        assert str(collection1.id) in option_values
        assert str(collection2.id) in option_values

    def test_post_with_valid_collection_id_redirects_to_tasklist(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, name="Q1 Report")

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/select-report",
            data={"collection_id": str(collection.id), "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"


class TestReportingLifecycleTasklist:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_tasklist_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}")
        assert response.status_code == expected_code

    def test_shows_all_tasklists(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report")
        org_1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        org_2 = factories.organisation.create(name="Org 2", can_manage_grants=False)
        _ = factories.organisation.create(name="Org 3", can_manage_grants=False)
        _ = factories.organisation.create(name="Org 4", can_manage_grants=False, mode=OrganisationModeEnum.TEST)

        factories.user_role.create(organisation=org_1, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(organisation=org_2, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        platform_task_list = soup.find("ul", {"id": "platform-tasks"})
        grant_task_list = soup.find("ul", {"id": "grant-tasks"})
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        assert platform_task_list is not None
        assert grant_task_list is not None
        assert report_task_list is not None

        platform_task_items = platform_task_list.find_all("li", {"class": "govuk-task-list__item"})
        grant_task_items = grant_task_list.find_all("li", {"class": "govuk-task-list__item"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})
        assert len(platform_task_items) == 3
        assert len(grant_task_items) == 5
        assert len(report_task_items) == 6

        # TODO: update for testing task list

        organisations_task = platform_task_items[0]
        task_title = organisations_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set up organisations"
        assert f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-organisations" in task_title.get(
            "href"
        )

        task_status = organisations_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "3 organisations" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        test_organisations_task = platform_task_items[1]
        task_title = test_organisations_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set up test organisations"
        assert (
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-test-organisations"
            in task_title.get("href")
        )

        task_status = test_organisations_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "1 test organisation" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        certifiers_task = platform_task_items[2]
        task_title = certifiers_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set up global certifiers"
        assert (
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers"
            in task_title.get("href")
        )

        task_status = certifiers_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "2 certifiers" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        mark_grant_as_onboarding_task = grant_task_items[0]
        task_title = mark_grant_as_onboarding_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Mark as onboarding with Funding Service"
        assert f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/mark-as-onboarding" in task_title.get(
            "href"
        )

        make_grant_live_task = grant_task_items[1]
        task_title = make_grant_live_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Make the grant live"
        assert f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-live" in task_title.get("href")

        task_status = make_grant_live_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "To do" in task_status.get_text(strip=True)
        assert "govuk-tag--grey" in task_status.get("class")

        set_up_grant_recipients_task = grant_task_items[2]
        task_title = set_up_grant_recipients_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set up grant recipients"
        assert (
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients"
            in task_title.get("href")
        )

        task_status = set_up_grant_recipients_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "0 grant recipients" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        set_up_grant_recipient_data_providers_task = grant_task_items[3]
        task_title = set_up_grant_recipient_data_providers_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set up grant recipient data providers"
        assert (
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers"
            in task_title.get("href")
        )

        task_status = set_up_grant_recipient_data_providers_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "0 data providers" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        override_grant_certifiers_task = grant_task_items[4]
        task_title = override_grant_certifiers_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Override certifiers for this grant"
        assert (
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers"
            in task_title.get("href")
        )

        task_status = override_grant_certifiers_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "0 overrides" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        set_reporting_dates_task = report_task_items[0]
        task_title = set_reporting_dates_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set reporting dates"
        assert f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-dates" in task_title.get("href")

        task_status = set_reporting_dates_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "To do" in task_status.get_text(strip=True)
        assert "govuk-tag--grey" in task_status.get("class")

        set_submission_dates_task = report_task_items[1]
        task_title = set_submission_dates_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set submission dates"
        assert f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-dates" in task_title.get("href")

        task_status = set_submission_dates_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "To do" in task_status.get_text(strip=True)
        assert "govuk-tag--grey" in task_status.get("class")

        schedule_report_task = report_task_items[2]
        task_title = schedule_report_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Sign off and lock report"

        task_status = schedule_report_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        make_report_live_task = report_task_items[3]
        task_title = make_report_live_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Open the report for submissions"

        task_status = make_report_live_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        send_emails_task = report_task_items[4]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send emails to data providers"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

    def test_get_tasklist_shows_correct_organisation_count_singular(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report")
        factories.organisation.create(name="Org 1", can_manage_grants=False)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
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
        collection = factories.collection.create(grant=grant, name="Q1 Report")
        factories.organisation.create(name="Regular Org", can_manage_grants=False)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        task_list = soup.find("ul", {"class": "govuk-task-list"})
        task_items = task_list.find_all("li", {"class": "govuk-task-list__item"})

        organisations_task = task_items[0]
        task_status = organisations_task.find("strong", {"class": "govuk-tag"})
        assert "1 organisation" in task_status.get_text(strip=True)

    def test_get_tasklist_with_live_grant_shows_completed_status(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Live Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(grant=grant, name="Q1 Report")

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        grant_task_list = soup.find("ul", {"id": "grant-tasks"})
        task_items = grant_task_list.find_all("li", {"class": "govuk-task-list__item"})
        mark_as_onboarding_task = task_items[0]
        make_grant_live_task = task_items[1]

        task_title = make_grant_live_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert "Make the grant live" in task_title.get_text(strip=True)

        task_link = make_grant_live_task.find("a", {"class": "govuk-link"})
        assert task_link is None

        task_status = make_grant_live_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Completed" in task_status.get_text(strip=True)
        assert "govuk-tag--green" in task_status.get("class")

        task_status = mark_as_onboarding_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Completed" in task_status.get_text(strip=True)
        assert "govuk-tag--green" in task_status.get("class")

    def test_get_tasklist_with_dates_set(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Draft Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            reporting_period_start_date=datetime.date(2025, 1, 1),
            reporting_period_end_date=datetime.date(2025, 4, 1),
            submission_period_start_date=datetime.date(2025, 4, 1),
            submission_period_end_date=datetime.date(2025, 4, 30),
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        task_list = soup.find("ul", {"class": "govuk-task-list"})
        assert task_list is not None

        report_task_list = soup.find("ul", {"id": "report-tasks"})
        task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        task_title = task_items[0].find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert "Set reporting dates" in task_title.get_text(strip=True)
        assert "Wednesday 1 January 2025 to Tuesday 1 April 2025" in task_title.get_text(strip=True)

        task_status = task_items[0].find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Completed" in task_status.get_text(strip=True)
        assert "govuk-tag--green" in task_status.get("class")

        task_title = task_items[1].find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert "Set submission dates" in task_title.get_text(strip=True)
        assert "Tuesday 1 April 2025 to Wednesday 30 April 2025" in task_title.get_text(strip=True)

        task_status = task_items[1].find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Completed" in task_status.get_text(strip=True)
        assert "govuk-tag--green" in task_status.get("class")

    @pytest.mark.parametrize(
        "collection_status",
        [
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.SCHEDULED,
        ],
    )
    def test_send_emails_task_cannot_start_yet_when_not_open(
        self, authenticated_platform_admin_client, factories, db_session, collection_status
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report", status=collection_status)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_emails_task = report_task_items[4]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send emails to data providers"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        link = send_emails_task.find("a", {"class": "govuk-link"})
        assert link is None

    def test_send_emails_task_do_once_when_open(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report", status=CollectionStatusEnum.OPEN)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_emails_task = report_task_items[4]
        task_title = send_emails_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send emails to data providers"
        assert (
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/report_open_notification"
            in task_title.get("href")
        )

        task_status = send_emails_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Do once" in task_status.get_text(strip=True)
        assert "govuk-tag--orange" in task_status.get("class")

    @pytest.mark.parametrize(
        "collection_status",
        [
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.SCHEDULED,
        ],
    )
    def test_send_deadline_reminder_mails_task_cannot_start_yet_when_not_open(
        self, authenticated_platform_admin_client, factories, db_session, collection_status
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report", status=collection_status)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_emails_task = report_task_items[5]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send deadline reminder emails to data providers"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        link = send_emails_task.find("a", {"class": "govuk-link"})
        assert link is None

    def test_send_deadline_reminder_emails_task_do_once_when_open(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report", status=CollectionStatusEnum.OPEN)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_emails_task = report_task_items[5]
        task_title = send_emails_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send deadline reminder emails to data providers"
        assert (
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/deadline_reminder"
            in task_title.get("href")
        )

        task_status = send_emails_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Do once" in task_status.get_text(strip=True)
        assert "govuk-tag--orange" in task_status.get("class")


class TestSendEmailsToRecipients:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_send_emails_to_recipients_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            submission_period_end_date=datetime.date(2025, 10, 1),
        )

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{ReportAdminEmailTypeEnum.REPORT_OPEN_NOTIFICATION.value}"
        )
        assert response.status_code == expected_code
        response = client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{ReportAdminEmailTypeEnum.DEADLINE_REMINDER.value}"
        )
        assert response.status_code == expected_code

    def test_send_emails_to_recipients_deadline_reminder_report_not_open(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.DRAFT,
            submission_period_end_date=datetime.date(2025, 10, 1),
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{ReportAdminEmailTypeEnum.DEADLINE_REMINDER.value}"
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "email_type, expected_heading, template_id",
        [
            (
                ReportAdminEmailTypeEnum.REPORT_OPEN_NOTIFICATION.value,
                "Send emails to data providers",
                "4fc8d831-e241-4648-a8d3-04fb1bd9193e",
            ),
            (
                ReportAdminEmailTypeEnum.DEADLINE_REMINDER.value,
                "Send deadline reminder emails",
                "6e482561-e1dc-4d4d-8a9e-3b5ad8add968",
            ),
        ],
    )
    def test_send_emails_to_recipients_page_content(
        self, authenticated_platform_admin_client, factories, db_session, email_type, expected_heading, template_id
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.OPEN,
            submission_period_end_date=datetime.date(2025, 10, 1),
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{email_type}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        h1 = soup.find("h1", {"class": "govuk-heading-l"})
        assert h1 is not None
        assert expected_heading in h1.get_text(strip=True)

        caption = soup.find("span", {"class": "govuk-caption-l"})
        assert caption is not None
        assert "Test Grant - Q1 Report" in caption.get_text(strip=True)

        notify_link = soup.find("a", href=lambda x: x and "notifications.service.gov.uk" in x)
        assert notify_link is not None
        assert template_id in notify_link.get("href")

        download_button = soup.find("a", {"class": "govuk-button"})
        assert download_button is not None
        assert "Download CSV" in download_button.get_text(strip=True)
        assert (
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{email_type}"
            in download_button.get("href")
        )

    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_download_csv_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            reporting_period_start_date=datetime.date(2025, 1, 1),
            reporting_period_end_date=datetime.date(2025, 3, 31),
            submission_period_start_date=datetime.date(2025, 4, 1),
            submission_period_end_date=datetime.date(2025, 4, 30),
        )

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{ReportAdminEmailTypeEnum.REPORT_OPEN_NOTIFICATION.value}"
        )
        assert response.status_code == expected_code
        response = client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{ReportAdminEmailTypeEnum.DEADLINE_REMINDER.value}"
        )
        assert response.status_code == expected_code

    def test_download_csv_format_and_content_report_open(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        other_grant = factories.grant.create(name="Other Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.OPEN,
            reporting_period_start_date=datetime.date(2025, 1, 1),
            reporting_period_end_date=datetime.date(2025, 3, 31),
            submission_period_start_date=datetime.date(2025, 4, 1),
            submission_period_end_date=datetime.date(2025, 4, 30),
        )

        org_1 = factories.organisation.create(name="Organisation 1", can_manage_grants=False)
        org_2 = factories.organisation.create(name="Organisation 2", can_manage_grants=False)
        other_org = factories.organisation.create(name="Organisation 3", can_manage_grants=False)

        factories.grant_recipient.create(grant=grant, organisation=org_1)
        factories.grant_recipient.create(grant=grant, organisation=org_2)
        factories.grant_recipient.create(grant=other_grant, organisation=other_org)

        user_1 = factories.user.create(email="user1@org1.example.com")
        user_2 = factories.user.create(email="user2@org1.example.com")
        user_3 = factories.user.create(email="user3@org2.example.com")
        user_4 = factories.user.create(email="user4@org3.example.com")

        factories.user_role.create(
            user=user_1, organisation=org_1, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )
        factories.user_role.create(
            user=user_2, organisation=org_1, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )
        factories.user_role.create(
            user=user_3, organisation=org_2, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        # user 4 has permissions as a data provider for the grant, but in an org that isn't a grant recipient
        factories.user_role.create(
            user=user_4, organisation=other_org, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )
        # user 4 also has permissions as a data provider for a different grant, as a proper grant recipient
        factories.user_role.create(
            user=user_4,
            organisation=other_org,
            grant=other_grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{ReportAdminEmailTypeEnum.REPORT_OPEN_NOTIFICATION.value}"
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert response.content_length > 0

        lines = response.text.splitlines()
        assert len(lines) == 4

        header = lines[0]
        assert "email_address" in header
        assert "grant_name" in header
        assert "reporting_period" in header
        assert "report_deadline" in header
        assert "grant_report_url" in header

        assert "user1@org1.example.com" in lines[1]
        assert "user2@org1.example.com" in lines[2]
        assert "user3@org2.example.com" in lines[3]
        assert "user4@org3.example.com" not in response.text

        assert all("Test Grant" in line for line in lines[1:])
        assert all("Wednesday 1 January 2025 to Monday 31 March 2025" in line for line in lines[1:])
        assert all("Wednesday 30 April 2025" in line for line in lines[1:])
        assert all(f"/grants/{grant.id}/reports" in line for line in lines[1:])

    def test_download_csv_format_and_content_deadline_reminder(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        other_grant = factories.grant.create(name="Other Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.OPEN,
            reporting_period_start_date=datetime.date(2025, 1, 1),
            reporting_period_end_date=datetime.date(2025, 3, 31),
            submission_period_start_date=datetime.date(2025, 4, 1),
            submission_period_end_date=datetime.date(2025, 4, 30),
        )
        question = factories.question.create(form__collection=collection)

        org_1 = factories.organisation.create(name="Organisation 1", can_manage_grants=False)
        org_2 = factories.organisation.create(name="Organisation 2", can_manage_grants=False)
        org_3 = factories.organisation.create(name="Organisation 3", can_manage_grants=False)
        other_org = factories.organisation.create(name="Organisation Other", can_manage_grants=False)

        gr1 = factories.grant_recipient.create(grant=grant, organisation=org_1)
        gr2 = factories.grant_recipient.create(grant=grant, organisation=org_2)
        factories.grant_recipient.create(grant=grant, organisation=org_3)
        factories.grant_recipient.create(grant=other_grant, organisation=other_org)

        user_1 = factories.user.create(email="user1@org1.example.com")
        user_2 = factories.user.create(email="user2@org1.example.com")
        user_3 = factories.user.create(email="user3@org2.example.com")
        user_4 = factories.user.create(email="user4@org2.example.com")
        user_5 = factories.user.create(email="user5@org3.example.com")
        user_other = factories.user.create(email="user@org-other.example.com")

        factories.user_role.create(
            user=user_1, organisation=org_1, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )
        factories.user_role.create(
            user=user_2, organisation=org_1, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER]
        )
        factories.user_role.create(
            user=user_3, organisation=org_2, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )
        factories.user_role.create(
            user=user_4, organisation=org_2, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER]
        )
        # user 5 is both member and certifier, but should only be in the report once
        factories.user_role.create(
            user=user_5,
            organisation=org_3,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
        )

        # user_other has permissions as a data provider for the grant, but in an org that isn't a grant recipient
        factories.user_role.create(
            user=user_other, organisation=other_org, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )
        # user_other also has permissions as a data provider for a different grant, as a proper grant recipient
        factories.user_role.create(
            user=user_4,
            organisation=other_org,
            grant=other_grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        # org 1 has an in progress submission, so should be in the list
        factories.submission.create(
            mode=SubmissionModeEnum.LIVE,
            collection=collection,
            data={str(question.id): "answer 1"},
            created_by=user_1,
            grant_recipient=gr1,
        )

        # org 2 has submitted their report, so should not be in the list
        submission_2 = factories.submission.create(
            mode=SubmissionModeEnum.LIVE,
            collection=collection,
            data={str(question.id): "answer 2"},
            created_by=user_3,
            grant_recipient=gr2,
        )
        factories.submission_event.create(
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
            submission=submission_2,
            related_entity_id=question.form.id,
            created_by=user_2,
        )
        factories.submission_event.create(
            event_type=SubmissionEventType.SUBMISSION_SUBMITTED, submission=submission_2, created_by=user_3
        )
        assert SubmissionHelper(submission_2).status == SubmissionStatusEnum.SUBMITTED

        # org 3 has not started their report (has no submission) so should be in the list

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{ReportAdminEmailTypeEnum.DEADLINE_REMINDER.value}"
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert response.content_length > 0

        lines = response.text.splitlines()
        assert len(lines) == 4

        header = lines[0]
        assert "email_address" in header
        assert "grant_name" in header
        assert "reporting_period" in header
        assert "report_deadline" in header
        assert "grant_report_url" in header

        assert "user3@org2.example.com" not in response.text
        assert "user4@org2.example.com" not in response.text
        assert "user@org-other.example.com" not in response.text
        assert "user1@org1.example.com" in lines[1]
        assert "user2@org1.example.com" in lines[2]
        assert "user5@org3.example.com" in lines[3]

        assert all("Test Grant" in line for line in lines[1:])
        assert all("Wednesday 1 January 2025 to Monday 31 March 2025" in line for line in lines[1:])
        assert all("Wednesday 30 April 2025" in line for line in lines[1:])
        assert all(f"/grants/{grant.id}/reports" in line for line in lines[1:])


class TestSetUpCertifiers:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_set_up_global_certifiers_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers")
        assert response.status_code == expected_code

    def test_get_set_up_global_certifiers_page(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Set up global certifiers"

        assert soup.find("textarea", {"id": "certifiers_data"}) is not None

    def test_get_shows_existing_certifiers(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Org", can_manage_grants=False)
        user = factories.user.create(name="John Doe", email="john.doe@example.com")
        factories.user_role.create(user=user, organisation=org, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "John Doe" in soup.text
        assert "john.doe@example.com" in soup.text

    def test_post_creates_user_and_adds_certifier_permission(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
            data={
                "certifiers_data": (
                    "organisation-name\tfirst-name\tlast-name\temail-address\n"
                    "Test Organisation\tJohn\tDoe\tjohn.doe@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Created or updated 1 certifier(s).")

        user = get_user_by_email("john.doe@example.com")
        assert user is not None
        assert user.name == "John Doe"
        assert len(user.roles) == 1
        assert RoleEnum.CERTIFIER in user.roles[0].permissions
        assert user.roles[0].organisation_id == org.id

    def test_post_with_multiple_certifiers(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Org 2", can_manage_grants=False)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
            data={
                "certifiers_data": (
                    "organisation-name\tfirst-name\tlast-name\temail-address\n"
                    "Org 1\tJohn\tDoe\tjohn.doe@example.com\n"
                    "Org 2\tJane\tSmith\tjane.smith@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Created or updated 2 certifier(s).")

        user1 = get_user_by_email("john.doe@example.com")
        assert user1 is not None
        assert user1.name == "John Doe"
        assert any(RoleEnum.CERTIFIER in role.permissions and role.organisation_id == org1.id for role in user1.roles)

        user2 = get_user_by_email("jane.smith@example.com")
        assert user2 is not None
        assert user2.name == "Jane Smith"
        assert any(RoleEnum.CERTIFIER in role.permissions and role.organisation_id == org2.id for role in user2.roles)

    def test_post_with_existing_user_upserts(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        existing_user = factories.user.create(email="existing@example.com", name="Old Name")

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
            data={
                "certifiers_data": (
                    "organisation-name\tfirst-name\tlast-name\temail-address\n"
                    "Test Organisation\tNew\tName\texisting@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Created or updated 1 certifier(s).")

        user = get_user_by_email("existing@example.com")
        assert user is not None
        assert user.id == existing_user.id
        assert user.name == "New Name"
        assert any(RoleEnum.CERTIFIER in role.permissions and role.organisation_id == org.id for role in user.roles)

    def test_post_redirects_to_tasklist(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        factories.organisation.create(name="Test Organisation", can_manage_grants=False)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
            data={
                "certifiers_data": (
                    "organisation-name\tfirst-name\tlast-name\temail-address\n"
                    "Test Organisation\tJohn\tDoe\tjohn.doe@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"

    def test_post_with_invalid_header_shows_error(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
            data={
                "certifiers_data": (
                    "wrong-header\tfirst-name\tlast-name\temail-address\n"
                    "Test Organisation\tJohn\tDoe\tjohn.doe@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "The header row must be exactly: organisation-name\tfirst-name\tlast-name\temail-address"
        )

    def test_post_with_invalid_email_shows_error(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        factories.organisation.create(name="Test Organisation", can_manage_grants=False)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
            data={
                "certifiers_data": (
                    "organisation-name\tfirst-name\tlast-name\temail-address\n"
                    "Test Organisation\tJohn\tDoe\tinvalid-email"
                ),
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Invalid email address(es): invalid-email")

    def test_post_with_invalid_organisation(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
            data={
                "certifiers_data": (
                    "organisation-name\tfirst-name\tlast-name\temail-address\n"
                    "Non Existent Org\tJohn\tDoe\tjohn.doe@example.com\n"
                ),
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Ignoring certifier for 'Non Existent Org' - organisation has not been set up.")
        assert get_user_by_email("john.doe@example.com") is None


class TestReportingLifecycleMakeGrantLive:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_confirm_page_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-live")
        assert response.status_code == expected_code

    def test_get_confirm_page_with_draft_grant(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-live"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test Grant Make grant live"

    def test_get_confirm_page_with_live_grant_redirects(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Already Live Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-live", follow_redirects=True
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Already Live Grant is already live")

    def test_post_makes_grant_live_with_enough_team_members(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.DRAFT)
        collection = factories.collection.create(grant=grant)
        factories.user_role.create(grant=grant, permissions=[RoleEnum.MEMBER])
        factories.user_role.create(grant=grant, permissions=[RoleEnum.ADMIN])

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-live",
            data={"submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(grant)
        assert grant.status == GrantStatusEnum.LIVE

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Test Grant is now live")

    def test_post_fails_without_enough_team_members(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.DRAFT)
        collection = factories.collection.create(grant=grant)
        factories.user_role.create(grant=grant, permissions=[RoleEnum.MEMBER])

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-live",
            data={"submit": "Make grant live"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        db_session.refresh(grant)
        assert grant.status == GrantStatusEnum.DRAFT

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "You must add at least two grant team users before making the grant live")


class TestReportingLifecycleMarkGrantAsOnboarding:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_confirm_page_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/mark-as-onboarding")
        assert response.status_code == expected_code

    def test_get_confirm_page_with_draft_grant(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/mark-as-onboarding"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test Grant Mark grant as onboarding with Funding Service"

    @pytest.mark.parametrize("from_status", [GrantStatusEnum.ONBOARDING, GrantStatusEnum.LIVE])
    def test_get_confirm_page_with_live_grant_redirects(
        self, authenticated_platform_admin_client, factories, db_session, from_status
    ):
        grant = factories.grant.create(name="Already Active Grant", status=from_status)
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/mark-as-onboarding", follow_redirects=True
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Already Active Grant is already marked as onboarding")

    def test_post_makes_grant_live_with_enough_team_members(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.DRAFT)
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/mark-as-onboarding",
            data={"submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(grant)
        assert grant.status == GrantStatusEnum.ONBOARDING

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Test Grant is now marked as onboarding.")


class TestManageOrganisations:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_manage_organisations_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-organisations")
        assert response.status_code == expected_code

    def test_get_manage_organisations_page(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-organisations"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Set up organisations"

        textarea = soup.find("textarea", {"id": "organisations_data"})
        assert textarea is not None
        assert "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n" in textarea.get_text()

    def test_post_creates_new_organisations(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        initial_count = get_organisation_count()

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tTest Department\tCentral Government\t01/01/2020\t\n"
            "E06000001\tTest Council\tUnitary Authority\t15/06/2021\t"
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
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
        collection = factories.collection.create(grant=grant)
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
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
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
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tRetired Department\tCentral Government\t01/01/2020\t31/12/2023"
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        org = db_session.query(Organisation).filter_by(external_id="GB-GOV-123").one()
        assert org.status == OrganisationStatus.RETIRED
        assert org.retirement_date == datetime.date(2023, 12, 31)

    def test_post_with_invalid_header_shows_error(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        tsv_data = "Wrong Header\nGB-GOV-123\tTest Department\tCentral Government\t01/01/2020\t"

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
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
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tTest Department\tInvalid Type\t01/01/2020\t"
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
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
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tTest Department\tCentral Government\t2020-01-01\t"
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
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
            ("anonymous_client", 302),
        ],
    )
    def test_manage_grant_recipients_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients")
        assert response.status_code == expected_code

    def test_get_manage_grant_recipients_page(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.organisation.create(name="Org 2", can_manage_grants=False)
        factories.organisation.create(name="Org 3", can_manage_grants=False)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients"
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
        collection = factories.collection.create(grant=grant)
        grant_managing_org = _get_grant_managing_organisation()
        factories.organisation.create(name="Regular Org", can_manage_grants=False)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients"
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
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.organisation.create(name="Org 2", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org1)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients"
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
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Org 2", can_manage_grants=False)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients",
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
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Org 1", can_manage_grants=False)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients",
            data={"recipients": [str(org.id)], "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"

    def test_post_without_recipients_shows_validation_error(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        factories.organisation.create(name="Org 1", can_manage_grants=False)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients",
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
        collection = factories.collection.create(grant=grant)
        _get_grant_managing_organisation()

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        select_element = soup.find("select", {"id": "recipients"})
        assert select_element is not None

        options = select_element.find_all("option")
        assert len(options) == 0


class TestSetUpGrantRecipientUsers:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_set_up_grant_recipient_data_providers_permissions(
        self, client_fixture, expected_code, request, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers"
        )
        assert response.status_code == expected_code

    def test_get_set_up_grant_recipient_data_providers_page(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Set up grant recipient data providers"

        assert soup.find("textarea", {"id": "users_data"}) is not None

    def test_post_creates_user_and_role(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers",
            data={
                "users_data": (
                    "organisation-name\tfull-name\temail-address\nTest Organisation\tJohn Doe\tjohn@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully set up 1 grant recipient data provider.")

        user = get_user_by_email("john@example.com")
        assert user is not None
        assert user.name == "John Doe"
        assert len(user.roles) == 1
        assert RoleEnum.DATA_PROVIDER in user.roles[0].permissions
        assert user.roles[0].organisation_id == org.id
        assert user.roles[0].grant_id == grant.id

    def test_post_with_existing_user_upserts(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        existing_user = factories.user.create(email="existing@example.com", name="Old Name")

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers",
            data={
                "users_data": (
                    "organisation-name\tfull-name\temail-address\nTest Organisation\tNew Name\texisting@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully set up 1 grant recipient data provider.")

        user = get_user_by_email("existing@example.com")
        assert user is not None
        assert user.id == existing_user.id
        assert user.name == "New Name"
        assert any(
            RoleEnum.DATA_PROVIDER in role.permissions and role.organisation_id == org.id and role.grant_id == grant.id
            for role in user.roles
        )

    def test_post_redirects_to_tasklist(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers",
            data={
                "users_data": (
                    "organisation-name\tfull-name\temail-address\nTest Organisation\tJohn Doe\tjohn@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"

    def test_post_with_invalid_header_shows_error(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers",
            data={
                "users_data": "wrong-header\tfull-name\temail-address\nTest Organisation\tJohn Doe\tjohn@example.com",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "The header row must be exactly: organisation-name\tfull-name\temail-address")

    def test_post_with_non_grant_recipient_shows_error(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers",
            data={
                "users_data": (
                    "organisation-name\tfull-name\temail-address\nNot A Recipient\tJohn Doe\tjohn@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Organisation 'Not A Recipient' is not a grant recipient for this grant.")

    def test_post_with_mixed_valid_invalid_orgs_creates_no_users(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Valid Org", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers",
            data={
                "users_data": (
                    "organisation-name\tfull-name\temail-address\n"
                    "Valid Org\tJohn Doe\tjohn@example.com\nInvalid Org\tJane Smith\tjane@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Organisation 'Invalid Org' is not a grant recipient for this grant.")

        assert get_user_by_email("john@example.com") is None
        assert get_user_by_email("jane@example.com") is None

    def test_post_creates_multiple_users(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Org 2", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers",
            data={
                "users_data": (
                    "organisation-name\tfull-name\temail-address\n"
                    "Org 1\tJohn Doe\tjohn@example.com\nOrg 2\tJane Smith\tjane@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully set up 2 grant recipient data providers.")

        user1 = get_user_by_email("john@example.com")
        assert user1 is not None
        assert user1.name == "John Doe"

        user2 = get_user_by_email("jane@example.com")
        assert user2 is not None
        assert user2.name == "Jane Smith"

    def test_post_with_invalid_emails_shows_error(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers",
            data={
                "users_data": (
                    "organisation-name\tfull-name\temail-address\n"
                    "Test Organisation\tJohn Doe\tinvalid-email\nTest Organisation\tJane Smith\talso-bad"
                ),
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Invalid email address(es): invalid-email, also-bad")

    def test_post_with_revoke_existing_checkbox_revokes_existing_data_providers(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Organisation 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Organisation 2", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)

        existing_user = factories.user.create(email="existing@example.com", name="Existing User")
        factories.user_role.create(
            user=existing_user, organisation=org1, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers",
            data={
                "users_data": (
                    "organisation-name\tfull-name\temail-address\nOrganisation 2\tNew User\tnew@example.com"
                ),
                "revoke_existing": "y",
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully set up 1 grant recipient data provider.")

        existing_user_refreshed = get_user_by_email("existing@example.com")
        assert existing_user_refreshed is not None
        data_provider_roles = [
            role for role in existing_user_refreshed.roles if RoleEnum.DATA_PROVIDER in role.permissions
        ]
        assert len(data_provider_roles) == 0

        new_user = get_user_by_email("new@example.com")
        assert new_user is not None
        assert new_user.name == "New User"
        assert len(new_user.roles) == 1
        assert RoleEnum.DATA_PROVIDER in new_user.roles[0].permissions
        assert new_user.roles[0].organisation_id == org2.id
        assert new_user.roles[0].grant_id == grant.id


class TestRevokeGrantRecipientDataProviders:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_revoke_grant_recipient_data_providers_permissions(
        self, client_fixture, expected_code, request, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-recipient-data-providers"
        )
        assert response.status_code == expected_code

    def test_get_revoke_grant_recipient_data_providers_page(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="John Doe", email="john@example.com")
        factories.user_role.create(
            user=user, organisation=org, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-recipient-data-providers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Revoke grant recipient data providers"

        assert soup.find("select", {"id": "grant_recipients_data_providers"}) is not None

    def test_post_revokes_user_role(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="John Doe", email="john@example.com")
        user_role = factories.user_role.create(
            user=user, organisation=org, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        from app.common.data.models_user import UserRole

        assert db_session.query(UserRole).filter_by(id=user_role.id).first() is not None

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-recipient-data-providers",
            data={"grant_recipients_data_providers": [f"{user.id}|{org.id}"], "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully revoked access for 1 data provider.")

        assert db_session.query(UserRole).filter_by(id=user_role.id).first() is None

    def test_post_revokes_multiple_user_roles(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Org 2", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)
        user1 = factories.user.create(name="John Doe", email="john@example.com")
        user2 = factories.user.create(name="Jane Smith", email="jane@example.com")
        user_role1 = factories.user_role.create(
            user=user1, organisation=org1, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )
        user_role2 = factories.user_role.create(
            user=user2, organisation=org2, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        from app.common.data.models_user import UserRole

        role1 = db_session.query(UserRole).filter_by(id=user_role1.id).first()
        role2 = db_session.query(UserRole).filter_by(id=user_role2.id).first()
        assert RoleEnum.DATA_PROVIDER in role1.permissions
        assert RoleEnum.DATA_PROVIDER in role2.permissions

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-recipient-data-providers",
            data={
                "grant_recipients_data_providers": [f"{user1.id}|{org1.id}", f"{user2.id}|{org2.id}"],
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully revoked access for 2 data providers.")

        assert db_session.query(UserRole).filter_by(id=user_role1.id).first() is None
        assert db_session.query(UserRole).filter_by(id=user_role2.id).first() is None

    def test_post_redirects_to_set_up_page(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="John Doe", email="john@example.com")
        factories.user_role.create(
            user=user, organisation=org, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-recipient-data-providers",
            data={"grant_recipients_data_providers": [f"{user.id}|{org.id}"], "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert (
            response.location
            == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipient-data-providers"
        )


class TestRevokeCertifiers:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_revoke_global_certifiers_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers")
        assert response.status_code == expected_code

    def test_get_revoke_global_certifiers_page(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        factories.organisation.create(name="Org 1")

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Revoke certifier"

        assert soup.find("select", {"id": "organisation_id"}) is not None
        assert soup.find("input", {"id": "email"}) is not None

    def test_post_revokes_certifier_permission(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation")
        user = factories.user.create(name="John Doe", email="john@example.com")
        user_role = factories.user_role.create(
            user=user, organisation=org, grant=None, permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER]
        )

        from app.common.data.models_user import UserRole

        assert db_session.query(UserRole).filter_by(id=user_role.id).first() is not None
        assert RoleEnum.CERTIFIER in user_role.permissions

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers",
            data={"organisation_id": str(org.id), "email": "john@example.com", "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully revoked certifier access for John Doe (john@example.com).")

        db_session.refresh(user_role)
        assert user_role.permissions == [RoleEnum.MEMBER]

    def test_post_with_nonexistent_user_shows_error(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation")

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers",
            data={"organisation_id": str(org.id), "email": "nonexistent@example.com", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "User with email 'nonexistent@example.com' does not exist.")

    def test_post_with_non_certifier_user_shows_error(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation")
        factories.user.create(name="John Doe", email="john@example.com")

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers",
            data={"organisation_id": str(org.id), "email": "john@example.com", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup, "User 'John Doe' (john@example.com) is not a global certifier for the selected organisation."
        )

    def test_post_redirects_to_set_up_global_certifiers_page(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation")
        user = factories.user.create(name="John Doe", email="john@example.com")
        factories.user_role.create(user=user, organisation=org, grant=None, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers",
            data={"organisation_id": str(org.id), "email": "john@example.com", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert (
            response.location
            == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers"
        )


class TestOverrideGrantCertifiers:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_override_grant_certifiers_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers"
        )
        assert response.status_code == expected_code

    def test_get_override_grant_certifiers_page(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create(grant=grant)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Override certifiers for this grant"

        assert soup.find("select", {"id": "organisation_id"}) is not None
        assert soup.find("input", {"id": "full_name"}) is not None
        assert soup.find("input", {"id": "email"}) is not None

    def test_organisation_dropdown_only_shows_grant_recipients(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Recipient Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Recipient Org 2", can_manage_grants=False)
        factories.organisation.create(name="Non-Recipient Org", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers"
        )

        soup = BeautifulSoup(response.data, "html.parser")
        select = soup.find("select", {"id": "organisation_id"})
        options = select.find_all("option")
        option_texts = [option.text.strip() for option in options if option.get("value")]

        assert "Recipient Org 1" in option_texts
        assert "Recipient Org 2" in option_texts
        assert "Non-Recipient Org" not in option_texts

    def test_post_creates_grant_specific_certifier_new_user(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers",
            data={
                "organisation_id": str(org.id),
                "full_name": "John Doe",
                "email": "john.doe@example.com",
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully added John Doe (john.doe@example.com) as a grant-specific certifier.")

        user = get_user_by_email("john.doe@example.com")
        assert user is not None
        assert user.name == "John Doe"
        assert len(user.roles) == 1
        assert RoleEnum.CERTIFIER in user.roles[0].permissions
        assert user.roles[0].organisation_id == org.id
        assert user.roles[0].grant_id == grant.id

    def test_post_creates_grant_specific_certifier_existing_user(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="Jane Doe", email="jane.doe@example.com")

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers",
            data={
                "organisation_id": str(org.id),
                "full_name": "Jane Doe",
                "email": "jane.doe@example.com",
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully added Jane Doe (jane.doe@example.com) as a grant-specific certifier.")

        db_session.refresh(user)
        assert len(user.roles) == 1
        assert RoleEnum.CERTIFIER in user.roles[0].permissions
        assert user.roles[0].grant_id == grant.id

    def test_grant_id_is_set_in_user_role(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers",
            data={
                "organisation_id": str(org.id),
                "full_name": "Alice Smith",
                "email": "alice@example.com",
                "submit": "y",
            },
        )

        user = get_user_by_email("alice@example.com")
        assert user.roles[0].grant_id == grant.id

    def test_tasklist_count_shows_grant_specific_certifiers_only(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Org", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        org_level_user1 = factories.user.create(email="org1@example.com")
        org_level_user2 = factories.user.create(email="org2@example.com")
        factories.user_role.create(user=org_level_user1, organisation=org, grant=None, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=org_level_user2, organisation=org, grant=None, permissions=[RoleEnum.CERTIFIER])

        grant_user1 = factories.user.create(email="grant1@example.com")
        grant_user2 = factories.user.create(email="grant2@example.com")
        grant_user3 = factories.user.create(email="grant3@example.com")
        factories.user_role.create(user=grant_user1, organisation=org, grant=grant, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=grant_user2, organisation=org, grant=grant, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=grant_user3, organisation=org, grant=grant, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert "3 overrides" in soup.text

    def test_existing_certifiers_section_shows_grant_specific_only(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Org", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        org_level_user = factories.user.create(name="Org Level User", email="org@example.com")
        factories.user_role.create(user=org_level_user, organisation=org, grant=None, permissions=[RoleEnum.CERTIFIER])

        grant_specific_user = factories.user.create(name="Grant Specific User", email="grant@example.com")
        factories.user_role.create(
            user=grant_specific_user, organisation=org, grant=grant, permissions=[RoleEnum.CERTIFIER]
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers"
        )

        assert response.status_code == 200
        assert b"Grant Specific User" in response.data
        assert b"Org Level User" not in response.data

    def test_post_with_invalid_email(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers",
            data={
                "organisation_id": str(org.id),
                "full_name": "John Doe",
                "email": "invalid-email",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Enter a valid email address")

    def test_post_with_missing_organisation(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create(grant=grant)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers",
            data={
                "organisation_id": "",
                "full_name": "John Doe",
                "email": "john@example.com",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Select an organisation")


class TestRevokeGrantOverrideCertifiers:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_revoke_grant_override_certifiers_permissions(
        self, client_fixture, expected_code, request, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers"
        )
        assert response.status_code == expected_code

    def test_get_revoke_grant_override_certifiers_page(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create(grant=grant)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Revoke grant-specific certifier"

        assert soup.find("select", {"id": "organisation_id"}) is not None
        assert soup.find("input", {"id": "email"}) is not None

    def test_post_successfully_revokes_grant_specific_certifier(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="John Doe", email="john@example.com")
        user_role = factories.user_role.create(
            user=user, organisation=org, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER]
        )

        from app.common.data.models_user import UserRole

        assert db_session.query(UserRole).filter_by(id=user_role.id).first() is not None
        assert RoleEnum.CERTIFIER in user_role.permissions

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers",
            data={"organisation_id": str(org.id), "email": "john@example.com", "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup, "Successfully revoked grant-specific certifier access for John Doe (john@example.com)."
        )

        db_session.refresh(user_role)
        assert user_role.permissions == [RoleEnum.MEMBER]

    def test_revoke_does_not_affect_org_level_certifier(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="John Doe", email="john@example.com")

        org_level_role = factories.user_role.create(
            user=user, organisation=org, grant=None, permissions=[RoleEnum.CERTIFIER]
        )
        factories.user_role.create(user=user, organisation=org, grant=grant, permissions=[RoleEnum.CERTIFIER])

        authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers",
            data={"organisation_id": str(org.id), "email": "john@example.com", "submit": "y"},
            follow_redirects=True,
        )

        db_session.refresh(org_level_role)
        db_session.refresh(user)
        assert RoleEnum.CERTIFIER in org_level_role.permissions
        assert len([r for r in user.roles if r.grant_id == grant.id and RoleEnum.CERTIFIER in r.permissions]) == 0

    def test_post_with_nonexistent_user_shows_error(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers",
            data={"organisation_id": str(org.id), "email": "nonexistent@example.com", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "User with email 'nonexistent@example.com' does not exist.")

    def test_post_with_user_without_grant_specific_permission(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="John Doe", email="john@example.com")
        factories.user_role.create(user=user, organisation=org, grant=None, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers",
            data={"organisation_id": str(org.id), "email": "john@example.com", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup, "User 'John Doe' (john@example.com) is not a grant-specific certifier for the selected organisation."
        )


class TestScheduleReport:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_schedule_report_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/schedule-report")
        assert response.status_code == expected_code

    def test_get_confirm_page_with_prerequisites_met(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user, organisation=grant_recipient.organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/schedule-report"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test Grant Sign off and lock report"

    def test_post_schedules_collection(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.DRAFT,
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/schedule-report",
            data={"submit": "Sign off and lock report"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Q1 Report is now locked")

    def test_post_fails_when_grant_recipients_have_no_users(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.DRAFT,
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        factories.grant_recipient.create(grant=grant)

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/schedule-report",
            data={"submit": "Schedule report"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "All grant recipients must have at least one data provider set up before scheduling a report"
        )

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.DRAFT


class TestSetCollectionDatesStatusRestriction:
    @pytest.mark.parametrize(
        "collection_status",
        [
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.CLOSED,
        ],
    )
    def test_get_set_dates_redirects_with_error_for_non_draft_status(
        self, authenticated_platform_admin_client, factories, db_session, collection_status
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=collection_status,
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-dates",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup,
            "You cannot set dates for Q1 Report because it is not in draft status.",
        )

    @pytest.mark.parametrize(
        "collection_status",
        [
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.CLOSED,
        ],
    )
    def test_post_set_dates_redirects_with_error_for_non_draft_status(
        self, authenticated_platform_admin_client, factories, db_session, collection_status
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=collection_status,
            reporting_period_start_date=datetime.date(2025, 1, 1),
            reporting_period_end_date=datetime.date(2025, 4, 1),
            submission_period_start_date=datetime.date(2025, 4, 1),
            submission_period_end_date=datetime.date(2025, 4, 30),
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-dates",
            data={
                "reporting_period_start_date-day": "1",
                "reporting_period_start_date-month": "2",
                "reporting_period_start_date-year": "2025",
                "reporting_period_end_date-day": "1",
                "reporting_period_end_date-month": "5",
                "reporting_period_end_date-year": "2025",
                "submission_period_start_date-day": "1",
                "submission_period_start_date-month": "5",
                "submission_period_start_date-year": "2025",
                "submission_period_end_date-day": "31",
                "submission_period_end_date-month": "5",
                "submission_period_end_date-year": "2025",
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(collection)
        assert collection.reporting_period_start_date == datetime.date(2025, 1, 1)
        assert collection.reporting_period_end_date == datetime.date(2025, 4, 1)

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup,
            "You cannot set dates for Q1 Report because it is not in draft status.",
        )

    def test_get_set_dates_allows_draft_status(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.DRAFT,
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-dates",
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Q1 Report Set reporting and submission dates"

    @pytest.mark.parametrize(
        "collection_status",
        [
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.CLOSED,
        ],
    )
    def test_tasklist_does_not_link_to_set_dates_for_non_draft_status(
        self, authenticated_platform_admin_client, factories, db_session, collection_status
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=collection_status,
            reporting_period_start_date=datetime.date(2025, 1, 1),
            reporting_period_end_date=datetime.date(2025, 4, 1),
            submission_period_start_date=datetime.date(2025, 4, 1),
            submission_period_end_date=datetime.date(2025, 4, 30),
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        reporting_dates_task = task_items[0]
        reporting_dates_link = reporting_dates_task.find("a", {"class": "govuk-link"})
        assert reporting_dates_link is None

        submission_dates_task = task_items[1]
        submission_dates_link = submission_dates_task.find("a", {"class": "govuk-link"})
        assert submission_dates_link is None

    def test_tasklist_links_to_set_dates_for_draft_status(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.DRAFT,
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        reporting_dates_task = task_items[0]
        reporting_dates_link = reporting_dates_task.find("a", {"class": "govuk-link"})
        assert reporting_dates_link is not None
        assert f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-dates" in reporting_dates_link.get(
            "href"
        )

        submission_dates_task = task_items[1]
        submission_dates_link = submission_dates_task.find("a", {"class": "govuk-link"})
        assert submission_dates_link is not None
        assert f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/set-dates" in submission_dates_link.get(
            "href"
        )


class TestMakeReportLive:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_make_report_live_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.SCHEDULED,
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=factories.user.create(),
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.CERTIFIER],
        )

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-report-live")
        assert response.status_code == expected_code

    def test_get_confirm_page_with_all_prerequisites_met(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.SCHEDULED,
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        certifier = factories.user.create()
        factories.user_role.create(
            user=certifier,
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
        )

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-report-live"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test Grant Open the report for submissions"

    @pytest.mark.freeze_time("2024-04-01 10:00:00")
    def test_post_makes_collection_open(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.SCHEDULED,
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        certifier = factories.user.create()
        factories.user_role.create(
            user=certifier,
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-report-live",
            data={"submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.OPEN

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Q1 Report is now live and grant recipients can start making submissions")

    def test_post_fails_when_grant_not_live(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.ONBOARDING)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.SCHEDULED,
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        certifier = factories.user.create()
        factories.user_role.create(
            user=certifier,
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-report-live",
            data={"submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Test Grant must be made live before opening a report")

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

    def test_post_fails_when_no_grant_recipients(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.SCHEDULED,
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-report-live",
            data={"submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Grant recipients must be set up before opening a report")

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

    def test_post_fails_when_grant_recipients_have_no_users(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.SCHEDULED,
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        certifier = factories.user.create()
        factories.user_role.create(
            user=certifier,
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-report-live",
            data={"submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "All grant recipients must have at least one data provider set up before opening a report"
        )

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

    def test_post_fails_when_dates_not_set(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.SCHEDULED,
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        certifier = factories.user.create()
        factories.user_role.create(
            user=certifier,
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-report-live",
            data={"submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "Cannot change collection status to Open: all reporting and submission period dates must be set"
        )

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

    def test_post_fails_when_collection_not_scheduled(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.DRAFT,
            reporting_period_start_date=datetime.date(2024, 1, 1),
            reporting_period_end_date=datetime.date(2024, 3, 31),
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        certifier = factories.user.create()
        factories.user_role.create(
            user=certifier,
            organisation=grant_recipient.organisation,
            grant=None,
            permissions=[RoleEnum.MEMBER, RoleEnum.CERTIFIER],
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/reporting-lifecycle/{grant.id}/{collection.id}/make-report-live",
            data={"submit": "Open report for submissions"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Q1 Report can only be made live from the 'scheduled' state; it is currently")

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.DRAFT
