"""add collection types

Revision ID: 021_add_collection_type
Revises: 020_add_question_options
Create Date: 2025-07-28 18:38:08.362357

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy import text

revision = "021_add_collection_type"
down_revision = "020_add_question_options"
branch_labels = None
depends_on = None

collection_type_enum = sa.Enum("MONITORING_REPORT", name="collection_type")


def upgrade() -> None:
    collection_type_enum.create(op.get_bind())
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(sa.Column("type", collection_type_enum, nullable=True))

    op.execute(text("UPDATE collection SET type='MONITORING_REPORT' WHERE type IS NULL"))

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.alter_column("type", nullable=False, existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("type")

    collection_type_enum.drop(op.get_bind())
