from collections.abc import Generator

import pytest
from redis import Redis
from redis.exceptions import ConnectionError
from testcontainers.core.container import DockerContainer
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

REDIS_IMAGE = "redis:8.8.4-alpine@sha256:ab669f1420eaa05360a417b24f3bd210c9272e2c79a4bb35d3e50b4bfd50dbee"


@pytest.fixture(scope="session")
def redis_container_client() -> Generator[Redis]:
    container = (
        DockerContainer(REDIS_IMAGE)
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


def test_healthcheck_without_redis_configuration(app, anonymous_client) -> None:
    assert app.extensions["redis"] is None

    response = anonymous_client.get("/healthcheck")
    assert response.status_code == 200
    assert response.get_data(as_text=True) == "OK"


def test_healthcheck_with_redis(app, anonymous_client, mocker) -> None:
    redis_client = mocker.Mock()
    redis_client.ping.return_value = True
    mocker.patch.dict(app.extensions, {"redis": redis_client})

    response = anonymous_client.get("/healthcheck")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "OK"
    redis_client.ping.assert_called_once_with()


def test_healthcheck_with_real_redis(app, anonymous_client, mocker, redis_container_client) -> None:
    mocker.patch.dict(app.extensions, {"redis": redis_container_client})

    response = anonymous_client.get("/healthcheck")

    assert response.status_code == 200
    assert response.get_data(as_text=True) == "OK"


def test_healthcheck_returns_error_when_redis_is_unavailable(app, anonymous_client, mocker, caplog) -> None:
    redis_client = mocker.Mock()
    redis_client.ping.side_effect = ConnectionError("connection unavailable")
    mocker.patch.dict(app.extensions, {"redis": redis_client})

    with caplog.at_level("ERROR", logger=app.logger.name):
        response = anonymous_client.get("/healthcheck")

    assert response.status_code == 500
    assert response.get_data(as_text=True) == "ERROR"
    assert "connection unavailable" not in response.get_data(as_text=True)
    assert any("Redis healthcheck error" in message for message in caplog.messages)


def test_db_healthcheck_current_revision(anonymous_client) -> None:
    response = anonymous_client.get("/healthcheck/db")
    assert response.status_code == 200
    assert response.content_type == "text/plain"

    # Get version and verify format (NNN_description)
    version = response.get_data(as_text=True)
    assert version.split("_")[0].isdigit()


def test_db_healthcheck_current_revision_logs_unexpected_exception(app, anonymous_client, mocker, caplog):
    engine = app.extensions["sqlalchemy"].engine
    mocker.patch.object(engine, "connect", side_effect=ValueError("unexpected!"))

    with caplog.at_level("ERROR", logger=app.logger.name):
        response = anonymous_client.get("/healthcheck/db")

    assert response.status_code == 500
    assert response.content_type == "text/plain"

    error_text = response.get_data(as_text=True)
    assert error_text == ("ERROR")
    # Assert the error message and exception are in the logs
    assert any("Database healthcheck error" in m for m in caplog.messages)
    assert any("unexpected!" in r for r in caplog.text.splitlines())
