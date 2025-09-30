"""Adding add_another column to component table

Revision ID: 006_add_another
Revises: 005_drop_dsir_table
Create Date: 2025-09-29 11:34:07.731125

"""

import sqlalchemy as sa
from alembic import op

revision = "006_add_another"
down_revision = "005_drop_dsir_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.add_column(sa.Column("add_another", sa.Boolean(), nullable=False, server_default=sa.text("false")))


def downgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_column("add_another")
