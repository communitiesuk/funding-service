from unittest.mock import Mock, patch
from uuid import uuid4

from app.metrics import MetricAttributeName, MetricEventName, emit_metric_count


class TestEmitMetricCount:
    @patch("app.metrics.metrics.count")
    def test_basic_emission_with_no_attributes(self, mock_count):
        emit_metric_count(MetricEventName.SUBMISSION_CREATED)

        mock_count.assert_called_once_with(
            MetricEventName.SUBMISSION_CREATED,
            1,
            attributes={},
        )

    @patch("app.metrics.metrics.count")
    def test_emission_with_custom_count(self, mock_count):
        emit_metric_count(MetricEventName.SUBMISSION_MANAGED_VALIDATION_ERROR, count=5)

        mock_count.assert_called_once_with(
            MetricEventName.SUBMISSION_MANAGED_VALIDATION_ERROR,
            5,
            attributes={},
        )

    @patch("app.metrics.metrics.count")
    def test_emission_with_custom_attributes(self, mock_count):
        user_id = uuid4()
        custom_attrs = {
            MetricAttributeName.USER_ID: str(user_id),
        }

        emit_metric_count(
            MetricEventName.SECTION_MARKED_COMPLETE,
            custom_attributes=custom_attrs,
        )

        mock_count.assert_called_once_with(
            MetricEventName.SECTION_MARKED_COMPLETE,
            1,
            attributes={
                "user-id": str(user_id),
            },
        )

    @patch("app.metrics.metrics.count")
    def test_emission_with_grant(self, mock_count, factories):
        grant = factories.grant.build(name="Test Grant")

        emit_metric_count(MetricEventName.SUBMISSION_CREATED, grant=grant)

        mock_count.assert_called_once_with(
            MetricEventName.SUBMISSION_CREATED,
            1,
            attributes={
                "grant": "Test Grant",
                "grant-id": str(grant.id),
            },
        )

    @patch("app.metrics.metrics.count")
    def test_emission_with_collection(self, mock_count, factories):
        collection = factories.collection.build(name="Monthly Report", grant__name="Parent Grant")

        emit_metric_count(MetricEventName.SUBMISSION_CREATED, collection=collection)

        mock_count.assert_called_once_with(
            MetricEventName.SUBMISSION_CREATED,
            1,
            attributes={
                "collection": "Monthly Report",
                "collection-id": str(collection.id),
                "collection-type": "monitoring report",
                "grant": "Parent Grant",
                "grant-id": str(collection.grant.id),
            },
        )

    @patch("app.metrics.metrics.count")
    def test_emission_with_grant_recipient(self, mock_count, factories):
        grant_recipient = factories.grant_recipient.build(
            organisation__name="Test Organisation", grant__name="Test Grant"
        )

        emit_metric_count(MetricEventName.SUBMISSION_CREATED, grant_recipient=grant_recipient)

        mock_count.assert_called_once_with(
            MetricEventName.SUBMISSION_CREATED,
            1,
            attributes={
                "grant-recipient": "Test Organisation",
                "grant-recipient-id": str(grant_recipient.id),
                "grant-recipient-mode": "live",
                "grant": "Test Grant",
                "grant-id": str(grant_recipient.grant.id),
            },
        )

    @patch("app.metrics.metrics.count")
    def test_emission_with_submission(self, mock_count, factories):
        grant_recipient = factories.grant_recipient.build(
            organisation__name="Test Organisation", grant__name="Test Grant"
        )
        submission = factories.submission.build(
            collection__name="Monthly Report", collection__grant=grant_recipient.grant, grant_recipient=grant_recipient
        )

        emit_metric_count(MetricEventName.SUBMISSION_SUBMITTED, submission=submission)

        mock_count.assert_called_once_with(
            MetricEventName.SUBMISSION_SUBMITTED,
            1,
            attributes={
                "submission-id": submission.id,
                "submission-mode": "preview",
                "collection": "Monthly Report",
                "collection-id": str(submission.collection.id),
                "collection-type": "monitoring report",
                "grant": "Test Grant",
                "grant-id": str(submission.collection.grant.id),
                "grant-recipient": "Test Organisation",
                "grant-recipient-id": str(submission.grant_recipient.id),
                "grant-recipient-mode": "live",
            },
        )

    @patch("app.metrics.metrics.count")
    def test_emission_with_managed_expression(self, mock_count):
        managed_expression = Mock()
        managed_expression.name = "TestExpression"

        emit_metric_count(
            MetricEventName.SUBMISSION_MANAGED_VALIDATION_ERROR,
            managed_expression=managed_expression,
        )

        mock_count.assert_called_once_with(
            MetricEventName.SUBMISSION_MANAGED_VALIDATION_ERROR,
            1,
            attributes={
                "managed-expression-name": "TestExpression",
            },
        )

    @patch("app.metrics.metrics.count")
    def test_explicit_grant_overrides_collection_grant(self, mock_count, factories):
        grant = factories.grant.build(name="Explicit Grant")
        collection = factories.collection.build(name="Monthly Report", grant__name="Parent Grant")

        emit_metric_count(
            MetricEventName.SUBMISSION_CREATED,
            collection=collection,
            grant=grant,
        )

        mock_count.assert_called_once_with(
            MetricEventName.SUBMISSION_CREATED,
            1,
            attributes={
                "collection": "Monthly Report",
                "collection-id": str(collection.id),
                "collection-type": "monitoring report",
                "grant": "Explicit Grant",
                "grant-id": str(grant.id),
            },
        )

    @patch("app.metrics.metrics.count")
    def test_custom_attributes_combined_with_model_attributes(self, mock_count, factories):
        grant = factories.grant.build(name="Test Grant")

        custom_attrs = {
            MetricAttributeName.USER_ID: "user-123",
        }

        emit_metric_count(
            MetricEventName.SUBMISSION_CREATED,
            grant=grant,
            custom_attributes=custom_attrs,
        )

        mock_count.assert_called_once_with(
            MetricEventName.SUBMISSION_CREATED,
            1,
            attributes={
                "user-id": "user-123",
                "grant": "Test Grant",
                "grant-id": str(grant.id),
            },
        )
