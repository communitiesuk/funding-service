"""Removing allow_decimals from number questions as it's redundant with number_type.

Revision ID: 042_remove_allow_decimals
Revises: 041_add_number_type
Create Date: 2026-02-02 14:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "042_remove_allow_decimals"
down_revision = "041_add_number_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
                UPDATE component
                SET data_options = '{"number_type"\\:"Whole number"}'
                WHERE data_type = 'NUMBER'
                """)
    )


def downgrade() -> None:
    op.execute(
        sa.text("""
                UPDATE component
                SET data_options = '{"allow_decimals"\\:false,"number_type"\\:"Whole number"}'
                WHERE data_type = 'NUMBER'
                """)
    )
