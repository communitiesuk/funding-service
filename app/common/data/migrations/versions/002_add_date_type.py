"""Add a new question type of Date

Revision ID: 002_add_date_type
Revises: 001_reset_migrations
Create Date: 2025-09-04 12:29:37.196441

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "002_add_date_type"
down_revision = "001_reset_migrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=[
            "TEXT_SINGLE_LINE",
            "TEXT_MULTI_LINE",
            "EMAIL",
            "URL",
            "INTEGER",
            "YES_NO",
            "RADIOS",
            "CHECKBOXES",
            "DATE",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="data_type")],
        enum_values_to_rename=[],
    )
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=[
            "GREATER_THAN",
            "LESS_THAN",
            "BETWEEN",
            "IS_YES",
            "IS_NO",
            "ANY_OF",
            "SPECIFICALLY",
            "IS_BEFORE",
            "IS_AFTER",
            "BETWEEN_DATES",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "EMAIL", "URL", "INTEGER", "YES_NO", "RADIOS", "CHECKBOXES"],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="data_type")],
        enum_values_to_rename=[],
    )
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN", "IS_YES", "IS_NO", "ANY_OF", "SPECIFICALLY"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )
