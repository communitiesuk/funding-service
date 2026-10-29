import contextvars
import json
import logging
import uuid
from collections.abc import Iterator
from contextlib import closing
from logging.config import DictConfigurator
from typing import Any

import pytest
import sentry_sdk
from pydantic import ValidationError

from app.config import UnitTestConfig
from app.logging import (
    CorrelationMiddleware,
    JSONFormatter,
    PlaintextFormatter,
    correlation,
    get_default_logging_config,
    parse_request_size,
)
from app.logging.correlation import ContextType, CorrelationContext, get_current_context, get_record_correlation
from app.logging.unlogged import UNLOGGED_PATHS
from tests.utils import build_db_config

ALB_ROOT = "1-5759e988-bd862e3fe1be46a994272793"


def _make_record(
    level: int = logging.INFO, msg: str = "test message", name: str = "app.tests", **extra: object
) -> logging.LogRecord:
    return logging.getLogger(name).makeRecord(name, level, __file__, 1, msg, None, None, extra=extra or None)


class TestParseAlbTraceId:
    @pytest.mark.parametrize(
        "header",
        [
            f"Root={ALB_ROOT}",
            f"Self=1-67891234-12456789abcdef012345678;Root={ALB_ROOT};Sampled=1",
            f"Root={ALB_ROOT};Parent=53995c3f42cd8ad8",
        ],
    )
    def test_extracts_root_segment(self, header):
        assert correlation.parse_alb_trace_id(header) == ALB_ROOT

    @pytest.mark.parametrize(
        "header",
        [
            None,
            "",
            "Root=not-a-trace-id",
            f"Root={ALB_ROOT}\nforged log line",
            f"Root={ALB_ROOT.upper()}",
            f"Self={ALB_ROOT}",
        ],
    )
    def test_rejects_anything_not_in_strict_format(self, header):
        assert correlation.parse_alb_trace_id(header) is None


class TestParseCloudfrontRequestId:
    def test_accepts_cloudfront_style_id(self):
        cf_id = "q5YRu6QDBnyZ3_rTFqUJyJr6HlbLWUqG0bnGLkEvTq-dg8PyQsKZ_w=="
        assert correlation.parse_cloudfront_request_id(cf_id) == cf_id

    @pytest.mark.parametrize("header", [None, "", "a" * 129, "abc def", "abc\ndef", 'abc"def'])
    def test_rejects_unsafe_values(self, header):
        assert correlation.parse_cloudfront_request_id(header) is None


class TestLogRecordCorrelation:
    def test_records_outside_a_unit_of_work_have_no_correlation_fields(self):
        assert get_record_correlation(_make_record()) == {}

    def test_unforked_sentry_scope_is_cleaned_up_on_exit(self):
        user_id = str(uuid.uuid4())
        context = CorrelationContext(context_type=ContextType.REQUEST, request_id=correlation.new_id(), user_id=user_id)

        with correlation._enter(context, fork_sentry_scope=False):
            scope_inside = sentry_sdk.get_isolation_scope()
            tags_inside = dict(scope_inside._tags)
            attributes_inside = dict(scope_inside._attributes)
            user_inside = scope_inside._user
        scope_after = sentry_sdk.get_isolation_scope()

        assert tags_inside["request_id"] == attributes_inside["request_id"] == context.request_id
        assert tags_inside["user_id"] == attributes_inside["user_id"] == user_id
        assert user_inside == {"id": user_id}
        assert "request_id" not in scope_after._tags
        assert "request_id" not in scope_after._attributes
        assert "user_id" not in scope_after._tags
        assert "user_id" not in scope_after._attributes
        assert scope_after._user is None

    def test_request_context_binds_method_and_path_from_the_environ(self):
        with correlation.request_context(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/test-path"},
            alb_trace_id=None,
            cloudfront_request_id=None,
            debug_logging=False,
        ) as context:
            assert context.method == "GET"
            assert context.path == "/test-path"


class TestFormatters:
    def test_json_formatter_emits_flat_correlation_fields(self):
        with correlation.request_context(
            {"REQUEST_METHOD": "GET"}, alb_trace_id=ALB_ROOT, cloudfront_request_id=None, debug_logging=False
        ) as context:
            record = _make_record(status=200)

        output = json.loads(JSONFormatter().format(record))

        assert output["message"] == "test message"
        assert output["level"] == "INFO"
        assert output["logger"] == "app.tests"
        assert output["log_type"] == "application"
        assert output["status"] == 200
        assert output["context_type"] == "request"
        assert output["request_id"] == context.request_id
        assert output["alb_trace_id"] == ALB_ROOT
        assert output["method"] == "GET"
        assert output["timestamp"].endswith("+00:00")
        assert isinstance(output["thread"], str)
        assert "_correlation" not in output

    def test_json_formatter_correlation_fields_win_over_extra(self):
        with correlation.request_context(
            {"REQUEST_METHOD": "GET"}, alb_trace_id=None, cloudfront_request_id=None, debug_logging=False
        ) as context:
            record = _make_record(request_id="spoofed")

        output = json.loads(JSONFormatter().format(record))

        assert output["request_id"] == context.request_id

    @pytest.mark.parametrize("full_context", [False, True])
    def test_plaintext_formatter_without_context_is_unchanged(self, full_context):
        output = PlaintextFormatter("%(levelname)s - %(message)s", full_context=full_context).format(_make_record())

        assert output == "INFO - test message"

    def test_concise_plaintext_formatter_appends_only_a_short_request_tag(self):
        with correlation.request_context(
            {"REQUEST_METHOD": "GET"}, alb_trace_id=ALB_ROOT, cloudfront_request_id=None, debug_logging=False
        ) as context:
            record = _make_record()

        output = PlaintextFormatter("%(levelname)s - %(message)s").format(record)

        assert output == f"INFO - test message [{context.request_id[:8]}]"

    def test_full_plaintext_formatter_shows_every_correlation_field(self):
        with correlation.request_context(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/test-path"},
            alb_trace_id=ALB_ROOT,
            cloudfront_request_id=None,
            debug_logging=False,
        ) as context:
            record = _make_record()

        output = PlaintextFormatter("%(asctime)s %(levelname)s - %(message)s", full_context=True).format(record)

        assert "INFO - test message [context_type=request " in output
        assert f"request_id={context.request_id}" in output
        assert "method=GET" in output
        assert "path=/test-path" in output
        assert f"alb_trace_id={ALB_ROOT}" in output
        assert output.endswith("]")


class TestLogFormatterConfig:
    @pytest.fixture(autouse=True)
    def _database_environment(self, monkeypatch):
        for name, value in build_db_config(None).items():
            monkeypatch.setenv(name, value)

    def test_plaintext_full_is_accepted_by_the_config(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMATTER", "plaintext-full")

        assert UnitTestConfig().LOG_FORMATTER == "plaintext-full"

    def test_unknown_log_formatter_is_rejected_by_the_config(self, monkeypatch):
        monkeypatch.setenv("LOG_FORMATTER", "not-a-formatter")

        with pytest.raises(ValidationError, match="LOG_FORMATTER"):
            UnitTestConfig()

    @pytest.mark.parametrize("log_formatter, expected_full_context", [("plaintext", False), ("plaintext-full", True)])
    def test_plaintext_log_formatter_selects_the_matching_variant(
        self, app, monkeypatch, log_formatter, expected_full_context
    ):
        monkeypatch.setitem(app.config, "LOG_FORMATTER", log_formatter)
        log_config = get_default_logging_config(app)

        formatter_name = log_config["handlers"]["default"]["formatter"]
        formatter = DictConfigurator(log_config).configure_formatter(log_config["formatters"][formatter_name])

        assert isinstance(formatter, PlaintextFormatter)
        assert formatter.full_context is expected_full_context


class TestUnloggedPaths:
    def test_every_unlogged_path_is_a_real_route(self, app):
        url_adapter = app.url_map.bind("localhost")

        for path in UNLOGGED_PATHS:
            url_adapter.match(path)


class TestParseRequestSize:
    @pytest.mark.parametrize(
        "content_length, expected", [("123", 123), ("0", 0), (None, 0), ("", 0), ("not-a-number", 0), ("1.5", 0)]
    )
    def test_tolerates_missing_and_malformed_values(self, content_length, expected):
        assert parse_request_size(content_length) == expected


class _TestBody:
    def __init__(self, chunks: list[bytes], fail_after_chunks: bool = False) -> None:
        self.chunks = chunks
        self.fail_after_chunks = fail_after_chunks
        self.close_calls = 0

    def __iter__(self) -> Iterator[bytes]:
        yield from self.chunks
        if self.fail_after_chunks:
            raise RuntimeError("body generation failed")

    def close(self) -> None:
        self.close_calls += 1


def _start_response(status: str, headers: Any, exc_info: Any = None) -> Any:
    return None


class TestCorrelationMiddleware:
    def _middleware(self, app, body: _TestBody, headers: list[tuple[str, str]] | None = None, start: bool = True):
        def wsgi_app(environ: Any, start_response: Any) -> _TestBody:
            if start:
                start_response("200 OK", headers or [])
            return body

        return CorrelationMiddleware(app, wsgi_app)

    def _finish_records(self, caplog) -> list[logging.LogRecord]:
        return [record for record in caplog.records if record.getMessage().startswith("Request finished")]

    def _streaming_records(self, caplog) -> list[logging.LogRecord]:
        return [record for record in caplog.records if record.getMessage().startswith("Response streaming")]

    def _serve(self, middleware: CorrelationMiddleware, environ: dict[str, Any]) -> list[bytes]:
        with closing(middleware(environ, _start_response)) as response:
            return list(response)

    def test_unit_of_work_lasts_until_the_response_is_closed_and_close_is_idempotent(self, app, caplog):
        body = _TestBody([b"first", b"second"])
        middleware = self._middleware(app, body)

        response = middleware({"REQUEST_METHOD": "GET", "PATH_INFO": "/test-path"}, _start_response)
        context_while_streaming = get_current_context()
        chunks = list(response)
        finished_before_close = self._finish_records(caplog)
        response.close()
        response.close()

        finished = self._finish_records(caplog)
        assert context_while_streaming is not None
        assert chunks == [b"first", b"second"]
        assert finished_before_close == []
        assert len(finished) == 1
        assert get_record_correlation(finished[0])["request_id"] == context_while_streaming.request_id
        assert finished[0].response_size == len(b"firstsecond")
        assert finished[0].response_streamed is True
        assert body.close_calls == 1
        assert get_current_context() is None

    def test_response_with_content_length_is_not_streamed(self, app, caplog):
        caplog.set_level(logging.DEBUG, logger="app.request")
        middleware = self._middleware(app, _TestBody([b"body"]), headers=[("Content-Length", "4")])

        self._serve(middleware, {"REQUEST_METHOD": "GET", "PATH_INFO": "/test-path"})

        assert self._finish_records(caplog)[0].response_streamed is False
        assert self._streaming_records(caplog) == []

    def test_streamed_response_logs_streaming_line_before_finish_line(self, app, caplog):
        caplog.set_level(logging.DEBUG, logger="app.request")
        middleware = self._middleware(app, _TestBody([b"first", b"second"]))

        self._serve(middleware, {"REQUEST_METHOD": "GET", "PATH_INFO": "/test-path"})

        streaming = self._streaming_records(caplog)
        finished = self._finish_records(caplog)
        assert len(streaming) == 1
        assert len(finished) == 1
        assert streaming[0].getMessage() == "Response streaming GET /test-path 200"
        assert streaming[0].levelno == logging.DEBUG
        assert streaming[0].status == 200
        assert caplog.records.index(streaming[0]) < caplog.records.index(finished[0])
        assert get_record_correlation(streaming[0])["request_id"] == get_record_correlation(finished[0])["request_id"]

    def test_start_response_called_twice_logs_streaming_line_once(self, app, caplog):
        caplog.set_level(logging.DEBUG, logger="app.request")

        def wsgi_app(environ: Any, start_response: Any) -> _TestBody:
            start_response("200 OK", [])
            start_response("500 INTERNAL SERVER ERROR", [], (RuntimeError, RuntimeError("test error"), None))
            return _TestBody([b"error"])

        self._serve(CorrelationMiddleware(app, wsgi_app), {"REQUEST_METHOD": "GET", "PATH_INFO": "/test-path"})

        assert len(self._streaming_records(caplog)) == 1
        assert self._finish_records(caplog)[0].status == 500

    # TODO[FSPT-1805]: discussion TBD around logging User-Agent/IP and privacy policy re sending to Sentry
    # def test_finish_line_logs_remote_addr_as_client_ip(self, app, caplog):
    #     middleware = self._middleware(app, _TestBody([b"body"]))
    #
    #     self._serve(middleware, {"REQUEST_METHOD": "GET", "PATH_INFO": "/test-path", "REMOTE_ADDR": "198.51.100.2"})
    #
    #     assert self._finish_records(caplog)[0].client_ip == "198.51.100.2"

    def test_finish_line_omits_client_ip_that_is_not_an_address(self, app, caplog):
        middleware = self._middleware(app, _TestBody([b"body"]))

        self._serve(
            middleware,
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/test-path", "REMOTE_ADDR": "not-an-address, 203.0.113.9"},
        )

        assert not hasattr(self._finish_records(caplog)[0], "client_ip")

    def test_finish_line_omits_absent_client_ip(self, app, caplog):
        middleware = self._middleware(app, _TestBody([b"body"]))

        self._serve(middleware, {"REQUEST_METHOD": "GET", "PATH_INFO": "/test-path"})

        assert not hasattr(self._finish_records(caplog)[0], "client_ip")

    def test_body_failing_before_a_status_is_sent_is_logged_as_a_500(self, app, caplog):
        middleware = self._middleware(app, _TestBody([], fail_after_chunks=True), start=False)

        with closing(middleware({"REQUEST_METHOD": "GET", "PATH_INFO": "/test-path"}, _start_response)) as response:
            with pytest.raises(RuntimeError):
                list(response)

        finished = self._finish_records(caplog)
        assert [(record.status, record.levelno) for record in finished] == [(500, logging.WARNING)]
        assert get_current_context() is None

    def test_unlogged_path_is_not_logged_but_exits_the_unit_of_work(self, app, caplog):
        caplog.set_level(logging.DEBUG, logger="app.request")
        middleware = self._middleware(app, _TestBody([b"OK"]))

        self._serve(middleware, {"REQUEST_METHOD": "GET", "PATH_INFO": "/healthcheck"})

        assert self._finish_records(caplog) == []
        assert self._streaming_records(caplog) == []
        assert get_current_context() is None

    def test_concurrent_requests_are_isolated(self, app, caplog):
        middleware = self._middleware(app, _TestBody([b"OK"]))
        first_request = contextvars.copy_context()
        second_request = contextvars.copy_context()

        first_response = first_request.run(
            middleware, {"REQUEST_METHOD": "GET", "PATH_INFO": "/first"}, _start_response
        )
        second_response = second_request.run(
            middleware, {"REQUEST_METHOD": "GET", "PATH_INFO": "/second"}, _start_response
        )
        first_context = first_request.run(get_current_context)
        second_context = second_request.run(get_current_context)
        logged_in_first = first_request.run(_make_record)
        logged_in_second = second_request.run(_make_record)
        first_request.run(first_response.close)
        first_cleared = first_request.run(get_current_context)
        second_still_entered = second_request.run(get_current_context)
        second_request.run(second_response.close)

        assert first_context is not None and second_context is not None
        assert first_context.request_id != second_context.request_id
        assert get_record_correlation(logged_in_first)["request_id"] == first_context.request_id
        assert get_record_correlation(logged_in_second)["request_id"] == second_context.request_id
        assert first_cleared is None
        assert second_still_entered is second_context
        assert second_request.run(get_current_context) is None
        assert get_current_context() is None

    def test_sequential_requests_on_one_connection_do_not_inherit_context(self, app, caplog):
        middleware = self._middleware(app, _TestBody([b"OK"]))
        alb_trace_id = "1-5759e988-bd862e3fe1be46a994272793"

        first_response = middleware(
            {"REQUEST_METHOD": "GET", "PATH_INFO": "/first", "HTTP_X_AMZN_TRACE_ID": f"Root={alb_trace_id}"},
            _start_response,
        )
        list(first_response)
        first_response.close()
        second_response = middleware({"REQUEST_METHOD": "GET", "PATH_INFO": "/second"}, _start_response)
        list(second_response)
        second_response.close()

        first_fields, second_fields = (get_record_correlation(record) for record in self._finish_records(caplog))
        assert first_fields["alb_trace_id"] == alb_trace_id
        assert second_fields["request_id"] != first_fields["request_id"]
        assert "alb_trace_id" not in second_fields
        assert get_current_context() is None
