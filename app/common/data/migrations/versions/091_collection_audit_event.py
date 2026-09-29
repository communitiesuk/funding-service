"""empty message

Revision ID: 091_collection_audit_event
Revises: 090_add_unclaimed_sub_constraint
Create Date: 2026-09-29 10:35:53.246954

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "091_collection_audit_event"
down_revision = "090_add_unclaimed_sub_constraint"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="auditeventtype",
        new_values=["PLATFORM_ADMIN_DB_EVENT", "SYSTEM", "USER_MANAGEMENT", "COLLECTION_CONFIGURATION"],
        affected_columns=[TableReference(table_schema="public", table_name="audit_event", column_name="event_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="auditeventtype",
        new_values=["PLATFORM_ADMIN_DB_EVENT", "SYSTEM", "USER_MANAGEMENT"],
        affected_columns=[TableReference(table_schema="public", table_name="audit_event", column_name="event_type")],
        enum_values_to_rename=[],
    )
