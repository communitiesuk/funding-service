"""Adding custom expression type to managed expression enum

Revision ID: 043_add_custom_expressions
Revises: 042_remove_allow_decimals
Create Date: 2026-02-09 12:47:40.332189

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "043_add_custom_expressions"
down_revision = "042_remove_allow_decimals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # type:ignore[unresolved-attribute]
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
            "CUSTOM",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # type:ignore[unresolved-attribute]
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
