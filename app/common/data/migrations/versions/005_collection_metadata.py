"""empty message

Revision ID: 005_collection_metadata
Revises: 004_add_detailed_grant_fields
Create Date: 2025-06-02 19:49:07.802724

"""

import sqlalchemy as sa
from alembic import op

revision = "005_collection_metadata"
down_revision = "004_add_detailed_grant_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "collection_metadata",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at_utc", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("event_key", sa.Enum("FORM_RUNNER_FORM_COMPLETED", name="metadata_event_key_enum"), nullable=False),
        sa.Column("collection_id", sa.Uuid(), nullable=False),
        sa.Column("form_id", sa.Uuid(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["collection_id"], ["collection.id"], name=op.f("fk_collection_metadata_collection_id_collection")
        ),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], name=op.f("fk_collection_metadata_created_by_id_user")),
        sa.ForeignKeyConstraint(["form_id"], ["form.id"], name=op.f("fk_collection_metadata_form_id_form")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_collection_metadata")),
    )


def downgrade() -> None:
    op.drop_table("collection_metadata")
