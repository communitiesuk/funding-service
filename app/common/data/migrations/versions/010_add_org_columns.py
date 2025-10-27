"""update organisations

Revision ID: 010_add_org_columns
Revises: 009_add_grant_status
Create Date: 2025-10-27 10:38:16.378678

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "010_add_org_columns"
down_revision = "009_add_grant_status"
branch_labels = None
depends_on = None

org_status_enum = postgresql.ENUM("ACTIVE", "RETIRED", name="organisationstatus", create_type=False)
org_type_enum = postgresql.ENUM(
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
    create_type=False,
)


def upgrade() -> None:
    org_status_enum.create(op.get_bind())
    org_type_enum.create(op.get_bind())

    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("external_id", sa.String(), nullable=True))
        batch_op.add_column(sa.Column("status", org_status_enum, nullable=True))
        batch_op.add_column(sa.Column("type", org_type_enum, nullable=True))
        batch_op.add_column(sa.Column("active_date", sa.Date(), nullable=True))
        batch_op.add_column(sa.Column("retirement_date", sa.Date(), nullable=True))
        batch_op.create_unique_constraint(batch_op.f("uq_organisation_external_id"), ["external_id"])

    op.execute("""UPDATE organisation SET "status"='ACTIVE'""")
    op.execute(
        """UPDATE organisation
           SET external_id='GB-GOV-27',
               "type"='CENTRAL_GOVERNMENT'
           WHERE name='Ministry of Housing, Communities and Local Government'
        """
    )

    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.alter_column("status", existing_nullable=True, nullable=False)


def downgrade() -> None:
    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("uq_organisation_external_id"), type_="unique")
        batch_op.drop_column("retirement_date")
        batch_op.drop_column("active_date")
        batch_op.drop_column("type")
        batch_op.drop_column("status")
        batch_op.drop_column("external_id")

    org_status_enum.drop(op.get_bind())
    org_type_enum.drop(op.get_bind())
