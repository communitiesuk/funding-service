"""Collection types

Revision ID: 049_collection_types
Revises: 048_multi_submissions_managed
Create Date: 2026-02-03 12:32:52.515204

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "049_collection_types"
down_revision = "048_multi_submissions_managed"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(
        enum_schema="public",
        enum_name="collection_type",
        new_values=[
            "MONITORING_REPORT",
            "APPLICATION",
            "ELIGIBILITY_CHECK",
            "EXPRESSION_OF_INTEREST",
            "BASELINE",
            "ASSESSMENT",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="collection", column_name="type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(
        enum_schema="public",
        enum_name="collection_type",
        new_values=["MONITORING_REPORT"],
        affected_columns=[TableReference(table_schema="public", table_name="collection", column_name="type")],
        enum_values_to_rename=[],
    )
