import json
import logging
from logging.config import DictConfigurator

import pytest
import sentry_sdk
from pydantic import ValidationError

from app.config import UnitTestConfig
from app.logging import (
    JSONFormatter,
    PlaintextFormatter,
    RejectReservedLogFieldsFilter,
    correlation,
    get_default_logging_config,
)
from app.logging.correlation import ContextType, CorrelationContext, get_record_correlation
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
        context = CorrelationContext(context_type=ContextType.REQUEST, request_id=correlation.new_id())

        with correlation._enter(context, fork_sentry_scope=False):
            tags_inside = dict(sentry_sdk.get_isolation_scope()._tags)
        tags_after = dict(sentry_sdk.get_isolation_scope()._tags)

        assert tags_inside["request_id"] == context.request_id
        assert "request_id" not in tags_after


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

    def test_reserved_log_fields_filter_rejects_a_correlation_field_as_extra(self):
        with correlation.request_context(
            {"REQUEST_METHOD": "GET"}, alb_trace_id=None, cloudfront_request_id=None, debug_logging=False
        ):
            record = _make_record(request_id="spoofed")

        with pytest.raises(ValueError, match="correlation field"):
            RejectReservedLogFieldsFilter().filter(record)

    def test_reserved_log_fields_filter_rejects_correlation_field_names_outside_a_unit_of_work(self):
        record = _make_record(user_id="test-user")

        with pytest.raises(ValueError, match="correlation field"):
            RejectReservedLogFieldsFilter().filter(record)

    def test_reserved_log_fields_filter_allows_unrelated_extras(self):
        record = _make_record(widget_id="widget-1")

        assert RejectReservedLogFieldsFilter().filter(record) is True
        assert record.widget_id == "widget-1"

    def test_reserved_log_fields_filter_ignores_third_party_loggers(self):
        record = _make_record(name="alembic.runtime.migration", user_id="test-user")

        assert RejectReservedLogFieldsFilter().filter(record) is True

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
