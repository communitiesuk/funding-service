"""empty message

Revision ID: 015_do_it
Revises: 014_do_it
Create Date: 2025-07-08 15:15:43.520812

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "015_do_it"
down_revision = "014_do_it"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN", "CHOICE_FROM_LIST"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(
        enum_schema="public",
        enum_name="managed_expression_enum",
        new_values=["GREATER_THAN", "LESS_THAN", "BETWEEN"],
        affected_columns=[TableReference(table_schema="public", table_name="expression", column_name="managed_name")],
        enum_values_to_rename=[],
    )
