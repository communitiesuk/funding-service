"""drop all sections

Revision ID: 034_drop_all_sections
Revises: 033_nullable_sections
Create Date: 2025-09-01 12:58:51.364325

"""

from alembic import op

revision = "034_drop_all_sections"
down_revision = "033_nullable_sections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.drop_constraint("uq_form_order_section", type_="unique")
        batch_op.drop_constraint("uq_form_slug_section", type_="unique")
        batch_op.drop_constraint("uq_form_title_section", type_="unique")

    op.execute("UPDATE form SET section_id = NULL")
    op.execute("DELETE FROM section")


def downgrade() -> None:
    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_form_title_section", ["title", "section_id"], postgresql_nulls_not_distinct=False
        )
        batch_op.create_unique_constraint(
            "uq_form_slug_section", ["slug", "section_id"], postgresql_nulls_not_distinct=False
        )
        batch_op.create_unique_constraint(
            "uq_form_order_section", ["order", "section_id"], postgresql_nulls_not_distinct=False
        )
