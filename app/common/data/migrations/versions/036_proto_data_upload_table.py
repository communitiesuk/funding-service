"""Add uploaded dataset table

Revision ID: 036_proto_data_upload_table
Revises: 035_remove_static_event_data
Create Date: 2026-01-12 18:28:24.996875

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "036_proto_data_upload_table"
down_revision = "035_remove_static_event_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "uploaded_dataset",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("name", postgresql.CITEXT(), nullable=False),
        sa.Column("grant_id", sa.Uuid(), nullable=True),
        sa.Column("data", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.Column("schema", postgresql.JSONB(astext_type=sa.Text()), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["grant_id"], ["grant.id"], name=op.f("fk_uploaded_dataset_grant_id_grant")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_uploaded_dataset")),
        sa.UniqueConstraint("name", name="uq_uploaded_dataset_name"),
    )


def downgrade() -> None:
    op.drop_table("uploaded_dataset")
