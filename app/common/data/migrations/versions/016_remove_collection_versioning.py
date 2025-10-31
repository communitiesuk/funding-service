"""remove collection versioning

Revision ID: 016_remove_collection_versioning
Revises: 015_add_collection_status
Create Date: 2025-10-31

"""

import sqlalchemy as sa
from alembic import op

revision = "016_remove_collection_versioning"
down_revision = "015_add_collection_status"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Drop foreign keys that reference composite (collection_id, collection_version)
    op.drop_constraint(op.f("fk_submission_collection_id_collection"), "submission", type_="foreignkey")
    op.drop_constraint(op.f("fk_form_collection_id_collection"), "form", type_="foreignkey")

    # 2. Drop unique constraints on Form that include collection_version
    op.drop_constraint("uq_form_order_collection", "form", type_="unique")
    op.drop_constraint("uq_form_title_collection", "form", type_="unique")
    op.drop_constraint("uq_form_slug_collection", "form", type_="unique")

    # 3. Drop collection_version columns from submission and form
    op.drop_column("submission", "collection_version")
    op.drop_column("form", "collection_version")

    # 4. Drop unique constraint on Collection that includes version
    op.drop_constraint("uq_collection_name_version_grant_id", "collection", type_="unique")

    # 5. Drop composite primary key and version column from collection
    op.drop_constraint(op.f("pk_collection"), "collection", type_="primary")
    op.drop_column("collection", "version")

    # 6. Create new simple primary key on collection.id
    op.create_primary_key(op.f("pk_collection"), "collection", ["id"])

    # 7. Create new unique constraint on Collection without version
    op.create_unique_constraint("uq_collection_name_grant_id", "collection", ["name", "grant_id"])

    # 8. Recreate Form unique constraints without collection_version
    op.create_unique_constraint("uq_form_order_collection", "form", ["order", "collection_id"], deferrable=True)
    op.create_unique_constraint("uq_form_title_collection", "form", ["title", "collection_id"])
    op.create_unique_constraint("uq_form_slug_collection", "form", ["slug", "collection_id"])

    # 9. Create new simple foreign keys
    op.create_foreign_key(
        op.f("fk_submission_collection_id_collection"), "submission", "collection", ["collection_id"], ["id"]
    )
    op.create_foreign_key(op.f("fk_form_collection_id_collection"), "form", "collection", ["collection_id"], ["id"])


def downgrade():
    # 1. Drop simple foreign keys
    op.drop_constraint(op.f("fk_submission_collection_id_collection"), "submission", type_="foreignkey")
    op.drop_constraint(op.f("fk_form_collection_id_collection"), "form", type_="foreignkey")

    # 2. Drop Form unique constraints without version
    op.drop_constraint("uq_form_order_collection", "form", type_="unique")
    op.drop_constraint("uq_form_title_collection", "form", type_="unique")
    op.drop_constraint("uq_form_slug_collection", "form", type_="unique")

    # 3. Drop Collection unique constraint without version
    op.drop_constraint("uq_collection_name_grant_id", "collection", type_="unique")

    # 4. Drop simple primary key
    op.drop_constraint(op.f("pk_collection"), "collection", type_="primary")

    # 5. Add version column back to collection
    op.add_column("collection", sa.Column("version", sa.Integer(), nullable=False, server_default="1"))

    # 6. Create composite primary key
    op.create_primary_key(op.f("pk_collection"), "collection", ["id", "version"])

    # 7. Remove server_default from version column
    op.alter_column("collection", "version", server_default=False)

    # 8. Create unique constraint with version
    op.create_unique_constraint("uq_collection_name_version_grant_id", "collection", ["name", "grant_id", "version"])

    # 9. Add collection_version columns back to form and submission
    op.add_column("form", sa.Column("collection_version", sa.Integer(), nullable=False, server_default="1"))
    op.add_column("submission", sa.Column("collection_version", sa.Integer(), nullable=False, server_default="1"))

    # 10. Remove server_defaults
    op.alter_column("form", "collection_version", server_default=False)
    op.alter_column("submission", "collection_version", server_default=False)

    # 11. Recreate Form unique constraints with collection_version
    op.create_unique_constraint(
        "uq_form_order_collection", "form", ["order", "collection_id", "collection_version"], deferrable=True
    )
    op.create_unique_constraint("uq_form_title_collection", "form", ["title", "collection_id", "collection_version"])
    op.create_unique_constraint("uq_form_slug_collection", "form", ["slug", "collection_id", "collection_version"])

    # 12. Recreate composite foreign keys
    op.create_foreign_key(
        op.f("fk_submission_collection_id_collection"),
        "submission",
        "collection",
        ["collection_id", "collection_version"],
        ["id", "version"],
    )
    op.create_foreign_key(
        op.f("fk_form_collection_id_collection"),
        "form",
        "collection",
        ["collection_id", "collection_version"],
        ["id", "version"],
    )
