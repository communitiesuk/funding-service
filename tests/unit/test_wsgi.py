from typing import Any

from werkzeug.middleware.proxy_fix import ProxyFix


def _start_response(status: str, headers: Any, exc_info: Any = None) -> Any:
    return None


class TestProxyFixForwardedFor:
    @staticmethod
    def _remote_addr_seen_by_app(environ: dict[str, Any]) -> str:
        seen: dict[str, Any] = {}

        def wsgi_app(app_environ: Any, start_response: Any) -> list[bytes]:
            seen.update(app_environ)
            start_response("200 OK", [])
            return []

        ProxyFix(wsgi_app, x_for=2)(environ, _start_response)
        return seen["REMOTE_ADDR"]

    def test_two_hops_select_the_client_address_as_cloudfront_saw_it(self):
        environ = {"REMOTE_ADDR": "192.0.2.4", "HTTP_X_FORWARDED_FOR": "198.51.100.2, 203.0.113.3"}

        assert self._remote_addr_seen_by_app(environ) == "198.51.100.2"

    def test_fewer_hops_than_configured_leave_remote_addr_unchanged(self):
        environ = {"REMOTE_ADDR": "192.0.2.4", "HTTP_X_FORWARDED_FOR": "203.0.113.3"}

        assert self._remote_addr_seen_by_app(environ) == "192.0.2.4"
