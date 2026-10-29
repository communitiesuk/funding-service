import datetime
import logging
import uuid
from typing import Any

import pytest
from flask import url_for

from app.common.data import interfaces
from app.logging.correlation import get_current_context, get_record_correlation
from tests.utils import recording_sentry_scope

ALB_ROOT = "1-5759e988-bd862e3fe1be46a994272793"
INCOMING_TRACE_ID = "0af7651916cd43dd8448eb211c80319c"


def _request_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [record for record in caplog.records if record.name == "app.request"]


def _correlations(records: list[logging.LogRecord]) -> list[dict[str, Any]]:
    return [dict(get_record_correlation(record)) for record in records]


def _records_for_request(caplog: pytest.LogCaptureFixture, request_id: str) -> list[logging.LogRecord]:
    return [record for record in caplog.records if get_record_correlation(record).get("request_id") == request_id]


class TestLogging:
    def test_basic_log_message(self, app, caplog) -> None:
        with app.app_context():
            app.logger.info("this is a test log message")

        assert caplog.messages == ["this is a test log message"]

    @pytest.mark.parametrize("simple", ["hello", 1, 1.0, True])
    def test_can_log_simple_interpolated_values(self, app, caplog, simple: Any) -> None:
        with app.app_context():
            app.logger.info("this is a test log %(simple)s", {"simple": simple})

        assert caplog.messages == [f"this is a test log {simple}"]

    @pytest.mark.parametrize("complex", [[1, 2, 3], (1, 2, 3), {"a": "b"}, {"a"}])
    def test_cannot_log_complex_data_types(self, app, caplog, complex: Any) -> None:
        with app.app_context(), pytest.raises(ValueError) as exc:
            app.logger.info("this is a test log %(complex)s", {"complex": complex})

        assert isinstance(exc.value, ValueError)
        assert str(exc.value) == f"Attempt to log data type `{type(complex)}` rejected by security policy."

    def test_can_log_date(self, app, caplog) -> None:
        test_date = datetime.date(2023, 6, 30)
        with app.app_context():
            app.logger.info("this is a test log %(date)s", {"date": test_date})

        assert caplog.messages == ["this is a test log 2023-06-30"]

    def test_can_log_datetime(self, app, caplog) -> None:
        test_datetime = datetime.datetime(2023, 6, 30, 14, 30, 45)
        with app.app_context():
            app.logger.info("this is a test log %(datetime)s", {"datetime": test_datetime})

        assert caplog.messages == ["this is a test log 2023-06-30 14:30:45"]


class TestRequestLogging:
    def test_logs_start_and_finish_of_request(self, anonymous_client, caplog) -> None:
        caplog.set_level(logging.DEBUG, logger="app")

        response = anonymous_client.get("/custom-cache-control")

        records = _request_records(caplog)
        assert [record.getMessage() for record in records] == [
            "Request started GET /custom-cache-control",
            f"Request finished GET /custom-cache-control 200 in {records[1].duration_ms}ms",
        ]
        assert [record.levelno for record in records] == [logging.DEBUG, logging.INFO]
        assert response.status_code == records[1].status == 200
        assert records[1].duration_ms >= 0

    def test_start_line_is_not_logged_at_info(self, anonymous_client, caplog) -> None:
        caplog.set_level(logging.INFO, logger="app")

        anonymous_client.get("/custom-cache-control")

        assert [record.getMessage().split(" in ")[0] for record in _request_records(caplog)] == [
            "Request finished GET /custom-cache-control 200"
        ]

    @pytest.mark.parametrize(
        "path, expected_status, expected_level",
        [
            ("/_testing/500", 500, logging.WARNING),
            ("/_testing/does-not-exist", 404, logging.INFO),
            ("/custom-cache-control", 200, logging.INFO),
        ],
    )
    def test_finish_line_level_depends_on_status(
        self, anonymous_client, caplog, path, expected_status, expected_level
    ) -> None:
        anonymous_client.get(path)

        finished = _request_records(caplog)[-1]
        assert finished.getMessage().startswith("Request finished")
        assert finished.status == expected_status
        assert finished.levelno == expected_level

    def test_finish_line_carries_request_and_response_details(self, anonymous_client, caplog) -> None:
        anonymous_client.get(
            "/custom-cache-control",
            data="test request body",
            headers={"User-Agent": "test-user-agent/1.0"},
            environ_base={"REMOTE_ADDR": "198.51.100.2"},
        )

        finished = _request_records(caplog)[-1]
        assert finished.request_size == len("test request body")
        assert finished.response_size == 0
        assert finished.response_streamed is False

        # TODO[FSPT-1805]: discussion TBD around logging User-Agent/IP and privacy policy re sending to Sentry
        # assert finished.user_agent == "test-user-agent/1.0"
        # assert finished.client_ip == "198.51.100.2"

    # TODO[FSPT-1805]: discussion TBD around logging User-Agent/IP and privacy policy re sending to Sentry
    # def test_finish_line_client_ip_is_the_test_client_remote_address(self, anonymous_client, caplog) -> None:
    #     response = anonymous_client.get("/custom-cache-control")
    #
    #     finished = _request_records(caplog)[-1]
    #     assert finished.client_ip == response.request.remote_addr

    def test_finish_line_omits_absent_client_details(self, anonymous_client, caplog) -> None:
        anonymous_client.get("/custom-cache-control", headers={"User-Agent": ""})

        finished = _request_records(caplog)[-1]
        assert finished.request_size == 0
        assert not hasattr(finished, "user_agent")

    def test_streamed_csv_export_finish_line_covers_the_body(self, authenticated_platform_admin_client, caplog) -> None:
        response = authenticated_platform_admin_client.get(url_for("data_analysis.download_user_management_events_csv"))

        finished = _request_records(caplog)[-1]
        assert response.status_code == 200
        assert finished.getMessage().startswith("Request finished GET /deliver/admin/data-analysis/")
        assert finished.response_streamed is True
        assert finished.response_size == len(response.data)
        assert get_current_context() is None

    def test_lines_logged_while_streaming_a_response_share_the_request_id(self, anonymous_client, caplog) -> None:
        response = anonymous_client.get("/_testing/streamed-response")

        streaming_record = next(r for r in caplog.records if r.getMessage() == "Generating streamed response body")
        finished = _request_records(caplog)[-1]
        request_id = get_record_correlation(finished)["request_id"]
        assert response.data == b"first chunk\nsecond chunk\n"
        assert get_record_correlation(streaming_record)["request_id"] == request_id
        assert get_record_correlation(streaming_record)["path"] == "/_testing/streamed-response"
        assert _records_for_request(caplog, request_id)[-1] is finished
        assert finished.response_streamed is True
        assert finished.response_size == len(response.data)
        assert get_current_context() is None

    def test_streamed_response_body_failure_is_logged_with_the_request_id(self, anonymous_client, caplog) -> None:
        with pytest.raises(RuntimeError, match="streamed body failed"):
            anonymous_client.get("/_testing/streamed-response-failure")

        body_failed = next(r for r in _request_records(caplog) if r.getMessage().startswith("Response body failed"))
        finished = _request_records(caplog)[-1]
        request_id = get_record_correlation(finished)["request_id"]

        assert body_failed.levelno == logging.WARNING
        assert body_failed.exc_info is not None
        assert body_failed.status == 200
        assert get_record_correlation(body_failed)["request_id"] == request_id

        assert finished.getMessage().startswith("Request finished GET /_testing/streamed-response-failure 200")
        assert finished.levelno == logging.WARNING
        assert finished.iteration_failed is True
        assert finished.response_streamed is True
        assert _records_for_request(caplog, request_id)[-1] is finished

    def test_streamed_response_logs_streaming_line_between_start_and_body(self, anonymous_client, caplog) -> None:
        caplog.set_level(logging.DEBUG, logger="app")

        anonymous_client.get("/_testing/streamed-response")

        finished = _request_records(caplog)[-1]
        request_records = _records_for_request(caplog, get_record_correlation(finished)["request_id"])
        assert [record.getMessage().split(" in ")[0] for record in request_records] == [
            "Request started GET /_testing/streamed-response",
            "Response streaming GET /_testing/streamed-response 200",
            "Generating streamed response body",
            "Request finished GET /_testing/streamed-response 200",
        ]
        assert request_records[1].levelno == logging.DEBUG

    def test_every_line_in_a_request_shares_a_generated_request_id(self, anonymous_client, caplog) -> None:
        caplog.set_level(logging.DEBUG, logger="app")

        anonymous_client.get("/custom-cache-control", headers={"X-Request-Id": "client-supplied"})
        anonymous_client.get("/custom-cache-control")

        first, second = _correlations(_request_records(caplog))[::2]
        first_finish = _correlations(_request_records(caplog))[1]
        assert uuid.UUID(first["request_id"])
        assert first["request_id"] == first_finish["request_id"]
        assert first["request_id"] != second["request_id"]
        assert first["trace_id"] == first_finish["trace_id"]
        assert first["trace_id"] != second["trace_id"]
        assert first["context_type"] == "request"
        assert first["method"] == "GET"
        assert first["path"] == "/custom-cache-control"
        assert first["endpoint"] == "custom_cache_control"

    def test_healthcheck_is_not_logged(self, anonymous_client, caplog) -> None:
        response = anonymous_client.get(url_for("healthcheck.healthcheck"))

        assert response.status_code == 200
        assert _request_records(caplog) == []

    def test_unknown_path_under_the_healthcheck_prefix_is_logged(self, anonymous_client, caplog) -> None:
        anonymous_client.get("/healthcheck/nope")

        finished = _request_records(caplog)[-1]
        assert finished.getMessage().startswith("Request finished GET /healthcheck/nope 404")
        assert finished.status == 404

    def test_context_is_cleared_after_request(self, anonymous_client) -> None:
        anonymous_client.get("/custom-cache-control")

        assert get_current_context() is None

    def test_second_request_does_not_inherit_the_first_requests_user(
        self, app, authenticated_platform_admin_client, caplog
    ) -> None:
        authenticated_platform_admin_client.get("/custom-cache-control")
        first_request_fields = _correlations(_request_records(caplog))
        caplog.clear()

        with app.app_context():
            signed_out_client = app.test_client()
            signed_out_client.get("/custom-cache-control")

        second_request_fields = _correlations(_request_records(caplog))
        assert first_request_fields[0]["user_id"] == str(authenticated_platform_admin_client.user.id)
        assert second_request_fields
        assert {fields["request_id"] for fields in second_request_fields}.isdisjoint(
            {fields["request_id"] for fields in first_request_fields}
        )
        assert all(fields.get("user_id") is None for fields in second_request_fields)
        assert get_current_context() is None

    @pytest.mark.parametrize(
        "headers, expected_alb_trace_id, expected_cloudfront_request_id",
        [
            (
                {"X-Amzn-Trace-Id": f"Self=1-67891234-12456789abcdef0123456789;Root={ALB_ROOT}", "X-Amz-Cf-Id": "a-_="},
                ALB_ROOT,
                "a-_=",
            ),
            ({"X-Amzn-Trace-Id": "Root=injected value", "X-Amz-Cf-Id": "bad value<script>"}, None, None),
            ({}, None, None),
        ],
    )
    def test_infrastructure_trace_ids_are_validated(
        self, anonymous_client, caplog, headers, expected_alb_trace_id, expected_cloudfront_request_id
    ) -> None:
        anonymous_client.get("/custom-cache-control", headers=headers)

        for fields in _correlations(_request_records(caplog)):
            assert fields.get("alb_trace_id") == expected_alb_trace_id
            assert fields.get("cloudfront_request_id") == expected_cloudfront_request_id

    def test_incoming_sentry_trace_headers_are_not_continued(self, anonymous_client, caplog) -> None:
        anonymous_client.get(
            "/custom-cache-control",
            headers={
                "sentry-trace": f"{INCOMING_TRACE_ID}-b7ad6b7169203331-1",
                "baggage": f"sentry-trace_id={INCOMING_TRACE_ID}",
            },
        )

        trace_ids = {fields.get("trace_id") for fields in _correlations(_request_records(caplog))}
        assert len(trace_ids) == 1
        assert None not in trace_ids
        assert INCOMING_TRACE_ID not in trace_ids

    def test_user_id_present_from_first_line_for_signed_in_user(
        self, authenticated_platform_admin_client, caplog
    ) -> None:
        caplog.set_level(logging.DEBUG, logger="app")

        authenticated_platform_admin_client.get("/custom-cache-control")

        user_id = str(authenticated_platform_admin_client.user.id)
        assert [fields.get("user_id") for fields in _correlations(_request_records(caplog))] == [user_id, user_id]

    def test_user_id_read_from_session_without_loading_user(self, anonymous_client, caplog) -> None:
        caplog.set_level(logging.DEBUG, logger="app")

        user_id = str(uuid.uuid4())
        with anonymous_client.session_transaction() as session:
            session["_user_id"] = user_id

        anonymous_client.get("/custom-cache-control")

        assert [fields.get("user_id") for fields in _correlations(_request_records(caplog))] == [user_id, user_id]

    def test_user_id_reflects_login_within_request(self, anonymous_client, caplog) -> None:
        caplog.set_level(logging.DEBUG, logger="app")

        magic_link = interfaces.magic_link.create_magic_link(email="test@local.gov.uk", user=None, redirect_to_path="/")

        anonymous_client.post(url_for("auth.claim_magic_link", magic_link_code=magic_link.code), json={"submit": "yes"})

        user_id = str(interfaces.user.get_user_by_email("test@local.gov.uk").id)
        claim_record = next(r for r in caplog.records if r.getMessage().startswith("Magic link claim page submitted"))
        started, finished = _correlations(_request_records(caplog))
        assert "user_id" not in started
        assert get_record_correlation(claim_record)["user_id"] == user_id
        assert finished["user_id"] == user_id

    def test_user_id_reflects_logout_within_request(self, authenticated_platform_admin_client, caplog) -> None:
        caplog.set_level(logging.DEBUG, logger="app")

        authenticated_platform_admin_client.get(url_for("auth.sign_out"))

        started, finished = _correlations(_request_records(caplog))
        assert started["user_id"] == str(authenticated_platform_admin_client.user.id)
        assert "user_id" not in finished

    def test_correlation_fields_are_set_as_sentry_tags_and_attributes(
        self, app, authenticated_platform_admin_client, caplog
    ) -> None:
        with recording_sentry_scope() as recorder:
            authenticated_platform_admin_client.get(
                "/custom-cache-control", headers={"X-Amzn-Trace-Id": f"Root={ALB_ROOT}", "X-Amz-Cf-Id": "abc"}
            )

        started = _correlations(_request_records(caplog))[0]
        expected_fields = {
            "context_type": "request",
            "request_id": started["request_id"],
            "user_id": str(authenticated_platform_admin_client.user.id),
            "alb_trace_id": ALB_ROOT,
            "cloudfront_request_id": "abc",
        }
        assert recorder.tags[0] == expected_fields
        assert recorder.attributes[0] == expected_fields

    def test_sentry_user_is_cleared_after_logout_within_request(self, authenticated_platform_admin_client) -> None:
        with recording_sentry_scope() as recorder:
            authenticated_platform_admin_client.get(url_for("auth.sign_out"))

        assert recorder.users[-1] is None
        assert "user_id" not in recorder.tags[-1]
        assert "user_id" not in recorder.attributes[-1]


class TestErrorLogging:
    def test_unhandled_exception_logged_exactly_once(self, app, anonymous_client, caplog, monkeypatch) -> None:
        monkeypatch.setitem(app.config, "PROPAGATE_EXCEPTIONS", False)

        response = anonymous_client.get("/_testing/unhandled-exception")

        error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
        assert response.status_code == 500
        assert len(error_records) == 1
        assert error_records[0].exc_info is not None
        assert error_records[0].exc_info[0] is RuntimeError
        assert get_record_correlation(error_records[0])["path"] == "/_testing/unhandled-exception"
        assert _request_records(caplog)[-1].status == 500

    def test_explicit_abort_500_logged_exactly_once(self, anonymous_client, caplog) -> None:
        response = anonymous_client.get("/_testing/500")

        error_records = [record for record in caplog.records if record.levelno >= logging.ERROR]
        assert response.status_code == 500
        assert [record.getMessage() for record in error_records] == ["Internal server error"]

    def test_finish_line_logged_when_exception_propagates(self, anonymous_client, caplog) -> None:
        with pytest.raises(RuntimeError):
            anonymous_client.get("/_testing/unhandled-exception")

        assert _request_records(caplog)[-1].status == 500
        assert get_current_context() is None
