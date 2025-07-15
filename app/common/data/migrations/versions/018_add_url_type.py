"""adds url question type

Revision ID: 018_add_url_type
Revises: 017_add_email_question_type
Create Date: 2025-07-15 16:20:42.732770

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "018_add_url_type"
down_revision = "017_add_email_question_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["EMAIL", "URL", "TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "YES_NO", "RADIOS"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["EMAIL", "TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "YES_NO", "RADIOS"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )
