"""Pre award feature flag

Revision ID: 053_pre_award_flag
Revises: 052_other_org
Create Date: 2026-04-10 12:27:20.333508

"""

import sqlalchemy as sa
from alembic import op

revision = "053_pre_award_flag"
down_revision = "052_other_org"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.add_column(sa.Column("allow_pre_award", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.drop_column("allow_pre_award")
