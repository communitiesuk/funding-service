import csv
import datetime
import io

import pytest
from bs4 import BeautifulSoup

from app import CollectionAdminEmailTypeEnum
from app.common.collections.types import TextSingleLineAnswer
from app.common.data.interfaces.organisations import get_organisation_count, get_organisations
from app.common.data.interfaces.user import get_user, get_user_by_email
from app.common.data.models import Organisation
from app.common.data.models_audit import AuditEvent
from app.common.data.types import (
    AuditEventType,
    CollectionStatusEnum,
    CollectionType,
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    GrantStatusEnum,
    OrganisationModeEnum,
    OrganisationStatus,
    OrganisationType,
    QuestionDataType,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
)
from app.common.helpers.collections import SubmissionHelper
from tests.models import FactoryAnswer, _get_grant_managing_organisation
from tests.utils import get_h1_text, get_h2_text, page_has_error, page_has_flash


class TestFlaskAdminAccess:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 200),
            ("authenticated_platform_data_analyst_client", 200),
            ("authenticated_platform_member_client", 200),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_admin_index_access(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/")
        assert response.status_code == expected_code

    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 403),
            ("authenticated_platform_data_analyst_client", 403),
            ("authenticated_platform_member_client", 403),
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
            ("authenticated_platform_grant_lifecycle_manager_client", 403),
            ("authenticated_platform_data_analyst_client", 403),
            ("authenticated_platform_member_client", 403),
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
    def test_admin_invitation_list_access(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/invitation/")
        assert response.status_code == expected_code


class TestCollectionLifecycleSelectGrant:
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
    def test_select_grant_permissions(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/collection-lifecycle/")
        assert response.status_code == expected_code

    def test_get_select_grant_page(self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session):
        draft_grant = factories.grant.create(name="Test Draft Grant", status=GrantStatusEnum.DRAFT)
        live_grant = factories.grant.create(name="Test Live Grant", status=GrantStatusEnum.LIVE)

        response = authenticated_platform_grant_lifecycle_manager_client.get("/deliver/admin/collection-lifecycle/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Collection lifecycle"

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
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, name="Q1 Report")

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            "/deliver/admin/collection-lifecycle/",
            data={"grant_id": str(grant.id), "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

    def test_post_with_valid_grant_id_multiple_reports_redirects_to_select_report(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        factories.collection.create(grant=grant, name="Q1 Report")
        factories.collection.create(grant=grant, name="Q2 Report")

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            "/deliver/admin/collection-lifecycle/",
            data={"grant_id": str(grant.id), "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/collection-lifecycle/{grant.id}/select-collection"

    def test_post_without_grant_id_shows_validation_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        factories.grant.create()

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            "/deliver/admin/collection-lifecycle/",
            data={"grant_id": "", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h2_text(soup) == "There is a problem"
        assert page_has_error(soup, "Select a grant to view its collection lifecycle")


class TestCollectionLifecycleSelectReport:
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
    def test_select_report_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/collection-lifecycle/{grant.id}/select-collection")
        assert response.status_code == expected_code

    def test_get_select_report_page(self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant")
        collection1 = factories.collection.create(grant=grant, name="Q1 Report")
        collection2 = factories.collection.create(grant=grant, name="Q2 Report")

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/select-collection"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Select collection"

        select_element = soup.find("select", {"id": "collection_id"})
        assert select_element is not None

        options = select_element.find_all("option")
        option_texts = [opt.get_text(strip=True) for opt in options]
        option_values = [opt.get("value") for opt in options]

        assert "Q1 Report (monitoring report)" in option_texts
        assert "Q2 Report (monitoring report)" in option_texts
        assert str(collection1.id) in option_values
        assert str(collection2.id) in option_values

    def test_post_with_valid_collection_id_redirects_to_tasklist(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant, name="Q1 Report")

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/select-collection",
            data={"collection_id": str(collection.id), "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"


class TestCollectionLifecycleTasklist:
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
    def test_tasklist_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}")
        assert response.status_code == expected_code

    def test_shows_all_tasklists(self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", privacy_policy_markdown="hello")
        collection = factories.collection.create(grant=grant, name="Q1 Report")
        org_1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        org_2 = factories.organisation.create(name="Org 2", can_manage_grants=False)
        _ = factories.organisation.create(name="Org 3", can_manage_grants=False)
        _ = factories.organisation.create(name="Org 4", can_manage_grants=False, mode=OrganisationModeEnum.TEST)

        factories.user_role.create(
            organisation=_get_grant_managing_organisation(), grant=grant, permissions=[RoleEnum.MEMBER]
        )
        factories.user_role.create(
            organisation=_get_grant_managing_organisation(), grant=grant, permissions=[RoleEnum.MEMBER]
        )

        factories.user_role.create(organisation=org_1, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(organisation=org_2, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        platform_task_list = soup.find("ul", {"id": "platform-tasks"})
        grant_task_list = soup.find("ul", {"id": "grant-tasks"})
        collection_task_list = soup.find("ul", {"id": "report-tasks"})
        assert platform_task_list is not None
        assert grant_task_list is not None
        assert collection_task_list is not None

        platform_task_items = platform_task_list.find_all("li", {"class": "govuk-task-list__item"})
        grant_task_items = grant_task_list.find_all("li", {"class": "govuk-task-list__item"})
        collection_task_items = collection_task_list.find_all("li", {"class": "govuk-task-list__item"})
        assert len(platform_task_items) == 2
        assert len(grant_task_items) == 6
        assert len(collection_task_items) == 10

        # TODO: update for testing task list

        organisations_task = platform_task_items[0]
        task_title = organisations_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set up organisations"
        assert f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations" in task_title.get(
            "href"
        )

        task_status = organisations_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "3 organisations" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        certifiers_task = platform_task_items[1]
        task_title = certifiers_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set up global certifiers"
        assert (
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers"
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
        assert f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/mark-as-onboarding" in task_title.get(
            "href"
        )

        set_privacy_policy = grant_task_items[1]
        task_title = set_privacy_policy.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set privacy policy"
        assert f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-privacy-policy" in task_title.get(
            "href"
        )

        make_grant_live_task = grant_task_items[2]
        task_title = make_grant_live_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Make the grant live"
        assert f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-live" in task_title.get("href")

        task_status = make_grant_live_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "To do" in task_status.get_text(strip=True)
        assert "govuk-tag--grey" in task_status.get("class")

        set_up_grant_recipients_task = grant_task_items[3]
        task_title = set_up_grant_recipients_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set up grant recipients"
        assert (
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients"
            in task_title.get("href")
        )

        task_status = set_up_grant_recipients_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "0 grant recipients" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        add_bulk_data_providers_task = grant_task_items[4]
        task_title = add_bulk_data_providers_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set up grant recipient data providers"
        assert (
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers"
            in task_title.get("href")
        )

        task_status = add_bulk_data_providers_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "0 data providers" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        override_grant_certifiers_task = grant_task_items[5]
        task_title = override_grant_certifiers_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Override certifiers for this grant"
        assert (
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers"
            in task_title.get("href")
        )

        task_status = override_grant_certifiers_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "0 overrides" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        set_reporting_dates_task = collection_task_items[0]
        task_title = set_reporting_dates_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set reporting dates"
        assert f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-reporting-dates" in task_title.get(
            "href"
        )

        task_status = set_reporting_dates_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Optional" in task_status.get_text(strip=True)
        assert "govuk-tag--blue" in task_status.get("class")

        set_submission_dates_task = collection_task_items[1]
        task_title = set_submission_dates_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Set submission dates"
        assert f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-submission-dates" in task_title.get(
            "href"
        )

        task_status = set_submission_dates_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "To do" in task_status.get_text(strip=True)
        assert "govuk-tag--grey" in task_status.get("class")

        schedule_collection_task = collection_task_items[3]
        task_title = schedule_collection_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Sign off and lock report"

        task_status = schedule_collection_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        make_collection_live_task = collection_task_items[4]
        task_title = make_collection_live_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Open the report for submissions"

        task_status = make_collection_live_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        send_emails_task = collection_task_items[5]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send emails to data providers"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        send_emails_task = collection_task_items[6]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send deadline reminder emails"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        send_emails_task = collection_task_items[7]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send report overdue emails"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        send_emails_task = collection_task_items[8]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Close the report"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        send_emails_task = collection_task_items[9]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send report closed emails"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

    def test_shows_all_tasklists_for_pre_award(self, authenticated_platform_grant_lifecycle_manager_client, factories):
        grant = factories.grant.create(
            name="Test Grant",
            privacy_policy_markdown="hello",
            allow_pre_award=True,
        )
        collection = factories.collection.create(grant=grant, name="Q1 Report", type=CollectionType.APPLICATION)
        org_1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        org_2 = factories.organisation.create(name="Org 2", can_manage_grants=False)
        _ = factories.organisation.create(name="Org 3", can_manage_grants=False)
        _ = factories.organisation.create(name="Org 4", can_manage_grants=False, mode=OrganisationModeEnum.TEST)

        factories.user_role.create(
            organisation=_get_grant_managing_organisation(), grant=grant, permissions=[RoleEnum.MEMBER]
        )
        factories.user_role.create(
            organisation=_get_grant_managing_organisation(), grant=grant, permissions=[RoleEnum.MEMBER]
        )

        factories.user_role.create(organisation=org_1, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(organisation=org_2, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        platform_task_list = soup.find("ul", {"id": "platform-tasks"})
        grant_task_list = soup.find("ul", {"id": "grant-tasks"})
        collection_task_list = soup.find("ul", {"id": "report-tasks"})
        assert platform_task_list is not None
        assert grant_task_list is not None
        assert collection_task_list is not None

        platform_task_items = platform_task_list.find_all("li", {"class": "govuk-task-list__item"})
        grant_task_items = grant_task_list.find_all("li", {"class": "govuk-task-list__item"})
        collection_task_items = collection_task_list.find_all("li", {"class": "govuk-task-list__item"})
        assert len(platform_task_items) == 2
        assert len(grant_task_items) == 6
        assert len(collection_task_items) == 9  # set-reporting-dates is not shown for pre-award collections

        # Prove set-reporting-dates is not showing up
        first_task_status = collection_task_items[0]
        task_title = first_task_status.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) != "Set reporting dates"
        assert task_title.get_text(strip=True) == "Set submission dates"
        assert f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-submission-dates" in task_title.get(
            "href"
        )
        task_status = first_task_status.find("strong", {"class": "govuk-tag"})
        assert "To do" in task_status.get_text(strip=True)
        assert "govuk-tag--grey" in task_status.get("class")

        schedule_collection_task = collection_task_items[2]
        task_title = schedule_collection_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Sign off and lock form"

        task_status = schedule_collection_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        make_collection_live_task = collection_task_items[3]
        task_title = make_collection_live_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Open the form for submissions"

        task_status = make_collection_live_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        send_emails_task = collection_task_items[6]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send form overdue emails"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        send_emails_task = collection_task_items[7]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Close the form"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        send_emails_task = collection_task_items[8]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send form closed emails"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

    def test_get_tasklist_shows_correct_organisation_count_singular(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report")
        factories.organisation.create(name="Org 1", can_manage_grants=False)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        task_list = soup.find("ul", {"class": "govuk-task-list"})
        task_items = task_list.find_all("li", {"class": "govuk-task-list__item"})

        organisations_task = task_items[0]
        task_status = organisations_task.find("strong", {"class": "govuk-tag"})
        assert "1 organisation" in task_status.get_text(strip=True)

    def test_get_tasklist_excludes_grant_managing_organisations_from_count(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report")
        factories.organisation.create(name="Regular Org", can_manage_grants=False)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        task_list = soup.find("ul", {"class": "govuk-task-list"})
        task_items = task_list.find_all("li", {"class": "govuk-task-list__item"})

        organisations_task = task_items[0]
        task_status = organisations_task.find("strong", {"class": "govuk-tag"})
        assert "1 organisation" in task_status.get_text(strip=True)

    def test_get_tasklist_with_live_grant_shows_completed_status(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(
            name="Test Live Grant", status=GrantStatusEnum.LIVE, privacy_policy_markdown="something"
        )
        collection = factories.collection.create(grant=grant, name="Q1 Report")

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        grant_task_list = soup.find("ul", {"id": "grant-tasks"})
        task_items = grant_task_list.find_all("li", {"class": "govuk-task-list__item"})
        mark_as_onboarding_task = task_items[0]
        set_privacy_policy = task_items[1]
        make_grant_live_task = task_items[2]

        task_status = mark_as_onboarding_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Completed" in task_status.get_text(strip=True)
        assert "govuk-tag--green" in task_status.get("class")

        task_status = set_privacy_policy.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Completed" in task_status.get_text(strip=True)
        assert "govuk-tag--green" in task_status.get("class")

        task_title = make_grant_live_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert "Make the grant live" in task_title.get_text(strip=True)

        task_link = make_grant_live_task.find("a", {"class": "govuk-link"})
        assert task_link is None

        task_status = make_grant_live_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Completed" in task_status.get_text(strip=True)
        assert "govuk-tag--green" in task_status.get("class")

    def test_get_tasklist_with_dates_set(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Draft Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            reporting_period_start_date=datetime.date(2025, 1, 1),
            reporting_period_end_date=datetime.date(2025, 4, 1),
            submission_period_start_date=datetime.date(2025, 4, 1),
            submission_period_end_date=datetime.date(2025, 4, 30),
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
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
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session, collection_status
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report", status=collection_status)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        collection_task_list = soup.find("ul", {"id": "report-tasks"})
        collection_task_items = collection_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_emails_task = collection_task_items[5]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send emails to data providers"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        link = send_emails_task.find("a", {"class": "govuk-link"})
        assert link is None

    def test_send_emails_task_do_once_when_open(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report", status=CollectionStatusEnum.OPEN)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_emails_task = report_task_items[5]
        task_title = send_emails_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send emails to data providers"
        assert (
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/collection-open-notification"
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
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session, collection_status
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report", status=collection_status)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_emails_task = report_task_items[6]
        task_title = send_emails_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send deadline reminder emails"

        task_status = send_emails_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        link = send_emails_task.find("a", {"class": "govuk-link"})
        assert link is None

    def test_send_deadline_reminder_emails_task_do_once_when_open(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report", status=CollectionStatusEnum.OPEN)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_emails_task = report_task_items[6]
        task_title = send_emails_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send deadline reminder emails"
        assert (
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/deadline-reminder"
            in task_title.get("href")
        )

        task_status = send_emails_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Do once" in task_status.get_text(strip=True)
        assert "govuk-tag--orange" in task_status.get("class")

    @pytest.mark.parametrize(
        "collection_status, submission_period_end_date",
        [
            (CollectionStatusEnum.DRAFT, None),
            (CollectionStatusEnum.SCHEDULED, None),
            (CollectionStatusEnum.OPEN, datetime.date(2099, 12, 31)),
        ],
    )
    def test_send_report_overdue_emails_task_cannot_start_yet(
        self,
        authenticated_platform_grant_lifecycle_manager_client,
        factories,
        db_session,
        collection_status,
        submission_period_end_date,
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=collection_status,
            submission_period_end_date=submission_period_end_date,
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_report_closed_task = report_task_items[7]
        task_title = send_report_closed_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send report overdue emails"

        task_status = send_report_closed_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        link = send_report_closed_task.find("a", {"class": "govuk-link"})
        assert link is None

    @pytest.mark.parametrize(
        "collection_status",
        [
            CollectionStatusEnum.OPEN,
        ],
    )
    def test_send_report_overdue_emails_task_do_once_when_overdue(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session, collection_status
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=collection_status,
            submission_period_end_date=datetime.date(2020, 1, 1),
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_report_closed_task = report_task_items[7]
        task_title = send_report_closed_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send report overdue emails"
        assert (
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/collection-overdue"
            in task_title.get("href")
        )

        task_status = send_report_closed_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Do once" in task_status.get_text(strip=True)
        assert "govuk-tag--orange" in task_status.get("class")

    @pytest.mark.parametrize(
        "collection_status",
        [
            CollectionStatusEnum.DRAFT,
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.OPEN,
        ],
    )
    def test_send_report_closed_notification_task_cannot_start_yet(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session, collection_status
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant, name="Q1 Report", status=collection_status)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_report_closed_notification_task = report_task_items[9]
        task_title = send_report_closed_notification_task.find("div", {"class": "govuk-task-list__name-and-hint"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send report closed emails"

        task_status = send_report_closed_notification_task.find("div", {"class": "govuk-task-list__status"})
        assert task_status is not None
        assert "Cannot start yet" in task_status.get_text(strip=True)
        assert "govuk-task-list__status--cannot-start-yet" in task_status.get("class")

        link = send_report_closed_notification_task.find("a", {"class": "govuk-link"})
        assert link is None

    def test_send_report_closed_notification_task_do_once_when_closed(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.CLOSED,
            submission_period_end_date=datetime.date(2020, 1, 1),
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        report_task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        send_report_closed_notification_task = report_task_items[9]
        task_title = send_report_closed_notification_task.find("a", {"class": "govuk-link"})
        assert task_title is not None
        assert task_title.get_text(strip=True) == "Send report closed emails"
        assert (
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/collection-closed-notification"
            in task_title.get("href")
        )

        task_status = send_report_closed_notification_task.find("strong", {"class": "govuk-tag"})
        assert task_status is not None
        assert "Do once" in task_status.get_text(strip=True)
        assert "govuk-tag--orange" in task_status.get("class")


class TestSendEmailsToRecipients:
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
    def test_send_emails_to_recipients_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            submission_period_end_date=datetime.date(2025, 10, 1),
        )
        closed_collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.CLOSED,
            submission_period_end_date=datetime.date(2025, 10, 1),
        )

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{CollectionAdminEmailTypeEnum.COLLECTION_OPEN_NOTIFICATION.value}"
        )
        assert response.status_code == expected_code
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{CollectionAdminEmailTypeEnum.DEADLINE_REMINDER.value}"
        )
        assert response.status_code == expected_code
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{CollectionAdminEmailTypeEnum.COLLECTION_OVERDUE.value}"
        )
        assert response.status_code == expected_code
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{closed_collection.id}/send-emails-to-data-providers/{CollectionAdminEmailTypeEnum.COLLECTION_CLOSED_NOTIFICATION.value}"
        )
        assert response.status_code == expected_code

    def test_send_emails_to_recipients_deadline_reminder_report_not_open(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.DRAFT,
            submission_period_end_date=datetime.date(2025, 10, 1),
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{CollectionAdminEmailTypeEnum.DEADLINE_REMINDER.value}"
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "collection_status, submission_period_end_date, expected_status",
        [
            (CollectionStatusEnum.DRAFT, datetime.date(2020, 1, 1), 404),
            (CollectionStatusEnum.SCHEDULED, datetime.date(2020, 1, 1), 404),
            (CollectionStatusEnum.OPEN, datetime.date(2020, 1, 1), 200),
            (CollectionStatusEnum.OPEN, datetime.date(2099, 1, 1), 404),
            (CollectionStatusEnum.CLOSED, datetime.date(2099, 1, 1), 404),
        ],
    )
    def test_send_emails_to_recipients_report_overdue_not_available(
        self,
        authenticated_platform_grant_lifecycle_manager_client,
        factories,
        db_session,
        collection_status,
        submission_period_end_date,
        expected_status,
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            submission_period_end_date=submission_period_end_date,
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{CollectionAdminEmailTypeEnum.COLLECTION_OVERDUE.value}"
        )
        assert response.status_code == expected_status

    @pytest.mark.parametrize(
        "collection_status, expected_status",
        [
            (CollectionStatusEnum.DRAFT, 404),
            (CollectionStatusEnum.SCHEDULED, 404),
            (CollectionStatusEnum.OPEN, 404),
            (CollectionStatusEnum.CLOSED, 200),
        ],
    )
    def test_send_emails_to_recipients_report_closed_not_available(
        self,
        authenticated_platform_grant_lifecycle_manager_client,
        factories,
        db_session,
        collection_status,
        expected_status,
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            submission_period_end_date=datetime.date(2020, 1, 1),
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{CollectionAdminEmailTypeEnum.COLLECTION_CLOSED_NOTIFICATION.value}"
        )
        assert response.status_code == expected_status

    @pytest.mark.parametrize(
        "email_type, report_status, expected_heading, template_id",
        [
            (
                CollectionAdminEmailTypeEnum.COLLECTION_OPEN_NOTIFICATION.value,
                CollectionStatusEnum.OPEN,
                "Send emails to data providers",
                "4fc8d831-e241-4648-a8d3-04fb1bd9193e",
            ),
            (
                CollectionAdminEmailTypeEnum.DEADLINE_REMINDER.value,
                CollectionStatusEnum.OPEN,
                "Send deadline reminder emails",
                "6e482561-e1dc-4d4d-8a9e-3b5ad8add968",
            ),
            (
                CollectionAdminEmailTypeEnum.COLLECTION_OVERDUE.value,
                CollectionStatusEnum.OPEN,
                "Send report overdue emails",
                "b11391b3-c589-48ae-a8a3-e2acaf951787",
            ),
            (
                CollectionAdminEmailTypeEnum.COLLECTION_CLOSED_NOTIFICATION.value,
                CollectionStatusEnum.CLOSED,
                "Send report closed emails",
                "b38d160d-800e-4b6a-b115-63ca7fc8975b",
            ),
        ],
    )
    def test_send_emails_to_recipients_page_content(
        self,
        authenticated_platform_grant_lifecycle_manager_client,
        factories,
        db_session,
        email_type,
        report_status,
        expected_heading,
        template_id,
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=report_status,
            submission_period_end_date=datetime.date(2025, 10, 1),
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/{email_type}"
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
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{email_type}"
            in download_button.get("href")
        )

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
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{CollectionAdminEmailTypeEnum.COLLECTION_OPEN_NOTIFICATION.value}"
        )
        assert response.status_code == expected_code
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{CollectionAdminEmailTypeEnum.DEADLINE_REMINDER.value}"
        )
        assert response.status_code == expected_code
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{CollectionAdminEmailTypeEnum.COLLECTION_OVERDUE.value}"
        )
        assert response.status_code == expected_code
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{CollectionAdminEmailTypeEnum.COLLECTION_CLOSED_NOTIFICATION.value}"
        )
        assert response.status_code == expected_code

    def test_download_csv_format_and_content_report_open(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{CollectionAdminEmailTypeEnum.COLLECTION_OPEN_NOTIFICATION.value}"
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert response.content_length > 0

        lines = response.text.splitlines()
        assert len(lines) == 4

        header = lines[0].split(",")
        assert "email_address" == header[0]
        assert "grant_name" == header[1]
        assert "collection_type_noun" == header[2]
        assert "organisation_name" == header[3]
        assert "submission_name" == header[4]
        assert "submission_deadline" == header[5]
        assert "grant_submission_url" == header[6]
        assert "is_test_data" == header[7]
        assert "requires_certification" == header[8]
        assert "submissions" == header[9]
        assert "unsubmitted_submissions" == header[10]

        assert "user1@org1.example.com" in lines[1]
        assert "user2@org1.example.com" in lines[2]
        assert "user3@org2.example.com" in lines[3]
        assert "user4@org3.example.com" not in response.text

        assert all("Test Grant" in line for line in lines[1:])
        assert all("report" in line for line in lines[1:])
        assert all("Q1 Report" in line for line in lines[1:])
        assert all("Wednesday 30 April 2025" in line for line in lines[1:])
        assert all(f"/grants/{grant.id}/collection/{collection.id}" in line for line in lines[1:])
        assert all(line.endswith(",,") for line in lines[1:])

    def test_download_csv_format_and_content_deadline_reminder(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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
            created_by=user_1,
            grant_recipient=gr1,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("answer 1"))],
            status=SubmissionStatusEnum.IN_PROGRESS,
        )

        # org 2 has submitted their report, so should not be in the list
        submission_2 = factories.submission.create(
            mode=SubmissionModeEnum.LIVE,
            collection=collection,
            created_by=user_3,
            grant_recipient=gr2,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("answer 2"))],
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
        submission_2.status = SubmissionStatusEnum.SUBMITTED
        assert SubmissionHelper(submission_2).status == SubmissionStatusEnum.SUBMITTED

        # org 3 has not started their report (has no submission) so should be in the list

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{CollectionAdminEmailTypeEnum.DEADLINE_REMINDER.value}"
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert response.content_length > 0

        lines = response.text.splitlines()
        assert len(lines) == 4

        header = lines[0].split(",")
        assert "email_address" == header[0]
        assert "grant_name" == header[1]
        assert "collection_type_noun" == header[2]
        assert "organisation_name" == header[3]
        assert "submission_name" == header[4]
        assert "submission_deadline" == header[5]
        assert "grant_submission_url" == header[6]
        assert "is_test_data" == header[7]
        assert "requires_certification" == header[8]
        assert "submissions" == header[9]
        assert "unsubmitted_submissions" == header[10]

        assert "user3@org2.example.com" not in response.text
        assert "user4@org2.example.com" not in response.text
        assert "user@org-other.example.com" not in response.text
        assert "user1@org1.example.com" in lines[1]
        assert "user2@org1.example.com" in lines[2]
        assert "user5@org3.example.com" in lines[3]

        assert all("Test Grant" in line for line in lines[1:])
        assert all("report" in line for line in lines[1:])
        assert all("Q1 Report" in line for line in lines[1:])
        assert all("Wednesday 30 April 2025" in line for line in lines[1:])
        assert all(f"/grants/{grant.id}/collection/{collection.id}" in line for line in lines[1:])
        assert all(line.endswith(",,") for line in lines[1:])

    def test_download_csv_format_and_content_report_closed(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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
            created_by=user_1,
            grant_recipient=gr1,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("answer 1"))],
            status=SubmissionStatusEnum.IN_PROGRESS,
        )

        # org 2 has submitted their report, so should not be in the list
        submission_2 = factories.submission.create(
            mode=SubmissionModeEnum.LIVE,
            collection=collection,
            created_by=user_3,
            grant_recipient=gr2,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("answer 2"))],
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
        submission_2.status = SubmissionStatusEnum.SUBMITTED

        # org 3 has not started their report (has no submission) so should be in the list

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{CollectionAdminEmailTypeEnum.COLLECTION_CLOSED_NOTIFICATION.value}"
        )

        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        assert response.content_length > 0

        lines = response.text.splitlines()
        assert len(lines) == 4

        header = lines[0].split(",")
        assert "email_address" == header[0]
        assert "grant_name" == header[1]
        assert "collection_type_noun" == header[2]
        assert "organisation_name" == header[3]
        assert "submission_name" == header[4]
        assert "submission_deadline" == header[5]
        assert "grant_submission_url" == header[6]
        assert "is_test_data" == header[7]
        assert "requires_certification" == header[8]
        assert "submissions" == header[9]
        assert "unsubmitted_submissions" == header[10]

        assert "user3@org2.example.com" not in response.text
        assert "user4@org2.example.com" not in response.text
        assert "user@org-other.example.com" not in response.text
        assert "user1@org1.example.com" in lines[1]
        assert "user2@org1.example.com" in lines[2]
        assert "user5@org3.example.com" in lines[3]

        assert all("Test Grant" in line for line in lines[1:])
        assert all("report" in line for line in lines[1:])
        assert all("Q1 Report" in line for line in lines[1:])
        assert all("Wednesday 30 April 2025" in line for line in lines[1:])
        assert all(f"/grants/{grant.id}/collection/{collection.id}" in line for line in lines[1:])
        assert all(line.endswith(",,") for line in lines[1:])

    def test_download_csv_multi_submission_collection(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.OPEN,
            allow_multiple_submissions=True,
            multiple_submissions_are_managed_by_service=True,
            reporting_period_start_date=datetime.date(2025, 1, 1),
            reporting_period_end_date=datetime.date(2025, 3, 31),
            submission_period_start_date=datetime.date(2025, 4, 1),
            submission_period_end_date=datetime.date(2025, 4, 30),
        )
        question = factories.question.create(
            form__collection=collection,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        collection.submission_name_question_id = question.id
        db_session.commit()

        org = factories.organisation.create(name="Organisation 1", can_manage_grants=False)
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=org)

        user = factories.user.create(email="user1@org1.example.com")
        factories.user_role.create(
            user=user, organisation=org, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        submitted_submission = factories.submission.create(
            mode=SubmissionModeEnum.LIVE,
            collection=collection,
            created_by=user,
            grant_recipient=grant_recipient,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Area Alpha"))],
        )
        factories.submission_event.create(
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
            submission=submitted_submission,
            related_entity_id=question.form.id,
            created_by=user,
        )
        factories.submission_event.create(
            event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
            submission=submitted_submission,
            created_by=user,
        )
        submitted_submission.status = SubmissionStatusEnum.SUBMITTED

        factories.submission.create(
            mode=SubmissionModeEnum.LIVE,
            collection=collection,
            created_by=user,
            grant_recipient=grant_recipient,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("Area Bravo"))],
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/send-emails-to-data-providers/download-csv/{CollectionAdminEmailTypeEnum.COLLECTION_OPEN_NOTIFICATION.value}"
        )

        assert response.status_code == 200

        reader = csv.DictReader(io.StringIO(response.text))
        rows = list(reader)
        assert len(rows) == 1

        row = rows[0]
        assert row["email_address"] == "user1@org1.example.com"
        assert "* Area Alpha" in row["submissions"]
        assert "* Area Bravo" in row["submissions"]
        assert "* Area Bravo" in row["unsubmitted_submissions"]
        assert "* Area Alpha" not in row["unsubmitted_submissions"]


class TestSetUpCertifiers:
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
    def test_set_up_global_certifiers_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers"
        )
        assert response.status_code == expected_code

    def test_get_set_up_global_certifiers_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Set up global certifiers"

        assert soup.find("textarea", {"id": "certifiers_data"}) is not None

    def test_get_shows_existing_certifiers(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Org", can_manage_grants=False)
        user = factories.user.create(name="John Doe", email="john.doe@example.com")
        factories.user_role.create(user=user, organisation=org, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "John Doe" in soup.text
        assert "john.doe@example.com" in soup.text

    def test_post_creates_user_and_adds_certifier_permission(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
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

    def test_post_with_multiple_certifiers(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Org 2", can_manage_grants=False)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
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

    def test_post_with_existing_user_upserts(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        existing_user = factories.user.create(email="existing@example.com", name="Old Name")

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
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

    def test_post_redirects_to_tasklist(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        factories.organisation.create(name="Test Organisation", can_manage_grants=False)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
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
        assert response.location == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

    def test_post_with_invalid_header_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
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

    def test_post_with_invalid_email_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        factories.organisation.create(name="Test Organisation", can_manage_grants=False)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
            data={
                "certifiers_data": (
                    "organisation-name\tfirst-name\tlast-name\temail-address\n"
                    "Test Organisation\tJohn\tDoe\tinvalid-email\n"
                    "Test Organisation\tJane\tSmith\tmostly-valid-email-with-smart’quote@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "Invalid email address(es): invalid-email, mostly-valid-email-with-smart’quote@example.com"
        )

    def test_post_with_invalid_organisation(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-global-certifiers",
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


class TestCollectionLifecycleMakeGrantLive:
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
    def test_confirm_page_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-live")
        assert response.status_code == expected_code

    def test_get_confirm_page_with_draft_grant(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-live"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test Grant Make grant live"

    def test_get_confirm_page_with_live_grant_redirects(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Already Live Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-live", follow_redirects=True
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Already Live Grant is already live")

    def test_post_makes_grant_live_with_enough_team_members(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.DRAFT, privacy_policy_markdown="hello")
        collection = factories.collection.create(grant=grant)
        factories.user_role.create(grant=grant, permissions=[RoleEnum.MEMBER])
        factories.user_role.create(grant=grant, permissions=[RoleEnum.ADMIN])

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-live",
            data={"submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(grant)
        assert grant.status == GrantStatusEnum.LIVE

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Test Grant is now live")

    def test_post_fails_without_enough_team_members(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.DRAFT)
        collection = factories.collection.create(grant=grant)
        factories.user_role.create(grant=grant, permissions=[RoleEnum.MEMBER])

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-live",
            data={"submit": "Make grant live"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        db_session.refresh(grant)
        assert grant.status == GrantStatusEnum.DRAFT

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Unable to make grant live")


class TestCollectionLifecycleMarkGrantAsOnboarding:
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
    def test_confirm_page_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/mark-as-onboarding")
        assert response.status_code == expected_code

    def test_get_confirm_page_with_draft_grant(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/mark-as-onboarding"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test Grant Mark grant as onboarding with Funding Service"

    @pytest.mark.parametrize("from_status", [GrantStatusEnum.ONBOARDING, GrantStatusEnum.LIVE])
    def test_get_confirm_page_with_live_grant_redirects(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session, from_status
    ):
        grant = factories.grant.create(name="Already Active Grant", status=from_status)
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/mark-as-onboarding", follow_redirects=True
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Already Active Grant is already marked as onboarding")

    def test_post_makes_grant_live_with_enough_team_members(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.DRAFT)
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/mark-as-onboarding",
            data={"submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(grant)
        assert grant.status == GrantStatusEnum.ONBOARDING

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Test Grant is now marked as onboarding.")


class TestManageOrganisations:
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
    def test_manage_organisations_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations")
        assert response.status_code == expected_code

    def test_get_manage_organisations_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Set up organisations"

        textarea = soup.find("textarea", {"id": "organisations_data"})
        assert textarea is not None
        assert "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n" in textarea.get_text()

    def test_post_creates_new_organisations(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        initial_count = get_organisation_count()
        initial_test_count = get_organisation_count(mode=OrganisationModeEnum.TEST)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tTest Department\tCentral Government\t01/01/2020\t\n"
            "E06000001\tTest Council\tUnitary Authority\t15/06/2021\t"
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Created or updated 2 organisations and 2 test organisations.")

        assert get_organisation_count() == initial_count + 2
        org1 = db_session.query(Organisation).filter_by(external_id="GB-GOV-123", mode=OrganisationModeEnum.LIVE).one()
        assert org1.name == "Test Department"
        assert org1.type == OrganisationType.CENTRAL_GOVERNMENT
        assert org1.status == OrganisationStatus.ACTIVE
        assert org1.active_date == datetime.date(2020, 1, 1)
        assert org1.retirement_date is None
        assert org1.iati_id == "GB-GOV-123"

        org2 = db_session.query(Organisation).filter_by(external_id="E06000001", mode=OrganisationModeEnum.LIVE).one()
        assert org2.name == "Test Council"
        assert org2.type == OrganisationType.UNITARY_AUTHORITY
        assert org2.status == OrganisationStatus.ACTIVE
        assert org2.active_date == datetime.date(2021, 6, 15)
        assert org2.retirement_date is None
        assert org2.ons_lad_id == "E06000001"

        assert get_organisation_count(mode=OrganisationModeEnum.TEST) == initial_test_count + 2
        org1 = db_session.query(Organisation).filter_by(external_id="GB-GOV-123", mode=OrganisationModeEnum.TEST).one()
        assert org1.name == "Test Department (test)"
        assert org1.type == OrganisationType.CENTRAL_GOVERNMENT
        assert org1.status == OrganisationStatus.ACTIVE
        assert org1.active_date == datetime.date(2020, 1, 1)
        assert org1.retirement_date is None

        org2 = db_session.query(Organisation).filter_by(external_id="E06000001", mode=OrganisationModeEnum.TEST).one()
        assert org2.name == "Test Council (test)"
        assert org2.type == OrganisationType.UNITARY_AUTHORITY
        assert org2.status == OrganisationStatus.ACTIVE
        assert org2.active_date == datetime.date(2021, 6, 15)
        assert org2.retirement_date is None

    def test_post_creates_charity_and_company_with_prefixed_external_ids(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "12345678\tTest Charity\tCharity\t01/01/2020\t\n"
            "87654321\tTest Company\tCompany\t15/06/2021\t"
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        charity = db_session.query(Organisation).filter_by(name="Test Charity", mode=OrganisationModeEnum.LIVE).one()
        assert charity.type == OrganisationType.CHARITY
        assert charity.external_id == "CC-12345678"
        assert charity.charity_commission_number == "12345678"

        company = db_session.query(Organisation).filter_by(name="Test Company", mode=OrganisationModeEnum.LIVE).one()
        assert company.type == OrganisationType.COMPANY
        assert company.external_id == "CH-87654321"
        assert company.companies_house_number == "87654321"

    def test_post_creates_charity_with_already_prefixed_id(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "CC-12345678\tPrefixed Charity\tCharity\t01/01/2020\t"
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        charity = (
            db_session.query(Organisation).filter_by(name="Prefixed Charity", mode=OrganisationModeEnum.LIVE).one()
        )
        assert charity.external_id == "CC-12345678"
        assert charity.charity_commission_number == "12345678"

    def test_post_updates_existing_organisations(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Created or updated 1 organisations and 1 test organisations.")

        assert get_organisation_count() == initial_count

        org = db_session.query(Organisation).filter_by(external_id="GB-GOV-123", mode=OrganisationModeEnum.LIVE).one()
        assert org.name == "Updated Name"
        org = db_session.query(Organisation).filter_by(external_id="GB-GOV-123", mode=OrganisationModeEnum.TEST).one()
        assert org.name == "Updated Name (test)"

    def test_post_creates_retired_organisation(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tRetired Department\tCentral Government\t01/01/2020\t31/12/2023"
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        org = db_session.query(Organisation).filter_by(external_id="GB-GOV-123", mode=OrganisationModeEnum.LIVE).one()
        assert org.status == OrganisationStatus.RETIRED
        assert org.retirement_date == datetime.date(2023, 12, 31)
        org = db_session.query(Organisation).filter_by(external_id="GB-GOV-123", mode=OrganisationModeEnum.TEST).one()
        assert org.status == OrganisationStatus.RETIRED
        assert org.retirement_date == datetime.date(2023, 12, 31)

    def test_post_creates_other_org_with_auto_generated_id(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "\tSome Other Org\tOther\t01/01/2020\t"
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        org = db_session.query(Organisation).filter_by(name="Some Other Org", mode=OrganisationModeEnum.LIVE).one()
        assert org.type == OrganisationType.OTHER
        assert org.external_id.startswith("FS-")
        assert len(org.external_id) == 12
        assert org.custom_code == org.external_id.removeprefix("FS-")
        assert len(org.custom_code) == 9
        assert org.custom_code.isdigit()

    def test_post_creates_other_org_with_explicit_fs_id(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "FS-MYCUSTOMID\tExplicit Other Org\tOther\t01/01/2020\t"
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        org = db_session.query(Organisation).filter_by(name="Explicit Other Org", mode=OrganisationModeEnum.LIVE).one()
        assert org.type == OrganisationType.OTHER
        assert org.external_id == "FS-MYCUSTOMID"
        assert org.custom_code == "MYCUSTOMID"

    def test_post_other_org_with_invalid_prefix_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "BADPREFIX-123\tBad Other Org\tOther\t01/01/2020\t"
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "does not start with 'FS-'")

    def test_post_with_invalid_header_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        tsv_data = "Wrong Header\nGB-GOV-123\tTest Department\tCentral Government\t01/01/2020\t"

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
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
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tTest Department\tInvalid Type\t01/01/2020\t"
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "The tab-separated data is not valid:")

    def test_post_with_invalid_date_format_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        tsv_data = (
            "organisation-id\torganisation-name\ttype\tactive-date\tretirement-date\n"
            "GB-GOV-123\tTest Department\tCentral Government\t2020-01-01\t"
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-organisations",
            data={"organisations_data": tsv_data, "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "The tab-separated data is not valid:")


class TestSetupGrantRecipients:
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
    def test_manage_grant_recipients_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients")
        assert response.status_code == expected_code

    def test_get_manage_grant_recipients_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.organisation.create(name="Org 2", can_manage_grants=False)
        factories.organisation.create(name="Org 3", can_manage_grants=False)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Set up grant recipients" in get_h1_text(soup)

        select_element = soup.find("select", {"id": "recipients"})
        assert select_element is not None

        options = select_element.find_all("option")
        option_texts = [opt.get_text(strip=True) for opt in options]

        assert "Org 1" in option_texts
        assert "Org 2" in option_texts
        assert "Org 3" in option_texts

    def test_get_excludes_grant_managing_organisations(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        from tests.models import _get_grant_managing_organisation

        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        grant_managing_org = _get_grant_managing_organisation()
        factories.organisation.create(name="Regular Org", can_manage_grants=False)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        select_element = soup.find("select", {"id": "recipients"})
        options = select_element.find_all("option")
        option_texts = [opt.get_text(strip=True) for opt in options]

        assert grant_managing_org.name not in option_texts
        assert "Regular Org" in option_texts

    def test_get_excludes_existing_grant_recipients(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.organisation.create(name="Org 2", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org1)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        select_element = soup.find("select", {"id": "recipients"})
        options = select_element.find_all("option")
        option_texts = [opt.get_text(strip=True) for opt in options]

        assert "Org 1" not in option_texts
        assert "Org 2" in option_texts

    def test_post_creates_grant_recipients(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False, with_matching_test_org=True)
        org2 = factories.organisation.create(name="Org 2", can_manage_grants=False, with_matching_test_org=True)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients",
            data={"recipients": [str(org1.id), str(org2.id)], "status": "awarded", "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup,
            (
                "Created 2 grant recipients and 2 test grant recipients. All existing grant team members have been"
                " set up as data providers/certifiers for the test grant recipients."
            ),
        )

        from app.common.data.interfaces.grant_recipients import get_grant_recipients

        grant_recipients = get_grant_recipients(grant)
        assert len(grant_recipients) == 2
        recipient_org_ids = {gr.organisation_id for gr in grant_recipients}
        assert org1.id in recipient_org_ids
        assert org2.id in recipient_org_ids
        assert all(gr.status == GrantRecipientStatusEnum.AWARDED for gr in grant_recipients)

        test_grant_recipients = get_grant_recipients(grant, mode=GrantRecipientModeEnum.TEST)
        assert len(test_grant_recipients) == 2
        test_recipient_org_ids = {gr.organisation_id for gr in test_grant_recipients}
        assert org1.matching_test_organisation.id in test_recipient_org_ids
        assert org2.matching_test_organisation.id in test_recipient_org_ids

    def test_post_sets_up_grant_team_members_in_test_grant_recipients(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False, with_matching_test_org=True)
        test_org1 = get_organisations(mode=OrganisationModeEnum.TEST, with_external_ids=[org1.external_id])[0]
        org2 = factories.organisation.create(name="Org 2", can_manage_grants=False, with_matching_test_org=True)
        test_org2 = get_organisations(mode=OrganisationModeEnum.TEST, with_external_ids=[org2.external_id])[0]
        team_member1 = factories.user.create()
        factories.user_role.create(
            user=team_member1,
            organisation=_get_grant_managing_organisation(),
            grant=grant,
            permissions=[RoleEnum.MEMBER],
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients",
            data={"recipients": [str(org1.id)], "status": "awarded", "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        user = get_user(team_member1.id)
        assert not any(
            r
            for r in user.roles
            if r.organisation == org1
            and r.grant == grant
            and RoleEnum.DATA_PROVIDER in r.permissions
            and RoleEnum.CERTIFIER in r.permissions
        ), "Should not be added to the live grant recipient organisation"
        assert any(
            r
            for r in user.roles
            if r.organisation == test_org1
            and r.grant == grant
            and RoleEnum.DATA_PROVIDER in r.permissions
            and RoleEnum.CERTIFIER in r.permissions
        ), "Should be added to the test grant recipient organisation"
        assert not any(r for r in user.roles if r.organisation == org2 and r.grant == grant), (
            "Should not be added to a non-grant-recipient organisation"
        )
        assert not any(r for r in user.roles if r.organisation == test_org2 and r.grant == grant), (
            "Should not be added to a non-grant-recipient test organisation"
        )

    def test_post_redirects_to_tasklist(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Org 1", can_manage_grants=False)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients",
            data={"recipients": [str(org.id)], "status": "applying", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

    def test_post_without_recipients_shows_validation_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        factories.organisation.create(name="Org 1", can_manage_grants=False)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients",
            data={"recipients": [], "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "This field is required.")

    def test_get_with_no_available_organisations_shows_empty_select(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        from tests.models import _get_grant_managing_organisation

        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        _get_grant_managing_organisation()

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-grant-recipients"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        select_element = soup.find("select", {"id": "recipients"})
        assert select_element is not None

        options = select_element.find_all("option")
        assert len(options) == 0


class TestAddIndividualDataProviders:
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
    def test_add_individual_data_providers_permissions(
        self, client_fixture, expected_code, request, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-individual-data-providers"
        )
        assert response.status_code == expected_code

    def test_get_add_individual_data_providers_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-individual-data-providers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Add a grant recipient data provider" in get_h1_text(soup)

        assert soup.find("select", {"id": "grant_recipient"}) is not None
        assert soup.find("input", {"id": "full_name"}) is not None
        assert soup.find("input", {"id": "email_address"}) is not None
        assert soup.find("input", {"id": "send_notification_email"}) is not None

    def test_post_creates_user_and_role(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-individual-data-providers",
            data={
                "grant_recipient": str(grant_recipient.id),
                "full_name": "John Doe",
                "email_address": "john@example.com",
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully added John Doe as a data provider.")

        user = get_user_by_email("john@example.com")
        assert user is not None
        assert user.name == "John Doe"
        assert len(user.roles) == 1
        assert RoleEnum.DATA_PROVIDER in user.roles[0].permissions
        assert user.roles[0].organisation_id == org.id
        assert user.roles[0].grant_id == grant.id

    def test_post_with_existing_user_upserts(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=org)
        existing_user = factories.user.create(email="existing@example.com", name="Old Name")

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-individual-data-providers",
            data={
                "grant_recipient": str(grant_recipient.id),
                "full_name": "New Name",
                "email_address": "existing@example.com",
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully added New Name as a data provider.")

        user = get_user_by_email("existing@example.com")
        assert user is not None
        assert user.id == existing_user.id
        assert user.name == "New Name"
        assert any(
            RoleEnum.DATA_PROVIDER in role.permissions and role.organisation_id == org.id and role.grant_id == grant.id
            for role in user.roles
        )

    def test_post_redirects_to_tasklist(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-individual-data-providers",
            data={
                "grant_recipient": str(grant_recipient.id),
                "full_name": "John Doe",
                "email_address": "john@example.com",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

    def test_post_with_invalid_email_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-individual-data-providers",
            data={
                "grant_recipient": str(grant_recipient.id),
                "full_name": "John Doe",
                "email_address": "invalid-email",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Invalid email address")

        assert get_user_by_email("invalid-email") is None

    def test_post_with_missing_grant_recipient_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-individual-data-providers",
            data={
                "grant_recipient": "",
                "full_name": "John Doe",
                "email_address": "john@example.com",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Select a grant recipient")

        assert get_user_by_email("john@example.com") is None

    def test_post_with_send_notification_email_sends_email(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session, mocker
    ):
        mock_send = mocker.patch("app.deliver_grant_funding.admin.views.notification_service.send_access_report_opened")

        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-individual-data-providers",
            data={
                "grant_recipient": str(grant_recipient.id),
                "full_name": "John Doe",
                "email_address": "john@example.com",
                "send_notification_email": "y",
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully added John Doe as a data provider and sent notification email.")

        mock_send.assert_called_once()
        call_kwargs = mock_send.call_args.kwargs
        assert call_kwargs["email_address"] == "john@example.com"
        assert call_kwargs["collection"] == collection
        assert call_kwargs["grant_recipient"] == grant_recipient

    def test_post_without_send_notification_email_does_not_send_email(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session, mocker
    ):
        mock_send = mocker.patch("app.deliver_grant_funding.admin.views.notification_service.send_access_report_opened")

        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        grant_recipient = factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-individual-data-providers",
            data={
                "grant_recipient": str(grant_recipient.id),
                "full_name": "John Doe",
                "email_address": "john@example.com",
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully added John Doe as a data provider.")

        mock_send.assert_not_called()


class TestAddBulkDataProviders:
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
    def test_add_bulk_data_providers_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers")
        assert response.status_code == expected_code

    def test_get_add_bulk_data_providers_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Set up grant recipient data providers" in get_h1_text(soup)

        assert soup.find("textarea", {"id": "users_data"}) is not None

    def test_post_creates_user_and_role(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers",
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

    def test_post_with_existing_user_upserts(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        existing_user = factories.user.create(email="existing@example.com", name="Old Name")

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers",
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

    def test_post_redirects_to_tasklist(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers",
            data={
                "users_data": (
                    "organisation-name\tfull-name\temail-address\nTest Organisation\tJohn Doe\tjohn@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

    def test_post_with_invalid_header_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers",
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
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers",
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
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Valid Org", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers",
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

    def test_post_creates_multiple_users(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Org 2", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers",
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

    def test_post_with_invalid_emails_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers",
            data={
                "users_data": (
                    "organisation-name\tfull-name\temail-address\n"
                    "Test Organisation\tJohn Doe\tinvalid-email\nTest Organisation\tJane Smith\talso-bad\n"
                    "Test Organisation\tJane Smith\tmostly-valid-email-with-smart’quote@example.com"
                ),
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "Invalid email address(es): invalid-email, also-bad, mostly-valid-email-with-smart’quote@example.com"
        )


class TestRevokeGrantRecipientDataProviders:
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
    def test_revoke_grant_recipient_data_providers_permissions(
        self, client_fixture, expected_code, request, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-recipient-data-providers"
        )
        assert response.status_code == expected_code

    def test_get_revoke_grant_recipient_data_providers_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Org 1", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="John Doe", email="john@example.com")
        factories.user_role.create(
            user=user, organisation=org, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-recipient-data-providers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Revoke grant recipient data providers"

        assert soup.find("select", {"id": "grant_recipients_data_providers"}) is not None

    def test_post_revokes_user_role(self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session):
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-recipient-data-providers",
            data={"grant_recipients_data_providers": [f"{user.id}|{org.id}"], "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully revoked access for 1 data provider.")

        assert db_session.query(UserRole).filter_by(id=user_role.id).first() is None

    def test_post_revokes_multiple_user_roles(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-recipient-data-providers",
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

    def test_post_redirects_to_set_up_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="John Doe", email="john@example.com")
        factories.user_role.create(
            user=user, organisation=org, grant=grant, permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER]
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-recipient-data-providers",
            data={"grant_recipients_data_providers": [f"{user.id}|{org.id}"], "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert (
            response.location
            == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/add-bulk-data-providers"
        )


class TestRevokeCertifiers:
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
    def test_revoke_global_certifiers_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers"
        )
        assert response.status_code == expected_code

    def test_get_revoke_global_certifiers_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        factories.organisation.create(name="Org 1")

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Revoke certifier"

        assert soup.find("select", {"id": "organisation_id"}) is not None
        assert soup.find("input", {"id": "email"}) is not None

    def test_post_revokes_certifier_permission(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers",
            data={"organisation_id": str(org.id), "email": "john@example.com", "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Successfully revoked certifier access for John Doe (john@example.com).")

        db_session.refresh(user_role)
        assert user_role.permissions == [RoleEnum.MEMBER]

    def test_post_with_nonexistent_user_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation")

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers",
            data={"organisation_id": str(org.id), "email": "nonexistent@example.com", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "User with email 'nonexistent@example.com' does not exist.")

    def test_post_with_non_certifier_user_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation")
        factories.user.create(name="John Doe", email="john@example.com")

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers",
            data={"organisation_id": str(org.id), "email": "john@example.com", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup, "User 'John Doe' (john@example.com) is not a global certifier for the selected organisation."
        )

    def test_post_redirects_to_set_up_global_certifiers_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation")
        user = factories.user.create(name="John Doe", email="john@example.com")
        factories.user_role.create(user=user, organisation=org, grant=None, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers",
            data={"organisation_id": str(org.id), "email": "john@example.com", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert (
            response.location
            == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-global-certifiers"
        )


class TestOverrideGrantCertifiers:
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
    def test_override_grant_certifiers_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers"
        )
        assert response.status_code == expected_code

    def test_get_override_grant_certifiers_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Override certifiers for this grant"

        assert soup.find("select", {"id": "organisation_id"}) is not None
        assert soup.find("input", {"id": "full_name"}) is not None
        assert soup.find("input", {"id": "email"}) is not None

    def test_organisation_dropdown_only_shows_grant_recipients(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org1 = factories.organisation.create(name="Recipient Org 1", can_manage_grants=False)
        org2 = factories.organisation.create(name="Recipient Org 2", can_manage_grants=False)
        factories.organisation.create(name="Non-Recipient Org", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org1)
        factories.grant_recipient.create(grant=grant, organisation=org2)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers"
        )

        soup = BeautifulSoup(response.data, "html.parser")
        select = soup.find("select", {"id": "organisation_id"})
        options = select.find_all("option")
        option_texts = [option.text.strip() for option in options if option.get("value")]

        assert "Recipient Org 1" in option_texts
        assert "Recipient Org 2" in option_texts
        assert "Non-Recipient Org" not in option_texts

    def test_post_creates_grant_specific_certifier_new_user(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers",
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
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="Jane Doe", email="jane.doe@example.com")

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers",
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

    def test_grant_id_is_set_in_user_role(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers",
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
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert "3 overrides" in soup.text

    def test_tasklist_excludes_test_org_certifiers_from_override_count(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        live_org = factories.organisation.create(can_manage_grants=False, with_matching_test_org=True)
        test_org = live_org.matching_test_organisation
        factories.grant_recipient.create(grant=grant, organisation=live_org)
        factories.grant_recipient.create(grant=grant, organisation=test_org, mode=GrantRecipientModeEnum.TEST)

        live_user = factories.user.create(email="live_certifier@example.com")
        test_user = factories.user.create(email="test_certifier@example.com")
        factories.user_role.create(user=live_user, organisation=live_org, grant=grant, permissions=[RoleEnum.CERTIFIER])
        factories.user_role.create(user=test_user, organisation=test_org, grant=grant, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert "1 override" in soup.text
        assert "2 overrides" not in soup.text

    def test_tasklist_deduplicates_data_provider_count(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        grant_recipient_1 = factories.grant_recipient.create(grant=grant)
        grant_recipient_2 = factories.grant_recipient.create(grant=grant)

        user = factories.user.create(email="shared_dp@example.com")
        factories.user_role.create(
            user=user,
            organisation=grant_recipient_1.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=user,
            organisation=grant_recipient_2.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert "1 data provider" in soup.text
        assert "2 data providers" not in soup.text

    def test_tasklist_shows_test_users_count(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        live_org = factories.organisation.create(can_manage_grants=False, with_matching_test_org=True)
        test_org = live_org.matching_test_organisation
        factories.grant_recipient.create(grant=grant, organisation=test_org, mode=GrantRecipientModeEnum.TEST)

        test_user = factories.user.create(email="test_dp@example.com")
        factories.user_role.create(
            user=test_user,
            organisation=test_org,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )

        soup = BeautifulSoup(response.data, "html.parser")
        assert "1 test user" in soup.text

    def test_existing_certifiers_section_shows_grant_specific_only(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers"
        )

        assert response.status_code == 200
        assert b"Grant Specific User" in response.data
        assert b"Org Level User" not in response.data

    def test_post_with_invalid_email(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers",
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

    def test_post_with_missing_organisation(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/override-grant-certifiers",
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
            ("authenticated_platform_grant_lifecycle_manager_client", 200),
            ("authenticated_platform_data_analyst_client", 403),
            ("authenticated_platform_member_client", 403),
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
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers"
        )
        assert response.status_code == expected_code

    def test_get_revoke_grant_override_certifiers_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        factories.grant_recipient.create(grant=grant)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Revoke grant-specific certifier"

        assert soup.find("select", {"id": "organisation_id"}) is not None
        assert soup.find("input", {"id": "email"}) is not None

    def test_post_successfully_revokes_grant_specific_certifier(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers",
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
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers",
            data={"organisation_id": str(org.id), "email": "john@example.com", "submit": "y"},
            follow_redirects=True,
        )

        db_session.refresh(org_level_role)
        db_session.refresh(user)
        assert RoleEnum.CERTIFIER in org_level_role.permissions
        assert len([r for r in user.roles if r.grant_id == grant.id and RoleEnum.CERTIFIER in r.permissions]) == 0

    def test_post_with_nonexistent_user_shows_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers",
            data={"organisation_id": str(org.id), "email": "nonexistent@example.com", "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "User with email 'nonexistent@example.com' does not exist.")

    def test_post_with_user_without_grant_specific_permission(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Organisation", can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)
        user = factories.user.create(name="John Doe", email="john@example.com")
        factories.user_role.create(user=user, organisation=org, grant=None, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/revoke-grant-override-certifiers",
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
            ("authenticated_platform_grant_lifecycle_manager_client", 200),
            ("authenticated_platform_data_analyst_client", 403),
            ("authenticated_platform_member_client", 403),
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
        response = client.get(f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/schedule-collection")
        assert response.status_code == expected_code

    def test_get_confirm_page_with_prerequisites_met(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
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

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/schedule-collection"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test Grant Sign off and lock report"

    def test_post_schedules_collection(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/schedule-collection",
            data={"submit": "Sign off and lock collection"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Q1 Report is now locked")

    def test_post_fails_when_grant_recipients_have_no_users(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/schedule-collection",
            data={"submit": "Schedule report"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "All grant recipients must have at least one data provider set up before scheduling a "
            f"{collection.type.constants.singular}",
        )

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.DRAFT


class TestSetCollectionDatesStatusRestriction:
    @pytest.mark.parametrize(
        "endpoint_suffix,date_type",
        [
            ("set-reporting-dates", "reporting"),
            ("set-submission-dates", "submission"),
        ],
    )
    @pytest.mark.parametrize(
        "collection_status",
        [
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.CLOSED,
        ],
    )
    def test_get_set_dates_redirects_with_error_for_non_draft_status(
        self,
        authenticated_platform_grant_lifecycle_manager_client,
        factories,
        collection_status,
        endpoint_suffix,
        date_type,
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=collection_status,
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/{endpoint_suffix}",
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup,
            f"You cannot set {date_type} dates for Q1 Report because it is not in draft status.",
        )

    def test_get_set_reporting_dates_redirects_with_error_for_pre_award(
        self, authenticated_platform_grant_lifecycle_manager_client, factories
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            type=CollectionType.APPLICATION,
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-reporting-dates",
            follow_redirects=True,
        )

        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup,
            f"You cannot set reporting dates for {collection.name} because it is not a monitoring report",
        )

    @pytest.mark.parametrize(
        "endpoint_suffix,date_type,post_data",
        [
            (
                "set-reporting-dates",
                "reporting",
                {
                    "reporting_period_start_date-day": "1",
                    "reporting_period_start_date-month": "2",
                    "reporting_period_start_date-year": "2025",
                    "reporting_period_end_date-day": "1",
                    "reporting_period_end_date-month": "5",
                    "reporting_period_end_date-year": "2025",
                    "submit": "y",
                },
            ),
            (
                "set-submission-dates",
                "submission",
                {
                    "submission_period_start_date-day": "1",
                    "submission_period_start_date-month": "5",
                    "submission_period_start_date-year": "2025",
                    "submission_period_end_date-day": "31",
                    "submission_period_end_date-month": "5",
                    "submission_period_end_date-year": "2025",
                    "submit": "y",
                },
            ),
        ],
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
        self,
        authenticated_platform_grant_lifecycle_manager_client,
        factories,
        db_session,
        collection_status,
        endpoint_suffix,
        date_type,
        post_data,
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/{endpoint_suffix}",
            data=post_data,
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(collection)
        assert collection.reporting_period_start_date == datetime.date(2025, 1, 1)
        assert collection.reporting_period_end_date == datetime.date(2025, 4, 1)
        assert collection.submission_period_start_date == datetime.date(2025, 4, 1)
        assert collection.submission_period_end_date == datetime.date(2025, 4, 30)

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(
            soup,
            f"You cannot set {date_type} dates for Q1 Report because it is not in draft status.",
        )

    @pytest.mark.parametrize(
        "endpoint_suffix,expected_title",
        [
            ("set-reporting-dates", "Q1 Report Set reporting dates"),
            ("set-submission-dates", "Q1 Report Set submission dates"),
        ],
    )
    def test_get_set_dates_allows_draft_status(
        self,
        authenticated_platform_grant_lifecycle_manager_client,
        factories,
        endpoint_suffix,
        expected_title,
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.DRAFT,
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/{endpoint_suffix}",
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == expected_title

    @pytest.mark.parametrize(
        "collection_status",
        [
            CollectionStatusEnum.SCHEDULED,
            CollectionStatusEnum.OPEN,
            CollectionStatusEnum.CLOSED,
        ],
    )
    def test_tasklist_does_not_link_to_set_dates_for_non_draft_status(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session, collection_status
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

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
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
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.DRAFT,
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        report_task_list = soup.find("ul", {"id": "report-tasks"})
        task_items = report_task_list.find_all("li", {"class": "govuk-task-list__item"})

        reporting_dates_task = task_items[0]
        reporting_dates_link = reporting_dates_task.find("a", {"class": "govuk-link"})
        assert reporting_dates_link is not None
        assert (
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-reporting-dates"
            in reporting_dates_link.get("href")
        )

        submission_dates_task = task_items[1]
        submission_dates_link = submission_dates_task.find("a", {"class": "govuk-link"})
        assert submission_dates_link is not None
        assert (
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-submission-dates"
            in submission_dates_link.get("href")
        )


class TestMakeReportLive:
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
    def test_make_collection_live_permissions(self, client_fixture, expected_code, request, factories, db_session):
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
        response = client.get(f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live")
        assert response.status_code == expected_code

    def test_get_confirm_page_with_all_prerequisites_met(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test Grant Open the report for submissions"

        checkboxes = soup.find_all("input", {"type": "checkbox"})
        checkbox_labels = [" ".join(soup.find("label", {"for": cb["id"]}).stripped_strings) for cb in checkboxes]
        assert (
            "It is correct that this grant has 1 grant recipient set up and the grant team has reviewed this"
            in checkbox_labels
        )
        assert (
            "It is correct that this grant has 1 grant recipient user set up and the grant team has reviewed this"
            in checkbox_labels
        )
        assert "The privacy policy has been set up" in checkbox_labels
        assert "It is correct that the report has certification enabled" in checkbox_labels
        assert "The submission dates are 1 April 2024 until 30 April 2024" in checkbox_labels
        assert "It is correct that multiple submissions are disabled" in checkbox_labels

    def test_get_confirm_page_shows_conditional_checkboxes_for_managed_multiple_submissions(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.SCHEDULED,
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
            allow_multiple_submissions=True,
            multiple_submissions_are_managed_by_service=True,
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        checkboxes = soup.find_all("input", {"type": "checkbox"})
        checkbox_labels = [" ".join(soup.find("label", {"for": cb["id"]}).stripped_strings) for cb in checkboxes]
        assert "It is correct that multiple submissions are enabled" in checkbox_labels
        assert "It is correct that multiple submissions are managed by the service" in checkbox_labels
        assert "It is correct that this grant has 0 managed submissions set up" in checkbox_labels

    def test_get_confirm_page_hides_managed_submissions_count_when_not_managed(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.SCHEDULED,
            submission_period_start_date=datetime.date(2024, 4, 1),
            submission_period_end_date=datetime.date(2024, 4, 30),
            allow_multiple_submissions=True,
            multiple_submissions_are_managed_by_service=False,
        )
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        factories.user_role.create(
            user=user,
            organisation=grant_recipient.organisation,
            grant=grant,
            permissions=[RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER],
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        checkboxes = soup.find_all("input", {"type": "checkbox"})
        checkbox_labels = [" ".join(soup.find("label", {"for": cb["id"]}).stripped_strings) for cb in checkboxes]
        assert "It is correct that multiple submissions are enabled" in checkbox_labels
        assert "It is correct that multiple submissions are not managed by the service" in checkbox_labels
        assert not any("managed submissions set up" in label for label in checkbox_labels)

    def test_post_fails_when_checkboxes_not_confirmed(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.SCHEDULED,
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live",
            data={"submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        error_summary = soup.find("div", {"class": "govuk-error-summary"})
        assert error_summary is not None

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

    @pytest.mark.freeze_time("2024-04-01 10:00:00")
    def test_post_makes_collection_open(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live",
            data={
                "confirm_grant_recipients": "y",
                "confirm_grant_recipient_users": "y",
                "confirm_privacy_policy": "y",
                "confirm_certification": "y",
                "confirm_reporting_dates": "y",
                "confirm_submission_dates": "y",
                "confirm_reminder_days": "y",
                "confirm_multiple_submissions": "y",
                "submit": "y",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.OPEN

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Q1 Report is now live and grant recipients can start making submissions")

    def test_post_fails_when_grant_not_live(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live",
            data={
                "confirm_grant_recipients": "y",
                "confirm_grant_recipient_users": "y",
                "confirm_privacy_policy": "y",
                "confirm_certification": "y",
                "confirm_reporting_dates": "y",
                "confirm_submission_dates": "y",
                "confirm_reminder_days": "y",
                "confirm_multiple_submissions": "y",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, f"Test Grant must be made live before opening a {collection.type.constants.singular}"
        )

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

    def test_post_fails_when_no_grant_recipients(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live",
            data={
                "confirm_grant_recipients": "y",
                "confirm_grant_recipient_users": "y",
                "confirm_privacy_policy": "y",
                "confirm_certification": "y",
                "confirm_reporting_dates": "y",
                "confirm_submission_dates": "y",
                "confirm_reminder_days": "y",
                "confirm_multiple_submissions": "y",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, f"Grant recipients must be set up before opening a {collection.type.constants.singular}"
        )

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

    def test_post_fails_when_grant_recipients_have_no_users(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live",
            data={
                "confirm_grant_recipients": "y",
                "confirm_grant_recipient_users": "y",
                "confirm_privacy_policy": "y",
                "confirm_certification": "y",
                "confirm_reporting_dates": "y",
                "confirm_submission_dates": "y",
                "confirm_reminder_days": "y",
                "confirm_multiple_submissions": "y",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "All grant recipients must have at least one data provider set up before opening a "
            f"{collection.type.constants.singular}",
        )

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

    def test_post_fails_when_dates_not_set(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live",
            data={
                "confirm_grant_recipients": "y",
                "confirm_grant_recipient_users": "y",
                "confirm_privacy_policy": "y",
                "confirm_certification": "y",
                "confirm_reporting_dates": "y",
                "confirm_submission_dates": "y",
                "confirm_reminder_days": "y",
                "confirm_multiple_submissions": "y",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "Cannot change report status to Open: submission period dates must be set",
        )

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

    def test_post_fails_when_collection_not_scheduled(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/make-collection-live",
            data={
                "confirm_grant_recipients": "y",
                "confirm_grant_recipient_users": "y",
                "confirm_privacy_policy": "y",
                "confirm_certification": "y",
                "confirm_reporting_dates": "y",
                "confirm_submission_dates": "y",
                "confirm_reminder_days": "y",
                "confirm_multiple_submissions": "y",
                "submit": "Open collection for submissions",
            },
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Q1 Report can only be made live from the 'scheduled' state; it is currently")

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.DRAFT


class TestSetUpTestGrantRecipientUsers:
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
    def test_set_up_test_grant_recipient_users_permissions(
        self, client_fixture, expected_code, request, factories, db_session
    ):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        client = request.getfixturevalue(client_fixture)
        response = client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-test-grant-recipient-users"
        )
        assert response.status_code == expected_code

    def test_get_set_up_test_grant_recipient_users_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        org = factories.organisation.create(name="Test Org", can_manage_grants=False, mode=OrganisationModeEnum.TEST)
        factories.grant_recipient.create(grant=grant, organisation=org, mode=GrantRecipientModeEnum.TEST)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-test-grant-recipient-users"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Add form designers to test Access grant funding"

        assert soup.find("select", {"id": "grant_recipient"}) is not None
        assert soup.find("select", {"id": "mhclg_user"}) is not None

    def test_get_shows_only_test_grant_recipients(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        test_org = factories.organisation.create(
            name="Test Org", can_manage_grants=False, mode=OrganisationModeEnum.TEST
        )
        live_org = factories.organisation.create(
            name="Live Org", can_manage_grants=False, mode=OrganisationModeEnum.LIVE
        )
        factories.grant_recipient.create(grant=grant, organisation=test_org, mode=GrantRecipientModeEnum.TEST)
        factories.grant_recipient.create(grant=grant, organisation=live_org, mode=GrantRecipientModeEnum.LIVE)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-test-grant-recipient-users"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        select_element = soup.find("select", {"id": "grant_recipient"})
        options = select_element.find_all("option")
        option_texts = [opt.get_text(strip=True) for opt in options]

        assert "Test Org" in option_texts
        assert "Live Org" not in option_texts

    def test_post_adds_mhclg_user_as_data_provider(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        from tests.models import _get_grant_managing_organisation

        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        test_org = factories.organisation.create(
            name="Test Org", can_manage_grants=False, mode=OrganisationModeEnum.TEST
        )
        grant_recipient = factories.grant_recipient.create(
            grant=grant, organisation=test_org, mode=GrantRecipientModeEnum.TEST
        )

        mhclg = _get_grant_managing_organisation()
        mhclg_user = factories.user.create(name="MHCLG User", email="mhclg.user@example.com")
        factories.user_role.create(user=mhclg_user, organisation=mhclg, grant=None, permissions=[RoleEnum.MEMBER])

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-test-grant-recipient-users",
            data={"grant_recipient": str(grant_recipient.id), "mhclg_user": str(mhclg_user.id), "submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, f"Added {mhclg_user.name} as a data provider for {test_org.name}")

        db_session.refresh(mhclg_user)
        data_provider_role = next(
            (
                role
                for role in mhclg_user.roles
                if role.organisation_id == test_org.id
                and role.grant_id == grant.id
                and RoleEnum.DATA_PROVIDER in role.permissions
            ),
            None,
        )
        assert data_provider_role is not None
        assert RoleEnum.DATA_PROVIDER in data_provider_role.permissions
        assert RoleEnum.CERTIFIER in data_provider_role.permissions

    def test_post_redirects_to_same_page(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        from tests.models import _get_grant_managing_organisation

        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        test_org = factories.organisation.create(
            name="Test Org", can_manage_grants=False, mode=OrganisationModeEnum.TEST
        )
        grant_recipient = factories.grant_recipient.create(
            grant=grant, organisation=test_org, mode=GrantRecipientModeEnum.TEST
        )

        mhclg = _get_grant_managing_organisation()
        mhclg_user = factories.user.create(name="MHCLG User", email="mhclg.user@example.com")
        factories.user_role.create(user=mhclg_user, organisation=mhclg, grant=None, permissions=[RoleEnum.MEMBER])

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-test-grant-recipient-users",
            data={"grant_recipient": str(grant_recipient.id), "mhclg_user": str(mhclg_user.id), "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert (
            response.location
            == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-test-grant-recipient-users"
        )

    def test_post_without_grant_recipient_shows_validation_error(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        from tests.models import _get_grant_managing_organisation

        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)

        mhclg = _get_grant_managing_organisation()
        mhclg_user = factories.user.create(name="MHCLG User", email="mhclg.user@example.com")
        factories.user_role.create(user=mhclg_user, organisation=mhclg, grant=None, permissions=[RoleEnum.MEMBER])

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-test-grant-recipient-users",
            data={"mhclg_user": str(mhclg_user.id), "submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Select a test grant recipient")

    def test_get_shows_existing_data_providers(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant")
        collection = factories.collection.create(grant=grant)
        test_org = factories.organisation.create(
            name="Test Org", can_manage_grants=False, mode=OrganisationModeEnum.TEST
        )
        factories.grant_recipient.create(grant=grant, organisation=test_org, mode=GrantRecipientModeEnum.TEST)
        user = factories.user.create(name="Existing Provider", email="existing@example.com")
        factories.user_role.create(
            user=user,
            organisation=test_org,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/set-up-test-grant-recipient-users"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Existing Provider" in soup.text
        assert "existing@example.com" in soup.text


class TestCloseReport:
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
    def test_close_collection_permissions(self, client_fixture, expected_code, request, factories, db_session):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
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
        response = client.get(f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/close-collection")
        assert response.status_code == expected_code

    def test_get_confirm_page_with_all_prerequisites_met(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.OPEN,
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

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/close-collection"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Close the report" in get_h1_text(soup)

    @pytest.mark.freeze_time("2024-05-01 10:00:00")
    def test_post_closes_report(self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.LIVE)
        question = factories.question.create(
            form__collection__grant=grant,
            form__collection__name="Q1 Report",
            form__collection__status=CollectionStatusEnum.OPEN,
            form__collection__reporting_period_start_date=datetime.date(2024, 1, 1),
            form__collection__reporting_period_end_date=datetime.date(2024, 3, 31),
            form__collection__submission_period_start_date=datetime.date(2024, 4, 1),
            form__collection__submission_period_end_date=datetime.date(2024, 4, 30),
        )
        collection = question.form.collection
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
        sub = factories.submission.create(
            collection=collection, answers=[FactoryAnswer(question, TextSingleLineAnswer("hi"))]
        )
        sub_submitted = factories.submission.create(
            collection=collection,
            status=SubmissionStatusEnum.SUBMITTED,
            answers=[FactoryAnswer(question, TextSingleLineAnswer("hi"))],
        )
        factories.submission_event.create(
            submission=sub_submitted,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
            related_entity_id=question.form_id,
        )
        factories.submission_event.create(submission=sub_submitted, event_type=SubmissionEventType.SUBMISSION_SUBMITTED)
        SubmissionHelper(sub_submitted)._sync_submission_data_and_status()
        assert sub_submitted.status == SubmissionStatusEnum.SUBMITTED

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/close-collection",
            data={"submit": "y"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert response.request.path == f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}"

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.CLOSED

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Q1 Report is now closed and grant recipients can make no more changes")

        db_session.refresh(sub)
        assert sub.status == SubmissionStatusEnum.NOT_SUBMITTED

        db_session.refresh(sub_submitted)
        assert SubmissionHelper(sub_submitted).status == SubmissionStatusEnum.SUBMITTED
        assert sub_submitted.status == SubmissionStatusEnum.SUBMITTED

    @pytest.mark.freeze_time("2024-05-01 10:00:00")
    def test_post_fails_when_grant_not_open(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/close-collection",
            data={"submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            f"{collection.name} can only be closed from the 'open' state; it is currently {collection.status.value}",
        )

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.SCHEDULED

    @pytest.mark.freeze_time("2024-04-20 10:00:00")
    def test_post_fails_when_submission_dates_not_passed(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        grant = factories.grant.create(name="Test Grant", status=GrantStatusEnum.ONBOARDING)
        collection = factories.collection.create(
            grant=grant,
            name="Q1 Report",
            status=CollectionStatusEnum.OPEN,
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

        response = authenticated_platform_grant_lifecycle_manager_client.post(
            f"/deliver/admin/collection-lifecycle/{grant.id}/{collection.id}/close-collection",
            data={"submit": "y"},
            follow_redirects=False,
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            (
                f"You cannot close the report for submissions before the submission period end "
                f"date of {collection.submission_period_end_date}"
            ),
        )

        db_session.refresh(collection)
        assert collection.status == CollectionStatusEnum.OPEN


class TestPlatformAdminDataAnalysis:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 403),
            ("authenticated_platform_data_analyst_client", 200),
            ("authenticated_platform_member_client", 403),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_data_analysis_index_permissions(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/data-analysis/")
        assert response.status_code == expected_code

    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 403),
            ("authenticated_platform_data_analyst_client", 200),
            ("authenticated_platform_member_client", 403),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_certification_events_csv_permissions(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/data-analysis/certification-events.csv")
        assert response.status_code == expected_code

    def test_data_analysis_index_page(self, authenticated_platform_data_analyst_client):
        response = authenticated_platform_data_analyst_client.get("/deliver/admin/data-analysis/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Data analysis"
        assert soup.find("a", href="/deliver/admin/data-analysis/certification-events.csv")

    def test_certification_events_csv_content(self, authenticated_platform_data_analyst_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        grant_recipient = factories.grant_recipient.create(grant=grant)
        user = factories.user.create()
        submission = factories.submission.create(
            collection=collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            created_by=user,
        )
        factories.submission_event.create(
            submission=submission,
            event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
            created_by=user,
            created_at_utc=datetime.datetime(2025, 6, 1, 10, 0, 0),
        )
        factories.submission_event.create(
            submission=submission,
            event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
            created_by=user,
            created_at_utc=datetime.datetime(2025, 7, 1, 12, 0, 0),
        )

        response = authenticated_platform_data_analyst_client.get(
            "/deliver/admin/data-analysis/certification-events.csv"
        )
        assert response.status_code == 200
        assert response.content_type == "text/csv; charset=utf-8"

        csv_content = response.data.decode("utf-8-sig")
        lines = csv_content.strip().splitlines()
        assert lines[0] == "Submission reference,Sent for certification at,Number of times sent for certification"
        assert len(lines) == 2
        row = lines[1].split(",")
        assert row[0] == submission.reference
        assert row[2] == "2"


class TestPlatformAdminSubmissionsView:
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
    def test_submission_list_permissions(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/submission/")
        assert response.status_code == expected_code

    def test_submission_list_shows_references(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        submission = factories.submission.create()

        response = authenticated_platform_grant_lifecycle_manager_client.get("/deliver/admin/submission/")
        assert response.status_code == 200
        assert submission.reference in response.data.decode()

    def test_submission_edit_is_disabled(
        self, authenticated_platform_grant_lifecycle_manager_client, factories, db_session
    ):
        submission = factories.submission.create()

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/submission/edit/?id={submission.id}",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_details_renders_timeline(
        self, authenticated_platform_grant_lifecycle_manager_client, submission_submitted
    ):
        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/submission/details/?id={submission_submitted.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        timeline = soup.find(class_="moj-timeline")
        assert timeline is not None
        assert len(timeline.find_all(class_="moj-timeline__item")) > 0

    def test_details_renders_empty_timeline(self, authenticated_platform_grant_lifecycle_manager_client, factories):
        submission = factories.submission.create(mode=SubmissionModeEnum.LIVE)

        response = authenticated_platform_grant_lifecycle_manager_client.get(
            f"/deliver/admin/submission/details/?id={submission.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        timeline = soup.find(class_="moj-timeline")
        assert timeline is not None
        assert len(timeline.find_all(class_="moj-timeline__item")) == 0


class TestPlatformAdminSubmissionEventView:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 403),
            ("authenticated_platform_data_analyst_client", 403),
            ("authenticated_platform_member_client", 403),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_submission_event_list_permissions(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/submissionevent/")
        assert response.status_code == expected_code

    def test_list_shows_event_type_and_submission_reference(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        event = factories.submission_event.create(event_type=SubmissionEventType.SUBMISSION_SUBMITTED)

        response = authenticated_platform_admin_client.get("/deliver/admin/submissionevent/")
        assert response.status_code == 200
        page = response.data.decode()
        assert SubmissionEventType.SUBMISSION_SUBMITTED in page
        assert event.submission.reference in page

    def test_edit_is_disabled(self, authenticated_platform_admin_client, factories, db_session):
        event = factories.submission_event.create()

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/submissionevent/edit/?id={event.id}",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_create_is_disabled(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get(
            "/deliver/admin/submissionevent/new/",
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_filter_by_submission_mode(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        collection = factories.collection.create(grant=grant)
        grant_recipient = factories.grant_recipient.create(grant=grant)

        live_submission = factories.submission.create(
            collection=collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
        )
        preview_submission = factories.submission.create(
            collection=collection,
            mode=SubmissionModeEnum.PREVIEW,
        )
        factories.submission_event.create(submission=live_submission)
        factories.submission_event.create(submission=preview_submission)

        response = authenticated_platform_admin_client.get("/deliver/admin/submissionevent/?flt0_0=LIVE")
        assert response.status_code == 200
        page = response.data.decode()
        assert live_submission.reference in page
        assert preview_submission.reference not in page

    def test_filter_by_event_type(self, authenticated_platform_admin_client, factories, db_session):
        completed_event = factories.submission_event.create(
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
        )
        submitted_event = factories.submission_event.create(
            event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
        )

        response = authenticated_platform_admin_client.get(
            "/deliver/admin/submissionevent/?flt2_2=SUBMISSION_SUBMITTED"
        )
        assert response.status_code == 200
        page = response.data.decode()
        assert submitted_event.submission.reference in page
        assert completed_event.submission.reference not in page


class TestPlatformAdminQuestionView:
    @pytest.mark.parametrize(
        "client_fixture, expected_code",
        [
            ("authenticated_platform_admin_client", 200),
            ("authenticated_platform_grant_lifecycle_manager_client", 403),
            ("authenticated_platform_data_analyst_client", 403),
            ("authenticated_platform_member_client", 403),
            ("authenticated_grant_admin_client", 403),
            ("authenticated_grant_member_client", 403),
            ("authenticated_no_role_client", 403),
            ("anonymous_client", 302),
        ],
    )
    def test_question_list_permissions(self, client_fixture, expected_code, request):
        client = request.getfixturevalue(client_fixture)
        response = client.get("/deliver/admin/question/")
        assert response.status_code == expected_code

    def test_list_shows_question_and_chain(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(name="Stargazer Grant")
        collection = factories.collection.create(grant=grant, name="Quarterly Report")
        form = factories.form.create(collection=collection, title="Project details")
        question = factories.question.create(form=form, name="project_name", text="Project name?")

        response = authenticated_platform_admin_client.get("/deliver/admin/question/")
        assert response.status_code == 200
        page = response.data.decode()
        assert question.name in page
        assert "Project name?" in page
        assert "Project details" in page
        assert "Quarterly Report" in page
        assert "Stargazer Grant" in page

    def test_list_excludes_groups(self, authenticated_platform_admin_client, factories, db_session):
        question = factories.question.create(name="visible_question")
        group = factories.group.create(name="hidden_group", form=question.form)

        response = authenticated_platform_admin_client.get("/deliver/admin/question/")
        assert response.status_code == 200
        page = response.data.decode()
        assert question.name in page
        assert group.name not in page

    def test_filter_by_grant_name(self, authenticated_platform_admin_client, factories, db_session):
        wanted_grant = factories.grant.create(name="Wanted Grant")
        unwanted_grant = factories.grant.create(name="Unwanted Grant")
        wanted_collection = factories.collection.create(grant=wanted_grant)
        unwanted_collection = factories.collection.create(grant=unwanted_grant)
        wanted_question = factories.question.create(form__collection=wanted_collection, name="wanted_question")
        unwanted_question = factories.question.create(form__collection=unwanted_collection, name="unwanted_question")

        response = authenticated_platform_admin_client.get("/deliver/admin/question/?flt2_2=Wanted+Grant")
        assert response.status_code == 200
        page = response.data.decode()
        assert wanted_question.name in page
        assert unwanted_question.name not in page

    def test_create_is_disabled(self, authenticated_platform_admin_client):
        response = authenticated_platform_admin_client.get("/deliver/admin/question/new/", follow_redirects=False)
        assert response.status_code == 302

    def test_delete_is_disabled(self, authenticated_platform_admin_client, factories, db_session):
        question = factories.question.create()
        response = authenticated_platform_admin_client.post(
            "/deliver/admin/question/delete/",
            data={"id": str(question.id)},
            follow_redirects=False,
        )
        assert response.status_code == 302

    def test_edit_form_renders_question_details_and_name_input(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        question = factories.question.create(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="Original text",
            hint="Original hint",
            name="original_name",
        )

        response = authenticated_platform_admin_client.get(f"/deliver/admin/question/edit/?id={question.id}")
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        assert soup.find("input", attrs={"name": "text"}) is None
        assert soup.find("input", attrs={"name": "hint"}) is None
        assert soup.find("input", attrs={"name": "data_type"}) is None

        summary = soup.find("dl", class_="govuk-summary-list")
        assert summary is not None
        details_text = summary.get_text()
        assert QuestionDataType.TEXT_SINGLE_LINE.value in details_text
        assert "Original text" in details_text
        assert "Original hint" in details_text

        name_field = soup.find("input", attrs={"name": "name"})
        assert name_field is not None and name_field.get("value") == "original_name"
        assert not name_field.has_attr("readonly")

    def test_edit_updates_name(self, authenticated_platform_admin_client, factories, db_session):
        question = factories.question.create(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="Untouched text",
            hint="Untouched hint",
            name="old_name",
        )
        original_slug = question.slug
        initial_audit_count = db_session.query(AuditEvent).count()

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/question/edit/?id={question.id}",
            data={"name": "new_name"},
            follow_redirects=False,
        )
        assert response.status_code == 302

        db_session.expire(question)
        assert question.name == "new_name"
        assert question.text == "Untouched text"
        assert question.hint == "Untouched hint"
        assert question.slug == original_slug

        assert db_session.query(AuditEvent).count() == initial_audit_count + 1
        audit_event = db_session.query(AuditEvent).order_by(AuditEvent.created_at_utc.desc()).first()
        assert audit_event.event_type == AuditEventType.PLATFORM_ADMIN_DB_EVENT
        assert audit_event.data["model_class"] == "Question"
        assert audit_event.data["action"] == "update"
        assert audit_event.data["model_id"] == str(question.id)
        assert audit_event.data["changes"]["name"]["old"] == "old_name"
        assert audit_event.data["changes"]["name"]["new"] == "new_name"
        assert audit_event.user_id == authenticated_platform_admin_client.user.id

    def test_edit_ignores_posted_text_and_hint(self, authenticated_platform_admin_client, factories, db_session):
        question = factories.question.create(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            text="Untouched text",
            hint="Untouched hint",
            name="original_name",
        )

        response = authenticated_platform_admin_client.post(
            f"/deliver/admin/question/edit/?id={question.id}",
            data={
                "text": "Bypass attempt",
                "hint": "Also a bypass",
                "name": "renamed",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302

        db_session.expire(question)
        assert question.text == "Untouched text"
        assert question.hint == "Untouched hint"
        assert question.name == "renamed"


class TestGrantRecipientChangeStatus:
    def test_change_status_action_appears_on_list_page(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        org = factories.organisation.create(can_manage_grants=False)
        factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.get("/deliver/admin/grantrecipient/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        action_button = soup.find("button", string=lambda t: t and "Change status" in t)
        assert action_button is not None

    def test_change_status_redirects_to_confirmation(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(can_manage_grants=False)
        gr = factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            "/deliver/admin/grantrecipient/action/",
            data={"action": "change_status", "rowid": str(gr.id), "url": "/deliver/admin/grantrecipient/"},
        )
        assert response.status_code == 302
        assert "_change_status=1" in response.location
        assert f"rowid={gr.id}" in response.location

    def test_change_status_redirect_preserves_filters(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(can_manage_grants=False)
        gr = factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.post(
            "/deliver/admin/grantrecipient/action/",
            data={
                "action": "change_status",
                "rowid": str(gr.id),
                "url": "/deliver/admin/grantrecipient/?flt0_0=some_filter",
            },
        )
        assert response.status_code == 302
        assert "flt0_0=some_filter" in response.location
        assert "_change_status=1" in response.location
        assert f"rowid={gr.id}" in response.location

    def test_confirmation_page_shows_radios(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(can_manage_grants=False)
        gr = factories.grant_recipient.create(grant=grant, organisation=org)

        response = authenticated_platform_admin_client.get(
            f"/deliver/admin/grantrecipient/?_change_status=1&rowid={gr.id}"
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        radios = soup.find_all("input", {"type": "radio", "name": "new_status"})
        assert len(radios) == 3

        radio_values = {r["value"] for r in radios}
        assert radio_values == {"applying", "allocated", "awarded"}

        banner = soup.find(class_="govuk-notification-banner")
        assert banner is not None
        assert "1 item(s) selected" in banner.get_text()

    def test_change_status_updates_grant_recipients(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        org_1 = factories.organisation.create(can_manage_grants=False)
        org_2 = factories.organisation.create(can_manage_grants=False)
        gr_1 = factories.grant_recipient.create(
            grant=grant, organisation=org_1, status=GrantRecipientStatusEnum.APPLYING
        )
        gr_2 = factories.grant_recipient.create(
            grant=grant, organisation=org_2, status=GrantRecipientStatusEnum.APPLYING
        )

        response = authenticated_platform_admin_client.post(
            "/deliver/admin/grantrecipient/action/",
            data={
                "action": "change_status",
                "rowid": [str(gr_1.id), str(gr_2.id)],
                "new_status": "awarded",
                "url": "/deliver/admin/grantrecipient/",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire_all()
        assert gr_1.status == GrantRecipientStatusEnum.AWARDED
        assert gr_2.status == GrantRecipientStatusEnum.AWARDED

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "2 grant recipient statuses changed to awarded")

    def test_change_status_creates_audit_events(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create()
        org = factories.organisation.create(can_manage_grants=False)
        gr = factories.grant_recipient.create(grant=grant, organisation=org, status=GrantRecipientStatusEnum.APPLYING)

        authenticated_platform_admin_client.post(
            "/deliver/admin/grantrecipient/action/",
            data={
                "action": "change_status",
                "rowid": str(gr.id),
                "new_status": "allocated",
                "url": "/deliver/admin/grantrecipient/",
            },
        )

        audit_events = db_session.execute(
            AuditEvent.__table__.select().where(AuditEvent.event_type == AuditEventType.PLATFORM_ADMIN_DB_EVENT)
        ).fetchall()
        assert len(audit_events) >= 1

    def test_change_status_with_invalid_status_shows_error(
        self, authenticated_platform_admin_client, factories, db_session
    ):
        grant = factories.grant.create()
        org = factories.organisation.create(can_manage_grants=False)
        gr = factories.grant_recipient.create(grant=grant, organisation=org, status=GrantRecipientStatusEnum.APPLYING)

        response = authenticated_platform_admin_client.post(
            "/deliver/admin/grantrecipient/action/",
            data={
                "action": "change_status",
                "rowid": str(gr.id),
                "new_status": "invalid_status",
                "url": "/deliver/admin/grantrecipient/",
            },
            follow_redirects=True,
        )
        assert response.status_code == 200

        db_session.expire(gr)
        assert gr.status == GrantRecipientStatusEnum.APPLYING

        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_flash(soup, "Invalid status selected")


class TestAdminDashboard:
    @pytest.mark.freeze_time("2026-06-15 12:00:00")
    def test_dashboard_shows_grant_stats(self, authenticated_platform_admin_client, factories, db_session):
        factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.grant.create(status=GrantStatusEnum.ONBOARDING)
        db_session.commit()

        response = authenticated_platform_admin_client.get("/deliver/admin/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Live grant" in soup.get_text()
        assert "Onboarding grant" in soup.get_text()

    @pytest.mark.freeze_time("2026-06-15 12:00:00")
    def test_dashboard_shows_collection_stats(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            name="Scheduled Collection",
            grant=grant,
            status=CollectionStatusEnum.SCHEDULED,
            submission_period_start_date=datetime.date(2026, 6, 18),
        )
        factories.collection.create(
            name="Open Collection",
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            submission_period_start_date=datetime.date(2026, 6, 5),
            submission_period_end_date=datetime.date(2026, 6, 25),
        )
        db_session.commit()

        response = authenticated_platform_admin_client.get("/deliver/admin/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Scheduled Collection" in soup.get_text()
        assert "Open Collection" in soup.get_text()

    @pytest.mark.freeze_time("2026-06-14 12:00:00")
    def test_dashboard_shows_overdue_collections(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            name="Overdue Collection",
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            submission_period_end_date=datetime.date(2026, 6, 13),
        )
        db_session.commit()

        response = authenticated_platform_admin_client.get("/deliver/admin/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "14 June 2026todaySend overdue emailsOverdue Collection" in soup.get_text(strip=True)

    @pytest.mark.freeze_time("2026-06-15 12:00:00")
    def test_dashboard_shows_upcoming_timeline(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            name="Opening Soon",
            grant=grant,
            status=CollectionStatusEnum.SCHEDULED,
            submission_period_start_date=datetime.date(2026, 6, 17),
        )
        factories.collection.create(
            name="Closing Soon",
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            submission_period_start_date=datetime.date(2026, 6, 5),
            submission_period_end_date=datetime.date(2026, 6, 18),
        )
        db_session.commit()

        response = authenticated_platform_admin_client.get("/deliver/admin/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "17 June 2026soonOpen for submissionsOpening Soon" in soup.get_text(strip=True)
        assert "19 June 2026soonSend overdue emailsClosing Soon" in soup.get_text(strip=True)

    @pytest.mark.freeze_time("2026-06-15 12:00:00")
    def test_dashboard_shows_today_tag(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            name="Opening Today",
            grant=grant,
            status=CollectionStatusEnum.SCHEDULED,
            submission_period_start_date=datetime.date(2026, 6, 15),
        )
        db_session.commit()

        response = authenticated_platform_admin_client.get("/deliver/admin/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        today_tags = soup.find_all("strong", class_="govuk-tag--green")
        assert any("today" in tag.get_text().lower() for tag in today_tags)

    @pytest.mark.freeze_time("2026-06-15 12:00:00")
    def test_dashboard_shows_send_reminder_emails(self, authenticated_platform_admin_client, factories, db_session):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        # Frozen to Monday 15 June 2026. Collection closes Tuesday 23 June.
        # 5 business days before 23 June = Tuesday 16 June (today) -> should appear.
        factories.collection.create(
            name="Needs Reminder",
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            submission_period_start_date=datetime.date(2026, 6, 1),
            submission_period_end_date=datetime.date(2026, 6, 23),
        )
        db_session.commit()

        response = authenticated_platform_admin_client.get("/deliver/admin/")
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "16 June 2026soonSend reminder emailsNeeds Reminder" in soup.get_text(strip=True)
