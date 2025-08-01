"""Add specifically managed expression

Revision ID: 024_add_specifically_mgd_exp
Revises: 023_add_checkbox_question_type
Create Date: 2025-08-01 15:55:52.482930

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "024_add_specifically_mgd_exp"
down_revision = "023_add_checkbox_question_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN", "IS_YES", "IS_NO", "ANY_OF", "SPECIFICALLY"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN", "IS_YES", "IS_NO", "ANY_OF"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )
