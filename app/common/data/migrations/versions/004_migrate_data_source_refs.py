"""empty message

Revision ID: 004_migrate_data_source_refs
Revises: 003_db_component_refs
Create Date: 2025-09-25 12:05:32.549245

"""

import sqlalchemy as sa
from alembic import op

revision = "004_migrate_data_source_refs"
down_revision = "003_db_component_refs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("component_reference", schema=None) as batch_op:
        batch_op.add_column(sa.Column("depends_on_data_source_item_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_component_reference_depends_on_data_source_item_id_data_source_item"),
            "data_source_item",
            ["depends_on_data_source_item_id"],
            ["id"],
        )


def downgrade() -> None:
    with op.batch_alter_table("component_reference", schema=None) as batch_op:
        batch_op.drop_constraint(
            batch_op.f("fk_component_reference_depends_on_data_source_item_id_data_source_item"), type_="foreignkey"
        )
        batch_op.drop_column("depends_on_data_source_item_id")
