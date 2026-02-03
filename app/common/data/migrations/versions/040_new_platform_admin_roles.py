"""add grant lifecycle manager and data analyst roles for platform admin

Revision ID: 040_new_platform_admin_roles
Revises: 039_remove_integer_data_type
Create Date: 2026-02-03 11:09:58.122316

"""

from alembic import op
from alembic_postgresql_enum import ColumnType, TableReference

revision = "040_new_platform_admin_roles"
down_revision = "039_remove_integer_data_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Drop existing CHECK constraints that reference the permissions column before
    # sync_enum_values. The sync renames role_enum -> role_enum_old and creates a new
    # role_enum; PostgreSQL cannot re-validate constraints that compare role_enum_old
    # values against the new role_enum type during ALTER COLUMN.
    with op.batch_alter_table("invitation") as batch_op:
        batch_op.drop_constraint(op.f("ck_invitation_non_admin_permissions_require_org"), type_="check")
        batch_op.drop_constraint(op.f("ck_invitation_member_permission_required"), type_="check")
    with op.batch_alter_table("user_role") as batch_op:
        batch_op.drop_constraint(op.f("ck_user_role_non_admin_permissions_require_org"), type_="check")
        batch_op.drop_constraint(op.f("ck_user_role_member_permission_required"), type_="check")

    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="role_enum",
        new_values=["ADMIN", "MEMBER", "DATA_PROVIDER", "CERTIFIER", "GRANT_LIFECYCLE_MANAGER", "DATA_ANALYST"],
        affected_columns=[
            TableReference(
                table_schema="public", table_name="invitation", column_name="permissions", column_type=ColumnType.ARRAY
            ),
            TableReference(
                table_schema="public", table_name="user_role", column_name="permissions", column_type=ColumnType.ARRAY
            ),
        ],
        enum_values_to_rename=[],
    )

    # Recreate the dropped constraints and add the new one
    with op.batch_alter_table("invitation") as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_invitation_non_admin_permissions_require_org"),
            "('CERTIFIER' != ALL(permissions) AND 'DATA_PROVIDER' != ALL(permissions)) OR organisation_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            op.f("ck_invitation_member_permission_required"),
            "'MEMBER' = ANY(permissions)",
        )
        batch_op.create_check_constraint(
            op.f("ck_platform_admin_permission_scope"),
            (
                "('DATA_ANALYST' != ALL(permissions) AND 'GRANT_LIFECYCLE_MANAGER' != ALL(permissions)) "
                "OR (organisation_id IS NULL AND grant_id IS NULL)"
            ),
        )

    with op.batch_alter_table("user_role") as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_user_role_non_admin_permissions_require_org"),
            "('CERTIFIER' != ALL(permissions) AND 'DATA_PROVIDER' != ALL(permissions)) OR organisation_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            op.f("ck_user_role_member_permission_required"),
            "'MEMBER' = ANY(permissions)",
        )
        batch_op.create_check_constraint(
            op.f("ck_platform_admin_permission_scope"),
            (
                "('DATA_ANALYST' != ALL(permissions) AND 'GRANT_LIFECYCLE_MANAGER' != ALL(permissions)) "
                "OR (organisation_id IS NULL AND grant_id IS NULL)"
            ),
        )


def downgrade() -> None:
    with op.batch_alter_table("invitation") as batch_op:
        batch_op.drop_constraint(op.f("ck_invitation_non_admin_permissions_require_org"), type_="check")
        batch_op.drop_constraint(op.f("ck_invitation_member_permission_required"), type_="check")
        batch_op.drop_constraint(op.f("ck_platform_admin_permission_scope"), type_="check")

    with op.batch_alter_table("user_role") as batch_op:
        batch_op.drop_constraint(op.f("ck_user_role_non_admin_permissions_require_org"), type_="check")
        batch_op.drop_constraint(op.f("ck_user_role_member_permission_required"), type_="check")
        batch_op.drop_constraint(op.f("ck_platform_admin_permission_scope"), type_="check")

    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="role_enum",
        new_values=["ADMIN", "MEMBER", "DATA_PROVIDER", "CERTIFIER"],
        affected_columns=[
            TableReference(
                table_schema="public", table_name="invitation", column_name="permissions", column_type=ColumnType.ARRAY
            ),
            TableReference(
                table_schema="public", table_name="user_role", column_name="permissions", column_type=ColumnType.ARRAY
            ),
        ],
        enum_values_to_rename=[],
    )

    with op.batch_alter_table("invitation") as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_invitation_non_admin_permissions_require_org"),
            "('CERTIFIER' != ALL(permissions) AND 'DATA_PROVIDER' != ALL(permissions)) OR organisation_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            op.f("ck_invitation_member_permission_required"),
            "'MEMBER' = ANY(permissions)",
        )
    with op.batch_alter_table("user_role") as batch_op:
        batch_op.create_check_constraint(
            op.f("ck_user_role_non_admin_permissions_require_org"),
            "('CERTIFIER' != ALL(permissions) AND 'DATA_PROVIDER' != ALL(permissions)) OR organisation_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            op.f("ck_user_role_member_permission_required"),
            "'MEMBER' = ANY(permissions)",
        )
