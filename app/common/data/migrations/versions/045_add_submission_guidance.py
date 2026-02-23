"""add submission guidance to collections

Revision ID: 045_add_submission_guidance
Revises: 044_add_multi_submission_sett
Create Date: 2026-02-19 19:22:19.729985

"""

import sqlalchemy as sa
from alembic import op

revision = "045_add_submission_guidance"
down_revision = "044_add_multi_submission_sett"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("submission_guidance", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("submission_guidance")
