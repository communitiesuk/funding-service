import uuid
from datetime import date

import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app import CollectionStatusEnum, GrantStatusEnum
from tests.utils import get_h1_text


class TestIndex:
    def test_get_index(self, authenticated_grant_recipient_member_client, factories):
        response = authenticated_grant_recipient_member_client.get(url_for("access_grant_funding.index"))
        assert response.status_code == 302
        assert (
            response.location
            == f"/access/organisation/{authenticated_grant_recipient_member_client.organisation.id}/grants"
        )


class TestListGrants:
    def test_get_list_grants_404(self, authenticated_grant_recipient_member_client, factories, client):
        response = authenticated_grant_recipient_member_client.get(
            url_for("access_grant_funding.list_grants", organisation_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
        ),
    )
    def test_get_list_grants(self, factories, client, request, client_fixture, can_access):
        client = request.getfixturevalue(client_fixture)
        organisation = client.organisation or factories.organisation.create(can_manage_grants=False)
        response = client.get(
            url_for(
                "access_grant_funding.list_grants",
                organisation_id=organisation.id,
            )
        )
        if can_access:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Select a grant"
        else:
            assert response.status_code == 403


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
        organisation = authenticated_grant_recipient_member_client.organisation or factories.organisation.create(
            can_manage_grants=False,
        )
        grant = factories.grant.create(organisation=organisation, status=GrantStatusEnum.LIVE)

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

        assert response.status_code == 404
        assert "Not a grant recipient" in response.data.decode()
