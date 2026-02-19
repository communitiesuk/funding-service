from datetime import date

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from pytest import FixtureRequest

from app import CollectionStatusEnum, GrantStatusEnum, TasklistSectionStatusEnum
from app.access_grant_funding.forms import DeclineSignOffForm
from app.common.data.types import (
    ExpressionType,
    ManagedExpressionsEnum,
    QuestionDataType,
    RoleEnum,
    SubmissionEventType,
    SubmissionModeEnum,
    SubmissionStatusEnum,
)
from app.common.forms import GenericSubmitForm
from app.common.helpers.collections import SubmissionHelper
from tests.utils import get_h1_text, page_has_button, page_has_error, page_has_link


class TestViewLockedReport:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
            ("authenticated_grant_recipient_data_provider_client", True),
            ("authenticated_grant_recipient_certifier_client", True),
        ),
    )
    def test_get_view_locked_report_access(
        self,
        request: FixtureRequest,
        client_fixture: str,
        can_access: bool,
        factories,
        submission_awaiting_sign_off,
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()

        response = client.get(
            url_for(
                "access_grant_funding.view_locked_report",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_awaiting_sign_off.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == f"Review report: {submission_awaiting_sign_off.collection.name}"

    @pytest.mark.parametrize(
        "client_fixture, can_certify",
        (
            ("authenticated_grant_recipient_member_client", False),
            ("authenticated_grant_recipient_data_provider_client", False),
            ("authenticated_grant_recipient_certifier_client", True),
        ),
    )
    def test_get_view_locked_reports_certifier(
        self,
        request: FixtureRequest,
        client_fixture: str,
        can_certify: bool,
        factories,
        submission_awaiting_sign_off,
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()

        response = client.get(
            url_for(
                "access_grant_funding.view_locked_report",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_awaiting_sign_off.id,
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")

        assert [key.text for key in soup.find_all("dt", class_="app-metadata__key")] == [
            "Submission deadline:",
            "Submitted by:",
            "Date submitted for sign off:",
            "Status:",
        ]

        if not can_certify:
            assert page_has_button(soup, button_text="Continue to sign off and submit") is None
            assert page_has_link(soup, link_text="Decline sign off") is None
        else:
            assert page_has_button(soup, button_text="Continue to sign off and submit") is not None
            assert page_has_link(soup, link_text="Decline sign off") is not None

    def test_get_view_locked_report_submitted(
        self,
        authenticated_grant_recipient_certifier_client,
        submission_submitted,
    ):
        grant_recipient = authenticated_grant_recipient_certifier_client.grant_recipient
        response = authenticated_grant_recipient_certifier_client.get(
            url_for(
                "access_grant_funding.view_locked_report",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_submitted.id,
            )
        )

        soup = BeautifulSoup(response.data, "html.parser")

        assert get_h1_text(soup) == submission_submitted.collection.name

        # now that its submitted we don't have certifier actions even though we have permissions
        # to do that
        assert page_has_button(soup, button_text="Sign off and submit report") is None
        assert page_has_link(soup, link_text="Decline sign off") is None

        assert [key.text for key in soup.find_all("dt", class_="app-metadata__key")] == [
            "Organisation:",
            "Submitted by:",
            "Certifier:",
            "Date submitted:",
        ]

    def test_view_locked_report_not_locked_redirects(
        self,
        authenticated_grant_recipient_member_client,
        factories,
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        submission = factories.submission.create(
            grant_recipient=grant_recipient, collection__grant=grant_recipient.grant, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.view_locked_report",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            )
        )

        assert response.status_code == 302
        assert response.location == (
            url_for(
                "access_grant_funding.list_reports",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
            )
        )

    def test_post_view_locked_report_certify_redirect(
        self,
        authenticated_grant_recipient_certifier_client,
        submission_awaiting_sign_off,
    ):
        organisation = authenticated_grant_recipient_certifier_client.organisation
        grant = authenticated_grant_recipient_certifier_client.grant

        helper = SubmissionHelper(submission_awaiting_sign_off)
        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

        form = GenericSubmitForm()

        response = authenticated_grant_recipient_certifier_client.post(
            url_for(
                "access_grant_funding.view_locked_report",
                organisation_id=organisation.id,
                grant_id=grant.id,
                submission_id=submission_awaiting_sign_off.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.confirm_report_submission_with_certify",
            organisation_id=organisation.id,
            grant_id=grant.id,
            submission_id=submission_awaiting_sign_off.id,
        )

        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

    def test_post_view_locked_report_403_with_incorrect_permissions(
        self, authenticated_grant_recipient_data_provider_client, submission_awaiting_sign_off
    ):
        organisation = authenticated_grant_recipient_data_provider_client.organisation
        grant = authenticated_grant_recipient_data_provider_client.grant

        helper = SubmissionHelper(submission_awaiting_sign_off)
        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

        form = GenericSubmitForm()

        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.view_locked_report",
                organisation_id=organisation.id,
                grant_id=grant.id,
                submission_id=submission_awaiting_sign_off.id,
            ),
            data=form.data,
            follow_redirects=True,
        )

        assert response.status_code == 403
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "You do not have permission to access this page"


class TextExportReportPDF:
    # the first method under test will spin up chromium which will always be marked as as a slow test
    @pytest.mark.fail_slow("1000ms", enabled=False)
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
            ("authenticated_grant_recipient_data_provider_client", True),
            ("authenticated_grant_recipient_certifier_client", True),
        ),
    )
    def test_get_export_report_pdf(
        self,
        request: FixtureRequest,
        client_fixture: str,
        can_access: bool,
        factories,
        submission_awaiting_sign_off,
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()

        response = client.get(
            url_for(
                "access_grant_funding.export_report_pdf",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_awaiting_sign_off.id,
            )
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            assert response.headers["Content-Type"] == "application/pdf"


class TestListReports:
    def test_get_list_reports(self, authenticated_grant_recipient_member_client, factories):
        organisation = authenticated_grant_recipient_member_client.organisation or factories.organisation.create(
            can_manage_grants=False,
        )
        grant = authenticated_grant_recipient_member_client.grant
        grant.status = GrantStatusEnum.LIVE

        _ = factories.collection.create_batch(
            2,
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            reporting_period_start_date=date(2025, 1, 1),
            reporting_period_end_date=date(2025, 3, 31),
            submission_period_start_date=date(2025, 11, 1),
            submission_period_end_date=date(2026, 2, 28),
        )
        response = authenticated_grant_recipient_member_client.get(
            url_for("access_grant_funding.list_reports", organisation_id=organisation.id, grant_id=grant.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Reports"
        table_elem = soup.find("table", class_="govuk-table")
        assert table_elem is not None
        assert len(table_elem.find_all("tr")) == 3

    def test_get_list_reports_not_grant_recipient(self, authenticated_grant_recipient_member_client, factories):
        organisation = authenticated_grant_recipient_member_client.organisation
        grant = factories.grant.create(organisation=organisation, status=GrantStatusEnum.LIVE)
        factories.grant_recipient.create(grant=grant, organisation=organisation)

        _ = factories.collection.create_batch(
            2,
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            reporting_period_start_date=date(2025, 1, 1),
            reporting_period_end_date=date(2025, 3, 31),
            submission_period_start_date=date(2025, 11, 1),
            submission_period_end_date=date(2026, 2, 28),
        )
        response = authenticated_grant_recipient_member_client.get(
            url_for("access_grant_funding.list_reports", organisation_id=organisation.id, grant_id=grant.id)
        )

        assert response.status_code == 403


class TestListCollectionSubmissions:
    def test_lists_submissions_for_collection(self, authenticated_grant_recipient_member_client, factories):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        collection = factories.collection.create(
            grant=grant_recipient.grant,
            allow_multiple_submissions=True,
            status=CollectionStatusEnum.OPEN,
        )
        submission_1 = factories.submission.create(
            collection=collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )
        submission_2 = factories.submission.create(
            collection=collection, grant_recipient=grant_recipient, mode=SubmissionModeEnum.LIVE
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_collection_submissions",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == collection.name
        assert submission_1.reference in soup.text
        assert submission_2.reference in soup.text

    def test_shows_empty_state_when_no_submissions(self, authenticated_grant_recipient_member_client, factories):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        collection = factories.collection.create(
            grant=grant_recipient.grant,
            allow_multiple_submissions=True,
            status=CollectionStatusEnum.OPEN,
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_collection_submissions",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "You have not started any reports yet." in soup.text

    def test_shows_display_name_from_submission_name_question(
        self, authenticated_grant_recipient_member_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        question = factories.question.create(
            form__collection__grant=grant_recipient.grant,
            form__collection__allow_multiple_submissions=True,
            form__collection__status=CollectionStatusEnum.OPEN,
            data_type=QuestionDataType.TEXT_SINGLE_LINE,
        )
        collection = question.form.collection
        collection.submission_name_question_id = question.id
        factories.submission.create(
            collection=collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            data={str(question.id): "My custom report name"},
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_collection_submissions",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "My custom report name" in soup.text

    def test_report_list_shows_go_to_reports_link_for_multi_submission_collection(
        self, authenticated_grant_recipient_member_client, factories
    ):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        grant = grant_recipient.grant
        grant.status = GrantStatusEnum.LIVE
        factories.collection.create(
            grant=grant,
            allow_multiple_submissions=True,
            status=CollectionStatusEnum.OPEN,
            reporting_period_start_date=date(2025, 1, 1),
            reporting_period_end_date=date(2025, 3, 31),
            submission_period_start_date=date(2025, 11, 1),
            submission_period_end_date=date(2026, 2, 28),
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_reports",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_link(soup, "Go to reports") is not None

    def test_submission_list_renders_guidance_as_markdown(self, authenticated_grant_recipient_member_client, factories):
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient
        collection = factories.collection.create(
            grant=grant_recipient.grant,
            allow_multiple_submissions=True,
            status=CollectionStatusEnum.OPEN,
            submission_guidance="## Getting started\n\nPlease complete a report for each project.",
        )

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.list_collection_submissions",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_id=collection.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        heading = soup.find("h2", string="Getting started")
        assert heading is not None
        assert "Please complete a report for each project." in soup.text


class TestDeclineSignOff:
    def test_decline_certification_post_success(
        self,
        authenticated_grant_recipient_certifier_client,
        factories,
        submission_awaiting_sign_off,
        grant_recipient,
        user,
        app,
        mock_notification_service_calls,
    ):
        organisation = authenticated_grant_recipient_certifier_client.organisation
        grant = authenticated_grant_recipient_certifier_client.grant

        helper = SubmissionHelper(submission_awaiting_sign_off)
        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF
        form = submission_awaiting_sign_off.collection.forms[0]
        assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED

        submitted_by_user = factories.user.create()
        # Give the user DATA_PROVIDER and CERTIFIER permissions to ensure they get both distinct emails sent as part
        # of this flow
        factories.user_role.create(
            user=submitted_by_user,
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
        )
        certification_event = next(
            event
            for event in submission_awaiting_sign_off.events
            if event.event_type == SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION
        )
        certification_event.created_by = submitted_by_user

        decline_form = DeclineSignOffForm()
        decline_form.decline_reason.data = "Reason for declining"

        response = authenticated_grant_recipient_certifier_client.post(
            url_for(
                "access_grant_funding.decline_report",
                organisation_id=grant_recipient.organisation_id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_awaiting_sign_off.id,
            ),
            data=decline_form.data,
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_reports",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
        )

        assert helper.status == SubmissionStatusEnum.IN_PROGRESS
        assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.IN_PROGRESS

        assert len(mock_notification_service_calls) == 3

    def test_decline_certification_post_form_validation_fails(
        self,
        authenticated_grant_recipient_certifier_client,
        factories,
        submission_awaiting_sign_off,
        grant_recipient,
        user,
        app,
        mock_notification_service_calls,
    ):
        helper = SubmissionHelper(submission_awaiting_sign_off)
        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF
        form = submission_awaiting_sign_off.collection.forms[0]
        assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED

        decline_form = DeclineSignOffForm()
        decline_form.decline_reason.data = ""

        response = authenticated_grant_recipient_certifier_client.post(
            url_for(
                "access_grant_funding.decline_report",
                organisation_id=grant_recipient.organisation_id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_awaiting_sign_off.id,
            ),
            data=decline_form.data,
            follow_redirects=False,
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Enter a reason for declining sign off")

        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF
        assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED

        assert len(mock_notification_service_calls) == 0

    def test_decline_certification_invalid_status(
        self,
        authenticated_grant_recipient_certifier_client,
        factories,
        grant_recipient,
        submission_in_progress,
        user,
    ):
        helper = SubmissionHelper(submission_in_progress)
        assert helper.status == SubmissionStatusEnum.IN_PROGRESS

        response = authenticated_grant_recipient_certifier_client.get(
            url_for(
                "access_grant_funding.decline_report",
                organisation_id=grant_recipient.organisation_id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_in_progress.id,
            ),
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.route_to_submission",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
            collection_id=submission_in_progress.collection.id,
        )

    def test_decline_sign_off_get(
        self, authenticated_grant_recipient_certifier_client, factories, submission_awaiting_sign_off, grant_recipient
    ):
        response = authenticated_grant_recipient_certifier_client.get(
            url_for(
                "access_grant_funding.decline_report",
                organisation_id=grant_recipient.organisation_id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_awaiting_sign_off.id,
            ),
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert (
            get_h1_text(soup)
            == f"Why are you declining sign off for the {submission_awaiting_sign_off.collection.name} report?"
        )


class TestConfirmReportSubmission:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", False),
            ("authenticated_grant_recipient_data_provider_client", True),
            ("authenticated_grant_recipient_certifier_client", False),
        ),
    )
    def test_get_confirm_report_submission_access(
        self, submission_ready_to_submit, client_fixture, can_access, request, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        submission_ready_to_submit.collection.requires_certification = False
        db_session.commit()

        response = client.get(
            url_for(
                "access_grant_funding.confirm_report_submission_direct_submission",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_ready_to_submit.id,
            ),
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Confirm and submit report"

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", False),
            ("authenticated_grant_recipient_data_provider_client", False),
            ("authenticated_grant_recipient_certifier_client", True),
        ),
    )
    def test_get_confirm_report_submission_certify_access(
        self, submission_awaiting_sign_off, client_fixture, can_access, request, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        submission_awaiting_sign_off.collection.requires_certification = True
        db_session.commit()

        response = client.get(
            url_for(
                "access_grant_funding.confirm_report_submission_with_certify",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_awaiting_sign_off.id,
            ),
            follow_redirects=False,
        )

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Confirm sign off and submit report"

    def test_get_redirects_if_requires_certification_and_not_awaiting_sign_off(
        self, authenticated_grant_recipient_certifier_client, submission_ready_to_submit
    ):
        grant_recipient = authenticated_grant_recipient_certifier_client.grant_recipient

        response = authenticated_grant_recipient_certifier_client.get(
            url_for(
                "access_grant_funding.confirm_report_submission_with_certify",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_ready_to_submit.id,
            ),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_reports",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
        )

    def test_get_redirects_if_not_requires_certification_and_not_ready_to_submit(
        self, authenticated_grant_recipient_data_provider_client, submission_in_progress
    ):
        grant_recipient = authenticated_grant_recipient_data_provider_client.grant_recipient
        submission_in_progress.collection.requires_certification = False

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.confirm_report_submission_direct_submission",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_in_progress.id,
            ),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_reports",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
        )

    def test_post_confirm_report_submission_when_requires_certification(
        self,
        authenticated_grant_recipient_certifier_client,
        submission_awaiting_sign_off,
        factories,
        mock_notification_service_calls,
    ):
        organisation = authenticated_grant_recipient_certifier_client.organisation
        grant = authenticated_grant_recipient_certifier_client.grant

        submitted_by_user = factories.user.create()
        # Give the user DATA_PROVIDER and CERTIFIER permissions to ensure they still only get one confirmation email
        factories.user_role.create(
            user=submitted_by_user,
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
        )
        certification_event = next(
            event
            for event in submission_awaiting_sign_off.events
            if event.event_type == SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION
        )
        certification_event.created_by = submitted_by_user

        # Make a couple more grant recipient users to check they all receive the notification email
        additional_users = factories.user.create_batch(2)
        factories.user_role.create(
            user=additional_users[0],
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )
        factories.user_role.create(
            user=additional_users[1],
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.CERTIFIER],
        )

        helper = SubmissionHelper(submission_awaiting_sign_off)
        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

        form = GenericSubmitForm()

        response = authenticated_grant_recipient_certifier_client.post(
            url_for(
                "access_grant_funding.confirm_report_submission_with_certify",
                organisation_id=organisation.id,
                grant_id=grant.id,
                submission_id=submission_awaiting_sign_off.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.submitted_confirmation",
            organisation_id=organisation.id,
            grant_id=grant.id,
            submission_id=submission_awaiting_sign_off.id,
        )

        assert helper.status == SubmissionStatusEnum.SUBMITTED
        assert helper.events.submission_state.is_approved
        assert helper.events.submission_state.is_submitted
        assert len(mock_notification_service_calls) == 4

    def test_post_confirm_report_submission_when_no_certification(
        self,
        authenticated_grant_recipient_data_provider_client,
        submission_ready_to_submit,
        factories,
        mock_notification_service_calls,
    ):
        organisation = authenticated_grant_recipient_data_provider_client.organisation
        grant = authenticated_grant_recipient_data_provider_client.grant
        submission_ready_to_submit.collection.requires_certification = False

        # Make a couple more grant recipient users to check they all receive the notification email
        additional_users = factories.user.create_batch(2)
        factories.user_role.create(
            user=additional_users[0],
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
        )
        factories.user_role.create(
            user=additional_users[1],
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.CERTIFIER],
        )

        helper = SubmissionHelper(submission_ready_to_submit)
        assert helper.status == SubmissionStatusEnum.READY_TO_SUBMIT

        form = GenericSubmitForm()

        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.confirm_report_submission_direct_submission",
                organisation_id=organisation.id,
                grant_id=grant.id,
                submission_id=submission_ready_to_submit.id,
            ),
            data=form.data,
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.submitted_confirmation",
            organisation_id=organisation.id,
            grant_id=grant.id,
            submission_id=submission_ready_to_submit.id,
        )

        assert helper.status == SubmissionStatusEnum.SUBMITTED
        assert helper.events.submission_state.is_submitted
        assert len(mock_notification_service_calls) == 3

    def test_post_confirm_report_submission_certify_failure_should_not_submit(
        self,
        authenticated_grant_recipient_certifier_client,
        submission_awaiting_sign_off,
        factories,
        mocker,
        app,
    ):
        organisation = authenticated_grant_recipient_certifier_client.organisation
        grant = authenticated_grant_recipient_certifier_client.grant

        submitted_by_user = factories.user.create()
        certification_event = next(
            event
            for event in submission_awaiting_sign_off.events
            if event.event_type == SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION
        )
        certification_event.created_by = submitted_by_user

        helper = SubmissionHelper(submission_awaiting_sign_off)
        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF

        form = GenericSubmitForm()

        def side_effect(*args, **kwargs):
            raise Exception("Failed email")

        mocker.patch(
            "app.services.notify.NotificationService._send_email",
            side_effect=side_effect,
        )

        # for this test we don't want the test to raise the actual exception to end the test
        # as we want to assert on what the app did after the response
        mocker.patch.dict(app.config, {"TESTING": False})

        response = authenticated_grant_recipient_certifier_client.post(
            url_for(
                "access_grant_funding.confirm_report_submission_with_certify",
                organisation_id=organisation.id,
                grant_id=grant.id,
                submission_id=submission_awaiting_sign_off.id,
            ),
            data=form.data,
            follow_redirects=False,
        )
        assert response.status_code == 500

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Sorry, there is a problem with the service"

        # even though we received a managed error response the submission should not have been
        # updated
        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF
        assert helper.events.submission_state.is_approved is False
        assert helper.events.submission_state.is_submitted is False

    def test_post_confirm_report_submission_with_invalid_data_redirects_and_shows_error(
        self,
        authenticated_grant_recipient_data_provider_client,
        factories,
    ):
        client = authenticated_grant_recipient_data_provider_client
        grant_recipient = client.grant_recipient
        form = factories.form.create(title="Financial Report", collection__grant=grant_recipient.grant)
        q1 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=0, name="threshold")
        q2 = factories.question.create(form=form, data_type=QuestionDataType.NUMBER, order=1, name="amount")
        form.collection.requires_certification = False

        factories.expression.create(
            question=q2,
            created_by=client.user,
            type_=ExpressionType.VALIDATION,
            managed_name=ManagedExpressionsEnum.GREATER_THAN,
            statement=f"(({q2.safe_qid})) > (({q1.safe_qid}))",
            context={"question_id": str(q2.id), "minimum_value": None, "minimum_expression": f"(({q1.safe_qid}))"},
        )

        submission = factories.submission.create(
            collection=form.collection,
            grant_recipient=grant_recipient,
            mode=SubmissionModeEnum.LIVE,
            data={str(q1.id): {"value": 150}, str(q2.id): {"value": 100}},
        )
        factories.submission_event.create(
            created_by=client.user,
            submission=submission,
            related_entity_id=form.id,
            event_type=SubmissionEventType.FORM_RUNNER_FORM_COMPLETED,
        )

        certifier = factories.user.create()
        factories.user_role.create(
            user=certifier,
            organisation=grant_recipient.organisation,
            permissions=[RoleEnum.CERTIFIER],
        )
        response = authenticated_grant_recipient_data_provider_client.post(
            url_for(
                "access_grant_funding.confirm_report_submission_direct_submission",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            ),
            data={"submit": "y"},
            follow_redirects=True,
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert "You cannot submit because you need to review some answers" in soup.text
        assert "amount" in soup.text


class TestViewSubmittedConfirmation:
    @pytest.mark.parametrize(
        "client_fixture, requires_certification, can_access",
        (
            ("authenticated_no_role_client", False, False),
            ("authenticated_no_role_client", True, False),
            ("authenticated_grant_recipient_member_client", False, False),
            ("authenticated_grant_recipient_member_client", True, False),
            ("authenticated_grant_recipient_data_provider_client", False, True),
            ("authenticated_grant_recipient_data_provider_client", True, False),
            ("authenticated_grant_recipient_certifier_client", False, False),
            ("authenticated_grant_recipient_certifier_client", True, True),
        ),
    )
    def test_submitted_confirmation_access(
        self,
        request: FixtureRequest,
        client_fixture: str,
        requires_certification: bool,
        can_access: bool,
        factories,
        submission_submitted,
        db_session,
    ):
        client = request.getfixturevalue(client_fixture)
        grant_recipient = getattr(client, "grant_recipient", None) or factories.grant_recipient.create()
        submission_submitted.collection.requires_certification = requires_certification
        db_session.commit()

        response = client.get(
            url_for(
                "access_grant_funding.submitted_confirmation",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission_submitted.id,
            )
        )

        if client_fixture == "authenticated_no_role_client":
            assert response.status_code == 403
        elif can_access:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            if requires_certification:
                assert get_h1_text(soup) == "Report signed off and submitted"
            else:
                assert get_h1_text(soup) == "Report submitted"
        else:
            assert response.status_code == 302
            assert response.location == url_for(
                "access_grant_funding.list_reports",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
            )

    @pytest.mark.parametrize(
        "submission_fixture",
        (
            ("submission_awaiting_sign_off"),
            ("submission_ready_to_submit"),
            ("submission_in_progress"),
        ),
    )
    def test_submitted_confirm_redirects_if_not_submitted(
        self, authenticated_grant_recipient_member_client, submission_fixture, request
    ):
        submission = request.getfixturevalue(submission_fixture)
        grant_recipient = authenticated_grant_recipient_member_client.grant_recipient

        response = authenticated_grant_recipient_member_client.get(
            url_for(
                "access_grant_funding.submitted_confirmation",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                submission_id=submission.id,
            )
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_reports",
            organisation_id=grant_recipient.organisation.id,
            grant_id=grant_recipient.grant.id,
        )
