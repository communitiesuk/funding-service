import os
from typing import Generator
from unittest.mock import patch

import pytest
from flask import Flask
from flask_sqlalchemy_lite import SQLAlchemy

from app import create_app


@pytest.fixture(scope="session")
def app_with_basic_auth(db: Generator[SQLAlchemy]) -> Generator[Flask, None, None]:
    with patch.dict(
        os.environ,
        # pragma: allowlist nextline secret
        {"BASIC_AUTH_ENABLED": "true", "BASIC_AUTH_USERNAME": "test", "BASIC_AUTH_PASSWORD": "password"},
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

    def test_basic_auth_enabled_requires_username_and_password(self, db):
        with patch.dict(os.environ, {"BASIC_AUTH_ENABLED": "true"}):
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
