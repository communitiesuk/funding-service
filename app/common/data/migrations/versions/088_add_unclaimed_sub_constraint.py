"""add unique constraint for unclaimed submissions

Revision ID: 088_add_unclaimed_sub_constraint
Revises: 087_submission_visibility
Create Date: 2026-09-16 00:51:26.956371

"""

import sqlalchemy as sa
from alembic import op

revision = "088_add_unclaimed_sub_constraint"
down_revision = "087_submission_visibility"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.create_index(
            "uq_submission_unclaimed_created_by_collection_mode",
            ["created_by_id", "collection_id", "mode"],
            unique=True,
            postgresql_where=sa.text("grant_recipient_id IS NULL"),
        )


def downgrade() -> None:
    with op.batch_alter_table("submission", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_submission_unclaimed_created_by_collection_mode", postgresql_where=sa.text("grant_recipient_id IS NULL")
        )
