def test_healthcheck(client) -> None:
    response = client.get("/healthcheck")
    assert response.status_code == 200
    assert "OK" in response.get_data(as_text=True)
