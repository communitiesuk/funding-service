"""make sections nullable on forms

Revision ID: 033_nullable_sections
Revises: 032_form_collection_fk
Create Date: 2025-09-01 12:47:25.886379

"""

import sqlalchemy as sa
from alembic import op

revision = "033_nullable_sections"
down_revision = "032_form_collection_fk"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.alter_column("section_id", existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.alter_column("section_id", existing_type=sa.UUID(), nullable=False)
