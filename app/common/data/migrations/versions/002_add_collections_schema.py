"""Adds a Collection table for users submitting data against a schema

Revision ID: 002_add_collection
Revises: 001_bootstrap
Create Date: 2025-05-22 14:31:33.583840

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "002_add_collection"
down_revision = "001_bootstrap"
branch_labels = None
depends_on = None

collection_status_enum = sa.Enum("NOT_STARTED", name="collection_status_enum")


def upgrade() -> None:
    op.create_table(
        "collection",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", collection_status_enum, nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("collection_schema_id", sa.Uuid(), nullable=False),
        sa.Column("collection_schema_version", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_schema_id", "collection_schema_version"],
            ["collection_schema.id", "collection_schema.version"],
            name=op.f("fk_collection_collection_schema_id_collection_schema"),
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], name=op.f("fk_collection_created_by_id_user")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection")),
    )


def downgrade() -> None:
    op.drop_table("collection")
    collection_status_enum.drop(op.get_bind())
