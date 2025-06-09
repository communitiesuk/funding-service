"""adding name column into user table

Revision ID: 007_adding_name_column
Revises: 006_metadata_enum
Create Date: 2025-06-06 10:15:36.813472

"""

import sqlalchemy as sa
from alembic import op

revision = "007_adding_name_column"
down_revision = "001_bootstrap"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.add_column(sa.Column("name", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("user", schema=None) as batch_op:
        batch_op.drop_column("name")
