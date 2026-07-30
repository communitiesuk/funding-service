"""Add allow submission reopening column to collection table

Revision ID: 075_allow_submission_reopening
Revises: 074_non_nullable_certification
Create Date: 2026-07-28 13:58:51.017374

"""

import sqlalchemy as sa
from alembic import op

revision = "075_allow_submission_reopening"
down_revision = "074_non_nullable_certification"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("allow_submission_reopening", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("allow_submission_reopening")
