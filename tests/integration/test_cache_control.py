import tempfile
from pathlib import Path

from flask import url_for

from tests.conftest import FundingServiceTestClient


class TestCacheControl:
    def test_healthcheck_cache_headers(self, anonymous_client: FundingServiceTestClient) -> None:
        response = anonymous_client.get("/healthcheck")
        assert response.status_code == 200

        assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, private, max-age=0"

    def test_redirect_cache_headers(self, anonymous_client: FundingServiceTestClient) -> None:
        response = anonymous_client.get("/", follow_redirects=False)
        assert response.status_code == 302

        assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, private, max-age=0"
        assert response.headers["Pragma"] == "no-cache"
        assert response.headers["Expires"] == "0"

    def test_404_page_cache_headers(self, anonymous_client: FundingServiceTestClient) -> None:
        response = anonymous_client.get("/nonexistent-page")
        assert response.status_code == 404

        assert response.headers["Cache-Control"] == "no-store, no-cache, must-revalidate, private, max-age=0"
        assert response.headers["Pragma"] == "no-cache"
        assert response.headers["Expires"] == "0"

    def test_static_file_cache_headers(self, anonymous_client: FundingServiceTestClient, monkeypatch) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            test_content = b"test file content"
            test_file_path = Path(tmpdir) / "test.txt"
            test_file_path.write_bytes(test_content)

            monkeypatch.setattr(anonymous_client.application, "static_folder", tmpdir)

            response = anonymous_client.get(url_for("static", filename="test.txt"))

            _ = response.get_data()
            response.close()

            assert response.headers["Cache-Control"] == "public, max-age=31536000"

    def test_custom_cache_control(self, anonymous_client: FundingServiceTestClient) -> None:
        response = anonymous_client.get("/custom-cache-control")
        assert response.status_code == 200
        assert response.headers["Cache-Control"] == "max-age=30"
