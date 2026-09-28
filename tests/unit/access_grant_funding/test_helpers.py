from unittest.mock import patch
from uuid import uuid4

from flask import Flask, session

from app.access_grant_funding.helpers import SignUpModes, emit_public_sign_up_metric_once
from app.access_grant_funding.session_models import clear_public_sign_up_session, start_public_sign_up
from app.common.data.types import GrantRecipientModeEnum, OrganisationModeEnum, SubmissionModeEnum
from app.constants import SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS
from app.metrics import MetricAttributeName, MetricEventName

LIVE_MODES = SignUpModes(
    organisation=OrganisationModeEnum.LIVE,
    grant_recipient=GrantRecipientModeEnum.LIVE,
    submission=SubmissionModeEnum.LIVE,
)
TEST_MODES = SignUpModes(
    organisation=OrganisationModeEnum.TEST,
    grant_recipient=GrantRecipientModeEnum.TEST,
    submission=SubmissionModeEnum.TEST,
)


class TestEmitPublicSignUpMetricOnce:
    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_emits_and_records_the_event_on_first_call(self, mock_emit, app: Flask, factories):
        collection = factories.collection.build()

        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE, LIVE_MODES, collection=collection)

            mock_emit.assert_called_once_with(
                MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE,
                grant_recipient=None,
                collection=collection,
                custom_attributes={MetricAttributeName.SUBMISSION_MODE: "live"},
            )
            assert session[SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS] == [str(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE)]

    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_merges_custom_attributes_with_the_submission_mode(self, mock_emit, app: Flask):
        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(
                MetricEventName.PUBLIC_SIGN_UP_ORGANISATION_CREATED,
                TEST_MODES,
                custom_attributes={MetricAttributeName.ORGANISATION_TYPE: "CHARITY"},
            )

            mock_emit.assert_called_once_with(
                MetricEventName.PUBLIC_SIGN_UP_ORGANISATION_CREATED,
                grant_recipient=None,
                collection=None,
                custom_attributes={
                    MetricAttributeName.ORGANISATION_TYPE: "CHARITY",
                    MetricAttributeName.SUBMISSION_MODE: "test",
                },
            )

    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_does_not_emit_the_same_event_twice_in_one_session(self, mock_emit, app: Flask):
        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE, LIVE_MODES)
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE, LIVE_MODES)

            mock_emit.assert_called_once_with(
                MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE,
                grant_recipient=None,
                collection=None,
                custom_attributes={MetricAttributeName.SUBMISSION_MODE: "live"},
            )

    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_emits_different_events_independently(self, mock_emit, app: Flask):
        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE, LIVE_MODES)
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_INELIGIBLE, LIVE_MODES)

            assert mock_emit.call_count == 2
            assert session[SESSION_EMITTED_PUBLIC_SIGN_UP_METRICS] == [
                str(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE),
                str(MetricEventName.PUBLIC_SIGN_UP_INELIGIBLE),
            ]

    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_starting_a_new_public_sign_up_resets_the_dedupe_and_allows_re_emission(self, mock_emit, app: Flask):
        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE, LIVE_MODES)

            start_public_sign_up(uuid4())
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE, LIVE_MODES)

            assert mock_emit.call_count == 2

    @patch("app.access_grant_funding.helpers.emit_metric_count")
    def test_clearing_the_public_sign_up_session_resets_the_dedupe_and_allows_re_emission(self, mock_emit, app: Flask):
        with app.test_request_context("/"):
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE, LIVE_MODES)

            clear_public_sign_up_session()
            emit_public_sign_up_metric_once(MetricEventName.PUBLIC_SIGN_UP_ELIGIBLE, LIVE_MODES)

            assert mock_emit.call_count == 2
