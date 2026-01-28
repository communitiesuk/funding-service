"""Adds the number data type to the question_data_type_enum

Revision ID: 037_add_number_data_type
Revises: 036_add_question_data_options
Create Date: 2026-01-28 15:53:10.868509

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "037_add_number_data_type"
down_revision = "036_add_question_data_options"
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
            "YES_NO",
            "RADIOS",
            "CHECKBOXES",
            "DATE",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="data_type")],
        enum_values_to_rename=[],
    )
