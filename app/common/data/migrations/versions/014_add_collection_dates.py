"""add collection dates

Revision ID: 014_add_collection_dates
Revises: 013_add_another_guidance
Create Date: 2025-11-01

"""

import sqlalchemy as sa
from alembic import op

revision = "014_add_collection_dates"
down_revision = "013_add_another_guidance"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("collection", sa.Column("reporting_period_start_date", sa.Date(), nullable=True))
    op.add_column("collection", sa.Column("reporting_period_end_date", sa.Date(), nullable=True))
    op.add_column("collection", sa.Column("submission_period_start_date", sa.Date(), nullable=True))
    op.add_column("collection", sa.Column("submission_period_end_date", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("collection", "submission_period_end_date")
    op.drop_column("collection", "submission_period_start_date")
    op.drop_column("collection", "reporting_period_end_date")
    op.drop_column("collection", "reporting_period_start_date")
