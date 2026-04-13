"""Add allow_public_sign_up to collection

Revision ID: 054_allow_public_sign_up
Revises: 053_pre_award_flag
Create Date: 2026-04-09 15:17:40.054174

"""

import sqlalchemy as sa
from alembic import op

revision = "054_allow_public_sign_up"
down_revision = "053_pre_award_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("allow_public_sign_up", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("allow_public_sign_up")
