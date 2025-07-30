import uuid

import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.models import Collection
from app.common.data.types import SubmissionModeEnum
from app.common.forms import GenericConfirmDeletionForm
from app.deliver_grant_funding.forms import AddTaskForm, SetUpReportForm
from tests.utils import AnyStringMatching, get_h1_text, page_has_button, page_has_error, page_has_link


class TestListReports:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.list_reports", grant_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_grant_member_get_no_reports(self, request: FixtureRequest, client_fixture: str, can_edit: bool, factories):
        client = request.getfixturevalue(client_fixture)

        response = client.get(url_for("deliver_grant_funding.list_reports", grant_id=client.grant.id))
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert client.grant.name in soup.text

        expected_links = [
            ("Add a monitoring report", AnyStringMatching(r"/grant/[a-z0-9-]{36}/set-up-report")),
        ]
        for expected_link in expected_links:
            button = page_has_link(soup, expected_link[0])
            assert (button is not None) is can_edit

            if can_edit:
                assert button.get("href") == expected_link[1]

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
            ("authenticated_platform_admin_client", True),
        ),
    )
    def test_grant_member_get_with_reports(
        self, request: FixtureRequest, client_fixture: str, can_edit: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant or factories.grant.create()
        factories.collection.create(grant=grant)

        response = client.get(url_for("deliver_grant_funding.list_reports", grant_id=grant.id))
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert grant.name in soup.text

        expected_links = [
            ("Add another monitoring report", AnyStringMatching(r"/grant/[a-z0-9-]{36}/set-up-report")),
            ("Add tasks", AnyStringMatching(r"/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}/add-task")),
            ("Manage", AnyStringMatching(r"/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}/manage")),
        ]
        for expected_link in expected_links:
            link = page_has_link(soup, expected_link[0])
            assert (link is not None) is can_edit

            if can_edit:
                assert link.get("href") == expected_link[1]


class TestSetUpReport:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.set_up_report", grant_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        factories.collection.create(grant=client.grant)

        response = client.get(url_for("deliver_grant_funding.set_up_report", grant_id=client.grant.id))

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert page_has_button(soup, "Continue and set up report")

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        assert len(client.grant.reports) == 0

        form = SetUpReportForm(data={"name": "Test monitoring report"})
        response = client.post(
            url_for("deliver_grant_funding.set_up_report", grant_id=client.grant.id),
            data=form.data,
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/reports")

            assert len(client.grant.reports) == 1
            assert client.grant.reports[0].name == "Test monitoring report"
            assert client.grant.reports[0].created_by == client.user

    def test_post_duplicate_report_name(self, authenticated_grant_admin_client, factories):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Monitoring report")

        form = SetUpReportForm(data={"name": "Monitoring report"})
        response = authenticated_grant_admin_client.post(
            url_for("deliver_grant_funding.set_up_report", grant_id=authenticated_grant_admin_client.grant.id),
            data=form.data,
        )
        soup = BeautifulSoup(response.data, "html.parser")

        assert response.status_code == 200
        assert page_has_error(soup, "A report with this name already exists")


class TestManageReport:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.manage_report", grant_id=uuid.uuid4(), report_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")

        response = client.get(
            url_for("deliver_grant_funding.manage_report", grant_id=client.grant.id, report_id=report.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Test Report" in soup.text

    def test_get_shows_delete_link_no_submissions(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_report",
                grant_id=authenticated_grant_admin_client.grant.id,
                report_id=report.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_link(soup, "Delete report")

    def test_get_hides_delete_link_with_submissions(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        factories.submission.create(collection=report, mode=SubmissionModeEnum.LIVE)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_report",
                grant_id=authenticated_grant_admin_client.grant.id,
                report_id=report.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert not page_has_link(soup, "Delete report")

    def test_get_with_delete_parameter_no_submissions(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_report",
                grant_id=authenticated_grant_admin_client.grant.id,
                report_id=report.id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this report")

    def test_get_with_delete_parameter_with_live_submissions(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        factories.submission.create(collection=report, mode=SubmissionModeEnum.LIVE)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_report",
                grant_id=authenticated_grant_admin_client.grant.id,
                report_id=report.id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert not page_has_button(soup, "Yes, delete this report")

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_update_name(
        self, request: FixtureRequest, client_fixture: str, can_access: bool, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Original Name")

        form = SetUpReportForm(data={"name": "Updated Name"})
        response = client.post(
            url_for("deliver_grant_funding.manage_report", grant_id=client.grant.id, report_id=report.id),
            data=form.data,
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/reports")

            updated_report = db_session.get(Collection, (report.id, report.version))
            assert updated_report.name == "Updated Name"

    def test_post_update_name_duplicate(self, authenticated_grant_admin_client, factories):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Existing Report")
        report2 = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Another Report")

        form = SetUpReportForm(data={"name": "Existing Report"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_report",
                grant_id=authenticated_grant_admin_client.grant.id,
                report_id=report2.id,
            ),
            data=form.data,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A report with this name already exists")

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_delete(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")

        form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = client.post(
            url_for("deliver_grant_funding.manage_report", grant_id=client.grant.id, report_id=report.id, delete=""),
            data=form.data,
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/reports")

            deleted_report = db_session.get(Collection, (report.id, report.version))
            assert deleted_report is None

    def test_update_name_when_delete_banner_showing_does_not_delete(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Original Name")

        form = SetUpReportForm(data={"name": "Updated Name"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_report",
                grant_id=authenticated_grant_admin_client.grant.id,
                report_id=report.id,
                delete="",
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/reports")

        updated_report = db_session.get(Collection, (report.id, report.version))
        assert updated_report is not None
        assert updated_report.name == "Updated Name"


class TestAddTask:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.add_task", grant_id=uuid.uuid4(), report_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant)

        response = client.get(url_for("deliver_grant_funding.add_task", grant_id=client.grant.id, report_id=report.id))

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "What is the name of the task?"

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant)

        form = AddTaskForm(data={"title": "Organisation information"})
        response = client.post(
            url_for("deliver_grant_funding.add_task", grant_id=client.grant.id, report_id=report.id),
            data=form.data,
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/reports")

            assert len(report.sections[0].forms) == 1
            assert report.sections[0].forms[0].title == "Organisation information"

    def test_post_duplicate_form_name(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Monitoring report")
        factories.form.create(section=report.sections[0], title="Organisation information")

        form = AddTaskForm(data={"title": "Organisation information"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_task",
                grant_id=authenticated_grant_admin_client.grant.id,
                report_id=report.id,
            ),
            data=form.data,
        )
        soup = BeautifulSoup(response.data, "html.parser")

        assert response.status_code == 200
        assert page_has_error(soup, "A task with this name already exists")
