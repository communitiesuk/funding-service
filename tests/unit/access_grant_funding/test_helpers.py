from unittest.mock import patch
from uuid import uuid4

from flask import Flask, session

from app.access_grant_funding.helpers import emit_public_sign_up_metric_once
from app.access_grant_funding.session_models import clear_public_sign_up_session, start_public_sign_up
from app.constants import SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS
from app.metrics import MetricEventName


class TestEmitPublicSignUpMetricOnce:
    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_emits_and_records_the_event_on_first_call(self, mock_emit, app: Flask, factories):
        collection = factories.collection.build()

        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE, collection=collection)

            mock_emit.assert_called_once_with(
                MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE,
                grant_recipient=None,
                collection=collection,
                custom_attributes=None,
            )
            assert session[SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS] == [str(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE)]

    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_does_not_emit_the_same_event_twice_in_one_session(self, mock_emit, app: Flask):
        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE)
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE)

            mock_emit.assert_called_once_with(
                MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE,
                grant_recipient=None,
                collection=None,
                custom_attributes=None,
            )

    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_emits_different_events_independently(self, mock_emit, app: Flask):
        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE)
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_INELIGIBLE)

            assert mock_emit.call_count == 2
            assert session[SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS] == [
                str(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE),
                str(MetricEventName.PUBLIC_SIGN_UP_INELIGIBLE),
            ]

    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_starting_a_new_public_sign_up_resets_the_dedupe_and_allows_re_emission(self, mock_emit, app: Flask):
        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE)

            start_public_sign_up(uuid4())
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE)

            assert mock_emit.call_count == 2

    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_clearing_the_public_sign_up_session_resets_the_dedupe_and_allows_re_emission(self, mock_emit, app: Flask):
        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE)

            clear_public_sign_up_session()
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE)

            assert mock_emit.call_count == 2
