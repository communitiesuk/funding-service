"""Make Grant name CITEXT for case insensitive comparisons

Revision ID: 003_make_grant_name_citext
Revises: 002_make_grant_name_unique
Create Date: 2025-03-31 14:00:36.295660

"""

import sqlalchemy as sa
from alembic import op
from alembic_utils.pg_extension import PGExtension
from sqlalchemy.dialects import postgresql

revision = "003_make_grant_name_citext"
down_revision = "002_make_grant_name_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    public_citext = PGExtension(schema="public", signature="citext")
    op.create_entity(public_citext)

    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.alter_column("name", existing_type=sa.VARCHAR(), type_=postgresql.CITEXT(), existing_nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.alter_column("name", existing_type=postgresql.CITEXT(), type_=sa.VARCHAR(), existing_nullable=False)

    public_citext = PGExtension(schema="public", signature="citext")
    op.drop_entity(public_citext)
