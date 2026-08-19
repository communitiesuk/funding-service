"""Add collection open notification sent timestamp

Revision ID: 080_collection_open_email_sent
Revises: 079_add_pgqueuer
Create Date: 2026-08-19 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "080_collection_open_email_sent"
down_revision = "079_add_pgqueuer"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("collection_open_notification_sent_at_utc", sa.DateTime(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("collection_open_notification_sent_at_utc")
