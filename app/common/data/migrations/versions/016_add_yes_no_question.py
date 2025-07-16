"""add yes/no question

Revision ID: 016_add_yes_no_question
Revises: 015_any_of_radios
Create Date: 2025-07-15 11:36:58.587172

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "016_add_yes_no_question"
down_revision = "015_any_of_radios"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "YES_NO", "RADIOS"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN", "IS_YES", "IS_NO", "ANY_OF"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN", "ANY_OF"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "RADIOS"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )
