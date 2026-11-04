from flask import Flask
from redis import Redis


class RedisExtension:
    def init_app(self, app: Flask) -> None:
        redis_url = app.config["REDIS_URL"]
        app.extensions["redis"] = (
            Redis.from_url(
                redis_url,
                socket_connect_timeout=app.config["REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS"],
                socket_timeout=app.config["REDIS_SOCKET_TIMEOUT_SECONDS"],
            )
            if redis_url
            else None
        )
