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
        response = anonymous_client.get("/custom-cache-control")

        records = _request_records(caplog)
        assert [record.getMessage() for record in records] == [
            "Request started GET /custom-cache-control",
            f"Request finished GET /custom-cache-control 200 in {records[1].duration_ms}ms",
        ]
        assert [record.levelno for record in records] == [logging.INFO, logging.INFO]
        assert response.status_code == records[1].status == 200
        assert records[1].duration_ms >= 0

    def test_every_line_in_a_request_shares_a_generated_request_id(self, anonymous_client, caplog) -> None:
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
        authenticated_platform_admin_client.get("/custom-cache-control")

        user_id = str(authenticated_platform_admin_client.user.id)
        assert [fields.get("user_id") for fields in _correlations(_request_records(caplog))] == [user_id, user_id]

    def test_user_id_read_from_session_without_loading_user(self, anonymous_client, caplog) -> None:
        user_id = str(uuid.uuid4())
        with anonymous_client.session_transaction() as session:
            session["_user_id"] = user_id

        anonymous_client.get("/custom-cache-control")

        assert [fields.get("user_id") for fields in _correlations(_request_records(caplog))] == [user_id, user_id]

    def test_user_id_reflects_login_within_request(self, anonymous_client, caplog) -> None:
        magic_link = interfaces.magic_link.create_magic_link(email="test@local.gov.uk", user=None, redirect_to_path="/")

        anonymous_client.post(url_for("auth.claim_magic_link", magic_link_code=magic_link.code), json={"submit": "yes"})

        user_id = str(interfaces.user.get_user_by_email("test@local.gov.uk").id)
        claim_record = next(r for r in caplog.records if r.getMessage().startswith("Magic link claim page submitted"))
        started, finished = _correlations(_request_records(caplog))
        assert "user_id" not in started
        assert get_record_correlation(claim_record)["user_id"] == user_id
        assert finished["user_id"] == user_id

    def test_user_id_reflects_logout_within_request(self, authenticated_platform_admin_client, caplog) -> None:
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
