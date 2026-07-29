"""Add DataSourceItem.alias

Revision ID: 077_data_source_item_alias
Revises: 076_add_another_repeats_over
Create Date: 2026-07-29 17:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "077_data_source_item_alias"
down_revision = "076_add_another_repeats_over"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("data_source_item", schema=None) as batch_op:
        batch_op.add_column(sa.Column("alias", sa.String(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("data_source_item", schema=None) as batch_op:
        batch_op.drop_column("alias")
