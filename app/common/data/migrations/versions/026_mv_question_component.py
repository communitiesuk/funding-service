"""Rename question to component

Revision ID: 026_mv_question_component
Revises: 025_ds_item_key_case_insensitive
Create Date: 2025-08-06 08:37:44.318167

"""

import sqlalchemy as sa
from alembic import op

revision = "026_mv_question_component"
down_revision = "025_ds_item_key_case_insensitive"
branch_labels = None
depends_on = None

type_enum = sa.Enum("QUESTION", name="component_type_enum")


def upgrade() -> None:
    type_enum.create(op.get_bind())

    op.rename_table("question", "component")

    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.drop_constraint("fk_data_source_question_id_question", type_="foreignkey")
        batch_op.create_foreign_key(
            batch_op.f("fk_data_source_question_id_component"), "component", ["question_id"], ["id"]
        )

    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_constraint("fk_expression_question_id_question", type_="foreignkey")
        batch_op.create_foreign_key(
            batch_op.f("fk_expression_question_id_component"), "component", ["question_id"], ["id"]
        )

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.add_column(sa.Column("type", type_enum, nullable=False))

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_constraint("uq_question_order_form", type_="unique")
        batch_op.drop_constraint("uq_question_slug_form", type_="unique")
        batch_op.drop_constraint("uq_question_text_form", type_="unique")
        batch_op.drop_constraint("uq_question_name_form", type_="unique")

        batch_op.create_unique_constraint("uq_component_order_form", ["order", "form_id"], deferrable=True)
        batch_op.create_unique_constraint("uq_component_slug_form", ["slug", "form_id"], deferrable=True)
        batch_op.create_unique_constraint("uq_component_text_form", ["text", "form_id"], deferrable=True)
        batch_op.create_unique_constraint("uq_component_name_form", ["name", "form_id"], deferrable=True)


def downgrade() -> None:
    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_expression_question_id_component"), type_="foreignkey")
        batch_op.create_foreign_key("fk_expression_question_id_question", "question", ["question_id"], ["id"])

    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_data_source_question_id_component"), type_="foreignkey")
        batch_op.create_foreign_key("fk_data_source_question_id_question", "question", ["question_id"], ["id"])

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_column("type")

    op.rename_table("component", "question")

    with op.batch_alter_table("question", schema=None) as batch_op:
        batch_op.drop_constraint("uq_component_order_form", type_="unique")
        batch_op.drop_constraint("uq_component_slug_form", type_="unique")
        batch_op.drop_constraint("uq_component_text_form", type_="unique")
        batch_op.drop_constraint("uq_component_name_form", type_="unique")

        batch_op.create_unique_constraint("uq_question_order_form", ["order", "form_id"], deferrable=True)
        batch_op.create_unique_constraint("uq_question_slug_form", ["slug", "form_id"], deferrable=True)
        batch_op.create_unique_constraint("uq_question_text_form", ["text", "form_id"], deferrable=True)
        batch_op.create_unique_constraint("uq_question_name_form", ["name", "form_id"], deferrable=True)

    type_enum.drop(op.get_bind())
