import logging
import uuid

import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.models import Collection, Form
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

        review_submissions_links = page_has_link(soup, "View 0 test submissions")
        assert review_submissions_links is not None
        assert review_submissions_links.get("href") == AnyStringMatching(
            r"/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}/submissions/test"
        )

        expected_links = [
            ("Add another monitoring report", AnyStringMatching(r"/grant/[a-z0-9-]{36}/set-up-report")),
            ("Add tasks", AnyStringMatching(r"/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}/add-task")),
            ("Change name", AnyStringMatching(r"/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}/change-name")),
            ("Delete", AnyStringMatching(r"/grant/[a-z0-9-]{36}/reports\?delete")),
        ]
        for expected_link in expected_links:
            link = page_has_link(soup, expected_link[0])
            assert (link is not None) is can_edit

            if can_edit:
                assert link.get("href") == expected_link[1]

    def test_get_hides_delete_link_with_submissions(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        factories.submission.create(collection=report, mode=SubmissionModeEnum.LIVE)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_report_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                report_id=report.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert not page_has_link(soup, "Delete")

    def test_get_with_delete_parameter_no_submissions(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_reports",
                grant_id=authenticated_grant_admin_client.grant.id,
                delete=report.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this report")

    @pytest.mark.parametrize(
        "client_fixture, can_delete",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_delete(self, request: FixtureRequest, client_fixture: str, can_delete: bool, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")

        form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = client.post(
            url_for("deliver_grant_funding.list_reports", grant_id=client.grant.id, delete=report.id),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/reports")

        deleted_report = db_session.get(Collection, (report.id, report.version))
        assert (deleted_report is None) == can_delete


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


class TestChangeReportName:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.change_report_name", grant_id=uuid.uuid4(), report_id=uuid.uuid4())
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
            url_for("deliver_grant_funding.change_report_name", grant_id=client.grant.id, report_id=report.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Test Report" in soup.text

    def test_get_with_delete_parameter_with_live_submissions(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        factories.submission.create(collection=report, mode=SubmissionModeEnum.LIVE)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_report_name",
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
            url_for("deliver_grant_funding.change_report_name", grant_id=client.grant.id, report_id=report.id),
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
                "deliver_grant_funding.change_report_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                report_id=report2.id,
            ),
            data=form.data,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A report with this name already exists")

    def test_update_name_when_delete_banner_showing_does_not_delete(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Original Name")

        form = SetUpReportForm(data={"name": "Updated Name"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_report_name",
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
            assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}")

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


class TestListReportTasks:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.list_report_tasks", grant_id=uuid.uuid4(), report_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_no_tasks(self, request: FixtureRequest, client_fixture: str, can_edit: bool, factories):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")

        response = client.get(
            url_for("deliver_grant_funding.list_report_tasks", grant_id=client.grant.id, report_id=report.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "This monitoring report has no tasks." in soup.text

        add_task_link = page_has_link(soup, "Add a task")
        assert (add_task_link is not None) is can_edit

        if add_task_link:
            expected_href = AnyStringMatching(r"/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}/add-task")
            assert add_task_link.get("href") == expected_href

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_with_tasks(self, request: FixtureRequest, client_fixture: str, can_edit: bool, factories):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        factories.form.create(section=report.sections[0], title="Organisation information")

        response = client.get(
            url_for("deliver_grant_funding.list_report_tasks", grant_id=client.grant.id, report_id=report.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Organisation information" in soup.text

        manage_task_link = page_has_link(soup, "Organisation information")
        add_another_task_list = page_has_link(soup, "Add another task")

        assert manage_task_link is not None
        assert (add_another_task_list is not None) is can_edit


class TestMoveTask:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_task",
                grant_id=uuid.uuid4(),
                form_id=uuid.uuid4(),
                direction="up",
            )
        )
        assert response.status_code == 404

    def test_400(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        forms = factories.form.create_batch(3, section=report.sections[0])

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_task",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=forms[0].id,
                direction="blah",
            )
        )
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "direction",
        ["up", "down"],
    )
    def test_move(self, authenticated_grant_admin_client, factories, db_session, direction):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        factories.form.reset_sequence()
        forms = factories.form.create_batch(3, section=report.sections[0])
        assert forms[1].title == "Form 1"

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_task",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=forms[1].id,
                direction=direction,
            )
        )
        assert response.status_code == 302

        if direction == "up":
            assert report.sections[0].forms[0].title == "Form 1"
        else:
            assert report.sections[0].forms[2].title == "Form 1"


class TestChangeFormName:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.change_form_name", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
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
        form = factories.form.create(section=report.sections[0], title="Organisation information")

        response = client.get(
            url_for("deliver_grant_funding.change_form_name", grant_id=client.grant.id, form_id=form.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Organisation information" in soup.text

    def test_get_blocked_if_live_submissions(self, authenticated_grant_admin_client, factories, caplog):
        form = factories.form.create(
            section__collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        factories.submission.create(mode=SubmissionModeEnum.LIVE, collection=form.section.collection)

        with caplog.at_level(logging.INFO):
            response = authenticated_grant_admin_client.get(
                url_for(
                    "deliver_grant_funding.change_form_name",
                    grant_id=authenticated_grant_admin_client.grant.id,
                    form_id=form.id,
                )
            )

        assert response.status_code == 403
        assert any(
            message
            == AnyStringMatching(
                r"^Blocking access to manage form [a-z0-9-]{36} because related collection has live submissions"
            )
            for message in caplog.messages
        )

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
        db_form = factories.form.create(section__collection__grant=client.grant, title="Organisation information")

        form = AddTaskForm(data={"title": "Updated Name"})
        response = client.post(
            url_for("deliver_grant_funding.change_form_name", grant_id=client.grant.id, form_id=db_form.id),
            data=form.data,
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/questions")

            updated_form = db_session.get(Form, db_form.id)
            assert updated_form.title == "Updated Name"

    def test_post_update_name_duplicate(self, authenticated_grant_admin_client, factories):
        db_form = factories.form.create(
            section__collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_form2 = factories.form.create(section=db_form.section, title="Project information")

        form = AddTaskForm(data={"title": "Organisation information"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_form_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=db_form2.id,
            ),
            data=form.data,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A task with this name already exists")


class TestListTaskQuestions:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.list_task_questions", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_admin_actions(self, request, client_fixture, can_edit, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        factories.question.create_batch(2, form=form)

        response = client.get(
            url_for("deliver_grant_funding.list_task_questions", grant_id=client.grant.id, form_id=form.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Organisation information"

        change_task_name_link = page_has_link(soup, "Change task name")
        delete_task_link = page_has_link(soup, "Delete task")

        assert (change_task_name_link is not None) is can_edit
        assert (delete_task_link is not None) is can_edit

        if can_edit:
            assert change_task_name_link.get("href") == AnyStringMatching(
                "/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/change-name"
            )
            assert delete_task_link.get("href") == AnyStringMatching(r"\?delete")

    def test_delete_confirmation_banner(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_task_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this task")

    def test_cannot_delete_with_live_submissions(self, authenticated_grant_admin_client, factories, db_session, caplog):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        factories.submission.create(collection=report, mode=SubmissionModeEnum.LIVE)

        with caplog.at_level(logging.INFO):
            response = authenticated_grant_admin_client.post(
                url_for(
                    "deliver_grant_funding.list_task_questions",
                    grant_id=authenticated_grant_admin_client.grant.id,
                    form_id=form.id,
                    delete="",
                )
            )

        assert response.status_code == 403
        assert any(
            message
            == AnyStringMatching(
                r"^Blocking access to delete form [a-z0-9-]{36} because related collection has live submissions"
            )
            for message in caplog.messages
        )


class TestMoveQuestion:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_question",
                grant_id=uuid.uuid4(),
                question_id=uuid.uuid4(),
                direction="up",
            )
        )
        assert response.status_code == 404

    def test_no_access_for_grant_members(self, authenticated_grant_member_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        questions = factories.question.create_batch(3, form=form)

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.move_question",
                grant_id=authenticated_grant_member_client.grant.id,
                question_id=questions[0].id,
                direction="blah",
            )
        )
        assert response.status_code == 403

    def test_400(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        questions = factories.question.create_batch(3, form=form)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=questions[0].id,
                direction="blah",
            )
        )
        assert response.status_code == 400

    @pytest.mark.parametrize(
        "direction",
        ["up", "down"],
    )
    def test_move(self, authenticated_grant_admin_client, factories, db_session, direction):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        factories.question.reset_sequence()
        questions = factories.question.create_batch(3, form=form)
        assert form.questions[1].text == "Question 1"

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=questions[1].id,
                direction=direction,
            )
        )
        assert response.status_code == 302

        if direction == "up":
            assert form.questions[0].text == "Question 1"
        else:
            assert form.questions[2].text == "Question 1"


class TestListSubmissions:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=uuid.uuid4(),
                report_id=uuid.uuid4(),
                submission_mode=SubmissionModeEnum.TEST,
            )
        )
        assert response.status_code == 404

    def test_no_submissions(self, authenticated_grant_member_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test Report")

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                report_id=report.id,
                submission_mode=SubmissionModeEnum.TEST,
            )
        )
        assert response.status_code == 200
        assert "No submissions found for this monitoring report" in response.text

    def test_based_on_submission_mode(self, authenticated_grant_member_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test Report")
        factories.submission.create(
            collection=report, mode=SubmissionModeEnum.TEST, created_by__email="submitter-test@recipient.org"
        )
        factories.submission.create(
            collection=report, mode=SubmissionModeEnum.LIVE, created_by__email="submitter-live@recipient.org"
        )

        test_response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                report_id=report.id,
                submission_mode=SubmissionModeEnum.TEST,
            )
        )
        live_response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                report_id=report.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )
        test_soup = BeautifulSoup(test_response.data, "html.parser")
        live_soup = BeautifulSoup(live_response.data, "html.parser")
        assert test_response.status_code == 200
        assert live_response.status_code == 200

        # TODO: this should be an organisation name, when we have that concept
        test_recipient_link = page_has_link(test_soup, "submitter-test@recipient.org")
        live_recipient_link = page_has_link(live_soup, "submitter-live@recipient.org")
        assert test_recipient_link.get("href") == AnyStringMatching("/grant/[a-z0-9-]{36}/submission/[a-z0-9-]{36}")
        assert live_recipient_link.get("href") == AnyStringMatching("/grant/[a-z0-9-]{36}/submission/[a-z0-9-]{36}")


class TestExportReportSubmissions:
    def test_404(self, authenticated_grant_member_client, factories, db_session):
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.export_report_submissions",
                grant_id=uuid.uuid4(),
                report_id=uuid.uuid4(),
                submission_mode=SubmissionModeEnum.TEST,
                export_format="csv",
            )
        )
        assert response.status_code == 404

    def test_unknown_export_type(self, authenticated_grant_member_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test Report")
        factories.submission.create(
            collection=report, mode=SubmissionModeEnum.TEST, created_by__email="submitter-test@recipient.org"
        )
        factories.submission.create(
            collection=report, mode=SubmissionModeEnum.LIVE, created_by__email="submitter-live@recipient.org"
        )
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.export_report_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                report_id=report.id,
                submission_mode=SubmissionModeEnum.TEST,
                export_format="json",
            )
        )
        assert response.status_code == 400

    def test_csv_download(self, authenticated_grant_member_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_member_client.grant, name="Test Report")
        factories.submission.create(
            collection=report, mode=SubmissionModeEnum.TEST, created_by__email="submitter-test@recipient.org"
        )
        factories.submission.create(
            collection=report, mode=SubmissionModeEnum.LIVE, created_by__email="submitter-live@recipient.org"
        )
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.export_report_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                report_id=report.id,
                submission_mode=SubmissionModeEnum.TEST,
                export_format="csv",
            )
        )
        assert response.status_code == 200
        assert response.mimetype == "text/csv"
        # relying on testing for the internal implementation that we're generating a good CSV
        assert response.content_length > 0
        assert len(response.text.splitlines()) == 2  # Header + 1 submission


class TestViewSubmission:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.view_submission", grant_id=uuid.uuid4(), submission_id=uuid.uuid4())
        )
        assert response.status_code == 404

    def test_forms_and_questions_and_answers_displayed(self, authenticated_grant_member_client, factories, db_session):
        factories.data_source_item.reset_sequence()
        report = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_completed_submissions_each_question_type__test=1,
            create_completed_submissions_each_question_type__use_random_data=False,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.view_submission",
                grant_id=authenticated_grant_member_client.grant.id,
                submission_id=report.test_submissions[0].id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        assert "Export test form" in soup.text
        assert len(report.sections[0].forms[0].questions) == 8, "If more questions added, check+update this test"

        assert "What is your name?" in soup.text
        assert "test name" in soup.text

        assert "What is your quest?" in soup.text
        assert "Line 1\r\nline2\r\nline 3" in soup.text

        assert "What is the airspeed velocity of an unladen swallow?" in soup.text
        assert "123" in soup.text

        assert "What is the best option?" in soup.text
        assert "Option 0" in soup.text

        assert "Do you like cheese?" in soup.text
        assert "Yes" in soup.text

        assert "What is your email address?" in soup.text
        assert "test@email.com" in soup.text

        assert "What is your website address?" in soup.text
        assert (
            "https://www.gov.uk/government/organisations/ministry-of-housing-communities-local-government" in soup.text
        )
        assert "What are your favourite cheeses?" in soup.text
        assert "Cheddar" in soup.text
        assert "Stilton" in soup.text
