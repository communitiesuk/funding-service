import datetime
import uuid

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from flask_login import login_user
from sqlalchemy import select

from app.common.data.models import GrantRecipient
from app.common.data.models_user import UserRole
from app.common.data.types import (
    AuthMethodEnum,
    CollectionStatusEnum,
    GrantRecipientModeEnum,
    GrantRecipientStatusEnum,
    GrantStatusEnum,
    OrganisationModeEnum,
    RoleEnum,
)
from tests.utils import get_h1_text, get_h2_text


class TestIndex:
    def test_get_index_just_one_grant_recipient_redirects(self, authenticated_grant_recipient_member_client):
        response = authenticated_grant_recipient_member_client.get(url_for("access_grant_funding.index"))
        assert response.status_code == 302
        assert response.location == (
            f"/access/organisation/{authenticated_grant_recipient_member_client.organisation.id}"
            f"/grants/{authenticated_grant_recipient_member_client.grant.id}/forms"
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
                "access_grant_funding.list_collections",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
            )
        )

        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h2_text(soup) == "Cookies on Access grant funding"

        # as no JS has run, the cookie banner should be hidden
        assert soup.find_all("div", class_="govuk-cookie-banner")[0].attrs.get("hidden", None) is not None


class TestPublicSignUpStartPage:
    def test_404_when_grant_slug_unknown(self, anonymous_client, factories):
        collection = factories.collection.create(
            grant__status=GrantStatusEnum.LIVE,
            status=CollectionStatusEnum.OPEN,
            allow_public_sign_up=True,
            slug="collection-slug",
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug="not-a-real-grant",
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 404

    def test_404_when_collection_slug_unknown(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug="not-a-real-collection",
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status, allow_public_sign_up, expected_status",
        (
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, True, 200),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, False, 404),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN, True, 404),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN, True, 404),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT, True, 404),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED, True, 404),
        ),
    )
    def test_anonymous_access_depends_on_status_and_allow_public_sign_up(
        self,
        anonymous_client,
        factories,
        grant_status,
        collection_status,
        allow_public_sign_up,
        expected_status,
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=allow_public_sign_up,
            slug="collection-slug",
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == expected_status

    @pytest.mark.parametrize(
        "grant_status, collection_status",
        (
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED),
        ),
    )
    def test_deliver_user_testing_access_allowed_for_any_status(
        self, anonymous_client, factories, user, db_session, grant_status, collection_status
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        can_manage_grants_organisation = grant.organisation

        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=True,
            slug="collection-slug",
        )
        factories.user_role.create(
            user=user, organisation=can_manage_grants_organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 200

    def test_page_content_with_prospectus_url(self, anonymous_client, factories):
        grant = factories.grant.create(
            status=GrantStatusEnum.LIVE, name="Test grant name", slug="grant-slug", description="Some grant description"
        )
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
            prospectus_url="https://example.com/prospectus",
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert get_h1_text(soup) == f"Apply for the {grant.name}"
        assert "Some grant description" in soup.get_text()
        assert soup.find("meta", attrs={"name": "robots"})["content"] == "noindex, nofollow"
        assert soup.find("a", href="https://example.com/prospectus") is not None

    def test_page_content_without_prospectus_url(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
            prospectus_url=None,
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "prospectus" not in soup.get_text().lower()

    def test_page_content_with_submission_deadline(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
            submission_period_end_date=datetime.date(2026, 8, 30),
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Deadline for applications" in soup.get_text()
        assert "30 August 2026" in soup.get_text()

    def test_page_content_without_submission_deadline(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
            submission_period_end_date=None,
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Deadline for applications" not in soup.get_text()

    def test_page_start_button(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )
        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        form = soup.find("form")
        assert form is not None
        assert form.get("method", "").lower() == "post"
        start_button = form.find("button", {"class": "govuk-button"})
        assert start_button is not None
        assert "Start now" in start_button.get_text(strip=True)

    def test_post_sets_signing_up_session_flag_and_redirects(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )

        response = anonymous_client.post(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "auth.collection_request_a_link_to_public_sign_up", grant_slug=grant.slug, collection_slug=collection.slug
        )

        with anonymous_client.session_transaction() as flask_session:
            assert flask_session["signing_up_for_collection_id"] == collection.id

    def test_post_as_member_deliver_user_skips_magic_link_and_redirects_to_sign_up_router(
        self, authenticated_grant_member_client, factories
    ):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )

        response = authenticated_grant_member_client.post(
            url_for(
                "access_grant_funding.public_sign_up_start_page",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_router", grant_slug=grant.slug, collection_slug=collection.slug
        )

        with authenticated_grant_member_client.session_transaction() as flask_session:
            assert "signing_up_for_collection_id" not in flask_session


class TestPublicSignUpRouter:
    def test_get_404s_for_unknown_grant(self, authenticated_no_role_client, factories):
        collection = factories.collection.create(slug="collection-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug="not-a-real-grant",
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 404

    def test_get_404s_for_unknown_collection(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug="not-a-real-collection",
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status, allow_public_sign_up, expected_status",
        (
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, True, 302),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, False, 404),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN, True, 404),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN, True, 404),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT, True, 404),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED, True, 404),
        ),
    )
    def test_anonymous_access_depends_on_status_and_allow_public_sign_up(
        self,
        anonymous_client,
        factories,
        grant_status,
        collection_status,
        allow_public_sign_up,
        expected_status,
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=allow_public_sign_up,
            slug="collection-slug",
        )

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == expected_status

    @pytest.mark.parametrize(
        "grant_status, collection_status",
        (
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED),
        ),
    )
    def test_deliver_user_testing_access_allowed_for_any_status(
        self, anonymous_client, factories, user, db_session, grant_status, collection_status
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        can_manage_grants_organisation = grant.organisation

        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=True,
            slug="collection-slug",
        )
        factories.user_role.create(
            user=user, organisation=can_manage_grants_organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        response = anonymous_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302

    def test_get_redirects_to_eligible_to_apply(self, authenticated_grant_member_client, factories):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant,
            status=CollectionStatusEnum.OPEN,
            slug="collection-slug",
            allow_public_sign_up=True,
        )

        response = authenticated_grant_member_client.get(
            url_for(
                "access_grant_funding.public_sign_up_router",
                grant_slug=grant.slug,
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug
        )


class TestEligibleToApplyPage:
    def test_get_redirects_when_not_authenticated(self, anonymous_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )

        response = anonymous_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.public_sign_up_start_page", grant_slug=grant.slug, collection_slug=collection.slug
        )

    def test_get_404s_for_unknown_grant(self, authenticated_no_role_client, factories):
        collection = factories.collection.create(slug="collection-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.eligible_to_apply",
                grant_slug="not-a-real-grant",
                collection_slug=collection.slug,
            )
        )

        assert response.status_code == 404

    def test_get_404s_for_unknown_collection(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")

        response = authenticated_no_role_client.get(
            url_for(
                "access_grant_funding.eligible_to_apply",
                grant_slug=grant.slug,
                collection_slug="not-a-real-collection",
            )
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status, allow_public_sign_up",
        (
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN, False),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN, True),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN, True),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT, True),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED, True),
        ),
    )
    def test_get_depends_on_status_and_allow_public_sign_up(
        self,
        authenticated_no_role_client,
        factories,
        grant_status,
        collection_status,
        allow_public_sign_up,
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=allow_public_sign_up,
            slug="collection-slug",
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 404

    @pytest.mark.parametrize(
        "grant_status, collection_status",
        (
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.DRAFT, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.DRAFT),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.ONBOARDING, CollectionStatusEnum.OPEN),
            (GrantStatusEnum.LIVE, CollectionStatusEnum.CLOSED),
        ),
    )
    def test_deliver_user_testing_access_allowed_for_any_status(
        self, anonymous_client, factories, user, db_session, grant_status, collection_status
    ):
        grant = factories.grant.create(status=grant_status, slug="grant-slug")
        can_manage_grants_organisation = grant.organisation

        collection = factories.collection.create(
            grant=grant,
            status=collection_status,
            allow_public_sign_up=True,
            slug="collection-slug",
        )
        factories.user_role.create(
            user=user, organisation=can_manage_grants_organisation, grant=grant, permissions=[RoleEnum.MEMBER]
        )
        factories.organisation.create(
            name="Test Organisation",
            domains=[user.email.split("@")[-1]],
            mode=OrganisationModeEnum.TEST,
        )

        login_user(user)
        with anonymous_client.session_transaction() as flask_session:
            flask_session["auth"] = AuthMethodEnum.SSO
        db_session.commit()

        response = anonymous_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 200

    @pytest.mark.authenticate_as("test@no-matching-org.com")
    def test_get_400s_when_no_organisation_matches_email_domain(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 400

    @pytest.mark.authenticate_as("test@shared-domain.com")
    def test_get_400s_when_multiple_organisations_match_email_domain(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        factories.organisation.create(name="Org A", domains=["shared-domain.com"])
        factories.organisation.create(name="Org B", domains=["shared-domain.com"])

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 400

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_get_with_known_grant_and_collection(self, authenticated_no_role_client, factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug", name="Test grant name")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        factories.organisation.create(name="Test Organisation", domains=["example-org.com"])

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.get(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 200

        soup = BeautifulSoup(response.data, "html.parser")
        assert "You are eligible to apply" in get_h1_text(soup)
        assert "Test grant name" in soup.text
        assert "Test Organisation" in soup.text

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_creates_grant_recipient_and_grants_data_provider_role(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(
            name="Test Organisation",
            domains=["example-org.com"],
            external_id="org-1",
            mode=OrganisationModeEnum.LIVE,
        )
        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=grant.id,
        )

        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).one()
        assert grant_recipient.status == GrantRecipientStatusEnum.APPLYING
        assert grant_recipient.mode == GrantRecipientModeEnum.LIVE

        user_role = db_session.scalars(
            select(UserRole).where(
                UserRole.user_id == authenticated_no_role_client.user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == grant.id,
            )
        ).one()
        assert RoleEnum.DATA_PROVIDER in user_role.permissions

        # We delete the signing_up_for_collection_id session flag
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert "signing_up_for_collection_id" not in flask_session

        # Success banner shows on the forms page
        followed_response = authenticated_no_role_client.get(response.location, follow_redirects=True)
        assert followed_response.status_code == 200
        soup = BeautifulSoup(followed_response.data, "html.parser")
        assert "Success" in soup.text
        assert "Sign in complete. You can start your application." in soup.text

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_reuses_existing_grant_recipient_when_user_already_has_role(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(name="Test Organisation", domains=["example-org.com"])
        existing_grant_recipient = factories.grant_recipient.create(grant=grant, organisation=organisation)
        factories.user_role.create(
            user=authenticated_no_role_client.user,
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 302

        grant_recipients = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).all()

        assert len(grant_recipients) == 1
        assert grant_recipients[0].id == existing_grant_recipient.id

        # We delete the signing_up_for_collection_id session flag
        with authenticated_no_role_client.session_transaction() as flask_session:
            assert "signing_up_for_collection_id" not in flask_session

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_403s_when_grant_recipient_exists_and_user_has_no_role(
        self, authenticated_no_role_client, factories, db_session
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE, slug="grant-slug")
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(name="Test Organisation", domains=["example-org.com"])
        # A colleague from the same email domain has already applied, but this user has no role on it yet
        factories.grant_recipient.create(grant=grant, organisation=organisation)

        with authenticated_no_role_client.session_transaction() as flask_session:
            flask_session["signing_up_for_collection_id"] = collection.id

        response = authenticated_no_role_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 403

        grant_recipients = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).all()
        assert len(grant_recipients) == 1

        user_role = db_session.scalars(
            select(UserRole).where(
                UserRole.user_id == authenticated_no_role_client.user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == grant.id,
            )
        ).one_or_none()
        assert user_role is None

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_as_deliver_user_redirects_to_submission_page(self, authenticated_grant_member_client, factories):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        factories.question.create(form__collection=collection)
        organisation = factories.organisation.create(
            name="Test Organisation", domains=["example-org.com"], mode=OrganisationModeEnum.TEST
        )
        factories.grant_recipient.create(grant=grant, organisation=organisation, mode=GrantRecipientModeEnum.TEST)
        factories.user_role.create(
            user=authenticated_grant_member_client.user,
            organisation=organisation,
            grant=grant,
            permissions=[RoleEnum.DATA_PROVIDER],
        )

        response = authenticated_grant_member_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        # Redirects to the forms page
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=grant.id,
        )

        # Checking submission page loads correctly
        followed_response = authenticated_grant_member_client.get(response.location, follow_redirects=True)
        assert followed_response.status_code == 200
        soup = BeautifulSoup(followed_response.data, "html.parser")
        assert "Testing grant recipient journey" in soup.text

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_as_deliver_user_without_existing_grant_recipient_creates_one(
        self, authenticated_grant_member_client, factories, db_session
    ):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(
            name="Test Organisation", domains=["example-org.com"], mode=OrganisationModeEnum.TEST
        )
        # The user has no role at all on the matched organisation, and no TEST grant recipient exists yet

        response = authenticated_grant_member_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        # Redirects to the forms page
        assert response.status_code == 302
        assert response.location == url_for(
            "access_grant_funding.list_collections",
            organisation_id=organisation.id,
            grant_id=grant.id,
        )

        # A TEST grant recipient is auto-created for the tester, along with the DATA_PROVIDER role
        grant_recipient = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).one()
        assert grant_recipient.status == GrantRecipientStatusEnum.APPLYING
        assert grant_recipient.mode == GrantRecipientModeEnum.TEST

        user_role = db_session.scalars(
            select(UserRole).where(
                UserRole.user_id == authenticated_grant_member_client.user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == grant.id,
            )
        ).one()
        assert RoleEnum.DATA_PROVIDER in user_role.permissions

        # Submission page now loads successfully
        followed_response = authenticated_grant_member_client.get(response.location, follow_redirects=True)
        assert followed_response.status_code == 200

    @pytest.mark.authenticate_as("test@example-org.com")
    def test_post_as_deliver_user_without_access_to_existing_grant_recipient_403s(
        self, authenticated_grant_member_client, factories, db_session
    ):
        grant = authenticated_grant_member_client.grant
        collection = factories.collection.create(
            grant=grant, status=CollectionStatusEnum.OPEN, slug="collection-slug", allow_public_sign_up=True
        )
        organisation = factories.organisation.create(
            name="Test Organisation", domains=["example-org.com"], mode=OrganisationModeEnum.TEST
        )
        # A TEST grant recipient already exists for this organisation and grant, but the user has no role on it
        factories.grant_recipient.create(grant=grant, organisation=organisation, mode=GrantRecipientModeEnum.TEST)

        response = authenticated_grant_member_client.post(
            url_for("access_grant_funding.eligible_to_apply", grant_slug=grant.slug, collection_slug=collection.slug)
        )

        assert response.status_code == 403

        # No new grant recipient or role was created for the user
        grant_recipients = db_session.scalars(
            select(GrantRecipient).where(
                GrantRecipient.grant_id == grant.id, GrantRecipient.organisation_id == organisation.id
            )
        ).all()
        assert len(grant_recipients) == 1

        user_role = db_session.scalars(
            select(UserRole).where(
                UserRole.user_id == authenticated_grant_member_client.user.id,
                UserRole.organisation_id == organisation.id,
                UserRole.grant_id == grant.id,
            )
        ).one_or_none()
        assert user_role is None
