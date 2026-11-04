from flask import Flask
from redis import Redis


class RedisExtension:
    client: Redis | None = None

    def init_app(self, app: Flask) -> None:
        cache_url = app.config["CACHE_URL"]
        self.client = (
            Redis.from_url(
                cache_url,
                socket_connect_timeout=app.config["REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS"],
                socket_timeout=app.config["REDIS_SOCKET_TIMEOUT_SECONDS"],
            )
            if cache_url
            else None
        )
        app.extensions["redis"] = self
