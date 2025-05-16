"""Adding section and form tables"

Revision ID: 007_add_section_form
Revises: 006_add_collection_schema
Create Date: 2025-05-15 15:46:51.388552

"""

import sqlalchemy as sa
from alembic import op

revision = "007_add_section_form"
down_revision = "006_add_collection_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "section",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("collection_schema_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_schema_id"],
            ["collection_schema.id"],
            name=op.f("fk_section_collection_schema_id_collection_schema"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_section")),
        sa.UniqueConstraint(
            "order", "collection_schema_id", deferrable=True, name="uq_section_order_collection_schema"
        ),
        sa.UniqueConstraint("slug", "collection_schema_id", name="uq_section_slug_collection_schema"),
        sa.UniqueConstraint("title", "collection_schema_id", name="uq_section_title_collection_schema"),
    )
    op.create_table(
        "form",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("order", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("section_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["section_id"], ["section.id"], name=op.f("fk_form_section_id_section")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_form")),
        sa.UniqueConstraint("order", "section_id", deferrable=True, name="uq_form_order_section"),
        sa.UniqueConstraint("slug", "section_id", name="uq_form_slug_section"),
        sa.UniqueConstraint("title", "section_id", name="uq_form_title_section"),
    )
    with op.batch_alter_table("collection_schema", schema=None) as batch_op:
        batch_op.add_column(sa.Column("slug", sa.String(), nullable=False))


def downgrade() -> None:
    with op.batch_alter_table("collection_schema", schema=None) as batch_op:
        batch_op.drop_column("slug")

    op.drop_table("form")
    op.drop_table("section")
