import ipaddress
from typing import Any
from urllib.parse import urlsplit

from tests.smoke.conftest import CLIENT_PATH, SmokeEnvironment, SmokeGet

# Globally routable because the endpoint masks non-public addresses, so a documentation-range spoof could never leak.
SPOOFED_ADDRESS = "1.2.3.4"
SPOOFED_HOST = "spoofed.example.com"


def _client_view(smoke_get: SmokeGet, headers: dict[str, str]) -> dict[str, Any]:
    response = smoke_get(CLIENT_PATH, headers)
    assert response.status_code == 200, response.text
    return response.json()


def test_plain_request_uses_the_public_scheme_and_canonical_host(
    baseline: dict[str, Any], smoke_env: SmokeEnvironment
) -> None:
    assert baseline["scheme"] == urlsplit(smoke_env.base_url).scheme
    assert baseline["host_is_canonical"] is True


def test_plain_request_arrives_with_the_forwarded_for_entries_the_config_expects(baseline: dict[str, Any]) -> None:
    assert baseline["forwarded_for_matches_config"] is True


def test_plain_request_resolves_the_callers_public_address(
    baseline: dict[str, Any], smoke_env: SmokeEnvironment
) -> None:
    if smoke_env.caller_is_public:
        assert ipaddress.ip_address(baseline["remote_addr"]).is_global
    else:
        assert baseline["remote_addr"] == "non-public"


def test_spoofed_forwarded_for_never_becomes_the_client(smoke_get: SmokeGet, baseline: dict[str, Any]) -> None:
    view = _client_view(smoke_get, {"X-Forwarded-For": SPOOFED_ADDRESS})

    assert view["remote_addr"] == baseline["remote_addr"]
    assert view["remote_addr"] != SPOOFED_ADDRESS
    assert view["forwarded_for_matches_config"] is False


def test_spoofed_forwarded_proto_is_ignored(
    smoke_get: SmokeGet, baseline: dict[str, Any], smoke_env: SmokeEnvironment
) -> None:
    spoofed_scheme = "http" if urlsplit(smoke_env.base_url).scheme == "https" else "https"

    view = _client_view(smoke_get, {"X-Forwarded-Proto": spoofed_scheme})

    assert view["scheme"] == baseline["scheme"]
    assert view["host_is_canonical"] is True


def test_spoofed_forwarded_host_is_ignored(smoke_get: SmokeGet, baseline: dict[str, Any]) -> None:
    view = _client_view(smoke_get, {"X-Forwarded-Host": SPOOFED_HOST})

    assert view["host_is_canonical"] is True
    assert view["scheme"] == baseline["scheme"]
    assert view["remote_addr"] == baseline["remote_addr"]


def test_spoofed_forwarded_header_is_ignored(smoke_get: SmokeGet, baseline: dict[str, Any]) -> None:
    view = _client_view(smoke_get, {"Forwarded": f"for={SPOOFED_ADDRESS};proto=http;host={SPOOFED_HOST}"})

    assert view["remote_addr"] == baseline["remote_addr"]
    assert view["scheme"] == baseline["scheme"]
    assert view["host_is_canonical"] is True
