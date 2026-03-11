"""Adds allocation collection type

Revision ID: 051_collection_type_allocation
Revises: 050_grant_recipient_status
Create Date: 2026-03-10 22:18:47.349060

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "051_collection_type_allocation"
down_revision = "050_grant_recipient_status"
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
            "ALLOCATION",
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
