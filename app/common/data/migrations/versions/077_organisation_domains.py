"""Add domains to organistions

Revision ID: 077_organisation_domains
Revises: 076_add_prospector_url_col
Create Date: 2026-08-04 09:22:55.818272

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "077_organisation_domains"
down_revision = "076_add_prospector_url_col"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("domains", postgresql.ARRAY(sa.String()), server_default="{}", nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.drop_column("domains")
