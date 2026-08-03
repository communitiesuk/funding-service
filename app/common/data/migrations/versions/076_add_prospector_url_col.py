"""Add prospector_url column to collection

Revision ID: 076_add_prospector_url_col
Revises: 075_allow_submission_reopening
Create Date: 2026-07-29 21:19:20.074810

"""

import sqlalchemy as sa
from alembic import op

revision = "076_add_prospector_url_col"
down_revision = "075_allow_submission_reopening"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("prospectus_url", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("prospectus_url")
