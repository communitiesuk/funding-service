"""make data source item keys case insensitive

Revision ID: 025_ds_item_key_case_insensitive
Revises: 024_add_specifically_mgd_exp
Create Date: 2025-08-07 15:05:03.406920

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "025_ds_item_key_case_insensitive"
down_revision = "024_add_specifically_mgd_exp"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("data_source_item", schema=None) as batch_op:
        batch_op.alter_column("key", existing_type=sa.VARCHAR(), type_=postgresql.CITEXT(), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("data_source_item", schema=None) as batch_op:
        batch_op.alter_column("key", existing_type=postgresql.CITEXT(), type_=sa.VARCHAR(), existing_nullable=False)
