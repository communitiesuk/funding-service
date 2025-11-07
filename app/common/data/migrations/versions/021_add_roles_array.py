"""add permissions array

Revision ID: 021_add_permissions_array
Revises: 020_add_access_roles
Create Date: 2025-11-07 20:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "021_add_permissions_array"
down_revision = "020_add_access_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "permissions",
                postgresql.ARRAY(
                    postgresql.ENUM(
                        "ADMIN", "MEMBER", "DATA_PROVIDER", "CERTIFIER", name="role_enum", create_type=False
                    )
                ),
                nullable=True,
            )
        )
    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "permissions",
                postgresql.ARRAY(
                    postgresql.ENUM(
                        "ADMIN", "MEMBER", "DATA_PROVIDER", "CERTIFIER", name="role_enum", create_type=False
                    )
                ),
                nullable=True,
            )
        )

    op.execute("UPDATE user_role SET permissions = ARRAY[role]")
    op.execute("UPDATE invitation SET permissions = ARRAY[role]")

    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.alter_column("permissions", existing_nullable=True, nullable=False)
        batch_op.create_check_constraint(
            op.f("ck_user_role_member_role_not_in_permissions_requires_org"),
            "'MEMBER' != ALL(permissions) OR organisation_id IS NOT NULL",
        )
    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.alter_column("permissions", existing_nullable=True, nullable=False)
        batch_op.create_check_constraint(
            op.f("ck_invitation_member_role_not_in_invitation_permissions_requires_org"),
            "'MEMBER' != ALL(permissions) OR organisation_id IS NOT NULL",
        )


def downgrade() -> None:
    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.drop_constraint(
            op.f("ck_invitation_member_role_not_in_invitation_permissions_requires_org"), type_="check"
        )
        batch_op.drop_column("permissions")
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_user_role_member_role_not_in_permissions_requires_org"), type_="check")
        batch_op.drop_column("permissions")
