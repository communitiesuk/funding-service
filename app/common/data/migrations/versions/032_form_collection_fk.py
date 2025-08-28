"""add FKs between form and collection directly so that we can later remove sections

Revision ID: 032_form_collection_fk
Revises: 031_support_guidance
Create Date: 2025-08-28 09:00:22.314171

"""

import sqlalchemy as sa
from alembic import op

revision = "032_form_collection_fk"
down_revision = "031_support_guidance"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Not backwards compatible with the code; we won't be able to create forms between this migration running and
    # the new code deploying, but we can tolerate that with current service use.
    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.add_column(sa.Column("collection_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("collection_version", sa.Integer(), nullable=True))

    op.execute(
        sqltext=(
            "UPDATE form "
            "SET collection_id = section.collection_id, collection_version = section.collection_version "
            "FROM section WHERE form.section_id = section.id"
        )
    )

    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.alter_column("collection_id", existing_nullable=True, nullable=False)
        batch_op.alter_column("collection_version", existing_nullable=True, nullable=False)

    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.create_unique_constraint(
            "uq_form_order_collection", ["order", "collection_id", "collection_version"], deferrable=True
        )
        batch_op.create_unique_constraint("uq_form_slug_collection", ["slug", "collection_id", "collection_version"])
        batch_op.create_unique_constraint("uq_form_title_collection", ["title", "collection_id", "collection_version"])
        batch_op.create_foreign_key(
            batch_op.f("fk_form_collection_id_collection"),
            "collection",
            ["collection_id", "collection_version"],
            ["id", "version"],
        )


def downgrade() -> None:
    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_form_collection_id_collection"), type_="foreignkey")
        batch_op.drop_constraint("uq_form_title_collection", type_="unique")
        batch_op.drop_constraint("uq_form_slug_collection", type_="unique")
        batch_op.drop_constraint("uq_form_order_collection", type_="unique")

    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.drop_column("collection_version")
        batch_op.drop_column("collection_id")
