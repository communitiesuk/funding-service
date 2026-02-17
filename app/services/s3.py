from typing import IO, Any

import boto3
from flask import Flask, current_app


class S3Service:
    def __init__(self) -> None:
        self._client: Any = None

    def init_app(self, app: Flask) -> None:
        endpoint_url = app.config.get("AWS_ENDPOINT_OVERRIDE")

        client = boto3.client(
            "s3",
            region_name=app.config["AWS_REGION"],
            aws_access_key_id=app.config.get("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=app.config.get("AWS_SECRET_ACCESS_KEY"),
            endpoint_url=endpoint_url,
        )

        app.extensions["s3_service"] = self
        app.extensions["s3_service.client"] = client

    @property
    def client(self) -> Any:
        return current_app.extensions["s3_service.client"]

    @property
    def bucket_name(self) -> str:
        return str(current_app.config["AWS_BUCKET_NAME"])

    def upload_file(self, file: IO[bytes], key: str) -> None:
        """Upload a file-like object to S3.

        Args:
            file: A file-like object (e.g. werkzeug FileStorage) to upload.
            key: The S3 object key (path) to store the file under.
        """
        self.client.upload_fileobj(file, self.bucket_name, key)
        current_app.logger.info("Uploaded file to S3: %(key)s", dict(key=key))

    def delete_file(self, key: str) -> None:
        """Delete a file from S3.

        Args:
            key: The S3 object key to delete.
        """
        self.client.delete_object(Bucket=self.bucket_name, Key=key)
        current_app.logger.info("Deleted file from S3: %(key)s", dict(key=key))

    def download_file(self, key: str) -> bytes:
        """Download a file from S3 and return its contents.

        Args:
            key: The S3 object key to download.

        Returns:
            The file contents as bytes.
        """
        response = self.client.get_object(Bucket=self.bucket_name, Key=key)
        return response["Body"].read()
