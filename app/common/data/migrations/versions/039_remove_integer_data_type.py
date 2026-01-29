"""Removes INTEGER from the data type enum.

Revision ID: 039_remove_integer_data_type
Revises: 038_convert_integers_to_numbers
Create Date: 2026-01-29 06:58:48.214175

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "039_remove_integer_data_type"
down_revision = "038_convert_integers_to_numbers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # type: ignore[attr-defined]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=[
            "TEXT_SINGLE_LINE",
            "TEXT_MULTI_LINE",
            "EMAIL",
            "URL",
            "NUMBER",
            "YES_NO",
            "RADIOS",
            "CHECKBOXES",
            "DATE",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="data_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # type: ignore[attr-defined]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=[
            "TEXT_SINGLE_LINE",
            "TEXT_MULTI_LINE",
            "EMAIL",
            "URL",
            "INTEGER",
            "NUMBER",
            "YES_NO",
            "RADIOS",
            "CHECKBOXES",
            "DATE",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="data_type")],
        enum_values_to_rename=[],
    )
