"""add access roles

Revision ID: 020_add_access_roles
Revises: 019_case_insensitive_component
Create Date: 2025-11-07 19:15:40.026361

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "020_add_access_roles"
down_revision = "019_case_insensitive_component"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="role_enum",
        new_values=["ADMIN", "MEMBER", "DATA_PROVIDER", "CERTIFIER"],
        affected_columns=[
            TableReference(table_schema="public", table_name="invitation", column_name="role"),
            TableReference(table_schema="public", table_name="user_role", column_name="role"),
        ],
        enum_values_to_rename=[],
    )
    op.create_check_constraint(
        op.f("ck_user_role_member_role_not_platform"),
        "user_role",
        "role != 'MEMBER' OR NOT (organisation_id IS NULL AND grant_id IS NULL)",
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="role_enum",
        new_values=["ADMIN", "MEMBER"],
        affected_columns=[
            TableReference(table_schema="public", table_name="invitation", column_name="role"),
            TableReference(table_schema="public", table_name="user_role", column_name="role"),
        ],
        enum_values_to_rename=[],
    )
    op.create_check_constraint(
        op.f("ck_user_role_member_role_not_platform"),
        "user_role",
        "role != 'MEMBER' OR NOT (organisation_id IS NULL AND grant_id IS NULL)",
    )
