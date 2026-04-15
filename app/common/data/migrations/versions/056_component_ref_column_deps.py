"""component reference supports data source columns

Revision ID: 056_component_ref_column_deps
Revises: 055_delete_self_component_refs
Create Date: 2026-04-14 15:49:00.608338

"""

import sqlalchemy as sa
from alembic import op

revision = "056_component_ref_column_deps"
down_revision = "055_delete_self_component_refs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("component_reference", schema=None) as batch_op:
        batch_op.add_column(sa.Column("depends_on_data_source_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("depends_on_column_name", sa.String(), nullable=True))
        batch_op.alter_column("depends_on_component_id", existing_type=sa.UUID(), nullable=True)
        batch_op.create_foreign_key(
            batch_op.f("fk_component_reference_depends_on_data_source_id_data_source"),
            "data_source",
            ["depends_on_data_source_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_check_constraint(
            "ck_component_reference_component_xor_data_source",
            "(depends_on_component_id IS NOT NULL) != (depends_on_data_source_id IS NOT NULL)",
        )
        batch_op.create_check_constraint(
            "ck_component_reference_item_requires_component",
            "depends_on_data_source_item_id IS NULL OR depends_on_component_id IS NOT NULL",
        )
        batch_op.create_check_constraint(
            "ck_component_reference_data_source_requires_column",
            "(depends_on_data_source_id IS NULL) = (depends_on_column_name IS NULL)",
        )


def downgrade() -> None:
    with op.batch_alter_table("component_reference", schema=None) as batch_op:
        batch_op.drop_constraint("ck_component_reference_data_source_requires_column", type_="check")
        batch_op.drop_constraint("ck_component_reference_item_requires_component", type_="check")
        batch_op.drop_constraint("ck_component_reference_component_xor_data_source", type_="check")
        batch_op.drop_constraint(
            batch_op.f("fk_component_reference_depends_on_data_source_id_data_source"), type_="foreignkey"
        )
        batch_op.alter_column("depends_on_component_id", existing_type=sa.UUID(), nullable=False)
        batch_op.drop_column("depends_on_column_name")
        batch_op.drop_column("depends_on_data_source_id")
