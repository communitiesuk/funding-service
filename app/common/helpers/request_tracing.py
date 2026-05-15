from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http.cookies import SimpleCookie

from flask import current_app, request
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.common.data.types import TraceLevelEnum

REQUEST_TRACING_COOKIE_NAME = "request_tracing"
REQUEST_TRACING_TTL = 15 * 60  # Number of seconds that tracing gets enabled for


@dataclass(frozen=True)
class RequestTracingState:
    levels: list[TraceLevelEnum]
    expires_in: str


def _serializer(secret: str) -> URLSafeTimedSerializer:
    # The salt here is for namespacing, not for cryptographic security, so it can be a static public string.
    return URLSafeTimedSerializer(secret, salt="request-tracing")


def _parse_payload(payload: object) -> list[TraceLevelEnum]:
    if not isinstance(payload, str):
        return []

    levels: list[TraceLevelEnum] = []
    for raw in payload.split("\n"):
        raw = raw.strip()
        if not raw:
            continue
        try:
            levels.append(TraceLevelEnum(raw))
        except ValueError:
            continue
    return levels


def encode_levels(levels: list[TraceLevelEnum], secret: str) -> str:
    payload = "\n".join([level.value for level in levels])
    return _serializer(secret).dumps(payload)


def decode_levels(token: str, secret: str) -> list[TraceLevelEnum]:
    try:
        payload = _serializer(secret).loads(token, max_age=REQUEST_TRACING_TTL)
    except BadSignature, SignatureExpired:
        return []

    return _parse_payload(payload)


def _decode_with_expiry(token: str, secret: str) -> tuple[list[TraceLevelEnum], datetime] | None:
    try:
        payload, signed_at = _serializer(secret).loads(token, max_age=REQUEST_TRACING_TTL, return_timestamp=True)
    except BadSignature, SignatureExpired:
        return None

    levels = _parse_payload(payload)
    if not levels:
        return None
    return levels, signed_at + timedelta(seconds=REQUEST_TRACING_TTL)


def get_tracing_levels_from_environ(wsgi_environ: dict[str, str], secret: str) -> list[TraceLevelEnum]:
    cookie_header = wsgi_environ.get("HTTP_COOKIE")
    if not cookie_header:
        return []

    cookies: SimpleCookie = SimpleCookie()
    cookies.load(cookie_header)
    morsel = cookies.get(REQUEST_TRACING_COOKIE_NAME)
    if morsel is None:
        return []

    return decode_levels(morsel.value, secret)


def get_tracing_levels() -> list[TraceLevelEnum]:
    token = request.cookies.get(REQUEST_TRACING_COOKIE_NAME)
    if not token:
        return []
    return decode_levels(token, current_app.config["SECRET_KEY"])


def get_tracing_state() -> RequestTracingState | None:
    token = request.cookies.get(REQUEST_TRACING_COOKIE_NAME)
    if not token:
        return None
    decoded = _decode_with_expiry(token, current_app.config["SECRET_KEY"])
    if decoded is None:
        return None
    levels, expires_at = decoded

    seconds_remaining = max(int((expires_at - datetime.now(UTC)).total_seconds()), 0)
    minutes, seconds = divmod(seconds_remaining, 60)

    expires_in = f"{minutes}m {seconds:02d}s"

    return RequestTracingState(levels=levels, expires_in=expires_in)
