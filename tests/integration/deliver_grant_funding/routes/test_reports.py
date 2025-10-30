import logging
import uuid
from datetime import date

import pytest
from _pytest.fixtures import FixtureRequest
from bs4 import BeautifulSoup
from flask import url_for

from app import QuestionDataType
from app.common.data import interfaces
from app.common.data.interfaces.collections import add_question_validation
from app.common.data.models import Collection, Expression, Form, Group, Question
from app.common.data.types import (
    ExpressionType,
    ManagedExpressionsEnum,
    QuestionPresentationOptions,
    SubmissionModeEnum,
)
from app.common.expressions import ExpressionContext
from app.common.expressions.forms import build_managed_expression_form
from app.common.expressions.managed import GreaterThan, IsAfter, IsNo, IsYes, LessThan
from app.common.forms import GenericConfirmDeletionForm, GenericSubmitForm
from app.deliver_grant_funding.forms import (
    AddGuidanceForm,
    AddTaskForm,
    GroupAddAnotherOptionsForm,
    GroupAddAnotherSummaryForm,
    GroupDisplayOptionsForm,
    GroupForm,
    QuestionForm,
    QuestionTypeForm,
    SetUpReportForm,
)
from app.deliver_grant_funding.session_models import (
    AddContextToComponentGuidanceSessionModel,
    AddContextToComponentSessionModel,
    AddContextToExpressionsModel,
)
from tests.utils import (
    AnyStringMatching,
    get_form_data,
    get_h1_text,
    get_h2_text,
    page_has_button,
    page_has_error,
    page_has_link,
)


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
            ("Add a monitoring report", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/set-up-report")),
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
            r"/deliver/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}/submissions/test"
        )

        expected_links = [
            ("Add another monitoring report", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/set-up-report")),
            ("Add tasks", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}/add-task")),
            ("Change name", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}/change-name")),
            ("Delete", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/reports\?delete")),
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/reports$")

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
            data=get_form_data(form),
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/reports$")

            assert len(client.grant.reports) == 1
            assert client.grant.reports[0].name == "Test monitoring report"
            assert client.grant.reports[0].created_by == client.user

    def test_post_duplicate_report_name(self, authenticated_grant_admin_client, factories):
        factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Monitoring report")

        form = SetUpReportForm(data={"name": "Monitoring report"})
        response = authenticated_grant_admin_client.post(
            url_for("deliver_grant_funding.set_up_report", grant_id=authenticated_grant_admin_client.grant.id),
            data=get_form_data(form),
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/reports$")

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
            data=get_form_data(form),
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/reports$")

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
            data=get_form_data(form),
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}$")

            assert len(report.forms) == 1
            assert report.forms[0].title == "Organisation information"

    def test_post_duplicate_form_name(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Monitoring report")
        factories.form.create(collection=report, title="Organisation information")

        form = AddTaskForm(data={"title": "Organisation information"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_task",
                grant_id=authenticated_grant_admin_client.grant.id,
                report_id=report.id,
            ),
            data=get_form_data(form),
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
            expected_href = AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/report/[a-z0-9-]{36}/add-task")
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
        factories.form.create(collection=report, title="Organisation information")

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
            data=get_form_data(form),
            follow_redirects=False,
        )

        if not can_preview:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/submissions/[a-z0-9-]{36}$")


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
        forms = factories.form.create_batch(3, collection=report)

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
        forms = factories.form.create_batch(3, collection=report)
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
            assert report.forms[0].title == "Form 1"
        else:
            assert report.forms[2].title == "Form 1"


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
        form = factories.form.create(collection=report, title="Organisation information")
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
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group")

        form = GroupForm(data={"name": "Updated test group"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.name == "Updated test group"

    def test_post_duplicate(self, authenticated_grant_admin_client, factories):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A question group with this name already exists")


class TestChangeGroupDisplayOptions:
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
        form = factories.form.create(collection=report, title="Organisation information")
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
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.presentation_options.show_questions_on_the_same_page is True

    def test_post_change_same_page_with_question_inter_dependencies(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_user = factories.user.create()
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "A question group cannot display on the same page if questions depend on answers within the group"
        )

    def test_post_change_same_page_with_internal_question_references(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_group = factories.group.create(
            name="Test group",
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=False),
        )
        db_question1 = factories.question.create(form=db_group.form, parent=db_group)
        factories.question.create(
            form=db_group.form,
            parent=db_group,
            text=f"Reference to (({db_question1.safe_qid}))",
        )

        form = GroupDisplayOptionsForm(data={"show_questions_on_the_same_page": "all-questions-on-same-page"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_display_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup, "A question group cannot display on the same page if questions depend on answers within the group"
        )


class TestChangeGroupAddAnotherOptions:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_group_add_another_options", grant_id=uuid.uuid4(), group_id=uuid.uuid4()
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
    def test_get(self, request: FixtureRequest, client_fixture: str, can_access: bool, factories):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", add_another=False)
        response = client.get(
            url_for(
                "deliver_grant_funding.change_group_add_another_options", grant_id=client.grant.id, group_id=group.id
            )
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
                        "name": "question_group_is_add_another",
                        "value": "no",
                        "checked": True,
                    },
                )
                is not None
            )

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group", add_another=False)

        assert db_group.add_another is False

        form = GroupAddAnotherOptionsForm(data={"question_group_is_add_another": "yes"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_add_another_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.add_another is True

    def test_post_is_blocked_if_group_contains_add_another(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group", add_another=False)
        factories.question.create(form=db_form, parent=db_group, add_another=True)

        assert db_group.add_another is False

        form = GroupAddAnotherOptionsForm(data={"question_group_is_add_another": "yes"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_add_another_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "A question group cannot be answered more than once if it already contains questions that can "
            "be answered more than once",
        )

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.add_another is False

    def test_post_is_blocked_if_group_is_inside_add_another(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group", add_another=True)
        factories.question.create(form=db_form, parent=db_group, add_another=True)
        db_group_2 = factories.group.create(form=db_form, name="Test group 2", add_another=False, parent=db_group)

        assert db_group_2.add_another is False

        form = GroupAddAnotherOptionsForm(data={"question_group_is_add_another": "yes"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_add_another_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group_2.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "A question group cannot be answered more than once if it is already inside a group that can be "
            "answered more than once",
        )

        updated_group = db_session.get(Group, db_group_2.id)
        assert updated_group.add_another is False

    def test_post_is_blocked_if_group_contains_depended_on_questions(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_group = factories.group.create(form=db_form, name="Test group", add_another=False)
        group_question = factories.question.create(form=db_form, parent=db_group)
        db_question = factories.question.create(form=db_form)

        add_question_validation(
            question=db_question,
            managed_expression=GreaterThan(question_id=group_question.id, minimum_value=100),
            user=factories.user.create(),
        )

        assert db_group.add_another is False

        form = GroupAddAnotherOptionsForm(data={"question_group_is_add_another": "yes"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_add_another_options",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=db_group.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(
            soup,
            "A question group cannot be answered more than once if questions elsewhere in the form depend "
            "on questions in this group",
        )

        updated_group = db_session.get(Group, db_group.id)
        assert updated_group.add_another is False


class TestChangeGroupAddAnotherSummaryQuestions:
    def test_get(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", add_another=True)
        q1 = factories.question.create(form=form, parent=group)
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.change_group_add_another_summary",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert (
            soup.find(
                "input",
                {
                    "type": "checkbox",
                    "name": "questions_to_show_in_add_another_summary",
                    "value": str(q1.id),
                    "checked": True,
                },
            )
            is not None
        )

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        group = factories.group.create(form=form, name="Test group", add_another=True)
        q1 = factories.question.create(form=form, parent=group)

        summary_form = GroupAddAnotherSummaryForm(
            group=group, data={"questions_to_show_in_add_another_summary": [str(q1.id)]}
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_group_add_another_summary",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data=get_form_data(summary_form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, group.id)
        assert updated_group.presentation_options.add_another_summary_line_question_ids == [q1.id]


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
        form = factories.form.create(collection=report, title="Organisation information")

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
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        factories.submission.create(mode=SubmissionModeEnum.LIVE, collection=form.collection)

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
        db_form = factories.form.create(collection__grant=client.grant, title="Organisation information")

        form = AddTaskForm(data={"title": "Updated Name"})
        response = client.post(
            url_for("deliver_grant_funding.change_form_name", grant_id=client.grant.id, form_id=db_form.id),
            data=get_form_data(form),
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 302
            assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/questions$")

            updated_form = db_session.get(Form, db_form.id)
            assert updated_form.title == "Updated Name"

    def test_post_update_name_duplicate(self, authenticated_grant_admin_client, factories):
        db_form = factories.form.create(
            collection__grant=authenticated_grant_admin_client.grant, title="Organisation information"
        )
        db_form2 = factories.form.create(collection=db_form.collection, title="Project information")

        form = AddTaskForm(data={"title": "Organisation information"})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.change_form_name",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=db_form2.id,
            ),
            data=get_form_data(form),
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A task with this name already exists")


class TestListGroupQuestions:
    def test_404(self, authenticated_grant_member_client, factories):
        report = factories.collection.create(grant=authenticated_grant_member_client.grant)
        form = factories.form.create(collection=report)
        question = factories.question.create(form=form)
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.list_group_questions", grant_id=uuid.uuid4(), group_id=uuid.uuid4())
        )
        assert response.status_code == 404

        # we don't load the group management page for any type of component
        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=question.form.collection.grant.id,
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
        form = factories.form.create(collection=report, title="Organisation information")
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
        add_question_group = page_has_link(soup, "Add a question group")

        assert (delete_group_link is not None) is can_edit
        assert (add_question_group is not None) is can_edit

        if can_edit:
            assert delete_group_link.get("href") == AnyStringMatching(r"\?delete")

    def test_get_shows_interpolated_questions(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")
        q1 = factories.question.create(form=form, name="my question name")
        group = factories.group.create(form=form, name="Test group", order=1)
        factories.question.create(form=form, parent=group, text=f"Reference to (({q1.safe_qid}))")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_group_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Reference to ((my question name))" in soup.text

    def test_delete_confirmation_banner(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")
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
        form = factories.form.create(collection=report, title="Organisation information")
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
        form = factories.form.create(collection=report, title="Organisation information")
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
                "/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/change-name"
            )
            assert delete_task_link.get("href") == AnyStringMatching(r"\?delete")

    def test_delete_confirmation_banner(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")

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

    def test_get_shows_interpolated_questions(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")
        q1 = factories.question.create(form=form, name="my question name")
        factories.question.create(form=form, text=f"Reference to (({q1.safe_qid}))")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_task_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )

        assert response.status_code == 200
        assert "Reference to ((my question name))" in response.text

    def test_cannot_delete_with_live_submissions(self, authenticated_grant_admin_client, factories, db_session, caplog):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")
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
        form = factories.form.create(collection=report, title="Organisation information")
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
                "/deliver/grant/[a-z0-9-]{36}/submissions/[a-z0-9-]{36}/[a-z0-9-]{36}"
            )

    def test_post_list_task_questions_returns_to_task_list(
        self, factories, db_session, authenticated_grant_admin_client
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")
        factories.question.create(form=form)

        preview_form = GenericSubmitForm()
        runner_response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.list_task_questions",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data=preview_form.data,
            follow_redirects=True,
        )
        soup = BeautifulSoup(runner_response.data, "html.parser")
        assert page_has_link(soup, "Back").get("href") == url_for(
            "deliver_grant_funding.list_task_questions",
            grant_id=authenticated_grant_admin_client.grant.id,
            form_id=form.id,
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
        form = factories.form.create(collection=report, title="Organisation information")
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
        form = factories.form.create(collection=report, title="Organisation information")
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
        form = factories.form.create(collection=report, title="Organisation information")
        factories.question.reset_sequence()
        questions = factories.question.create_batch(3, form=form)
        assert form.cached_questions[1].text == "Question 1"

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=questions[1].id,
                direction=direction,
            )
        )
        del form.cached_questions
        assert response.status_code == 302

        if direction == "up":
            assert form.cached_questions[0].text == "Question 1"
        else:
            assert form.cached_questions[2].text == "Question 1"

    # todo: think about if interfaces that update questions should also clear their forms
    #       cachce if it exists (for now we're just going to leave it and assume instances are
    #       loaded once per request)
    def test_move_group(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", order=0)
        question1 = factories.question.create(parent=group, text="Question 1", order=0)
        factories.question.create(parent=group, text="Question 2", order=1)
        factories.question.create(form=form, text="Question 3", order=1)
        assert form.cached_questions[0].text == "Question 1"

        # we can move the whole group on the form page
        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.move_component",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=group.id,
                direction="down",
            )
        )
        del form.cached_questions

        assert response.status_code == 302
        assert response.location == AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/questions")
        assert form.cached_questions[0].text == "Question 3"

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
        del form.cached_questions
        assert response.status_code == 302
        assert response.location == AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions")

        assert form.cached_questions[1].text == "Question 2"


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
        form = factories.form.create(collection=report, title="Organisation information")

        response = client.get(
            url_for("deliver_grant_funding.choose_question_type", grant_id=client.grant.id, form_id=form.id)
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "What type of question do you need?"

            assert len(soup.select("input[type=radio]")) == 9, "Should show an option for each kind of question"

    def test_post(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")

        form = QuestionTypeForm(data={"question_data_type": QuestionDataType.TEXT_SINGLE_LINE.name})
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.choose_question_type",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=db_form.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/questions/add\?question_data_type=TEXT_SINGLE_LINE"
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
        form = factories.form.create(collection=report, title="Organisation information")

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
        db_form = factories.form.create(collection=report, title="Organisation information")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant.id,
                form_id=db_form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
            ),
            data={
                "text": "question",
                "hint": "hint text",
                "name": "question name",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}$")

        # Stretching the test case a little but validates the flash message
        response = authenticated_grant_admin_client.get(response.location)
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Edit question"
        assert get_h2_text(soup) == "Question created"

    def test_post_with_invalid_context_references(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant.id,
                form_id=db_form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
            ),
            data={
                "text": "question ((invalid_reference))",
                "hint": "hint text",
                "name": "question name",
            },
            follow_redirects=False,
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        assert page_has_error(soup, "Reference is not valid: ((invalid_reference))")

    @pytest.mark.parametrize("context_field", ["text", "hint"])
    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session, mocker, context_field
    ):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
        form = QuestionForm(
            data={
                "text": "Updated question",
                "hint": "Updated hint",
                "name": "Updated name",
                "add_context": context_field,
            },
            question_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        spy_validate = mocker.spy(interfaces.collections, "_validate_and_sync_component_references")
        response = authenticated_grant_admin_client.post(
            url_for("deliver_grant_funding.add_question", grant_id=grant.id, form_id=db_form.id),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert spy_validate.call_count == 0

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert sess["question"]["field"] == "component"

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")

        session_data = AddContextToComponentSessionModel(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            component_form_data={
                "text": "Test question text",
                "name": "Test question name",
                "hint": "Test question hint",
                "add_context": "text",
            },
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant.id,
                form_id=db_form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
            ),
            data={
                "text": "Test question text",
                "name": "Test question name",
                "hint": "Test question hint",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}$")

        # Stretching the test case a little but validates the flash message
        response = authenticated_grant_admin_client.get(response.location)
        assert response.status_code == 200

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert "question" not in sess

    def test_post_add_to_group(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
        group = factories.group.create(form=db_form, name="Test group", order=0)

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=grant.id,
                form_id=db_form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
                parent_id=group.id,
            ),
            data={
                "text": "question",
                "hint": "hint text",
                "name": "question name",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}$")

        # Stretching the test case a little but validates the group specific flash message
        response = authenticated_grant_admin_client.get(response.location)
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Edit question"
        assert get_h2_text(soup) == "Question created"
        assert page_has_link(soup, "Return to the question group")

    def test_restore_from_session_when_returning_from_add_session_flow(
        self, authenticated_grant_admin_client, factories
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")
        group = factories.group.create(form=form, name="Test group", order=0)

        session_data = AddContextToComponentSessionModel(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            component_form_data={
                "text": "Test question text",
                "name": "Test question name",
                "hint": "Test question hint",
                "add_context": "text",
            },
            parent_id=group.id,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.add_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
                question_type=QuestionDataType.TEXT_SINGLE_LINE.name,
                parent_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        # Verify that the session data is restored to the form
        text_input = soup.find("textarea", {"name": "text"})
        assert text_input.text.strip() == "Test question text"

        name_input = soup.find("input", {"name": "name"})
        assert name_input["value"] == "Test question name"

        hint_textarea = soup.find("textarea", {"name": "hint"})
        assert hint_textarea.text.strip() == "Test question hint"


class TestAddQuestionGroup:
    def test_404(self, authenticated_grant_admin_client, factories):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.add_question", grant_id=uuid.uuid4(), form_id=uuid.uuid4())
        )
        assert response.status_code == 404

        # valid grant and form context but adding to a missing question group
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)
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
        db_form = factories.form.create(collection=report)

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
            data=get_form_data(form),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/groups/add$")

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
        form = factories.form.create(collection=report, title="Organisation information")

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
        db_form = factories.form.create(collection=report, title="Organisation information")

        with authenticated_grant_admin_client.session_transaction() as session:
            session["add_question_group"] = {"group_name": "Test group"}

        form = GroupDisplayOptionsForm(
            data={
                "show_questions_on_the_same_page": "all-questions-on-same-page",
            },
        )
        response = authenticated_grant_admin_client.post(
            url_for("deliver_grant_funding.add_question_group_display_options", grant_id=grant.id, form_id=db_form.id),
            data=get_form_data(form),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions\?form_id=[a-z0-9-]{36}$"
        )

    def test_post_duplicate(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "A question group with this name already exists")


class TestSelectContextSource:
    def test_get_fails_with_empty_session(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 400

    def test_get_shows_available_context_source_choices(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test question text",
                    "name": "Test question name",
                    "hint": "Test question hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select a data source" in soup.text

    def test_get_works_for_existing_group_available_context_source_choices(
        self, authenticated_grant_admin_client, factories
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)
        group = factories.group.create(form=form)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                component_id=group.id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select a data source" in soup.text

    def test_post_redirect_and_updates_session(self, authenticated_grant_admin_client, factories):
        assert len(ExpressionContext.ContextSources) == 1, "Check all redirects if adding new context source choices"

        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)
        factories.question.create(form=form)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data={"data_source": "TASK"},
        )
        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )


class TestSelectContextSourceQuestion:
    def test_get_fails_with_invalid_session(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 400

    def test_get_lists_questions(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)
        question1 = factories.question.create(form=form, text="Question 1")
        question2 = factories.question.create(form=form, text="Question 2")

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.TEXT_SINGLE_LINE,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                data_source=ExpressionContext.ContextSources.TASK,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select which question's answer to use" in soup.text
        assert question1.text in soup.text
        assert question2.text in soup.text

    def test_get_lists_questions_from_depends_on_question_if_condition(
        self, authenticated_grant_admin_client, factories
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)
        reference_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        depends_on_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        skipped_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=form, data_type=QuestionDataType.TEXT_SINGLE_LINE)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=ExpressionType.CONDITION,
                managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
                expression_form_data={
                    "type": "Greater than",
                    "greater_than_value": None,
                    "greater_than_inclusive": True,
                    "add_context": "greater_than_expression",
                },
                component_id=target_question.id,
                depends_on_question_id=depends_on_question.id,
                data_source=ExpressionContext.ContextSources.TASK,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Select which question's answer to use" in soup.text
        assert reference_question.text in soup.text
        assert depends_on_question.text not in soup.text and skipped_question.text not in soup.text

    def test_post_redirects_to_component_and_updates_session(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)
        question = factories.question.create(form=form, text="Source question")

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentSessionModel(
                data_type=QuestionDataType.YES_NO,
                component_form_data={
                    "text": "Test text",
                    "name": "Test name",
                    "hint": "Test hint",
                    "add_context": "text",
                },
                data_source=ExpressionContext.ContextSources.TASK,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data={"question": str(question.id)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/questions/add\?question_data_type=YES_NO$"
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            assert question_data["component_form_data"]["text"] == f"Test text (({question.safe_qid}))"

    def test_post_redirects_to_guidance_and_updates_session(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)
        referenced_question = factories.question.create(form=form)
        question = factories.question.create(form=form)

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToComponentGuidanceSessionModel(
                component_form_data={
                    "add_context": "guidance_body",
                    "guidance_body": "Some guidance text here",
                    "guidance_heading": "Guidance header",
                    "preview": False,
                },
                component_id=question.id,
                data_source=ExpressionContext.ContextSources.TASK,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data={"question": str(referenced_question.id)},
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}/guidance"
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            assert (
                question_data["component_form_data"]["guidance_body"]
                == f"Some guidance text here (({referenced_question.safe_qid}))"
            )

    @pytest.mark.parametrize(
        "expression_type, existing_expression",
        (
            (ExpressionType.CONDITION, False),
            (ExpressionType.CONDITION, True),
            (ExpressionType.VALIDATION, False),
            (ExpressionType.VALIDATION, True),
        ),
    )
    def test_post_redirects_to_expression_and_updates_session(
        self, authenticated_grant_admin_client, factories, db_session, expression_type, existing_expression
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant)
        form = factories.form.create(collection=report)
        reference_data_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        depends_on_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=form, data_type=QuestionDataType.INTEGER)

        expression_id = None
        if existing_expression:
            expression = GreaterThan(question_id=target_question.id, minimum_value=100)
            interfaces.collections.add_question_validation(
                target_question, interfaces.user.get_current_user(), expression
            )
            db_session.commit()
            expression_id = target_question.expressions[0].id

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = AddContextToExpressionsModel(
                field=expression_type,
                managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
                expression_form_data={
                    "type": "Greater than",
                    "greater_than_value": None,
                    "greater_than_expression": "",
                    "greater_than_inclusive": False,
                    "add_context": "greater_than_expression",
                },
                component_id=target_question.id,
                data_source=ExpressionContext.ContextSources.TASK,
                depends_on_question_id=depends_on_question.id
                if expression_type is ExpressionType.CONDITION and not existing_expression
                else None,
                expression_id=expression_id,
            ).model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.select_context_source_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                form_id=form.id,
            ),
            data={"question": str(reference_data_question.id)},
            follow_redirects=False,
        )
        assert response.status_code == 302

        with authenticated_grant_admin_client.session_transaction() as sess:
            question_data = sess.get("question")
            assert question_data is not None
            assert (
                question_data["expression_form_data"]["greater_than_expression"]
                == f"(({reference_data_question.safe_qid}))"
            )

        if expression_type is ExpressionType.CONDITION:
            if existing_expression:
                assert response.location == AnyStringMatching(
                    rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/condition/{expression_id}"
                )
            else:
                assert response.location == AnyStringMatching(
                    rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/"
                    + rf"{target_question.id}/add-condition/{depends_on_question.id}"
                )
        else:
            if existing_expression:
                assert response.location == AnyStringMatching(
                    rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/validation/{expression_id}"
                )
            else:
                assert response.location == AnyStringMatching(
                    rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}/add-validation"
                )


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
        form = factories.form.create(collection=report, title="Organisation information")
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
            form__collection__grant=authenticated_grant_admin_client.grant,
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

    def test_post(self, authenticated_grant_admin_client, factories, db_session, mocker):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
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
        spy_validate = mocker.spy(interfaces.collections, "_validate_and_sync_component_references")
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/questions$")
        assert spy_validate.call_count == 1

    def test_post_update_question_in_group_redirects_to_group_questions_page(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        group = factories.group.create(form__collection__grant=grant)
        question = factories.question.create(
            form=group.form,
            parent=group,
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

    def test_post_with_invalid_context_references(self, authenticated_grant_admin_client, factories, db_session):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
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
                "hint": "Updated hint ((invalid_reference))",
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
            data=get_form_data(form),
            follow_redirects=False,
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        assert page_has_error(soup, "Reference is not valid: ((invalid_reference))")

    @pytest.mark.parametrize("context_field", ["text", "hint"])
    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session, mocker, context_field
    ):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
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
                "add_context": context_field,
            },
            question_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        spy_validate = mocker.spy(interfaces.collections, "_validate_and_sync_component_references")
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=question.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert spy_validate.call_count == 0

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert sess["question"]["field"] == "component"

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
        question = factories.question.create(
            form=db_form,
            text="My question",
            name="Question name",
            hint="Question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )

        session_data = AddContextToComponentSessionModel(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            component_form_data={
                "text": "Test question text",
                "name": "Test question name",
                "hint": "Test question hint",
            },
            component_id=question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=grant.id,
                question_id=question.id,
            ),
            data={
                "text": "Test question text",
                "name": "Test question name",
                "hint": "Test question hint",
                "submit": "y",
            },
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/questions$")

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert "question" not in sess

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

    def test_restore_from_session_when_returning_from_add_session_flow(
        self, authenticated_grant_admin_client, factories
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")
        question = factories.question.create(
            form=form,
            text="Existing question text",
            name="Existing question name",
            hint="Existing question hint",
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )

        session_data = AddContextToComponentSessionModel(
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
            component_form_data={
                "text": "Updated question text from session",
                "name": "Updated question name from session",
                "hint": "Updated question hint from session",
                "add_context": "text",
            },
            component_id=question.id,
            parent_id=None,
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            sess["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.edit_question",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        # Verify that the session data overrides the existing question data
        text_input = soup.find("textarea", {"name": "text"})
        assert text_input.text.strip() == "Updated question text from session"

        hint_textarea = soup.find("textarea", {"name": "hint"})
        assert hint_textarea.text.strip() == "Updated question hint from session"


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
        form = factories.form.create(collection=report, title="Organisation information")
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
        form = factories.form.create(collection=report, title="Organisation information")

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

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_get_only_lists_referenceable_questions(self, request, client_fixture, can_access, factories, db_session):
        client = request.getfixturevalue(client_fixture)
        report = factories.collection.create(grant=client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")

        factories.question.create(
            form=form,
            text="Do you like cheese?",
            name="cheese question",
            data_type=QuestionDataType.YES_NO,
        )

        factories.question.create(
            form=form,
            text="What is your email?",
            name="email question",
            data_type=QuestionDataType.EMAIL,
        )

        factories.question.create(
            form=form, text="How much cheese do you buy?", name="how much cheese", data_type=QuestionDataType.INTEGER
        )

        group = factories.group.create(
            form=form, presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True)
        )
        factories.question.create(
            form=form,
            parent=group,
            text="What is the most cheese you've ever eaten?",
            name="most cheese",
            data_type=QuestionDataType.INTEGER,
        )
        second_group_question = factories.question.create(
            form=form,
            parent=group,
            text="What is the least cheese you've ever eaten?",
            name="least cheese",
            data_type=QuestionDataType.INTEGER,
        )

        response = client.get(
            url_for(
                "deliver_grant_funding.add_question_condition_select_question",
                grant_id=client.grant.id,
                component_id=second_group_question.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert "What answer should the condition check?" in soup.text
            assert "Do you like cheese? (cheese question)" in soup.text
            assert "How much cheese do you buy? (how much cheese)" in soup.text
            assert "What is your email? (email question)" not in soup.text
            assert "What is the most cheese you've ever eaten? (most question)" not in soup.text
            assert "What is the least cheese you've ever eaten? (least cheese)" not in soup.text

    def test_post(self, authenticated_grant_admin_client, factories):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")

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
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{second_question.id}/add-condition/{first_question.id}"
        )

    def test_wtforms_validation_prevents_invalid_choice_from_manipulation(
        self, authenticated_grant_admin_client, factories
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        form = factories.form.create(collection=report, title="Organisation information")

        group = factories.group.create(
            form=form,
            presentation_options=QuestionPresentationOptions(show_questions_on_the_same_page=True),
        )
        q1 = factories.question.create(form=form, parent=group, data_type=QuestionDataType.YES_NO)
        q2 = factories.question.create(form=form, parent=group, data_type=QuestionDataType.EMAIL)

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
        assert page_has_error(soup, "Not a valid choice")


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
        form = factories.form.create(collection=report, title="Organisation information")

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
        db_form = factories.form.create(collection=report, title="Organisation information")

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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.CONDITION
        assert expression.managed_name == "Yes"
        assert expression.managed.referenced_question.id == depends_on_question.id

    def test_post_for_group(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")

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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/group/{target_group.id}/questions"
        )

        assert len(target_group.expressions) == 1
        expression = target_group.expressions[0]
        assert expression.type_ == ExpressionType.CONDITION
        assert expression.managed_name == "Yes"
        assert expression.managed.referenced_question.id == depends_on_question.id

    def test_post_duplicate_condition(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")

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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "condition based on this question already exists" in soup.text

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session, mocker
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        depends_on_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="total cheese eaten",
            data_type=QuestionDataType.INTEGER,
        )

        target_question = factories.question.create(
            form=db_form,
            text="Why do you eat so much cheese?",
            name="why so much cheese",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        assert len(target_question.expressions) == 0

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question)
        form = ConditionForm(
            data={
                "type": "Greater than",
                "greater_than_value": None,
                "greater_than_expression": "",
                "greater_than_inclusive": False,
                "add_context": "greater_than_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                depends_on_question_id=depends_on_question.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert len(target_question.expressions) == 0

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.CONDITION

    def test_post_to_remove_context_updates_session_and_reloads_page(
        self, authenticated_grant_admin_client, factories, db_session, mocker
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        reference_data_question = factories.question.create(form=db_form, data_type=QuestionDataType.INTEGER)
        depends_on_question = factories.question.create(form=db_form, data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=db_form, data_type=QuestionDataType.TEXT_MULTI_LINE)

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
            expression_form_data={
                "type": "Greater than",
                "greater_than_value": None,
                "greater_than_expression": f"(({reference_data_question.safe_qid}))",
                "greater_than_inclusive": True,
            },
            component_id=target_question.id,
            depends_on_question_id=depends_on_question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question)
        form = ConditionForm(
            data={
                "type": "Greater than",
                "greater_than_value": None,
                "greater_than_expression": f"(({reference_data_question.safe_qid}))",
                "greater_than_inclusive": False,
                "remove_context": "greater_than_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                depends_on_question_id=depends_on_question.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302

        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                depends_on_question_id=depends_on_question.id,
            )
        )
        assert len(target_question.expressions) == 0

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.CONDITION
            assert session["question"]["expression_form_data"]["greater_than_expression"] == ""
            assert session["question"]["expression_form_data"]["greater_than_inclusive"] is False

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        reference_data_question = factories.question.create(
            form=db_form,
            text="How much cheese do you buy a month?",
            name="total cheese bought",
            data_type=QuestionDataType.INTEGER,
        )

        depends_on_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="total cheese eaten",
            data_type=QuestionDataType.INTEGER,
        )

        target_question = factories.question.create(
            form=db_form,
            text="Why do you eat so much cheese?",
            name="why so much cheese",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        ConditionForm = build_managed_expression_form(ExpressionType.CONDITION, depends_on_question)
        form = ConditionForm(
            data={
                "type": "Greater than",
                "greater_than_value": None,
                "greater_than_expression": f"(({reference_data_question.safe_qid}))",
                "greater_than_inclusive": False,
            }
        )

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            managed_expression_name=ManagedExpressionsEnum.GREATER_THAN,
            expression_form_data=form.data,
            component_id=target_question.id,
            depends_on_question_id=depends_on_question.id,
            value_dependent_question_id=reference_data_question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                component_id=target_question.id,
                depends_on_question_id=depends_on_question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.CONDITION
        assert expression.managed_name == "Greater than"
        assert expression.managed.referenced_question.id == depends_on_question.id

        with authenticated_grant_admin_client.session_transaction() as session:
            assert "question" not in session


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
        db_form = factories.form.create(collection=report, title="Organisation information")
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
        db_form = factories.form.create(collection=report, title="Organisation information")
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
        db_form = factories.form.create(collection=report, title="Organisation information")
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        assert target_question.expressions[0].managed_name == "No"

    def test_post_update_group_condition(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/group/{target_question.id}/questions"
        )

        assert len(target_question.expressions) == 1
        assert target_question.expressions[0].managed_name == "No"

    def test_post_update_condition_duplicate(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "condition based on this question already exists" in soup.text

    def test_post_delete(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 0

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        depends_on_question = factories.question.create(
            form=db_form,
            text="When did you last buy cheese?",
            name="last cheese purchase",
            data_type=QuestionDataType.DATE,
        )

        target_question = factories.question.create(
            form=db_form,
            text="Why haven't you bought cheese in such a long time?",
            name="lack of cheese reason",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        expression = IsAfter(question_id=depends_on_question.id, earliest_value=date(2025, 1, 1))
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id

        assert len(target_question.expressions) == 1
        assert target_question.expressions[0].managed_name == "Is after"

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION, depends_on_question, target_question.expressions[0]
        )
        form = ConditionForm(
            data={
                "type": "Is after",
                "earliest_value": date(2025, 1, 1),
                "earliest_expression": "",
                "add_context": "earliest_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert len(target_question.expressions) == 1

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.CONDITION

    def test_post_to_remove_context_updates_session_and_reloads_page(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        reference_data_question = factories.question.create(form=db_form, data_type=QuestionDataType.DATE)
        depends_on_question = factories.question.create(form=db_form, data_type=QuestionDataType.DATE)
        target_question = factories.question.create(form=db_form, data_type=QuestionDataType.TEXT_MULTI_LINE)

        expression = IsAfter(
            question_id=depends_on_question.id,
            earliest_value=None,
            earliest_expression=f"(({reference_data_question.safe_qid}))",
            inclusive=True,
        )
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION, depends_on_question, target_question.expressions[0]
        )
        form = ConditionForm(
            data={
                "type": "Is after",
                "earliest_value": None,
                "earliest_expression": f"(({reference_data_question.safe_qid}))",
                "earliest_inclusive": False,
                "remove_context": "earliest_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            )
        )
        assert len(target_question.expressions) == 1

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.CONDITION
            assert session["question"]["expression_form_data"]["earliest_expression"] == ""
            assert session["question"]["expression_form_data"]["earliest_inclusive"] is False

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        reference_data_question = factories.question.create(
            form=db_form,
            text="When did the year start?",
            name="start of year",
            data_type=QuestionDataType.DATE,
        )

        depends_on_question = factories.question.create(
            form=db_form,
            text="When did you last buy cheese?",
            name="last cheese purchase",
            data_type=QuestionDataType.DATE,
        )

        target_question = factories.question.create(
            form=db_form,
            text="Why haven't you bought cheese in such a long time?",
            name="lack of cheese reason",
            data_type=QuestionDataType.TEXT_MULTI_LINE,
        )

        expression = IsAfter(question_id=depends_on_question.id, earliest_value=date(2025, 12, 1))
        interfaces.collections.add_component_condition(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert len(target_question.expressions) == 1
        assert target_question.expressions[0].managed_name == "Is after"

        ConditionForm = build_managed_expression_form(
            ExpressionType.CONDITION, depends_on_question, target_question.expressions[0]
        )
        form = ConditionForm(
            data={
                "type": "Is after",
                "earliest_value": None,
                "earliest_expression": f"(({reference_data_question.safe_qid}))",
            }
        )

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.CONDITION,
            managed_expression_name=ManagedExpressionsEnum.IS_AFTER,
            expression_id=expression_id,
            expression_form_data=form.data,
            component_id=target_question.id,
            depends_on_question_id=depends_on_question.id,
            value_dependent_question_id=reference_data_question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_condition",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.CONDITION
        assert expression.managed_name == "Is after"
        assert expression.managed.referenced_question.id == depends_on_question.id
        assert expression.statement == f"{depends_on_question.safe_qid} > (({reference_data_question.safe_qid}))"

        with authenticated_grant_admin_client.session_transaction() as session:
            assert "question" not in session


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
        db_form = factories.form.create(collection=report, title="Organisation information")
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
        db_form = factories.form.create(collection=report, title="Organisation information")
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
        db_form = factories.form.create(collection=report, title="Organisation information")
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        assert len(question.expressions) == 1
        expression = question.expressions[0]
        assert expression.type_ == ExpressionType.VALIDATION
        assert expression.managed_name == "Greater than"

    def test_post_duplicate_validation(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
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

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        target_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat?",
            name="quantity of cheese",
            data_type=QuestionDataType.INTEGER,
        )

        assert len(target_question.expressions) == 0

        ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, target_question)
        form = ValidationForm(
            data={
                "type": "Less than",
                "less_than_value": None,
                "less_than_expression": "",
                "less_than_inclusive": False,
                "add_context": "less_than_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=target_question.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert len(target_question.expressions) == 0

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION

    def test_post_to_remove_context_updates_session_and_reloads_page(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        referenced_question = factories.question.create(form=db_form, data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=db_form, data_type=QuestionDataType.INTEGER)

        assert len(target_question.expressions) == 0

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.BETWEEN,
            expression_form_data={
                "type": "Between",
                "between_bottom_of_range": None,
                "between_bottom_of_range_expression": f"(({referenced_question.safe_qid}))",
                "between_bottom_inclusive": True,
                "between_top_of_range": 100,
                "between_top_of_range_expression": "",
                "between_top_inclusive": True,
            },
            component_id=target_question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, target_question)
        form = ValidationForm(
            data={
                "type": "Between",
                "between_bottom_of_range": None,
                "between_bottom_of_range_expression": f"(({referenced_question.safe_qid}))",
                "between_bottom_inclusive": False,
                "between_top_of_range": 100,
                "between_top_of_range_expression": "",
                "between_top_inclusive": True,
                "remove_context": "between_bottom_of_range_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=target_question.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=target_question.id,
            )
        )
        assert len(target_question.expressions) == 0

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION
            assert session["question"]["expression_form_data"]["between_bottom_of_range_expression"] == ""
            assert session["question"]["expression_form_data"]["between_bottom_inclusive"] is False
            assert session["question"]["expression_form_data"]["between_top_of_range"] == 100

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        reference_data_question = factories.question.create(
            form=db_form,
            text="How much cheese do you buy a month?",
            name="total cheese bought",
            data_type=QuestionDataType.INTEGER,
        )

        target_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="quantity of cheese",
            data_type=QuestionDataType.INTEGER,
        )

        ValidationForm = build_managed_expression_form(ExpressionType.VALIDATION, target_question)
        form = ValidationForm(
            data={
                "type": "Less than",
                "less_than_value": None,
                "less_than_expression": f"(({reference_data_question.safe_qid}))",
                "less_than_inclusive": True,
            }
        )

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.LESS_THAN,
            expression_form_data=form.data,
            component_id=target_question.id,
            value_dependent_question_id=reference_data_question.id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.add_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=target_question.id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.VALIDATION
        assert expression.managed_name == "Less than"
        assert expression.managed.referenced_question.id == target_question.id

        with authenticated_grant_admin_client.session_transaction() as session:
            assert "question" not in session


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
        db_form = factories.form.create(collection=report, title="Organisation information")
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
        db_form = factories.form.create(collection=report, title="Organisation information")
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
        db_form = factories.form.create(collection=report, title="Organisation information")
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        assert len(question.expressions) == 1
        assert question.expressions[0].managed_name == "Less than"

    def test_post_update_validation_duplicate(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
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
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "validation already exists on the question" in soup.text

    def test_post_delete(self, authenticated_grant_admin_client, factories, db_session):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Organisation information")
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
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        assert len(question.expressions) == 0

    def test_post_to_remove_context_updates_session_and_reloads_page(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        referenced_question = factories.question.create(form=db_form, data_type=QuestionDataType.INTEGER)
        target_question = factories.question.create(form=db_form, data_type=QuestionDataType.INTEGER)

        expression = LessThan(
            question_id=target_question.id,
            maximum_value=None,
            maximum_expression=f"(({referenced_question.safe_qid}))",
            inclusive=True,
        )
        interfaces.collections.add_question_validation(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert target_question.expressions[0].managed_name == "Less than"
        assert len(target_question.expressions) == 1

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, target_question, target_question.expressions[0]
        )
        form = ValidationForm(
            data={
                "type": "Less than",
                "less_than_value": None,
                "less_than_expression": f"(({referenced_question.safe_qid}))",
                "less_than_inclusive": False,
                "remove_context": "less_than_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location.endswith(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            )
        )
        assert len(target_question.expressions) == 1

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION
            assert session["question"]["expression_form_data"]["less_than_expression"] == ""
            assert session["question"]["expression_form_data"]["less_than_inclusive"] is False

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        report = factories.collection.create(grant=authenticated_grant_admin_client.grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        target_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="quantity of cheese",
            data_type=QuestionDataType.INTEGER,
        )

        expression = LessThan(question_id=target_question.id, maximum_value=1000)
        interfaces.collections.add_question_validation(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert target_question.expressions[0].managed_name == "Less than"
        assert len(target_question.expressions) == 1

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, target_question, target_question.expressions[0]
        )
        form = ValidationForm(
            data={
                "type": "Less than",
                "less_than_value": 1000,
                "less_than_expression": "",
                "less_than_inclusive": False,
                "add_context": "less_than_expression",
            }
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            "^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/add-context/select-source$"
        )
        assert len(target_question.expressions) == 1

        with authenticated_grant_admin_client.session_transaction() as session:
            assert session["question"]["field"] == ExpressionType.VALIDATION

    def test_post_from_add_context_success_cleans_that_bit_of_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        grant = authenticated_grant_admin_client.grant
        report = factories.collection.create(grant=grant, name="Test Report")
        db_form = factories.form.create(collection=report, title="Cheese habits")

        reference_data_question = factories.question.create(
            form=db_form,
            text="How much cheese do you buy a month?",
            name="total cheese bought",
            data_type=QuestionDataType.INTEGER,
        )

        target_question = factories.question.create(
            form=db_form,
            text="How much cheese do you eat a month?",
            name="quantity of cheese eaten",
            data_type=QuestionDataType.INTEGER,
        )

        expression = LessThan(question_id=target_question.id, maximum_value=1000)
        interfaces.collections.add_question_validation(target_question, interfaces.user.get_current_user(), expression)
        db_session.commit()

        expression_id = target_question.expressions[0].id
        assert target_question.expressions[0].managed_name == "Less than"
        assert len(target_question.expressions) == 1

        ValidationForm = build_managed_expression_form(
            ExpressionType.VALIDATION, target_question, target_question.expressions[0]
        )
        form = ValidationForm(
            data={
                "type": "Less than",
                "less_than_value": 1000,
                "less_than_expression": f"(({reference_data_question.safe_qid}))",
                "less_than_inclusive": True,
            }
        )

        session_data = AddContextToExpressionsModel(
            field=ExpressionType.VALIDATION,
            managed_expression_name=ManagedExpressionsEnum.LESS_THAN,
            expression_form_data=form.data,
            component_id=target_question.id,
            value_dependent_question_id=reference_data_question.id,
            expression_id=expression_id,
        )

        with authenticated_grant_admin_client.session_transaction() as session:
            session["question"] = session_data.model_dump(mode="json")

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.edit_question_validation",
                grant_id=authenticated_grant_admin_client.grant.id,
                expression_id=expression_id,
            ),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            rf"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{target_question.id}"
        )

        assert len(target_question.expressions) == 1
        expression = target_question.expressions[0]
        assert expression.type_ == ExpressionType.VALIDATION
        assert expression.managed_name == "Less than"
        assert expression.managed.referenced_question.id == target_question.id
        assert expression.statement == f"{target_question.safe_qid} <=(({reference_data_question.safe_qid}))"

        with authenticated_grant_admin_client.session_transaction() as session:
            assert "question" not in session


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
        question = factories.question.create(form__collection__grant=client.grant)

        response = client.get(
            url_for("deliver_grant_funding.manage_guidance", grant_id=client.grant.id, question_id=question.id)
        )

        if can_access:
            assert response.status_code == 200
        else:
            assert response.status_code == 403

    def test_get_add_guidance(self, authenticated_grant_admin_client, factories):
        question = factories.question.create(form__collection__grant=authenticated_grant_admin_client.grant)

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
            form__collection__grant=authenticated_grant_admin_client.grant,
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
        question = factories.question.create(form__collection__grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data={
                "guidance_heading": "How to answer",
                "guidance_body": "Please provide detailed information",
                "submit": "y",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/question/{question.id}"
        )

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == "How to answer"
        assert updated_question.guidance_body == "Please provide detailed information"

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        question = factories.question.create(form__collection__grant=authenticated_grant_admin_client.grant)

        form = AddGuidanceForm(
            guidance_heading="How to answer",
            guidance_body="Please provide detailed information",
            add_context="guidance_body",
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/add-context/select-source$"
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert sess["question"]["field"] == "guidance"

    def test_post_update_guidance(self, authenticated_grant_admin_client, factories, db_session):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Old heading",
            guidance_body="Old body",
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data={"guidance_heading": "Updated heading", "guidance_body": "Updated body", "submit": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/question/[a-z0-9-]{36}$")

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == "Updated heading"
        assert updated_question.guidance_body == "Updated body"

    def test_post_clear_guidance(self, authenticated_grant_admin_client, factories, db_session):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Existing heading",
            guidance_body="Existing body",
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data={"guidance_heading": "", "guidance_body": "", "submit": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 302

        updated_question = db_session.get(Question, question.id)
        assert updated_question.guidance_heading == ""
        assert updated_question.guidance_body == ""

    def test_post_guidance_with_heading_or_text_but_not_both(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        question = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Existing heading",
            guidance_body="Existing body",
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=question.id,
            ),
            data={"guidance_heading": "Existing heading", "guidance_body": "", "submit": "y"},
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
            form__collection__grant=authenticated_grant_admin_client.grant,
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
            form__collection__grant=authenticated_grant_admin_client.grant,
            guidance_heading="Old heading",
            guidance_body="Old body",
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                question_id=group.id,
            ),
            data={"guidance_heading": "Updated heading", "guidance_body": "Updated body", "submit": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, group.id)
        assert updated_group.guidance_heading == "Updated heading"
        assert updated_group.guidance_body == "Updated body"


class TestManageAddAnotherGuidance:
    def test_404(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.manage_add_another_guidance", grant_id=uuid.uuid4(), group_id=uuid.uuid4())
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
        group = factories.group.create(form__collection__grant=client.grant)

        response = client.get(
            url_for("deliver_grant_funding.manage_add_another_guidance", grant_id=client.grant.id, group_id=group.id)
        )

        if can_access:
            assert response.status_code == 200
        else:
            assert response.status_code == 403

    def test_get_add_guidance(self, authenticated_grant_admin_client, factories):
        group = factories.group.create(form__collection__grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_add_another_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Add another summary page guidance" in soup.text
        assert page_has_button(soup, "Save guidance")

    def test_get_edit_guidance(self, authenticated_grant_admin_client, factories):
        group = factories.question.create(
            form__collection__grant=authenticated_grant_admin_client.grant, add_another_guidance_body="Existing body"
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.manage_add_another_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "Existing body" in soup.text
        assert "Edit add another summary page guidance" in soup.text
        assert page_has_button(soup, "Save guidance")

    def test_post_add_guidance(self, authenticated_grant_admin_client, factories, db_session):
        group = factories.group.create(form__collection__grant=authenticated_grant_admin_client.grant)

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_add_another_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data={
                "guidance_body": "Please provide detailed information",
                "submit": "y",
            },
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            f"/deliver/grant/{authenticated_grant_admin_client.grant.id}/group/{group.id}/questions"
        )

        updated_group = db_session.get(Group, group.id)
        assert updated_group.add_another_guidance_body == "Please provide detailed information"

    def test_post_to_add_context_redirects_and_sets_up_session(
        self, authenticated_grant_admin_client, factories, db_session
    ):
        group = factories.group.create(form__collection__grant=authenticated_grant_admin_client.grant)

        form = AddGuidanceForm(
            guidance_body="Please provide detailed information",
            add_context="guidance_body",
        )
        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_add_another_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data=get_form_data(form, submit=""),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching(
            r"^/deliver/grant/[a-z0-9-]{36}/task/[a-z0-9-]{36}/add-context/select-source$"
        )

        with authenticated_grant_admin_client.session_transaction() as sess:
            assert sess["question"]["field"] == "guidance"
            assert sess["question"]["is_add_another_guidance"] is True

    def test_post_update_guidance(self, authenticated_grant_admin_client, factories, db_session):
        group = factories.group.create(
            form__collection__grant=authenticated_grant_admin_client.grant,
            add_another_guidance_body="Old body",
        )

        response = authenticated_grant_admin_client.post(
            url_for(
                "deliver_grant_funding.manage_add_another_guidance",
                grant_id=authenticated_grant_admin_client.grant.id,
                group_id=group.id,
            ),
            data={"guidance_body": "Updated body", "submit": "y"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/group/[a-z0-9-]{36}/questions$")

        updated_group = db_session.get(Group, group.id)
        assert updated_group.add_another_guidance_body == "Updated body"


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
        live_grant_recipient = factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant, organisation__name="Test Organisation Ltd"
        )
        factories.submission.create(
            collection=report,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=live_grant_recipient,
            created_by__email="submitter-live@recipient.org",
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

        test_recipient_link = page_has_link(test_soup, "submitter-test@recipient.org")
        live_recipient_link = page_has_link(live_soup, "Test Organisation Ltd")
        assert test_recipient_link.get("href") == AnyStringMatching(
            "/deliver/grant/[a-z0-9-]{36}/submission/[a-z0-9-]{36}"
        )
        assert live_recipient_link.get("href") == AnyStringMatching(
            "/deliver/grant/[a-z0-9-]{36}/submission/[a-z0-9-]{36}"
        )

        test_submission_tags = test_soup.select(".govuk-tag")
        live_submission_tags = live_soup.select(".govuk-tag")
        assert {tag.text.strip() for tag in test_submission_tags} == {"In progress", "Not started"}
        assert {tag.text.strip() for tag in live_submission_tags} == {"Not started"}

    def test_live_mode_shows_all_grant_recipients_including_those_without_submissions(
        self, authenticated_grant_member_client, factories, db_session
    ):
        report = factories.collection.create(
            grant=authenticated_grant_member_client.grant,
            name="Test Report",
        )
        grant_recipient_with_submission = factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant, organisation__name="Organisation With Submission"
        )
        factories.grant_recipient.create(
            grant=authenticated_grant_member_client.grant, organisation__name="Organisation Without Submission"
        )
        factories.submission.create(
            collection=report,
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient_with_submission,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "deliver_grant_funding.list_submissions",
                grant_id=authenticated_grant_member_client.grant.id,
                report_id=report.id,
                submission_mode=SubmissionModeEnum.LIVE,
            )
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200

        assert "Organisation With Submission" in response.text
        assert "Organisation Without Submission" in response.text

        link_with_submission = page_has_link(soup, "Organisation With Submission")
        assert link_with_submission is not None
        assert link_with_submission.get("href") == AnyStringMatching(
            "/deliver/grant/[a-z0-9-]{36}/submission/[a-z0-9-]{36}"
        )

        link_without_submission = page_has_link(soup, "Organisation Without Submission")
        assert link_without_submission is None

        submission_tags = soup.select(".govuk-tag")
        tag_texts = {tag.text.strip() for tag in submission_tags}
        assert "Not started" in tag_texts


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
        assert len(report.forms[0].cached_questions) == 9, "If more questions added, check+update this test"

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

        assert "When did you last buy some cheese" in soup.text
        assert "1 January 2025" in soup.text
