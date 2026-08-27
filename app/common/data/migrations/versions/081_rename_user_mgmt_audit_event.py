"""Rename the Access grant funding user management audit event type now it covers all user permission changes

Revision ID: 081_rename_user_mgmt_audit_event
Revises: 080_add_eligibility_section
Create Date: 2026-08-25 15:52:34.402195

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "081_rename_user_mgmt_audit_event"
down_revision = "080_add_eligibility_section"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="auditeventtype",
        new_values=["PLATFORM_ADMIN_DB_EVENT", "SYSTEM", "USER_MANAGEMENT"],
        affected_columns=[TableReference(table_schema="public", table_name="audit_event", column_name="event_type")],
        enum_values_to_rename=[("ACCESS_GRANT_FUNDING_USER_MANAGEMENT", "USER_MANAGEMENT")],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="auditeventtype",
        new_values=["PLATFORM_ADMIN_DB_EVENT", "SYSTEM", "ACCESS_GRANT_FUNDING_USER_MANAGEMENT"],
        affected_columns=[TableReference(table_schema="public", table_name="audit_event", column_name="event_type")],
        enum_values_to_rename=[("USER_MANAGEMENT", "ACCESS_GRANT_FUNDING_USER_MANAGEMENT")],
    )
