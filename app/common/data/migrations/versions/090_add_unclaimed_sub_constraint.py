"""add unique constraint for unclaimed submissions

Revision ID: 090_add_unclaimed_sub_constraint
Revises: 089_collection_email_settings
Create Date: 2026-09-29 08:51:26.956371

"""

import sqlalchemy as sa
from alembic import op

revision = "090_add_unclaimed_sub_constraint"
down_revision = "089_collection_email_settings"
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
