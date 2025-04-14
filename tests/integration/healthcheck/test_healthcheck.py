def test_healthcheck(anonymous_client) -> None:
    response = anonymous_client.get("/healthcheck")
    assert response.status_code == 200
    assert "OK" in response.get_data(as_text=True)
