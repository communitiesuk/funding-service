import logging
import uuid

import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app import QuestionDataType
from app.common.data import interfaces
from app.common.data.models import Collection, Expression, Form, Group, Question
from app.common.data.types import ExpressionType, QuestionPresentationOptions, SubmissionModeEnum
from app.common.expressions.forms import build_managed_expression_form
from app.common.expressions.managed import GreaterThan, IsNo, IsYes
from app.common.forms import GenericConfirmDeletionForm, GenericSubmitForm
from app.deliver_grant_funding.forms import (
    AddGuidanceForm,
    AddTaskForm,
    GroupDisplayOptionsForm,
    GroupForm,
    QuestionForm,
    QuestionTypeForm,
    SetUpReportForm,
)
from tests.utils import AnyStringMatching, get_h1_text, get_h2_text, page_has_button, page_has_error, page_has_link


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

        review_submissions_links = page_has_link(soup, "0 test submissions")
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

    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_list_report_tasks_preview(
        self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        generic_grant = factories.grant.create()
        grant = getattr(client, "grant", None) or generic_grant

        report = factories.collection.create(grant=grant, name="Test Report")

        form = GenericSubmitForm()
        response = client.post(
            url_for("deliver_grant_funding.list_report_tasks", grant_id=grant.id, report_id=report.id),
            data=form.data,
            follow_redirects=False,
        )

        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/submissions/[a-z0-9-]{36}")


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


class TestChangeQuestionGroupName:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.change_group_name", grant_id=uuid.uuid4(), group_id=uuid.uuid4())
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
        group = factories.group.create(form=form, name="Test group")
        response = client.get(
            url_for("deliver_grant_funding.change_group_name", grant_id=client.grant.id, group_id=group.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "Test group" in soup.text

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        db_form = factories.form.create(
            section__collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group")

        form = GroupForm(data={"name": "Updated test group"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions")

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.name == "Updated test group"

    def test_post_duplicate(self, authenticated_grant_admin_client, factories):
        db_form = factories.form.create(
            section__collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        factories.group.create(form=db_form, name="Duplicate test group")
        db_group = factories.group.create(form=db_form, name="Test group")

        form = GroupForm(data={"name": "Duplicate test group"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A question group with this name already exists")


class TestChangeQuestionGroupDisplay:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.change_group_display_options", grant_id=uuid.uuid4(), group_id=uuid.uuid4())
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
        group = factories.group.create(
            form=form,
            name="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        response = client.get(
            url_for("deliver_grant_funding.change_group_display_options", grant_id=client.grant.id, group_id=group.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            # the correct option is selected based on whats in the database
            assert (
                soup.find(
                    "input",
                    {
                        "type": "radio",
                        "name": "show_questions_on_the_same_page",
                        "value": "all-questions-on-same-page",
                        "checked": True,
                    },
                )
                is not None
            )

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        db_form = factories.form.create(
            section__collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(
            form=db_form,
            name="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )

        assert db_group.presentation_options.show_questions_on_the_same_page is False

        form = GroupDisplayOptionsForm(data={"show_questions_on_the_same_page": "all-questions-on-same-page"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_display_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions")

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.presentation_options.show_questions_on_the_same_page is True

    def test_post_change_same_page_with_question_inter_dependencies(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_user = factories.user.create()
        db_form = factories.form.create(
            section__collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(
            form=db_form,
            name="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )
        db_question1 = factories.question.create(form=db_form, parent=db_group)
        _ = factories.question.create(
            form=db_form,
            parent=db_group,
            expressions=[
                Expression.from_managed(GreaterThan(question_id=db_question1.id, minimum_value=1000), db_user)
            ],
        )

        form = GroupDisplayOptionsForm(data={"show_questions_on_the_same_page": "all-questions-on-same-page"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_display_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "A question group cannot display on the same page if questions depend on answers within the group"
        )


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


class TestListGroupQuestions:
    def test_404(self, authenticated_grant_member_client, factories):
        report = factories.collection.create(grant=authenticated_grant_member_client.grant)
        form = factories.form.create(section=report.sections[0])
        question = factories.question.create(form=form)
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.list_group_questions", grant_id=uuid.uuid4(), group_id=uuid.uuid4())
        )
        assert response.status_code == 404

        # we don't load the group management page for any type of component
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=question.form.section.collection.grant.id,
                group_id=question.id,
            )
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
        group = factories.group.create(form=form, name="Test group", order=0)
        factories.question.create(form=form, parent=group, order=0)

        response = client.get(
            url_for("deliver_grant_funding.list_group_questions", grant_id=client.grant.id, group_id=group.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Test group"

        # todo: extend with "change name" and "question group settings"
        delete_group_link = page_has_link(soup, "Delete question group")

        assert (delete_group_link is not None) is can_edit

        if can_edit:
            assert delete_group_link.get("href") == AnyStringMatching(r"\?delete")

    def test_delete_confirmation_banner(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        group = factories.group.create(form=form, name="Test group", order=0)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this question group")

    def test_cannot_delete_with_depended_on_questions_in_group(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        user = factories.user.create()
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        group = factories.group.create(form=form, name="Test group", order=0)
        question = factories.question.create(form=form, parent=group, order=0, data_type=QuestionDataType.INTEGER)
        factories.question.create(
            form=form,
            order=1,
            expressions=[Expression.from_managed(GreaterThan(question_id=question.id, minimum_value=1000), user)],
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
                delete="",
            )
        )

        assert response.status_code == 302

        response = authenticated_grant_admin_client.get(response.location)
        soup = BeautifulSoup(response.data, "html.parser")
        assert "You cannot delete an answer that other questions depend on" in soup.text


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

    @pytest.mark.parametrize(
        "client_fixture, can_preview",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_member_client", True),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_list_task_questions_preview(
        self, request: FixtureRequest, client_fixture: str, can_preview: bool, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        generic_grant = factories.grant.create()
        grant = getattr(client, "grant", None) or generic_grant
        report = factories.collection.create(grant=grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        factories.question.create(form=form)

        preview_form = GenericSubmitForm()
        response = client.post(
            url_for("deliver_grant_funding.list_task_questions", grant_id=grant.id, form_id=form.id),
            data=preview_form.data,
            follow_redirects=False,
        )

        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching(
                "/grant/[a-z0-9-]{36}/submissions/[a-z0-9-]{36}/[a-z0-9-]{36}"
            )


class TestMoveQuestion:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=uuid.uuid4(),
                component_id=uuid.uuid4(),
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
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_member_client.grant.id,
                component_id=questions[0].id,
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
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=questions[0].id,
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
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=questions[1].id,
                direction=direction,
            )
        )
        assert response.status_code == 302

        if direction == "up":
            assert form.questions[0].text == "Question 1"
        else:
            assert form.questions[2].text == "Question 1"

    def test_move_group(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        group = factories.group.create(form=form, name="Test group", order=0)
        question1 = factories.question.create(parent=group, text="Question 1", order=0)
        factories.question.create(parent=group, text="Question 2", order=1)
        factories.question.create(form=form, text="Question 3", order=1)
        assert form.questions[0].text == "Question 1"

        # we can move the whole group on the form page
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=group.id,
                direction="down",
            )
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(r"/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/questions")

        assert form.questions[0].text == "Question 3"

        # we can move questions inside the group
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=question1.id,
                source=group.id,
                direction="down",
            )
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(r"/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions")

        assert form.questions[1].text == "Question 2"


class TestChooseQuestionType:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.choose_question_type", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ["authenticated_grant_member_client", False],
            ["authenticated_grant_admin_client", True],
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")

        response = client.get(
            url_for("deliver_grant_funding.choose_question_type", grant_id=client.grant.id, form_id=form.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "What type of question do you need?"

            assert len(soup.select("input[type=radio]")) == 8, "Should show an option for each kind of question"

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")

        form = QuestionTypeForm(data={"question_data_type": QuestionDataType.TEXT_SINGLE_LINE.name})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.choose_question_type",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=db_form.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/questions/add\?question_data_type=TEXT_SINGLE_LINE"
        )


class TestAddQuestion:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.add_question", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ["authenticated_grant_member_client", False],
            ["authenticated_grant_admin_client", True],
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")

        response = client.get(url_for("deliver_grant_funding.add_question", grant_id=client.grant.id, form_id=form.id))

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Add question"

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")

        form = QuestionForm(
            data={
                "text": "question",
                "hint": "hint text",
                "name": "question name",
            },
            question_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant.id,
                form_id=db_form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
            ),
            data=form.data,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}")

        # Stretching the test case a little but validates the flash message
        response = authenticated_grant_admin_client.get(response.location)
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Edit question"
        assert get_h2_text(soup) == "Question created"

    def test_post_add_to_group(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        group = factories.group.create(form=db_form, name="Test group", order=0)

        form = QuestionForm(
            data={
                "text": "question",
                "hint": "hint text",
                "name": "question name",
            },
            question_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant.id,
                form_id=db_form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
                parent_id=group.id,
            ),
            data=form.data,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}")

        # Stretching the test case a little but validates the group specific flash message
        response = authenticated_grant_admin_client.get(response.location)
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Edit question"
        assert get_h2_text(soup) == "Question created"
        assert page_has_link(soup, "Return to the question group")


class TestAddQuestionGroup:
    def test_404(self, authenticated_grant_admin_client, factories):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.add_question", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
        )
        assert response.status_code == 404

        # valid grant and form context but adding to a missing question group
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(section=report.sections[0])
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                parent_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    def test_missing_name(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant)
        db_form = factories.form.create(section=report.sections[0])

        form = GroupDisplayOptionsForm(
            data={
                "show_questions_on_the_same_page": "all-questions-on-same-page",
            },
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_group_display_options",
                grant_id=grant.id,
                form_id=db_form.id,
            ),
            data=form.data,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/groups/add")

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ["authenticated_grant_member_client", False],
            ["authenticated_grant_admin_client", True],
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")

        with client.session_transaction() as session:
            session["add_question_group"] = {"group_name": "Test group"}

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_group_display_options", grant_id=client.grant.id, form_id=form.id
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "How should the question group be displayed?"

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")

        with authenticated_grant_admin_client.session_transaction() as session:
            session["add_question_group"] = {"group_name": "Test group"}

        form = GroupDisplayOptionsForm(
            data={
                "show_questions_on_the_same_page": "all-questions-on-same-page",
            },
        )
        response = authenticated_grant_admin_client.post(
            url_for("deliver_grant_funding.add_question_group_display_options", grant_id=grant.id, form_id=db_form.id),
            data=form.data,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}")

    def test_post_duplicate(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        factories.group.create(form=db_form, name="Duplicate test group")

        form = GroupForm(
            data={
                "name": "Duplicate test group",
            },
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_group_name",
                grant_id=grant.id,
                form_id=db_form.id,
                name="Duplicate test group",
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A question group with this name already exists")


class TestEditQuestion:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.edit_question", grant_id=uuid.uuid4(), question_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ["authenticated_grant_member_client", False],
            ["authenticated_grant_admin_client", True],
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )

        response = client.get(
            url_for("deliver_grant_funding.edit_question", grant_id=client.grant.id, question_id=question.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Edit question"

            db_question = db_session.get(Question, question.id)
            assert db_question.text == "My question"
            assert db_question.name == "Question name"
            assert db_question.hint == "Question hint"
            assert db_question.data_type == QuestionDataType.TEXT_SINGLE_LINE

    def test_get_with_group(self, request, authenticated_grant_admin_client, factories, db_session):
        group = factories.group.create(
            form__section__collection__grant=authenticated_grant_admin_client.grant,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
            name="Test group",
        )
        question = factories.question.create(parent=group, form=group.form)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")

        # we link back to the parent group in the breadcrumbs
        assert page_has_link(soup, "Test group")

        # the option to edit guidance text is removed and we give a prompt for what you can do
        assert "This question is part of a group of questions that are all on the same page." in soup.text
        assert page_has_link(soup, "question group")

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )

        form = QuestionForm(
            data={
                "text": "Updated question",
                "hint": "Updated hint",
                "name": "Updated name",
            },
            question_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=question.id,
            ),
            data=form.data,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}")

    @pytest.mark.xfail
    def test_post_dependency_order_errors(self):
        # TODO: write me, followup PR, sorry
        # If you're a dev and you're looking at this please consider doing a kindness and taking 10 mins to write a nice
        # test here.
        raise AssertionError()

    @pytest.mark.xfail
    def test_post_data_source_item_errors(self):
        # TODO: write me, followup PR, sorry
        # If you're a dev and you're looking at this please consider doing a kindness and taking 10 mins to write a nice
        # test here.
        raise AssertionError()


class TestAddQuestionConditionSelectQuestion:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=uuid.uuid4(),
                component_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        group = factories.group.create(form=form, name="Test group")

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=client.grant.id,
                component_id=question.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "There are no questions in this form that can be used as a condition." in soup.text
            assert "The question" in soup.text

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=client.grant.id,
                component_id=group.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "There are no questions in this form that can be used as a condition." in soup.text
            assert "The question group" in soup.text

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_with_available_questions(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")

        factories.question.create(
            form=form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )

        second_question = factories.question.create(
            form=form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=client.grant.id,
                component_id=second_question.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "What answer should the condition check?" in soup.text
            assert "Do you like cheese? (cheese question)" in soup.text

    def test_post(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")

        first_question = factories.question.create(
            form=form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )

        second_question = factories.question.create(
            form=form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=second_question.id,
            ),
            data={"question": str(first_question.id)},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/grant/{authenticated_grant_admin_client.grant.id}/question/{second_question.id}/add-condition/{first_question.id}"
        )

    def test_post_rejects_same_page_group(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")

        group = factories.group.create(
            form=form,
            name="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        q1 = factories.question.create(
            form=form,
            parent=group,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )

        q2 = factories.question.create(
            form=form, parent=group, text="What is your email?", name="email question", data_type=QuestionDataType.EMAIL
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=q2.id,
            ),
            data={"question": str(q1.id)},
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.text, "html.parser")
        assert page_has_error(soup, "Select an answer that is not on the same page as this question")


class TestAddQuestionCondition:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=uuid.uuid4(),
                component_id=uuid.uuid4(),
                depends_on_question_id=uuid.uuid4(),
            )
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(section=report.sections[0], title="Organisation information")

        group = factories.group.create(
            form=form,
        )

        depends_on_question = factories.question.create(
            form=form,
            text="Do you like cheese?",
            name="cheese question",
            hint="Please select yes or no",
            data_type=QuestionDataType.YES_NO,
        )

        target_question = factories.question.create(
            form=form,
            text="What is your email?",
            name="email question",
            hint="Enter your email",
            data_type=QuestionDataType.EMAIL,
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=client.grant.id,
                component_id=target_question.id,
                depends_on_question_id=depends_on_question.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=client.grant.id,
                component_id=group.id,
                depends_on_question_id=depends_on_question.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")

        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            hint="Please select yes or no",
            data_type=QuestionDataType.YES_NO,
        )

        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            hint="Enter your email",
            data_type=QuestionDataType.EMAIL,
        )

        assert len(target_question.expressions) == 0

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question)
        form = ConditionForm(data={"type": "Yes"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                depends_on_question_id=depends_on_question.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type == ExpressionType.CONDITION
        assert expression.managed_name == "Yes"
        assert expression.managed.referenced_question.id == depends_on_question.id

    def test_post_for_group(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")

        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            hint="Please select yes or no",
            data_type=QuestionDataType.YES_NO,
        )

        target_group = factories.group.create(form=db_form)

        assert len(target_group.expressions) == 0

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question)
        form = ConditionForm(data={"type": "Yes"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_group.id,
                depends_on_question_id=depends_on_question.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/grant/{authenticated_grant_admin_client.grant.id}/group/{target_group.id}/questions"
        )

        assert len(target_group.expressions) == 1
        expression = target_group.expressions[0]
        assert expression.type == ExpressionType.CONDITION
        assert expression.managed_name == "Yes"
        assert expression.managed.referenced_question.id == depends_on_question.id

    def test_post_duplicate_condition(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")

        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            hint="Please select yes or no",
            data_type=QuestionDataType.YES_NO,
        )

        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            hint="Enter your email",
            data_type=QuestionDataType.EMAIL,
        )

        expression = IsYes(question_id=depends_on_question.id, referenced_question=depends_on_question)
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question)
        form = ConditionForm(data={"type": "Yes"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                depends_on_question_id=depends_on_question.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "condition based on this question already exists" in soup.text


class TestEditQuestionCondition:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.edit_question_condition", grant_id=uuid.uuid4(), expression_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )
        expression = IsYes(question_id=depends_on_question.id, referenced_question=depends_on_question)
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id

        response = client.get(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=client.grant.id,
                expression_id=expression_id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")

            assert get_h1_text(soup) == "Edit condition"

            assert "The question" in soup.text
            assert "What is your email?" in soup.text

            assert "Depends on the answer to" in soup.text
            assert "Do you like cheese?" in soup.text

            yes_radio = soup.find("input", {"type": "radio", "value": "Yes"})
            no_radio = soup.find("input", {"type": "radio", "value": "No"})
            assert yes_radio is not None
            assert no_radio is not None
            assert yes_radio.get("checked") is not None
            assert no_radio.get("checked") is None

            assert page_has_button(soup, "Save condition")

            delete_link = page_has_link(soup, "Delete condition")
            assert delete_link is not None

    def test_get_with_delete_parameter(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )
        expression = IsYes(question_id=depends_on_question.id, referenced_question=depends_on_question)
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this condition")

    def test_post_update_condition(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )
        expression = IsYes(question_id=depends_on_question.id, referenced_question=depends_on_question)
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert target_question.expressions[0].managed_name == "Yes"

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION, depends_on_question, target_question.expressions[0]
        )
        form = ConditionForm(data={"type": "No"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        assert target_question.expressions[0].managed_name == "No"

    def test_post_update_group_condition(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.group.create(form=db_form)
        expression = IsYes(question_id=depends_on_question.id, referenced_question=depends_on_question)
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert target_question.expressions[0].managed_name == "Yes"

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION, depends_on_question, target_question.expressions[0]
        )
        form = ConditionForm(data={"type": "No"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/grant/{authenticated_grant_admin_client.grant.id}/group/{target_question.id}/questions"
        )

        assert len(target_question.expressions) == 1
        assert target_question.expressions[0].managed_name == "No"

    def test_post_update_condition_duplicate(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )
        yes_expression = IsYes(question_id=depends_on_question.id, referenced_question=depends_on_question)
        interfaces.collections.add_component_condition(
            target_question, interfaces.user.get_current_user(), yes_expression
        )

        no_expression = IsNo(question_id=depends_on_question.id, referenced_question=depends_on_question)
        interfaces.collections.add_component_condition(
            target_question, interfaces.user.get_current_user(), no_expression
        )
        db_session.commit()

        assert len(target_question.expressions) == 2
        yes_expression_id = None
        for expr in target_question.expressions:
            if expr.managed_name == "Yes":
                yes_expression_id = expr.id
                break

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION, depends_on_question, target_question.expressions[0]
        )
        form = ConditionForm(data={"type": "No"})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=yes_expression_id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "condition based on this question already exists" in soup.text

    def test_post_delete(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        depends_on_question = factories.question.create(
            form=db_form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )
        target_question = factories.question.create(
            form=db_form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )
        expression = IsYes(question_id=depends_on_question.id, referenced_question=depends_on_question)
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert len(target_question.expressions) == 1

        form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
                delete="",
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 0


class TestAddQuestionValidation:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.add_question_validation", grant_id=uuid.uuid4(), question_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.INTEGER,
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=client.grant.id,
                question_id=question.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")

            assert get_h1_text(soup) == "Add validation"

            assert "Task" in soup.text
            assert "Organisation information" in soup.text

            assert "Question" in soup.text
            assert "How many employees do you have?" in soup.text

            greater_than_radio = soup.find("input", {"type": "radio", "value": "Greater than"})
            less_than_radio = soup.find("input", {"type": "radio", "value": "Less than"})
            between_radio = soup.find("input", {"type": "radio", "value": "Between"})
            assert greater_than_radio is not None
            assert less_than_radio is not None
            assert between_radio is not None

            assert page_has_button(soup, "Add validation")

    def test_get_no_validation_available(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="What is your name?",
            name="applicant name",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "This question cannot be validated." in soup.text

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.INTEGER,
        )

        assert len(question.expressions) == 0

        ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question)
        form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        assert len(question.expressions) == 1
        expression = question.expressions[0]
        assert expression.type == ExpressionType.VALIDATION
        assert expression.managed_name == "Greater than"

    def test_post_duplicate_validation(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.INTEGER,
        )

        ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question)
        first_validation = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        expression = first_validation.get_expression(question)
        interfaces.collections.add_question_validation(question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        duplicate_form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data=duplicate_form.data,
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "validation already exists on the question" in soup.text


class TestEditQuestionValidation:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.edit_question_validation", grant_id=uuid.uuid4(), expression_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.INTEGER,
        )

        ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question)
        form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        expression = form.get_expression(question)
        interfaces.collections.add_question_validation(question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        db_session.refresh(question)
        expression_id = question.expressions[0].id

        response = client.get(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=client.grant.id,
                expression_id=expression_id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")

            assert get_h1_text(soup) == "Edit validation"

            assert "Task" in soup.text
            assert "Organisation information" in soup.text

            assert "Question" in soup.text
            assert "How many employees do you have?" in soup.text

            greater_than_radio = soup.find("input", {"type": "radio", "value": "Greater than"})
            less_than_radio = soup.find("input", {"type": "radio", "value": "Less than"})
            between_radio = soup.find("input", {"type": "radio", "value": "Between"})
            assert greater_than_radio.get("checked") is not None
            assert less_than_radio.get("checked") is None
            assert between_radio.get("checked") is None

            min_value_input = soup.find("input", {"name": "greater_than_value"})
            assert min_value_input.get("value") == "10"

            assert page_has_button(soup, "Save validation")

            delete_link = page_has_link(soup, "Delete validation")
            assert delete_link is not None

    def test_get_with_delete_parameter(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.INTEGER,
        )

        ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question)
        form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        expression = form.get_expression(question)
        interfaces.collections.add_question_validation(question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        db_session.refresh(question)
        expression_id = question.expressions[0].id

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
                delete="",
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this validation")

    def test_post_update_validation(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.INTEGER,
        )

        ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question)
        original_form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        expression = original_form.get_expression(question)
        interfaces.collections.add_question_validation(question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = question.expressions[0].id
        assert question.expressions[0].managed_name == "Greater than"

        UpdateForm = build_managed_expression_form(ExpressionType.VALIDATION, question, question.expressions[0])
        form = UpdateForm(data={"type": "Less than", "less_than_value": "100", "less_than_inclusive": True})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        assert len(question.expressions) == 1
        assert question.expressions[0].managed_name == "Less than"

    def test_post_update_validation_duplicate(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.INTEGER,
        )

        ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question)
        greater_than_form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        greater_than_expression = greater_than_form.get_expression(question)
        interfaces.collections.add_question_validation(
            question, interfaces.user.get_current_user(), greater_than_expression
        )

        less_than_form = ValidationForm(
            data={"type": "Less than", "less_than_value": "100", "less_than_inclusive": True}
        )
        less_than_expression = less_than_form.get_expression(question)
        interfaces.collections.add_question_validation(
            question, interfaces.user.get_current_user(), less_than_expression
        )
        db_session.commit()

        assert len(question.expressions) == 2
        greater_than_expression_id = None
        for expr in question.expressions:
            if expr.managed_name == "Greater than":
                greater_than_expression_id = expr.id
                break

        UpdateForm = build_managed_expression_form(ExpressionType.VALIDATION, question, question.expressions[0])
        form = UpdateForm(data={"type": "Less than", "less_than_value": "100", "less_than_inclusive": True})

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=greater_than_expression_id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "validation already exists on the question" in soup.text

    def test_post_delete(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(section=report.sections[0], title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="How many employees do you have?",
            name="employee count",
            data_type=QuestionDataType.INTEGER,
        )

        ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, question)
        form = ValidationForm(
            data={"type": "Greater than", "greater_than_value": "10", "greater_than_inclusive": False}
        )
        expression = form.get_expression(question)
        interfaces.collections.add_question_validation(question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = question.expressions[0].id
        assert len(question.expressions) == 1

        delete_form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
                delete="",
            ),
            data=delete_form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        assert len(question.expressions) == 0


class TestManageGuidance:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.manage_guidance", grant_id=uuid.uuid4(), question_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_access_control(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        question = factories.question.create(form__section__collection__grant=client.grant)

        response = client.get(
            url_for("deliver_grant_funding.manage_guidance", grant_id=client.grant.id, question_id=question.id)
        )

        if can_access:
            assert response.status_code == 200
        else:
            assert response.status_code == 403

    def test_get_add_guidance(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(form__section__collection__grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Add guidance" in soup.text
        assert page_has_button(soup, "Save guidance")

    def test_get_edit_guidance(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(
            form__section__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Existing heading",
            guidance_body="Existing body",
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Edit guidance" in soup.text
        assert page_has_button(soup, "Save guidance")

    def test_post_add_guidance(self, authenticated_grant_admin_client, factories, db_session):
        question = factories.question.create(form__section__collection__grant=authenticated_grant_admin_client.grant)

        form = AddGuidanceForm(guidance_heading="How to answer", guidance_body="Please provide detailed information")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            f"/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == "How to answer"
        assert updated_question.guidance_body == "Please provide detailed information"

    def test_post_update_guidance(self, authenticated_grant_admin_client, factories, db_session):
        question = factories.question.create(
            form__section__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Old heading",
            guidance_body="Old body",
        )

        form = AddGuidanceForm(guidance_heading="Updated heading", guidance_body="Updated body")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}")

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == "Updated heading"
        assert updated_question.guidance_body == "Updated body"

    def test_post_clear_guidance(self, authenticated_grant_admin_client, factories, db_session):
        question = factories.question.create(
            form__section__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Existing heading",
            guidance_body="Existing body",
        )

        form = AddGuidanceForm(guidance_heading="", guidance_body="")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == ""
        assert updated_question.guidance_body == ""

    def test_post_guidance_with_heading_or_text_but_not_Both(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        question = factories.question.create(
            form__section__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Existing heading",
            guidance_body="Existing body",
        )

        form = AddGuidanceForm(guidance_heading="Existing heading", guidance_body="")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.text, "html.parser")
        assert page_has_error(soup, "Provide both a page heading and guidance text, or neither")

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == "Existing heading"
        assert updated_question.guidance_body == "Existing body"

    def test_get_edit_guidance_groups(self, authenticated_grant_admin_client, factories, db_session):
        group = factories.group.create(
            form__section__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Existing heading",
            guidance_body="Existing body",
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Edit guidance" in soup.text
        assert "Existing body" in soup.text

    def test_post_update_guidance_groups(self, authenticated_grant_admin_client, factories, db_session):
        group = factories.group.create(
            form__section__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Old heading",
            guidance_body="Old body",
        )

        form = AddGuidanceForm(guidance_heading="Updated heading", guidance_body="Updated body")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=group.id,
            ),
            data={k: v for k, v in form.data.items() if k not in ["preview"]},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions")

        updated_group = db_session.get(Group, group.id)
        assert updated_group.guidance_heading == "Updated heading"
        assert updated_group.guidance_body == "Updated body"


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
        report = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
            create_completed_submissions_each_question_type__test=1,
        )
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

        test_submission_tags = test_soup.select(".govuk-tag")
        live_submission_tags = live_soup.select(".govuk-tag")
        assert [tag.text.strip() for tag in test_submission_tags] == ["In progress", "Not started"]
        assert [tag.text.strip() for tag in live_submission_tags] == ["Not started"]


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
                export_format="zip",
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

    def test_json_download(self, authenticated_grant_member_client, factories, db_session):
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
        assert response.status_code == 200
        assert response.mimetype == "application/json"

        assert response.content_length > 0
        assert len(response.json["submissions"]) == 1


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
