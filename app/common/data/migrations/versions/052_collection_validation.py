"""Collection validation

Revision ID: 052_collection_validation
Revises: 051_collection_type_allocation
Create Date: 2026-03-11 00:41:56.609570

"""

import sqlalchemy as sa
from alembic import op

revision = "052_collection_validation"
down_revision = "051_collection_type_allocation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("requires_validation", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("requires_validation")
