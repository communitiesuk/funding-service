import dataclasses
import datetime
import uuid
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from flask import Flask, current_app, url_for
from notifications_python_client import NotificationsAPIClient  # type: ignore[attr-defined]
from notifications_python_client.errors import APIError, TokenError

from app.common.data.types import GrantRecipientModeEnum
from app.common.filters import format_date, format_datetime

if TYPE_CHECKING:
    from app.common.data.models import Collection, Grant, GrantRecipient, Organisation, Submission
    from app.common.data.models_user import User
    from app.common.helpers.collections import SubmissionHelper


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
                email_address=email_address,
                template_id=template_id,
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
                "service_desk_url": current_app.config["ACCESS_SERVICE_DESK_URL"],
            },
            govuk_notify_reference=govuk_notify_reference,
        )

    # TODO reinstate this once we finish the certifier flow
    #
    # def send_collection_submission(self, submission: "Submission") -> Notification:
    #     return self._send_email(
    #         submission.created_by.email,
    #         current_app.config["GOVUK_NOTIFY_COLLECTION_SUBMISSION_TEMPLATE_ID"],
    #         personalisation={
    #             "submission name": submission.collection.name,
    #             "submission reference": submission.reference,
    #             "submission url": url_for(
    #                 "access_grant_funding.route_to_submission",
    #                 organisation_id=submission.grant_recipient.organisation_id,
    #                 collection_id=submission.collection.id,
    #                 grant_id=submission.collection.grant_id,
    #                 _external=True,
    #             ),
    #         },
    #     )

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

    def send_access_report_opened(
        self, email_address: str, *, collection: "Collection", grant_recipient: "GrantRecipient"
    ) -> Notification:
        personalisation = {
            "grant_name": grant_recipient.grant.name,
            "reporting_period": collection.name,
            "report_deadline": format_date(collection.submission_period_end_date)
            if collection.submission_period_end_date
            else "(Dates to be confirmed)",
            "is_test_data": "yes" if grant_recipient.mode == GrantRecipientModeEnum.TEST else "no",
            "grant_report_url": url_for(
                "access_grant_funding.route_to_submission",
                organisation_id=grant_recipient.organisation.id,
                grant_id=grant_recipient.grant.id,
                collection_id=collection.id,
                _external=True,
            ),
        }
        return self._send_email(
            email_address,
            current_app.config["GOVUK_NOTIFY_GRANT_RECIPIENT_REPORT_NOTIFICATION_TEMPLATE_ID"],
            personalisation=personalisation,
        )

    def send_access_submission_sent_for_certification_confirmation(
        self, email_address: str, *, submission: "Submission"
    ) -> Notification:
        return self._send_email(
            email_address,
            current_app.config["GOVUK_NOTIFY_ACCESS_SUBMISSION_SENT_FOR_CERTIFICATION_CONFIRMATION_TEMPLATE_ID"],
            personalisation={
                "grant_name": submission.collection.grant.name,
                "reporting_period": submission.collection.name,
                "is_test_data": "yes" if submission.grant_recipient.mode == GrantRecipientModeEnum.TEST else "no",
                "grant_report_url": url_for(
                    "access_grant_funding.view_locked_report",
                    organisation_id=submission.grant_recipient.organisation.id,
                    grant_id=submission.grant_recipient.grant.id,
                    submission_id=submission.id,
                    _external=True,
                ),
            },
        )

    def send_access_submission_ready_to_certify(
        self, email_address: str, *, submission: "Submission", submitted_by: "User"
    ) -> Notification:
        personalisation = {
            "grant_name": submission.collection.grant.name,
            "report_submitter": submitted_by.name,
            "reporting_period": submission.collection.name,
            "report_deadline": format_date(submission.collection.submission_period_end_date)
            if submission.collection.submission_period_end_date
            else "(Dates to be confirmed)",
            "is_test_data": "yes" if submission.grant_recipient.mode == GrantRecipientModeEnum.TEST else "no",
            "grant_report_url": url_for(
                "access_grant_funding.view_locked_report",
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

    def send_access_certifier_confirm_submission_declined(
        self,
        certifier_user: "User",
        submission_helper: "SubmissionHelper",
    ) -> Notification:
        if not (
            submission_helper.sent_for_certification_by and submission_helper.events.submission_state.declined_at_utc
        ):
            current_app.logger.warning(
                "Missing value on the submission state for submission id %(submission_id)s",
                dict(submission_id=submission_helper.id),
            )
        personalisation = {
            "grant_name": submission_helper.collection.grant.name,
            "submitter_name": submission_helper.sent_for_certification_by.name
            if submission_helper.sent_for_certification_by
            else "(Submitter not known)",
            "certifier_name": certifier_user.name,
            "reporting_period": submission_helper.collection.name,
            "certifier_comments": submission_helper.events.submission_state.declined_reason,
            "report_deadline": format_date(submission_helper.collection.submission_period_end_date)
            if submission_helper.collection.submission_period_end_date
            else "(Dates to be confirmed)",
            "decline_date": format_datetime(submission_helper.events.submission_state.declined_at_utc)
            if submission_helper.events.submission_state.declined_at_utc
            else "(Declined date not known)",
            "is_test_data": "yes"
            if submission_helper.submission.grant_recipient.mode == GrantRecipientModeEnum.TEST
            else "no",
            "grant_report_url": url_for(
                "access_grant_funding.route_to_submission",
                organisation_id=submission_helper.submission.grant_recipient.organisation.id,
                grant_id=submission_helper.submission.grant_recipient.grant.id,
                collection_id=submission_helper.collection.id,
                _external=True,
            ),
        }
        return self._send_email(
            email_address=certifier_user.email,
            template_id=current_app.config["GOVUK_NOTIFY_ACCESS_CERTIFIER_REPORT_DECLINED_TEMPLATE_ID"],
            personalisation=personalisation,
        )

    def send_access_submitter_submission_declined(
        self,
        certifier_user: "User",
        submission_helper: "SubmissionHelper",
    ) -> Notification:
        submission_state = submission_helper.events.submission_state
        if not submission_helper.sent_for_certification_by:
            # as this is the user we're sending the email to its a hard requirement
            # todo: this should probably be part of the interface instead
            raise ValueError(f"Missing values on the submission state for submission id {submission_helper.id}")
        personalisation = {
            "grant_name": submission_helper.collection.grant.name,
            "certifier_name": certifier_user.name,
            "reporting_period": submission_helper.collection.name,
            "certifier_comments": submission_state.declined_reason,
            "is_test_data": "yes"
            if submission_helper.submission.grant_recipient.mode == GrantRecipientModeEnum.TEST
            else "no",
            "grant_report_url": url_for(
                "access_grant_funding.route_to_submission",
                organisation_id=submission_helper.submission.grant_recipient.organisation.id,
                grant_id=submission_helper.submission.grant_recipient.grant.id,
                collection_id=submission_helper.collection.id,
                _external=True,
            ),
        }
        return self._send_email(
            email_address=str(submission_helper.sent_for_certification_by.email),
            template_id=current_app.config["GOVUK_NOTIFY_ACCESS_SUBMITTER_REPORT_DECLINED_TEMPLATE_ID"],
            personalisation=personalisation,
        )

    def send_access_submission_certified_and_submitted(
        self, email_address: str, *, submission_helper: "SubmissionHelper"
    ) -> Notification:
        if (
            submission_helper.collection.requires_certification
            and not (submission_helper.sent_for_certification_by and submission_helper.certified_by)
            or not submission_helper.submitted_at_utc
        ):
            # note baseline reports are unlikely to have reporting dates and we don't
            # expect them here
            current_app.logger.warning(
                "Submitted email sent with missing details for submission id %(submission_id)s",
                dict(submission_id=submission_helper.id),
            )

        personalisation = {
            "grant_name": submission_helper.collection.grant.name,
            "submitter_name": submission_helper.sent_for_certification_by.name
            if submission_helper.sent_for_certification_by
            else "(Submitter not known)",
            "certifier_name": submission_helper.certified_by.name
            if submission_helper.certified_by
            else "(Certifier not known)",
            "reporting_period": submission_helper.collection.name,
            "date_submitted": format_datetime(submission_helper.submitted_at_utc)
            if submission_helper.submitted_at_utc
            else "(Date submitted not known)",
            "is_test_data": "yes"
            if submission_helper.submission.grant_recipient.mode == GrantRecipientModeEnum.TEST
            else "no",
            "grant_report_url": url_for(
                "access_grant_funding.view_locked_report",
                organisation_id=submission_helper.submission.grant_recipient.organisation.id,
                grant_id=submission_helper.submission.grant_recipient.grant.id,
                submission_id=submission_helper.id,
                _external=True,
            ),
            "government_department": f"the {submission_helper.collection.grant.organisation.name}",
        }
        return self._send_email(
            email_address,
            current_app.config["GOVUK_NOTIFY_ACCESS_SUBMISSION_CERTIFICATION_SUBMISSION_CONFIRMATION_TEMPLATE_ID"],
            personalisation=personalisation,
        )
