from datetime import date

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from pytest import FixtureRequest

from app import CollectionStatusEnum, GrantStatusEnum, TasklistSectionStatusEnum
from app.access_grant_funding.forms import DeclineSignOffForm
from app.common.data.types import SubmissionModeEnum, SubmissionStatusEnum
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
    def test_view_locked_reports_access(
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
    def test_view_locked_reports_certifier(
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

        if not can_certify:
            assert page_has_button(soup, button_text="Sign off and submit report") is None
            assert page_has_link(soup, link_text="Decline sign off") is None
        else:
            assert page_has_button(soup, button_text="Sign off and submit report") is not None
            assert page_has_link(soup, link_text="Decline sign off") is not None

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
        helper = SubmissionHelper(submission_awaiting_sign_off)
        assert helper.status == SubmissionStatusEnum.AWAITING_SIGN_OFF
        form = submission_awaiting_sign_off.collection.forms[0]
        assert helper.get_status_for_form(form) == TasklistSectionStatusEnum.COMPLETED

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

        assert len(mock_notification_service_calls) == 2

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
