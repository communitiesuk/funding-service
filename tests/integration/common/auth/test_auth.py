import datetime

from bs4 import BeautifulSoup
from flask import url_for
from flask_login import current_user

from tests.utils import AnyStringMatching, page_has_error


class TestSignInView:
    def test_get(self, client):
        response = client.get(url_for("auth.request_a_link_to_sign_in"))
        assert response.status_code == 200
        assert b"Request a link to sign in" in response.data

    def test_post_invalid_email(self, client):
        response = client.post(url_for("auth.request_a_link_to_sign_in"), data={"email_address": "invalid-email"})
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Enter an email address in the correct format")

    def get_test_post_non_communities_email(self, client):
        response = client.post(url_for("auth.request_a_link_to_sign_in"), data={"email_address": "test@example.com"})
        assert response.status_code == 200
        soup = BeautifulSoup(response.data, "html.parser")
        assert page_has_error(soup, "Email address must end with @communities.gov.uk")

    def test_post_valid_email(self, client, mock_notification_service_calls):
        response = client.post(
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


class TestCheckEmailPage:
    def test_get(self, client, factories):
        magic_link = factories.magic_link.create(user__email="test@communities.gov.uk")
        response = client.get(url_for("auth.check_email", magic_link_id=magic_link.id))
        assert response.status_code == 200
        assert b"Check your email" in response.data
        assert b"test@communities.gov.uk" in response.data


class TestClaimMagicLinkView:
    def test_get(self, client, factories):
        magic_link = factories.magic_link.create()

        response = client.get(url_for("auth.claim_magic_link", magic_link_code=magic_link.code))
        assert response.status_code == 200
        assert b"Sign in" in response.data

    def test_redirect_on_unknown_magic_link(self, client):
        response = client.get(url_for("auth.claim_magic_link", magic_link_code="unknown-code"))
        assert response.status_code == 302
        assert response.location == url_for("auth.request_a_link_to_sign_in")

    def test_redirect_on_used_magic_link(self, client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk",
            redirect_to_path="/my-redirect",
            claimed_at_utc=datetime.datetime.now() - datetime.timedelta(hours=1),
        )

        response = client.get(url_for("auth.claim_magic_link", magic_link_code=magic_link.code))
        assert response.status_code == 302
        assert response.location == url_for("auth.request_a_link_to_sign_in")

    def test_redirect_on_expired_magic_link(self, client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk",
            redirect_to_path="/my-redirect",
            expires_at_utc=datetime.datetime.now() - datetime.timedelta(hours=1),
        )

        response = client.get(url_for("auth.claim_magic_link", magic_link_code=magic_link.code))
        assert response.status_code == 302
        assert response.location == url_for("auth.request_a_link_to_sign_in")

    def test_post_claims_link_and_redirects(self, client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk", redirect_to_path="/my-redirect", claimed_at_utc=None
        )

        assert current_user.is_authenticated is False

        response = client.post(
            url_for("auth.claim_magic_link", magic_link_code=magic_link.code),
            json={"submit": "yes"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == "/my-redirect"
        assert magic_link.claimed_at_utc is not None
        assert current_user.is_authenticated is True
        assert magic_link.user.id == current_user.id


class TestSignOutView:
    def test_get(self, client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk", redirect_to_path="/my-redirect", claimed_at_utc=None
        )

        # A bit unencapsulated for testing the sign out view, but don't otherwise have an easy+reliable way to get
        # the user in the session
        client.post(url_for("auth.claim_magic_link", magic_link_code=magic_link.code), json={"submit": "yes"})
        with client.session_transaction() as session:
            assert "_user_id" in session

        response = client.get(url_for("auth.sign_out"), follow_redirects=True)
        assert response.status_code == 200

        with client.session_transaction() as session:
            assert "_user_id" not in session
