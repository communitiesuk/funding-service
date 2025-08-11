"""Reorder and re-word question data type enum

Revision ID: 029_reorder_and_reword_enums
Revises: 028_remove_submission_status
Create Date: 2025-08-11 12:45:32.004941

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "029_reorder_and_reword_enums"
down_revision = "028_remove_submission_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "EMAIL", "URL", "INTEGER", "YES_NO", "RADIOS", "CHECKBOXES"],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="data_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["EMAIL", "URL", "TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "YES_NO", "RADIOS", "CHECKBOXES"],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="data_type")],
        enum_values_to_rename=[],
    )
