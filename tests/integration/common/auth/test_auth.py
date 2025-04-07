from bs4 import BeautifulSoup
from flask import url_for

from tests.utils import page_has_error


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
    with client.session_transaction() as sess:
        assert sess["email_address"] == "test@communities.gov.uk"


def test_check_email_page_with_session(client):
    with client.session_transaction() as sess:
        sess["email_address"] = "test@communities.gov.uk"

    response = client.get("/check-your-email")
    assert response.status_code == 200
    assert b"Check your email" in response.data
    assert b"test@communities.gov.uk" in response.data


def test_check_email_page_without_session(client):
    response = client.get("/check-your-email", follow_redirects=True)
    assert response.status_code == 200
    assert b"Request a link to sign in" in response.data
    assert url_for("auth.sign_in") in response.request.path
