from typing import Any

from werkzeug.middleware.proxy_fix import ProxyFix

from app.sentry import IgnoreIncomingTraceHeaders


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


class TestIgnoreIncomingTraceHeaders:
    def test_trace_headers_are_removed_and_other_headers_kept(self):
        seen: dict[str, Any] = {}

        def wsgi_app(app_environ: Any, start_response: Any) -> list[bytes]:
            seen.update(app_environ)
            start_response("200 OK", [])
            return []

        environ = {
            "HTTP_SENTRY_TRACE": "0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-1",
            "HTTP_BAGGAGE": "sentry-trace_id=0af7651916cd43dd8448eb211c80319c",
            "HTTP_TRACEPARENT": "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01",
            "HTTP_TRACESTATE": "vendor=value",
            "HTTP_X_AMZN_TRACE_ID": "Root=1-5759e988-bd862e3fe1be46a994272793",
        }

        IgnoreIncomingTraceHeaders(wsgi_app)(environ, _start_response)

        assert seen == {"HTTP_X_AMZN_TRACE_ID": "Root=1-5759e988-bd862e3fe1be46a994272793"}
