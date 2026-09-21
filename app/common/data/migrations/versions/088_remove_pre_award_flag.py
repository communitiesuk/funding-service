"""Remove pre-award feature flag from grant

Revision ID: 088_remove_pre_award_flag
Revises: 087_submission_visibility
Create Date: 2026-09-21 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "088_remove_pre_award_flag"
down_revision = "087_submission_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.drop_column("allow_pre_award")


def downgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.add_column(sa.Column("allow_pre_award", sa.Boolean(), nullable=False, server_default=sa.false()))
