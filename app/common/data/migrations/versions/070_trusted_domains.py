"""Adds trusted domain property to organisations

Revision ID: 070_trusted_domains
Revises: 069_changes_req_sub_status
Create Date: 2026-07-14 17:10:20.627658

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "070_trusted_domains"
down_revision = "069_changes_req_sub_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("trusted_domains", postgresql.ARRAY(sa.Text()), server_default="{}", nullable=False)
        )


def downgrade() -> None:
    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.drop_column("trusted_domains")
