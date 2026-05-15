import logging
import uuid

from flask import url_for
from pytest_mock import MockerFixture
from sqlalchemy import select

from app.common.data.models_audit import AuditEvent
from app.common.data.models_user import UserRole
from app.common.data.types import (
    AuditEventType,
    GrantRecipientModeEnum,
    GrantStatusEnum,
    OrganisationModeEnum,
    RoleEnum,
)
from app.extensions import db


def _manual_intervention_logs(caplog) -> list[str]:
    return [
        r.getMessage()
        for r in caplog.records
        if r.levelno == logging.ERROR and "manual intervention required" in r.getMessage()
    ]


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

    def test_technical_failure_captures_error_with_full_context(
        self, anonymous_client, mocker: MockerFixture, caplog
    ) -> None:
        new_scope = mocker.patch("app.deliver_grant_funding.routes.api.callbacks.sentry_sdk.new_scope")
        scope = new_scope.return_value.__enter__.return_value
        payload = self._payload(status="technical-failure", to="failed@example.com")

        response = anonymous_client.post(
            url_for("deliver_grant_funding.api.govuk_notify_callback"),
            json=payload,
            headers={"Authorization": "Bearer local-use-secret"},
        )

        assert response.status_code == 202

        assert any("technical-failure" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)

        scope.set_context.assert_called_once()
        context_name, context = scope.set_context.call_args.args
        assert context_name == "notify_callback"
        assert context["to"] == "failed@example.com"
        assert context["status"] == "technical-failure"
        assert context["id"] == payload["id"]
        assert context["template_id"] == payload["template_id"]

    def test_non_email_notification_captures_warning(self, anonymous_client, mocker: MockerFixture, caplog) -> None:
        new_scope = mocker.patch("app.deliver_grant_funding.routes.api.callbacks.sentry_sdk.new_scope")
        scope = new_scope.return_value.__enter__.return_value
        payload = self._payload(notification_type="sms", to="+447700900000")

        response = anonymous_client.post(
            url_for("deliver_grant_funding.api.govuk_notify_callback"),
            json=payload,
            headers={"Authorization": "Bearer local-use-secret"},
        )
        assert response.status_code == 202

        assert any(
            "unhandled notification type" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING
        )
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

    class TestPermanentFailureCallback:
        @staticmethod
        def _post(anonymous_client, *, status: str, to: str, notification_id: uuid.UUID | None = None) -> tuple:
            payload = {
                "id": str(notification_id or uuid.uuid4()),
                "reference": None,
                "notification_type": "email",
                "template_id": str(uuid.uuid4()),
                "template_version": 1,
                "to": to,
                "status": status,
                "created_at": "2026-04-30T12:00:00Z",
                "sent_at": "2026-04-30T12:00:01Z",
                "completed_at": "2026-04-30T12:00:02Z",
            }
            response = anonymous_client.post(
                url_for("deliver_grant_funding.api.govuk_notify_callback"),
                json=payload,
                headers={"Authorization": "Bearer local-use-secret"},
            )
            return response, payload

        def test_permanent_failure_removes_all_roles_and_writes_audit_events(
            self, anonymous_client, factories, caplog
        ) -> None:
            grant = factories.grant.create(status=GrantStatusEnum.LIVE)
            recipient_org = factories.organisation.create(can_manage_grants=False)
            factories.grant_recipient.create(grant=grant, organisation=recipient_org)

            affected_user = factories.user.create(email="bouncer@example.com")
            other_user = factories.user.create(email="backup@example.com")
            factories.user_role.create(
                user=affected_user,
                organisation=recipient_org,
                grant=grant,
                permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
            )
            factories.user_role.create(
                user=other_user,
                organisation=recipient_org,
                grant=grant,
                permissions=[RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER],
            )

            with caplog.at_level(logging.ERROR, logger="app"):
                response, payload = self._post(anonymous_client, status="permanent-failure", to="bouncer@example.com")

            assert response.status_code == 202

            remaining = db.session.scalars(select(UserRole).where(UserRole.user_id == affected_user.id)).all()
            assert remaining == []
            other_user_role = db.session.scalars(select(UserRole).where(UserRole.user_id == other_user.id)).one()
            assert other_user_role.organisation == recipient_org
            assert set(other_user_role.permissions) == {RoleEnum.MEMBER, RoleEnum.DATA_PROVIDER, RoleEnum.CERTIFIER}

            audit_events = db.session.scalars(
                select(AuditEvent).where(AuditEvent.event_type == AuditEventType.SYSTEM)
            ).all()
            assert len(audit_events) == 1
            event = audit_events[0]
            assert event.data["model_class"] == "UserRole"
            assert event.data["action"] == "delete"
            assert event.data["context"]["notification_id"] == payload["id"]
            assert event.data["changes"]["user_id"] == str(affected_user.id)
            assert event.data["changes"]["grant_id"] == str(grant.id)
            assert event.data["changes"]["organisation_id"] == str(recipient_org.id)

            assert _manual_intervention_logs(caplog) == []

        def test_permanent_failure_flags_uncovered_grant(self, anonymous_client, factories, caplog) -> None:
            grant = factories.grant.create(status=GrantStatusEnum.LIVE)
            recipient_org = factories.organisation.create(can_manage_grants=False)
            factories.grant_recipient.create(grant=grant, organisation=recipient_org)

            affected_user = factories.user.create(email="bouncer@example.com")
            factories.user_role.create(
                user=affected_user, organisation=recipient_org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
            )

            with caplog.at_level(logging.ERROR, logger="app"):
                response, _ = self._post(anonymous_client, status="permanent-failure", to="bouncer@example.com")

            assert response.status_code == 202

            remaining = db.session.scalars(select(UserRole).where(UserRole.user_id == affected_user.id)).all()
            assert remaining == []

            logs = _manual_intervention_logs(caplog)
            assert any("DATA_PROVIDER" in msg and str(grant.id) in msg and str(recipient_org.id) in msg for msg in logs)

        def test_permanent_failure_with_org_level_backup_does_not_flag(
            self, anonymous_client, factories, caplog
        ) -> None:
            grant = factories.grant.create(status=GrantStatusEnum.LIVE)
            recipient_org = factories.organisation.create(can_manage_grants=False)
            factories.grant_recipient.create(grant=grant, organisation=recipient_org)

            affected_user = factories.user.create(email="bouncer@example.com")
            backup_user = factories.user.create(email="org-backup@example.com")
            factories.user_role.create(
                user=affected_user, organisation=recipient_org, grant=grant, permissions=[RoleEnum.CERTIFIER]
            )
            factories.user_role.create(
                user=backup_user, organisation=recipient_org, grant=None, permissions=[RoleEnum.CERTIFIER]
            )

            with caplog.at_level(logging.ERROR, logger="app"):
                response, _ = self._post(anonymous_client, status="permanent-failure", to="bouncer@example.com")

            assert response.status_code == 202
            assert _manual_intervention_logs(caplog) == []
            backup_user_role = db.session.scalars(select(UserRole).where(UserRole.user_id == backup_user.id)).one()
            assert backup_user_role.organisation == recipient_org
            assert set(backup_user_role.permissions) == {RoleEnum.MEMBER, RoleEnum.CERTIFIER}

        def test_permanent_failure_cover_on_different_recipient_org_does_not_count(
            self, anonymous_client, factories, caplog
        ) -> None:
            """A DATA_PROVIDER on a different recipient organisation for the same grant does NOT cover the
            affected user's recipient organisation — this was the bug the org-aware helper fixes."""
            grant = factories.grant.create(status=GrantStatusEnum.LIVE)
            recipient_org_a = factories.organisation.create(can_manage_grants=False)
            recipient_org_b = factories.organisation.create(can_manage_grants=False)
            factories.grant_recipient.create(grant=grant, organisation=recipient_org_a)
            factories.grant_recipient.create(grant=grant, organisation=recipient_org_b)

            affected_user = factories.user.create(email="bouncer@example.com")
            unrelated_user = factories.user.create(email="other-org@example.com")
            factories.user_role.create(
                user=affected_user, organisation=recipient_org_a, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
            )
            factories.user_role.create(
                user=unrelated_user, organisation=recipient_org_b, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
            )

            with caplog.at_level(logging.ERROR, logger="app"):
                response, _ = self._post(anonymous_client, status="permanent-failure", to="bouncer@example.com")

            assert response.status_code == 202
            logs = _manual_intervention_logs(caplog)
            assert any(str(recipient_org_a.id) in msg and "DATA_PROVIDER" in msg for msg in logs)

        def test_permanent_failure_unknown_email_logs_error_and_no_db_changes(self, anonymous_client, caplog) -> None:
            response, _ = self._post(anonymous_client, status="permanent-failure", to="not-a-user@example.com")

            assert response.status_code == 202
            assert any("not-a-user@example.com" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)

            audit_events = db.session.scalars(
                select(AuditEvent).where(AuditEvent.event_type == AuditEventType.SYSTEM)
            ).all()
            assert audit_events == []

        def test_permanent_failure_on_test_org_removes_roles_without_flagging(
            self, anonymous_client, factories, caplog
        ) -> None:
            grant = factories.grant.create()
            recipient_org = factories.organisation.create(can_manage_grants=False, mode=OrganisationModeEnum.TEST)
            factories.grant_recipient.create(grant=grant, organisation=recipient_org, mode=GrantRecipientModeEnum.TEST)

            affected_user = factories.user.create(email="bouncer@example.com")
            factories.user_role.create(
                user=affected_user, organisation=recipient_org, grant=grant, permissions=[RoleEnum.DATA_PROVIDER]
            )

            with caplog.at_level(logging.ERROR, logger="app"):
                response, _ = self._post(anonymous_client, status="permanent-failure", to="bouncer@example.com")

            assert response.status_code == 202

            remaining = db.session.scalars(select(UserRole).where(UserRole.user_id == affected_user.id)).all()
            assert remaining == []
            assert _manual_intervention_logs(caplog) == []

    class TestTemporaryFailureCallback:
        @staticmethod
        def _post(anonymous_client, *, to: str) -> tuple:
            payload = {
                "id": str(uuid.uuid4()),
                "reference": None,
                "notification_type": "email",
                "template_id": str(uuid.uuid4()),
                "template_version": 1,
                "to": to,
                "status": "temporary-failure",
                "created_at": "2026-04-30T12:00:00Z",
                "sent_at": "2026-04-30T12:00:01Z",
                "completed_at": "2026-04-30T12:00:02Z",
            }
            response = anonymous_client.post(
                url_for("deliver_grant_funding.api.govuk_notify_callback"),
                json=payload,
                headers={"Authorization": "Bearer local-use-secret"},
            )
            return response, payload

        def test_temporary_failure_flags_when_user_is_only_certifier(self, anonymous_client, factories, caplog) -> None:
            grant = factories.grant.create(status=GrantStatusEnum.LIVE)
            recipient_org = factories.organisation.create(can_manage_grants=False)
            factories.grant_recipient.create(grant=grant, organisation=recipient_org)

            affected_user = factories.user.create(email="bouncer@example.com")
            factories.user_role.create(
                user=affected_user, organisation=recipient_org, grant=grant, permissions=[RoleEnum.CERTIFIER]
            )

            with caplog.at_level(logging.ERROR, logger="app"):
                response, _ = self._post(anonymous_client, to="bouncer@example.com")

            assert response.status_code == 202

            remaining = db.session.scalars(select(UserRole).where(UserRole.user_id == affected_user.id)).all()
            assert len(remaining) == 1

            audit_events = db.session.scalars(
                select(AuditEvent).where(AuditEvent.event_type == AuditEventType.SYSTEM)
            ).all()
            assert audit_events == []

            logs = _manual_intervention_logs(caplog)
            assert any("CERTIFIER" in msg and str(grant.id) in msg and str(recipient_org.id) in msg for msg in logs)

        def test_temporary_failure_with_coverage_does_not_flag(self, anonymous_client, factories, caplog) -> None:
            grant = factories.grant.create(status=GrantStatusEnum.LIVE)
            recipient_org = factories.organisation.create(can_manage_grants=False)
            factories.grant_recipient.create(grant=grant, organisation=recipient_org)

            affected_user = factories.user.create(email="bouncer@example.com")
            other_user = factories.user.create(email="backup@example.com")
            factories.user_role.create(
                user=affected_user, organisation=recipient_org, grant=grant, permissions=[RoleEnum.CERTIFIER]
            )
            factories.user_role.create(
                user=other_user, organisation=recipient_org, grant=grant, permissions=[RoleEnum.CERTIFIER]
            )

            with caplog.at_level(logging.ERROR, logger="app"):
                response, _ = self._post(anonymous_client, to="bouncer@example.com")

            assert response.status_code == 202
            assert _manual_intervention_logs(caplog) == []

        def test_unknown_email_logs_error_and_no_db_changes(self, anonymous_client, caplog) -> None:
            with caplog.at_level(logging.ERROR, logger="app"):
                response, _ = self._post(anonymous_client, to="not-a-user@example.com")

            assert response.status_code == 202
            assert any("not-a-user@example.com" in r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)
            assert _manual_intervention_logs(caplog) == []
