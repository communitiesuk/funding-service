"""grant privacy policies

Revision ID: 033_grant_privacy_policies
Revises: 032_entity_modes
Create Date: 2025-12-16 10:44:45.613091

"""

import sqlalchemy as sa
from alembic import op

revision = "033_grant_privacy_policies"
down_revision = "032_entity_modes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.add_column(sa.Column("privacy_policy_markdown", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.drop_column("privacy_policy_markdown")
