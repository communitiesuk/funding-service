"""Add file upload question type

Revision ID: 043_file_upload_question_type
Revises: 042_remove_allow_decimals
Create Date: 2026-02-18 22:29:21.759223

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "043_file_upload_question_type"
down_revision = "042_remove_allow_decimals"
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
            "NUMBER",
            "YES_NO",
            "RADIOS",
            "CHECKBOXES",
            "DATE",
            "FILE_UPLOAD",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="component", column_name="data_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
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
