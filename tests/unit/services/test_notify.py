import datetime
import uuid

import responses
from responses import matchers

from app import notification_service
from app.common.data.types import SubmissionEventType
from app.common.helpers.collections import SubmissionHelper
from app.common.helpers.submission_events import SubmissionEventHelper
from app.services.notify import Notification


class TestNotificationService:
    """
    Test that the methods we've written for sending emails using the GOV.UK Notify Python SDK map to the expected
    HTTP API calls.
    """

    @responses.activate
    def test_send_magic_link(self, app):
        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": "test@test.com",
                        "template_id": "1e5b3cce-99ea-4813-ab39-e52f578c88f6",
                        "personalisation": {
                            "magic_link": "https://magic-link",
                            "magic_link_expires_at": "1:00pm on 4 April 2025",
                            "request_new_magic_link": "https://new-magic-link",
                            "service_desk_url": app.config["ACCESS_SERVICE_DESK_URL"],
                        },
                        "reference": "abc123",
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},  # partial GOV.UK Notify response
        )

        resp = notification_service.send_magic_link(
            "test@test.com",
            magic_link_url="https://magic-link",
            # Timestamp is in UTC; `send_magic_link` will convert to Europe/London local time
            magic_link_expires_at_utc=datetime.datetime.fromisoformat("2025-04-04T12:00:00+00:00"),
            request_new_magic_link_url="https://new-magic-link",
            govuk_notify_reference="abc123",
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    # TODO reinstate this once we finish the certifier flow
    # @responses.activate
    # def test_send_collection_submission(self, app, factories):
    #     # grant = factories.grant.build(id=uuid.UUID("00000000-0000-0000-0000-000000000001"))
    #     collection = factories.collection.build(
    #         name="My test collection", grant__id=uuid.UUID("00000000-0000-0000-0000-000000000001")
    #     )
    #     submission = factories.submission.build(
    #         id=uuid.UUID("10000000-0000-0000-0000-000000000000"),
    #         collection=collection,
    #         mode=SubmissionModeEnum.LIVE,
    #     )
    #     request_matcher = responses.post(
    #         url="https://api.notifications.service.gov.uk/v2/notifications/email",
    #         status=201,
    #         match=[
    #             matchers.json_params_matcher(
    #                 {
    #                     "email_address": submission.created_by.email,
    #                     "template_id": "2ff34065-0a75-4cc3-a782-1c00016e526e",
    #                     "personalisation": {
    #                         "submission name": "My test collection",
    #                         "submission reference": "10000000",
    #                         "submission url": "http://funding.communities.gov.localhost:8080/deliver/grant/00000000-0000-0000-0000-000000000001/submissions/10000000-0000-0000-0000-000000000000",
    #                     },
    #                 }
    #             )
    #         ],
    #         json={"id": "00000000-0000-0000-0000-000000000000"},  # partial GOV.UK Notify response
    #     )
    #
    #     resp = notification_service.send_collection_submission(submission)
    #     assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
    #     assert request_matcher.call_count == 1

    @responses.activate
    def test_send_member_confirmation(self, app, factories):
        grant = factories.grant.build(name="This is a test grant name")
        email_address = "test@communities.gov.uk"
        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": email_address,
                        "template_id": "49ba98c5-0573-4c77-8cb0-3baebe70ee86",
                        "personalisation": {
                            "grant_name": grant.name,
                            "sign_in_url": f"http://funding.communities.gov.localhost:8080/deliver/grant/{grant.id}/reports",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_member_confirmation(grant=grant, email_address="test@communities.gov.uk")
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    @responses.activate
    def test_send_deliver_org_admin_invitation(self, app, factories):
        organisation = factories.organisation.build(name="Test organisation")
        email_address = "test@communities.gov.uk"
        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": email_address,
                        "template_id": "fd143e8b-c735-4e12-9eb5-1655724216d5",
                        "personalisation": {
                            "organisation_name": "Test organisation",
                            "sign_in_url": "http://funding.communities.gov.localhost:8080/deliver/grants",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_deliver_org_admin_invitation(
            organisation=organisation, email_address="test@communities.gov.uk"
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    @responses.activate
    def test_send_deliver_org_member_invitation(self, app, factories):
        organisation = factories.organisation.build(name="Test organisation")
        email_address = "test@communities.gov.uk"
        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": email_address,
                        "template_id": "fc85bd85-89bb-4bfc-87af-26e5cdc6cfed",
                        "personalisation": {
                            "organisation_name": "Test organisation",
                            "sign_in_url": "http://funding.communities.gov.localhost:8080/deliver/grants",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_deliver_org_member_invitation(
            organisation=organisation, email_address="test@communities.gov.uk"
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    @responses.activate
    def test_send_access_submission_signed_off_confirmation(self, app, factories):
        grant_recipient = factories.grant_recipient.build(
            grant__name="Test grant",
        )
        submission = factories.submission.build(
            grant_recipient=grant_recipient,
            collection__grant=grant_recipient.grant,
            collection__name="Test collection",
        )
        email_address = "test@communities.gov.uk"
        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": email_address,
                        "template_id": "e78b9c68-5d45-40a1-8339-04fe7ffc8caa",
                        "personalisation": {
                            "grant_name": "Test grant",
                            "reporting_period": "Test collection",
                            "grant_report_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission.grant_recipient.organisation.id}/grants/{submission.grant_recipient.grant.id}/reports/{submission.id}/tasklist",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_access_submission_sent_for_certification_confirmation(
            submission=submission, email_address="test@communities.gov.uk"
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    @responses.activate
    def test_send_access_submission_ready_to_certify(self, app, factories):
        grant_recipient = factories.grant_recipient.build(
            grant__name="Test grant",
        )
        submission = factories.submission.build(
            grant_recipient=grant_recipient,
            collection__grant=grant_recipient.grant,
            collection__name="Test collection",
            collection__submission_period_end_date=datetime.date(2025, 11, 18),
        )
        submitted_by_user = factories.user.build(name="Submitter User")
        email_address = "test@communities.gov.uk"
        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": email_address,
                        "template_id": "e511c0d0-2ac8-4ded-80a2-13b79023c5d5",
                        "personalisation": {
                            "grant_name": "Test grant",
                            "report_submitter": "Submitter User",
                            "reporting_period": "Test collection",
                            "report_deadline": "Tuesday 18 November 2025",
                            "grant_report_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission.grant_recipient.organisation.id}/grants/{submission.grant_recipient.grant.id}/reports/{submission.id}/tasklist",
                            "government_department": "Test Organisation",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_access_submission_ready_to_certify(
            submission=submission, email_address="test@communities.gov.uk", submitted_by=submitted_by_user
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    def test_send_access_certifier_confirm_submission_declined(
        self, app, factories, submission_awaiting_sign_off, mock_notification_service_calls
    ):
        certifier = factories.user.build(name="Certifier User", email="certifier@test.com")
        factories.submission_event.build(
            submission=submission_awaiting_sign_off,
            event_type=SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER,
            created_by=certifier,
            created_at_utc=datetime.datetime(2025, 12, 1, 9, 30, 0),
            data={"declined_reason": "Decline reason"},
        )
        helper = SubmissionHelper(submission_awaiting_sign_off)
        expected_personalisation = {
            "grant_name": "Test grant",
            "submitter_name": "Submitter User",
            "certifier_name": "Certifier User",
            "certifier_comments": "Decline reason",
            "reporting_period": "Test collection",
            "report_deadline": "Wednesday 3 December 2025",
            "decline_date": "9:30am on Monday 1 December 2025",
            "grant_report_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission_awaiting_sign_off.grant_recipient.organisation.id}/grants/{submission_awaiting_sign_off.grant_recipient.grant.id}/collection/{submission_awaiting_sign_off.collection.id}",
        }
        notification_service.send_access_certifier_confirm_submission_declined(
            certifier_user=certifier,
            submission_helper=helper,
        )
        assert len(mock_notification_service_calls) == 1
        assert mock_notification_service_calls[0].kwargs["personalisation"] == expected_personalisation
        assert mock_notification_service_calls[0].kwargs["template_id"] == "1245cb41-5aec-4957-872c-6471657e57e6"
        assert mock_notification_service_calls[0].kwargs["email_address"] == "certifier@test.com"

    @responses.activate
    def test_send_access_submitter_submission_declined(
        self, app, factories, submission_awaiting_sign_off, mock_notification_service_calls
    ):
        certifier = factories.user.build(name="Certifier User")
        factories.submission_event.build(
            submission=submission_awaiting_sign_off,
            event_type=SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER,
            created_by=certifier,
            created_at_utc=datetime.datetime(2025, 12, 1, 9, 30, 0),
            data={"declined_reason": "Decline reason"},
        )
        helper = SubmissionHelper(submission_awaiting_sign_off)

        expected_personalisation = {
            "grant_name": "Test grant",
            "certifier_name": "Certifier User",
            "reporting_period": "Test collection",
            "certifier_comments": "Decline reason",
            "grant_report_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission_awaiting_sign_off.grant_recipient.organisation.id}/grants/{submission_awaiting_sign_off.grant_recipient.grant.id}/collection/{submission_awaiting_sign_off.collection.id}",
        }

        notification_service.send_access_submitter_submission_declined(
            submission_helper=helper,
            certifier_user=certifier,
        )
        assert len(mock_notification_service_calls) == 1
        assert mock_notification_service_calls[0].kwargs["personalisation"] == expected_personalisation
        assert mock_notification_service_calls[0].kwargs["template_id"] == "791d1a61-c249-4752-9163-6cc81abf4ba9"
        assert mock_notification_service_calls[0].kwargs["email_address"] == "submitter@test.com"

    @responses.activate
    def test_send_access_submission_certified_and_submitted(self, app, factories):
        grant_recipient = factories.grant_recipient.build(
            grant__name="Test grant",
        )
        submission = factories.submission.build(
            grant_recipient=grant_recipient,
            collection__grant=grant_recipient.grant,
            collection__name="Test collection",
            collection__reporting_period_start_date=datetime.date(2025, 10, 13),
            collection__reporting_period_end_date=datetime.date(2025, 10, 27),
            collection__submission_period_end_date=datetime.date(2025, 12, 30),
        )
        submitted_by_user = factories.user.build(name="Submitter User", email="submitter@communities.gov.uk")
        certifier_user = factories.user.build(name="Certifier User", email="certifier@communities.gov.uk")
        factories.submission_event.build(
            event_type=SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION,
            submission=submission,
            created_by=submitted_by_user,
            data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION),
            created_at_utc=datetime.datetime(2025, 11, 24, 0, 0, 0),
        )
        factories.submission_event.build(
            event_type=SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER,
            submission=submission,
            created_by=certifier_user,
            data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER),
            created_at_utc=datetime.datetime(2025, 11, 24, 11, 0, 0),
        )
        factories.submission_event.build(
            event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
            submission=submission,
            created_by=certifier_user,
            data=SubmissionEventHelper.event_from(SubmissionEventType.SUBMISSION_SUBMITTED),
            created_at_utc=datetime.datetime(2025, 11, 25, 10, 37, 0),
        )
        helper = SubmissionHelper(submission)

        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": "test@communities.gov.uk",
                        "template_id": "a8ffd584-0899-40df-ba56-cba95b2db0de",
                        "personalisation": {
                            "grant_name": "Test grant",
                            "submitter_name": "Submitter User",
                            "certifier_name": "Certifier User",
                            "reporting_period": "Monday 13 October 2025 to Monday 27 October 2025",
                            "date_submitted": "10:37am on Tuesday 25 November 2025",
                            "grant_report_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission.grant_recipient.organisation.id}/grants/{submission.grant_recipient.grant.id}/reports/{submission.id}/tasklist",
                            "government_department": "the Test Organisation",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_access_submission_certified_and_submitted(
            email_address="test@communities.gov.uk",
            submission_helper=helper,
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1
