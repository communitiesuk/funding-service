import dataclasses
import datetime
import uuid
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from flask import Flask, current_app, url_for
from notifications_python_client import NotificationsAPIClient  # type: ignore[attr-defined]
from notifications_python_client.errors import APIError, TokenError

from app.common.filters import format_date

if TYPE_CHECKING:
    from app.common.data.models import Grant, Organisation, Submission
    from app.common.data.models_user import User


class NotificationError(Exception):
    def __init__(
        self,
        message: str = "There was a problem sending the email through GOV.UK Notify",
    ):
        self.message = message
        super().__init__(self.message)


@dataclasses.dataclass(frozen=True)
class Notification:
    id: uuid.UUID


def _format_utc_timestamp_to_local(dt: datetime.datetime) -> str:
    dt = dt.astimezone(ZoneInfo("Europe/London"))
    hour_format = dt.strftime("%-I:%M%p").lower()
    date_format = dt.strftime("%-d %B %Y")
    return f"{hour_format} on {date_format}"


class NotificationService:
    def __init__(self) -> None:
        self.client: NotificationsAPIClient | None = None

    def init_app(self, app: Flask) -> None:
        app.extensions["notification_service"] = self
        app.extensions["notification_service.client"] = NotificationsAPIClient(app.config["GOVUK_NOTIFY_API_KEY"])  # type: ignore[no-untyped-call]

    def _send_email(
        self,
        email_address: str,
        template_id: str,
        personalisation: dict[str, Any] | None,
        govuk_notify_reference: str | None = None,
        email_reply_to_id: str | None = None,
        one_click_unsubscribe_url: str | None = None,
    ) -> Notification:
        if current_app.config["GOVUK_NOTIFY_DISABLE"]:
            current_app.logger.info(
                "Notification service is disabled. Would have sent email to %(email_address)s",
                dict(email_address=email_address),
            )
            return Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))

        try:
            notification_data = current_app.extensions["notification_service.client"].send_email_notification(
                email_address,
                template_id,
                personalisation=personalisation,
                reference=govuk_notify_reference,
                email_reply_to_id=email_reply_to_id,
                one_click_unsubscribe_url=one_click_unsubscribe_url,
            )
            return Notification(id=uuid.UUID(notification_data["id"]))
        except (TokenError, APIError) as e:
            raise NotificationError() from e

    def send_magic_link(
        self,
        email_address: str,
        *,
        magic_link_url: str,
        magic_link_expires_at_utc: datetime.datetime,
        request_new_magic_link_url: str,
        govuk_notify_reference: str | None = None,
    ) -> Notification:
        return self._send_email(
            email_address,
            current_app.config["GOVUK_NOTIFY_MAGIC_LINK_TEMPLATE_ID"],
            personalisation={
                "magic_link": magic_link_url,
                "magic_link_expires_at": _format_utc_timestamp_to_local(magic_link_expires_at_utc),
                "request_new_magic_link": request_new_magic_link_url,
            },
            govuk_notify_reference=govuk_notify_reference,
        )

    def send_collection_submission(self, submission: "Submission") -> Notification:
        return self._send_email(
            submission.created_by.email,
            current_app.config["GOVUK_NOTIFY_COLLECTION_SUBMISSION_TEMPLATE_ID"],
            personalisation={
                "submission name": submission.collection.name,
                "submission reference": submission.reference,
                "submission url": url_for(
                    "developers.access.submission_tasklist", submission_id=submission.id, _external=True
                ),
            },
        )

    def send_member_confirmation(self, email_address: str, *, grant: "Grant") -> Notification:
        return self._send_email(
            email_address,
            current_app.config["GOVUK_NOTIFY_MEMBER_CONFIRMATION_TEMPLATE_ID"],
            personalisation={
                "grant_name": grant.name,
                "sign_in_url": url_for("deliver_grant_funding.list_reports", grant_id=grant.id, _external=True),
            },
        )

    def send_deliver_org_admin_invitation(self, email_address: str, *, organisation: "Organisation") -> Notification:
        return self._send_email(
            email_address,
            current_app.config["GOVUK_NOTIFY_DELIVER_ORGANISATION_ADMIN_TEMPLATE_ID"],
            personalisation={
                "organisation_name": organisation.name,
                "sign_in_url": url_for("deliver_grant_funding.list_grants", _external=True),
            },
        )

    def send_deliver_org_member_invitation(self, email_address: str, *, organisation: "Organisation") -> Notification:
        return self._send_email(
            email_address,
            current_app.config["GOVUK_NOTIFY_DELIVER_ORGANISATION_MEMBER_TEMPLATE_ID"],
            personalisation={
                "organisation_name": organisation.name,
                "sign_in_url": url_for("deliver_grant_funding.list_grants", _external=True),
            },
        )

    def send_access_submission_signed_off_confirmation(
        self, email_address: str, *, submission: "Submission"
    ) -> Notification:
        return self._send_email(
            email_address,
            current_app.config["GOVUK_NOTIFY_ACCESS_SUBMISSION_SENT_FOR_CERTIFICATION_CONFIRMATION_TEMPLATE_ID"],
            personalisation={
                "grant_name": submission.collection.grant.name,
                "reporting_period": submission.collection.name,
                "grant_report_url": url_for(
                    "access_grant_funding.tasklist",
                    organisation_id=submission.grant_recipient.organisation.id,
                    grant_id=submission.grant_recipient.grant.id,
                    submission_id=submission.id,
                    _external=True,
                ),
            },
        )

    # todo: do we want to persist the user who sent it for sign off, the user who certified, etc.
    def send_access_submission_ready_to_certify(
        self, email_address: str, *, submission: "Submission", submitted_by: "User | None" = None
    ) -> Notification:
        personalisation = {
            "grant_name": submission.collection.grant.name,
            "report_submitter": submitted_by.name if submitted_by else submission.created_by.name,
            "reporting_period": submission.collection.name,
            "report_deadline": format_date(submission.collection.submission_period_end_date)
            if submission.collection.submission_period_end_date
            else "(Monitoring report has no deadline set)",
            "grant_report_url": url_for(
                "access_grant_funding.tasklist",
                organisation_id=submission.grant_recipient.organisation.id,
                grant_id=submission.grant_recipient.grant.id,
                submission_id=submission.id,
                _external=True,
            ),
            "government_department": submission.collection.grant.organisation.name,
        }
        return self._send_email(
            email_address,
            current_app.config["GOVUK_NOTIFY_ACCESS_SUBMISSION_READY_TO_CERTIFY_TEMPLATE_ID"],
            personalisation=personalisation,
        )
