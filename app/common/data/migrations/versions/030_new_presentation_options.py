"""make presentation options not nullable

Revision ID: 030_new_presentation_options
Revises: 029_reorder_and_reword_enums
Create Date: 2025-08-13 11:43:04.127562

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "030_new_presentation_options"
down_revision = "029_reorder_and_reword_enums"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sqltext="UPDATE component SET presentation_options='{}' WHERE presentation_options IS NULL")

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.alter_column(
            "presentation_options", existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=False
        )


def downgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.alter_column(
            "presentation_options", existing_type=postgresql.JSONB(astext_type=sa.Text()), nullable=True
        )
