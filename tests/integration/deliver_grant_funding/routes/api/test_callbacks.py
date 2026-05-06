import uuid

import pytest
from flask import url_for
from pytest_mock import MockerFixture


class TestGovukNotifyCallback:
    @staticmethod
    def _payload(**overrides):
        payload = {
            "id": str(uuid.uuid4()),
            "reference": None,
            "notification_type": "email",
            "template_id": str(uuid.uuid4()),
            "template_version": 1,
            "to": "recipient@example.com",
            "status": "delivered",
            "created_at": "2026-04-30T12:00:00Z",
            "sent_at": "2026-04-30T12:00:01Z",
            "completed_at": "2026-04-30T12:00:02Z",
        }
        payload.update(overrides)
        return payload

    def test_delivered_email_returns_204_and_does_not_capture(self, anonymous_client, mocker: MockerFixture) -> None:
        capture_message = mocker.patch("app.deliver_grant_funding.routes.api.callbacks.sentry_sdk.capture_message")

        response = anonymous_client.post(
            url_for("deliver_grant_funding.api.govuk_notify_callback"),
            json=self._payload(),
            headers={"Authorization": "Bearer local-use-secret"},
        )

        assert response.status_code == 204
        capture_message.assert_not_called()

    @pytest.mark.parametrize("status", ["temporary-failure", "permanent-failure", "technical-failure"])
    def test_failed_email_captures_error_with_full_context(
        self, anonymous_client, mocker: MockerFixture, status
    ) -> None:
        capture_message = mocker.patch("app.deliver_grant_funding.routes.api.callbacks.sentry_sdk.capture_message")
        new_scope = mocker.patch("app.deliver_grant_funding.routes.api.callbacks.sentry_sdk.new_scope")
        scope = new_scope.return_value.__enter__.return_value
        payload = self._payload(status=status, to="failed@example.com")

        response = anonymous_client.post(
            url_for("deliver_grant_funding.api.govuk_notify_callback"),
            json=payload,
            headers={"Authorization": "Bearer local-use-secret"},
        )

        assert response.status_code == 202
        capture_message.assert_called_once()
        _, kwargs = capture_message.call_args
        assert kwargs["level"] == "error"
        assert status in capture_message.call_args.args[0]
        scope.set_context.assert_called_once()
        context_name, context = scope.set_context.call_args.args
        assert context_name == "notify_callback"
        assert context["to"] == "failed@example.com"
        assert context["status"] == status
        assert context["id"] == payload["id"]
        assert context["template_id"] == payload["template_id"]

    def test_non_email_notification_captures_warning(self, anonymous_client, mocker: MockerFixture) -> None:
        capture_message = mocker.patch("app.deliver_grant_funding.routes.api.callbacks.sentry_sdk.capture_message")
        new_scope = mocker.patch("app.deliver_grant_funding.routes.api.callbacks.sentry_sdk.new_scope")
        scope = new_scope.return_value.__enter__.return_value
        payload = self._payload(notification_type="sms", to="+447700900000")

        response = anonymous_client.post(
            url_for("deliver_grant_funding.api.govuk_notify_callback"),
            json=payload,
            headers={"Authorization": "Bearer local-use-secret"},
        )

        assert response.status_code == 202
        capture_message.assert_called_once()
        _, kwargs = capture_message.call_args
        assert kwargs["level"] == "warning"
        scope.set_context.assert_called_once()
        context_name, context = scope.set_context.call_args.args
        assert context_name == "notify_callback"
        assert context["notification_type"] == "sms"
        assert context["to"] == "+447700900000"

    def test_missing_or_wrong_token_returns_403(self, anonymous_client, mocker: MockerFixture) -> None:
        capture_message = mocker.patch("app.deliver_grant_funding.routes.api.callbacks.sentry_sdk.capture_message")

        no_auth = anonymous_client.post(
            url_for("deliver_grant_funding.api.govuk_notify_callback"),
            json=self._payload(),
        )
        wrong_auth = anonymous_client.post(
            url_for("deliver_grant_funding.api.govuk_notify_callback"),
            json=self._payload(),
            headers={"Authorization": "Bearer wrong"},
        )

        assert no_auth.status_code == 403
        assert wrong_auth.status_code == 403
        capture_message.assert_not_called()

    def test_invalid_payload(self, anonymous_client, mocker: MockerFixture) -> None:
        capture_exception = mocker.patch("app.deliver_grant_funding.routes.api.callbacks.sentry_sdk.capture_exception")

        response = anonymous_client.post(
            url_for("deliver_grant_funding.api.govuk_notify_callback"),
            json={"key": "value"},
            headers={"Authorization": "Bearer local-use-secret"},
        )

        assert response.status_code == 400
        capture_exception.assert_called_once()

    def test_ignores_internal_domains(self, anonymous_client, mocker: MockerFixture) -> None:
        capture_message = mocker.patch("app.deliver_grant_funding.routes.api.callbacks.sentry_sdk.capture_message")

        response = anonymous_client.post(
            url_for("deliver_grant_funding.api.govuk_notify_callback"),
            json=self._payload(to="test@test.communities.gov.uk"),
            headers={"Authorization": "Bearer local-use-secret"},
        )

        assert response.status_code == 202
        capture_message.assert_not_called()

    def test_non_json_returns_400(self, anonymous_client) -> None:
        response = anonymous_client.post(
            url_for("deliver_grant_funding.api.govuk_notify_callback"),
            data="not-json",
            headers={"Authorization": "Bearer local-use-secret", "Content-Type": "text/plain"},
        )
        assert response.status_code == 400
