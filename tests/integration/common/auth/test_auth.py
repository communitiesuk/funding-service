import datetime
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from sqlalchemy import func, select

from app.common.auth.authorisation_helper import AuthorisationHelper
from app.common.data import interfaces
from app.common.data.models_user import Invitation, MagicLink, User, UserRole
from app.common.data.types import RoleEnum
from tests.utils import AnyStringMatching, get_h1_text, get_h2_text, page_has_error


class TestSignInView:
    def test_get(self, anonymous_client):
        response = anonymous_client.get(url_for("auth.request_a_link_to_sign_in"))
        assert response.status_code == 200
        assert b"Request a link to sign in" in response.data

    def test_post_invalid_email(self, anonymous_client):
        response = anonymous_client.post(
            url_for("auth.request_a_link_to_sign_in"), data={"email_address": "invalid-email"}
        )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Enter an email address in the correct format")

    def get_test_post_non_communities_email(self, client):
        response = client.post(url_for("auth.request_a_link_to_sign_in"), data={"email_address": "test@example.com"})
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Email address must end with @communities.gov.uk or @test.communities.gov.uk")

    def test_post_mhclg_email_redirects_to_sso(self, anonymous_client, mock_notification_service_calls):
        response = anonymous_client.post(
            url_for("auth.request_a_link_to_sign_in"),
            data={"email_address": "test@communities.gov.uk"},
            follow_redirects=True,
        )
        soup = BeautifulSoup(response.data, "html.parser")

        assert response.status_code == 200
        assert "Deliver grant funding" in get_h1_text(soup)
        assert "Sign in with your MHCLG account" in get_h2_text(soup)
        with anonymous_client.session_transaction() as session:
            assert "magic_link_redirect" not in session

    def test_post_valid_non_mhclg_email(self, anonymous_client, mock_notification_service_calls):
        response = anonymous_client.post(
            url_for("auth.request_a_link_to_sign_in"),
            data={"email_address": "test@example.com"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Check your email" in response.data
        assert b"test@example.com" in response.data
        assert len(mock_notification_service_calls) == 1
        assert mock_notification_service_calls[0].kwargs["personalisation"]["magic_link"] == AnyStringMatching(
            r"http://funding.communities.gov.localhost:8080/sign-in/.*"
        )
        assert (
            mock_notification_service_calls[0].kwargs["personalisation"]["request_new_magic_link"]
            == "http://funding.communities.gov.localhost:8080/request-a-link-to-sign-in"
        )

    @pytest.mark.parametrize(
        "next_, safe_next",
        (
            ("/blah/blah", "/blah/blah"),
            ("https://bad.place/blah", "/"),  # Single test case; see TestSanitiseRedirectURL for more exhaustion
        ),
    )
    def test_post_valid_email_with_redirect(
        self, anonymous_client, mock_notification_service_calls, db_session, next_, safe_next
    ):
        with anonymous_client.session_transaction() as session:
            session["next"] = next_

        response = anonymous_client.post(
            url_for("auth.request_a_link_to_sign_in"),
            data={"email_address": "test@example.com"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert (
            db_session.scalar(select(MagicLink).order_by(MagicLink.created_at_utc.desc())).redirect_to_path == safe_next
        )

        with anonymous_client.session_transaction() as session:
            assert "next" not in session


class TestCheckEmailPage:
    def test_get(self, anonymous_client, factories):
        magic_link = factories.magic_link.create(email="test@communities.gov.uk")
        response = anonymous_client.get(url_for("auth.check_email", magic_link_id=magic_link.id))
        assert response.status_code == 200
        assert b"Check your email" in response.data
        assert b"test@communities.gov.uk" in response.data


class TestClaimMagicLinkView:
    def test_get(self, anonymous_client, factories):
        magic_link = factories.magic_link.create()

        response = anonymous_client.get(url_for("auth.claim_magic_link", magic_link_code=magic_link.code))
        assert response.status_code == 200
        assert b"Sign in" in response.data

    def test_redirect_on_unknown_magic_link(self, anonymous_client):
        response = anonymous_client.get(url_for("auth.claim_magic_link", magic_link_code="unknown-code"))
        assert response.status_code == 302
        assert response.location == url_for("auth.request_a_link_to_sign_in", link_expired=True)

    def test_redirect_on_used_magic_link(self, anonymous_client, factories):
        # FIXME: Check that the session["next"] is the original redirect_to_path value
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk",
            redirect_to_path="/my-redirect",
            claimed_at_utc=datetime.datetime.now() - datetime.timedelta(hours=1),
        )
        response = anonymous_client.get(
            url_for("auth.claim_magic_link", magic_link_code=magic_link.code), follow_redirects=True
        )
        soup = BeautifulSoup(response.data, "html.parser")
        assert response.status_code == 200
        assert "Link expired" in get_h2_text(soup)

    def test_redirect_on_expired_magic_link(self, anonymous_client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk",
            redirect_to_path="/my-redirect",
            expires_at_utc=datetime.datetime.now() - datetime.timedelta(hours=1),
        )

        response = anonymous_client.get(url_for("auth.claim_magic_link", magic_link_code=magic_link.code))
        assert response.status_code == 302
        assert response.location == url_for("auth.request_a_link_to_sign_in", link_expired=True)

    @pytest.mark.parametrize(
        "redirect_to, safe_redirect_to",
        (
            ("/blah/blah", "/blah/blah"),
            ("https://bad.place/blah", "/"),  # Single test case; see TestSanitiseRedirectURL for more exhaustion
        ),
    )
    def test_post_claims_link_and_creates_user_and_redirects(
        self, anonymous_client, factories, db_session, redirect_to, safe_redirect_to
    ):
        user_email = "new_user@email.com"

        magic_link = interfaces.magic_link.create_magic_link(email=user_email, user=None, redirect_to_path=redirect_to)

        user_from_db = db_session.scalar(select(User).where(User.email == user_email))
        assert user_from_db is None

        user = interfaces.user.get_current_user()
        assert user.is_authenticated is False

        response = anonymous_client.post(
            url_for("auth.claim_magic_link", magic_link_code=magic_link.code),
            json={"submit": "yes"},
            follow_redirects=False,
        )

        user_from_db = db_session.scalar(select(User).where(User.email == user_email))

        assert response.status_code == 302
        assert response.location == safe_redirect_to
        assert magic_link.claimed_at_utc is not None
        assert magic_link.is_usable is False
        assert user.is_authenticated is True
        assert magic_link.user.id == user.id
        assert user_from_db is not None


class TestSignOutView:
    def test_get(self, anonymous_client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk", redirect_to_path="/my-redirect", claimed_at_utc=None
        )

        # A bit unencapsulated for testing the sign out view, but don't otherwise have an easy+reliable way to get
        # the user in the session
        anonymous_client.post(url_for("auth.claim_magic_link", magic_link_code=magic_link.code), json={"submit": "yes"})
        with anonymous_client.session_transaction() as session:
            assert "_user_id" in session

        response = anonymous_client.get(url_for("auth.sign_out"), follow_redirects=True)
        assert response.status_code == 200

        with anonymous_client.session_transaction() as session:
            assert "_user_id" not in session


class TestSSOSignInView:
    def test_get(self, anonymous_client):
        response = anonymous_client.get(url_for("auth.sso_sign_in"))
        assert response.status_code == 200
        assert b"A connected and consistent digital service" in response.data


class TestSSOGetTokenView:
    def test_get_without_fs_platform_admin_role_and_with_no_assigned_roles(self, app, anonymous_client):
        with patch("app.common.auth.build_msal_app") as mock_build_msap_app:
            # Partially mock the expected return value; just enough for the test.
            mock_build_msap_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test@test.communities.gov.uk",
                    "name": "SSO User",
                    "roles": [],
                    "sub": "someStringValue",
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"))

        assert response.status_code == 302
        assert response.location == url_for("auth.signed_in_but_no_permissions", invite_expired=False)

    def test_login_with_grant_member_role(self, anonymous_client, factories):
        with patch("app.common.auth.build_msal_app") as mock_build_msap_app:
            user = factories.user.create(email="test.member@communities.gov.uk")
            grant = factories.grant.create()
            factories.user_role.create(user=user, grant=grant, permissions=[RoleEnum.MEMBER])
            # Partially mock the expected return value; just enough for the test.
            mock_build_msap_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "Test.Member@communities.gov.uk",
                    "name": "SSO User",
                    "roles": [],
                    "sub": user.azure_ad_subject_id,
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=True)
            current_user = interfaces.user.get_current_user()
            assert not AuthorisationHelper.is_platform_admin(current_user)
            assert current_user.name == "SSO User"
            assert current_user.email == "Test.Member@communities.gov.uk"
            assert response.status_code == 200

    def test_get_without_any_roles_should_redirect(self, app, anonymous_client):
        with patch("app.common.auth.build_msal_app") as mock_build_msap_app:
            # Partially mock the expected return value; just enough for the test.
            mock_build_msap_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test@test.communities.gov.uk",
                    "name": "SSO User",
                    "sub": "someStringValue",
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"))

        assert response.status_code == 302
        assert response.location == url_for("auth.signed_in_but_no_permissions", invite_expired=False)

    def test_get_valid_token_with_redirect(self, anonymous_client, factories, db_session):
        dummy_grant = factories.grant.create()
        factories.user.create(email="test@test.communities.gov.uk", azure_ad_subject_id="subject_id")
        with anonymous_client.session_transaction() as session:
            session["next"] = url_for("deliver_grant_funding.grant_homepage", grant_id=dummy_grant.id)

        with patch("app.common.auth.build_msal_app") as mock_build_msap_app:
            # Partially mock the expected return value; just enough for the test.
            mock_build_msap_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test@test.communities.gov.uk",
                    "name": "SSO User",
                    "roles": ["FS_PLATFORM_ADMIN"],
                    "sub": "subject_id",
                }
            }
            response = anonymous_client.get(
                url_for("auth.sso_get_token"),
                follow_redirects=True,
            )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert dummy_grant.name in get_h1_text(soup)

        with anonymous_client.session_transaction() as session:
            assert "next" not in session

        new_user = db_session.scalar(select(User).where(User.email == "test@test.communities.gov.uk"))
        assert new_user.name == "SSO User"

    def test_platform_admin_first_login(self, anonymous_client, factories, db_session):
        with patch("app.common.auth.build_msal_app") as mock_build_msal_app:
            mock_build_msal_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test.member@communities.gov.uk",
                    "name": "SSO User",
                    "roles": ["FS_PLATFORM_ADMIN"],
                    "sub": "abc123",
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=True)
        user = interfaces.user.get_current_user()
        assert response.status_code == 200
        assert AuthorisationHelper.is_platform_admin(user)

    def test_platform_admin_with_fs_platform_admin_role_removed(self, anonymous_client, factories, db_session):
        with patch("app.common.auth.build_msal_app") as mock_build_msal_app:
            user = factories.user.create(email="test.member@communities.gov.uk", azure_ad_subject_id="abc123")
            factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN])

            mock_build_msal_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test.member@communities.gov.uk",
                    "name": "SSO User",
                    "roles": [],
                    "sub": "abc123",
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=False)
            updated_user = db_session.scalar(select(User).where(User.azure_ad_subject_id == "abc123"))

            assert AuthorisationHelper.is_platform_admin(updated_user) is False

        assert response.status_code == 302
        assert response.location == url_for("auth.signed_in_but_no_permissions", invite_expired=False)

    def test_platform_admin_with_grant_member_role_fs_platform_admin_role_removed(
        self, anonymous_client, factories, db_session
    ):
        with patch("app.common.auth.build_msal_app") as mock_build_msal_app:
            user = factories.user.create(email="test.member@communities.gov.uk", azure_ad_subject_id="wer234")
            grant = factories.grant.create()
            factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN])
            factories.user_role.create(user=user, permissions=[RoleEnum.MEMBER], grant=grant)
            assert db_session.scalar(select(func.count()).select_from(UserRole)) == 2

            mock_build_msal_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test.member@communities.gov.uk",
                    "name": "SSO User",
                    "roles": [],
                    "sub": "wer234",
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=True)
            updated_user = db_session.scalar(select(User).where(User.azure_ad_subject_id == "wer234"))

            assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1
            assert AuthorisationHelper.is_deliver_grant_member(grant_id=grant.id, user=updated_user) is True
            assert AuthorisationHelper.is_platform_admin(updated_user) is False

        assert response.status_code == 200

    def test_platform_admin_remove_all_other_roles(self, anonymous_client, factories, db_session):
        with patch("app.common.auth.build_msal_app") as mock_build_msal_app:
            user = factories.user.create(email="test.member@communities.gov.uk", azure_ad_subject_id="wer234")
            factories.user_role.create(user=user, permissions=[RoleEnum.ADMIN])
            grants = factories.grant.create_batch(2)
            for grant in grants:
                factories.user_role.create(user=user, permissions=[RoleEnum.MEMBER], grant=grant)
            assert db_session.scalar(select(func.count()).select_from(UserRole)) == 3

            mock_build_msal_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test.member@communities.gov.uk",
                    "name": "SSO User",
                    "roles": ["FS_PLATFORM_ADMIN"],
                    "sub": "wer234",
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=True)
            updated_user = db_session.scalar(select(User).where(User.azure_ad_subject_id == "wer234"))
            assert AuthorisationHelper.is_platform_admin(updated_user) is True
            assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1

        assert response.status_code == 200

    def test_platform_admin_signin_claims_pending_invitations(self, anonymous_client, factories, db_session):
        grants = factories.grant.create_batch(3)
        for grant in grants:
            factories.invitation.create(
                email="test@communities.gov.uk",
                organisation=grant.organisation,
                grant=grant,
                permissions=[RoleEnum.MEMBER],
            )
        assert db_session.scalar(select(func.count()).select_from(Invitation)) == 3

        with patch("app.common.auth.build_msal_app") as mock_build_msal_app:
            mock_build_msal_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test@communities.gov.uk",
                    "name": "SSO User",
                    "roles": ["FS_PLATFORM_ADMIN"],
                    "sub": "wer234",
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=True)

        assert response.status_code == 200
        user = db_session.scalar(select(User).where(User.azure_ad_subject_id == "wer234"))
        assert AuthorisationHelper.is_platform_admin(user) is True
        assert db_session.scalar(select(func.count()).select_from(UserRole)) == 1
        usable_invites_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
        assert not usable_invites_from_db

    def test_grant_member_with_valid_invites_first_login(self, anonymous_client, factories, db_session):
        with patch("app.common.auth.build_msal_app") as mock_build_msal_app:
            user = interfaces.user.get_current_user()
            assert user.is_anonymous

            grants = factories.grant.create_batch(3)
            invitations = []

            for grant in grants:
                invitation = factories.invitation.create(
                    email="test@communities.gov.uk",
                    organisation=grant.organisation,
                    grant=grant,
                    permissions=[RoleEnum.MEMBER],
                )
                invitations.append(invitation)

            mock_build_msal_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test@communities.gov.uk",
                    "name": "SSO User",
                    "roles": [],
                    "sub": "abc123",
                }
            }
            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=True)
        assert response.status_code == 200

        assert len(user.roles) == 3

        usable_invites_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
        assert not usable_invites_from_db

    @pytest.mark.freeze_time("2025-10-01 12:00:00")
    def test_invalid_grant_team_member_invitations_redirects_to_permissions_error(
        self, anonymous_client, factories, db_session
    ):
        with patch("app.common.auth.build_msal_app") as mock_build_msal_app:
            grants = factories.grant.create_batch(2)
            # Create an expired invitation
            factories.invitation.create(
                email="test@communities.gov.uk",
                organisation=grants[-1].organisation,
                grant=grants[-1],
                permissions=[RoleEnum.MEMBER],
                expires_at_utc=datetime.datetime(2025, 9, 1, 12, 0, 0),
            )

            mock_build_msal_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test@communities.gov.uk",
                    "name": "SSO User",
                    "roles": [],
                    "sub": "abc123",
                }
            }
            usable_invites_from_db = db_session.scalars(select(Invitation).where(Invitation.is_usable.is_(True))).all()
            assert not usable_invites_from_db
            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=False)

        assert response.status_code == 302
        assert response.location == url_for("auth.signed_in_but_no_permissions", invite_expired=True)

    def test_response_when_build_msal_app_returns_token_used_error(self, anonymous_client, factories, db_session):
        with patch("app.common.auth.build_msal_app") as mock_build_msal_app:
            mock_build_msal_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "error": "invalid_grant",
                "error_codes": [54005],
            }
            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=False)
            assert response.status_code == 302
            assert response.location == url_for("auth.sign_out")

    def test_response_when_build_msal_app_returns_other_error(self, anonymous_client, factories, db_session):
        with patch("app.common.auth.build_msal_app") as mock_build_msal_app:
            mock_build_msal_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "error": "bad_error",
                "error_codes": [12345],
            }
            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=False)
            assert response.status_code == 500
            assert "Azure AD get-token flow failed with: {'error': 'bad_error', 'error_codes': [12345]}"


class TestAuthenticatedUserRedirect:
    def test_magic_link_get(self, authenticated_no_role_client):
        response = authenticated_no_role_client.get(url_for("auth.request_a_link_to_sign_in"))
        assert response.status_code == 302

    def test_sso_get(self, authenticated_no_role_client):
        response = authenticated_no_role_client.get(url_for("auth.sso_sign_in"))
        assert response.status_code == 302
