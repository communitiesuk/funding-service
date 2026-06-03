"""Add mark_submissions_enabled to collection

Revision ID: 064_mark_submissions_enabled
Revises: 063_mark_submission
Create Date: 2026-06-03 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "064_mark_submissions_enabled"
down_revision = "063_mark_submission"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "collection", sa.Column("mark_submissions_enabled", sa.Boolean(), nullable=False, server_default="false")
    )


def downgrade() -> None:
    op.drop_column("collection", "mark_submissions_enabled")
