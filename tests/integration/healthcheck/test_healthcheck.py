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
