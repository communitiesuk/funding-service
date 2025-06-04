"""empty message

Revision ID: 006_restrict_db_cascading
Revises: 005_collection_metadata
Create Date: 2025-06-04 08:25:49.296148

"""

from alembic import op

revision = "006_restrict_db_cascading"
down_revision = "005_collection_metadata"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_constraint("fk_collection_created_by_id_user", type_="foreignkey")
        batch_op.drop_constraint("fk_collection_collection_schema_id_collection_schema", type_="foreignkey")
        batch_op.create_foreign_key(
            batch_op.f("fk_collection_collection_schema_id_collection_schema"),
            "collection_schema",
            ["collection_schema_id", "collection_schema_version"],
            ["id", "version"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_collection_created_by_id_user"), "user", ["created_by_id"], ["id"], ondelete="RESTRICT"
        )

    with op.batch_alter_table("collection_metadata", schema=None) as batch_op:
        batch_op.drop_constraint("fk_collection_metadata_created_by_id_user", type_="foreignkey")
        batch_op.drop_constraint("fk_collection_metadata_form_id_form", type_="foreignkey")
        batch_op.drop_constraint("fk_collection_metadata_collection_id_collection", type_="foreignkey")
        batch_op.create_foreign_key(
            batch_op.f("fk_collection_metadata_created_by_id_user"),
            "user",
            ["created_by_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_collection_metadata_form_id_form"), "form", ["form_id"], ["id"], ondelete="RESTRICT"
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_collection_metadata_collection_id_collection"),
            "collection",
            ["collection_id"],
            ["id"],
            ondelete="RESTRICT",
        )

    with op.batch_alter_table("collection_schema", schema=None) as batch_op:
        batch_op.drop_constraint("fk_collection_schema_created_by_id_user", type_="foreignkey")
        batch_op.drop_constraint("fk_collection_schema_grant_id_grant", type_="foreignkey")
        batch_op.create_foreign_key(
            batch_op.f("fk_collection_schema_created_by_id_user"),
            "user",
            ["created_by_id"],
            ["id"],
            ondelete="RESTRICT",
        )
        batch_op.create_foreign_key(
            batch_op.f("fk_collection_schema_grant_id_grant"), "grant", ["grant_id"], ["id"], ondelete="RESTRICT"
        )

    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.drop_constraint("fk_form_section_id_section", type_="foreignkey")
        batch_op.create_foreign_key(
            batch_op.f("fk_form_section_id_section"), "section", ["section_id"], ["id"], ondelete="RESTRICT"
        )

    with op.batch_alter_table("magic_link", schema=None) as batch_op:
        batch_op.drop_constraint("fk_magic_link_user_id_user", type_="foreignkey")
        batch_op.create_foreign_key(
            batch_op.f("fk_magic_link_user_id_user"), "user", ["user_id"], ["id"], ondelete="RESTRICT"
        )

    with op.batch_alter_table("question", schema=None) as batch_op:
        batch_op.drop_constraint("fk_question_form_id_form", type_="foreignkey")
        batch_op.create_foreign_key(
            batch_op.f("fk_question_form_id_form"), "form", ["form_id"], ["id"], ondelete="RESTRICT"
        )

    with op.batch_alter_table("section", schema=None) as batch_op:
        batch_op.drop_constraint("fk_section_collection_schema_id_collection_schema", type_="foreignkey")
        batch_op.create_foreign_key(
            batch_op.f("fk_section_collection_schema_id_collection_schema"),
            "collection_schema",
            ["collection_schema_id", "collection_schema_version"],
            ["id", "version"],
            ondelete="RESTRICT",
        )


def downgrade() -> None:
    with op.batch_alter_table("section", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_section_collection_schema_id_collection_schema"), type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_section_collection_schema_id_collection_schema",
            "collection_schema",
            ["collection_schema_id", "collection_schema_version"],
            ["id", "version"],
        )

    with op.batch_alter_table("question", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_question_form_id_form"), type_="foreignkey")
        batch_op.create_foreign_key("fk_question_form_id_form", "form", ["form_id"], ["id"])

    with op.batch_alter_table("magic_link", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_magic_link_user_id_user"), type_="foreignkey")
        batch_op.create_foreign_key("fk_magic_link_user_id_user", "user", ["user_id"], ["id"])

    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_form_section_id_section"), type_="foreignkey")
        batch_op.create_foreign_key("fk_form_section_id_section", "section", ["section_id"], ["id"])

    with op.batch_alter_table("collection_schema", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_collection_schema_grant_id_grant"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_collection_schema_created_by_id_user"), type_="foreignkey")
        batch_op.create_foreign_key("fk_collection_schema_grant_id_grant", "grant", ["grant_id"], ["id"])
        batch_op.create_foreign_key("fk_collection_schema_created_by_id_user", "user", ["created_by_id"], ["id"])

    with op.batch_alter_table("collection_metadata", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_collection_metadata_collection_id_collection"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_collection_metadata_form_id_form"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_collection_metadata_created_by_id_user"), type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_collection_metadata_collection_id_collection", "collection", ["collection_id"], ["id"]
        )
        batch_op.create_foreign_key("fk_collection_metadata_form_id_form", "form", ["form_id"], ["id"])
        batch_op.create_foreign_key("fk_collection_metadata_created_by_id_user", "user", ["created_by_id"], ["id"])

    with op.batch_alter_table("collection", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_collection_created_by_id_user"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_collection_collection_schema_id_collection_schema"), type_="foreignkey")
        batch_op.create_foreign_key(
            "fk_collection_collection_schema_id_collection_schema",
            "collection_schema",
            ["collection_schema_id", "collection_schema_version"],
            ["id", "version"],
        )
        batch_op.create_foreign_key("fk_collection_created_by_id_user", "user", ["created_by_id"], ["id"])
