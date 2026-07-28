"""Add the rolling submissions collection setting

Revision ID: 074_rolling_submissions
Revises: 073_eligibility_checks
Create Date: 2026-07-28 23:19:34.232472

"""

import sqlalchemy as sa
from alembic import op

revision = "074_rolling_submissions"
down_revision = "073_eligibility_checks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("allow_rolling_submissions", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("allow_rolling_submissions")
