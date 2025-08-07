"""add group component type

Revision ID: 027_add_group_type
Revises: 026_mv_question_component
Create Date: 2025-08-06 09:11:17.038093

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference
from sqlalchemy.dialects import postgresql

from app.common.data.types import ComponentType

revision = "027_add_group_type"
down_revision = "026_mv_question_component"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.add_column(sa.Column("parent_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(batch_op.f("fk_component_parent_id_component"), "component", ["parent_id"], ["id"])

    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="component_type_enum",
        new_values=["QUESTION", "GROUP"],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="type")],
        enum_values_to_rename=[],
    )

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.alter_column(
            "data_type",
            existing_type=postgresql.ENUM(
                "EMAIL",
                "URL",
                "TEXT_SINGLE_LINE",
                "TEXT_MULTI_LINE",
                "INTEGER",
                "YES_NO",
                "RADIOS",
                name="question_data_type_enum",
            ),
            nullable=True,
        )
        batch_op.drop_constraint("uq_component_order_form", type_="unique")
        batch_op.create_unique_constraint("uq_component_order_form", ["order", "parent_id", "form_id"], deferrable=True)

        # note alembic does not find this check constraint automatically
        # https://github.com/sqlalchemy/alembic/issues/508
        batch_op.create_check_constraint(
            "ck_component_type_question_requires_data_type",
            f"data_type IS NOT NULL OR type != '{ComponentType.QUESTION.value}'",
        )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="component_type_enum",
        new_values=["QUESTION"],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="type")],
        enum_values_to_rename=[],
    )
    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_component_parent_id_component"), type_="foreignkey")
        batch_op.drop_column("parent_id")

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_constraint("uq_component_order_form", type_="unique")
        batch_op.create_unique_constraint(
            "uq_component_order_form", ["order", "form_id"], postgresql_nulls_not_distinct=False
        )
        batch_op.alter_column(
            "data_type",
            existing_type=postgresql.ENUM(
                "EMAIL",
                "URL",
                "TEXT_SINGLE_LINE",
                "TEXT_MULTI_LINE",
                "INTEGER",
                "YES_NO",
                "RADIOS",
                name="question_data_type_enum",
            ),
            nullable=False,
        )
        batch_op.drop_constraint("ck_component_type_question_requires_data_type", type_="check")
