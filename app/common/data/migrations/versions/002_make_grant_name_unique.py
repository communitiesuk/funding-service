"""Add a unique constraint to the grant name column

Revision ID: 002_make_grant_name_unique
Revises: 001_initial_grant_table
Create Date: 2025-03-27 13:02:42.292921

"""

from alembic import op

revision = "002_make_grant_name_unique"
down_revision = "001_initial_grant_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.create_unique_constraint(batch_op.f("uq_grant_name"), ["name"])


def downgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_grant_name"), type_="unique")
