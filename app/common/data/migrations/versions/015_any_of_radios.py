"""add AnyOf condition for radios

Revision ID: 015_any_of_radios
Revises: 014_sync_data_type_enum
Create Date: 2025-07-12 08:37:51.692418

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "015_any_of_radios"
down_revision = "014_sync_data_type_enum"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN", "ANY_OF"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )
