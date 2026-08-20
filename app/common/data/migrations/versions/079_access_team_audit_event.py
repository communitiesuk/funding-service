"""Update audit events to track user permission changes by Access grant funding users

Revision ID: 079_access_team_audit_event
Revises: 078_add_collection_id_magic_link
Create Date: 2026-08-20 11:37:27.767738

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "079_access_team_audit_event"
down_revision = "078_add_collection_id_magic_link"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="auditeventtype",
        new_values=["PLATFORM_ADMIN_DB_EVENT", "SYSTEM", "ACCESS_GRANT_FUNDING_USER_MANAGEMENT"],
        affected_columns=[TableReference(table_schema="public", table_name="audit_event", column_name="event_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="auditeventtype",
        new_values=["PLATFORM_ADMIN_DB_EVENT", "SYSTEM"],
        affected_columns=[TableReference(table_schema="public", table_name="audit_event", column_name="event_type")],
        enum_values_to_rename=[],
    )
