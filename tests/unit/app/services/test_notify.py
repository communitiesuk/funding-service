import datetime
import uuid

import responses
from responses import matchers

from app import notification_service
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
                        "template_id": "9773e73c-85a1-4c3f-a808-02b9623616a3",
                        "personalisation": {
                            "magic_link": "https://magic-link",
                            "magic_link_expires_at": "1:00pm on 4 April 2025",
                            "request_new_magic_link": "https://new-magic-link",
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
    def test_send_collection_submission(self, app, factories):
        submission = factories.submission.build(
            id=uuid.UUID("10000000-0000-0000-0000-000000000000"),
            collection__name="My test collection",
        )
        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": submission.created_by.email,
                        "template_id": "2ff34065-0a75-4cc3-a782-1c00016e526e",
                        "personalisation": {
                            "submission name": "My test collection",
                            "submission reference": "10000000",
                            "submission url": "http://funding.communities.gov.localhost:8080/developers/submissions/10000000-0000-0000-0000-000000000000",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},  # partial GOV.UK Notify response
        )

        resp = notification_service.send_collection_submission(submission)
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1

    @responses.activate
    def test_send_member_confirmation(self, app, factories):
        grant_name = "This is a test grant name"
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
                            "grant_name": grant_name,
                            "sign_in_url": "http://funding.communities.gov.localhost:8080/sso/sign-in",
                        },
                    }
                )
            ],
            json={"id": "00000000-0000-0000-0000-000000000000"},
        )
        resp = notification_service.send_member_confirmation(
            grant_name=grant_name, email_address="test@communities.gov.uk"
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1
