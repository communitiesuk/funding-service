"""Add system-notification-failure-cleanup audit event type.

Revision ID: 060_notify_cleanup_audit_event
Revises: 059_reopen_submission
Create Date: 2026-05-12 11:08:45.815081

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "060_notify_cleanup_audit_event"
down_revision = "059_reopen_submission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="auditeventtype",
        new_values=["PLATFORM_ADMIN_DB_EVENT", "SYSTEM"],
        affected_columns=[TableReference(table_schema="public", table_name="audit_event", column_name="event_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="auditeventtype",
        new_values=["PLATFORM_ADMIN_DB_EVENT"],
        affected_columns=[TableReference(table_schema="public", table_name="audit_event", column_name="event_type")],
        enum_values_to_rename=[],
    )
