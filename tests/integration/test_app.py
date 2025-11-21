import os
from typing import Generator
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask_sqlalchemy_lite import SQLAlchemy
from testcontainers.postgres import PostgresContainer

from app import create_app
from tests.utils import build_db_config, get_link_hrefs, get_service_name_text


@pytest.fixture(scope="session")
def app_with_basic_auth(setup_db_container: PostgresContainer, db: SQLAlchemy) -> Generator[Flask, None, None]:
    with patch.dict(
        os.environ,
        {
            "BASIC_AUTH_ENABLED": "true",
            "BASIC_AUTH_USERNAME": "test",
            # pragma: allowlist nextline secret
            "BASIC_AUTH_PASSWORD": "password",
            **build_db_config(setup_db_container),
        },
    ):
        app = create_app()

    app.config.update({"TESTING": True})
    yield app


class TestBasicAuth:
    def test_basic_auth_disabled(self, app):
        with app.test_client() as client:
            response = client.get("/", follow_redirects=False)
            assert response.status_code == 302
            assert "WWW-Authenticate" not in response.headers

    def test_basic_auth_enabled_requires_username_and_password(self, db, setup_db_container):
        with patch.dict(
            os.environ,
            {
                "BASIC_AUTH_ENABLED": "true",
                **build_db_config(setup_db_container),
            },
        ):
            with pytest.raises(ValueError) as e:
                create_app()

            assert "BASIC_AUTH_USERNAME and BASIC_AUTH_PASSWORD must be set if BASIC_AUTH_ENABLED is true." in str(
                e.value
            )

    def test_basic_auth_enabled(self, app_with_basic_auth):
        with app_with_basic_auth.test_client() as client:
            response = client.get("/", follow_redirects=False)
            assert response.status_code == 401
            assert response.headers["WWW-Authenticate"] == "Basic"

    def test_basic_auth_enabled_allows_healthcheck(self, app_with_basic_auth):
        with app_with_basic_auth.test_client() as client:
            response = client.get(url_for("healthcheck.healthcheck"), follow_redirects=False)
            assert response.status_code == 200


class TestAppErrorHandlers:
    @pytest.mark.parametrize(
        "service_url, service_desk_url, service_name",
        [
            ("/access", "ACCESS_SERVICE_DESK_URL", "MHCLG Access grant funding"),
            ("/deliver", "DELIVER_SERVICE_DESK_URL", "MHCLG Funding Service"),
            ("", "SERVICE_DESK_URL", "MHCLG Funding Service"),
        ],
    )
    def test_app_404_on_unknown_url(self, app, client, service_url, service_desk_url, service_name):
        response = client.get(f"{service_url}/route/to/nowhere")
        assert response.status_code == 404

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Page not found" in soup.text
        assert app.config[service_desk_url] in get_link_hrefs(soup)
        assert service_name == get_service_name_text(soup)

    @pytest.mark.parametrize(
        "service_url, service_desk_url, service_name",
        [
            ("/access", "ACCESS_SERVICE_DESK_URL", "MHCLG Access grant funding"),
            ("/deliver", "DELIVER_SERVICE_DESK_URL", "MHCLG Funding Service"),
            ("", "SERVICE_DESK_URL", "MHCLG Funding Service"),
        ],
    )
    def test_app_404_on_sqlalchemy_not_found(self, app, client, service_url, service_desk_url, service_name):
        response = client.get(f"{service_url}/_testing/sqlalchemy-not-found")
        assert response.status_code == 404

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Page not found" in soup.text
        assert app.config[service_desk_url] in get_link_hrefs(soup)
        assert service_name == get_service_name_text(soup)

    @pytest.mark.parametrize(
        "service_url, service_desk_url, service_name",
        [
            ("/access", "ACCESS_SERVICE_DESK_URL", "MHCLG Access grant funding"),
            ("/deliver", "DELIVER_SERVICE_DESK_URL", "MHCLG Funding Service"),
            ("", "SERVICE_DESK_URL", "MHCLG Funding Service"),
        ],
    )
    def test_app_500_on_internal_server_error(self, app, client, service_url, service_desk_url, service_name):
        response = client.get(f"{service_url}/_testing/500")
        assert response.status_code == 500

        soup = BeautifulSoup(response.data, "html.parser")
        assert "Sorry, there is a problem with the service" in soup.text
        assert app.config[service_desk_url] in get_link_hrefs(soup)
        assert service_name == get_service_name_text(soup)

    @pytest.mark.parametrize(
        "service_url, service_desk_url, service_name",
        [
            ("/access", "ACCESS_SERVICE_DESK_URL", "MHCLG Access grant funding"),
            ("/deliver", "DELIVER_SERVICE_DESK_URL", "MHCLG Funding Service"),
            ("", "SERVICE_DESK_URL", "MHCLG Funding Service"),
        ],
    )
    def test_app_403_on_forbidden_url(self, app, client, service_url, service_desk_url, service_name):
        response = client.get(f"{service_url}/_testing/403")
        assert response.status_code == 403

        soup = BeautifulSoup(response.data, "html.parser")
        assert "You do not have permission to access this page" in soup.text
        assert app.config[service_desk_url] in get_link_hrefs(soup)
        assert service_name == get_service_name_text(soup)
