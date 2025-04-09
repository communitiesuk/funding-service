import datetime

from bs4 import BeautifulSoup
from flask import url_for

from tests.utils import AnyStringMatching, page_has_error


def test_sign_in_page_get(client):
    response = client.get(url_for("auth.sign_in"))
    assert response.status_code == 200
    assert b"Request a link to sign in" in response.data


def test_sign_in_page_post_invalid_email(client):
    response = client.post(url_for("auth.sign_in"), data={"email_address": "invalid-email"})
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert page_has_error(soup, "Enter an email address in the correct format")


def test_sign_in_page_post_non_communities_email(client):
    response = client.post(url_for("auth.sign_in"), data={"email_address": "test@example.com"})
    assert response.status_code == 200
    soup = BeautifulSoup(response.data, "html.parser")
    assert page_has_error(soup, "Email address must end with @communities.gov.uk")


def test_sign_in_page_post_valid_email(client, mock_notification_service_calls):
    response = client.post(
        url_for("auth.sign_in"),
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
        == "http://funding.communities.gov.localhost:8080/sign-in"
    )


def test_check_email_page(client, factories):
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
        assert response.location == url_for("auth.sign_in")

    def test_redirect_on_used_magic_link(self, client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk",
            redirect_to_path="/my-redirect",
            claimed_at_utc=datetime.datetime.now() - datetime.timedelta(hours=1),
        )

        response = client.get(url_for("auth.claim_magic_link", magic_link_code=magic_link.code))
        assert response.status_code == 302
        assert response.location == url_for("auth.sign_in")

    def test_redirect_on_expired_magic_link(self, client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk",
            redirect_to_path="/my-redirect",
            expires_at_utc=datetime.datetime.now() - datetime.timedelta(hours=1),
        )

        response = client.get(url_for("auth.claim_magic_link", magic_link_code=magic_link.code))
        assert response.status_code == 302
        assert response.location == url_for("auth.sign_in")

    def test_post_claims_link_and_redirects(self, client, factories):
        magic_link = factories.magic_link.create(
            user__email="test@communities.gov.uk", redirect_to_path="/my-redirect", claimed_at_utc=None
        )

        response = client.post(
            url_for("auth.claim_magic_link", magic_link_code=magic_link.code),
            json={"submit": "yes"},
            follow_redirects=False,
        )

        assert response.status_code == 302
        assert response.location == "/my-redirect"
        assert magic_link.claimed_at_utc is not None
