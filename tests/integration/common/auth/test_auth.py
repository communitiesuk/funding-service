import datetime
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from flask import url_for
from sqlalchemy import select

from app.common.data import interfaces
from app.common.data.models import MagicLink
from app.common.data.models_user import User
from app.common.data.types import RoleEnum
from tests.utils import AnyStringMatching, page_has_error


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

    def test_post_valid_email(self, anonymous_client, mock_notification_service_calls):
        response = anonymous_client.post(
            url_for("auth.request_a_link_to_sign_in"),
            data={"email_address": "test@communities.gov.uk"},
            follow_redirects=True,
        )
        assert response.status_code == 200
        assert b"Check your email" in response.data
        assert b"test@communities.gov.uk" in response.data
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
            data={"email_address": "test@test.communities.gov.uk"},
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
        magic_link = factories.magic_link.create(user__email="test@communities.gov.uk")
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
        assert response.location == url_for("auth.request_a_link_to_sign_in")

    def test_redirect_on_used_magic_link(self, anonymous_client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk",
            redirect_to_path="/my-redirect",
            claimed_at_utc=datetime.datetime.now() - datetime.timedelta(hours=1),
        )

        response = anonymous_client.get(url_for("auth.claim_magic_link", magic_link_code=magic_link.code))
        assert response.status_code == 302
        assert response.location == url_for("auth.request_a_link_to_sign_in")

    def test_redirect_on_expired_magic_link(self, anonymous_client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk",
            redirect_to_path="/my-redirect",
            expires_at_utc=datetime.datetime.now() - datetime.timedelta(hours=1),
        )

        response = anonymous_client.get(url_for("auth.claim_magic_link", magic_link_code=magic_link.code))
        assert response.status_code == 302
        assert response.location == url_for("auth.request_a_link_to_sign_in")

    @pytest.mark.parametrize(
        "redirect_to, safe_redirect_to",
        (
            ("/blah/blah", "/blah/blah"),
            ("https://bad.place/blah", "/"),  # Single test case; see TestSanitiseRedirectURL for more exhaustion
        ),
    )
    def test_post_claims_link_and_redirects(self, anonymous_client, factories, redirect_to, safe_redirect_to):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk", redirect_to_path=redirect_to, claimed_at_utc=None
        )
        user = interfaces.user.get_current_user()

        assert user.is_authenticated is False

        response = anonymous_client.post(
            url_for("auth.claim_magic_link", magic_link_code=magic_link.code),
            json={"submit": "yes"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == safe_redirect_to
        assert magic_link.claimed_at_utc is not None
        assert user.is_authenticated is True
        assert magic_link.user.id == user.id


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
    def test_get_without_fsd_admin_role(self, app, anonymous_client):
        with patch("app.common.auth.build_msal_app") as mock_build_msap_app:
            # Partially mock the expected return value; just enough for the test.
            mock_build_msap_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test@test.communities.gov.uk",
                    "name": "SSO User",
                    "roles": [],
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"))

        assert response.status_code == 403
        assert "https://mhclgdigital.atlassian.net/servicedesk/customer/portal/5" in response.text

    def test_get_without_fsd_admin_role_and_with_grant_member_role(self, anonymous_client, factories):
        with patch("app.common.auth.build_msal_app") as mock_build_msap_app:
            user = factories.user.create(email="test.member@communities.gov.uk")
            grant = factories.grant.create()
            factories.user_role.create(user_id=user.id, user=user, role=RoleEnum.MEMBER, grant=grant)
            # Partially mock the expected return value; just enough for the test.
            mock_build_msap_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test.member@communities.gov.uk",
                    "name": "SSO User",
                    "roles": [],
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=True)

            assert not interfaces.user.get_current_user().is_platform_admin

        assert response.status_code == 200

    def test_get_without_fsd_admin_role_and_with_no_roles(self, anonymous_client):
        with patch("app.common.auth.build_msal_app") as mock_build_msap_app:
            # Partially mock the expected return value; just enough for the test.
            mock_build_msap_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test.member.nodb@communities.gov.uk",
                    "name": "SSO User",
                    "roles": [],
                }
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"), follow_redirects=True)

        assert response.status_code == 403

    def test_get_without_any_roles_should_403(self, app, anonymous_client):
        with patch("app.common.auth.build_msal_app") as mock_build_msap_app:
            # Partially mock the expected return value; just enough for the test.
            mock_build_msap_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {"preferred_username": "test@test.communities.gov.uk", "name": "SSO User"}
            }

            response = anonymous_client.get(url_for("auth.sso_get_token"))

        assert response.status_code == 403
        assert "https://mhclgdigital.atlassian.net/servicedesk/customer/portal/5" in response.text

    def test_get_valid_token_with_redirect(self, anonymous_client, factories, db_session):
        dummy_grant = factories.grant.create()
        with anonymous_client.session_transaction() as session:
            session["next"] = f"grants/{dummy_grant.id}"

        with patch("app.common.auth.build_msal_app") as mock_build_msap_app:
            # Partially mock the expected return value; just enough for the test.
            mock_build_msap_app.return_value.acquire_token_by_auth_code_flow.return_value = {
                "id_token_claims": {
                    "preferred_username": "test@test.communities.gov.uk",
                    "name": "SSO User",
                    "roles": ["FSD_ADMIN"],
                }
            }
            response = anonymous_client.get(
                url_for("auth.sso_get_token"),
                follow_redirects=True,
            )
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert dummy_grant.name in soup.h1.text

        with anonymous_client.session_transaction() as session:
            assert "next" not in session

        new_user = db_session.scalar(select(User).where(User.email == "test@test.communities.gov.uk"))
        assert new_user.name == "SSO User"


class TestAuthenticatedUserRedirect:
    def test_magic_link_get(self, authenticated_client):
        response = authenticated_client.get(url_for("auth.request_a_link_to_sign_in"))
        assert response.status_code == 302

    def test_sso_get(self, authenticated_client):
        response = authenticated_client.get(url_for("auth.sso_sign_in"))
        assert response.status_code == 302
