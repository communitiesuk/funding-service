"""rename questions and add group type

Revision ID: 020_rename_questions
Revises: 019_add_data_source_item_ref
Create Date: 2025-07-22 15:03:03.584244

"""

import sqlalchemy as sa
from alembic import op

revision = "020_rename_questions"
down_revision = "019_add_data_source_item_ref"
branch_labels = None
depends_on = None

type_enum = sa.Enum("QUESTION", "GROUP", name="component_type_enum")


def upgrade() -> None:
    type_enum.create(op.get_bind())

    op.rename_table("question", "component")
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "type",
                type_enum,
                nullable=True,
            )
        )

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.execute("UPDATE component SET type = 'QUESTION' WHERE type IS NULL")
        batch_op.alter_column("type", nullable=False)

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.alter_column("data_type", nullable=True)

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
        batch_op.add_column(sa.Column("parent_id", sa.Uuid(), nullable=True))
        batch_op.drop_constraint("uq_question_order_form", type_="unique")
        batch_op.create_unique_constraint("uq_question_order_form", ["order", "parent_id", "form_id"], deferrable=True)
        batch_op.create_foreign_key(batch_op.f("fk_component_parent_id_component"), "component", ["parent_id"], ["id"])


def downgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.alter_column("data_type", nullable=False)

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_column("type")

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_component_parent_id_component"), type_="foreignkey")
        batch_op.drop_constraint("uq_question_order_form", type_="unique")
        batch_op.create_unique_constraint(
            "uq_question_order_form", ["order", "form_id"], postgresql_nulls_not_distinct=False
        )
        batch_op.drop_column("parent_id")

    op.rename_table("component", "question")

    with op.batch_alter_table("expression", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_expression_question_id_component"), type_="foreignkey")
        batch_op.create_foreign_key("fk_expression_question_id_question", "question", ["question_id"], ["id"])

    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_data_source_question_id_component"), type_="foreignkey")
        batch_op.create_foreign_key("fk_data_source_question_id_question", "question", ["question_id"], ["id"])

    type_enum.drop(op.get_bind())
