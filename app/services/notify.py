import dataclasses
import datetime
import uuid
from typing import Any
from zoneinfo import ZoneInfo

from flask import Flask, current_app
from notifications_python_client import NotificationsAPIClient  # type: ignore[attr-defined]
from notifications_python_client.errors import APIError, TokenError


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
