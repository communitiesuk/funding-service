import os
from typing import Generator
from unittest.mock import patch

import pytest
from flask import Flask, url_for
from flask_sqlalchemy_lite import SQLAlchemy
from testcontainers.postgres import PostgresContainer

from app import create_app
from tests.utils import build_db_config


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
    def test_app_404_on_unknown_url(self, app, client):
        response = client.get("/route/to/nowhere")
        assert response.status_code == 404
        assert "Page not found" in response.text
        assert app.config["SERVICE_DESK_URL"] in response.text

    def test_app_404_on_sqlalchemy_not_found(self, app, client):
        response = client.get("/_testing/sqlalchemy-not-found")
        assert response.status_code == 404
        assert "Page not found" in response.text
        assert app.config["SERVICE_DESK_URL"] in response.text

    def test_app_500_on_internal_server_error(self, app, client):
        response = client.get("/_testing/500")
        assert response.status_code == 500
        assert "Sorry, there is a problem with the service" in response.text
        assert app.config["SERVICE_DESK_URL"] in response.text


class TestAppIndex:
    def test_get_app_index_redirects_to_access_grant_funding(self, anonymous_client):
        response = anonymous_client.get("/", follow_redirects=False)
        assert response.status_code == 302
        assert response.location == url_for("access_grant_funding.index")
