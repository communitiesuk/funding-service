"""add UK postcode validator

Revision ID: 024_sync_managed_expression_enum
Revises: 023_remove_role_columns
Create Date: 2025-11-17 14:52:54.201569

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "024_sync_managed_expression_enum"
down_revision = "023_remove_role_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
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
            "UK_POSTCODE",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
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
