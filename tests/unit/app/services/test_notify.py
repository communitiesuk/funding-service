import datetime
import uuid

import responses
from responses import matchers

from app.services.notify import Notification, get_notification_service


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
                        "template_id": "c19811c2-dc4a-4504-99b5-7bcbae8d9659",
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

        resp = get_notification_service().send_magic_link(
            "test@test.com",
            "https://magic-link",
            # Timestamp is in UTC; `send_magic_link` will convert to Europe/London local time
            datetime.datetime.fromisoformat("2025-04-04T12:00:00+00:00"),
            "https://new-magic-link",
            "abc123",
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1
