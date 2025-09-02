"""empty message

Revision ID: 035_remove_sections
Revises: 034_drop_all_sections
Create Date: 2025-09-01 17:07:10.368933

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "035_remove_sections"
down_revision = "034_drop_all_sections"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.drop_constraint("fk_form_section_id_section", type_="foreignkey")
        batch_op.drop_column("section_id")

    op.drop_table("section")


def downgrade() -> None:
    op.create_table(
        "section",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column(
            "created_at_utc",
            postgresql.TIMESTAMP(),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column(
            "updated_at_utc",
            postgresql.TIMESTAMP(),
            server_default=sa.text("now()"),
            autoincrement=False,
            nullable=False,
        ),
        sa.Column("title", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("order", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.Column("slug", sa.VARCHAR(), autoincrement=False, nullable=False),
        sa.Column("collection_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("collection_version", sa.INTEGER(), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id", "collection_version"],
            ["collection.id", "collection.version"],
            name="fk_section_collection_id_collection",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_section"),
        sa.UniqueConstraint(
            "collection_id",
            "collection_version",
            "order",
            name="uq_section_order_collection",
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
        sa.UniqueConstraint(
            "collection_id",
            "collection_version",
            "slug",
            name="uq_section_slug_collection",
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
        sa.UniqueConstraint(
            "collection_id",
            "collection_version",
            "title",
            name="uq_section_title_collection",
            postgresql_include=[],
            postgresql_nulls_not_distinct=False,
        ),
    )

    with op.batch_alter_table("form", schema=None) as batch_op:
        batch_op.add_column(sa.Column("section_id", sa.UUID(), autoincrement=False, nullable=True))
        batch_op.create_foreign_key("fk_form_section_id_section", "section", ["section_id"], ["id"])
