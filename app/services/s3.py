from urllib.parse import urlencode

import boto3
from flask import Flask
from werkzeug.datastructures import FileStorage

from app.common.collections.types import FileUploadAnswer


class S3Service:
    def init_app(self, app: Flask) -> None:
        self._app = app
        # https://docs.aws.amazon.com/boto3/latest/guide/credentials.html
        self._resource = boto3.resource("s3")
        self._bucket_name = str(self._app.config["AWS_S3_BUCKET_NAME"])
        self._bucket = self._resource.Bucket(self._bucket_name)
        app.extensions["s3_service"] = self
        self._client = boto3.client("s3")

    def upload_file(self, file: FileStorage, key: str, tags: dict[str, str] | None = None) -> None:
        extra_args: dict[str, str] = {}
        if tags:
            extra_args["Tagging"] = urlencode(tags)
        self._bucket.upload_fileobj(Fileobj=file.stream, Key=key, ExtraArgs=extra_args if extra_args else None)

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

    def update_file_tags(self, key: str, tags: dict[str, str]) -> None:
        tag_set = [{"Key": k, "Value": v} for k, v in tags.items()]
        self._client.put_object_tagging(Bucket=self._bucket_name, Key=key, Tagging={"TagSet": tag_set})
