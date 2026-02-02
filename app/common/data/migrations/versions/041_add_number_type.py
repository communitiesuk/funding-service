"""Add number type to data_options, set to INTEGER for existing whole number questions

Revision ID: 041_add_number_type
Revises: 040_new_platform_admin_roles
Create Date: 2026-02-02 14:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "041_add_number_type"
down_revision = "040_new_platform_admin_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text("""
                UPDATE component
                SET data_options = '{"allow_decimals"\\:false, "number_type"\\:"Whole number"}'
                WHERE data_type = 'NUMBER'
                """)
    )


def downgrade() -> None:
    op.execute(
        sa.text("""
                UPDATE component
                SET data_options = '{"allow_decimals"\\:false}'
                WHERE data_type = 'NUMBER'
                """)
    )
