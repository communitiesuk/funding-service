"""add collection status

Revision ID: 015_add_collection_status
Revises: 014_add_collection_dates
Create Date: 2025-11-02 10:17:37.041932

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "015_add_collection_status"
down_revision = "014_add_collection_dates"
branch_labels = None
depends_on = None


def upgrade() -> None:
    sa.Enum("DRAFT", "SCHEDULED", "OPEN", "CLOSED", name="collection_status").create(op.get_bind())
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "status",
                postgresql.ENUM("DRAFT", "SCHEDULED", "OPEN", "CLOSED", name="collection_status", create_type=False),
                nullable=True,
            )
        )

    op.execute("UPDATE collection SET status = 'DRAFT'::collection_status WHERE status IS NULL")

    op.alter_column("collection", "status", nullable=False, existing_nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_column("status")

    sa.Enum("DRAFT", "SCHEDULED", "OPEN", "CLOSED", name="collection_status").drop(op.get_bind())
