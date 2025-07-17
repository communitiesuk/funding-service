"""add question options for rendering

Revision ID: 020_add_question_options
Revises: 019_add_data_source_item_ref
Create Date: 2025-07-17 15:51:36.171814

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "020_add_question_options"
down_revision = "019_add_data_source_item_ref"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("question", schema=None) as batch_op:
        batch_op.add_column(sa.Column("options", postgresql.JSONB(astext_type=sa.Text()), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("question", schema=None) as batch_op:
        batch_op.drop_column("options")
