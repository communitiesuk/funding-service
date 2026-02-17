import io
from unittest.mock import MagicMock

from app.services.s3 import S3Service


class TestS3Service:
    def test_init_app_registers_extension(self, app):
        assert "s3_service" in app.extensions
        assert "s3_service.client" in app.extensions

    def test_bucket_name_from_config(self, app):
        assert app.extensions["s3_service"].bucket_name == app.config["AWS_BUCKET_NAME"]

    def test_upload_file(self, app):
        s3: S3Service = app.extensions["s3_service"]
        mock_client = MagicMock()
        original_client = app.extensions["s3_service.client"]
        app.extensions["s3_service.client"] = mock_client

        try:
            file = io.BytesIO(b"test content")
            s3.upload_file(file, "test/key.pdf")

            mock_client.upload_fileobj.assert_called_once_with(file, app.config["AWS_BUCKET_NAME"], "test/key.pdf")
        finally:
            app.extensions["s3_service.client"] = original_client

    def test_delete_file(self, app):
        s3: S3Service = app.extensions["s3_service"]
        mock_client = MagicMock()
        original_client = app.extensions["s3_service.client"]
        app.extensions["s3_service.client"] = mock_client

        try:
            s3.delete_file("test/key.pdf")

            mock_client.delete_object.assert_called_once_with(Bucket=app.config["AWS_BUCKET_NAME"], Key="test/key.pdf")
        finally:
            app.extensions["s3_service.client"] = original_client

    def test_download_file(self, app):
        s3: S3Service = app.extensions["s3_service"]
        mock_body = MagicMock()
        mock_body.read.return_value = b"file contents"
        mock_client = MagicMock()
        mock_client.get_object.return_value = {"Body": mock_body}

        original_client = app.extensions["s3_service.client"]
        app.extensions["s3_service.client"] = mock_client

        try:
            result = s3.download_file("test/key.pdf")

            assert result == b"file contents"
            mock_client.get_object.assert_called_once_with(Bucket=app.config["AWS_BUCKET_NAME"], Key="test/key.pdf")
        finally:
            app.extensions["s3_service.client"] = original_client
