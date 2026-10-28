import re
from typing import Any

from tests.smoke.conftest import SmokeGet, client_view

FORGED_TRACE_ID = "0123456789abcdef0123456789abcdef"
FORGED_SPAN_ID = "0123456789abcdef"
TRACE_ID_PATTERN = re.compile(r"[0-9a-f]{32}")


def test_plain_request_reports_a_well_formed_trace_id(baseline: dict[str, Any]) -> None:
    assert TRACE_ID_PATTERN.fullmatch(baseline["trace_id"])


def test_each_plain_request_starts_a_new_trace(smoke_get: SmokeGet) -> None:
    first_view = client_view(smoke_get)
    second_view = client_view(smoke_get)

    assert first_view["trace_id"] != second_view["trace_id"]


def test_forged_sentry_trace_and_baggage_do_not_choose_the_trace_id(smoke_get: SmokeGet) -> None:
    view = client_view(
        smoke_get,
        {
            "sentry-trace": f"{FORGED_TRACE_ID}-{FORGED_SPAN_ID}-1",
            "baggage": f"sentry-trace_id={FORGED_TRACE_ID},sentry-sample_rate=1.0,sentry-sampled=true",
        },
    )

    assert view["trace_id"] != FORGED_TRACE_ID
    assert TRACE_ID_PATTERN.fullmatch(view["trace_id"])


def test_forged_traceparent_and_tracestate_do_not_choose_the_trace_id(smoke_get: SmokeGet) -> None:
    view = client_view(
        smoke_get,
        {"traceparent": f"00-{FORGED_TRACE_ID}-{FORGED_SPAN_ID}-01", "tracestate": "forged=placeholder"},
    )

    assert view["trace_id"] != FORGED_TRACE_ID
    assert TRACE_ID_PATTERN.fullmatch(view["trace_id"])
