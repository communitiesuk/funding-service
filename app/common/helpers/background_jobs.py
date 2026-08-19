from app.common.data.interfaces.background_jobs import (
    SendCollectionOpenNotificationEmailsJob,
    mark_collection_open_notification_emails_sent,
)
from app.common.data.interfaces.collections import get_collection
from app.common.data.interfaces.grant_recipients import get_grant_recipients
from app.common.helpers.collections import SubmissionHelper
from app.extensions import notification_service


def send_collection_open_notification_emails(job: SendCollectionOpenNotificationEmailsJob) -> int:
    collection = get_collection(job.collection_id)
    grant_recipients = get_grant_recipients(
        grant=collection.grant,
        with_data_providers=True,
        with_organisations=True,
    )

    sent_count = 0
    for grant_recipient in grant_recipients:
        submissions = [
            SubmissionHelper(submission)
            for submission in grant_recipient.submissions
            if submission.collection_id == collection.id
        ]

        for data_provider in grant_recipient.data_providers:
            notification_service.send_access_report_opened(
                data_provider.email,
                collection=collection,
                grant_recipient=grant_recipient,
                submission_helpers=submissions,
            )
            sent_count += 1

    mark_collection_open_notification_emails_sent(job)
    return sent_count
