import uuid

import pytest
import responses
from responses import matchers

from app.services.notify import Notification, get_notification_service


class TestNotificationService:
    """
    Test that the methods we've written for sending emails using the GOV.UK Notify Python SDK map to the expected
    HTTP API calls.
    """

    @pytest.mark.skip(reason="reference implement - to be adjusted")
    @responses.activate
    def test_send_magic_link(self, app):
        request_matcher = responses.post(
            url="https://api.notifications.service.gov.uk/v2/notifications/email",
            status=201,
            match=[
                matchers.json_params_matcher(
                    {
                        "email_address": "test@test.com",
                        "template_id": "02a6d48a-f227-4b9a-9dd7-9e0cf203c8a2",
                        "personalisation": {
                            "name of fund": "test fund",
                            "link to application": "https://magic-link",
                            "contact details": "contact@test.com",
                            "request new link url": "https://new-magic-link",
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
            "test fund",
            "contact@test.com",
            "https://new-magic-link",
            "abc123",
        )
        assert resp == Notification(id=uuid.UUID("00000000-0000-0000-0000-000000000000"))
        assert request_matcher.call_count == 1
