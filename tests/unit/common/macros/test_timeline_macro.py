from datetime import datetime

import pytest
from bs4 import BeautifulSoup
from flask import render_template_string

from app.common.data.types import CollectionType, SubmissionEventType, SubmissionModeEnum
from app.common.helpers.timeline import from_submission_event

GRANT_ORG = "MHCLG"
RECIPIENT_ORG = "Recipient Council"


@pytest.mark.parametrize(
    "event_type, expected_title, expected_recipient_org",
    [
        (SubmissionEventType.FORM_RUNNER_FORM_COMPLETED, "section completed", RECIPIENT_ORG),
        (SubmissionEventType.FORM_RUNNER_FORM_RESET_BY_CERTIFIER, "section reset by certifier", RECIPIENT_ORG),
        (SubmissionEventType.FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS, 'section reset to "In Progress"', RECIPIENT_ORG),
        (SubmissionEventType.SUBMISSION_APPROVED_BY_CERTIFIER, "signed off and submitted by certifier", RECIPIENT_ORG),
        (SubmissionEventType.SUBMISSION_DECLINED_BY_CERTIFIER, "declined by certifier", RECIPIENT_ORG),
        (SubmissionEventType.SUBMISSION_REOPENED, "reopened for changes", GRANT_ORG),
        (SubmissionEventType.SUBMISSION_SENT_FOR_CERTIFICATION, "completed and sent for certification", RECIPIENT_ORG),
        (SubmissionEventType.SUBMISSION_SUBMITTED, f"submitted to {GRANT_ORG}", RECIPIENT_ORG),
    ],
)
class TestTimelinePartials:
    def test_partial_title_byline_time(self, factories, event_type, expected_title, expected_recipient_org):
        grant = factories.grant.build(
            organisation=factories.organisation.build(name=GRANT_ORG, can_manage_grants=True),
        )
        grant_recipient = factories.grant_recipient.build(
            grant=grant,
            organisation__name=RECIPIENT_ORG,
        )
        submission = factories.submission.build(
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient,
            collection=factories.collection.build(grant=grant, type=CollectionType.MONITORING_REPORT),
        )
        event = factories.submission_event.build(
            event_type=event_type,
            submission=submission,
            created_at_utc=datetime(2025, 6, 15, 10, 30, 0),
        )

        item = from_submission_event(event)
        template = f"common/macros/timeline/{event_type.name.lower()}.html"

        html = BeautifulSoup(
            render_template_string(f'{{% include "{template}" %}}', item=item),
            "html.parser",
        )

        assert expected_title in html.find("h2").text
        assert expected_recipient_org in html.find("p", class_="moj-timeline__byline").text
        assert html.find("time") is not None


class TestSubmissionDetails:
    def test_shows_reopened_reason(self, factories):
        grant = factories.grant.build(
            organisation=factories.organisation.build(name=GRANT_ORG, can_manage_grants=True),
        )
        grant_recipient = factories.grant_recipient.build(grant=grant, organisation__name=RECIPIENT_ORG)
        submission = factories.submission.build(
            mode=SubmissionModeEnum.LIVE,
            grant_recipient=grant_recipient,
            collection=factories.collection.build(grant=grant),
        )
        event = factories.submission_event.build(
            event_type=SubmissionEventType.SUBMISSION_REOPENED,
            submission=submission,
            data={"reopened_reason": "Please update the submission"},
        )

        item = from_submission_event(event)

        html = BeautifulSoup(
            render_template_string(
                '{% include "common/macros/timeline/submission_reopened.html" %}',
                item=item,
            ),
            "html.parser",
        )

        assert "Reason for reopening" in html.find("span", class_="govuk-details__summary-text").text
        assert "Please update the submission" in html.find("div", class_="govuk-details__text").text
