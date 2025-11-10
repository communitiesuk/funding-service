"""remove role columns

Revision ID: 023_remove_role_columns
Revises: 022_make_role_nullable
Create Date: 2025-11-09 11:55:41.338973

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "023_remove_role_columns"
down_revision = "022_make_role_nullable"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.drop_column("role")

    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.drop_column("role")


def downgrade() -> None:
    with op.batch_alter_table("user_role", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "role",
                postgresql.ENUM("ADMIN", "MEMBER", "DATA_PROVIDER", "CERTIFIER", name="role_enum", create_type=False),
                autoincrement=False,
                nullable=True,
            )
        )

    with op.batch_alter_table("invitation", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "role",
                postgresql.ENUM("ADMIN", "MEMBER", "DATA_PROVIDER", "CERTIFIER", name="role_enum", create_type=False),
                autoincrement=False,
                nullable=True,
            )
        )
