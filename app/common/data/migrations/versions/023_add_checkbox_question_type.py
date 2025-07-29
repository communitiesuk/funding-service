"""add checkbox question type

Revision ID: 023_add_checkbox_question_type
Revises: 022_force_migrations
Create Date: 2025-07-29 14:00:32.329736

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "023_add_checkbox_question_type"
down_revision = "022_force_migrations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["EMAIL", "URL", "TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "YES_NO", "RADIOS", "CHECKBOXES"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["EMAIL", "URL", "TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "YES_NO", "RADIOS"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )
