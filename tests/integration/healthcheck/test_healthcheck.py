from sqlalchemy.exc import OperationalError


def test_healthcheck(anonymous_client) -> None:
    response = anonymous_client.get("/healthcheck")
    assert response.status_code == 200
    assert "OK" in response.get_data(as_text=True)


def test_db_healthcheck_current_revision(anonymous_client) -> None:
    response = anonymous_client.get("/healthcheck/db")
    assert response.status_code == 200
    assert response.content_type == "text/plain"

    # Get version and verify format (NNN_description)
    version = response.get_data(as_text=True)
    assert version.split("_")[0].isdigit()


def test_db_healthcheck_current_revision_logs_unexpected_exception(app, anonymous_client, mocker):
    engine = app.extensions["sqlalchemy"].engine
    mocker.patch.object(engine, "connect", side_effect=ValueError("unexpected!"))
    logger_exception = mocker.patch.object(app.logger, "exception")

    response = anonymous_client.get("/healthcheck/db")
    assert response.status_code == 500
    assert response.content_type == "text/plain"

    error_text = response.get_data(as_text=True)
    assert error_text.startswith("ERROR")
    logger_exception.assert_called_once_with("Database healthcheck error")
    logged_args, logged_kwargs = logger_exception.call_args
    assert "unexpected!" in str(logged_args) or "unexpected!" in str(logged_kwargs)

    # Patch the connect method on the engine to raise OperationalError
    engine = app.extensions["sqlalchemy"].engine
    mocker.patch.object(engine, "connect", side_effect=OperationalError("statement", "params", "orig"))
    logger_exception = mocker.patch.object(app.logger, "exception")

    response = anonymous_client.get("/healthcheck/db")
    assert response.status_code == 500
    assert response.content_type == "text/plain"

    error_text = response.get_data(as_text=True)
    assert error_text.startswith("ERROR")
    logger_exception.assert_called_once_with("Database healthcheck error")
