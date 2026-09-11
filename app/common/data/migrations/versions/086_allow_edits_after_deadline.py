"""Add allow_edits_after_submission_deadline to collection

Revision ID: 086_allow_edits_after_deadline
Revises: 085_invitation_created_by
Create Date: 2026-09-08 14:58:49.514000

"""

import sqlalchemy as sa
from alembic import op

revision = "086_allow_edits_after_deadline"
down_revision = "085_invitation_created_by"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("allow_edits_after_submission_deadline", sa.Boolean(), nullable=False, server_default=sa.true())
        )


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("allow_edits_after_submission_deadline")
