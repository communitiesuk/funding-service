"""Configure allowing expression defaults

Revision ID: 062_empty_default_values
Revises: 061_pre_award_collections
Create Date: 2026-05-27 15:45:39.868494

"""

import sqlalchemy as sa
from alembic import op

revision = "062_empty_default_values"
down_revision = "061_pre_award_collections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("allow_empty_default_values", sa.Boolean(), nullable=False, server_default=sa.false())
        )


def downgrade() -> None:
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_column("allow_empty_default_values")
