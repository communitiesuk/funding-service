"""Add collection reminder email settings

Revision ID: 089_collection_email_settings
Revises: 088_remove_pre_award_flag
Create Date: 2026-09-21 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "089_collection_email_settings"
down_revision = "088_remove_pre_award_flag"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("send_deadline_reminder_emails", sa.Boolean(), nullable=False, server_default=sa.true())
        )
        batch_op.add_column(sa.Column("send_overdue_emails", sa.Boolean(), nullable=False, server_default=sa.true()))


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("send_overdue_emails")
        batch_op.drop_column("send_deadline_reminder_emails")
