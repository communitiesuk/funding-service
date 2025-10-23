"""Add another guidance field

Revision ID: 013_add_another_guidance
Revises: 012_grant_recipient_relationship
Create Date: 2025-10-23 12:58:28.429964

"""

import sqlalchemy as sa
from alembic import op

revision = "013_add_another_guidance"
down_revision = "012_grant_recipient_relationship"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.add_column(sa.Column("add_another_guidance_body", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_column("add_another_guidance_body")
