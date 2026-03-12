from datetime import date, timedelta

from flask import url_for
from sqlalchemy.orm import Session

from app.common.data.interfaces.grant_recipients import get_grant_recipient_or_none
from app.common.data.types import (
    CollectionStatusEnum,
    CollectionType,
    GrantRecipientStatus,
    GrantStatusEnum,
    RoleEnum,
)
from tests.conftest import FundingServiceTestClient, _Factories


class TestPublicGrantSignUp:
    def test_get_public_sign_up_page_returns_404_when_no_public_sign_up_collection(
        self, anonymous_client: FundingServiceTestClient, factories: _Factories
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
            allow_public_sign_up=False,
        )
        response = anonymous_client.get(
            url_for("access_grant_funding.public_grant_sign_up", grant_slug=grant.name.lower().replace(" ", "-"))
        )
        assert response.status_code == 404

    def test_get_public_sign_up_page_returns_404_when_grant_not_live(
        self, anonymous_client: FundingServiceTestClient, factories: _Factories
    ):
        grant = factories.grant.create(status=GrantStatusEnum.DRAFT)
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
            allow_public_sign_up=True,
        )
        response = anonymous_client.get(
            url_for("access_grant_funding.public_grant_sign_up", grant_slug=grant.name.lower().replace(" ", "-"))
        )
        assert response.status_code == 404

    def test_get_public_sign_up_page_returns_404_when_collection_not_open(
        self, anonymous_client: FundingServiceTestClient, factories: _Factories
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.CLOSED,
            allow_public_sign_up=True,
        )
        response = anonymous_client.get(
            url_for("access_grant_funding.public_grant_sign_up", grant_slug=grant.name.lower().replace(" ", "-"))
        )
        assert response.status_code == 404

    def test_get_public_sign_up_page_success(self, anonymous_client: FundingServiceTestClient, factories: _Factories):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        deadline = date.today() + timedelta(days=30)
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
            allow_public_sign_up=True,
            submission_period_end_date=deadline,
        )
        response = anonymous_client.get(
            url_for("access_grant_funding.public_grant_sign_up", grant_slug=grant.name.lower().replace(" ", "-"))
        )
        assert response.status_code == 200
        assert grant.name in response.text
        assert grant.description in response.text
        assert "X-Robots-Tag" in response.headers
        assert "noindex" in response.headers["X-Robots-Tag"]
        assert "nofollow" in response.headers["X-Robots-Tag"]

    def test_get_public_sign_up_page_has_robots_meta_tag(
        self, anonymous_client: FundingServiceTestClient, factories: _Factories
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
            allow_public_sign_up=True,
        )
        response = anonymous_client.get(
            url_for("access_grant_funding.public_grant_sign_up", grant_slug=grant.name.lower().replace(" ", "-"))
        )
        assert response.status_code == 200
        assert 'name="robots" content="noindex, nofollow"' in response.text

    def test_post_public_sign_up_sets_session_variable(
        self, anonymous_client: FundingServiceTestClient, factories: _Factories
    ):
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
            allow_public_sign_up=True,
        )
        response = anonymous_client.post(
            url_for("access_grant_funding.public_grant_sign_up", grant_slug=grant.name.lower().replace(" ", "-")),
            follow_redirects=False,
        )
        assert response.status_code == 302
        assert "/request-a-link-to-sign-in" in response.location

        with anonymous_client.session_transaction() as sess:
            assert sess["signing_up_for_grant_id"] == str(grant.id)

    def test_get_public_sign_up_page_returns_404_for_nonexistent_grant(
        self, anonymous_client: FundingServiceTestClient
    ):
        response = anonymous_client.get(
            url_for("access_grant_funding.public_grant_sign_up", grant_slug="nonexistent-grant")
        )
        assert response.status_code == 404

    def test_get_public_sign_up_page_returns_404_for_invalid_slug(self, anonymous_client: FundingServiceTestClient):
        response = anonymous_client.get("/access/grants/invalid slug!")
        assert response.status_code == 404


class TestPublicSignUpOnMagicLinkClaim:
    def test_magic_link_claim_processes_public_sign_up_new_grant_recipient(
        self,
        anonymous_client: FundingServiceTestClient,
        factories: _Factories,
        db_session: Session,
    ):
        """When a user signs in with a matching email domain and the org is NOT a grant recipient yet,
        we should create a new grant recipient and assign the user as data provider."""
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
            allow_public_sign_up=True,
        )
        organisation = factories.organisation.create(can_manage_grants=False, trusted_email_domain="example.org")

        user = factories.user.create(email="testuser@example.org")
        magic_link = factories.magic_link.create(user=user, email="testuser@example.org")

        with anonymous_client.session_transaction() as sess:
            sess["signing_up_for_grant_id"] = str(grant.id)

        response = anonymous_client.post(
            url_for("auth.claim_magic_link", magic_link_code=magic_link.code),
        )
        assert response.status_code == 302

        grant_recipient = get_grant_recipient_or_none(grant.id, organisation.id)
        assert grant_recipient is not None
        assert grant_recipient.status == GrantRecipientStatus.APPLYING

        assert any(
            role.organisation_id == organisation.id
            and role.grant_id == grant.id
            and RoleEnum.DATA_PROVIDER in role.permissions
            for role in user.roles
        )

        with anonymous_client.session_transaction() as sess:
            assert "signing_up_for_grant_id" not in sess

    def test_magic_link_claim_processes_public_sign_up_existing_grant_recipient(
        self,
        anonymous_client: FundingServiceTestClient,
        factories: _Factories,
        db_session: Session,
    ):
        """When a user signs in with a matching email domain and the org IS already a grant recipient,
        we should just assign the user as data provider."""
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
            allow_public_sign_up=True,
        )
        organisation = factories.organisation.create(can_manage_grants=False, trusted_email_domain="example.org")
        factories.grant_recipient.create(grant=grant, organisation=organisation)

        user = factories.user.create(email="testuser@example.org")
        magic_link = factories.magic_link.create(user=user, email="testuser@example.org")

        with anonymous_client.session_transaction() as sess:
            sess["signing_up_for_grant_id"] = str(grant.id)

        response = anonymous_client.post(
            url_for("auth.claim_magic_link", magic_link_code=magic_link.code),
        )
        assert response.status_code == 302

        assert any(
            role.organisation_id == organisation.id
            and role.grant_id == grant.id
            and RoleEnum.DATA_PROVIDER in role.permissions
            for role in user.roles
        )

    def test_magic_link_claim_no_match_when_email_domain_not_found(
        self,
        anonymous_client: FundingServiceTestClient,
        factories: _Factories,
        db_session: Session,
    ):
        """When the user's email domain doesn't match any organisation, no grant recipient should be created."""
        grant = factories.grant.create(status=GrantStatusEnum.LIVE)
        factories.collection.create(
            grant=grant,
            type=CollectionType.APPLICATION,
            status=CollectionStatusEnum.OPEN,
            allow_public_sign_up=True,
        )

        user = factories.user.create(email="testuser@nomatch.org")
        magic_link = factories.magic_link.create(user=user, email="testuser@nomatch.org")

        with anonymous_client.session_transaction() as sess:
            sess["signing_up_for_grant_id"] = str(grant.id)

        response = anonymous_client.post(
            url_for("auth.claim_magic_link", magic_link_code=magic_link.code),
        )
        assert response.status_code == 302

        # Session variable should still be cleaned up
        with anonymous_client.session_transaction() as sess:
            assert "signing_up_for_grant_id" not in sess

    def test_magic_link_claim_without_sign_up_session_does_nothing(
        self,
        anonymous_client: FundingServiceTestClient,
        factories: _Factories,
        db_session: Session,
    ):
        """Normal magic link sign-in without signing_up_for_grant_id should not trigger any sign-up logic."""
        user = factories.user.create(email="normaluser@example.org")
        magic_link = factories.magic_link.create(user=user, email="normaluser@example.org")

        response = anonymous_client.post(
            url_for("auth.claim_magic_link", magic_link_code=magic_link.code),
        )
        assert response.status_code == 302

        # No new roles should be created (user has no roles)
        assert len(user.roles) == 0
