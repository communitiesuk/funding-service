"""Add collection_id column to magic_link table

Revision ID: 078_add_collection_id_magic_link
Revises: 077_organisation_domains
Create Date: 2026-08-04 00:34:00.217019

"""

import sqlalchemy as sa
from alembic import op

revision = "078_add_collection_id_magic_link"
down_revision = "077_organisation_domains"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("magic_link", schema=None) as batch_op:
        batch_op.add_column(sa.Column("collection_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_magic_link_collection_id_collection"), "collection", ["collection_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("magic_link", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_magic_link_collection_id_collection"), type_="foreignkey")
        batch_op.drop_column("collection_id")
