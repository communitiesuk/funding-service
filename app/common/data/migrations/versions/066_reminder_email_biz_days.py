"""add a column to track when reminder emails should be sent for a collection

Revision ID: 066_reminder_email_biz_days
Revises: 065_add_grant_recipient_status
Create Date: 2026-06-18 10:22:03.377000

"""

import sqlalchemy as sa
from alembic import op

revision = "066_reminder_email_biz_days"
down_revision = "065_add_grant_recipient_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "reminder_email_business_days_before_closing", sa.Integer(), nullable=False, server_default=sa.text("5")
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("reminder_email_business_days_before_closing")
