"""add email question type

Revision ID: 017_add_email_question_type
Revises: 016_add_yes_no_question
Create Date: 2025-07-15 15:37:51.281946

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "017_add_email_question_type"
down_revision = "016_add_yes_no_question"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["EMAIL", "TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "YES_NO", "RADIOS"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "YES_NO", "RADIOS"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )
