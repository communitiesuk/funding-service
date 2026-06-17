import uuid

import pytest
from bs4 import BeautifulSoup
from flask import url_for

from app.common.data.models import Collection
from app.common.data.types import CollectionStatusEnum, CollectionType, GrantStatusEnum
from app.common.forms import GenericConfirmDeletionForm
from tests.utils import AnyStringMatching, get_form_data, page_has_button, page_has_link


class TestListPreAwardForms:
    def test_404(self, authenticated_grant_member_client):
        response = authenticated_grant_member_client.get(
            url_for("deliver_grant_funding.list_pre_award_forms", grant_id=uuid.uuid4())
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "client_fixture, can_edit",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_grant_member_get_no_forms(
        self, request: pytest.FixtureRequest, client_fixture: str, can_edit: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        client.grant.allow_pre_award = True

        response = client.get(url_for("deliver_grant_funding.list_pre_award_forms", grant_id=client.grant.id))
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert client.grant.name in soup.text

        expected_links = [
            ("Add a form", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/applications/set-up")),
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
    def test_grant_member_get_with_forms(
        self, request: pytest.FixtureRequest, client_fixture: str, can_edit: bool, factories
    ):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant or factories.grant.create()
        grant.allow_pre_award = True
        factories.collection.create(grant=grant, type=CollectionType.APPLICATION)

        response = client.get(url_for("deliver_grant_funding.list_pre_award_forms", grant_id=grant.id))
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert grant.name in soup.text

        test_submission_links = page_has_link(soup, "0 test submissions")
        assert test_submission_links is not None
        assert test_submission_links.get("href") == AnyStringMatching(
            r"/deliver/grant/[a-z0-9-]{36}/applications/[a-z0-9-]{36}/submissions/test"
        )

        live_submissions_links = page_has_link(soup, "0 live submissions")
        assert live_submissions_links is not None
        assert live_submissions_links.get("href") == AnyStringMatching(
            r"/deliver/grant/[a-z0-9-]{36}/applications/[a-z0-9-]{36}/submissions/live"
        )

        expected_links = [
            ("Add a form", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/applications/set-up")),
            ("Add sections", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/applications/[a-z0-9-]{36}/add-section")),
            ("Change name", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/applications/[a-z0-9-]{36}/change-name")),
            ("Delete", AnyStringMatching(r"/deliver/grant/[a-z0-9-]{36}/pre-award\?delete")),
        ]
        for expected_link in expected_links:
            link = page_has_link(soup, expected_link[0])
            assert (link is not None) is can_edit

            if can_edit:
                assert link.get("href") == expected_link[1]

    def test_get_with_delete_parameter_no_submissions(self, authenticated_grant_admin_client, factories):
        authenticated_grant_admin_client.grant.allow_pre_award = True
        pre_award_form = factories.collection.create(
            grant=authenticated_grant_admin_client.grant, name="Test form", type=CollectionType.APPLICATION
        )

        response = authenticated_grant_admin_client.get(
            url_for(
                "deliver_grant_funding.list_pre_award_forms",
                grant_id=authenticated_grant_admin_client.grant.id,
                delete=pre_award_form.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_button(soup, "Yes, delete this form")

    @pytest.mark.parametrize(
        "client_fixture, can_delete",
        (
            ("authenticated_grant_member_client", False),
            ("authenticated_grant_admin_client", True),
        ),
    )
    def test_post_delete(
        self, request: pytest.FixtureRequest, client_fixture: str, can_delete: bool, factories, db_session
    ):
        client = request.getfixturevalue(client_fixture)
        client.grant.allow_pre_award = True
        pre_award_form = factories.collection.create(
            grant=client.grant, name="Test Form", type=CollectionType.APPLICATION
        )

        form = GenericConfirmDeletionForm(data={"confirm_deletion": True})
        response = client.post(
            url_for("deliver_grant_funding.list_pre_award_forms", grant_id=client.grant.id, delete=pre_award_form.id),
            data=get_form_data(form),
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == AnyStringMatching("^/deliver/grant/[a-z0-9-]{36}/pre-award$")

        deleted_form = db_session.get(Collection, pre_award_form.id)
        assert (deleted_form is None) == can_delete

    @pytest.mark.parametrize(
        "collection_status", [status for status in CollectionStatusEnum if status != CollectionStatusEnum.DRAFT]
    )
    @pytest.mark.parametrize(
        "client_fixture", ("authenticated_grant_admin_client", "authenticated_platform_admin_client")
    )
    def test_get_no_change_or_delete_links_when_form_not_draft(
        self, factories, collection_status, client_fixture, request
    ):
        client = request.getfixturevalue(client_fixture)
        grant = client.grant if client.grant else factories.grant.create()
        grant.allow_pre_award = True
        factories.collection.create(
            grant=grant, name="Test Form", type=CollectionType.APPLICATION, status=collection_status
        )

        response = client.get(url_for("deliver_grant_funding.list_pre_award_forms", grant_id=grant.id))

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")

        change_name_link = page_has_link(soup, "Change name")
        delete_link = page_has_link(soup, "Delete")

        assert change_name_link is None
        assert delete_link is None

    def test_404_when_pre_award_flag_disabled(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.list_pre_award_forms", grant_id=authenticated_grant_admin_client.grant.id)
        )
        assert response.status_code == 404

    @pytest.mark.parametrize(
        "status, expected",
        (
            (GrantStatusEnum.DRAFT, "Forms cannot be published until the grant is live."),
            (GrantStatusEnum.LIVE, "There are no forms live."),
        ),
    )
    def test_get_grant_status_description(
        self,
        factories,
        authenticated_platform_admin_client,
        status: GrantStatusEnum,
        expected: str,
    ):
        grant = factories.grant.create(status=status, allow_pre_award=True)

        response = authenticated_platform_admin_client.get(
            url_for("deliver_grant_funding.list_pre_award_forms", grant_id=grant.id)
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert grant.name in soup.text

        assert expected in " ".join(soup.text.split())


class TestPreAwardNavigation:
    def test_nav_shows_pre_award_link_when_flag_enabled(self, authenticated_grant_admin_client):
        authenticated_grant_admin_client.grant.allow_pre_award = True

        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.grant_details", grant_id=authenticated_grant_admin_client.grant.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_link(soup, "Pre-award") is not None

    def test_nav_hides_pre_award_link_when_flag_disabled(self, authenticated_grant_admin_client):
        response = authenticated_grant_admin_client.get(
            url_for("deliver_grant_funding.grant_details", grant_id=authenticated_grant_admin_client.grant.id)
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_link(soup, "Pre-award") is None
