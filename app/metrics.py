from enum import StrEnum
from typing import TYPE_CHECKING, Mapping, Optional
from uuid import UUID

from sentry_sdk import metrics

from app.common.expressions.managed import ManagedExpression

if TYPE_CHECKING:
    from app.common.data.models import Collection, Grant, GrantRecipient, Submission


class MetricAttributeName(StrEnum):
    GRANT_RECIPIENT = "grant-recipient"
    GRANT_RECIPIENT_ID = "grant-recipient-id"
    GRANT = "grant"
    GRANT_ID = "grant-id"
    COLLECTION = "collection"
    COLLECTION_ID = "collection-id"
    COLLECTION_TYPE = "collection-type"
    SUBMISSION = "submission"
    SUBMISSION_ID = "submission-id"
    SUBMISSION_MODE = "submission-mode"
    USER_ID = "user-id"

    MANAGED_EXPRESSION_NAME = "managed-expression-name"


class MetricEventName(StrEnum):
    SECTION_MARKED_COMPLETE = "section-marked-as-complete"
    SECTION_MARKED_INCOMPLETE = "section-marked-as-incomplete"
    SECTION_RESET_TO_IN_PROGRESS = "section-reset-to-in-progress"

    SUBMISSION_CREATED = "submission-created"
    SUBMISSION_SENT_FOR_CERTIFICATION = "submission-sent-for-certification"
    SUBMISSION_CERTIFIED = "submission-certified"
    SUBMISSION_CERTIFICATION_DECLINED = "submission-certification-declined"
    SUBMISSION_SUBMITTED = "submission-submitted"

    SUBMISSION_MANAGED_VALIDATION_ERROR = "submission-managed-validation-error"
    SUBMISSION_MANAGED_VALIDATION_SUCCESS = "submission-managed-validation-success"


def _get_event_attributes(
    grant_recipient: Optional["GrantRecipient"] = None,
    submission: Optional["Submission"] = None,
    collection: Optional["Collection"] = None,
    grant: Optional["Grant"] = None,
    managed_expression: Optional["ManagedExpression"] = None,
    custom_attributes: Mapping[MetricAttributeName, str | int | UUID] | None = None,
) -> dict[str, str | int | UUID]:
    attributes: dict[str, str | int | UUID] = (
        {str(k): v for k, v in custom_attributes.items()} if custom_attributes else {}
    )

    if submission:
        attributes[str(MetricAttributeName.SUBMISSION_ID)] = submission.id
        attributes[str(MetricAttributeName.SUBMISSION_MODE)] = str(submission.mode)

        if not collection:
            collection = submission.collection

        if not grant_recipient:
            grant_recipient = submission.grant_recipient

    if collection:
        attributes[str(MetricAttributeName.COLLECTION)] = collection.name
        attributes[str(MetricAttributeName.COLLECTION_ID)] = str(collection.id)
        attributes[str(MetricAttributeName.COLLECTION_TYPE)] = str(collection.type)

        if not grant:
            grant = collection.grant

    if grant_recipient:
        attributes[str(MetricAttributeName.GRANT_RECIPIENT)] = grant_recipient.organisation.name
        attributes[str(MetricAttributeName.GRANT_RECIPIENT_ID)] = str(grant_recipient.id)

        if not grant:
            grant = grant_recipient.grant

    if grant:
        attributes[str(MetricAttributeName.GRANT)] = grant.name
        attributes[str(MetricAttributeName.GRANT_ID)] = str(grant.id)

    if managed_expression:
        attributes[str(MetricAttributeName.MANAGED_EXPRESSION_NAME)] = managed_expression.name

    return attributes


def emit_metric_count(
    event: MetricEventName,
    count: int = 1,
    grant_recipient: Optional["GrantRecipient"] = None,
    submission: Optional["Submission"] = None,
    collection: Optional["Collection"] = None,
    grant: Optional["Grant"] = None,
    managed_expression: Optional["ManagedExpression"] = None,
    custom_attributes: Mapping[MetricAttributeName, str | int | UUID] | None = None,
) -> None:
    # TODO: emit as structured log for longer retention

    metrics.count(
        event,
        count,
        attributes=_get_event_attributes(
            grant_recipient=grant_recipient,
            submission=submission,
            collection=collection,
            grant=grant,
            managed_expression=managed_expression,
            custom_attributes=custom_attributes,
        ),
    )
