"""add 'other' organisation type

Revision ID: 052_other_org
Revises: 051_data_upload_metadata
Create Date: 2026-04-01 22:54:59.659863

"""

from alembic import op
from alembic_postgresql_enum import TableReference

revision = "052_other_org"
down_revision = "051_data_upload_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="organisationtype",
        new_values=[
            "CENTRAL_GOVERNMENT",
            "UNITARY_AUTHORITY",
            "SHIRE_DISTRICT",
            "METROPOLITAN_DISTRICT",
            "LONDON_BOROUGH",
            "SHIRE_COUNTY",
            "COMBINED_AUTHORITY",
            "NORTHERN_IRELAND_AUTHORITY",
            "SCOTTISH_UNITARY_AUTHORITY",
            "WELSH_UNITARY_AUTHORITY",
            "OTHER",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="organisation", column_name="type")],
        enum_values_to_rename=[],
    )


def downgrade() -> None:
    op.sync_enum_values(  # ty: ignore[unresolved-attribute]
        enum_schema="public",
        enum_name="organisationtype",
        new_values=[
            "CENTRAL_GOVERNMENT",
            "UNITARY_AUTHORITY",
            "SHIRE_DISTRICT",
            "METROPOLITAN_DISTRICT",
            "LONDON_BOROUGH",
            "SHIRE_COUNTY",
            "COMBINED_AUTHORITY",
            "NORTHERN_IRELAND_AUTHORITY",
            "SCOTTISH_UNITARY_AUTHORITY",
            "WELSH_UNITARY_AUTHORITY",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="organisation", column_name="type")],
        enum_values_to_rename=[],
    )
