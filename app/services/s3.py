import boto3
from flask import Flask
from werkzeug.datastructures import FileStorage

from app.common.collections.types import FileUploadAnswer


class S3Service:
    def init_app(self, app: Flask) -> None:
        self._app = app
        # https://docs.aws.amazon.com/boto3/latest/guide/credentials.html
        self._resource = boto3.resource("s3")
        self._bucket = self._resource.Bucket(app.config["AWS_S3_BUCKET_NAME"])
        app.extensions["s3_service"] = self

    @property
    def bucket_name(self) -> str:
        return str(self._app.config["AWS_S3_BUCKET_NAME"])

    def upload_file(self, file: FileStorage, key: str) -> None:
        self._bucket.upload_fileobj(Fileobj=file.stream, Key=key)

    def download_file(self, key: str) -> bytes:
        # prefer using `generate_and_give_access_to_url` instead of this method, at the time of writing
        # there is a signature conflict generating URLs which we should further investigate when there's time
        return self._bucket.Object(key).get()["Body"].read()

    def generate_and_give_access_to_url(self, answer: FileUploadAnswer) -> str:
        raise NotImplementedError("Signed URLs failing on signature mismatch")

    def delete_file(self, key: str) -> None:
        self._bucket.delete_objects(Delete={"Objects": [{"Key": key}]})

    def delete_prefix(self, prefix: str) -> None:
        self._bucket.objects.filter(Prefix=prefix).delete()
