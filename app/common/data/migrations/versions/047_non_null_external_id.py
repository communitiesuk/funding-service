"""make organisation external_id non nullable

Revision ID: 047_non_null_external_id
Revises: 046_unique_orgs_within_type
Create Date: 2026-02-24 14:00:46.528421

"""

import sqlalchemy as sa
from alembic import op

revision = "047_non_null_external_id"
down_revision = "046_unique_orgs_within_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.alter_column("external_id", existing_type=sa.VARCHAR(), nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.alter_column("external_id", existing_type=sa.VARCHAR(), nullable=True)
