"""add SUBMISSION_CHANGES_REQUESTED to submission_event_type_enum

Revision ID: 067_add_submission_changes_requested_event_t
Revises: 066_reminder_email_biz_days
Create Date: 2026-06-23 23:10:49.619507

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "068_changes_requested_event"
down_revision = "067_add_typed_external_id_cols"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="submission_event_type_enum",
        new_values=[
            "FORM_RUNNER_FORM_COMPLETED",
            "FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS",
            "FORM_RUNNER_FORM_RESET_BY_CERTIFIER",
            "SUBMISSION_SENT_FOR_CERTIFICATION",
            "SUBMISSION_DECLINED_BY_CERTIFIER",
            "SUBMISSION_APPROVED_BY_CERTIFIER",
            "SUBMISSION_SUBMITTED",
            "SUBMISSION_REOPENED",
            "SUBMISSION_CHANGES_REQUESTED",
        ],
        affected_columns=[
            TableReference(table_schema="public", table_name="submission_event", column_name="event_type")
        ],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="submission_event_type_enum",
        new_values=[
            "FORM_RUNNER_FORM_COMPLETED",
            "FORM_RUNNER_FORM_RESET_TO_IN_PROGRESS",
            "FORM_RUNNER_FORM_RESET_BY_CERTIFIER",
            "SUBMISSION_SENT_FOR_CERTIFICATION",
            "SUBMISSION_DECLINED_BY_CERTIFIER",
            "SUBMISSION_APPROVED_BY_CERTIFIER",
            "SUBMISSION_SUBMITTED",
            "SUBMISSION_REOPENED",
        ],
        affected_columns=[
            TableReference(table_schema="public", table_name="submission_event", column_name="event_type")
        ],
        enum_values_to_rename=[],
    )
