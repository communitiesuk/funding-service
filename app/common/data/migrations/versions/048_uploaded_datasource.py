"""Abitrary datasource uploads

Revision ID: 048_uploaded_datasource
Revises: 047_non_null_external_id
Create Date: 2026-02-12 10:11:36.240573

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "048_uploaded_datasource"
down_revision = "047_non_null_external_id"
branch_labels = None
depends_on = None


data_source_type_enum = sa.Enum(
    "CUSTOM", "STATIC", "GRANT_RECIPIENT", "PROJECT_LEVEL", name="data_source_type_enum", create_type=False
)


def upgrade() -> None:
    data_source_type_enum.create(op.get_bind())
    op.create_table(
        "data_source_organisation_item",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("data_source_id", sa.Uuid(), nullable=False),
        sa.Column("external_id", sa.String(), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(
            ["data_source_id"],
            ["data_source.id"],
            name=op.f("fk_data_source_organisation_item_data_source_id_data_source"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_data_source_organisation_item")),
        sa.UniqueConstraint("data_source_id", "external_id", name="uq_data_source_external_id"),
    )
    with op.batch_alter_table("data_source_organisation_item", schema=None) as batch_op:
        batch_op.create_index("ix_data_source_organisation_item_data_source_id", ["data_source_id"], unique=False)
        batch_op.create_index("ix_data_source_organisation_item_external_id", ["external_id"], unique=False)

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.add_column(sa.Column("data_source_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            batch_op.f("fk_component_data_source_id_data_source"), "data_source", ["data_source_id"], ["id"]
        )

    op.execute(
        sa.text("""
            UPDATE component
            SET data_source_id = data_source.id
            FROM data_source
            WHERE component.id = data_source.question_id
        """)
    )

    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "type",
                data_source_type_enum,
                nullable=True,
            )
        )
        batch_op.add_column(sa.Column("name", postgresql.CITEXT(), nullable=True))
        batch_op.add_column(sa.Column("grant_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("collection_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("created_by_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("updated_by_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("schema", postgresql.JSONB(astext_type=sa.Text()), nullable=True))
        batch_op.add_column(sa.Column("s3_uri", sa.String, nullable=True))
        batch_op.create_index("ix_data_source_collection_id", ["collection_id"], unique=False)
        batch_op.create_index("ix_data_source_grant_id", ["grant_id"], unique=False)
        batch_op.create_unique_constraint("uq_data_source_name", ["name"])
        batch_op.create_check_constraint(
            "ck_data_source_non_custom_requires_name_grant_collection_and_schema",
            (
                "type = 'CUSTOM' OR "
                "(name IS NOT NULL AND grant_id IS NOT NULL AND collection_id IS NOT NULL AND schema IS NOT NULL)"
            ),
        )
        batch_op.create_check_constraint(
            "ck_data_source_collection_requires_grant",
            "collection_id IS NULL OR grant_id IS NOT NULL",
        )
        batch_op.create_foreign_key(batch_op.f("fk_data_source_grant_id_grant"), "grant", ["grant_id"], ["id"])
        batch_op.create_foreign_key(
            batch_op.f("fk_data_source_collection_id_collection"), "collection", ["collection_id"], ["id"]
        )
        batch_op.create_foreign_key(batch_op.f("fk_data_source_updated_by_id_user"), "user", ["updated_by_id"], ["id"])
        batch_op.create_foreign_key(batch_op.f("fk_data_source_created_by_id_user"), "user", ["created_by_id"], ["id"])

    op.execute(
        sa.text("""
                UPDATE data_source
                SET type = 'CUSTOM'
                """)
    )

    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.alter_column("type", existing_nullable=True, nullable=False)
        batch_op.drop_constraint("uq_question_id", type_="unique")
        batch_op.drop_constraint("fk_data_source_question_id_component", type_="foreignkey")
        batch_op.drop_column("question_id")


def downgrade() -> None:
    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.add_column(sa.Column("question_id", sa.UUID(), autoincrement=False, nullable=True))
        batch_op.create_foreign_key("fk_data_source_question_id_component", "component", ["question_id"], ["id"])

    op.execute(
        sa.text("""
            UPDATE data_source
            SET question_id = component.id
            FROM component
            WHERE data_source.id = component.data_source_id
        """)
    )

    op.execute(
        sa.text("""
            DELETE FROM data_source
            WHERE type != 'CUSTOM'
        """)
    )

    with op.batch_alter_table("data_source", schema=None) as batch_op:
        batch_op.alter_column("question_id", existing_nullable=True, nullable=False)
        batch_op.drop_constraint(batch_op.f("fk_data_source_created_by_id_user"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_data_source_updated_by_id_user"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_data_source_collection_id_collection"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_data_source_grant_id_grant"), type_="foreignkey")
        batch_op.drop_constraint("ck_data_source_non_custom_requires_name_grant_collection_and_schema", type_="check")
        batch_op.drop_constraint("ck_data_source_collection_requires_grant", type_="check")
        batch_op.drop_constraint("uq_data_source_name", type_="unique")
        batch_op.drop_index("ix_data_source_grant_id")
        batch_op.drop_index("ix_data_source_collection_id")
        batch_op.create_unique_constraint("uq_question_id", ["question_id"])
        batch_op.drop_column("s3_uri")
        batch_op.drop_column("schema")
        batch_op.drop_column("updated_by_id")
        batch_op.drop_column("created_by_id")
        batch_op.drop_column("collection_id")
        batch_op.drop_column("grant_id")
        batch_op.drop_column("name")
        batch_op.drop_column("type")

    with op.batch_alter_table("component", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_component_data_source_id_data_source"), type_="foreignkey")
        batch_op.drop_column("data_source_id")

    with op.batch_alter_table("data_source_organisation_item", schema=None) as batch_op:
        batch_op.drop_index("ix_data_source_organisation_item_external_id")
        batch_op.drop_index("ix_data_source_organisation_item_data_source_id")

    op.drop_table("data_source_organisation_item")
    data_source_type_enum.drop(op.get_bind())
