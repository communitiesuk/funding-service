import logging
import os
from typing import Generator
from unittest.mock import patch

import pytest
from bs4 import BeautifulSoup
from flask import Flask, url_for
from flask_sqlalchemy_lite import SQLAlchemy
from testcontainers.community.postgres import PostgresContainer

from app import create_app
from tests.smoke.conftest import CLIENT_PATH
from tests.utils import build_db_config, get_link_hrefs, get_service_name_text, recording_sentry_scope


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


class TestSentryUserContext:
    def test_sentry_user_is_only_the_signed_in_users_id(self, authenticated_platform_admin_client) -> None:
        with recording_sentry_scope() as recorder:
            authenticated_platform_admin_client.get("/custom-cache-control")

        user_id = str(authenticated_platform_admin_client.user.id)
        assert recorder.users[-1] == {"id": user_id}


class TestClientHealthcheck:
    @pytest.mark.parametrize(
        "forwarded_for, expected_forwarded_for_matches_config",
        [
            (None, True),
            ("198.51.100.1", False),
            ("198.51.100.1, 198.51.100.2,198.51.100.3", False),
            (" , ", True),
        ],
    )
    def test_reports_whether_forwarded_for_matches_config(
        self, app, anonymous_client, forwarded_for, expected_forwarded_for_matches_config
    ):
        headers = {"X-Forwarded-For": forwarded_for} if forwarded_for is not None else {}

        response = anonymous_client.get(
            url_for("healthcheck.client_healthcheck"),
            headers=headers,
            environ_overrides={"REMOTE_ADDR": "1.2.3.4", "wsgi.url_scheme": "https"},
        )

        assert app.config["PROXY_FIX_FOR"] == 0
        assert response.status_code == 200
        assert response.json == {
            "remote_addr": "1.2.3.4",
            "scheme": "https",
            "host_is_canonical": True,
            "forwarded_for_matches_config": expected_forwarded_for_matches_config,
        }

    @pytest.mark.parametrize("forwarded_for", ["198.51.100.1, 198.51.100.2", " 198.51.100.1 , 198.51.100.2 "])
    def test_logs_a_warning_when_forwarded_for_does_not_match_config(
        self, app, anonymous_client, caplog, forwarded_for
    ):
        with caplog.at_level(logging.WARNING, logger=app.logger.name):
            anonymous_client.get(url_for("healthcheck.client_healthcheck"), headers={"X-Forwarded-For": forwarded_for})

        warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
        assert len(warnings) == 1
        assert "2 X-Forwarded-For entries (PROXY_FIX_FOR is 0)" in warnings[0].getMessage()
        assert f"SERVER_NAME is {app.config['SERVER_NAME']}" in warnings[0].getMessage()
        assert "198.51.100.1" not in warnings[0].getMessage()

    def test_logs_nothing_when_forwarded_for_matches_config(self, app, anonymous_client, caplog):
        with caplog.at_level(logging.WARNING, logger=app.logger.name):
            anonymous_client.get(url_for("healthcheck.client_healthcheck"))

        assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []

    def test_smoke_tests_target_this_route(self, app):
        assert url_for("healthcheck.client_healthcheck") == CLIENT_PATH

    @pytest.mark.parametrize(
        "remote_addr, expected_remote_addr",
        [
            ("1.2.3.4", "1.2.3.4"),
            ("2606:4700::1", "2606:4700::1"),
            ("10.0.0.5", "non-public"),
            ("172.16.0.1", "non-public"),
            ("127.0.0.1", "non-public"),
            ("100.64.0.1", "non-public"),
            ("203.0.113.9", "non-public"),
            ("fe80::1", "non-public"),
            ("not-an-ip-address", "non-public"),
        ],
    )
    def test_reports_only_public_remote_addresses(self, anonymous_client, remote_addr, expected_remote_addr):
        response = anonymous_client.get(
            url_for("healthcheck.client_healthcheck"), environ_overrides={"REMOTE_ADDR": remote_addr}
        )

        assert response.status_code == 200
        assert response.json["remote_addr"] == expected_remote_addr

    def test_is_not_cacheable(self, anonymous_client):
        response = anonymous_client.get(url_for("healthcheck.client_healthcheck"))

        assert response.headers["Cache-Control"] == "no-store"

    def test_is_exempt_from_basic_auth(self, app_with_basic_auth):
        with app_with_basic_auth.test_client() as client:
            client_response = client.get(url_for("healthcheck.client_healthcheck"), buffered=True)
            db_response = client.get(url_for("healthcheck.db_healthcheck_current_revision"), buffered=True)

        assert client_response.status_code == 200
        assert db_response.status_code == 401
