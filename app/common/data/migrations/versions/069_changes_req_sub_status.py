"""add CHANGES_REQUESTED and SUBMITTED_WITH_CHANGES to submission_status_enum

Revision ID: 069_changes_req_sub_status
Revises: 068_changes_requested_event
Create Date: 2026-06-27 18:43:59.766835

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "069_changes_req_sub_status"
down_revision = "068_changes_requested_event"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="submission_status_enum",
        new_values=[
            "NOT_STARTED",
            "IN_PROGRESS",
            "READY_TO_SUBMIT",
            "AWAITING_SIGN_OFF",
            "SUBMITTED",
            "NOT_SUBMITTED",
            "PARTIALLY_SUBMITTED",
            "CHANGES_REQUESTED",
            "SUBMITTED_WITH_CHANGES",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="submission", column_name="status")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="submission_status_enum",
        new_values=[
            "NOT_STARTED",
            "IN_PROGRESS",
            "READY_TO_SUBMIT",
            "AWAITING_SIGN_OFF",
            "SUBMITTED",
            "NOT_SUBMITTED",
            "PARTIALLY_SUBMITTED",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="submission", column_name="status")],
        enum_values_to_rename=[],
    )
