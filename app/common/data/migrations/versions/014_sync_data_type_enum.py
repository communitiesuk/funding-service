"""sync question data type enums

Revision ID: 014_sync_data_type_enum
Revises: 013_data_sources
Create Date: 2025-07-11 15:22:42.081776

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "014_sync_data_type_enum"
down_revision = "013_data_sources"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER", "RADIOS"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="question_data_type_enum",
        new_values=["TEXT_SINGLE_LINE", "TEXT_MULTI_LINE", "INTEGER"],
        affected_columns=[TableReference(table_schema="public", table_name="question", column_name="data_type")],
        enum_values_to_rename=[],
    )
