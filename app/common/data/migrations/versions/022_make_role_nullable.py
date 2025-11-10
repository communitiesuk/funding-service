"""make role columns nullable

Revision ID: 022_make_role_nullable
Revises: 021_add_permissions_array
Create Date: 2025-11-09 11:00:00.000000

"""

from alembic import op

revision = "022_make_role_nullable"
down_revision = "021_add_permissions_array"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_constraint(op.f("ck_user_role_member_role_not_platform"), type_="check")
        batch_op.alter_column("role", existing_nullable=False, nullable=True)

    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.alter_column("role", existing_nullable=False, nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.alter_column("role", existing_nullable=True, nullable=False)

    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.alter_column("role", existing_nullable=True, nullable=False)
        batch_op.create_check_constraint(
            op.f("ck_user_role_member_role_not_platform"),
            "role != 'MEMBER' OR organisation_id IS NOT NULL",
        )
