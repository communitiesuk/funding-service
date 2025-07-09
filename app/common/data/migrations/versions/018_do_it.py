"""empty message

Revision ID: 018_do_it
Revises: 017_do_it
Create Date: 2025-07-09 10:28:28.666204

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "018_do_it"
down_revision = "017_do_it"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.add_column(sa.Column("used_choice_ids", postgresql.ARRAY(sa.String()), nullable=True))

    op.execute("UPDATE data_source SET used_choice_ids=ARRAY[]::text[]")

    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.alter_column("used_choice_ids", existing_nullable=True, nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.drop_column("used_choice_ids")
