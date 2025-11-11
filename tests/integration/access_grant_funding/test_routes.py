import uuid

import pytest
from bs4 import BeautifulSoup
from flask import url_for

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
