"""sync role enum for changed values

Revision ID: 011_sync_role_enum
Revises: 010_expression_managed_name
Create Date: 2025-06-28 12:44:36.920129

"""

from alembic import op
from alembic_postgresql_enum import TableReference
from sqlalchemy import text

revision = "011_sync_role_enum"
down_revision = "010_expression_managed_name"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(text("DELETE FROM user_role WHERE role IN ('EDITOR', 'ASSESSOR', 'S151_OFFICER')"))

    # WARNING: this also deletes the check constraints touching the enum, so we need to regenerate the ones we want
    #           to keep afterwards.
    op.sync_enum_values(
        enum_schema="public",
        enum_name="role_enum",
        new_values=["ADMIN", "MEMBER"],
        affected_columns=[TableReference(table_schema="public", table_name="user_role", column_name="role")],
        enum_values_to_rename=[],
    )

    op.create_check_constraint(
        "member_role_not_platform",
        "user_role",
        "role != 'MEMBER' OR NOT (organisation_id IS NULL AND grant_id IS NULL)",
    )


def downgrade() -> None:
    op.sync_enum_values(
        enum_schema="public",
        enum_name="role_enum",
        new_values=["ADMIN", "MEMBER", "EDITOR", "ASSESSOR", "S151_OFFICER"],
        affected_columns=[TableReference(table_schema="public", table_name="user_role", column_name="role")],
        enum_values_to_rename=[],
    )

    op.create_check_constraint(
        "assessor_role_grant_only",
        "user_role",
        "role != 'ASSESSOR' OR (organisation_id IS NULL AND grant_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "member_role_not_platform",
        "user_role",
        "role != 'MEMBER' OR NOT (organisation_id IS NULL AND grant_id IS NULL)",
    )
    op.create_check_constraint(
        "s151_officer_role_org_only",
        "user_role",
        "role != 'S151_OFFICER' OR (organisation_id IS NOT NULL AND grant_id IS NULL)",
    )
