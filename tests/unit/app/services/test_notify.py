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
