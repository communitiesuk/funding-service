from collections.abc import Generator
from pathlib import Path

import pytest
import yaml
from redis import Redis
from redis.exceptions import ConnectionError
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy


def _redis_image_from_compose() -> str:
    compose = yaml.safe_load((Path(__file__).resolve().parents[3] / "docker-compose.yml").read_text())
    return compose["services"]["redis"]["image"]


@pytest.fixture(scope="session")
def redis_container_client() -> Generator[Redis]:
    container = (
        DockerContainer(_redis_image_from_compose())
        .with_exposed_ports(6379)
        .waiting_for(LogMessageWaitStrategy("Ready to accept connections"))
    )
    container.start()

    client = Redis(
        host=container.get_container_host_ip(),
        port=int(container.get_exposed_port(6379)),
        socket_connect_timeout=1,
        socket_timeout=1,
    )
    yield client

    client.close()
    container.stop()


class TestHealthcheck:
    def test_healthcheck_without_redis_configuration(self, app, anonymous_client) -> None:
        assert app.extensions["redis"].client is None

        response = anonymous_client.get("/healthcheck")
        assert response.status_code == 200
        assert response.get_data(as_text=True) == "OK"

    def test_healthcheck_with_redis(self, app, anonymous_client, mocker) -> None:
        redis_client = mocker.Mock()
        redis_client.ping.return_value = True
        mocker.patch.object(app.extensions["redis"], "client", redis_client)

        response = anonymous_client.get("/healthcheck/db")

        assert response.status_code == 200
        assert response.json["redis"] == "OK"
        redis_client.ping.assert_called_once_with()

    def test_healthcheck_with_real_redis(self, app, anonymous_client, mocker, redis_container_client) -> None:
        mocker.patch.object(app.extensions["redis"], "client", redis_container_client)

        response = anonymous_client.get("/healthcheck/db")

        assert response.status_code == 200
        assert response.json["redis"] == "OK"

    def test_healthcheck_returns_error_when_redis_is_unavailable(self, app, anonymous_client, mocker, caplog) -> None:
        redis_client = mocker.Mock()
        redis_client.ping.side_effect = ConnectionError("connection unavailable")
        mocker.patch.object(app.extensions["redis"], "client", redis_client)

        response = anonymous_client.get("/healthcheck")
        assert response.status_code == 200
        assert response.get_data(as_text=True) == "OK"

        with caplog.at_level("ERROR", logger=app.logger.name):
            db_response = anonymous_client.get("/healthcheck/db")

        assert db_response.status_code == 200
        assert db_response.json["redis"] == "ERROR"
        assert "connection unavailable" not in db_response.get_data(as_text=True)
        assert any("Redis healthcheck error" in message for message in caplog.messages)

    def test_db_healthcheck_current_revision_without_redis(self, anonymous_client) -> None:
        response = anonymous_client.get("/healthcheck/db")
        assert response.status_code == 200
        assert response.json["redis"] == "NOT_CONFIGURED"

        version = response.json["db"]
        assert version.split("_")[0].isdigit()

    def test_db_healthcheck_current_revision_logs_unexpected_exception(self, app, anonymous_client, mocker, caplog):
        engine = app.extensions["sqlalchemy"].engine
        mocker.patch.object(engine, "connect", side_effect=ValueError("unexpected!"))

        with caplog.at_level("ERROR", logger=app.logger.name):
            response = anonymous_client.get("/healthcheck/db")

        assert response.status_code == 200
        assert response.json["db"] == "ERROR"

        # Assert the error message and exception are in the logs
        assert any("Database healthcheck error" in m for m in caplog.messages)
        assert any("unexpected!" in r for r in caplog.text.splitlines())
