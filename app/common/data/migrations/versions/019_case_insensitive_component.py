"""Changing Component name and text to be case insensitive

Revision ID: 019_case_insensitive_component
Revises: 018_add_onboarding_status
Create Date: 2025-11-06 14:05:35.661762

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "019_case_insensitive_component"
down_revision = "018_add_onboarding_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.alter_column("text", existing_type=sa.VARCHAR(), type_=postgresql.CITEXT(), existing_nullable=False)
        batch_op.alter_column("name", existing_type=sa.VARCHAR(), type_=postgresql.CITEXT(), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.alter_column("name", existing_type=postgresql.CITEXT(), type_=sa.VARCHAR(), existing_nullable=False)
        batch_op.alter_column("text", existing_type=postgresql.CITEXT(), type_=sa.VARCHAR(), existing_nullable=False)
