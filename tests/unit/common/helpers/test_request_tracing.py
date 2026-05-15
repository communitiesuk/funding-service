from app.common.data.types import TraceLevelEnum
from app.common.helpers.request_tracing import (
    REQUEST_TRACING_COOKIE_NAME,
    REQUEST_TRACING_TTL,
    decode_levels,
    encode_levels,
    get_tracing_levels_from_environ,
)


class TestEncodeAndDecodeLevels:
    def test_round_trip_single_level(self):
        token = encode_levels([TraceLevelEnum.TRACE], "secret")
        assert decode_levels(token, "secret") == [TraceLevelEnum.TRACE]

    def test_empty_round_trips_to_empty_list(self):
        token = encode_levels([], "secret")
        assert decode_levels(token, "secret") == []

    def test_wrong_secret_returns_empty_list(self):
        token = encode_levels([TraceLevelEnum.TRACE], "secret")
        assert decode_levels(token, "different-secret") == []

    def test_tampered_token_returns_empty_list(self):
        token = encode_levels([TraceLevelEnum.TRACE], "secret")
        tampered = token[:-1] + ("a" if token[-1] != "a" else "b")
        assert decode_levels(tampered, "secret") == []

    def test_malformed_token_returns_empty_list(self):
        assert decode_levels("not-a-real-token", "secret") == []

    def test_expired_token_returns_empty_list(self, monkeypatch):
        import itsdangerous.timed as itsdangerous_timed

        signing_time = 1_735_732_800  # Jan 1 2025 noon
        monkeypatch.setattr(itsdangerous_timed.time, "time", lambda: signing_time)
        token = encode_levels([TraceLevelEnum.TRACE], "secret")

        monkeypatch.setattr(itsdangerous_timed.time, "time", lambda: signing_time + REQUEST_TRACING_TTL + 1)
        assert decode_levels(token, "secret") == []

    def test_token_just_inside_ttl_still_valid(self, monkeypatch):
        import itsdangerous.timed as itsdangerous_timed

        signing_time = 1_735_732_800  # Jan 1 2025 noon
        monkeypatch.setattr(itsdangerous_timed.time, "time", lambda: signing_time)
        token = encode_levels([TraceLevelEnum.TRACE], "secret")

        monkeypatch.setattr(itsdangerous_timed.time, "time", lambda: signing_time + REQUEST_TRACING_TTL - 1)
        assert decode_levels(token, "secret") == [TraceLevelEnum.TRACE]


class TestGetTracingLevelsFromEnviron:
    def test_returns_empty_list_when_no_cookie_header(self):
        assert get_tracing_levels_from_environ({}, "secret") == []

    def test_returns_empty_list_when_tracing_cookie_missing(self):
        environ = {"HTTP_COOKIE": "session=abc; other=xyz"}
        assert get_tracing_levels_from_environ(environ, "secret") == []

    def test_extracts_levels_from_cookie_header(self):
        token = encode_levels([TraceLevelEnum.TRACE, TraceLevelEnum.PROFILE], "secret")
        environ = {"HTTP_COOKIE": f"session=abc; {REQUEST_TRACING_COOKIE_NAME}={token}; other=xyz"}
        assert get_tracing_levels_from_environ(environ, "secret") == [TraceLevelEnum.TRACE, TraceLevelEnum.PROFILE]

    def test_wrong_secret_returns_empty_list(self):
        token = encode_levels([TraceLevelEnum.TRACE], "secret")
        environ = {"HTTP_COOKIE": f"{REQUEST_TRACING_COOKIE_NAME}={token}"}
        assert get_tracing_levels_from_environ(environ, "different-secret") == []
