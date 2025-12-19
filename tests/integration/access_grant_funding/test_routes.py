import uuid

import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.types import RoleEnum
from tests.utils import get_h1_text, get_h2_text


class TestIndex:
    def test_get_index_just_one_grant_recipient_redirects(self, authenticated_grant_recipient_member_client):
        response = authenticated_grant_recipient_member_client.get(url_for("access_grant_funding.index"))
        assert response.status_code == 302
        assert response.location == (
            f"/access/organisation/{authenticated_grant_recipient_member_client.organisation.id}"
            f"/grants/{authenticated_grant_recipient_member_client.grant.id}/reports"
        )

    def test_get_index_two_grant_recipients_same_org_redirects(
        self, authenticated_grant_recipient_member_client, factories
    ):
        user = authenticated_grant_recipient_member_client.user
        grant = factories.grant.create()
        organisation = authenticated_grant_recipient_member_client.organisation

        factories.grant_recipient.create(grant=grant, organisation=organisation)
        factories.user_role.create(
            user=user, organisation=organisation, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        response = authenticated_grant_recipient_member_client.get(url_for("access_grant_funding.index"))
        assert response.status_code == 302
        assert (
            response.location
            == f"/access/organisation/{authenticated_grant_recipient_member_client.organisation.id}/grants"
        )

    def test_get_index_two_grant_recipient_orgs_redirects(self, authenticated_grant_recipient_member_client, factories):
        user = authenticated_grant_recipient_member_client.user
        grant = authenticated_grant_recipient_member_client.grant
        organisation = factories.organisation.create()

        factories.grant_recipient.create(grant=grant, organisation=organisation)
        factories.user_role.create(
            user=user, organisation=organisation, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
        )

        response = authenticated_grant_recipient_member_client.get(url_for("access_grant_funding.index"))
        assert response.status_code == 302
        assert response.location == "/access/organisations"

    def test_get_index_403_if_no_permissions(self, authenticated_no_role_client):
        response = authenticated_no_role_client.get(url_for("access_grant_funding.index"), follow_redirects=True)
        assert response.status_code == 403


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


class TestListOrganisations:
    @pytest.mark.parametrize(
        "client_fixture, can_access",
        (
            ("authenticated_no_role_client", False),
            ("authenticated_grant_recipient_member_client", True),
        ),
    )
    def test_get_list_organisations(self, factories, client, request, client_fixture, can_access):
        client = request.getfixturevalue(client_fixture)
        if can_access:
            user = client.user
            grant = client.grant
            second_organisation = factories.organisation.create()
            factories.grant_recipient.create(organisation=second_organisation, grant=grant)
            factories.user_role.create(
                user=user, permissions=[RoleEnum.MEMBER], organisation=second_organisation, grant=grant
            )
        response = client.get(url_for("access_grant_funding.list_organisations"))
        if can_access:
            assert response.status_code == 200
            soup = BeautifulSoup(response.data, "html.parser")
            assert get_h1_text(soup) == "Select an organisation"
        else:
            assert response.status_code == 403

    def test_get_list_organisations_redirects_when_only_one_org(self, authenticated_grant_recipient_member_client):
        organisation = authenticated_grant_recipient_member_client.organisation
        response = authenticated_grant_recipient_member_client.get(
            url_for("access_grant_funding.list_organisations"), follow_redirects=False
        )
        assert response.status_code == 302
        assert response.location == url_for("access_grant_funding.list_grants", organisation_id=organisation.id)


class TestListGrantTeam:
    def test_get_list_grant_team(self, authenticated_grant_recipient_data_provider_client):
        organisation = authenticated_grant_recipient_data_provider_client.organisation
        grant = authenticated_grant_recipient_data_provider_client.grant

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for("access_grant_funding.list_grant_team", organisation_id=organisation.id, grant_id=grant.id)
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Team"
        assert any(
            authenticated_grant_recipient_data_provider_client.user.name in td.get_text() for td in soup.find_all("td")
        )

    def test_get_list_grant_team_shows_multiple_permissions(
        self, authenticated_grant_recipient_data_provider_client, factories
    ):
        user = authenticated_grant_recipient_data_provider_client.user
        organisation = authenticated_grant_recipient_data_provider_client.organisation
        grant = authenticated_grant_recipient_data_provider_client.grant

        factories.user_role.create(user=user, organisation=organisation, grant=None, permissions=[RoleEnum.CERTIFIER])

        response = authenticated_grant_recipient_data_provider_client.get(
            url_for("access_grant_funding.list_grant_team", organisation_id=organisation.id, grant_id=grant.id)
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == "Team"
        assert any("Can certify" in td.get_text() for td in soup.find_all("td"))
        assert any("Can edit and submit" in td.get_text() for td in soup.find_all("td"))


class TestCookieBanner:
    def test_access_loads_with_invisible_cookie_banner(
        self, authenticated_grant_recipient_data_provider_client, grant_recipient
    ):
        response = authenticated_grant_recipient_data_provider_client.get(
            url_for(
                "access_grant_funding.list_reports",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h2_text(soup) == "Cookies on Access grant funding"

        # as no JS has run, the cookie banner should be hidden
        assert soup.find_all("div", class_="govuk-cookie-banner")[0].attrs.get("hidden", None) is not None
