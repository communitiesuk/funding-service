"""add typed external id columns

Revision ID: 067_add_typed_external_id_cols
Revises: 066_reminder_email_biz_days
Create Date: 2026-06-23 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op
from alembic_postgresql_enum import TableReference

revision = "067_add_typed_external_id_cols"
down_revision = "066_reminder_email_biz_days"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.sync_enum_values(  # ty:ignore[unresolved-attribute]
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
            "CHARITY",
            "COMPANY",
            "OTHER",
        ],
        affected_columns=[TableReference(table_schema="public", table_name="organisation", column_name="type")],
        enum_values_to_rename=[],
    )

    op.add_column("organisation", sa.Column("iati_id", sa.String(), nullable=True))
    op.add_column("organisation", sa.Column("ons_lad_id", sa.String(), nullable=True))
    op.add_column("organisation", sa.Column("companies_house_number", sa.String(), nullable=True))
    op.add_column("organisation", sa.Column("charity_commission_number", sa.String(), nullable=True))
    op.add_column("organisation", sa.Column("custom_code", sa.String(), nullable=True))

    op.execute("""
        UPDATE organisation
        SET iati_id = external_id
        WHERE type = 'CENTRAL_GOVERNMENT'
    """)
    op.execute("""
        UPDATE organisation
        SET ons_lad_id = external_id
        WHERE type IN (
            'UNITARY_AUTHORITY', 'SHIRE_DISTRICT', 'METROPOLITAN_DISTRICT',
            'LONDON_BOROUGH', 'SHIRE_COUNTY', 'COMBINED_AUTHORITY',
            'NORTHERN_IRELAND_AUTHORITY', 'SCOTTISH_UNITARY_AUTHORITY',
            'WELSH_UNITARY_AUTHORITY'
        )
    """)
    op.execute("""
        UPDATE organisation
        SET custom_code = external_id
        WHERE type = 'OTHER'
    """)

    op.create_check_constraint(
        "ck_typed_external_id",
        "organisation",
        """
        (type = 'CENTRAL_GOVERNMENT' AND iati_id IS NOT NULL) OR
        (type IN ('UNITARY_AUTHORITY', 'SHIRE_DISTRICT', 'METROPOLITAN_DISTRICT',
                  'LONDON_BOROUGH', 'SHIRE_COUNTY', 'COMBINED_AUTHORITY',
                  'NORTHERN_IRELAND_AUTHORITY', 'SCOTTISH_UNITARY_AUTHORITY',
                  'WELSH_UNITARY_AUTHORITY') AND ons_lad_id IS NOT NULL) OR
        (type = 'CHARITY' AND charity_commission_number IS NOT NULL) OR
        (type = 'COMPANY' AND companies_house_number IS NOT NULL) OR
        (type = 'OTHER' AND custom_code IS NOT NULL)
        """,
    )


def downgrade() -> None:
    op.drop_constraint("ck_typed_external_id", "organisation", type_="check")
    op.drop_column("organisation", "custom_code")
    op.drop_column("organisation", "charity_commission_number")
    op.drop_column("organisation", "companies_house_number")
    op.drop_column("organisation", "ons_lad_id")
    op.drop_column("organisation", "iati_id")

    op.sync_enum_values(  # ty:ignore[unresolved-attribute]
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
