"""Converts any existing rows with a data type of INTEGER to use NUMBER instead.

Revision ID: 038_convert_integers_to_numbers
Revises: 037_add_number_data_type
Create Date: 2026-01-28 18:12:10.868509

"""

import sqlalchemy as sa
from alembic import op

revision = "038_convert_integers_to_numbers"
down_revision = "037_add_number_data_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
                UPDATE component
                SET data_type='NUMBER'
                WHERE data_type = 'INTEGER'
                """)
    )


def downgrade() -> None:
    op.execute(
        sa.text("""
                UPDATE component
                SET data_type='INTEGER'
                WHERE data_type = 'NUMBER'
                """)
    )
