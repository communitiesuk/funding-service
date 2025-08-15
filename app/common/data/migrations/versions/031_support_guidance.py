"""support question guidance

Revision ID: 031_support_guidance
Revises: 030_new_presentation_options
Create Date: 2025-08-15 13:35:03.360967

"""

import sqlalchemy as sa
from alembic import op

revision = "031_support_guidance"
down_revision = "030_new_presentation_options"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.add_column(sa.Column("guidance_heading", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("guidance_body", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_column("guidance_body")
        batch_op.drop_column("guidance_heading")
