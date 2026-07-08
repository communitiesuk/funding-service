import datetime
import uuid

import pytest
import responses
from responses import matchers

from app.common.data.types import GrantRecipientModeEnum, SubmissionEventType
from app.common.filters import format_datetime
from app.common.helpers.collections import SubmissionHelper
from app.common.helpers.submission_events import SubmissionEventHelper
from app.extensions import notification_service
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
    def test_send_access_report_opened(self, app, factories):
        grant_recipient = factories.grant_recipient.build(
            organisation__name="Test organisation",
            grant__name="Test grant",
            mode=GrantRecipientModeEnum.LIVE,
        )
        collection = factories.collection.build(
            name="Test collection",
            grant=grant_recipient.grant,
            submission_period_end_date=datetime.date(2025, 12, 31),
        )
        email_address = "test@communities.gov.uk"
        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": email_address,
                        "template_id": "4fc8d831-e241-4648-a8d3-04fb1bd9193e",
                        "personalisation": {
                            "grant_name": "Test grant",
                            "organisation_name": "Test organisation",
                            "submission_name": "Test collection",
                            "requires_certification": "yes",
                            "submission_deadline": "Wednesday 31 December 2025",
                            "is_test_data": "no",
                            "grant_submission_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{grant_recipient.organisation.id}/grants/{grant_recipient.grant.id}/collection/{collection.id}",
                            "allows_multiple_submissions": "no",
                            "collection_type_noun": "report",
                            "submissions": "",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_access_report_opened(
            email_address=email_address,
            collection=collection,
            grant_recipient=grant_recipient,
            submission_helpers=[],
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    @responses.activate
    def test_send_access_submission_send_for_sign_off_confirmation(self, app, factories):
        grant_recipient = factories.grant_recipient.build(
            organisation__name="Test organisation",
            grant__name="Test grant",
        )
        submission = factories.submission.build(
            grant_recipient=grant_recipient,
            reference="TG-R123456",
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
                            "organisation_name": "Test organisation",
                            "reference": "TG-R123456",
                            "submission_name": "Test collection",
                            "is_test_data": "no",
                            "grant_submission_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission.grant_recipient.organisation.id}/grants/{submission.grant_recipient.grant.id}/reports/{submission.id}/view",
                            "collection_type_noun": "report",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_access_submission_sent_for_certification_confirmation(
            submission_helper=SubmissionHelper(submission), email_address="test@communities.gov.uk"
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    @responses.activate
    def test_send_access_submission_ready_to_certify(self, app, factories):
        grant_recipient = factories.grant_recipient.build(
            organisation__name="Test organisation",
            grant__name="Test grant",
        )
        submission = factories.submission.build(
            grant_recipient=grant_recipient,
            reference="TG-R123456",
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
                            "organisation_name": "Test organisation",
                            "reference": "TG-R123456",
                            "submitter": "Submitter User",
                            "submission_name": "Test collection",
                            "submission_deadline": "Tuesday 18 November 2025",
                            "is_test_data": "no",
                            "grant_submission_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission.grant_recipient.organisation.id}/grants/{submission.grant_recipient.grant.id}/reports/{submission.id}/view",
                            "government_department": "Test Organisation",
                            "collection_type_noun": "report",
                            "collection_type_noun_capitalised": "Report",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_access_submission_ready_to_certify(
            submission_helper=SubmissionHelper(submission),
            email_address="test@communities.gov.uk",
            submitted_by=submitted_by_user,
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
            "organisation_name": submission_awaiting_sign_off.grant_recipient.organisation.name,
            "reference": submission_awaiting_sign_off.reference,
            "submitter_name": "Submitter User",
            "certifier_name": "Certifier User",
            "certifier_comments": "Decline reason",
            "submission_name": "Test collection",
            "submission_deadline": "Wednesday 3 December 2025",
            "decline_date": "9:30am on Monday 1 December 2025",
            "is_test_data": "no",
            "grant_submission_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission_awaiting_sign_off.grant_recipient.organisation.id}/grants/{submission_awaiting_sign_off.grant_recipient.grant.id}/collection/{submission_awaiting_sign_off.collection.id}",
            "collection_type_noun": "report",
        }
        notification_service.send_access_certifier_confirm_submission_declined(
            user=certifier,
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
            "organisation_name": submission_awaiting_sign_off.grant_recipient.organisation.name,
            "reference": submission_awaiting_sign_off.reference,
            "certifier_name": "Certifier User",
            "submission_name": "Test collection",
            "certifier_comments": "Decline reason",
            "submission_deadline": "Wednesday 3 December 2025",
            "is_test_data": "no",
            "grant_submission_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission_awaiting_sign_off.grant_recipient.organisation.id}/grants/{submission_awaiting_sign_off.grant_recipient.grant.id}/collection/{submission_awaiting_sign_off.collection.id}",
            "collection_type_noun": "report",
        }

        notification_service.send_access_submitter_submission_declined(
            submission_helper=helper,
            user=helper.sent_for_certification_by,
        )
        assert len(mock_notification_service_calls) == 1
        assert mock_notification_service_calls[0].kwargs["personalisation"] == expected_personalisation
        assert mock_notification_service_calls[0].kwargs["template_id"] == "791d1a61-c249-4752-9163-6cc81abf4ba9"
        assert mock_notification_service_calls[0].kwargs["email_address"] == "submitter@test.com"

    @responses.activate
    def test_send_access_submission_reopened(
        self,
        app,
        factories,
        submission_submitted,
        mock_notification_service_calls,
    ):
        grant_team_user = factories.user.build(name="Grant Team User")
        factories.submission_event.build(
            submission=submission_submitted,
            event_type=SubmissionEventType.SUBMISSION_REOPENED,
            created_by=grant_team_user,
            created_at_utc=datetime.datetime(2025, 12, 1, 9, 30, 0),
            data={"reopened_reason": "Reopen reason"},
        )
        helper = SubmissionHelper(submission_submitted)

        expected_personalisation = {
            "is_test_data": "no",
            "submission_name": "Test collection",
            "grant_name": "Test grant",
            "reopening_reason": "^ Reopen reason\n",
            "requires_certification": "yes",
            "grant_submission_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission_submitted.grant_recipient.organisation.id}/grants/{submission_submitted.grant_recipient.grant.id}/collection/{submission_submitted.collection.id}",
            "collection_type_noun": "report",
        }

        notification_service.send_access_submission_reopened(
            submission_helper=helper,
            user=helper.submitted_by,
        )
        assert len(mock_notification_service_calls) == 1
        assert mock_notification_service_calls[0].kwargs["personalisation"] == expected_personalisation
        assert mock_notification_service_calls[0].kwargs["template_id"] == "ad07a53a-d930-4cb3-ad57-595a1c104e61"
        assert mock_notification_service_calls[0].kwargs["email_address"] == "certifier@communities.gov.uk"

    @responses.activate
    def test_send_access_submission_reopened_reason_on_multiple_lines(
        self,
        app,
        factories,
        submission_submitted,
        mock_notification_service_calls,
    ):
        grant_team_user = factories.user.build(name="Grant Team User")
        factories.submission_event.build(
            submission=submission_submitted,
            event_type=SubmissionEventType.SUBMISSION_REOPENED,
            created_by=grant_team_user,
            created_at_utc=datetime.datetime(2025, 12, 1, 9, 30, 0),
            data={"reopened_reason": "Reopen reason\nOn\n\nMultiple lines"},
        )
        helper = SubmissionHelper(submission_submitted)

        expected_personalisation = {
            "is_test_data": "no",
            "submission_name": "Test collection",
            "grant_name": "Test grant",
            "reopening_reason": "^ Reopen reason\n^ On\n^ \n^ Multiple lines\n",
            "requires_certification": "yes",
            "grant_submission_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission_submitted.grant_recipient.organisation.id}/grants/{submission_submitted.grant_recipient.grant.id}/collection/{submission_submitted.collection.id}",
            "collection_type_noun": "report",
        }

        notification_service.send_access_submission_reopened(
            submission_helper=helper,
            user=helper.submitted_by,
        )
        assert len(mock_notification_service_calls) == 1
        assert mock_notification_service_calls[0].kwargs["personalisation"] == expected_personalisation
        assert mock_notification_service_calls[0].kwargs["template_id"] == "ad07a53a-d930-4cb3-ad57-595a1c104e61"
        assert mock_notification_service_calls[0].kwargs["email_address"] == "certifier@communities.gov.uk"

    @responses.activate
    def test_send_access_submission_reopened_fails_when_no_reason_provided(
        self,
        app,
        factories,
        submission_submitted,
        mock_notification_service_calls,
    ):
        grant_team_user = factories.user.build(name="Grant Team User")
        factories.submission_event.build(
            submission=submission_submitted,
            event_type=SubmissionEventType.SUBMISSION_REOPENED,
            created_by=grant_team_user,
            created_at_utc=datetime.datetime(2025, 12, 1, 9, 30, 0),
            data={"reopened_reason": None},
        )
        helper = SubmissionHelper(submission_submitted)

        with pytest.raises(ValueError, match="because there is no reopened reason"):
            notification_service.send_access_submission_reopened(
                submission_helper=helper,
                user=helper.submitted_by,
            )

    @responses.activate
    def test_send_changes_requested_submission(
        self,
        factories,
        submission_submitted,
        mock_notification_service_calls,
    ):
        grant_team_user = factories.user.build(name="Grant Team User")
        factories.submission_event.build(
            submission=submission_submitted,
            event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
            created_by=grant_team_user,
            created_at_utc=datetime.datetime(2025, 12, 1, 9, 30, 0),
            data={"changes_requested_reason": "Please fix this section"},
        )
        helper = SubmissionHelper(submission_submitted)

        expected_personalisation = {
            "is_test_data": "no",
            "submission_name": "Test collection",
            "grant_name": "Test grant",
            "changes_requested_reason": "^ Please fix this section\n",
            "requires_certification": "yes",
            "grant_submission_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission_submitted.grant_recipient.organisation.id}/grants/{submission_submitted.grant_recipient.grant.id}/collection/{submission_submitted.collection.id}",
            "government_department": f"the {submission_submitted.collection.grant.organisation.name}",
            "collection_type_noun": "report",
        }

        notification_service.send_changes_requested_submission(
            submission_helper=helper,
            user=helper.submitted_by,
        )
        assert len(mock_notification_service_calls) == 1
        assert mock_notification_service_calls[0].kwargs["personalisation"] == expected_personalisation
        assert mock_notification_service_calls[0].kwargs["template_id"] == "07c9df47-e33f-4d71-841c-673f1ca0d0a6"
        assert mock_notification_service_calls[0].kwargs["email_address"] == "certifier@communities.gov.uk"

    @responses.activate
    def test_send_changes_requested_submission_reason_on_multiple_lines(
        self,
        app,
        factories,
        submission_submitted,
        mock_notification_service_calls,
    ):
        grant_team_user = factories.user.build(name="Grant Team User")
        factories.submission_event.build(
            submission=submission_submitted,
            event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
            created_by=grant_team_user,
            created_at_utc=datetime.datetime(2025, 12, 1, 9, 30, 0),
            data={"changes_requested_reason": "Fix section 1\nAnd section 2"},
        )
        helper = SubmissionHelper(submission_submitted)

        notification_service.send_changes_requested_submission(
            submission_helper=helper,
            user=helper.submitted_by,
        )
        assert mock_notification_service_calls[0].kwargs["personalisation"]["changes_requested_reason"] == (
            "^ Fix section 1\n^ And section 2\n"
        )

    @responses.activate
    def test_send_changes_requested_submission_fails_when_no_reason_provided(
        self,
        app,
        factories,
        submission_submitted,
    ):
        grant_team_user = factories.user.build(name="Grant Team User")
        factories.submission_event.build(
            submission=submission_submitted,
            event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
            created_by=grant_team_user,
            created_at_utc=datetime.datetime(2025, 12, 1, 9, 30, 0),
            data={"changes_requested_reason": None},
        )
        helper = SubmissionHelper(submission_submitted)

        with pytest.raises(ValueError, match="because there is no changes requested reason"):
            notification_service.send_changes_requested_submission(
                submission_helper=helper,
                user=helper.submitted_by,
            )

    @responses.activate
    def test_send_submission_with_changes_notify_requester(
        self,
        factories,
        submission_submitted,
        mock_notification_service_calls,
    ):
        grant_team_user = factories.user.build(name="Grant Team User", email="grant.team@communities.gov.uk")
        factories.submission_event.build(
            submission=submission_submitted,
            event_type=SubmissionEventType.SUBMISSION_CHANGES_REQUESTED,
            created_by=grant_team_user,
            created_at_utc=datetime.datetime(2025, 12, 1, 9, 30, 0),
            data={"changes_requested_reason": "Please fix this section"},
        )
        helper = SubmissionHelper(submission_submitted)

        expected_personalisation = {
            "submission_name": "Test collection",
            "collection_type_noun": "report",
            "grant_name": "Test grant",
            "organisation_name": submission_submitted.grant_recipient.organisation.name,
            "submitter_name": helper.sent_for_certification_by.name,
            "requires_certification": "yes",
            "certifier_name": helper.certified_by.name,
            "date_submitted": format_datetime(helper.submitted_at_utc),
            "grant_submission_url": (
                f"http://funding.communities.gov.localhost:8080/deliver/grant/{submission_submitted.collection.grant.id}"
                f"/submission/{submission_submitted.id}"
            ),
        }

        notification_service.send_submission_with_changes_notify_requester(
            user=grant_team_user,
            submission_helper=helper,
        )
        assert len(mock_notification_service_calls) == 1
        assert mock_notification_service_calls[0].kwargs["personalisation"] == expected_personalisation
        assert mock_notification_service_calls[0].kwargs["template_id"] == "8ee3b678-d69f-4f50-bcc2-87dcd6ad4d43"
        assert mock_notification_service_calls[0].kwargs["email_address"] == "grant.team@communities.gov.uk"

    @responses.activate
    def test_send_access_submission_submitted_requires_certification(self, app, factories):
        grant_recipient = factories.grant_recipient.build(
            grant__name="Test grant",
        )
        submission = factories.submission.build(
            grant_recipient=grant_recipient,
            collection__grant=grant_recipient.grant,
            collection__requires_certification=True,
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
                            "organisation_name": submission.grant_recipient.organisation.name,
                            "reference": submission.reference,
                            "submitter_name": "Submitter User",
                            "certifier_name": "Certifier User",
                            "requires_certification": "yes",
                            "submission_name": "Test collection",
                            "date_submitted": "10:37am on Tuesday 25 November 2025",
                            "is_test_data": "no",
                            "grant_submission_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission.grant_recipient.organisation.id}/grants/{submission.grant_recipient.grant.id}/reports/{submission.id}/view",
                            "government_department": "the Test Organisation",
                            "collection_type_noun": "report",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_access_submission_submitted(
            email_address="test@communities.gov.uk",
            submission_helper=helper,
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    @responses.activate
    def test_send_access_submission_submitted_no_certification(self, app, factories):
        grant_recipient = factories.grant_recipient.build(
            grant__name="Test grant",
        )
        submission = factories.submission.build(
            grant_recipient=grant_recipient,
            collection__grant=grant_recipient.grant,
            collection__requires_certification=False,
            collection__name="Test collection",
            collection__reporting_period_start_date=datetime.date(2025, 10, 13),
            collection__reporting_period_end_date=datetime.date(2025, 10, 27),
            collection__submission_period_end_date=datetime.date(2025, 12, 30),
        )
        submitted_by_user = factories.user.build(name="Submitter User", email="submitter@communities.gov.uk")

        factories.submission_event.build(
            event_type=SubmissionEventType.SUBMISSION_SUBMITTED,
            submission=submission,
            created_by=submitted_by_user,
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
                        "email_address": "submitter@communities.gov.uk",
                        "template_id": "a8ffd584-0899-40df-ba56-cba95b2db0de",
                        "personalisation": {
                            "grant_name": "Test grant",
                            "organisation_name": submission.grant_recipient.organisation.name,
                            "reference": submission.reference,
                            "submitter_name": "Submitter User",
                            "certifier_name": "",
                            "requires_certification": "no",
                            "submission_name": "Test collection",
                            "is_test_data": "no",
                            "date_submitted": "10:37am on Tuesday 25 November 2025",
                            "grant_submission_url": f"http://funding.communities.gov.localhost:8080/access/organisation/{submission.grant_recipient.organisation.id}/grants/{submission.grant_recipient.grant.id}/reports/{submission.id}/view",
                            "government_department": "the Test Organisation",
                            "collection_type_noun": "report",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_access_submission_submitted(
            email_address="submitter@communities.gov.uk",
            submission_helper=helper,
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    @responses.activate
    def test_send_grant_export(self, app):
        export_json = '{"hello": "world"}'
        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": "dev@communities.gov.uk",
                        "template_id": "580db095-420e-4690-a640-c0ebd9748a0b",
                        "personalisation": {
                            "link_to_file": {
                                "file": "eyJoZWxsbyI6ICJ3b3JsZCJ9",
                                "filename": "grants.json",
                                "confirm_email_before_download": True,
                                "retention_period": None,
                            },
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_grant_export(
            "dev@communities.gov.uk",
            export_json=export_json,
            filename="grants.json",
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    def test_send_grant_export_rejects_external_email(self, app):
        with pytest.raises(ValueError, match="Cannot send grant export to external email address"):
            notification_service.send_grant_export(
                "external@gmail.com",
                export_json='{"hello": "world"}',
                filename="grants.json",
            )
