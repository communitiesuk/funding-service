"""Submission status awaiting sign off

Revision ID: 025_awaiting_sign_off_status
Revises: 024_sync_managed_expression_enum
Create Date: 2025-11-18 17:30:27.391808

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "025_awaiting_sign_off_status"
down_revision = "024_sync_managed_expression_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="submission_event_key_enum",
        new_values=[
            "FORM_RUNNER_FORM_COMPLETED",
            "SUBMISSION_SENT_FOR_CERTIFICATION",
            "SUBMISSION_SUBMITTED",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="submission_event", column_name="key")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="submission_event_key_enum",
        new_values=["FORM_RUNNER_FORM_COMPLETED", "SUBMISSION_SUBMITTED"],
        affected_columns=[TableReference(table_schema="public", table_name="submission_event", column_name="key")],
        enum_values_to_rename=[],
    )
