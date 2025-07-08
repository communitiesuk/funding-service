"""empty message

Revision ID: 016_do_it
Revises: 015_do_it
Create Date: 2025-07-08 19:43:42.667220

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "016_do_it"
down_revision = "015_do_it"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "RADIOS", "CHECKBOXES"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "RADIOS"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )
