from datetime import date

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from pytest import FixtureRequest

from app import CollectionStatusEnum, GrantStatusEnum
from tests.utils import get_h1_text, page_has_button, page_has_link


class TestViewLockedReport:
    @pytest.mark.parametrize(
        "client_fixture, can_access, can_certify",
        (
            ("authenticated_no_role_client", False, False),
            ("authenticated_grant_recipient_member_client", True, False),
            ("authenticated_grant_recipient_data_provider_client", True, False),
            ("authenticated_grant_recipient_certifier_client", True, True),
        ),
    )
    def test_view_locked_reports_access(
        self,
        request: FixtureRequest,
        client_fixture: str,
        can_access: bool,
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

        if not can_access:
            assert response.status_code == 403
        else:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == f"Review Report: {submission_awaiting_sign_off.collection.name}"

            if not can_certify:
                assert page_has_button(soup, button_text="Sign off and submit report") is None
                assert page_has_link(soup, link_text="Decline sign off") is None
            else:
                assert page_has_button(soup, button_text="Sign off and submit report") is not None
                assert page_has_link(soup, link_text="Decline sign off") is not None


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
