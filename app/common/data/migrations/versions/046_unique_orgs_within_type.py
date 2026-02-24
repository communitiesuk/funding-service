"""unique orgs within type (live/test)

Revision ID: 046_unique_orgs_within_type
Revises: 045_add_submission_guidance
Create Date: 2026-02-18 15:14:08.046918

"""

from alembic import op
from sqlalchemy.dialects import postgresql

revision = "046_unique_orgs_within_type"
down_revision = "045_add_submission_guidance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.alter_column(
            "type",
            existing_type=postgresql.ENUM(
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
                name="organisationtype",
            ),
            nullable=False,
        )
        batch_op.drop_constraint("uq_organisation_external_id", type_="unique")
        batch_op.drop_constraint("uq_organisation_name", type_="unique")
        batch_op.create_unique_constraint("uq_organisation_external_id_mode", ["external_id", "mode"])
        batch_op.create_unique_constraint("uq_organisation_name_mode", ["name", "mode"])


def downgrade() -> None:
    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.drop_constraint("uq_organisation_name_mode", type_="unique")
        batch_op.drop_constraint("uq_organisation_external_id_mode", type_="unique")
        batch_op.create_unique_constraint("uq_organisation_name", ["name"], postgresql_nulls_not_distinct=False)
        batch_op.create_unique_constraint(
            "uq_organisation_external_id", ["external_id"], postgresql_nulls_not_distinct=False
        )
        batch_op.alter_column(
            "type",
            existing_type=postgresql.ENUM(
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
                name="organisationtype",
            ),
            nullable=True,
        )
