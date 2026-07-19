"""Add allow validation column to collection table

Revision ID: 072_add_allow_validation_col
Revises: 071_add_release_notes
Create Date: 2026-07-19 00:47:04.366815

"""

import sqlalchemy as sa
from alembic import op

revision = "072_add_allow_validation_col"
down_revision = "071_add_release_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("allow_validation", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("allow_validation")
