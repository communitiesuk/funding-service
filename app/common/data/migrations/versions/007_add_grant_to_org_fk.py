"""track ownership of grants by orgs (eg MHCLG)

Revision ID: 007_add_grant_to_org_fk
Revises: 006_add_another
Create Date: 2025-10-15 18:32:12.661381

"""

import sqlalchemy as sa
from alembic import op

revision = "007_add_grant_to_org_fk"
down_revision = "006_add_another"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.add_column(sa.Column("organisation_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_grant_organisation_id_organisation"), "organisation", ["organisation_id"], ["id"]
        )

    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.add_column(sa.Column("can_manage_grants", sa.Boolean(), nullable=False))
        batch_op.create_index(
            "uq_organisation_name_can_manage_grants",
            ["can_manage_grants"],
            unique=True,
            postgresql_where=sa.text("can_manage_grants IS true"),
        )


def downgrade() -> None:
    with op.batch_alter_table("organisation", schema=None) as batch_op:
        batch_op.drop_index(
            "uq_organisation_name_can_manage_grants", postgresql_where=sa.text("can_manage_grants IS true")
        )
        batch_op.drop_column("can_manage_grants")

    with op.batch_alter_table("grant", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_grant_organisation_id_organisation"), type_="foreignkey")
        batch_op.drop_column("organisation_id")
